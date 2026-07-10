"""Celery tasks for authentication emails."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("email")


@shared_task(name="send_otp_email_task", bind=True, max_retries=3, default_retry_delay=10)
def send_otp_email_task(self, user_email: str, otp_code: str, otp_type: str = "otp"):
    """Send an OTP email in the background, retrying transient SMTP failures.

    Delegates to the single source of truth (``send_otp_email``) so sync and
    async paths behave identically. Exceptions are logged and retried, never
    swallowed.
    """
    from api.auth.send_mail_sms import send_otp_email

    logger.info("Celery task: sending %s email to %s", otp_type, user_email)
    try:
        return send_otp_email(user_email, otp_code, otp_type)
    except Exception as exc:
        logger.exception("Celery OTP email task failed for %s (attempt %s)",
                         user_email, self.request.retries + 1)
        raise self.retry(exc=exc)
