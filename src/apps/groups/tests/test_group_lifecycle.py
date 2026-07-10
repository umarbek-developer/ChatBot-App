"""Group lifecycle: uniqueness, normalization, soft-delete, permissions.

Covers the redesign that stopped duplicate/auto-created groups and added a
proper owner-only soft delete.
"""
from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from apps.common.exceptions import ConflictError, PermissionDeniedError, ValidationErrorLike
from apps.groups.models import Group, GroupMember
from apps.groups.services import GroupService


@pytest.fixture
def users(db):
    from apps.users.models import User
    owner = User.objects.create_user(email="own@test.dev", password="x", first_name="Own")
    other = User.objects.create_user(email="oth@test.dev", password="x", first_name="Oth")
    return owner, other


@pytest.fixture
def service():
    return GroupService()


@pytest.mark.django_db
def test_create_normalizes_name_and_slug(users, service):
    owner, _ = users
    g = service.create(owner=owner, name="  Dev   Team  ")
    assert g.name == "Dev Team"      # trimmed + collapsed spaces
    assert g.slug == "dev-team"
    assert GroupMember.objects.filter(group=g, user=owner, role="owner").exists()


@pytest.mark.django_db
def test_duplicate_name_rejected(users, service):
    owner, _ = users
    service.create(owner=owner, name="Developers")
    with pytest.raises(ConflictError) as exc:
        service.create(owner=owner, name="Developers")
    assert exc.value.details["slug"] == "developers"
    assert Group.objects.filter(name__iexact="developers").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("variant", ["developers", "DEVELOPERS", "Developers", "  developers "])
def test_case_and_space_insensitive_duplicates_rejected(users, service, variant):
    owner, _ = users
    service.create(owner=owner, name="Developers")
    with pytest.raises(ConflictError):
        service.create(owner=owner, name=variant)


@pytest.mark.django_db
def test_reserved_name_rejected(users, service):
    owner, _ = users
    with pytest.raises(ValidationErrorLike):
        service.create(owner=owner, name="admin")


@pytest.mark.django_db
def test_too_short_rejected(users, service):
    owner, _ = users
    with pytest.raises(ValidationErrorLike):
        service.create(owner=owner, name="ab")


@pytest.mark.django_db
def test_db_constraint_blocks_duplicate_active_slug(users, service):
    """Even bypassing the service, the DB refuses two active groups with one slug."""
    owner, _ = users
    service.create(owner=owner, name="Developers")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Group.objects.create(name="Developers 2", slug="developers", owner=owner)


@pytest.mark.django_db
def test_non_owner_cannot_delete(users, service):
    owner, other = users
    g = service.create(owner=owner, name="Developers")
    GroupMember.objects.create(group=g, user=other, role="admin", status="active")
    with pytest.raises(PermissionDeniedError):
        service.delete(actor=other, group=g)
    assert Group.objects.filter(slug="developers").exists()


@pytest.mark.django_db
def test_owner_soft_delete_records_deleted_by_and_frees_name(users, service):
    owner, _ = users
    g = service.create(owner=owner, name="Developers")
    service.delete(actor=owner, group=g)

    assert not Group.objects.filter(slug="developers").exists()   # hidden from live manager
    tomb = Group.all_objects.get(pk=g.pk)
    assert tomb.is_deleted and tomb.deleted_at is not None
    assert tomb.deleted_by_id == owner.pk                          # soft delete, recoverable

    # name is now reusable
    g2 = service.create(owner=owner, name="Developers")
    assert g2.slug == "developers" and g2.pk != g.pk


@pytest.mark.django_db
def test_no_group_created_without_explicit_call(users):
    """Sanity: merely having users/logging in creates zero groups."""
    assert Group.objects.count() == 0
