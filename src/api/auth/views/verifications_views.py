from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.users.models import UserOTPVerifications, UserOTPIDVerifications, ChangeEmailLogs
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import redirect
from rest_framework.permissions import IsAuthenticated


class VerificationsOTPView(APIView):

    def post(self, request):
        email = request.data.get("email")
        code = request.data.get("code")
        if not email or not code or len(code) != 6:
            return Response({
                "error": "Email and code required"
            }, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now()
        try:
            otp = UserOTPVerifications.objects.get(user__email=email, for_forget_password=False)
            if otp.error_expired_at > now:
                return Response({
                    "error": f"Your account blocked until {otp.error_expired_at}"
                }, status=status.HTTP_400_BAD_REQUEST)
            if code != otp.code:
                otp.attapts += 1
                if otp.attapts > 6:
                    otp.expired_at = now - timedelta(minutes=10)
                    otp.attapts = 0
                    otp.error_expired_at = now + timedelta(minutes=5)
                    otp.code = ""
                    otp.save()
                    return Response({
                        "error": f"Your account blocked until {otp.error_expired_at}"
                    }, status=status.HTTP_400_BAD_REQUEST)
                otp.save()
                return Response({
                    "error": f"sms code wrong! attapts: {otp.attapts}"
                }, status=status.HTTP_400_BAD_REQUEST)

            if not otp.is_code_expired():
                return Response({
                    "error": f"sms code expired. please resend!"
                }, status=status.HTTP_400_BAD_REQUEST)
            otp.expired_at = now - timedelta(minutes=10)
            otp.user.is_active = True
            otp.user.save()
            otp.save()

            return Response({
                "error": "Your account verified!"
            }, status=status.HTTP_200_OK)

        except:
            return Response({
                "error": "Verifications code expired!"
            }, status=status.HTTP_400_BAD_REQUEST)
        
    
class VerificationsOTPLinkView(APIView):

    def get(self, request, link_id):
        try:
            otp_link = UserOTPIDVerifications.objects.get(code=link_id)
            if otp_link.is_code_expired():
                otp_link.user.is_active = True
                otp_link.user.save()
                return redirect("https://google.com")
            return Response({
                "error": "Verifications code expired! please resend link"
            }, status=status.HTTP_400_BAD_REQUEST)
        except:
            return Response({
                "error": "Verifications code expired!"
            }, status=status.HTTP_400_BAD_REQUEST)
    

class VerificationsOTPForgetPasswrdView(APIView):

    def post(self, request):
        email = request.data.get("email")
        code = request.data.get("code")
        if not email or not code or len(code) != 6:
            return Response({
                "error": "Email and code required"
            }, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now()
        otp_data = UserOTPVerifications.objects.filter(user__email=email, for_forget_password=True).last()
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
                    "error": f"otp code expired!"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if otp_data.code == code:
                otp_data.for_forget_password_verified = True
                otp_data.expired_at = now + timedelta(minutes=30)
                otp_data.save()
                return Response({
                    "message": "You can add new passoword until 30 minutes"
                }, status=status.HTTP_200_OK)
        
        return Response({
            "error": "verifications code wrong!"
        }, status=status.HTTP_400_BAD_REQUEST)


class VerificationsOTPForChangeEmailView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get("code")
        if not code or len(code) != 6:
            return Response({
                "error": "code required"
            }, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now()
        change_email_obj = ChangeEmailLogs.objects.filter(user=request.user, is_changed=False).last()
        if change_email_obj:
            user_is_blocked = change_email_obj.is_blocked()
            if user_is_blocked:
                return Response({
                    "error": f"your account blocked until {user_is_blocked}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            can_changed = change_email_obj.is_expired()
            if not can_changed:
                return Response({
                    "error": "code expired please resend"
                }, status=status.HTTP_400_BAD_REQUEST)

            if code != change_email_obj.code:
                change_email_obj.attapts += 1
                if change_email_obj.attapts > 6:
                    change_email_obj.expired_at = now - timedelta(minutes=10)
                    change_email_obj.attapts = 0
                    change_email_obj.error_expired_at = now + timedelta(hours=1)
                    change_email_obj.code = ""
                    change_email_obj.save()
                    return Response({
                        "error": f"Your account blocked until {change_email_obj.error_expired_at}"
                    }, status=status.HTTP_400_BAD_REQUEST)
                change_email_obj.save()
                return Response({
                    "error": f"sms code wrong! attapts: {change_email_obj.attapts}"
                }, status=status.HTTP_400_BAD_REQUEST)

            change_email_obj.expired_at = now - timedelta(minutes=10)
            change_email_obj.is_changed = True
            change_email_obj.old_email = change_email_obj.user.email
            change_email_obj.user.email = change_email_obj.new_email
            change_email_obj.user.save()
            change_email_obj.save()

            return Response({
                "error": "Your email changed successfully!"
            }, status=status.HTTP_200_OK)

        else:
            return Response({
                "error": "Verifications code expired!"
            }, status=status.HTTP_400_BAD_REQUEST)
        
    