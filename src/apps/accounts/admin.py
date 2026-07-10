from django.contrib import admin

from apps.accounts.models import Device, Profile, Session


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "username", "display_name", "status", "is_verified", "last_seen_at")
    list_filter = ("status", "is_verified", "is_deleted")
    search_fields = ("user__email", "username", "display_name")
    raw_id_fields = ("user",)
    readonly_fields = ("id", "created_at", "updated_at", "last_seen_at")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "name", "is_active", "last_active_at")
    list_filter = ("platform", "is_active")
    search_fields = ("user__email", "device_id", "name")
    raw_id_fields = ("user",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("user", "device", "ip_address", "expires_at", "revoked_at", "last_used_at")
    list_filter = ("expires_at", "revoked_at")
    search_fields = ("user__email", "refresh_jti", "ip_address")
    raw_id_fields = ("user", "device")
    readonly_fields = ("id", "created_at", "updated_at", "refresh_jti")
