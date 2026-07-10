"""Messaging services — voice message creation and realtime fan-out.

Binary audio arrives over HTTP (authenticated, validated, with real upload
progress) rather than base64-over-WebSocket. Once persisted, the service pushes
a standard ``message`` event into the room's channel-layer group so every
connected client renders the voice bubble through the exact same path as text
messages (timeline, unread, replies, reactions, receipts).
"""
from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from apps.common.exceptions import ValidationErrorLike
from apps.common.services import BaseService
from apps.messaging.models import Message, PlayedReceipt, VoiceMessage

logger = logging.getLogger("apps")

_PALETTE = ["#3B82F6", "#8B5CF6", "#EC4899", "#22C55E", "#F59E0B", "#06B6D4", "#EF4444", "#14B8A6"]


def color_for(seed: str) -> str:
    return _PALETTE[sum(map(ord, seed)) % len(_PALETTE)]


def broadcast_event(room: str, event: dict[str, Any]) -> None:
    """Push an event to everyone in a room's channel group (sync-callable).

    Best-effort: a realtime notification failure (e.g. Redis/channel layer down)
    must NEVER break the database write or HTTP response that triggered it. Any
    error is logged and swallowed so the caller's operation still succeeds.
    """
    layer = get_channel_layer()
    if layer is None:  # pragma: no cover
        return
    try:
        async_to_sync(layer.group_send)(f"chat_{room}", {"type": "fanout", "event": event})
    except Exception:
        logger.exception(
            "Realtime broadcast failed (room=%s, event=%s); continuing without it",
            room, event.get("type"),
        )


class VoiceService(BaseService):
    MAX_SIZE = 12 * 1024 * 1024                 # 12 MB
    MAX_DURATION_MS = 5 * 60 * 1000             # 5 minutes
    ALLOWED_MIME = {
        "audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav",
    }

    def create(
        self,
        *,
        user: Any,
        room: str,
        audio_file: Any,
        duration_ms: int,
        waveform: list[int] | None = None,
        client_id: str = "",
        reply_to_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate(audio_file, duration_ms)
        room = (room or "").strip()[:140]
        if not room:
            raise ValidationErrorLike("A room is required.")

        sender_key = str(user.pk)
        sender_name = (user.get_full_name() or "").strip() or user.email.split("@")[0]
        reply_to = None
        if reply_to_id:
            reply_to = Message.objects.filter(id=reply_to_id, room=room).first()

        with transaction.atomic():
            msg = Message.objects.create(
                room=room, sender=user, sender_key=sender_key, sender_name=sender_name,
                sender_color=color_for(sender_key), kind=Message.Kind.VOICE,
                duration_ms=min(int(duration_ms), self.MAX_DURATION_MS),
                client_id=client_id[:64], reply_to=reply_to,
            )
            voice = VoiceMessage.objects.create(
                message=msg, audio=audio_file, mime=getattr(audio_file, "content_type", "audio/webm"),
                duration_ms=min(int(duration_ms), self.MAX_DURATION_MS),
                file_size=getattr(audio_file, "size", 0),
                waveform=self._clean_waveform(waveform),
            )
            msg.attachment_url = voice.url
            msg.save(update_fields=["attachment_url", "updated_at"])

        event = msg.to_event()
        broadcast_event(room, {"type": "message", "message": event})
        return event

    def _validate(self, audio_file: Any, duration_ms: int) -> None:
        if audio_file is None:
            raise ValidationErrorLike("No audio file was provided.")
        size = getattr(audio_file, "size", 0)
        if size <= 0:
            raise ValidationErrorLike("The audio file is empty.")
        if size > self.MAX_SIZE:
            raise ValidationErrorLike("Voice message exceeds the 12 MB limit.")
        mime = (getattr(audio_file, "content_type", "") or "").split(";")[0].strip()
        # Some browsers/clients label audio blobs as octet-stream; accept that as a
        # fallback but still reject clearly-wrong types (image/*, video/*, etc.).
        if mime and mime != "application/octet-stream" and mime not in self.ALLOWED_MIME:
            raise ValidationErrorLike(f"Unsupported audio format: {mime}.")
        if int(duration_ms or 0) > self.MAX_DURATION_MS:
            raise ValidationErrorLike("Voice message exceeds the 5 minute limit.")

    @staticmethod
    def _clean_waveform(waveform: list[int] | None) -> list[int]:
        if not isinstance(waveform, list):
            return []
        cleaned = []
        for v in waveform[:256]:
            try:
                cleaned.append(max(0, min(100, int(v))))
            except (TypeError, ValueError):
                cleaned.append(0)
        return cleaned
