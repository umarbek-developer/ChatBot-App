"""Reusable managers and querysets for the platform.

The soft-delete machinery here is the single source of truth for how rows are
logically removed across the whole project. Concrete models inherit it through
``apps.common.models.SoftDeleteModel`` / ``BaseModel`` and therefore never issue
a physical ``DELETE`` unless ``hard=True`` is passed explicitly.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that understands the logical-deletion contract."""

    def alive(self) -> "SoftDeleteQuerySet":
        return self.filter(is_deleted=False)

    def dead(self) -> "SoftDeleteQuerySet":
        return self.filter(is_deleted=True)

    def delete(self):  # type: ignore[override]
        """Bulk soft-delete: never touches the physical row."""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        """Escape hatch for GDPR / purge jobs and tests."""
        return super().delete()

    def restore(self):
        return self.update(is_deleted=False, deleted_at=None)


class SoftDeleteManager(models.Manager):
    """Default manager that hides soft-deleted rows.

    Two managers are exposed on every soft-deletable model:

    * ``objects``      -> only live rows (``alive_only=True``)
    * ``all_objects``  -> every row, including tombstones
    """

    def __init__(self, *args, alive_only: bool = True, **kwargs) -> None:
        self.alive_only = alive_only
        super().__init__(*args, **kwargs)

    def get_queryset(self) -> SoftDeleteQuerySet:
        qs = SoftDeleteQuerySet(self.model, using=self._db)
        if self.alive_only:
            return qs.filter(is_deleted=False)
        return qs

    # convenience passthroughs -------------------------------------------------
    def alive(self) -> SoftDeleteQuerySet:
        return self.get_queryset().alive()

    def dead(self) -> SoftDeleteQuerySet:
        return SoftDeleteQuerySet(self.model, using=self._db).dead()

    def hard_delete(self):
        return SoftDeleteQuerySet(self.model, using=self._db).hard_delete()
