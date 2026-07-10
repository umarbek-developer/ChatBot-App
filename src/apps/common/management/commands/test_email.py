"""``python manage.py test_email you@example.com``

Isolates SMTP problems from the registration flow. Prints the loaded email
configuration (password only as "loaded/MISSING", never the value), performs a
raw SMTP connect → STARTTLS → AUTH probe, then sends a real message through the
project's own ``send_otp_email`` path. Any failure prints the COMPLETE traceback.
"""
from __future__ import annotations

import smtplib
import socket
import ssl
import traceback

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test verification email to diagnose SMTP/email configuration."

    def add_arguments(self, parser):
        parser.add_argument("recipient", help="Destination email address")
        parser.add_argument("--code", default="123456", help="OTP code to embed (default 123456)")

    def handle(self, *args, **opts):
        recipient = opts["recipient"]
        self.stdout.write(self.style.MIGRATE_HEADING("\n1) Loaded email configuration"))
        cfg = {
            "DEBUG": settings.DEBUG,
            "EMAIL_BACKEND": settings.EMAIL_BACKEND,
            "EMAIL_HOST": settings.EMAIL_HOST,
            "EMAIL_PORT": settings.EMAIL_PORT,
            "EMAIL_USE_TLS": settings.EMAIL_USE_TLS,
            "EMAIL_USE_SSL": getattr(settings, "EMAIL_USE_SSL", False),
            "EMAIL_HOST_USER": settings.EMAIL_HOST_USER or "(EMPTY!)",
            "EMAIL_HOST_PASSWORD": "loaded" if settings.EMAIL_HOST_PASSWORD else "MISSING!",
            "EMAIL_TIMEOUT": getattr(settings, "EMAIL_TIMEOUT", None),
            "DEFAULT_FROM_EMAIL": settings.DEFAULT_FROM_EMAIL,
            "SERVER_EMAIL": getattr(settings, "SERVER_EMAIL", None),
            "EMAIL_USE_CELERY": getattr(settings, "EMAIL_USE_CELERY", None),
        }
        for k, v in cfg.items():
            self.stdout.write(f"   {k:<20} = {v}")

        if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            raise CommandError(
                "EMAIL_HOST_USER / EMAIL_HOST_PASSWORD are empty. Populate them in .env "
                "and RESTART the process (long-running workers cache the old environment)."
            )

        # --- raw SMTP probe (skipped for non-SMTP backends like locmem/console) ---
        if "smtp" in settings.EMAIL_BACKEND.lower():
            self.stdout.write(self.style.MIGRATE_HEADING("\n2) Raw SMTP probe (DNS → connect → STARTTLS → AUTH)"))
            try:
                self.stdout.write(f"   Resolving {settings.EMAIL_HOST} ...")
                socket.getaddrinfo(settings.EMAIL_HOST, settings.EMAIL_PORT)
                self.stdout.write("   DNS OK. Connecting ...")
                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT,
                                      timeout=getattr(settings, "EMAIL_TIMEOUT", 20))
                server.ehlo()
                if settings.EMAIL_USE_TLS:
                    self.stdout.write("   STARTTLS ...")
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                self.stdout.write("   AUTH LOGIN ...")
                server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                server.quit()
                self.stdout.write(self.style.SUCCESS("   SMTP AUTH OK ✓"))
            except smtplib.SMTPAuthenticationError as e:
                self.stderr.write(self.style.ERROR(f"   SMTP AUTH FAILED: {e.smtp_code} {e.smtp_error}"))
                self.stderr.write("   → The Gmail App Password is wrong/revoked, or 2FA is off. Regenerate it.")
                raise CommandError("SMTP authentication failed.")
            except (socket.timeout, TimeoutError):
                raise CommandError(f"Timeout connecting to {settings.EMAIL_HOST}:{settings.EMAIL_PORT} "
                                   "— outbound SMTP is likely blocked (firewall/host).")
            except OSError as e:
                raise CommandError(f"Network/connection error: {e}")

        # --- send via the project's real code path ---
        self.stdout.write(self.style.MIGRATE_HEADING("\n3) Sending via send_otp_email()"))
        try:
            from api.auth.send_mail_sms import send_otp_email
            delivered = send_otp_email(recipient, opts["code"], "otp")
            self.stdout.write(self.style.SUCCESS(
                f"   send_otp_email delivered {delivered} message(s) to {recipient} ✓"
            ))
        except Exception:
            self.stderr.write(self.style.ERROR("   SEND FAILED — full traceback:\n"))
            self.stderr.write(traceback.format_exc())
            raise CommandError("Email send failed (see traceback above).")

        self.stdout.write(self.style.SUCCESS(f"\n✅ Test email sent to {recipient}. Check that inbox (and spam)."))
