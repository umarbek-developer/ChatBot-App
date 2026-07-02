from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.users.models import ChangeEmailLogs
from django.utils import timezone
from datetime import timedelta
from apps.users.models import User
from api.auth.send_mail_sms import send_otp_email
# from api.auth.tasks import send_otp_email_task # celery bilan yuborish kerak bo'lsa
import re



class ChangeEmailViews(APIView):
    permission_classes = [IsAuthenticated]

    def create_change_email(self, user, exp_at): 
        ChangeEmailLogs.objects.create(
            user=user,
            expired_at=exp_at,
            error_expired_at=self.now,              
        )
    
    def check_email(self, email):
        # Emailni tekshirish uchun andoza (pattern)
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        
        # re.match() yordamida email andozaga mos kelishini tekshiramiz
        if re.match(pattern, email):
            return True
        return False

    def get(self, request):
        now = timezone.now()
        self.now = now
        change_email_obj = ChangeEmailLogs.objects.filter(user=request.user).last()
        if change_email_obj:
            user_is_blocked = change_email_obj.is_blocked()
            if user_is_blocked:
                return Response({
                    "error": f"your account blocked until {user_is_blocked}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            can_changed = change_email_obj.is_expired()
            if can_changed:
                return Response({
                    "message": f"you can change your email within {can_changed}"
                })
        
            if change_email_obj.attapts > 5:
                change_email_obj.error_expired_at = now + timedelta(days=3)
                change_email_obj.attapts = 0
                change_email_obj.save()
                return Response({
                    "error": f"your account blocked until {user_is_blocked}"

                }, status=status.HTTP_400_BAD_REQUEST)
        
            if change_email_obj.created_at >= now - timedelta(days=3) and change_email_obj.is_changed == False:
                change_email_obj.attapts += 1
                change_email_obj.expired_at = now + timedelta(minutes=15)
                change_email_obj.save()
            else:
                self.create_change_email(request.user, now + timedelta(minutes=15))
        else:
            self.create_change_email(request.user, now + timedelta(minutes=15))
        
        return Response({
            "message": "you can change your email within 15 minute"
        })

    def post(self, request):
        now = timezone.now()
        self.now = now
        change_email_obj = ChangeEmailLogs.objects.filter(user=request.user).last()
        if change_email_obj:
            user_is_blocked = change_email_obj.is_blocked()
            if user_is_blocked:
                return Response({
                    "error": f"your account blocked until {user_is_blocked}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            can_changed = change_email_obj.is_expired()
            if can_changed:
                email = request.data.get("email")
                validate = self.check_email(email)
                if not validate:
                    return Response({
                        "error": "email incorect format"
                    }, status=status.HTTP_400_BAD_REQUEST)
                try:
                    User.objects.get(email=email)
                    return Response({
                        "error": "this email already existst"
                    }, status=status.HTTP_400_BAD_REQUEST)
                except:
                    pass 
                change_email_obj.generate_code()
                change_email_obj.new_email = email
                change_email_obj.attapts = 1
                change_email_obj.save()
                print(change_email_obj.code)
                send_otp_email(
                    email, change_email_obj.code
                )
                return Response({
                    "message": f"this {email} verifications code sent"
                })
            
        return Response({
                "error": "you can't this action"
            }, status=status.HTTP_400_BAD_REQUEST)