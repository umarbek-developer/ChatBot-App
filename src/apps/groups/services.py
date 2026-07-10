"""Group business logic.

All state changes go through ``GroupService``. Each method enforces
authorization (raising ``PermissionDeniedError`` / ``ConflictError`` from
``apps.common.exceptions``), runs inside a transaction where multiple rows
change, keeps ``member_count`` correct, and writes an ``AuditLog`` entry for
moderation-sensitive actions. Views call these and never mutate models directly.
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from django.db.models import F, Q
from django.utils import timezone
from django.utils.text import slugify

from apps.common.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationErrorLike
from apps.common.models import AuditLog
from apps.common.services import BaseService
from apps.groups import permissions as perms
from apps.groups.models import Group, GroupMember, Invite, JoinRequest

# Names that must not become groups (collide with routes / are confusing).
RESERVED_GROUP_NAMES = {
    "admin", "api", "me", "new", "create", "settings", "account", "login",
    "register", "logout", "chat", "ws", "static", "media", "null", "undefined",
}
NAME_MIN, NAME_MAX = 3, 50


def _broadcast_group_event(slug: str, event_type: str, payload: dict[str, Any]) -> None:
    """Notify clients currently connected to a group's realtime room."""
    from apps.messaging.services import broadcast_event
    broadcast_event(slug, {"type": event_type, **payload})


