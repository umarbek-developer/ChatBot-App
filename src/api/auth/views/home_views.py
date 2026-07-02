from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from api.pagination import CustomPagination


class HomeAPIView(APIView):
    pagination_class = CustomPagination
    
    def get(self, request):
        user_id = request.GET.get("user_id")
        if not user_id:
            return Response(
                {'error': 'Iltimos, foydalanuvchi ID sini kiriting!'},
                status=status.HTTP_400_BAD_REQUEST
            )
        data = {
            "status": "success",
        }
        return Response(data, status=status.HTTP_200_OK)

