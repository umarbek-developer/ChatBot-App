import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import ScopedRateThrottle
from apps.users.models import User, UserOTPVerifications, UserOTPIDVerifications
from api.auth.serializers import user_serializers
from api.auth.send_mail_sms import deliver_otp
from django.utils import timezone
from django.conf import settings
from datetime import timedelta

logger = logging.getLogger("api")


class RegisterViews(APIView):
    """Register a user (inactive) and email a verification code.

    Guarantees:
      * The user is created **inactive** and only activated after OTP verify.
      * If the email cannot be sent, the request FAILS (no fake success) and the
        just-created user is rolled back so the email is free to retry.
      * Re-registering an unverified email resends a code (non-destructive);
        an already-verified email is rejected, never deleted.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def _issue_otp_code(self, user) -> str:
        otp = UserOTPVerifications.objects.create(
            user=user, code="", expired_at=timezone.now(), error_expired_at=timezone.now(),
        )
        return otp.generate_code()

    def _issue_link_code(self, user) -> str:
        now = timezone.now()
        otp = UserOTPIDVerifications.objects.create(
            user=user,
            expired_at=now + timedelta(minutes=getattr(settings, "OTP_TTL_MINUTES", 10)),
            error_expired_at=now,
        )
        return settings.BASE_URL_LINK + str(otp.code)

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        password = request.data.get("password")
        password2 = request.data.get("password2")
        otp_type = request.data.get("otp_type")

        if password != password2:
            return Response({"error": "Passwords do not match"}, status=status.HTTP_400_BAD_REQUEST)
        if otp_type not in ("link", "otp"):
            return Response({"error": "otp_type must be 'otp' or 'link'"},
                            status=status.HTTP_400_BAD_REQUEST)

        # Non-destructive duplicate handling.
        existing = User.objects.filter(email=email).first()
        if existing and existing.is_active:
            return Response({"error": "This email is already registered. Please sign in."},
                            status=status.HTTP_400_BAD_REQUEST)
        if existing and not existing.is_active:
            # Stale unverified signup — clear it so the fresh data/password can be used.
            logger.info("Re-registration of unverified email %s; clearing stale record", email)
            existing.delete()

        ser = user_serializers.UserCreateSerializer(data={**request.data, "email": email})
        ser.is_valid(raise_exception=True)
        logger.info("Serializer validated for %s", email)
        user = ser.save()  # inactive by default (User.is_active default False)
        logger.info("User created (inactive) %s id=%s; issuing %s", email, user.id, otp_type)

        try:
            if otp_type == "otp":
                code = self._issue_otp_code(user)
                logger.info("OTP created for %s; dispatching email", email)
                deliver_otp(email, code, "otp")
                success_msg = "Verification code sent to your email"
            else:
                link = self._issue_link_code(user)
                deliver_otp(email, link, "link")
                success_msg = "Verification link sent to your email"
        except Exception as exc:
            # Never swallow: log the COMPLETE traceback, roll back, and surface
            # the real error in DEBUG so it's diagnosable (generic only in prod).
            logger.exception("OTP email delivery FAILED for %s", email)
            user.delete()
            detail = str(exc) if settings.DEBUG else (
                "We couldn't send the verification email right now. Please try again in a moment."
            )
            return Response(
                {"error": "Email delivery failed", "detail": detail,
                 "type": type(exc).__name__ if settings.DEBUG else None},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        logger.info("Registration OK for %s; awaiting verification", email)
        return Response({"message": success_msg}, status=status.HTTP_201_CREATED)
