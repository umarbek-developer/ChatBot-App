from django.db.models import Q
from django.shortcuts import render
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from apps.chat.models import Call
from apps.chat.serializers import CallSerializer
from apps.common.pagination import StandardPageNumberPagination


# --- existing template views (unchanged) ---
def index(request):
    return render(request, "chat/index.html")


def room(request, room_name):
    return render(request, "chat/room.html", {"room_name": room_name})


# --- call history API ---
class CallHistoryView(ListAPIView):
    """Recent calls involving the current user (outgoing + incoming)."""

    serializer_class = CallSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPageNumberPagination

    def get_queryset(self):
        user = self.request.user
        return (
            Call.objects.select_related("caller", "receiver")
            .filter(Q(caller=user) | Q(receiver=user))
            .order_by("-created_at")
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["user_id"] = self.request.user.pk
        return ctx
