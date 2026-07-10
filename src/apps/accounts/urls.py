from django.urls import path

from apps.accounts.views import (
    AvatarView,
    LogoutAllView,
    LogoutView,
    MeView,
    SessionListView,
)

urlpatterns = [
    path("accounts/me/", MeView.as_view(), name="accounts-me"),
    path("accounts/me/avatar/", AvatarView.as_view(), name="accounts-avatar"),
    path("accounts/sessions/", SessionListView.as_view(), name="accounts-sessions"),
    path("accounts/logout/", LogoutView.as_view(), name="accounts-logout"),
    path("accounts/logout-all/", LogoutAllView.as_view(), name="accounts-logout-all"),
]
