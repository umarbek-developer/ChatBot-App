"""Group authorization: permission constants, role defaults, and resolvers.

Authorization is enforced primarily in the service layer (services raise
``PermissionDeniedError`` which the global exception handler renders as 403),
keeping views thin. The DRF permission classes here guard the coarse viewset
gates (must be authenticated / must be a member).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission

if TYPE_CHECKING:
    from apps.groups.models import GroupMember


class GroupPerm:
    SEND_MESSAGES = "send_messages"
    DELETE_MESSAGES = "delete_messages"
    PIN_MESSAGES = "pin_messages"
    POST_ANNOUNCEMENT = "post_announcement"
    INVITE_MEMBERS = "invite_members"
    MANAGE_INVITES = "manage_invites"
    KICK_MEMBERS = "kick_members"
    BAN_MEMBERS = "ban_members"
    MUTE_MEMBERS = "mute_members"
    MANAGE_ROLES = "manage_roles"
    MANAGE_GROUP = "manage_group"        # edit settings, slow mode, announcement
    DELETE_GROUP = "delete_group"        # owner only
    APPROVE_REQUESTS = "approve_requests"


# Default permission set per standard role tier.
_MEMBER = {GroupPerm.SEND_MESSAGES, GroupPerm.INVITE_MEMBERS}
_MODERATOR = _MEMBER | {
    GroupPerm.DELETE_MESSAGES, GroupPerm.PIN_MESSAGES,
    GroupPerm.MUTE_MEMBERS, GroupPerm.KICK_MEMBERS,
}
_ADMIN = _MODERATOR | {
    GroupPerm.BAN_MEMBERS, GroupPerm.MANAGE_ROLES, GroupPerm.MANAGE_GROUP,
    GroupPerm.MANAGE_INVITES, GroupPerm.POST_ANNOUNCEMENT, GroupPerm.APPROVE_REQUESTS,
}
_OWNER = _ADMIN | {GroupPerm.DELETE_GROUP}

ROLE_DEFAULTS: dict[str, set[str]] = {
    "owner": _OWNER,
    "admin": _ADMIN,
    "moderator": _MODERATOR,
    "member": _MEMBER,
}


def effective_permissions(member: "GroupMember") -> set[str]:
    """Union of the member's role-tier defaults and any custom-role grants."""
    if member is None or not member.is_active_member:
        return set()
    perms = set(ROLE_DEFAULTS.get(member.role, set()))
    if member.custom_role_id and isinstance(member.custom_role.permissions, list):
        perms |= set(member.custom_role.permissions)
    return perms


def can(member: "GroupMember", perm: str) -> bool:
    return perm in effective_permissions(member)


# Role strength for "can't act on someone equal or above you" checks.
ROLE_RANK = {"member": 0, "moderator": 1, "admin": 2, "owner": 3}


def outranks(actor: "GroupMember", target: "GroupMember") -> bool:
    return ROLE_RANK.get(actor.role, 0) > ROLE_RANK.get(target.role, 0)


class IsAuthenticatedGroupUser(BasePermission):
    message = "Authentication is required to access groups."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)
