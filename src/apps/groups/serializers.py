"""Serializers for the groups API — presentation only, no business logic."""
from __future__ import annotations

from rest_framework import serializers

from apps.groups.models import Group, GroupMember, Invite, JoinRequest


class UserBriefSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    full_name = serializers.CharField(read_only=True)


class GroupSerializer(serializers.ModelSerializer):
    owner = UserBriefSerializer(read_only=True)

    class Meta:
        model = Group
        fields = [
            "id", "name", "slug", "description", "rules", "visibility",
            "owner", "avatar", "banner", "pinned_announcement",
            "slow_mode_seconds", "member_count", "created_at",
        ]
        read_only_fields = ["id", "slug", "owner", "member_count", "created_at"]


class GroupCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    rules = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
    visibility = serializers.ChoiceField(
        choices=Group.Visibility.choices, default=Group.Visibility.PUBLIC
    )


class GroupUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    rules = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    visibility = serializers.ChoiceField(choices=Group.Visibility.choices, required=False)
    pinned_announcement = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    slow_mode_seconds = serializers.IntegerField(min_value=0, max_value=21600, required=False)


class GroupMemberSerializer(serializers.ModelSerializer):
    user = UserBriefSerializer(read_only=True)
    is_muted = serializers.BooleanField(read_only=True)

    class Meta:
        model = GroupMember
        fields = ["id", "user", "role", "status", "nickname", "is_muted", "joined_at"]


class InviteSerializer(serializers.ModelSerializer):
    is_usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invite
        fields = ["id", "code", "max_uses", "uses", "expires_at", "is_revoked", "is_usable", "created_at"]
        read_only_fields = fields


class JoinRequestSerializer(serializers.ModelSerializer):
    user = UserBriefSerializer(read_only=True)

    class Meta:
        model = JoinRequest
        fields = ["id", "user", "message", "status", "created_at", "decided_at"]
        read_only_fields = fields
