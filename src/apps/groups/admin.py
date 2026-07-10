from django.contrib import admin

from apps.groups.models import Group, GroupMember, Invite, JoinRequest, Role


class GroupMemberInline(admin.TabularInline):
    model = GroupMember
    extra = 0
    raw_id_fields = ("user", "custom_role")
    fields = ("user", "role", "status", "muted_until", "joined_at")
    readonly_fields = ("joined_at",)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "visibility", "owner", "member_count", "is_deleted", "created_at")
    list_filter = ("visibility", "is_deleted", "created_at")
    search_fields = ("slug", "name", "owner__email")
    raw_id_fields = ("owner", "created_by", "updated_by")
    readonly_fields = ("id", "member_count", "created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [GroupMemberInline]
    date_hierarchy = "created_at"


@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "group", "role", "status", "is_muted", "joined_at")
    list_filter = ("role", "status")
    search_fields = ("user__email", "group__slug")
    raw_id_fields = ("user", "group", "custom_role")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "group", "priority")
    search_fields = ("name", "group__slug")
    raw_id_fields = ("group",)


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ("code", "group", "created_by", "uses", "max_uses", "is_revoked", "expires_at")
    list_filter = ("is_revoked",)
    search_fields = ("code", "group__slug")
    raw_id_fields = ("group", "created_by")
    readonly_fields = ("code",)


@admin.register(JoinRequest)
class JoinRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "group", "status", "created_at", "decided_at")
    list_filter = ("status",)
    search_fields = ("user__email", "group__slug")
    raw_id_fields = ("user", "group", "decided_by")
