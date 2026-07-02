from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from apps.chat.views import index, room

urlpatterns = [
    path('', TemplateView.as_view(
        template_name='index.html'
    )),
    path('api/v1/', include('api.urls')),
    path('admin/', admin.site.urls),
    path('chat/', index, name="chat-app"),
    path('chat/<str:room_name>/', room, name="room-app"),
]

if settings.DEBUG:
    urlpatterns += [
        *static(settings.STATIC_URL, document_root=settings.STATIC_ROOT),
        *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    ]
