from django.apps import AppConfig


class GroupsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.groups"
    verbose_name = "Groups"

    def ready(self) -> None:
        from apps.groups import signals  # noqa: F401
