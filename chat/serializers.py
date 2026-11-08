"""Serializers for REST APIs in the chat application."""

from rest_framework import serializers

from .models import Chat, Message


class MessageSerializer(serializers.ModelSerializer):
    """Serialize stored chat messages for read APIs."""

    sender = serializers.CharField(source="sender.username", read_only=True)

    class Meta:
        model = Message
        fields = ["id", "sender", "content", "sent_at"]


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


class DirectChatCreateSerializer(serializers.Serializer):
    """Request body for opening or retrieving a 1-on-1 chat."""

    other_user_id = serializers.UUIDField()
