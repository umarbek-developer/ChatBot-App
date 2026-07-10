from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        # Register signal handlers (auto-provision Profile, etc.).
        from apps.accounts import signals  # noqa: F401
