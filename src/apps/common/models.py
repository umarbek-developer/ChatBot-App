"""Abstract model building blocks shared by every feature app.

Composition over a single god-mixin: an app picks exactly the guarantees it
needs (UUID PK, timestamps, soft-delete, audit trail) or grabs ``BaseModel``
which wires the common four together. This keeps migrations predictable and
makes the intent of each concrete model obvious from its bases.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.managers import SoftDeleteManager


class UUIDPrimaryKeyModel(models.Model):
    """Non-sequential, non-enumerable primary key for every public entity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Logical deletion. Rows are tombstoned, never physically removed by default."""

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = SoftDeleteManager(alive_only=False)

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents: bool = False, hard: bool = False):  # type: ignore[override]
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
        return None

    def restore(self) -> None:
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class AuditModel(models.Model):
    """Tracks which user created/updated a row.

    ``related_name`` uses ``%(app_label)s_%(class)s`` so the reverse accessors
    never collide across apps — the bug the legacy ``apps.utils.BaseModel`` has.
    """

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_created",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_updated",
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True


class BaseModel(UUIDPrimaryKeyModel, TimeStampedModel, SoftDeleteModel):
    """The default base for domain entities: UUID + timestamps + soft-delete."""

    class Meta:
        abstract = True
        ordering = ("-created_at",)


class AuditableBaseModel(BaseModel, AuditModel):
    """``BaseModel`` plus created_by/updated_by attribution."""

    class Meta:
        abstract = True
        ordering = ("-created_at",)


class AuditLog(UUIDPrimaryKeyModel):
    """Append-only record of security- and business-critical actions.

    Written by services (never by views directly) so the trail reflects domain
    intent rather than HTTP mechanics.
    """

    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        JOIN = "join", "Join"
        LEAVE = "leave", "Leave"
        KICK = "kick", "Kick"
        BAN = "ban", "Ban"
        MUTE = "mute", "Mute"
        INVITE = "invite", "Invite"
        ROLE_CHANGE = "role_change", "Role change"
        OTHER = "other", "Other"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=32, choices=Action.choices, db_index=True)
    target_type = models.CharField(max_length=100, blank=True, db_index=True)
    target_id = models.CharField(max_length=64, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["actor", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} · {self.target_type}:{self.target_id}"
