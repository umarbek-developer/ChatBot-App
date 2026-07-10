"""Domain exceptions and a unified DRF exception handler.

Every error that leaves the API — whether raised by DRF validation, a
permission check, or a service-layer ``ApplicationError`` — is rendered through
one envelope so clients only ever parse a single shape:

    {
        "success": false,
        "error": {
            "code": "validation_error",
            "message": "Human readable summary.",
            "details": { ... optional field errors / context ... }
        }
    }
"""
from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class ApplicationError(Exception):
    """Base class for expected, business-rule errors raised by services.

    Services raise these instead of returning ad-hoc dicts; the handler below
    maps them to a clean HTTP response, keeping views free of error plumbing.
    """

    default_message = "Something went wrong."
    default_code = "application_error"
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Any = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class PermissionDeniedError(ApplicationError):
    default_message = "You do not have permission to perform this action."
    default_code = "permission_denied"
    status_code = status.HTTP_403_FORBIDDEN


class NotFoundError(ApplicationError):
    default_message = "The requested resource was not found."
    default_code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(ApplicationError):
    default_message = "The request conflicts with the current state."
    default_code = "conflict"
    status_code = status.HTTP_409_CONFLICT


class RateLimitedError(ApplicationError):
    default_message = "Too many requests. Please slow down."
    default_code = "rate_limited"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


class ValidationErrorLike(ApplicationError):
    """Service-layer validation failure (distinct from DRF serializer errors)."""

    default_message = "The submitted data is invalid."
    default_code = "validation_error"
    status_code = status.HTTP_400_BAD_REQUEST


def _envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return {"success": False, "error": payload}


def custom_exception_handler(exc: Exception, context: dict) -> Response | None:
    """DRF ``EXCEPTION_HANDLER`` entrypoint.

    Handles our ``ApplicationError`` family first, then delegates everything
    else to DRF and re-wraps its response in the standard envelope.
    """
    if isinstance(exc, ApplicationError):
        return Response(
            _envelope(exc.code, exc.message, exc.details),
            status=exc.status_code,
        )

    # Normalise the two Django-native errors DRF handles specially.
    if isinstance(exc, Http404):
        return Response(
            _envelope("not_found", "The requested resource was not found."),
            status=status.HTTP_404_NOT_FOUND,
        )
    if isinstance(exc, DjangoPermissionDenied):
        return Response(
            _envelope("permission_denied", "You do not have permission to perform this action."),
            status=status.HTTP_403_FORBIDDEN,
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        # Unhandled -> let Django's 500 machinery (and Sentry later) take over.
        return None

    data = response.data
    code = _code_for_status(response.status_code)
    message, details = _split_drf_payload(data)
    response.data = _envelope(code, message, details)
    return response


def _code_for_status(code: int) -> str:
    return {
        status.HTTP_400_BAD_REQUEST: "validation_error",
        status.HTTP_401_UNAUTHORIZED: "authentication_failed",
        status.HTTP_403_FORBIDDEN: "permission_denied",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
    }.get(code, "error")


def _split_drf_payload(data: Any) -> tuple[str, Any]:
    """Extract a headline message + structured details from a DRF error body."""
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail is not None and len(data) == 1:
            return str(detail), None
        # Field-level validation errors: keep the full map as details.
        first_key = next(iter(data), None)
        first_val = data[first_key] if first_key is not None else None
        if isinstance(first_val, (list, tuple)) and first_val:
            message = f"{first_key}: {first_val[0]}"
        else:
            message = "Validation failed."
        return message, data
    if isinstance(data, list) and data:
        return str(data[0]), data
    return "An error occurred.", None
