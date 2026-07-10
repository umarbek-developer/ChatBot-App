"""Base primitives for the service layer.

Business logic lives in services, not views or serializers. A service is a
callable unit that mutates state, enforces invariants, writes audit logs, and
fans out side effects (Celery tasks, channel-layer events). Views orchestrate;
services decide.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.common.models import AuditLog


class BaseService:
    """Lightweight base that gives services a transaction helper and audit sink.

    Subclasses implement domain methods; they are intentionally not forced into
    a single ``execute`` shape because real services have several entrypoints
    (e.g. ``GroupService.create``, ``.invite``, ``.kick``).
    """

    atomic = staticmethod(transaction.atomic)

    @staticmethod
    def audit(
        *,
        actor: Any = None,
        action: str,
        target: Any = None,
        target_type: str = "",
        target_id: str = "",
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str = "",
    ) -> AuditLog:
        """Persist an audit record for a domain action.

        Pass either a ``target`` model instance (its type/pk are derived) or the
        explicit ``target_type``/``target_id`` pair.
        """
        if target is not None:
            target_type = target_type or target.__class__.__name__
            target_id = target_id or str(getattr(target, "pk", ""))
        return AuditLog.objects.create(
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata=metadata or {},
            ip_address=ip_address,
            user_agent=user_agent or "",
        )
