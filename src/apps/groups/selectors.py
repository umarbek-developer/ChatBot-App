"""Read side for groups: query builders with joins pre-applied (no N+1)."""
from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from apps.groups.models import Group, GroupMember, Invite, JoinRequest


def group_detail_qs() -> QuerySet[Group]:
    return Group.objects.select_related("owner")


def discover_groups(*, search: str = "") -> QuerySet[Group]:
    """Public (and private, which are discoverable) groups for the join screen."""
    qs = group_detail_qs().filter(
        visibility__in=[Group.Visibility.PUBLIC, Group.Visibility.PRIVATE]
    )
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(slug__icontains=search) | Q(description__icontains=search))
    return qs.order_by("-member_count", "-created_at")


def user_groups(*, user: Any) -> QuerySet[Group]:
    """Groups the user is an active member of."""
    return (
        group_detail_qs()
        .filter(memberships__user=user, memberships__status=GroupMember.Status.ACTIVE)
        .distinct()
        .order_by("-updated_at")
    )


def group_members(*, group: Group, status: str = GroupMember.Status.ACTIVE) -> QuerySet[GroupMember]:
    return (
        GroupMember.objects.select_related("user", "custom_role")
        .filter(group=group, status=status)
        .order_by("-role", "joined_at")
    )


def membership(*, group: Group, user: Any) -> GroupMember | None:
    return (
        GroupMember.objects.select_related("group", "custom_role")
        .filter(group=group, user=user)
        .first()
    )


def pending_requests(*, group: Group) -> QuerySet[JoinRequest]:
    return (
        JoinRequest.objects.select_related("user")
        .filter(group=group, status=JoinRequest.Status.PENDING)
        .order_by("created_at")
    )


def active_invites(*, group: Group) -> QuerySet[Invite]:
    return Invite.objects.filter(group=group, is_revoked=False).order_by("-created_at")
