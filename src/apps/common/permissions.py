"""Reusable object-level permission classes.

Feature apps compose these or subclass ``BaseObjectPermission`` for domain rules
(e.g. group role checks). Every mutating endpoint is expected to declare at
least one permission class — the API has no implicitly-open write paths.
"""
from __future__ import annotations

from typing import Any

from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsOwnerOrReadOnly(BasePermission):
    """Write access only for the object's owner; reads open to authenticated users.

    Looks for an ownership attribute in a conventional order so it works across
    models without per-view configuration.
    """

    owner_fields = ("owner", "user", "created_by", "author")

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return self._owner(obj) == getattr(request, "user", None)

    def _owner(self, obj: Any) -> Any:
        for field in self.owner_fields:
            if hasattr(obj, field):
                return getattr(obj, field)
        return None


class IsSelf(BasePermission):
    """Object *is* the requesting user (profile/account endpoints)."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        user = getattr(request, "user", None)
        return obj == user or getattr(obj, "user", None) == user


class BaseObjectPermission(BasePermission):
    """Extension point for domain permissions with a readable denial message."""

    message = "You do not have permission to perform this action."

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:  # pragma: no cover
        raise NotImplementedError
