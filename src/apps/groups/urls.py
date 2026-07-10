from rest_framework.routers import DefaultRouter

from apps.groups.views import GroupViewSet, InviteResolveView

router = DefaultRouter()
router.include_root_view = False
router.register(r"groups", GroupViewSet, basename="group")
router.register(r"invites", InviteResolveView, basename="invite")

urlpatterns = router.urls
