"""Serializers for messaging (voice upload + read history)."""
from __future__ import annotations

import json

from rest_framework import serializers

from apps.messaging.models import Message


class VoiceUploadSerializer(serializers.Serializer):
    room = serializers.CharField(max_length=140)
    audio = serializers.FileField()
    duration_ms = serializers.IntegerField(min_value=0, max_value=5 * 60 * 1000)
    client_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    reply_to_id = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    waveform = serializers.CharField(required=False, allow_blank=True, default="[]")

    def validate_waveform(self, value: str) -> list[int]:
        if not value:
            return []
        try:
            data = json.loads(value)
        except (ValueError, TypeError):
            return []
        return data if isinstance(data, list) else []


class MessageHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "room", "kind", "sender_name", "text", "attachment_url",
                  "duration_ms", "is_edited", "is_deleted", "created_at"]
