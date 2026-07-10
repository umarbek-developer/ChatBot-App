"""Redis-backed ephemeral realtime state: presence, last-seen, event throttling.

This intentionally does NOT touch PostgreSQL — presence and typing churn far too
fast to persist. State lives in a dedicated Redis db (``REDIS_REALTIME_URL``)
with TTLs so a hard crash self-heals instead of leaving ghosts online.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import redis.asyncio as aioredis
from django.conf import settings

# One client per running event loop. In production there is a single long-lived
# loop (Daphne/Uvicorn), so this is effectively a singleton; under pytest each
# test gets its own loop, and an asyncio client must not be shared across loops.
_pools: dict[Any, aioredis.Redis] = {}


def _client() -> aioredis.Redis:
    loop = asyncio.get_running_loop()
    client = _pools.get(loop)
    if client is None:
        client = aioredis.from_url(settings.REDIS_REALTIME_URL, decode_responses=True)
        _pools[loop] = client
    return client


def _room_key(room: str) -> str:
    return f"presence:{room}"


async def join(room: str, key: str, member: dict[str, Any]) -> None:
    r = _client()
    await r.hset(_room_key(room), key, json.dumps(member))
    await r.expire(_room_key(room), 3600)
    await r.set(f"lastseen:{key}", int(time.time()))


async def leave(room: str, key: str) -> None:
    r = _client()
    await r.hdel(_room_key(room), key)
    await r.set(f"lastseen:{key}", int(time.time()))


async def members(room: str) -> list[dict[str, Any]]:
    r = _client()
    raw = await r.hgetall(_room_key(room))
    out = []
    for v in raw.values():
        try:
            out.append(json.loads(v))
        except (ValueError, TypeError):
            continue
    return out


async def last_seen(key: str) -> int | None:
    r = _client()
    val = await r.get(f"lastseen:{key}")
    return int(val) if val else None


async def touch(key: str) -> None:
    await _client().set(f"lastseen:{key}", int(time.time()))


async def set_call_online(user_id: str) -> None:
    await _client().set(f"callonline:{user_id}", "1", ex=7200)


async def clear_call_online(user_id: str) -> None:
    await _client().delete(f"callonline:{user_id}")


async def is_call_online(user_id: str) -> bool:
    return bool(await _client().get(f"callonline:{user_id}"))


async def set_in_call(user_id: str, call_id: str) -> None:
    """Mark a user busy for the lifetime of a call (2h TTL safety net)."""
    await _client().set(f"incall:{user_id}", call_id, ex=7200)


async def clear_in_call(user_id: str) -> None:
    await _client().delete(f"incall:{user_id}")


async def in_call(user_id: str) -> str | None:
    return await _client().get(f"incall:{user_id}")


async def allow(key: str, kind: str, window: float = 1.0) -> bool:
    """Server-side throttle: True at most once per ``window`` seconds per key/kind.

    Used to drop typing/recording bursts before they hit the channel layer, so a
    client hammering keystrokes can't amplify into a broadcast storm.
    """
    r = _client()
    throttle_key = f"throttle:{kind}:{key}"
    # SET NX EX with sub-second precision via PX.
    ok = await r.set(throttle_key, "1", nx=True, px=int(window * 1000))
    return bool(ok)
