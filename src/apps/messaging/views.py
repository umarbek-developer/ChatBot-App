"""Messaging HTTP API — voice upload.

Thin: validate → delegate to ``VoiceService`` (which persists + broadcasts) →
return the message event so the caller can reconcile its optimistic bubble.
Authenticated + throttled to blunt spam; the service enforces size/duration/mime.
"""
from __future__ import annotations

from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.response import created
from apps.messaging.serializers import VoiceUploadSerializer
from apps.messaging.services import VoiceService

voice_service = VoiceService()


class VoiceUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "voice"

    def post(self, request: Request):
        ser = VoiceUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        event = voice_service.create(
            user=request.user,
            room=data["room"],
            audio_file=data["audio"],
            duration_ms=data["duration_ms"],
            waveform=data["waveform"],
            client_id=data.get("client_id", ""),
            reply_to_id=data.get("reply_to_id") or None,
        )
        return created(event, message="Voice message sent.")
