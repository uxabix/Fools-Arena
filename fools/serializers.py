"""Request-body serializers for fools REST endpoints.

These are intentionally lightweight (no ``ModelSerializer``) because responses
are built from :func:`fools.services.serialize_lobby` /
:func:`fools.services.serialize_game`.
"""

from rest_framework import serializers


class LobbyCreateSerializer(serializers.Serializer):
    """Validate payload for :class:`fools.api_views.LobbyListCreateAPI` POST."""

    name = serializers.CharField(
        max_length=100,
        error_messages={
            "required": "Enter a lobby name.",
            "blank": "Enter a lobby name.",
            "max_length": "Use 100 characters or fewer.",
        },
    )
    is_private = serializers.BooleanField(default=False)
    password = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        write_only=True,
        error_messages={"max_length": "Use 128 characters or fewer."},
    )
    max_players = serializers.IntegerField(
        min_value=2,
        max_value=8,
        default=4,
        error_messages={
            "invalid": "Enter a whole number of players.",
            "min_value": "Use at least 2 players.",
            "max_value": "Use 8 players or fewer.",
        },
    )
    card_count = serializers.ChoiceField(
        choices=[24, 36, 52],
        default=36,
        error_messages={
            "invalid_choice": "Choose a deck of 24, 36, or 52 cards.",
        },
    )
    is_transferable = serializers.BooleanField(default=False)
    neighbor_throw_only = serializers.BooleanField(default=False)
    fill_with_bots = serializers.BooleanField(default=False)
    allow_jokers = serializers.BooleanField(default=False)
    turn_time_limit = serializers.IntegerField(
        required=False, allow_null=True, min_value=0
    )

    def validate(self, attrs):
        """Require a password only for a private lobby.

        A public lobby drops any password so it is not stored.

        Args:
            attrs: Incoming validated fields.

        Returns:
            The same dict, normalized.

        Raises:
            serializers.ValidationError: When a private lobby lacks a password.
        """
        if attrs.get("is_private") and not (attrs.get("password") or "").strip():
            raise serializers.ValidationError(
                {"password": "Enter a password for a private lobby."}
            )
        if not attrs.get("is_private"):
            attrs["password"] = ""
        return attrs


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
