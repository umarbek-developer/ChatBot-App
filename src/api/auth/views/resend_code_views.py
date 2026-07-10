import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.users.models import User, UserOTPVerifications, ChangeEmailLogs
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from api.auth.send_mail_sms import deliver_otp
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

logger = logging.getLogger("api")


def _email_failure(email, exc):
    """Log the full traceback and return a 502 with the real cause in DEBUG."""
    logger.exception("OTP resend email delivery FAILED for %s", email)
    detail = str(exc) if settings.DEBUG else "We couldn't resend the code right now. Please try again."
    return Response({"error": "Email delivery failed", "detail": detail,
                     "type": type(exc).__name__ if settings.DEBUG else None},
                    status=status.HTTP_502_BAD_GATEWAY)


class ResendVerificationsOTPView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp_resend"

    def send_otp_code(self, otp_data):
        code = otp_data.generate_code()
        return deliver_otp(otp_data.user.email, code, "otp")

    def post(self, request, otp_type):
        email = request.data.get("email")
        if otp_type not in ("otp", "link"):
            return Response({
                "error": "error from sending resend code"
            }, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email=email)
        except:
            return Response({
                "error": "error from sending resend code"
            }, status=status.HTTP_400_BAD_REQUEST)
        otp_data = UserOTPVerifications.objects.filter(user=user).last()
        now = timezone.now()
        if not otp_data:
            return Response({
                "error": "error from sending resend code"
            }, status=status.HTTP_400_BAD_REQUEST)

        # NOTE: resend is intentionally allowed while the current code is still
        # valid (the user may not have received it). Abuse is bounded by
        # resend_attapts (max 3 -> 1-day block), error_expired_at, the DRF
        # throttle (5/hour) and the client-side cooldown timer.
        if otp_data.resend_attapts >= 3:
            otp_data.error_expired_at = now + timedelta(days=1)
            otp_data.resend_attapts = 0
            otp_data.attapts = 0
            otp_data.save()
            return Response({
                "error": f"you can resend mail code after: {otp_data.error_expired_at}"
            }, status=status.HTTP_400_BAD_REQUEST)

        if now < otp_data.error_expired_at:
            return Response({
                "error": f"you can resend mail code after: {otp_data.error_expired_at}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if now - timedelta(minutes=5) > otp_data.expired_at:
            return Response({
                "error": "error from sending resend code"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            self.send_otp_code(otp_data)
        except Exception as exc:
            return _email_failure(email, exc)
        otp_data.resend_attapts += 1
        otp_data.save()

        return Response({
            "message": "Verifications code sent to your email"
        }, status=status.HTTP_201_CREATED)
            

class ResendVerificationsOTPForChangeEmailView(APIView):
    permission_classes = [IsAuthenticated]

    def send_otp_code(self, otp_data):
        code = otp_data.generate_code()
        return deliver_otp(otp_data.user.email, code, "otp")

    def post(self, request, otp_type):
        if otp_type not in ("otp", "link"):
            return Response({
                "error": "error from sending resend code"
            }, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        change_email_obj = ChangeEmailLogs.objects.filter(user=request.user, is_changed=False).last()
        if change_email_obj:
            if change_email_obj.created_at <= now - timedelta(minutes=30):
                return Response({
                    "error": "You can't this actions."
                }, status=status.HTTP_400_BAD_REQUEST)
            user_is_blocked = change_email_obj.is_blocked()
            if user_is_blocked:
                return Response({
                    "error": f"your account blocked until {user_is_blocked}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            can_changed = change_email_obj.is_expired()
            if can_changed:
                return Response({
                    "message": f"Verifications code is active now {can_changed}"
                }, status=status.HTTP_201_CREATED)

            if change_email_obj.resend_attapts >= 3:
                change_email_obj.expired_at = now - timedelta(minutes=10)
                change_email_obj.attapts = 0
                change_email_obj.error_expired_at = now + timedelta(days=2)
                change_email_obj.code = ""
                change_email_obj.save()
                return Response({
                    "error": f"Your account blocked until {change_email_obj.error_expired_at}"
                }, status=status.HTTP_400_BAD_REQUEST)
            change_email_obj.resend_attapts += 1
            change_email_obj.attapts = 0
            change_email_obj.save()
            try:
                self.send_otp_code(change_email_obj)
            except Exception as exc:
                return _email_failure(change_email_obj.user.email, exc)

            return Response({
                "message": "Verifications code sent to your email"
            }, status=status.HTTP_201_CREATED)

        return Response({
            "error": "You can't this actions."
        }, status=status.HTTP_400_BAD_REQUEST)
            
