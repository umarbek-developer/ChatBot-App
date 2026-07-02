from django.urls import path, include

urlpatterns = [
    path('admin/', include('api.admin.urls')),
    path('user/', include('api.user.urls')),
    path('', include('api.auth.urls')),
]
