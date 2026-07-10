"""JWT authentication middleware for Django Channels.

Browsers can't set Authorization headers on a WebSocket handshake, so the token
is passed as a query param: ``ws://host/ws/chat/<room>/?token=<access_jwt>``.
Valid tokens resolve ``scope['user']`` to the real user; anonymous connections
are allowed through as guests (the consumer assigns them a stable guest identity)
so the open, no-login chat keeps working alongside authenticated sessions.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _get_user(token: str) -> Any:
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    from apps.users.models import User

    try:
        access = AccessToken(token)
        return User.objects.get(id=access["user_id"])
    except (TokenError, User.DoesNotExist, KeyError, Exception):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope: dict, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]
        scope["user"] = await _get_user(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
