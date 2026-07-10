"""Background tasks for groups."""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="groups.revoke_expired_invites")
def revoke_expired_invites() -> int:
    """Mark invite links that have passed their expiry as revoked.

    Scheduled via Celery Beat; keeps ``discover``/invite listings clean without
    per-request checks (the model still guards usability defensively).
    """
    from apps.groups.models import Invite

    updated = (
        Invite.objects.filter(is_revoked=False, expires_at__isnull=False, expires_at__lte=timezone.now())
        .update(is_revoked=True)
    )
    if updated:
        logger.info("Revoked %s expired group invites", updated)
    return updated
