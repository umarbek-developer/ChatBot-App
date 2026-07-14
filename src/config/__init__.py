# Make the Celery app available as soon as Django starts so that any
# @shared_task in the project binds to it and autodiscover_tasks() runs.
from .celery import app as celery_app

__all__ = ("celery_app",)
