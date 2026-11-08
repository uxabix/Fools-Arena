"""Request-body serializers for game REST endpoints.

These are intentionally lightweight (no ``ModelSerializer``) because responses
are built from :func:`game.services.serialize_lobby` /
:func:`game.services.serialize_game`.
"""

from rest_framework import serializers


class LobbyCreateSerializer(serializers.Serializer):
    """Validate payload for :class:`game.api_views.LobbyListCreateAPI` POST."""

    name = serializers.CharField(max_length=100)
    is_private = serializers.BooleanField(default=False)
    password = serializers.CharField(
        max_length=128, required=False, allow_blank=True, write_only=True
    )

    def validate(self, attrs):
        """Require a non-empty password when ``is_private`` is true.

        Args:
            attrs: Incoming validated fields.

        Returns:
            The same dict, possibly normalized.

        Raises:
            serializers.ValidationError: When a private lobby lacks a password.
        """
        if attrs.get("is_private") and not (attrs.get("password") or "").strip():
            raise serializers.ValidationError(
                {"password": "Password is required for a private lobby."}
            )
        return attrs
    max_players = serializers.IntegerField(min_value=2, max_value=8, default=4)
    card_count = serializers.ChoiceField(choices=[24, 36, 52], default=36)
    is_transferable = serializers.BooleanField(default=False)
    neighbor_throw_only = serializers.BooleanField(default=False)
    allow_jokers = serializers.BooleanField(default=False)
    turn_time_limit = serializers.IntegerField(required=False, allow_null=True, min_value=0)


class LobbyJoinSerializer(serializers.Serializer):
    """Optional password when joining a private lobby."""
    password = serializers.CharField(
        max_length=128, required=False, allow_blank=True, write_only=True
    )


class ReadySerializer(serializers.Serializer):
    """Boolean ready flag for lobby members."""
    ready = serializers.BooleanField()


class AttackSerializer(serializers.Serializer):
    """List of card UUIDs played from the actor's hand."""
    card_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
    )


class DefendSerializer(serializers.Serializer):
    """Table row id plus defending card id."""
    table_card_id = serializers.UUIDField()
    card_id = serializers.UUIDField()


class LobbyMessageSerializer(serializers.Serializer):
    """Free-text lobby chat body."""
    content = serializers.CharField(max_length=4000)
