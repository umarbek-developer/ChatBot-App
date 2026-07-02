from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views.test import TestView

router = DefaultRouter()
router.include_root_view = False

urlpatterns = [

    path('test/', TestView.as_view(), name='test'),
    path('', include(router.urls))
]
