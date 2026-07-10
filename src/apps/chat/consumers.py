"""Server-authoritative realtime chat consumer.

Replaces the old echo relay. The server now owns identity, message ids/timestamps,
persistence and delivery/read state; clients send intent and render what the
server confirms. Ephemeral signals (typing, recording, presence) go through Redis
with throttling and never hit PostgreSQL.

Wire protocol (JSON both ways), ``type`` field switches behaviour:
  → in:  message | typing | recording | read | reaction | edit | delete
  ← out: history | message | typing | recording | read | reaction | edit
         | delete | presence | status
"""
from __future__ import annotations

import uuid
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from apps.chat import presence


class ChatConsumer(AsyncJsonWebsocketConsumer):
    HISTORY_LIMIT = 50

    # ---- lifecycle -----------------------------------------------------------
    async def connect(self) -> None:
        self.room = self.scope["url_route"]["kwargs"]["room_name"]
        self.group = f"chat_{self.room}"
        self.identity = await self._resolve_identity()

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

        # Tell the client its server-resolved identity (critical for auth users,
        # whose id differs from any guest key they connected with).
        await self.send_json({"type": "self", "identity": self.identity})
        # Backfill history, then announce presence.
        await self.send_json({"type": "history", "messages": await self._history()})
        await presence.join(self.room, self.identity["id"], self.identity)
        await self._broadcast({"type": "presence", "state": "join", "member": self.identity})
        await self.send_json({"type": "presence", "state": "snapshot",
                              "members": await presence.members(self.room)})

    async def disconnect(self, code: int) -> None:
        if not hasattr(self, "identity"):
            return
        # Clear any lingering typing/recording indicator instantly on tab close /
        # network drop / refresh, so peers don't wait for a client-side timeout.
        await self._broadcast({"type": "typing_stop", "author": self.identity})
        await self._broadcast({"type": "recording", "author": self.identity, "active": False})
        await presence.leave(self.room, self.identity["id"])
        await self._broadcast({"type": "presence", "state": "leave", "member": self.identity})
        await self.channel_layer.group_discard(self.group, self.channel_name)

    # ---- inbound dispatch ----------------------------------------------------
    async def receive_json(self, content: dict[str, Any], **kwargs) -> None:
        handler = {
            "message": self._on_message,
            # typing (both the short and the Telegram-style dotted names)
            "typing": self._on_typing,
            "typing.start": self._on_typing,
            "typing_stop": self._on_typing_stop,
            "typing.stop": self._on_typing_stop,
            # voice recording status
            "recording": self._on_recording,
            "voice.recording.start": self._on_recording_start,
            "voice.recording.stop": self._on_recording_stop,
            "read": self._on_read,
            "played": self._on_played,
            "reaction": self._on_reaction,
            "edit": self._on_edit,
            "delete": self._on_delete,
        }.get(content.get("type"))
        if handler:
            await handler(content)

    async def _on_message(self, content: dict[str, Any]) -> None:
        event = await self._create_message(content)
        await self._broadcast({"type": "message", "message": event})
        # Delivery: if anyone else is present in the room, it's delivered.
        others = [m for m in await presence.members(self.room) if m["id"] != self.identity["id"]]
        status = "delivered" if others else "sent"
        await self.send_json({"type": "status", "id": event["id"],
                              "client_id": event["client_id"], "status": status})

    async def _on_typing(self, content: dict[str, Any]) -> None:
        if await presence.allow(self.identity["id"], "typing", 1.0):
            await presence.touch(self.identity["id"])
            await self._broadcast({"type": "typing", "author": self.identity})

    async def _on_typing_stop(self, content: dict[str, Any]) -> None:
        # No throttle: "stop" must land immediately (send/clear/blur).
        await self._broadcast({"type": "typing_stop", "author": self.identity})

    async def _on_recording(self, content: dict[str, Any]) -> None:
        active = bool(content.get("active", True))
        # No throttle on the "stop" so it disappears instantly (per spec).
        if not active or await presence.allow(self.identity["id"], "recording", 1.5):
            await self._broadcast({"type": "recording", "author": self.identity, "active": active})

    async def _on_recording_start(self, content: dict[str, Any]) -> None:
        await self._on_recording({**content, "active": True})

    async def _on_recording_stop(self, content: dict[str, Any]) -> None:
        await self._on_recording({**content, "active": False})

    async def _on_read(self, content: dict[str, Any]) -> None:
        ids = content.get("ids") or []
        read_ids = await self._mark_read(ids)
        if read_ids:
            await self._broadcast({"type": "read", "reader": self.identity, "ids": read_ids})

    async def _on_played(self, content: dict[str, Any]) -> None:
        mid = content.get("id")
        if mid and await self._mark_played(mid):
            await self._broadcast({"type": "played", "reader": self.identity, "id": mid})

    async def _on_reaction(self, content: dict[str, Any]) -> None:
        result = await self._toggle_reaction(content.get("id"), content.get("emoji", ""))
        if result is not None:
            await self._broadcast({"type": "reaction", "id": content["id"],
                                   "reactions": result, "author": self.identity})

    async def _on_edit(self, content: dict[str, Any]) -> None:
        ok = await self._edit_message(content.get("id"), content.get("text", ""))
        if ok:
            await self._broadcast({"type": "edit", "id": content["id"], "text": content["text"]})

    async def _on_delete(self, content: dict[str, Any]) -> None:
        if await self._delete_message(content.get("id")):
            await self._broadcast({"type": "delete", "id": content["id"]})

    # ---- group event fan-out -------------------------------------------------
    async def _broadcast(self, event: dict[str, Any]) -> None:
        await self.channel_layer.group_send(self.group, {"type": "fanout", "event": event})

    async def fanout(self, message: dict[str, Any]) -> None:
        await self.send_json(message["event"])

    # ---- identity ------------------------------------------------------------
    async def _resolve_identity(self) -> dict[str, Any]:
        from urllib.parse import parse_qs

        user = self.scope.get("user")
        if user is not None and getattr(user, "is_authenticated", False):
            name = (user.get_full_name() or "").strip() or user.email.split("@")[0]
            return {"id": str(user.pk), "name": name, "color": self._color(str(user.pk)),
                    "authenticated": True}
        q = parse_qs(self.scope.get("query_string", b"").decode())
        key = (q.get("key") or [str(uuid.uuid4())])[0][:64]
        name = (q.get("name") or ["Guest"])[0][:60]
        return {"id": key, "name": name, "color": self._color(key), "authenticated": False}

    @staticmethod
    def _color(seed: str) -> str:
        palette = ["#3B82F6", "#8B5CF6", "#EC4899", "#22C55E", "#F59E0B", "#06B6D4", "#EF4444", "#14B8A6"]
        return palette[sum(map(ord, seed)) % len(palette)]

    # ---- database (sync, off the event loop) ---------------------------------
    @database_sync_to_async
    def _create_message(self, content: dict[str, Any]) -> dict[str, Any]:
        from apps.messaging.models import Message

        reply_to = None
        reply_id = content.get("reply_to_id")
        if reply_id:
            reply_to = Message.objects.filter(id=reply_id, room=self.room).first()
        kind = content.get("kind") or ("image" if content.get("image") else "text")
        attachment = content.get("image") or content.get("audio") or ""
        msg = Message.objects.create(
            room=self.room,
            sender=self.scope["user"] if self.identity.get("authenticated") else None,
            sender_key=self.identity["id"],
            sender_name=self.identity["name"],
            sender_color=self.identity["color"],
            kind=kind,
            text=(content.get("text") or "")[:8000],
            attachment_url=attachment,
            duration_ms=int(content.get("duration_ms") or 0),
            client_id=(content.get("client_id") or "")[:64],
            reply_to=reply_to,
        )
        return msg.to_event()  # serialise here, inside the sync DB thread

    @database_sync_to_async
    def _history(self) -> list[dict[str, Any]]:
        from apps.messaging.models import Message

        qs = (
            Message.objects.filter(room=self.room)
            .prefetch_related("reactions").select_related("reply_to", "voice")
            .order_by("-created_at")[: self.HISTORY_LIMIT]
        )
        return [m.to_event() for m in reversed(list(qs))]

    @database_sync_to_async
    def _mark_read(self, ids: list[str]) -> list[str]:
        from apps.messaging.models import Message, ReadReceipt

        done = []
        for mid in ids[:200]:
            msg = Message.objects.filter(id=mid, room=self.room).first()
            if not msg or msg.sender_key == self.identity["id"]:
                continue
            _, created = ReadReceipt.objects.get_or_create(
                message=msg, reader_key=self.identity["id"],
                defaults={"reader_name": self.identity["name"], "read_at": timezone.now()},
            )
            done.append(str(msg.id))
        return done

    @database_sync_to_async
    def _mark_played(self, message_id: str) -> bool:
        from apps.messaging.models import Message, PlayedReceipt

        msg = Message.objects.filter(id=message_id, room=self.room, kind=Message.Kind.VOICE).first()
        if not msg or msg.sender_key == self.identity["id"]:
            return False
        _, created = PlayedReceipt.objects.get_or_create(
            message=msg, player_key=self.identity["id"],
            defaults={"player_name": self.identity["name"]},
        )
        return created

    @database_sync_to_async
    def _toggle_reaction(self, message_id: str, emoji: str) -> dict[str, int] | None:
        from apps.messaging.models import Message, Reaction

        if not message_id or not emoji:
            return None
        msg = Message.objects.filter(id=message_id, room=self.room).first()
        if not msg:
            return None
        existing = Reaction.objects.filter(message=msg, emoji=emoji, actor_key=self.identity["id"])
        if existing.exists():
            existing.delete()
        else:
            Reaction.objects.create(message=msg, emoji=emoji, actor_key=self.identity["id"],
                                    actor_name=self.identity["name"])
        return msg.reaction_summary()

    @database_sync_to_async
    def _edit_message(self, message_id: str, text: str) -> bool:
        from apps.messaging.models import Message, MessageEditHistory

        msg = Message.objects.filter(id=message_id, room=self.room, sender_key=self.identity["id"]).first()
        if not msg or msg.is_deleted:
            return False
        MessageEditHistory.objects.create(message=msg, previous_text=msg.text)
        msg.text = (text or "")[:8000]
        msg.is_edited = True
        msg.edited_at = timezone.now()
        msg.save(update_fields=["text", "is_edited", "edited_at", "updated_at"])
        return True

    @database_sync_to_async
    def _delete_message(self, message_id: str) -> bool:
        from apps.messaging.models import Message

        msg = Message.objects.filter(id=message_id, room=self.room, sender_key=self.identity["id"]).first()
        if not msg:
            return False
        msg.delete()  # soft delete
        return True
