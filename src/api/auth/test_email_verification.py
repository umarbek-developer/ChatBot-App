"""End-to-end tests for the registration + email verification pipeline.

Uses the in-memory email backend (``mail.outbox``) so the full send path runs
without touching real SMTP, and asserts the critical guarantee: a user is never
active until the correct, unexpired code is entered.
"""
from __future__ import annotations

import pytest
from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

REGISTER = "/api/v1/auth/register/"
VERIFY = "/api/v1/auth/register/otp/verify/"
RESEND = "/api/v1/auth/resend/otp/"

VALID = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "newuser@example.com",
    "password": "Str0ng!pw",
    "password2": "Str0ng!pw",
    "otp_type": "otp",
}


@pytest.fixture(autouse=True)
def _email_env(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.EMAIL_HOST_USER = "sender@example.com"
    settings.EMAIL_HOST_PASSWORD = "app-password"
    settings.DEFAULT_FROM_EMAIL = "Pulse <sender@example.com>"
    settings.EMAIL_USE_CELERY = False
    cache.clear()  # reset throttles between tests
    mail.outbox.clear()
    yield


@pytest.fixture
def client():
    return APIClient()


def _code_for(email):
    from apps.users.models import UserOTPVerifications
    return UserOTPVerifications.objects.filter(user__email=email).latest("created_at").code


@pytest.mark.django_db
def test_registration_creates_inactive_user_and_sends_email(client):
    from apps.users.models import User, UserOTPVerifications

    resp = client.post(REGISTER, VALID, format="json")
    assert resp.status_code == 201, resp.content

    user = User.objects.get(email=VALID["email"])
    assert user.is_active is False, "user MUST NOT be active before verification"

    otp = UserOTPVerifications.objects.get(user=user)
    assert len(otp.code) == 6 and otp.code.isdigit()
    assert otp.expired_at > timezone.now()

    assert len(mail.outbox) == 1
    assert VALID["email"] in mail.outbox[0].to
    assert otp.code in mail.outbox[0].body                   # plain-text part
    assert otp.code in mail.outbox[0].alternatives[0][0]     # html part


@pytest.mark.django_db
def test_password_mismatch_rejected(client):
    resp = client.post(REGISTER, {**VALID, "password2": "different"}, format="json")
    assert resp.status_code == 400
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_duplicate_active_email_rejected_not_deleted(client):
    from apps.users.models import User

    u = User.objects.create_user(email=VALID["email"], password="Str0ng!pw", first_name="Ada")
    u.is_active = True
    u.save()
    resp = client.post(REGISTER, VALID, format="json")
    assert resp.status_code == 400
    assert User.objects.filter(email=VALID["email"]).exists()  # NOT deleted


@pytest.mark.django_db
def test_wrong_code_keeps_user_inactive(client):
    from apps.users.models import User

    client.post(REGISTER, VALID, format="json")
    resp = client.post(VERIFY, {"email": VALID["email"], "code": "000000"}, format="json")
    assert resp.status_code == 400
    assert User.objects.get(email=VALID["email"]).is_active is False


@pytest.mark.django_db
def test_correct_code_activates_user(client):
    from apps.users.models import User

    client.post(REGISTER, VALID, format="json")
    code = _code_for(VALID["email"])
    resp = client.post(VERIFY, {"email": VALID["email"], "code": code}, format="json")
    assert resp.status_code == 200, resp.content
    assert User.objects.get(email=VALID["email"]).is_active is True


@pytest.mark.django_db
def test_expired_code_is_rejected(client):
    from apps.users.models import User, UserOTPVerifications

    client.post(REGISTER, VALID, format="json")
    code = _code_for(VALID["email"])
    UserOTPVerifications.objects.filter(user__email=VALID["email"]).update(
        expired_at=timezone.now() - timezone.timedelta(minutes=1)
    )
    resp = client.post(VERIFY, {"email": VALID["email"], "code": code}, format="json")
    assert resp.status_code == 400
    assert User.objects.get(email=VALID["email"]).is_active is False


@pytest.mark.django_db
def test_resend_sends_a_new_email(client):
    client.post(REGISTER, VALID, format="json")
    mail.outbox.clear()
    resp = client.post(RESEND, {"email": VALID["email"]}, format="json")
    assert resp.status_code in (200, 201)
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_email_send_failure_rolls_back_registration(client, monkeypatch):
    """If delivery fails, registration must FAIL (no fake success) and leave no user."""
    from apps.users.models import User
    import api.auth.views.register_views as rv

    def _boom(*a, **k):
        raise RuntimeError("SMTP down (simulated)")

    monkeypatch.setattr(rv, "deliver_otp", _boom)
    resp = client.post(REGISTER, VALID, format="json")
    assert resp.status_code == 502
    assert resp.json()["error"] == "Email delivery failed"
    assert not User.objects.filter(email=VALID["email"]).exists()  # rolled back
