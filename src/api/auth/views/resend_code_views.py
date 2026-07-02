from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.users.models import User, UserOTPVerifications, ChangeEmailLogs
from django.utils import timezone
from datetime import timedelta
from api.auth.send_mail_sms import send_otp_email
# from api.auth.tasks import send_otp_email_task # celery bilan yuborish kerak bo'lsa
from rest_framework.permissions import IsAuthenticated

    
class ResendVerificationsOTPView(APIView):

    def send_otp_code(self, otp_data):
        code = otp_data.generate_code()
        send_otp_email(otp_data.user.email, code, "otp")

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

        if otp_data.is_code_expired():
            return Response({
                "error": f"you can resend mail code after: {otp_data.expired_at}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
        
        otp_data.resend_attapts += 1
        self.send_otp_code(otp_data)

        return Response({
            "message": "Verifications code sent to your email"
        }, status=status.HTTP_201_CREATED)
            

class ResendVerificationsOTPForChangeEmailView(APIView):
    permission_classes = [IsAuthenticated]

    def send_otp_code(self, otp_data):
        code = otp_data.generate_code()
        send_otp_email(otp_data.user.email, code, "otp")

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
            self.send_otp_code(change_email_obj)

            return Response({
                "message": "Verifications code sent to your email"
            }, status=status.HTTP_201_CREATED)

        return Response({
            "error": "You can't this actions."
        }, status=status.HTTP_400_BAD_REQUEST)
            
