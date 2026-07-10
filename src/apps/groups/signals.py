"""Safety-net signals for groups.

The service layer is the primary keeper of ``member_count``; these handlers
guarantee it stays correct even if a membership row is created or removed
outside a service (admin actions, data migrations, tests).
"""
from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.groups.models import Group, GroupMember


def _recount(group_id: Any) -> None:
    from django.db.models import Q

    count = GroupMember.objects.filter(
        group_id=group_id, status=GroupMember.Status.ACTIVE
    ).filter(Q(is_deleted=False)).count()
    Group.all_objects.filter(pk=group_id).update(member_count=count)


@receiver(post_save, sender=GroupMember, dispatch_uid="groups_member_saved")
def member_saved(sender, instance: GroupMember, **kwargs: Any) -> None:
    _recount(instance.group_id)


@receiver(post_delete, sender=GroupMember, dispatch_uid="groups_member_deleted")
def member_deleted(sender, instance: GroupMember, **kwargs: Any) -> None:
    _recount(instance.group_id)
