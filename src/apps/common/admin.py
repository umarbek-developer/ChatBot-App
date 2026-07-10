from django.contrib import admin

from apps.common.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "target_type", "target_id", "ip_address", "created_at")
    list_filter = ("action", "target_type", "created_at")
    search_fields = ("target_id", "actor__email", "ip_address")
    readonly_fields = (
        "id",
        "actor",
        "action",
        "target_type",
        "target_id",
        "metadata",
        "ip_address",
        "user_agent",
        "created_at",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:  # audit trail is append-only
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
