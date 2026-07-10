from django.urls import path, include

urlpatterns = [
    path('admin/', include('api.admin.urls')),
    path('user/', include('api.user.urls')),
    path('', include('apps.groups.urls')),
    path('', include('apps.messaging.urls')),
    path('', include('apps.chat.urls')),
    path('', include('apps.accounts.urls')),
    path('', include('api.auth.urls')),
]
