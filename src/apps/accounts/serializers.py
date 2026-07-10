"""Serializers for the authenticated account surface (me / profile / sessions)."""
from __future__ import annotations

import re

from rest_framework import serializers

from apps.accounts.models import Profile, Session
from apps.users.models import User

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


class MeSerializer(serializers.Serializer):
    """Read model for the current user + profile (the single source of auth truth)."""

    def to_representation(self, user: User) -> dict:
        p: Profile | None = getattr(user, "profile", None)
        request = self.context.get("request")

        def media(field):
            if p and field and hasattr(field, "url"):
                url = field.url
                return request.build_absolute_uri(url) if request else url
            return None

        return {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "language": user.language,
            "is_active": user.is_active,
            "profile": {
                "username": p.username if p else None,
                "display_name": (p.display_name if p and p.display_name else user.full_name).strip(),
                "bio": p.bio if p else "",
                "avatar": media(p.avatar) if p else None,
                "banner": media(p.banner) if p else None,
                "status": p.status if p else Profile.Status.OFFLINE,
                "status_text": p.status_text if p else "",
                "last_seen_at": p.last_seen_at if p else None,
                "is_verified": p.is_verified if p else False,
            },
        }


class ProfileUpdateSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True, max_length=32)
    display_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    bio = serializers.CharField(required=False, allow_blank=True, max_length=500)
    status_text = serializers.CharField(required=False, allow_blank=True, max_length=140)
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=13)
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)

    def validate_username(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            return value
        if not _USERNAME_RE.match(value):
            raise serializers.ValidationError("3-32 chars: letters, numbers and underscores only.")
        user = self.context["request"].user
        clash = Profile.objects.filter(username__iexact=value).exclude(user=user).exists()
        if clash:
            raise serializers.ValidationError("This username is already taken.")
        return value


class SessionSerializer(serializers.ModelSerializer):
    device_name = serializers.SerializerMethodField()
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = Session
        fields = ["id", "device_name", "ip_address", "user_agent", "created_at",
                  "last_used_at", "expires_at", "revoked_at", "is_current"]

    def get_device_name(self, obj: Session) -> str:
        return str(obj.device) if obj.device_id else "Unknown device"

    def get_is_current(self, obj: Session) -> bool:
        return str(obj.refresh_jti) == str(self.context.get("current_jti") or "")
