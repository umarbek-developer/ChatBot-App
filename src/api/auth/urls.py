from django.urls import include, path
from rest_framework.routers import DefaultRouter
from api.auth.views.login_views import LoginView
from api.auth.views.register_views import RegisterViews
from api.auth.views.verifications_views import VerificationsOTPView, VerificationsOTPLinkView, \
    VerificationsOTPForgetPasswrdView, VerificationsOTPForChangeEmailView
from api.auth.views.resend_code_views import ResendVerificationsOTPView, ResendVerificationsOTPForChangeEmailView
from api.auth.views.forget_password_views import ForgetPasswordView, SetForgetPasswordView
from api.auth.views.change_password_views import ChangePasswordViews
from api.auth.views.change_email_views import ChangeEmailViews


router = DefaultRouter()
router.include_root_view = False

urlpatterns = [
    path("auth/login/", LoginView.as_view()),
    path("auth/resend/<str:otp_type>/", ResendVerificationsOTPView.as_view()),
    path("auth/register/", RegisterViews.as_view()),
    path("auth/register/otp/verify/", VerificationsOTPView.as_view()),
    path("auth/register/confirmations/<uuid:link_id>/", VerificationsOTPLinkView.as_view()),
    path("auth/forget-password/otp/verify/", VerificationsOTPForgetPasswrdView.as_view()),
    path("auth/forget-password/set/", SetForgetPasswordView.as_view()),
    path("auth/forget-password/<str:otp_type>/", ForgetPasswordView.as_view()),
    path("auth/change-password/", ChangePasswordViews.as_view()),
    path("auth/change-email/", ChangeEmailViews.as_view()),
    path("auth/change-email/verification/resend/<str:otp_type>/", ResendVerificationsOTPForChangeEmailView.as_view()),
    path("auth/change-email/verification/", VerificationsOTPForChangeEmailView.as_view()),

    # path('', include(router.urls)),
    # path('restaurant/', RestaurantViewset.as_view({'get': 'list','post':'create'}), name='restaurant-detail'),
]
