from django.contrib import admin

from apps.messaging.models import (
    Message,
    MessageEditHistory,
    PlayedReceipt,
    Reaction,
    ReadReceipt,
    VoiceMessage,
)


@admin.register(VoiceMessage)
class VoiceMessageAdmin(admin.ModelAdmin):
    list_display = ("message", "duration_ms", "file_size", "mime", "created_at")
    search_fields = ("message__room", "message__sender_name")
    raw_id_fields = ("message",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(PlayedReceipt)
class PlayedReceiptAdmin(admin.ModelAdmin):
    list_display = ("message", "player_name", "played_at")
    search_fields = ("player_name", "player_key")
    raw_id_fields = ("message",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("room", "sender_name", "kind", "short_text", "is_edited", "is_deleted", "created_at")
    list_filter = ("kind", "is_edited", "is_deleted", "created_at")
    search_fields = ("room", "sender_name", "text", "sender_key")
    raw_id_fields = ("sender", "reply_to")
    readonly_fields = ("id", "created_at", "updated_at", "edited_at")
    date_hierarchy = "created_at"

    @admin.display(description="text")
    def short_text(self, obj: Message) -> str:
        return (obj.text[:60] + "…") if len(obj.text) > 60 else obj.text


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ("emoji", "actor_name", "message", "created_at")
    search_fields = ("actor_name", "actor_key")
    raw_id_fields = ("message",)


@admin.register(ReadReceipt)
class ReadReceiptAdmin(admin.ModelAdmin):
    list_display = ("message", "reader_name", "read_at")
    search_fields = ("reader_name", "reader_key")
    raw_id_fields = ("message",)


@admin.register(MessageEditHistory)
class MessageEditHistoryAdmin(admin.ModelAdmin):
    list_display = ("message", "created_at")
    raw_id_fields = ("message",)
