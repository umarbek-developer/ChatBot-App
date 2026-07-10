"""Integration test for voice message upload.

Exercises the real HTTP endpoint (auth + multipart + validation + service) and
asserts persistence and the standardized response envelope.
"""
from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient


def _audio(name="v.webm"):
    return SimpleUploadedFile(name, b"OpusHead-fake-audio-" * 64, content_type="audio/webm")


@pytest.fixture
def user(db):
    from apps.users.models import User
    u = User.objects.create_user(email="voicer@test.dev", password="Str0ng!pw", first_name="Voi")
    u.is_active = True
    u.save()
    return u


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {user.token()['access_token']}")
    return client


@pytest.mark.django_db
def test_voice_upload_persists_and_returns_event(auth_client):
    from apps.messaging.models import Message, VoiceMessage

    resp = auth_client.post("/api/v1/voice/", {
        "room": "test-room", "audio": _audio(), "duration_ms": 3200,
        "client_id": "abc", "waveform": "[10, 50, 90, 30]",
    }, format="multipart")

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["success"] is True
    event = body["data"]
    assert event["kind"] == "voice"
    assert event["duration_ms"] == 3200
    assert event["waveform"] == [10, 50, 90, 30]
    assert "/media/voice/" in event["audio"]

    msg = Message.objects.get(id=event["id"])
    assert msg.kind == Message.Kind.VOICE
    assert VoiceMessage.objects.filter(message=msg).exists()

    # cleanup uploaded file
    VoiceMessage.objects.get(message=msg).audio.delete(save=False)


@pytest.mark.django_db
def test_voice_upload_rejects_oversized_duration(auth_client):
    resp = auth_client.post("/api/v1/voice/", {
        "room": "test-room", "audio": _audio(), "duration_ms": 999_999_999,
    }, format="multipart")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_voice_upload_requires_auth():
    resp = APIClient().post("/api/v1/voice/", {
        "room": "r", "audio": _audio(), "duration_ms": 1000,
    }, format="multipart")
    assert resp.status_code == 401
