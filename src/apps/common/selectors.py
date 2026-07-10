"""Base primitives for the selector layer.

Selectors are the read side: pure query builders that return querysets/objects
with the right ``select_related``/``prefetch_related`` already applied. Keeping
reads here (and out of views/serializers) is what prevents N+1 regressions from
creeping back in as the API grows.
"""
from __future__ import annotations

from typing import TypeVar

from django.db.models import Model, QuerySet

from apps.common.exceptions import NotFoundError

M = TypeVar("M", bound=Model)


def get_object_or_error(
    queryset: QuerySet[M],
    *,
    error: str = "The requested resource was not found.",
    **filters,
) -> M:
    """Fetch exactly one row or raise the API-friendly ``NotFoundError``.

    Unlike ``get_object_or_404`` this participates in our error envelope and
    carries a domain-specific message.
    """
    try:
        return queryset.get(**filters)
    except queryset.model.DoesNotExist as exc:  # type: ignore[attr-defined]
        raise NotFoundError(error) from exc
