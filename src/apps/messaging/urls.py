from django.urls import path

from apps.messaging.views import VoiceUploadView

urlpatterns = [
    path("voice/", VoiceUploadView.as_view(), name="voice-upload"),
]
