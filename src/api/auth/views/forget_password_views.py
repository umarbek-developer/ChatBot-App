from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.users.models import UserOTPVerifications
from django.utils import timezone
from datetime import timedelta
from api.auth.send_mail_sms import send_otp_email
# from api.auth.tasks import send_otp_email_task # celery bilan yuborish kerak bo'lsa




class ForgetPasswordView(APIView):

    def send_otp_code(self, otp_data):
        otp = UserOTPVerifications.objects.create(
            user=otp_data.user,
            code="",
            for_forget_password=True,
            expired_at=timezone.now(),
            error_expired_at=timezone.now()
        )
        code = otp.generate_code()
        send_otp_email(otp.user.email, code, "otp")

    def post(self, request, otp_type):
        email = request.data.get("email")
        if otp_type not in ("otp", "link"):
            return Response({
                "error": "Otp type error, need to (otp, link)"
            }, status=status.HTTP_400_BAD_REQUEST)
        if not email:
            return Response({
                "error": "Email is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now()
        otp_data = UserOTPVerifications.objects.filter(user__email=email).last()
        if otp_data:
            if otp_data.error_expired_at > now:
                return Response({
                    "error": f"Your account blocked until {otp_data.error_expired_at}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if otp_data.resend_attapts >= 3:
                otp_data.error_expired_at = now + timedelta(days=1)
                otp_data.resend_attapts = 0
                otp_data.attapts = 0
                otp_data.save()
                return Response({
                    "error": f"you can resend mail code after: {otp_data.error_expired_at}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if otp_data.is_code_expired():
                return Response({
                    "error": f"you can resend mail code after: {otp_data.expired_at}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            otp_data.resend_attapts += 1
            otp_data.save()
            self.send_otp_code(otp_data)



        return Response({
            "message": "Verifications code sent to your email"
        }, status=status.HTTP_200_OK)
        
        
class SetForgetPasswordView(APIView):

    def validate_password(self, password, password2):
        symbles = ['!', "@", "#", "$", "%", "^", "&", "*", "(", ")", "?", ",", ".", "_", "-", "=", "[", "]", '"', "'", ":", ";"]
        if password != password2:
            return "passwords not equal"
        elif len(password) < 8:
            return "your password must be length more 8"
        elif len(password) > 35:
            return "your password must be length less 35"
        elif not any(char.isupper() for char in password):
            return "your password must contain capital letter"
        elif not any(char.isdigit() for char in password):
            return "your password must contain numbers"
        elif not any(char.islower() for char in password):
            return "your password must contain lower letter"
        elif not any(char in symbles for char in password):
            return "your password must contain symbles"
        return False

    def post(self, request):
        email = request.data.get("email")
        new_password = request.data.get("new_password")
        new_password_again = request.data.get("new_password_again")
        if not email or not new_password or not new_password_again:
            return Response({
                "error": "Email, new_password, new_password_again is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now()
        otp_data = UserOTPVerifications.objects.filter(user__email=email, for_forget_password=True, for_forget_password_verified=True).last()
        if otp_data:
            if otp_data.error_expired_at > now:
                return Response({
                    "error": f"Your account blocked until {otp_data.error_expired_at}"
                }, status=status.HTTP_400_BAD_REQUEST)
            if otp_data.resend_attapts >= 3:
                otp_data.error_expired_at = now + timedelta(days=1)
                otp_data.resend_attapts = 0
                otp_data.attapts = 0
                otp_data.save()
                return Response({
                    "error": f"you can resend mail code after: {otp_data.error_expired_at}"
                }, status=status.HTTP_400_BAD_REQUEST)
            if not otp_data.is_code_expired():
                return Response({
                    "error": f"you can't change password time expired. please try later."
                }, status=status.HTTP_400_BAD_REQUEST)
            resp = self.validate_password(new_password, new_password_again)
            if not resp:
                otp_data.for_forget_password_verified = False
                otp_data.expired_at = now - timedelta(minutes=30)
                otp_data.user.set_password(new_password)
                otp_data.user.save()
                otp_data.save()
                return Response({
                    "message": "your password successfully changed!"
                }, status=status.HTTP_200_OK)
            return Response({
                "error": resp
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            "error": "Something went wrong!"
        }, status=status.HTTP_400_BAD_REQUEST)
