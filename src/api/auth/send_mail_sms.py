"""OTP / verification email delivery.

Two layers:

* ``send_otp_email`` — the low-level sender. Renders the branded HTML (+ plain
  text fallback) and sends it, **raising on any failure** and logging every
  step. It never swallows exceptions (that was the original bug that hid SMTP
  errors behind a fake success).
* ``deliver_otp`` — the caller-facing router. Uses Celery in production and
  synchronous sending in development (per ``settings.EMAIL_USE_CELERY``), with a
  sync fallback if the broker is unreachable. Returns ``True``/``False`` so views
  can report a real failure instead of faking "code sent".
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger("email")

_SUBJECTS = {
    "otp": "Your Pulse verification code",
    "link": "Confirm your Pulse account",
}


def send_otp_email(user_email: str, otp_code, otp_type: str = "otp") -> int:
    """Render and send a verification email. Raises on failure (never silent).

    Returns the number of successfully delivered messages (1 on success).
    """
    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        logger.error(
            "Email credentials are empty (EMAIL_HOST_USER/EMAIL_PASSWORD). "
            "Check that .env is populated AND the server process was restarted "
            "after adding them — long-running workers cache the old environment."
        )
        raise RuntimeError("Email is not configured on the server.")

    template = "verify_email.html" if otp_type == "otp" else "verify_email_link.html"
    context = {
        "code": otp_code,
        "link": otp_code,
        "minutes": getattr(settings, "OTP_TTL_MINUTES", 10),
        "support_email": settings.EMAIL_HOST_USER,
    }

    try:
        html_body = render_to_string(template, context)
    except Exception:
        logger.exception("Failed to render OTP email template %s", template)
        raise

    text_body = strip_tags(html_body)
    from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER
    subject = _SUBJECTS.get(otp_type, "Verification")

    message = EmailMultiAlternatives(subject, text_body, from_email, [user_email])
    message.attach_alternative(html_body, "text/html")

    logger.info("Sending '%s' verification email to %s (from=%s)", otp_type, user_email, from_email)
    delivered = message.send(fail_silently=False)  # raises on SMTP/auth/TLS errors
    logger.info("SMTP send() reported %s delivered message(s) to %s", delivered, user_email)
    return delivered


def deliver_otp(user_email: str, otp_code, otp_type: str = "otp") -> None:
    """Dispatch the OTP email.

    * Production / ``EMAIL_USE_CELERY`` → queue a Celery task (fire-and-forget;
      the task logs + retries). Falls back to sync send if the broker is down.
    * Development → send synchronously and **let exceptions propagate** so the
      caller can surface the *real* error (no silent failure, no generic mask).
    """
    if getattr(settings, "EMAIL_USE_CELERY", False):
        try:
            from api.auth.tasks import send_otp_email_task

            send_otp_email_task.delay(user_email, str(otp_code), otp_type)
            logger.info("Queued OTP email task for %s via Celery", user_email)
            return
        except Exception:
            logger.exception("Could not queue Celery email task; falling back to sync send")

    # Synchronous path: raises on any failure (creds/DNS/TLS/auth/SMTP) with a
    # full traceback logged by send_otp_email + the caller.
    send_otp_email(user_email, otp_code, otp_type)
