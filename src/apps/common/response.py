"""Helpers for the standard success envelope.

Mirrors the error envelope in ``exceptions.py`` so every response the API emits
has a predictable ``success`` flag. Views stay thin — they call ``ok(...)``
instead of hand-assembling dicts.
"""
from __future__ import annotations

from typing import Any

from rest_framework import status as http_status
from rest_framework.response import Response


def ok(
    data: Any = None,
    *,
    message: str | None = None,
    status: int = http_status.HTTP_200_OK,
    **extra: Any,
) -> Response:
    body: dict[str, Any] = {"success": True}
    if message is not None:
        body["message"] = message
    body["data"] = data
    body.update(extra)
    return Response(body, status=status)


def created(data: Any = None, *, message: str | None = None, **extra: Any) -> Response:
    return ok(data, message=message, status=http_status.HTTP_201_CREATED, **extra)


def no_content() -> Response:
    return Response(status=http_status.HTTP_204_NO_CONTENT)
