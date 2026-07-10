"""WebSocket integration test for WebRTC call signaling.

Drives two authenticated peers through the real ASGI stack (JWT middleware →
CallConsumer → Redis channel layer) and asserts the offer/answer/ICE relay and
the persisted Call record.
"""
from __future__ import annotations

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from config.asgi import application


async def _recv(comm, type_, tries=10):
    for _ in range(tries):
        msg = await comm.receive_json_from(timeout=3)
        if msg.get("type") == type_:
            return msg
    raise AssertionError(f"did not receive {type_}")


@database_sync_to_async
def _make_user(email):
    from apps.users.models import User
    User.objects.filter(email=email).delete()
    u = User.objects.create_user(email=email, password="Str0ng!pw", first_name=email.split("@")[0])
    u.is_active = True
    u.save()
    return u, u.token()["access_token"]


@database_sync_to_async
def _call_count(caller_id):
    from apps.chat.models import Call
    return Call.objects.filter(caller_id=caller_id).count()


@database_sync_to_async
def _call_status(call_id):
    from apps.chat.models import Call
    return Call.objects.get(id=call_id).status


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_call_offer_answer_ice_signaling():
    caller, ctok = await _make_user("caller@test.dev")
    callee, rtok = await _make_user("callee@test.dev")

    a = WebsocketCommunicator(application, f"/ws/call/?token={ctok}")
    b = WebsocketCommunicator(application, f"/ws/call/?token={rtok}")
    assert (await a.connect())[0]
    assert (await b.connect())[0]

    # Caller sends an offer targeting the callee.
    await a.send_json_to({
        "type": "call.offer", "to": str(callee.pk),
        "call_type": "video", "sdp": {"type": "offer", "sdp": "v=0..."},
    })

    incoming = await _recv(b, "call.incoming")
    assert incoming["from"]["id"] == str(caller.pk)
    assert incoming["call_type"] == "video"
    call_id = incoming["call_id"]
    assert await _call_count(caller.pk) == 1
    assert await _call_status(call_id) == "ringing"

    # Callee answers -> caller receives answer, call becomes ongoing.
    await b.send_json_to({
        "type": "call.answer", "to": str(caller.pk),
        "call_id": call_id, "sdp": {"type": "answer", "sdp": "v=0..."},
    })
    answer = await _recv(a, "call.answer")
    assert answer["call_id"] == call_id
    assert await _call_status(call_id) == "ongoing"

    # ICE candidates relay both ways.
    await a.send_json_to({"type": "call.ice_candidate", "to": str(callee.pk),
                          "call_id": call_id, "candidate": {"candidate": "abc"}})
    ice = await _recv(b, "call.ice_candidate")
    assert ice["candidate"]["candidate"] == "abc"

    # Hang up -> peer notified, call ended.
    await a.send_json_to({"type": "call.end", "to": str(callee.pk), "call_id": call_id})
    ended = await _recv(b, "call.ended")
    assert ended["call_id"] == call_id
    assert await _call_status(call_id) == "ended"

    await a.disconnect()
    await b.disconnect()
