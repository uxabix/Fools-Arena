"""Serializers for REST APIs in the chat application."""

from rest_framework import serializers

from .models import Chat, Message


class MessageSerializer(serializers.ModelSerializer):
    """Serialize stored chat messages for read APIs."""

    sender = serializers.CharField(source="sender.username", read_only=True)
    sender_id = serializers.UUIDField(read_only=True)
    kind = serializers.CharField(read_only=True)

    class Meta:
        model = Message
        fields = ["id", "sender", "sender_id", "content", "sent_at", "kind"]


class MessageCreateSerializer(serializers.ModelSerializer):
    """Validate inbound message bodies for create endpoints."""

    class Meta:
        model = Message
        fields = ["content"]

    def validate_content(self, value):
        """Strip whitespace and enforce non-empty, bounded length."""
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Message cannot be empty.")
        if len(value) > 10000:
            raise serializers.ValidationError("Message exceeds maximum length.")
        return value


class ChatSerializer(serializers.ModelSerializer):
    """Serialize chat metadata for listing and direct-chat creation responses."""

    peer_username = serializers.SerializerMethodField()
    peer_id = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    last_activity = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = [
            "id",
            "name",
            "is_group",
            "is_lobby",
            "is_global",
            "lobby",
            "dm_pair_key",
            "peer_username",
            "peer_id",
            "last_message",
            "last_activity",
            "unread_count",
        ]
        read_only_fields = ["dm_pair_key"]

    def get_peer_username(self, obj):
        """Return the other user's username in a DM for the current viewer."""
        request = self.context.get("request")
        if not request or not getattr(request.user, "is_authenticated", False):
            return None
        if not obj.is_direct_message():
            return None
        other = obj.get_other_participant(request.user)
        return other.username if other else None

    def get_peer_id(self, obj):
        """Return the other user's id in a DM for the current viewer."""
        request = self.context.get("request")
        if not request or not getattr(request.user, "is_authenticated", False):
            return None
        if not obj.is_direct_message():
            return None
        other = obj.get_other_participant(request.user)
        return str(other.pk) if other else None

    def get_last_message(self, obj):
        """Return a short preview of the newest line, when the queryset annotated it."""
        from .services import preview_text

        content = getattr(obj, "last_content", None)
        if not content:
            return None
        sent = getattr(obj, "last_sent_at", None)
        return {
            "sender": getattr(obj, "last_sender_name", "") or "",
            "content": preview_text(content, limit=160),
            "sent_at": sent.isoformat() if sent else None,
            "kind": getattr(obj, "last_kind", None) or "user",
        }

    def get_last_activity(self, obj):
        """Return the newest message time, or None for an empty chat."""
        sent = getattr(obj, "last_sent_at", None)
        return sent.isoformat() if sent else None

    def get_unread_count(self, obj):
        """Return annotated unread messages, or zero when the annotation is absent."""
        return int(getattr(obj, "unread_count", 0) or 0)


class DirectChatCreateSerializer(serializers.Serializer):
    """Request body for opening or retrieving a 1-on-1 chat."""

    other_user_id = serializers.UUIDField()
