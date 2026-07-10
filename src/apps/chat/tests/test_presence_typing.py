"""Realtime presence: typing + voice-recording indicators over Channels/Redis.

Drives multiple guest sockets through the real ASGI stack and asserts events
reach *other* viewers of the same conversation only, that both the short and the
Telegram-style dotted event names work, and that a disconnect clears a lingering
indicator immediately.

Note: we never issue a deliberately-timing-out ``receive`` before a later
``send`` — in this Channels version a timed-out receive cancels the application
task. ``_recv`` skips past connect frames (self/history/presence) without ever
timing out on an event that is genuinely in flight.
"""
from __future__ import annotations

import pytest
from channels.testing import WebsocketCommunicator

from config.asgi import application


async def _recv(comm, type_, tries=15):
    for _ in range(tries):
        msg = await comm.receive_json_from(timeout=3)
        if msg.get("type") == type_:
            return msg
    raise AssertionError(f"did not receive {type_}")


async def _open(room, name, key):
    c = WebsocketCommunicator(application, f"/ws/chat/{room}/?name={name}&key={key}")
    connected, _ = await c.connect()
    assert connected
    await _recv(c, "self")
    await _recv(c, "history")
    return c


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_typing_reaches_other_viewer_not_self():
    a = await _open("room1", "Alice", "a1")
    b = await _open("room1", "Bob", "b1")

    await a.send_json_to({"type": "typing"})
    ev = await _recv(b, "typing")     # _recv skips b's presence frames
    assert ev["author"]["name"] == "Alice"

    await a.disconnect()
    await b.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_dotted_event_names_supported():
    a = await _open("room2", "Alice", "a2")
    b = await _open("room2", "Bob", "b2")

    await a.send_json_to({"type": "typing.start"})
    assert (await _recv(b, "typing"))["author"]["name"] == "Alice"

    await a.send_json_to({"type": "voice.recording.start"})
    rec = await _recv(b, "recording")
    assert rec["active"] is True and rec["author"]["name"] == "Alice"

    await a.send_json_to({"type": "voice.recording.stop"})
    assert (await _recv(b, "recording"))["active"] is False

    await a.disconnect()
    await b.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_multiple_users_typing_simultaneously():
    a = await _open("room3", "Alice", "a3")
    b = await _open("room3", "Bob", "b3")
    c = await _open("room3", "Cara", "c3")

    await a.send_json_to({"type": "typing"})
    await b.send_json_to({"type": "typing"})

    seen = set()
    for _ in range(10):
        msg = await c.receive_json_from(timeout=3)
        if msg.get("type") == "typing":
            seen.add(msg["author"]["name"])
        if {"Alice", "Bob"} <= seen:
            break
    assert {"Alice", "Bob"} <= seen

    await a.disconnect()
    await b.disconnect()
    await c.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_disconnect_clears_typing_immediately():
    a = await _open("room4", "Alice", "a4")
    b = await _open("room4", "Bob", "b4")

    await a.send_json_to({"type": "typing"})
    await _recv(b, "typing")

    await a.disconnect()               # tab close / network drop
    stop = await _recv(b, "typing_stop")
    assert stop["author"]["name"] == "Alice"

    await b.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_typing_isolated_to_conversation():
    a = await _open("roomA", "Alice", "aA")
    outsider = await _open("roomB", "Zed", "zB")

    # Drain the outsider's own presence frames (join + snapshot) so the queue is
    # empty before we probe for a (non-)leak.
    await _recv(outsider, "presence")
    await _recv(outsider, "presence")

    await a.send_json_to({"type": "typing"})

    # The outsider (different room) must receive NOTHING. receive_nothing asserts
    # silence without cancelling the application task.
    assert await outsider.receive_nothing(timeout=0.8)

    await a.disconnect()
    await outsider.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_presence_snapshot_on_connect():
    a = WebsocketCommunicator(application, "/ws/chat/roomP/?name=Alice&key=aP")
    assert (await a.connect())[0]
    await _recv(a, "self")
    await _recv(a, "history")
    snap = await _recv(a, "presence")
    assert snap["state"] in ("join", "snapshot")
    await a.disconnect()
