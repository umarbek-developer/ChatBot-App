from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserOTPVerifications, UserOTPIDVerifications,\
    ChangePasswordLogs, ChangeEmailLogs

class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'full_name', 'is_active')
    list_editable = ("is_active", )

    search_fields = ('email', 'first_name', 'last_name', 'telegram_id')

    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': (
        'first_name', 'last_name', 'telegram_id')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    ordering = ('date_joined',)

    readonly_fields = ('date_joined', 'last_login')


admin.site.register(User, UserAdmin)

@admin.register(UserOTPVerifications)
class UserOTPVerificationsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "code",
        "attapts",
        "resend_attapts",
        "for_forget_password",
        "for_forget_password_verified",
        "expired_at",
        "created_at",
    )

    list_filter = (
        "for_forget_password",
        "for_forget_password_verified",
        "created_at",
        "expired_at",
    )

    search_fields = (
        "user__username",
        "user__email",
        "code",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = ("-created_at",)


@admin.register(UserOTPIDVerifications)
class UserOTPIDVerificationsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "code",
        "attapts",
        "expired_at",
        "created_at",
    )

    list_filter = (
        "created_at",
        "expired_at",
    )

    search_fields = (
        "user__username",
        "user__email",
        "code",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = ("-created_at",)


@admin.register(ChangePasswordLogs)
class ChangePasswordLogsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "attapts",
        "is_changed",
        "expired_at",
        "error_expired_at",
        "created_at",
    )

    list_filter = (
        "is_changed",
        "created_at",
        "expired_at",
    )

    search_fields = (
        "user__username",
        "user__email",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = ("-created_at",)

    # passwordlarni admin panelda edit qilib yubormaslik uchun
    exclude = (
        "old_password",
        "new_password",
    )


@admin.register(ChangeEmailLogs)
class ChangeEmailLogsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "old_email",
        "new_email",
        "code",
        "attapts",
        "resend_attapts",
        "is_changed",
        "expired_at",
        "created_at",
    )

    list_filter = (
        "is_changed",
        "created_at",
        "expired_at",
    )

    search_fields = (
        "user__username",
        "user__email",
        "old_email",
        "new_email",
        "code",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = ("-created_at",)
