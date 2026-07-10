from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.users.models import User
from apps.accounts.services import DeviceService, SessionService
from api.auth.serializers.user_serializers import UserLoginSerializer


class LoginView(APIView):

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        message = "Email or password wrong"
        try:
            user = User.objects.get(email=email)
            if user.check_password(password):
                if user.is_active:
                    # Record a revocable session (enables device/session management
                    # and logout-all) while keeping the original response shape.
                    device = None
                    device_id = request.data.get("device_id")
                    if device_id:
                        device = DeviceService().register(
                            user=user, device_id=str(device_id),
                            name=request.data.get("device_name", ""),
                            platform=request.data.get("platform", "web"),
                        )
                    tokens = SessionService().issue(user=user, request=request, device=device)
                    return Response({
                        "message": "Login successs",
                        "user": UserLoginSerializer(user).data,
                        "token": {
                            "access_token": tokens["access_token"],
                            "refresh_token": tokens["refresh_token"],
                        },
                        "session_id": tokens["session_id"],
                    }, status=status.HTTP_200_OK)
                message = "User not verified!"
        except User.DoesNotExist:
            pass

        return Response({
            "error": message,
        }, status=status.HTTP_400_BAD_REQUEST)
    
