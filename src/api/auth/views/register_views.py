from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.users.models import User, UserOTPVerifications, UserOTPIDVerifications
from api.auth.serializers import user_serializers
from api.auth.send_mail_sms import send_otp_email
# from api.auth.tasks import send_otp_email_task # celery bilan yuborish kerak bo'lsa
from django.utils import timezone
from django.conf import settings
from datetime import timedelta

class RegisterViews(APIView):

    def send_otp_code(self, user, email):
        otp = UserOTPVerifications.objects.create(
            user=user,
            code="",
            expired_at=timezone.now(),
            error_expired_at=timezone.now()
        )
        code = otp.generate_code()
        send_otp_email(email, code, "otp")
        
    
    def send_otp_code_link(self, user, email):
        now = timezone.now()
        otp = UserOTPIDVerifications.objects.create(
            user=user,
            expired_at=now + timedelta(minutes=3),
            error_expired_at=timezone.now()
        )
        url = settings.BASE_URL_LINK + str(otp.code)
        send_otp_email(email, url, 'link')
        
    


    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        password2 = request.data.get("password2")
        otp_type = request.data.get("otp_type")

        if password != password2:
            return Response({
                "error": "Passwords not match"
            }, status=status.HTTP_400_BAD_REQUEST)
    
        try:
            User.objects.get(email=email).delete()
            return Response({
                "error": "Email already exists"
            }, status=status.HTTP_400_BAD_REQUEST)
        except:
            pass

        if otp_type not in ('link', 'otp'):
            return Response({
                "error": "OTP type not correct form (link, otp)"
            }, status=status.HTTP_400_BAD_REQUEST)
        ser = user_serializers.UserCreateSerializer(data=request.data)
        if ser.is_valid(raise_exception=True):
            ser.save()
            user = User.objects.get(email=email)
            if otp_type == "otp":
                self.send_otp_code(user, email)
                return Response({
                    "message": "Verifications code sent to your email"
                }, status=status.HTTP_201_CREATED)
            else:
                self.send_otp_code_link(user, email)
                return Response({
                    "message": "Verifications link sent to your email"
                }, status=status.HTTP_201_CREATED)
                
        return Response({
            "error": "Something went wrong"
        }, status=status.HTTP_400_BAD_REQUEST)
        

