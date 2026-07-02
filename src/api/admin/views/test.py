from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


@extend_schema(
    description="This is a test view"
)
class TestView(APIView):

    def get(self, request):
        return Response({"detail": 'Hello, world!'}, status=status.HTTP_200_OK)
