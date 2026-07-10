"""Serializers for call history."""
from __future__ import annotations

from rest_framework import serializers

from apps.chat.models import Call


class CallPartySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)


class CallSerializer(serializers.ModelSerializer):
    caller = CallPartySerializer(read_only=True)
    receiver = CallPartySerializer(read_only=True)
    duration_seconds = serializers.IntegerField(read_only=True)
    direction = serializers.SerializerMethodField()

    class Meta:
        model = Call
        fields = [
            "id", "caller", "receiver", "call_type", "status",
            "direction", "duration_seconds", "started_at", "ended_at", "created_at",
        ]

    def get_direction(self, obj: Call) -> str:
        me = self.context.get("user_id")
        return "outgoing" if str(obj.caller_id) == str(me) else "incoming"
