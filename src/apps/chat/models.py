"""Call history model.

WebRTC media is peer-to-peer and never touches the server; only *signaling*
flows through Django Channels. This model records the call lifecycle (who called
whom, type, timing, outcome) so users get a real call log — the durable
by-product of the ephemeral signaling handled in ``call_consumers``.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel


class Call(BaseModel):
    class Type(models.TextChoices):
        VOICE = "voice", "Voice"
        VIDEO = "video", "Video"

    class Status(models.TextChoices):
        RINGING = "ringing", "Ringing"
        ONGOING = "ongoing", "Ongoing"
        ENDED = "ended", "Ended"
        REJECTED = "rejected", "Rejected"
        MISSED = "missed", "Missed"
        BUSY = "busy", "Busy"
        CANCELED = "canceled", "Canceled"

    caller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calls_made"
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calls_received"
    )
    room = models.CharField(max_length=140, blank=True, help_text="Group/room context, if any.")
    call_type = models.CharField(max_length=6, choices=Type.choices, default=Type.VOICE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RINGING, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)   # when answered
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["caller", "-created_at"]),
            models.Index(fields=["receiver", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.call_type} {self.caller_id}->{self.receiver_id} ({self.status})"

    @property
    def duration_seconds(self) -> int:
        if self.started_at and self.ended_at:
            return max(0, int((self.ended_at - self.started_at).total_seconds()))
        return 0

    def mark(self, status: str, *, answered: bool = False) -> None:
        self.status = status
        now = timezone.now()
        if answered and not self.started_at:
            self.started_at = now
        if status in (self.Status.ENDED, self.Status.REJECTED, self.Status.MISSED,
                      self.Status.BUSY, self.Status.CANCELED) and not self.ended_at:
            self.ended_at = now
        self.save(update_fields=["status", "started_at", "ended_at", "updated_at"])
