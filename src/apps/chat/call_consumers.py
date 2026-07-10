"""WebRTC signaling consumer.

The server is a *signaling relay only* — SDP offers/answers and ICE candidates
are forwarded between the two authenticated peers; the audio/video itself flows
peer-to-peer and never reaches Django. Each user has a personal channel-layer
group ``call_<user_id>`` so 1:1 calls target an individual regardless of which
chat room they're viewing.

Inbound event types (dot-namespaced per the brief):
    call.offer · call.answer · call.ice_candidate · call.reject · call.end
Server-emitted:
    call.incoming · call.answer · call.ice_candidate · call.rejected
    call.ended · call.busy · call.unavailable
"""
from __future__ import annotations

from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.chat import presence


class CallConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        user = self.scope.get("user")
        if not (user and getattr(user, "is_authenticated", False)):
            await self.close(code=4401)  # calls require a logged-in user
            return
        self.user_id = str(user.pk)
        self.name = (user.get_full_name() or "").strip() or user.email.split("@")[0]
        self.group = f"call_{self.user_id}"
        self.active_call_id: str | None = None
        self.peer_id: str | None = None

        await self.channel_layer.group_add(self.group, self.channel_name)
        await presence.set_call_online(self.user_id)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        if not hasattr(self, "user_id"):
            return
        # Tear down a call in progress so the peer isn't left hanging.
        if self.active_call_id and self.peer_id:
            await self._finalize(self.active_call_id, answered=True, status="ended")
            await self._relay(self.peer_id, {"type": "call.ended", "call_id": self.active_call_id})
            await presence.clear_in_call(self.user_id)
            await presence.clear_in_call(self.peer_id)
        await presence.clear_call_online(self.user_id)
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content: dict[str, Any], **kwargs) -> None:
        handler = {
            "call.offer": self._offer,
            "call.answer": self._answer,
            "call.ice_candidate": self._ice,
            "call.reject": self._reject,
            "call.end": self._end,
        }.get(content.get("type"))
        if handler:
            await handler(content)

    # ---- signaling handlers --------------------------------------------------
    async def _offer(self, c: dict[str, Any]) -> None:
        to = str(c.get("to") or "")
        if not to or to == self.user_id:
            return
        call_type = "video" if c.get("call_type") == "video" else "voice"

        if not await presence.is_call_online(to):
            call = await self._create_call(to, call_type, status="missed")
            await self.send_json({"type": "call.unavailable", "call_id": str(call.id)})
            return
        if await presence.in_call(to):
            await self._create_call(to, call_type, status="busy")
            await self.send_json({"type": "call.busy", "to": to})
            return

        call = await self._create_call(to, call_type, status="ringing")
        self.active_call_id = str(call.id)
        self.peer_id = to
        await self._relay(to, {
            "type": "call.incoming",
            "call_id": str(call.id),
            "call_type": call_type,
            "sdp": c.get("sdp"),
            "from": {"id": self.user_id, "name": self.name},
        })

    async def _answer(self, c: dict[str, Any]) -> None:
        to = str(c.get("to") or "")
        call_id = c.get("call_id")
        self.active_call_id = call_id
        self.peer_id = to
        await self._finalize(call_id, answered=True, status="ongoing")
        await presence.set_in_call(self.user_id, call_id)
        await presence.set_in_call(to, call_id)
        await self._relay(to, {
            "type": "call.answer", "call_id": call_id, "sdp": c.get("sdp"),
            "from": {"id": self.user_id, "name": self.name},
        })

    async def _ice(self, c: dict[str, Any]) -> None:
        to = str(c.get("to") or "")
        if to:
            await self._relay(to, {"type": "call.ice_candidate",
                                   "candidate": c.get("candidate"), "call_id": c.get("call_id")})

    async def _reject(self, c: dict[str, Any]) -> None:
        to = str(c.get("to") or "")
        await self._finalize(c.get("call_id"), answered=False, status="rejected")
        if to:
            await self._relay(to, {"type": "call.rejected", "call_id": c.get("call_id")})
        self.active_call_id = self.peer_id = None

    async def _end(self, c: dict[str, Any]) -> None:
        to = str(c.get("to") or "")
        call_id = c.get("call_id")
        await self._finalize(call_id, answered=False, status="ended")
        await presence.clear_in_call(self.user_id)
        if to:
            await presence.clear_in_call(to)
            await self._relay(to, {"type": "call.ended", "call_id": call_id})
        self.active_call_id = self.peer_id = None

    # ---- fan-out -------------------------------------------------------------
    async def _relay(self, user_id: str, event: dict[str, Any]) -> None:
        await self.channel_layer.group_send(f"call_{user_id}", {"type": "signal", "event": event})

    async def signal(self, message: dict[str, Any]) -> None:
        await self.send_json(message["event"])

    # ---- database ------------------------------------------------------------
    @database_sync_to_async
    def _create_call(self, receiver_id: str, call_type: str, status: str):
        from apps.chat.models import Call

        return Call.objects.create(
            caller_id=self.user_id, receiver_id=receiver_id, call_type=call_type, status=status,
        )

    @database_sync_to_async
    def _finalize(self, call_id: str | None, *, answered: bool, status: str) -> None:
        from apps.chat.models import Call

        if not call_id:
            return
        call = Call.objects.filter(id=call_id).first()
        if not call or call.status in (Call.Status.ENDED, Call.Status.REJECTED):
            return
        # A ring that never connected and is now ending = missed, not ended.
        if status == "ended" and call.status == Call.Status.RINGING and not answered:
            status = Call.Status.MISSED
        call.mark(status, answered=answered)
