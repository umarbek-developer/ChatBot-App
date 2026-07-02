from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.users.models import ChangePasswordLogs
from django.utils import timezone
from datetime import timedelta


class ChangePasswordViews(APIView):
    permission_classes = [IsAuthenticated]

    def create_change_password(self, user, exp_at):
        ChangePasswordLogs.objects.create(
            user=user,
            expired_at=exp_at,
            error_expired_at=self.now,
            old_password="",
            new_password=""
        )

    def validate_password_first(self, old_password, new_password, new_password2):
        if old_password == new_password:
            return "old pasword equal new password"
        elif new_password != new_password2:
            return "new passwords not match"
        return False
    
    def validate_password_last(self, new_password):
        symbles = ['!', "@", "#", "$", "%", "^", "&", "*", "(", ")", "?", ",", ".", "_", "-", "=", "[", "]", '"', "'", ":", ";"]
        if len(new_password) < 8:
            return "your password must be length more 8"
        elif len(new_password) > 35:
            return "your password must be length less 35"
        elif not any(char.isupper() for char in new_password):
            return "your password must contain capital letter"
        elif not any(char.isdigit() for char in new_password):
            return "your password must contain numbers"
        elif not any(char.islower() for char in new_password):
            return "your password must contain lower letter"
        elif not any(char in symbles for char in new_password):
            return "your password must contain symbles"
        return False
        
    def get(self, request):
        now = timezone.now()
        self.now = now
        change_password = ChangePasswordLogs.objects.filter(user=request.user).last()
        if change_password:
            user_is_blocked = change_password.is_blocked()
            if user_is_blocked:
                return Response({
                    "error": f"your account blocked until {user_is_blocked}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            can_changed = change_password.is_expired()
            if can_changed:
                return Response({
                    "message": f"you can change your password within {can_changed}"
                })
            
            if change_password.attapts > 5:
                change_password.error_expired_at = now + timedelta(days=3)
                change_password.attapts = 0
                change_password.save()
                return Response({
                    "error": f"your account blocked until {user_is_blocked}"

                }, status=status.HTTP_400_BAD_REQUEST)

            if change_password.created_at >= now - timedelta(days=3) and change_password.is_changed == False:
                change_password.attapts += 1
                change_password.expired_at = now + timedelta(minutes=15)
                change_password.save()
            else:
                self.create_change_password(request.user, now + timedelta(minutes=15))
        else:
            self.create_change_password(request.user, now + timedelta(minutes=15))

        return Response({
            "message": "you can change your password within 15 minutes"
        })
    
    def post(self, request):
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")
        new_password2 = request.data.get("new_password2")
        now = timezone.now()
        validate1 = self.validate_password_first(old_password, new_password, new_password2)
        if validate1:
            return Response({
                    "error": validate1
            }, status=status.HTTP_400_BAD_REQUEST)

        change_password = ChangePasswordLogs.objects.filter(user=request.user, is_changed=False).last()

        if not change_password:
            return Response({
                    "error": "You can open change request first"
            }, status=status.HTTP_400_BAD_REQUEST)

        if not change_password.is_expired():
            return Response({
                    "error": "times is up"
            }, status=status.HTTP_400_BAD_REQUEST)
        blocked = change_password.is_blocked()
        if blocked:
            return Response({
                    "error": f"your account blocked for {blocked}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if change_password.attapts > 5:
            change_password.attapts = 0
            change_password.error_expired_at = now + timedelta(days=1)
            change_password.expired_at = now
            change_password.save()
            return Response({
                    "error": f"your account blocked until 1 days"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not request.user.check_password(old_password):
            change_password.attapts += 1
            change_password.save()
            return Response({
                    "error": f"old password not match"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        validate2 = self.validate_password_last(new_password)
        if validate2:
            return Response({
                    "error": validate2
            }, status=status.HTTP_400_BAD_REQUEST)
        
        request.user.set_password(new_password)
        request.user.save()
        change_password.is_changed = True
        change_password.expired_at = now
        change_password.old_password = old_password
        change_password.new_password = new_password
        change_password.save()

        return Response({
            "message": "your password changed successfully"
        })
