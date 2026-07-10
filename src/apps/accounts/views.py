"""Authenticated account API: current user, profile editing, sessions, logout.

Thin views over the accounts models + ``SessionService``. Every endpoint here
requires a valid JWT, which is exactly what makes the frontend able to answer
"am I logged in and who am I?" over HTTP (the fix for the guest-mode bug).
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Profile, Session
from apps.accounts.serializers import MeSerializer, ProfileUpdateSerializer, SessionSerializer
from apps.accounts.services import SessionService
from apps.common.response import ok

session_service = SessionService()

_USER_FIELDS = {"phone_number", "first_name", "last_name"}
_PROFILE_FIELDS = {"username", "display_name", "bio", "status_text"}


class MeView(APIView):
    """GET current user+profile; PATCH to edit profile/basic fields."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return ok(MeSerializer(request.user, context={"request": request}).data)

    def patch(self, request: Request):
        ser = ProfileUpdateSerializer(data=request.data, context={"request": request}, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        user = request.user
        profile, _ = Profile.objects.get_or_create(user=user)

        user_dirty, profile_dirty = [], []
        for field, value in data.items():
            if field in _USER_FIELDS:
                setattr(user, field, value)
                user_dirty.append(field)
            elif field in _PROFILE_FIELDS:
                setattr(profile, field, value or "")
                profile_dirty.append(field)
            elif field == "username":
                profile.username = value or None
                profile_dirty.append("username")
        if user_dirty:
            user.save(update_fields=user_dirty)
        if profile_dirty:
            profile.save()
        return ok(MeSerializer(user, context={"request": request}).data, message="Profile updated.")


class AvatarView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request):
        file = request.FILES.get("avatar")
        if not file:
            return ok({"error": "No file"}, message="No avatar provided.")
        if file.size > 5 * 1024 * 1024:
            from apps.common.exceptions import ValidationErrorLike
            raise ValidationErrorLike("Avatar must be under 5 MB.")
        if not (file.content_type or "").startswith("image/"):
            from apps.common.exceptions import ValidationErrorLike
            raise ValidationErrorLike("Avatar must be an image.")
        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.avatar = file
        profile.save(update_fields=["avatar", "updated_at"])
        return ok(MeSerializer(request.user, context={"request": request}).data, message="Avatar updated.")


class SessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        current_jti = getattr(request.auth, "payload", {}).get("jti") if request.auth else None
        qs = Session.objects.filter(user=request.user, revoked_at__isnull=True).order_by("-created_at")
        return ok(SessionSerializer(qs, many=True, context={"current_jti": current_jti}).data)


class LogoutView(APIView):
    """Blacklist the supplied refresh token (log out this device)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request):
        refresh = request.data.get("refresh") or request.data.get("refresh_token")
        if refresh:
            try:
                token = RefreshToken(refresh)
                jti = str(token.get("jti", ""))
                token.blacklist()
                Session.objects.filter(user=request.user, refresh_jti=jti).update(revoked_at=timezone.now())
            except TokenError:
                pass
        return ok(message="Logged out.")


class LogoutAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request):
        count = session_service.logout_all(user=request.user)
        return ok({"revoked": count}, message=f"Signed out of {count} session(s).")
