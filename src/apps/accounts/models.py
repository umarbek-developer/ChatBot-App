"""Account-adjacent models: profile, devices and login sessions.

The existing ``apps.users.User`` stays the auth identity and is deliberately not
modified. Everything that would otherwise bloat that model — presence hints,
avatars, per-device push tokens, session bookkeeping — lives here, keyed off the
user via one-to-one / foreign keys. This keeps auth stable while giving the
messaging platform the richer account surface it needs.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel, TimeStampedModel, UUIDPrimaryKeyModel


class Profile(BaseModel):
    """Public-facing user profile. One row per user, auto-created on signup."""

    class Status(models.TextChoices):
        ONLINE = "online", "Online"
        AWAY = "away", "Away"
        BUSY = "busy", "Busy"
        OFFLINE = "offline", "Offline"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    display_name = models.CharField(max_length=150, blank=True)
    username = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        help_text="Public @handle, unique across the platform.",
    )
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    banner = models.ImageField(upload_to="banners/", null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OFFLINE)
    status_text = models.CharField(max_length=140, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["username"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return self.display_name or self.username or str(self.user_id)

    def touch_last_seen(self) -> None:
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at", "updated_at"])


class Device(BaseModel):
    """A client install (browser, iOS, Android) tied to a user.

    Push tokens and per-device revocation live here so "logout this device" and
    push fan-out both have a stable anchor independent of JWT lifetimes.
    """

    class Platform(models.TextChoices):
        WEB = "web", "Web"
        IOS = "ios", "iOS"
        ANDROID = "android", "Android"
        DESKTOP = "desktop", "Desktop"
        UNKNOWN = "unknown", "Unknown"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="devices",
    )
    device_id = models.CharField(
        max_length=255,
        help_text="Stable client-generated identifier for this install.",
    )
    name = models.CharField(max_length=150, blank=True)
    platform = models.CharField(max_length=16, choices=Platform.choices, default=Platform.UNKNOWN)
    push_token = models.CharField(max_length=512, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_active_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-last_active_at", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "device_id"],
                name="uniq_device_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_platform_display()} · {self.name or self.device_id}"


class Session(UUIDPrimaryKeyModel, TimeStampedModel):
    """A login session, one per issued refresh token.

    Bridges JWT (stateless) with a stateful, revocable record so the platform
    can list "active sessions", revoke one, or "log out everywhere". The
    ``refresh_jti`` links back to SimpleJWT's OutstandingToken for blacklisting.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        related_name="sessions",
        null=True,
        blank=True,
    )
    refresh_jti = models.CharField(max_length=255, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "revoked_at"]),
            models.Index(fields=["refresh_jti"]),
        ]

    def __str__(self) -> str:
        state = "revoked" if self.is_revoked else "active"
        return f"Session<{self.user_id}> {state}"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])
