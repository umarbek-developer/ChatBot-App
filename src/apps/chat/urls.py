from django.urls import path

from apps.chat.views import CallHistoryView

urlpatterns = [
    path("calls/", CallHistoryView.as_view(), name="call-history"),
]