class GroupService(BaseService):
    # ---- normalization / validation -----------------------------------------
    @staticmethod
    def normalize_name(name: str) -> str:
        # Trim, collapse internal whitespace to single spaces.
        return re.sub(r"\s+", " ", (name or "").strip())

    def _validate_name(self, name: str) -> str:
        name = self.normalize_name(name)
        if len(name) < NAME_MIN:
            raise ValidationErrorLike(f"Group name must be at least {NAME_MIN} characters.")
        if len(name) > NAME_MAX:
            raise ValidationErrorLike(f"Group name must be at most {NAME_MAX} characters.")
        if slugify(name).replace("-", "") in RESERVED_GROUP_NAMES or name.lower() in RESERVED_GROUP_NAMES:
            raise ValidationErrorLike("That group name is reserved. Please choose another.")
        return name

    # ---- lifecycle -----------------------------------------------------------
    def create(self, *, owner: Any, name: str, description: str = "", rules: str = "",
               visibility: str = Group.Visibility.PUBLIC, slug: str | None = None) -> Group:
        name = self._validate_name(name)
        slug = slugify(name)
        if not slug:
            raise ValidationErrorLike("Group name must contain letters or numbers.")
        if visibility not in Group.Visibility.values:
            raise ValidationErrorLike("Invalid visibility.")

        # Reject duplicates (case-insensitive on name OR slug) among ACTIVE groups.
        # Group.objects excludes soft-deleted rows, so this checks live groups only;
        # the DB partial UniqueConstraint is the final backstop against races.
        existing = Group.objects.filter(Q(name__iexact=name) | Q(slug=slug)).first()
        if existing:
            raise ConflictError(
                "A group with this name already exists.",
                details={"slug": existing.slug, "name": existing.name},
            )

        with self.atomic():
            group = Group.objects.create(
                name=name, slug=slug, description=description, rules=rules,
                visibility=visibility, owner=owner, created_by=owner, updated_by=owner,
            )
            GroupMember.objects.create(
                group=group, user=owner, role=GroupMember.Role.OWNER,
                status=GroupMember.Status.ACTIVE,
            )
            self._recount(group)
            self.audit(actor=owner, action=AuditLog.Action.CREATE, target=group,
                       metadata={"slug": slug, "visibility": visibility})
        _broadcast_group_event(slug, "group.created",
                               {"group": {"slug": slug, "name": name, "visibility": visibility}})
        return group

    def update(self, *, actor: Any, group: Group, **fields) -> Group:
        self._require(actor, group, perms.GroupPerm.MANAGE_GROUP)
        allowed = {"name", "description", "rules", "visibility", "pinned_announcement", "slow_mode_seconds"}
        if fields.get("name"):
            new_name = self._validate_name(fields["name"])
            clash = Group.objects.filter(Q(name__iexact=new_name)).exclude(pk=group.pk).exists()
            if clash:
                raise ConflictError("A group with this name already exists.")
            fields["name"] = new_name
        for key, value in fields.items():
            if key in allowed and value is not None:
                setattr(group, key, value)
        group.updated_by = actor
        group.save()
        self.audit(actor=actor, action=AuditLog.Action.UPDATE, target=group,
                   metadata={"fields": [k for k in fields if k in allowed]})
        _broadcast_group_event(group.slug, "group.updated",
                               {"group": {"slug": group.slug, "name": group.name,
                                          "description": group.description, "visibility": group.visibility}})
        return group

    def delete(self, *, actor: Any, group: Group) -> None:
        member = self._member(group, actor)
        if not (member and member.role == GroupMember.Role.OWNER):
            raise PermissionDeniedError("Only the owner can delete this group.")
        slug = group.slug
        with self.atomic():
            group.deleted_by = actor
            group.save(update_fields=["deleted_by"])
            group.delete()  # soft delete (sets is_deleted / deleted_at)
            self.audit(actor=actor, action=AuditLog.Action.DELETE, target=group)
        # Instantly notify everyone currently in the group's chat.
        _broadcast_group_event(slug, "group.deleted", {"slug": slug})

    # ---- membership ----------------------------------------------------------
    def join(self, *, user: Any, group: Group, message: str = "") -> dict[str, Any]:
        """Join a public group instantly; for private groups create a request."""
        existing = self._member(group, user)
        if existing and existing.status == GroupMember.Status.BANNED:
            raise PermissionDeniedError("You are banned from this group.")
        if existing and existing.is_active_member:
            raise ConflictError("You are already a member of this group.")

        if group.visibility == Group.Visibility.PUBLIC:
            member = self._activate(group, user)
            return {"status": "joined", "member_id": str(member.id)}

        if group.visibility == Group.Visibility.INVITE:
            raise PermissionDeniedError("This group is invite-only. Use an invite link.")

        # private -> approval workflow
        req, created = JoinRequest.objects.get_or_create(
            group=group, user=user, status=JoinRequest.Status.PENDING,
            defaults={"message": message[:300]},
        )
        return {"status": "requested", "request_id": str(req.id), "already": not created}

    def join_with_invite(self, *, user: Any, code: str) -> dict[str, Any]:
        try:
            invite = Invite.objects.select_related("group").get(code=code)
        except Invite.DoesNotExist as exc:
            raise NotFoundError("Invite link is invalid.") from exc
        if not invite.is_usable:
            raise ConflictError("This invite link has expired or is no longer valid.")

        existing = self._member(invite.group, user)
        if existing and existing.status == GroupMember.Status.BANNED:
            raise PermissionDeniedError("You are banned from this group.")
        if existing and existing.is_active_member:
            raise ConflictError("You are already a member of this group.")

        with self.atomic():
            member = self._activate(invite.group, user)
            Invite.objects.filter(pk=invite.pk).update(uses=F("uses") + 1)
        return {"status": "joined", "group_slug": invite.group.slug, "member_id": str(member.id)}

    def leave(self, *, user: Any, group: Group) -> None:
        member = self._member(group, user)
        if not member or not member.is_active_member:
            raise ConflictError("You are not a member of this group.")
        if member.role == GroupMember.Role.OWNER:
            raise ConflictError("Owners must transfer ownership before leaving.")
        with self.atomic():
            member.status = GroupMember.Status.LEFT
            member.save(update_fields=["status", "updated_at"])
            self._recount(group)
            self.audit(actor=user, action=AuditLog.Action.LEAVE, target=group)

    # ---- moderation ----------------------------------------------------------
    def kick(self, *, actor: Any, group: Group, target_user: Any) -> None:
        self._moderate(actor, group, target_user, perms.GroupPerm.KICK_MEMBERS,
                       new_status=GroupMember.Status.KICKED, action=AuditLog.Action.KICK)

    def ban(self, *, actor: Any, group: Group, target_user: Any) -> None:
        self._moderate(actor, group, target_user, perms.GroupPerm.BAN_MEMBERS,
                       new_status=GroupMember.Status.BANNED, action=AuditLog.Action.BAN)

    def unban(self, *, actor: Any, group: Group, target_user: Any) -> None:
        acting = self._require(actor, group, perms.GroupPerm.BAN_MEMBERS)
        member = self._member(group, target_user)
        if not member or member.status != GroupMember.Status.BANNED:
            raise ConflictError("That user is not banned.")
        member.status = GroupMember.Status.LEFT
        member.save(update_fields=["status", "updated_at"])
        self.audit(actor=actor, action=AuditLog.Action.OTHER, target=group,
                   metadata={"unban": str(getattr(target_user, "pk", ""))})

    def mute(self, *, actor: Any, group: Group, target_user: Any, minutes: int = 60) -> None:
        self._require(actor, group, perms.GroupPerm.MUTE_MEMBERS)
        member = self._member(group, target_user)
        if not member or not member.is_active_member:
            raise NotFoundError("That user is not an active member.")
        member.muted_until = timezone.now() + timedelta(minutes=max(1, minutes))
        member.save(update_fields=["muted_until", "updated_at"])
        self.audit(actor=actor, action=AuditLog.Action.MUTE, target=group,
                   metadata={"user": str(getattr(target_user, "pk", "")), "minutes": minutes})

    def set_role(self, *, actor: Any, group: Group, target_user: Any, role: str) -> GroupMember:
        acting = self._require(actor, group, perms.GroupPerm.MANAGE_ROLES)
        if role not in GroupMember.Role.values or role == GroupMember.Role.OWNER:
            raise ValidationErrorLike("Invalid role assignment.")
        member = self._member(group, target_user)
        if not member or not member.is_active_member:
            raise NotFoundError("That user is not an active member.")
        if not perms.outranks(acting, member) and acting.user_id != group.owner_id:
            raise PermissionDeniedError("You cannot change the role of an equal or higher member.")
        member.role = role
        member.save(update_fields=["role", "updated_at"])
        self.audit(actor=actor, action=AuditLog.Action.ROLE_CHANGE, target=group,
                   metadata={"user": str(getattr(target_user, "pk", "")), "role": role})
        return member

    # ---- invites -------------------------------------------------------------
    def create_invite(self, *, actor: Any, group: Group, max_uses: int = 0,
                      expires_in_hours: int | None = None) -> Invite:
        self._require(actor, group, perms.GroupPerm.MANAGE_INVITES)
        expires_at = None
        if expires_in_hours:
            expires_at = timezone.now() + timedelta(hours=expires_in_hours)
        invite = Invite.objects.create(
            group=group, created_by=actor, max_uses=max(0, max_uses), expires_at=expires_at
        )
        self.audit(actor=actor, action=AuditLog.Action.INVITE, target=group,
                   metadata={"code": invite.code})
        return invite

    def revoke_invite(self, *, actor: Any, invite: Invite) -> None:
        self._require(actor, invite.group, perms.GroupPerm.MANAGE_INVITES)
        invite.is_revoked = True
        invite.save(update_fields=["is_revoked", "updated_at"])

    # ---- join requests -------------------------------------------------------
    def approve_request(self, *, actor: Any, request_obj: JoinRequest) -> GroupMember:
        self._require(actor, request_obj.group, perms.GroupPerm.APPROVE_REQUESTS)
        if request_obj.status != JoinRequest.Status.PENDING:
            raise ConflictError("This request has already been decided.")
        with self.atomic():
            member = self._activate(request_obj.group, request_obj.user)
            request_obj.status = JoinRequest.Status.APPROVED
            request_obj.decided_by = actor
            request_obj.decided_at = timezone.now()
            request_obj.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
            self.audit(actor=actor, action=AuditLog.Action.JOIN, target=request_obj.group,
                       metadata={"approved": str(request_obj.user_id)})
        return member

    def reject_request(self, *, actor: Any, request_obj: JoinRequest) -> None:
        self._require(actor, request_obj.group, perms.GroupPerm.APPROVE_REQUESTS)
        if request_obj.status != JoinRequest.Status.PENDING:
            raise ConflictError("This request has already been decided.")
        request_obj.status = JoinRequest.Status.REJECTED
        request_obj.decided_by = actor
        request_obj.decided_at = timezone.now()
        request_obj.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])

    # ---- internals -----------------------------------------------------------
    def _activate(self, group: Group, user: Any) -> GroupMember:
        member, _ = GroupMember.objects.get_or_create(group=group, user=user)
        member.status = GroupMember.Status.ACTIVE
        if member.role not in GroupMember.Role.values:
            member.role = GroupMember.Role.MEMBER
        member.joined_at = member.joined_at or timezone.now()
        member.save()
        self._recount(group)
        return member

    def _moderate(self, actor, group, target_user, perm, *, new_status, action) -> None:
        acting = self._require(actor, group, perm)
        member = self._member(group, target_user)
        if not member or not member.is_active_member:
            raise NotFoundError("That user is not an active member.")
        if member.role == GroupMember.Role.OWNER:
            raise PermissionDeniedError("You cannot moderate the group owner.")
        if not perms.outranks(acting, member):
            raise PermissionDeniedError("You cannot moderate an equal or higher member.")
        with self.atomic():
            member.status = new_status
            member.save(update_fields=["status", "updated_at"])
            self._recount(group)
            self.audit(actor=actor, action=action, target=group,
                       metadata={"user": str(getattr(target_user, "pk", ""))})

    def _member(self, group: Group, user: Any) -> GroupMember | None:
        return GroupMember.objects.select_related("custom_role").filter(group=group, user=user).first()

    def _require(self, actor: Any, group: Group, perm: str) -> GroupMember:
        member = self._member(group, actor)
        if not member or not member.is_active_member:
            raise PermissionDeniedError("You are not a member of this group.")
        if not perms.can(member, perm):
            raise PermissionDeniedError("You do not have permission to perform this action.")
        return member

    @staticmethod
    def _recount(group: Group) -> None:
        count = GroupMember.objects.filter(group=group, status=GroupMember.Status.ACTIVE).count()
        Group.objects.filter(pk=group.pk).update(member_count=count)
        group.member_count = count
