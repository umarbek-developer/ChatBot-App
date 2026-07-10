"""Signal handlers for the accounts app.

Auto-provisioning the Profile here (rather than in the register view) guarantees
every User — API signup, admin-created, or management command — always has a
profile, so downstream code never has to null-check it.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="accounts_create_profile")
def create_profile_for_new_user(sender: Any, instance: Any, created: bool, **kwargs: Any) -> None:
    if created:
        Profile.objects.get_or_create(
            user=instance,
            defaults={"display_name": (instance.get_full_name() or "").strip()},
        )
