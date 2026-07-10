"""Thin group API views.

Views validate input with serializers, delegate every mutation to
``GroupService``, and shape output. They hold no business rules — authorization
and invariants are enforced in the service and surface as our error envelope.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.pagination import StandardPageNumberPagination
from apps.common.response import created, ok
from apps.groups import selectors
from apps.groups.models import Group, Invite, JoinRequest
from apps.groups.permissions import IsAuthenticatedGroupUser
from apps.groups.serializers import (
    GroupCreateSerializer,
    GroupMemberSerializer,
    GroupSerializer,
    GroupUpdateSerializer,
    InviteSerializer,
    JoinRequestSerializer,
)
from apps.groups.services import GroupService

service = GroupService()


class GroupViewSet(viewsets.ViewSet):
    """CRUD + membership + moderation for groups, mounted at /api/v1/groups/."""

    permission_classes = [IsAuthenticated, IsAuthenticatedGroupUser]
    pagination_class = StandardPageNumberPagination
    lookup_field = "slug"

    def _get_group(self, slug: str) -> Group:
        return get_object_or_404(selectors.group_detail_qs(), slug=slug)

    # ---- discovery / listing -------------------------------------------------
    @extend_schema(responses=GroupSerializer(many=True))
    def list(self, request: Request) -> Response:
        """Groups the current user belongs to."""
        qs = selectors.user_groups(user=request.user)
        return ok(GroupSerializer(qs, many=True).data)

    @extend_schema(responses=GroupSerializer(many=True))
    @action(detail=False, methods=["get"])
    def discover(self, request: Request) -> Response:
        qs = selectors.discover_groups(search=request.query_params.get("search", ""))
        return ok(GroupSerializer(qs, many=True).data)

    def retrieve(self, request: Request, slug: str) -> Response:
        group = self._get_group(slug)
        return ok(GroupSerializer(group).data)

    # ---- lifecycle -----------------------------------------------------------
    @extend_schema(request=GroupCreateSerializer, responses=GroupSerializer)
    def create(self, request: Request) -> Response:
        ser = GroupCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        group = service.create(owner=request.user, **ser.validated_data)
        return created(GroupSerializer(group).data, message="Group created.")

    @extend_schema(request=GroupUpdateSerializer, responses=GroupSerializer)
    def partial_update(self, request: Request, slug: str) -> Response:
        group = self._get_group(slug)
        ser = GroupUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        group = service.update(actor=request.user, group=group, **ser.validated_data)
        return ok(GroupSerializer(group).data, message="Group updated.")

    def destroy(self, request: Request, slug: str) -> Response:
        group = self._get_group(slug)
        service.delete(actor=request.user, group=group)
        return ok(message="Group deleted.")

    # ---- membership ----------------------------------------------------------
    @action(detail=True, methods=["post"])
    def join(self, request: Request, slug: str) -> Response:
        group = self._get_group(slug)
        result = service.join(user=request.user, group=group, message=request.data.get("message", ""))
        return ok(result, message="Requested to join." if result["status"] == "requested" else "Joined group.")

    @action(detail=True, methods=["post"])
    def leave(self, request: Request, slug: str) -> Response:
        group = self._get_group(slug)
        service.leave(user=request.user, group=group)
        return ok(message="You left the group.")

    @extend_schema(responses=GroupMemberSerializer(many=True))
    @action(detail=True, methods=["get"])
    def members(self, request: Request, slug: str) -> Response:
        group = self._get_group(slug)
        return ok(GroupMemberSerializer(selectors.group_members(group=group), many=True).data)

    # ---- moderation ----------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="members/(?P<user_id>[^/.]+)/kick")
    def kick(self, request: Request, slug: str, user_id: str) -> Response:
        group = self._get_group(slug)
        service.kick(actor=request.user, group=group, target_user=self._user(user_id))
        return ok(message="Member kicked.")

    @action(detail=True, methods=["post"], url_path="members/(?P<user_id>[^/.]+)/ban")
    def ban(self, request: Request, slug: str, user_id: str) -> Response:
        group = self._get_group(slug)
        service.ban(actor=request.user, group=group, target_user=self._user(user_id))
        return ok(message="Member banned.")

    @action(detail=True, methods=["post"], url_path="members/(?P<user_id>[^/.]+)/mute")
    def mute(self, request: Request, slug: str, user_id: str) -> Response:
        group = self._get_group(slug)
        minutes = int(request.data.get("minutes", 60))
        service.mute(actor=request.user, group=group, target_user=self._user(user_id), minutes=minutes)
        return ok(message="Member muted.")

    @action(detail=True, methods=["post"], url_path="members/(?P<user_id>[^/.]+)/role")
    def set_role(self, request: Request, slug: str, user_id: str) -> Response:
        group = self._get_group(slug)
        member = service.set_role(actor=request.user, group=group,
                                  target_user=self._user(user_id), role=request.data.get("role", ""))
        return ok(GroupMemberSerializer(member).data, message="Role updated.")

    # ---- invites -------------------------------------------------------------
    @extend_schema(responses=InviteSerializer)
    @action(detail=True, methods=["get", "post"])
    def invites(self, request: Request, slug: str) -> Response:
        group = self._get_group(slug)
        if request.method == "POST":
            invite = service.create_invite(
                actor=request.user, group=group,
                max_uses=int(request.data.get("max_uses", 0)),
                expires_in_hours=request.data.get("expires_in_hours"),
            )
            return created(InviteSerializer(invite).data, message="Invite created.")
        return ok(InviteSerializer(selectors.active_invites(group=group), many=True).data)

    # ---- join requests -------------------------------------------------------
    @extend_schema(responses=JoinRequestSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="requests")
    def requests(self, request: Request, slug: str) -> Response:
        group = self._get_group(slug)
        return ok(JoinRequestSerializer(selectors.pending_requests(group=group), many=True).data)

    @action(detail=True, methods=["post"], url_path="requests/(?P<req_id>[^/.]+)/approve")
    def approve(self, request: Request, slug: str, req_id: str) -> Response:
        group = self._get_group(slug)
        req = get_object_or_404(JoinRequest, pk=req_id, group=group)
        member = service.approve_request(actor=request.user, request_obj=req)
        return ok(GroupMemberSerializer(member).data, message="Request approved.")

    @action(detail=True, methods=["post"], url_path="requests/(?P<req_id>[^/.]+)/reject")
    def reject(self, request: Request, slug: str, req_id: str) -> Response:
        group = self._get_group(slug)
        req = get_object_or_404(JoinRequest, pk=req_id, group=group)
        service.reject_request(actor=request.user, request_obj=req)
        return ok(message="Request rejected.")

    # ---- helpers -------------------------------------------------------------
    @staticmethod
    def _user(user_id: str):
        from apps.users.models import User
        return get_object_or_404(User, pk=user_id)


class InviteResolveView(viewsets.ViewSet):
    """Public-ish endpoint to redeem an invite code (still requires auth)."""

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"])
    def redeem(self, request: Request) -> Response:
        result = service.join_with_invite(user=request.user, code=request.data.get("code", ""))
        return ok(result, message="Joined group via invite.")
