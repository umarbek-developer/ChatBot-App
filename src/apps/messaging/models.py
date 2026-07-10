"""Persistent chat messages, reactions and read receipts.

These back the realtime layer: the WebSocket consumer writes here on every send
so history survives reloads/reconnects and message state (sent → delivered →
read) is server-authoritative rather than a client illusion.

Identity note: the chat supports both authenticated users and lightweight
guests, so every actor is tracked by a stable ``*_key`` string (the user UUID
for members, a client-generated id for guests). ``sender`` is a nullable FK kept
in sync for members, enabling joins/attribution without breaking guest flows.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel


class Message(BaseModel):
    class Kind(models.TextChoices):
        TEXT = "text", "Text"
        IMAGE = "image", "Image"
        VOICE = "voice", "Voice"
        FILE = "file", "File"
        SYSTEM = "system", "System"

    room = models.CharField(max_length=140, db_index=True)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="messages", null=True, blank=True,
    )
    sender_key = models.CharField(max_length=64, db_index=True)
    sender_name = models.CharField(max_length=120)
    sender_color = models.CharField(max_length=9, default="#64748B")

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TEXT)
    text = models.TextField(blank=True)
    attachment_url = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(default=0)  # voice length

    reply_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, related_name="replies", null=True, blank=True
    )
    client_id = models.CharField(max_length=64, blank=True, db_index=True)

    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=["room", "created_at"]),
            models.Index(fields=["room", "is_deleted", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.room}] {self.sender_name}: {self.text[:32]}"

    def to_event(self) -> dict[str, Any]:
        """Serialise to the wire shape shared by REST history and WS broadcast."""
        return {
            "id": str(self.id),
            "client_id": self.client_id,
            "room": self.room,
            "kind": self.kind,
            "authorId": self.sender_key,
            "author": self.sender_name,
            "color": self.sender_color,
            "text": "" if self.is_deleted else self.text,
            "image": "" if self.is_deleted else (self.attachment_url if self.kind == self.Kind.IMAGE else ""),
            "audio": "" if self.is_deleted else (self.attachment_url if self.kind == self.Kind.VOICE else ""),
            "duration_ms": self.duration_ms,
            "waveform": [] if self.is_deleted else self._waveform(),
            "reply_to": self._reply_payload(),
            "edited": self.is_edited,
            "deleted": self.is_deleted,
            "ts": int(self.created_at.timestamp() * 1000),
            "reactions": self.reaction_summary(),
        }

    def _waveform(self) -> list[int]:
        if self.kind != self.Kind.VOICE:
            return []
        voice = getattr(self, "voice", None)
        return voice.waveform if voice else []

    def _reply_payload(self) -> dict[str, Any] | None:
        if not self.reply_to_id:
            return None
        r = self.reply_to
        return {"id": str(r.id), "author": r.sender_name, "text": (r.text[:120] or "Attachment")}

    def reaction_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for r in self.reactions.all():
            summary[r.emoji] = summary.get(r.emoji, 0) + 1
        return summary


class Reaction(BaseModel):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reactions")
    emoji = models.CharField(max_length=16)
    actor_key = models.CharField(max_length=64, db_index=True)
    actor_name = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "emoji", "actor_key"], name="uniq_reaction_per_actor"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.emoji} by {self.actor_name}"


class ReadReceipt(BaseModel):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="receipts")
    reader_key = models.CharField(max_length=64, db_index=True)
    reader_name = models.CharField(max_length=120, blank=True)
    read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["message", "reader_key"], name="uniq_receipt_per_reader"),
        ]
        indexes = [models.Index(fields=["message", "reader_key"])]

    def __str__(self) -> str:
        return f"read {self.message_id} by {self.reader_name}"


class MessageEditHistory(BaseModel):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="edit_history")
    previous_text = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"edit@{self.created_at:%H:%M} of {self.message_id}"


def _voice_upload_path(instance: "VoiceMessage", filename: str) -> str:
    return f"voice/{instance.message.room}/{instance.message_id}.webm"


class VoiceMessage(BaseModel):
    """Audio payload + metadata for a voice ``Message`` (kind=voice).

    Consolidates what the brief split as VoiceAttachment (the file) and
    VoiceMetadata (duration/size/waveform) into one row — a 1:1 with Message —
    to avoid three-table joins on the hot timeline path. Swap the FileField
    storage backend to S3/MinIO in production without touching this model.
    """

    message = models.OneToOneField(Message, on_delete=models.CASCADE, related_name="voice")
    audio = models.FileField(upload_to=_voice_upload_path, max_length=255)
    mime = models.CharField(max_length=60, default="audio/webm")
    duration_ms = models.PositiveIntegerField(default=0)
    file_size = models.PositiveIntegerField(default=0)
    waveform = models.JSONField(default=list, blank=True, help_text="Normalised 0-100 amplitude bars.")

    class Meta:
        indexes = [models.Index(fields=["message"])]

    def __str__(self) -> str:
        return f"voice {self.duration_ms}ms for {self.message_id}"

    @property
    def url(self) -> str:
        try:
            return self.audio.url
        except ValueError:
            return ""


class PlayedReceipt(BaseModel):
    """Records that a listener played a voice message (Telegram 'played' state)."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="plays")
    player_key = models.CharField(max_length=64, db_index=True)
    player_name = models.CharField(max_length=120, blank=True)
    played_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["message", "player_key"], name="uniq_play_per_listener"),
        ]

    def __str__(self) -> str:
        return f"played {self.message_id} by {self.player_name}"
