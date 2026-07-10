"""Account services: session lifecycle and device registration.

This is the seam between stateless JWTs and the stateful, revocable session
records the platform needs for device management and "log out everywhere".
Views call these; they never mint tokens or touch the blacklist directly.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Device, Session
from apps.common.models import AuditLog
from apps.common.services import BaseService


class SessionService(BaseService):
    """Owns creation/rotation/revocation of authenticated sessions."""

    def issue(
        self,
        *,
        user: Any,
        request: Any = None,
        device: Device | None = None,
    ) -> dict[str, Any]:
        """Mint a refresh/access pair and record a revocable Session.

        Returns a serialisable dict with both tokens and the session id so the
        client can later reference the session it wants to revoke.
        """
        refresh = RefreshToken.for_user(user)
        jti = str(refresh.get("jti", ""))
        expires_at = self._expiry(refresh)

        with self.atomic():
            session = Session.objects.create(
                user=user,
                device=device,
                refresh_jti=jti,
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
                expires_at=expires_at,
                last_used_at=timezone.now(),
            )
            self.audit(
                actor=user,
                action=AuditLog.Action.LOGIN,
                target=session,
                metadata={"device_id": getattr(device, "device_id", None)},
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )

        return {
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh),
            "session_id": str(session.id),
            "expires_at": expires_at.isoformat(),
        }

    def revoke(self, *, session: Session, actor: Any = None) -> None:
        """Revoke a single session and blacklist its refresh token."""
        with self.atomic():
            self._blacklist(session.refresh_jti)
            session.revoke()
            self.audit(actor=actor or session.user, action=AuditLog.Action.LOGOUT, target=session)

    def logout_all(self, *, user: Any, except_session: Session | None = None) -> int:
        """Revoke every active session for a user (log out everywhere).

        Returns the number of sessions revoked. Optionally keeps the current
        session alive (``except_session``) for "log out other devices".
        """
        qs = Session.objects.filter(user=user, revoked_at__isnull=True)
        if except_session is not None:
            qs = qs.exclude(pk=except_session.pk)

        count = 0
        with self.atomic():
            for session in qs.select_for_update():
                self._blacklist(session.refresh_jti)
                session.revoke()
                count += 1
            self.audit(actor=user, action=AuditLog.Action.LOGOUT, target=user,
                       metadata={"scope": "all", "revoked": count})
        return count

    # internals ---------------------------------------------------------------
    @staticmethod
    def _expiry(refresh: RefreshToken) -> datetime:
        # Derive from the token lifetime so the value's tz-awareness matches the
        # project's USE_TZ setting (and therefore what the DB backend accepts).
        return timezone.now() + refresh.lifetime

    @staticmethod
    def _blacklist(jti: str) -> None:
        """Blacklist an outstanding refresh token by jti, if the app is enabled."""
        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                BlacklistedToken,
                OutstandingToken,
            )
        except Exception:  # pragma: no cover - blacklist app not installed
            return
        for token in OutstandingToken.objects.filter(jti=jti):
            BlacklistedToken.objects.get_or_create(token=token)


class DeviceService(BaseService):
    """Registers/updates the calling client's device record (upsert by device_id)."""

    def register(
        self,
        *,
        user: Any,
        device_id: str,
        name: str = "",
        platform: str = Device.Platform.UNKNOWN,
        push_token: str = "",
    ) -> Device:
        device, _ = Device.objects.update_or_create(
            user=user,
            device_id=device_id,
            defaults={
                "name": name,
                "platform": platform,
                "push_token": push_token,
                "is_active": True,
                "last_active_at": timezone.now(),
            },
        )
        return device


def _client_ip(request: Any) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _user_agent(request: Any) -> str:
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:1024]
