"""Group domain models.

A ``Group`` is the platform's shared conversation space (Telegram/Discord-style).
Its ``slug`` doubles as the realtime channel identifier, so the existing
WebSocket room routing (``ws/chat/<slug>/``) keeps working unchanged while the
group gains real membership, roles, invites and moderation state.

Design notes
------------
* Standard role hierarchy (owner/admin/moderator/member) lives on
  ``GroupMember.role``; fine-grained custom roles are modelled by ``Role`` and
  attached via ``GroupMember.custom_role`` — permissions resolve to the union of
  both (see ``apps.groups.permissions``).
* Membership is a durable row keyed ``(group, user)``: joining/leaving/kicking
  flips ``status`` rather than churning rows, which preserves history and keeps
  ban enforcement simple.
* ``member_count`` is denormalised for cheap listing and kept in sync by the
  service layer (with a signal safety-net).
"""
from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from apps.common.models import AuditableBaseModel, BaseModel


def _invite_code() -> str:
    return secrets.token_urlsafe(8)


class Group(AuditableBaseModel):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"          # anyone can find & join instantly
        PRIVATE = "private", "Private"       # discoverable, join needs approval
        INVITE = "invite", "Invite-only"     # hidden, join only via invite link

    name = models.CharField(max_length=120)
    # Uniqueness is enforced by partial constraints below (active rows only), so a
    # name/slug becomes reusable once a group is soft-deleted. Hence no unique=True.
    slug = models.SlugField(max_length=140, db_index=True)
    description = models.TextField(max_length=1000, blank=True)
    rules = models.TextField(max_length=4000, blank=True)
    visibility = models.CharField(
        max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC, db_index=True
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_groups"
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="deleted_groups", null=True, blank=True,
    )
    avatar = models.ImageField(upload_to="groups/avatars/", null=True, blank=True)
    banner = models.ImageField(upload_to="groups/banners/", null=True, blank=True)

    pinned_announcement = models.TextField(max_length=2000, blank=True)
    slow_mode_seconds = models.PositiveIntegerField(default=0)
    member_count = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["visibility", "-member_count"]),
            models.Index(fields=["owner", "-created_at"]),
        ]
        constraints = [
            # Case-insensitive unique name among *active* groups. A soft-deleted
            # group frees its name for reuse (Telegram/Slack behaviour).
            models.UniqueConstraint(
                Lower("name"), condition=Q(is_deleted=False), name="uniq_active_group_name_ci",
            ),
            models.UniqueConstraint(
                "slug", condition=Q(is_deleted=False), name="uniq_active_group_slug",
            ),
        ]

    def __str__(self) -> str:
        return f"#{self.slug}"

    @property
    def is_public(self) -> bool:
        return self.visibility == self.Visibility.PUBLIC


class Role(BaseModel):
    """Optional custom role with a fine-grained permission set (JSON list)."""

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=60)
    color = models.CharField(max_length=9, default="#94A3B8")
    priority = models.PositiveIntegerField(default=0, help_text="Higher wins in conflicts.")
    permissions = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("-priority", "name")
        constraints = [
            models.UniqueConstraint(fields=["group", "name"], name="uniq_role_name_per_group"),
        ]

    def __str__(self) -> str:
        return f"{self.name} @ {self.group.slug}"


class GroupMember(BaseModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MODERATOR = "moderator", "Moderator"
        MEMBER = "member", "Member"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        LEFT = "left", "Left"
        KICKED = "kicked", "Kicked"
        BANNED = "banned", "Banned"

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_memberships"
    )
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.MEMBER, db_index=True)
    custom_role = models.ForeignKey(
        "groups.Role", on_delete=models.SET_NULL, related_name="members", null=True, blank=True
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    nickname = models.CharField(max_length=60, blank=True)
    muted_until = models.DateTimeField(null=True, blank=True)
    is_pinned = models.BooleanField(default=False)      # user pinned this chat
    notifications_muted = models.BooleanField(default=False)
    last_read_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-role", "joined_at")
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="uniq_member_per_group"),
        ]
        indexes = [
            models.Index(fields=["group", "status"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} · {self.role} @ {self.group.slug}"

    @property
    def is_active_member(self) -> bool:
        return self.status == self.Status.ACTIVE

    @property
    def is_muted(self) -> bool:
        return self.muted_until is not None and self.muted_until > timezone.now()


class Invite(BaseModel):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="invites")
    code = models.CharField(max_length=32, unique=True, default=_invite_code, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="created_invites", null=True
    )
    max_uses = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    uses = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["group", "is_revoked"])]

    def __str__(self) -> str:
        return f"invite:{self.code} → {self.group.slug}"

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= timezone.now()

    @property
    def is_exhausted(self) -> bool:
        return self.max_uses > 0 and self.uses >= self.max_uses

    @property
    def is_usable(self) -> bool:
        return not (self.is_revoked or self.is_expired or self.is_exhausted)


class JoinRequest(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="join_requests")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="join_requests"
    )
    message = models.CharField(max_length=300, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="decided_join_requests", null=True, blank=True,
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["group", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "user"],
                condition=models.Q(status="pending"),
                name="uniq_pending_request_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"join:{self.user_id} → {self.group.slug} ({self.status})"
