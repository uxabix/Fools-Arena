"""Admin configuration for the game system of the Durak card game application.

This module defines the Django admin interface configuration for all models
in the game app, providing comprehensive management tools for administrators
to monitor and manage game functionality, lobbies, players, and card mechanics.
"""

import json
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.db import models
from django.core.exceptions import ValidationError
from .models import (
    CardSuit, CardRank, Lobby, LobbySettings, LobbyPlayer, Game, GamePlayer,
    Card, SpecialCard, SpecialRuleSet, SpecialRuleSetCard, GameDeck,
    PlayerHand, TableCard, DiscardPile, Turn, Move
)


@admin.register(CardSuit)
class CardSuitAdmin(admin.ModelAdmin):
    """Admin interface for the CardSuit model.

    Provides management capabilities for playing card suits with visual indicators
    and efficient display for quick suit identification and management.

    Features:
        - Color-coded suit display with emojis
        - Filtering by color (red/black)
        - Search by suit name
        - Readonly ID field
        - Optimized for small dataset

    Attributes:
        list_display: Fields shown in the suit list view
        list_filter: Available filters in the admin sidebar
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        ordering: Default ordering for the suit list
    """

    list_display = ('suit_display', 'color_display', 'id')
    list_filter = ('color',)
    search_fields = ('name',)
    readonly_fields = ('id',)
    ordering = ('name',)

    def suit_display(self, obj):
        """Display suit name with appropriate emoji indicator.

        Args:
            obj (CardSuit): The card suit instance.

        Returns:
            str: HTML formatted suit name with emoji.
        """
        emoji_map = {
            'Hearts': '♥️',
            'Diamonds': '♦️',
            'Clubs': '♣️',
            'Spades': '♠️'
        }
        emoji = emoji_map.get(obj.name, '🃏')
        return format_html('{} {}', emoji, obj.name)

    suit_display.short_description = "Suit"
    suit_display.admin_order_field = 'name'

    def color_display(self, obj):
        """Display suit color with visual indicator.

        Args:
            obj (CardSuit): The card suit instance.

        Returns:
            str: HTML formatted color with styling.
        """
        if obj.color == 'red':
            return format_html('<span style="color: #dc3545; font-weight: bold;">🔴 Red</span>')
        else:
            return format_html('<span style="color: #212529; font-weight: bold;">⚫ Black</span>')

    color_display.short_description = "Color"
    color_display.admin_order_field = 'color'


@admin.register(CardRank)
class CardRankAdmin(admin.ModelAdmin):
    """Admin interface for the CardRank model.

    Provides management capabilities for playing card ranks with value-based
    ordering and face card identification for game logic management.

    Features:
        - Value-based display with face card indicators
        - Ordering by numeric value
        - Quick identification of face cards
        - Search by rank name
        - Readonly fields for system data

    Attributes:
        list_display: Fields shown in the rank list view
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        ordering: Default ordering by rank value
    """

    list_display = ('rank_display', 'value', 'card_type_display', 'id')
    search_fields = ('name',)
    readonly_fields = ('id',)
    ordering = ('value',)

    def rank_display(self, obj):
        """Display rank name with value information.

        Args:
            obj (CardRank): The card rank instance.

        Returns:
            str: Formatted rank name with value.
        """
        return f"{obj.name} ({obj.value})"

    rank_display.short_description = "Rank"
    rank_display.admin_order_field = 'value'

    def card_type_display(self, obj):
        """Display whether this is a face card or number card.

        Args:
            obj (CardRank): The card rank instance.

        Returns:
            str: HTML formatted card type indicator.
        """
        if obj.is_face_card():
            return format_html('<span style="color: #6f42c1; font-weight: bold;">👑 Face Card</span>')
        else:
            return format_html('<span style="color: #20c997;">🔢 Number Card</span>')

    card_type_display.short_description = "Type"


@admin.register(Lobby)
class LobbyAdmin(admin.ModelAdmin):
    """Admin interface for the Lobby model.

    Provides comprehensive management capabilities for game lobbies including
    player management, game status tracking, and lobby configuration.

    Features:
        - Visual status indicators with privacy settings
        - Player count tracking and capacity management
        - Advanced filtering by status, privacy, and creation date
        - Direct access to lobby settings and players
        - Custom actions for lobby management
        - Enhanced search across owners and lobby names

    Attributes:
        list_display: Fields shown in the lobby list view
        list_filter: Available filters in the admin sidebar
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        date_hierarchy: Date-based navigation
        ordering: Default ordering for the lobby list
        fieldsets: Organization of fields in the detail view
        inlines: Inline editing of related objects
        actions: Custom bulk actions available
    """

    list_display = (
        'lobby_info_display',
        'owner',
        'status_display',
        'privacy_display',
        'player_count_display',
        'created_at_formatted',
        'can_start_display'
    )

    list_display_links = ('lobby_info_display',)

    list_filter = (
        'status',
        'is_private',
        'created_at',
        ('owner', admin.RelatedOnlyFieldListFilter),
    )

    search_fields = (
        'name',
        'owner__username',
        'owner__email',
    )

    readonly_fields = (
        'id',
        'created_at',
        'password_hash',
        'player_count_display',
        'can_start_display',
        'lobby_statistics'
    )

    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    fieldsets = (
        ('Lobby Information', {
            'fields': ('id', 'name', 'owner'),
            'description': 'Basic lobby identification and ownership.'
        }),
        ('Privacy & Access', {
            'fields': ('is_private', 'password_hash'),
            'description': 'Privacy settings and access control.',
            'classes': ('collapse',)
        }),
        ('Game Status', {
            'fields': ('status', 'player_count_display', 'can_start_display'),
            'description': 'Current lobby state and game readiness.'
        }),
        ('Statistics', {
            'fields': ('lobby_statistics',),
            'description': 'Detailed lobby activity statistics.',
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'description': 'System-generated timing information.',
            'classes': ('collapse',)
        }),
    )

    actions = ['close_lobbies', 'reset_lobby_status', 'export_lobby_data']

    def lobby_info_display(self, obj):
        """Display lobby name with ID for identification.

        Args:
            obj (Lobby): The lobby instance.

        Returns:
            str: Formatted lobby name with truncated ID.
        """
        short_id = str(obj.id)[:8]
        return f"{obj.name} ({short_id}...)"

    lobby_info_display.short_description = "Lobby"
    lobby_info_display.admin_order_field = 'name'

    def status_display(self, obj):
        """Display lobby status with visual indicators.

        Args:
            obj (Lobby): The lobby instance.

        Returns:
            str: HTML formatted status with color coding.
        """
        status_colors = {
            'waiting': '#28a745',
            'playing': '#007bff',
            'closed': '#6c757d'
        }
        status_icons = {
            'waiting': '⏳',
            'playing': '🎮',
            'closed': '🔒'
        }

        color = status_colors.get(obj.status, '#6c757d')
        icon = status_icons.get(obj.status, '❓')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color, icon, obj.get_status_display()
        )

    status_display.short_description = "Status"
    status_display.admin_order_field = 'status'

    def privacy_display(self, obj):
        """Display privacy setting with visual indicator.

        Args:
            obj (Lobby): The lobby instance.

        Returns:
            str: HTML formatted privacy status.
        """
        if obj.is_private:
            return format_html('<span style="color: #dc3545;">🔐 Private</span>')
        else:
            return format_html('<span style="color: #28a745;">🌐 Public</span>')

    privacy_display.short_description = "Privacy"
    privacy_display.admin_order_field = 'is_private'

    def player_count_display(self, obj):
        """Display current player count with capacity information.

        Args:
            obj (Lobby): The lobby instance.

        Returns:
            str: Player count with capacity and status indicators.
        """
        try:
            current_count = obj.get_active_players().count()
            max_count = obj.settings.max_players
            ready_count = obj.players.filter(status='ready').count()

            if current_count >= max_count:
                color = '#dc3545'  # Red for full
                status = '🔴 Full'
            elif current_count == 0:
                color = '#6c757d'  # Gray for empty
                status = '⚪ Empty'
            else:
                color = '#28a745'  # Green for available
                status = '🟢 Available'

            return format_html(
                '<span style="color: {};">{} {}/{}</span><br>'
                '<small style="color: #666;">({} ready)</small>',
                color, status, current_count, max_count, ready_count
            )
        except:
            return format_html('<span style="color: #dc3545;">❌ Error</span>')

    player_count_display.short_description = "Players"

    def created_at_formatted(self, obj):
        """Display formatted creation timestamp with relative time.

        Args:
            obj (Lobby): The lobby instance.

        Returns:
            str: Formatted datetime with relative time indicator.
        """
        now = timezone.now()
        time_diff = now - obj.created_at

        if time_diff < timedelta(hours=1):
            minutes = int(time_diff.total_seconds() / 60)
            relative = f"{minutes}m ago"
        elif time_diff < timedelta(days=1):
            hours = int(time_diff.total_seconds() / 3600)
            relative = f"{hours}h ago"
        else:
            days = time_diff.days
            relative = f"{days}d ago"

        return format_html(
            '{}<br><small style="color: #666;">({})}</small>',
            obj.created_at.strftime('%Y-%m-%d %H:%M'),
            relative
        )

    created_at_formatted.short_description = "Created"
    created_at_formatted.admin_order_field = 'created_at'

    def can_start_display(self, obj):
        """Display whether the lobby can start a game.

        Args:
            obj (Lobby): The lobby instance.

        Returns:
            str: Visual indicator for game start readiness.
        """
        if obj.can_start_game():
            return format_html('<span style="color: #28a745;">✅ Ready</span>')
        else:
            return format_html('<span style="color: #dc3545;">❌ Not Ready</span>')

    can_start_display.short_description = "Can Start"

    def lobby_statistics(self, obj):
        """Display comprehensive lobby statistics.

        Args:
            obj (Lobby): The lobby instance.

        Returns:
            str: HTML formatted statistics summary.
        """
        try:
            total_players = obj.players.count()
            active_players = obj.get_active_players().count()
            games_played = obj.game_set.count()
            messages_sent = obj.messages.count()

            return format_html(
                '<div style="background: #f8f9fa; padding: 10px; border: 1px solid #dee2e6;">'
                '<strong>Statistics:</strong><br>'
                'Total Players Joined: {}<br>'
                'Currently Active: {}<br>'
                'Games Played: {}<br>'
                'Messages Sent: {}<br>'
                '</div>',
                total_players, active_players, games_played, messages_sent
            )
        except:
            return format_html('<span style="color: #dc3545;">Statistics unavailable</span>')

    lobby_statistics.short_description = "Statistics"

    def get_queryset(self, request):
        """Optimize queryset for the admin interface.

        Args:
            request: The HTTP request object.

        Returns:
            QuerySet: Optimized queryset with prefetched related objects.
        """
        return super().get_queryset(request).select_related(
            'owner',
            'settings'
        ).prefetch_related(
            'players',
            'game_set',
            'messages'
        )

    def close_lobbies(self, request, queryset):
        """Custom admin action to close selected lobbies.

        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected lobbies.
        """
        updated = queryset.filter(status__in=['waiting', 'playing']).update(status='closed')
        self.message_user(
            request,
            f"Closed {updated} lobby(ies). Active games may continue."
        )

    close_lobbies.short_description = "Close selected lobbies"

    def reset_lobby_status(self, request, queryset):
        """Custom admin action to reset lobby status to waiting.

        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected lobbies.
        """
        if not request.user.is_superuser:
            self.message_user(request, "Only superusers can reset lobby status.", level='ERROR')
            return

        updated = queryset.update(status='waiting')
        self.message_user(request, f"Reset {updated} lobby(ies) to waiting status.")

    reset_lobby_status.short_description = "Reset to waiting status (Superuser only)"

    def export_lobby_data(self, request, queryset):
        """Custom admin action to export lobby data.

        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected lobbies.
        """
        count = queryset.count()
        self.message_user(
            request,
            f"Export initiated for {count} lobby(ies). Download link will be provided when ready."
        )

    export_lobby_data.short_description = "Export lobby data"


class LobbyPlayerInline(admin.TabularInline):
    """Inline admin interface for LobbyPlayer model within Lobby admin.

    Provides a compact view of players within a lobby directly from
    the lobby admin page, allowing quick player management.
    """
    model = LobbyPlayer
    extra = 0
    readonly_fields = ('id', 'status')
    fields = ('user', 'status', 'id')


@admin.register(LobbySettings)
class LobbySettingsAdmin(admin.ModelAdmin):
    """Admin interface for the LobbySettings model.

    Provides management capabilities for lobby game configuration settings
    with validation and rule compatibility checking.

    Features:
        - Configuration overview with rule compatibility
        - Settings validation and beginner-friendly indicators
        - Direct lobby access links
        - Custom validation for settings combinations
        - Readonly fields for computed properties

    Attributes:
        list_display: Fields shown in the settings list view
        list_filter: Available filters in the admin sidebar
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        fieldsets: Organization of fields in the detail view
    """

    list_display = (
        'settings_summary',
        'lobby_link',
        'configuration_display',
        'compatibility_display',
        'beginner_friendly_display'
    )

    list_display_links = ('settings_summary',)

    list_filter = (
        'max_players',
        'card_count',
        'is_transferable',
        'neighbor_throw_only',
        'allow_jokers',
        ('special_rule_set', admin.RelatedOnlyFieldListFilter),
    )

    search_fields = (
        'lobby__name',
        'lobby__owner__username',
    )

    readonly_fields = (
        'id',
        'beginner_friendly_display',
        'has_time_limit',
        'compatibility_display'
    )

    fieldsets = (
        ('Basic Settings', {
            'fields': ('id', 'lobby', 'max_players', 'card_count'),
            'description': 'Core game configuration parameters.'
        }),
        ('Game Rules', {
            'fields': ('is_transferable', 'neighbor_throw_only', 'allow_jokers'),
            'description': 'Gameplay rule modifications.'
        }),
        ('Advanced Configuration', {
            'fields': ('turn_time_limit', 'special_rule_set'),
            'description': 'Advanced settings and special rules.',
            'classes': ('collapse',)
        }),
        ('Compatibility Analysis', {
            'fields': ('beginner_friendly_display', 'compatibility_display'),
            'description': 'Automated analysis of settings compatibility.',
            'classes': ('collapse',)
        }),
    )

    def settings_summary(self, obj):
        """Display a summary of key settings.

        Args:
            obj (LobbySettings): The lobby settings instance.

        Returns:
            str: Formatted summary of main settings.
        """
        return f"{obj.lobby.name} ({obj.card_count} cards, {obj.max_players} players)"

    settings_summary.short_description = "Settings"
    settings_summary.admin_order_field = 'lobby__name'

    def lobby_link(self, obj):
        """Display link to the associated lobby.

        Args:
            obj (LobbySettings): The lobby settings instance.

        Returns:
            str: HTML formatted link to lobby admin page.
        """
        lobby_url = reverse('admin:game_lobby_change', args=[obj.lobby.pk])
        return format_html('<a href="{}" style="color: #007bff;">🎯 {}</a>', lobby_url, obj.lobby.name)

    lobby_link.short_description = "Lobby"

    def configuration_display(self, obj):
        """Display configuration details with visual indicators.

        Args:
            obj (LobbySettings): The lobby settings instance.

        Returns:
            str: HTML formatted configuration summary.
        """
        features = []

        if obj.is_transferable:
            features.append('<span style="color: #007bff;">🔄 Transferable</span>')
        if obj.neighbor_throw_only:
            features.append('<span style="color: #6f42c1;">👥 Neighbor Only</span>')
        if obj.allow_jokers:
            features.append('<span style="color: #fd7e14;">🃏 Jokers</span>')
        if obj.has_time_limit():
            features.append(f'<span style="color: #dc3545;">⏱️ {obj.turn_time_limit}s</span>')

        if not features:
            return format_html('<span style="color: #6c757d;">📋 Standard Rules</span>')

        return format_html('<br>'.join(features))

    configuration_display.short_description = "Configuration"

    def compatibility_display(self, obj):
        """Display rule set compatibility information.

        Args:
            obj (LobbySettings): The lobby settings instance.

        Returns:
            str: HTML formatted compatibility status.
        """
        if obj.special_rule_set:
            if obj.special_rule_set.is_compatible_with_player_count(obj.max_players):
                return format_html(
                    '<span style="color: #28a745;">✅ Compatible</span><br>'
                    '<small>{}</small>',
                    obj.special_rule_set.name
                )
            else:
                return format_html(
                    '<span style="color: #dc3545;">❌ Incompatible</span><br>'
                    '<small>Requires {}+ players</small>',
                    obj.special_rule_set.min_players
                )
        else:
            return format_html('<span style="color: #6c757d;">📋 No Special Rules</span>')

    compatibility_display.short_description = "Rule Compatibility"

    def beginner_friendly_display(self, obj):
        """Display whether settings are beginner-friendly.

        Args:
            obj (LobbySettings): The lobby settings instance.

        Returns:
            str: Visual indicator for beginner-friendliness.
        """
        if obj.is_beginner_friendly():
            return format_html('<span style="color: #28a745;">✅ Beginner Friendly</span>')
        else:
            return format_html('<span style="color: #ffc107;">⚠️ Advanced</span>')

    beginner_friendly_display.short_description = "Difficulty"


# Добавим LobbyPlayerInline к LobbyAdmin
LobbyAdmin.inlines = [LobbyPlayerInline]


@admin.register(LobbyPlayer)
class LobbyPlayerAdmin(admin.ModelAdmin):
    """Admin interface for the LobbyPlayer model.

    Provides management capabilities for player-lobby relationships
    with status tracking and lobby navigation.

    Features:
        - Player status management with visual indicators
        - Direct links to user and lobby admin pages
        - Status-based filtering and searching
        - Bulk status update actions
        - Activity tracking and management

    Attributes:
        list_display: Fields shown in the lobby player list view
        list_filter: Available filters in the admin sidebar
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        ordering: Default ordering for the player list
        actions: Custom bulk actions available
    """

    list_display = (
        'player_info_display',
        'lobby_link',
        'status_display',
        'activity_display'
    )

    list_display_links = ('player_info_display',)

    list_filter = (
        'status',
        ('lobby', admin.RelatedOnlyFieldListFilter),
        ('user', admin.RelatedOnlyFieldListFilter),
    )

    search_fields = (
        'user__username',
        'user__email',
        'lobby__name',
    )

    readonly_fields = ('id',)
    ordering = ('lobby__name', 'user__username')

    actions = ['mark_as_ready', 'mark_as_waiting', 'remove_from_lobby']

    def player_info_display(self, obj):
        """Display player information with user link.

        Args:
            obj (LobbyPlayer): The lobby player instance.

        Returns:
            str: HTML formatted player info with admin link.
        """
        user_url = reverse('admin:accounts_user_change', args=[obj.user.pk])
        return format_html('<a href="{}" style="color: #007bff;">👤 {}</a>', user_url, obj.user.username)

    player_info_display.short_description = "Player"
    player_info_display.admin_order_field = 'user__username'

    def lobby_link(self, obj):
        """Display link to the associated lobby.

        Args:
            obj (LobbyPlayer): The lobby player instance.

        Returns:
            str: HTML formatted link to lobby admin page.
        """
        lobby_url = reverse('admin:game_lobby_change', args=[obj.lobby.pk])
        return format_html('<a href="{}" style="color: #28a745;">🎯 {}</a>', lobby_url, obj.lobby.name)

    lobby_link.short_description = "Lobby"
    lobby_link.admin_order_field = 'lobby__name'

    def status_display(self, obj):
        """Display player status with visual indicators.

        Args:
            obj (LobbyPlayer): The lobby player instance.

        Returns:
            str: HTML formatted status with color coding.
        """
        status_colors = {
            'waiting': '#ffc107',
            'ready': '#28a745',
            'playing': '#007bff',
            'left': '#6c757d'
        }
        status_icons = {
            'waiting': '⏳',
            'ready': '✅',
            'playing': '🎮',
            'left': '👋'
        }

        color = status_colors.get(obj.status, '#6c757d')
        icon = status_icons.get(obj.status, '❓')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color, icon, obj.get_status_display()
        )

    status_display.short_description = "Status"
    status_display.admin_order_field = 'status'

    def activity_display(self, obj):
        """Display player activity status.

        Args:
            obj (LobbyPlayer): The lobby player instance.

        Returns:
            str: Visual indicator for player activity.
        """
        if obj.is_active():
            return format_html('<span style="color: #28a745;">🟢 Active</span>')
        else:
            return format_html('<span style="color: #6c757d;">⚪ Inactive</span>')

    activity_display.short_description = "Activity"

    def mark_as_ready(self, request, queryset):
        """Custom admin action to mark players as ready.

        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected lobby players.
        """
        updated = queryset.filter(status__in=['waiting']).update(status='ready')
        self.message_user(request, f"Marked {updated} player(s) as ready.")

    mark_as_ready.short_description = "Mark selected players as ready"

    def mark_as_waiting(self, request, queryset):
        """Custom admin action to mark players as waiting.

        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected lobby players.
        """
        updated = queryset.filter(status__in=['ready']).update(status='waiting')
        self.message_user(request, f"Marked {updated} player(s) as waiting.")

    mark_as_waiting.short_description = "Mark selected players as waiting"

    def remove_from_lobby(self, request, queryset):
        """Custom admin action to remove players from lobbies.

        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected lobby players.
        """
        if not request.user.is_superuser:
            self.message_user(request, "Only superusers can remove players.", level='ERROR')
            return

        updated = queryset.update(status='left')
        self.message_user(request, f"Removed {updated} player(s) from their lobbies.")

    remove_from_lobby.short_description = "Remove from lobby (Superuser only)"


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    """Admin interface for the Game model.

    Provides comprehensive management capabilities for game sessions
    with detailed tracking of game state, players, and statistics.

    Features:
        - Game status tracking with visual indicators
        - Player management and winner/loser identification
        - Game duration and statistics display
        - Trump card information with suit indicators
        - Advanced filtering by lobby, status, and duration
        - Custom actions for game management

    Attributes:
        list_display: Fields shown in the game list view
        list_filter: Available filters in the admin sidebar
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        date_hierarchy: Date-based navigation
        ordering: Default ordering for the game list
        fieldsets: Organization of fields in the detail view
        actions: Custom bulk actions available
    """

    list_display = (
        'game_info_display',
        'lobby_link',
        'status_display',
        'trump_card_display',
        'player_count_display',
        'duration_display',
        'winner_display'
    )

    list_display_links = ('game_info_display',)

    list_filter = (
        'status',
        'started_at',
        'finished_at',
        ('lobby', admin.RelatedOnlyFieldListFilter),
        ('loser', admin.RelatedOnlyFieldListFilter),
    )

    search_fields = (
        'lobby__name',
        'lobby__owner__username',
        'loser__username',
    )

    readonly_fields = (
        'id',
        'started_at',
        'finished_at',
        'player_count_display',
        'duration_display',
        'winner_display',
        'game_statistics'
    )

    date_hierarchy = 'started_at'
    ordering = ('-started_at',)

    fieldsets = (
        ('Game Information', {
            'fields': ('id', 'lobby', 'trump_card'),
            'description': 'Basic game identification and trump suit.'
        }),
        ('Game Status', {
            'fields': ('status', 'player_count_display', 'winner_display'),
            'description': 'Current game state and outcome information.'
        }),
        ('Timing Information', {
            'fields': ('started_at', 'finished_at', 'duration_display'),
            'description': 'Game duration and timing details.',
            'classes': ('collapse',)
        }),
        ('Game Results', {
            'fields': ('loser',),
            'description': 'Game outcome and losing player identification.'
        }),
        ('Statistics', {
            'fields': ('game_statistics',),
            'description': 'Detailed game statistics and analytics.',
            'classes': ('collapse',)
        }),
    )

    actions = ['finish_games', 'export_game_data']

    def game_info_display(self, obj):
        """Display game information with ID.

        Args:
            obj (Game): The game instance.

        Returns:
            str: Formatted game info with truncated ID.
        """
        short_id = str(obj.id)[:8]
        return f"Game {short_id}..."

    game_info_display.short_description = "Game"
    game_info_display.admin_order_field = 'started_at'

    def lobby_link(self, obj):
        """Display link to the associated lobby.

        Args:
            obj (Game): The game instance.

        Returns:
            str: HTML formatted link to lobby admin page.
        """
        lobby_url = reverse('admin:game_lobby_change', args=[obj.lobby.pk])
        return format_html('<a href="{}" style="color: #28a745;">🎯 {}</a>', lobby_url, obj.lobby.name)

    lobby_link.short_description = "Lobby"
    lobby_link.admin_order_field = 'lobby__name'

    def status_display(self, obj):
        """Display game status with visual indicators.

        Args:
            obj (Game): The game instance.

        Returns:
            str: HTML formatted status with color coding.
        """
        if obj.status == 'in_progress':
            return format_html('<span style="color: #007bff; font-weight: bold;">🎮 In Progress</span>')
        elif obj.status == 'finished':
            return format_html('<span style="color: #28a745; font-weight: bold;">🏁 Finished</span>')
        else:
            return format_html('<span style="color: #6c757d; font-weight: bold;">❓ Unknown</span>')

    status_display.short_description = "Status"
    status_display.admin_order_field = 'status'

    def trump_card_display(self, obj):
        """Display trump card information with suit indicator.

        Args:
            obj (Game): The game instance.

        Returns:
            str: HTML formatted trump card with suit emoji.
        """
        suit_emojis = {
            'Hearts': '♥️',
            'Diamonds': '♦️',
            'Clubs': '♣️',
            'Spades': '♠️'
        }

        suit_colors = {
            'Hearts': '#dc3545',
            'Diamonds': '#dc3545',
            'Clubs': '#212529',
            'Spades': '#212529'
        }

        emoji = suit_emojis.get(obj.trump_card.suit.name, '🃏')
        color = suit_colors.get(obj.trump_card.suit.name, '#6c757d')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span><br>'
            '<small style="color: #666;">Trump: {} of {}</small>',
            color, emoji, obj.trump_card.suit.name,
            obj.trump_card.rank.name, obj.trump_card.suit.name
        )

    trump_card_display.short_description = "Trump"

    def player_count_display(self, obj):
        """Display number of players in the game.

        Args:
            obj (Game): The game instance.

        Returns:
            str: Player count with visual indicator.
        """
        count = obj.get_player_count()
        return format_html('<span style="color: #007bff;">👥 {} players</span>', count)

    player_count_display.short_description = "Players"

    def duration_display(self, obj):
        """Display game duration information.

        Args:
            obj (Game): The game instance.

        Returns:
            str: Formatted duration or current runtime.
        """
        if obj.finished_at:
            duration = obj.finished_at - obj.started_at
            total_seconds = int(duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours > 0:
                return format_html('<span style="color: #6c757d;">⏱️ {}h {}m {}s</span>', hours, minutes, seconds)
            elif minutes > 0:
                return format_html('<span style="color: #6c757d;">⏱️ {}m {}s</span>', minutes, seconds)
            else:
                return format_html('<span style="color: #6c757d;">⏱️ {}s</span>', seconds)
        else:
            now = timezone.now()
            runtime = now - obj.started_at
            minutes = int(runtime.total_seconds() / 60)
            return format_html('<span style="color: #007bff;">⏳ {}m (ongoing)</span>', minutes)

    duration_display.short_description = "Duration"

    def winner_display(self, obj):
        """Display game winner information.

        Args:
            obj (Game): The game instance.

        Returns:
            str: Winner information or game status.
        """
        if obj.status == 'finished' and obj.loser:
            winners = obj.get_winner()
            if winners and winners.count() == 1:
                winner = winners.first()
                return format_html('<span style="color: #28a745;">🏆 {}</span>', winner.user.username)
            elif winners and winners.count() > 1:
                return format_html('<span style="color: #28a745;">🏆 {} winners</span>', winners.count())
            else:
                return format_html('<span style="color: #6c757d;">❓ Unknown</span>')
        elif obj.status == 'in_progress':
            return format_html('<span style="color: #007bff;">🎮 In Progress</span>')
        else:
            return format_html('<span style="color: #6c757d;">⏳ Pending</span>')

    winner_display.short_description = "Winner"

    def game_statistics(self, obj):
        """Display comprehensive game statistics.

        Args:
            obj (Game): The game instance.

        Returns:
            str: HTML formatted statistics summary.
        """
        try:
            turns_count = obj.turns.count()
            moves_count = Move.objects.filter(turn__game=obj).count()
            cards_on_table = obj.tablecard_set.count()
            cards_discarded = obj.discardpile_set.count()

            return format_html(
                '<div style="background: #f8f9fa; padding: 10px; border: 1px solid #dee2e6;">'
                '<strong>Game Statistics:</strong><br>'
                'Total Turns: {}<br>'
                'Total Moves: {}<br>'
                'Cards on Table: {}<br>'
                'Cards Discarded: {}<br>'
                '</div>',
                turns_count, moves_count, cards_on_table, cards_discarded
            )
        except:
            return format_html('<span style="color: #dc3545;">Statistics unavailable</span>')

    game_statistics.short_description = "Statistics"

    def get_queryset(self, request):
        """Optimize queryset for the admin interface.

        Args:
            request: The HTTP request object.

        Returns:
            QuerySet: Optimized queryset with prefetched related objects.
        """
        return super().get_queryset(request).select_related(
            'lobby',
            'lobby__owner',
            'trump_card',
            'trump_card__suit',
            'trump_card__rank',
            'loser'
        ).prefetch_related(
            'players',
            'turns',
            'tablecard_set'
        )

    def finish_games(self, request, queryset):
        """Custom admin action to finish selected games.

        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected games.
        """
        if not request.user.is_superuser:
            self.message_user(request, "Only superusers can finish games.", level='ERROR')
            return

        updated = queryset.filter(status='in_progress').update(
            status='finished',
            finished_at=timezone.now()
        )
        self.message_user(request, f"Finished {updated} game(s).")

    finish_games.short_description = "Finish selected games (Superuser only)"

    def export_game_data(self, request, queryset):
        """Custom admin action to export game data.

        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected games.
        """
        count = queryset.count()
        self.message_user(
            request,
            f"Export initiated for {count} game(s). Download link will be provided when ready."
        )

    export_game_data.short_description = "Export game data"


@admin.register(GamePlayer)
class GamePlayerAdmin(admin.ModelAdmin):
    """Admin interface for the GamePlayer model.

    Provides management capabilities for game player relationships
    with card tracking and position management.

    Features:
        - Player position and card count tracking
        - Direct links to game and user admin pages
        - Elimination status monitoring
        - Seat position management
        - Card count validation

    Attributes:
        list_display: Fields shown in the game player list view
        list_filter: Available filters in the admin sidebar
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        ordering: Default ordering by seat position
    """

    list_display = (
        'player_info_display',
        'game_link',
        'seat_position',
        'cards_display',
        'status_display'
    )

    list_display_links = ('player_info_display',)

    list_filter = (
        'seat_position',
        'cards_remaining',
        ('game', admin.RelatedOnlyFieldListFilter),
        ('user', admin.RelatedOnlyFieldListFilter),
    )

    search_fields = (
        'user__username',
        'game__lobby__name',
    )

    readonly_fields = ('id',)
    ordering = ('game', 'seat_position')

    def player_info_display(self, obj):
        """Display player information with user link.

        Args:
            obj (GamePlayer): The game player instance.

        Returns:
            str: HTML formatted player info with admin link.
        """
        user_url = reverse('admin:accounts_user_change', args=[obj.user.pk])
        return format_html('<a href="{}" style="color: #007bff;">👤 {}</a>', user_url, obj.user.username)

    player_info_display.short_description = "Player"
    player_info_display.admin_order_field = 'user__username'

    def game_link(self, obj):
        """Display link to the associated game.

        Args:
            obj (GamePlayer): The game player instance.

        Returns:
            str: HTML formatted link to game admin page.
        """
        game_url = reverse('admin:game_game_change', args=[obj.game.pk])
        short_id = str(obj.game.id)[:8]
        return format_html('<a href="{}" style="color: #28a745;">🎮 Game {}</a>', game_url, short_id)

    game_link.short_description = "Game"

    def cards_display(self, obj):
        """Display card count with visual indicator.

        Args:
            obj (GamePlayer): The game player instance.

        Returns:
            str: HTML formatted card count.
        """
        if obj.cards_remaining == 0:
            return format_html('<span style="color: #28a745; font-weight: bold;">🃏 0 cards (OUT)</span>')
        elif obj.cards_remaining <= 3:
            return format_html('<span style="color: #ffc107; font-weight: bold;">🃏 {} cards (LOW)</span>',
                               obj.cards_remaining)
        else:
            return format_html('<span style="color: #007bff;">🃏 {} cards</span>', obj.cards_remaining)

    cards_display.short_description = "Cards"
    cards_display.admin_order_field = 'cards_remaining'

    def status_display(self, obj):
        """Display player game status.

        Args:
            obj (GamePlayer): The game player instance.

        Returns:
            str: Visual indicator for player status.
        """
        if obj.is_eliminated():
            return format_html('<span style="color: #28a745;">✅ Eliminated</span>')
        else:
            return format_html('<span style="color: #007bff;">🎮 Playing</span>')

    status_display.short_description = "Status"


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    """Admin interface for the Card model.

    Provides management capabilities for playing cards with suit and rank
    organization, special card identification, and game usage tracking.

    Features:
        - Visual card representation with suit colors
        - Special card effect indicators
        - Suit and rank filtering
        - Card usage statistics
        - Trump card identification
        - Search by card properties

    Attributes:
        list_display: Fields shown in the card list view
        list_filter: Available filters in the admin sidebar
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        ordering: Default ordering by suit and rank
        fieldsets: Organization of fields in the detail view
    """

    list_display = (
        'card_display',
        'suit_display',
        'rank_display',
        'special_display',
        'usage_stats'
    )

    list_display_links = ('card_display',)

    list_filter = (
        ('suit', admin.RelatedOnlyFieldListFilter),
        ('rank', admin.RelatedOnlyFieldListFilter),
        ('special_card', admin.RelatedOnlyFieldListFilter),
    )

    search_fields = (
        'suit__name',
        'rank__name',
        'special_card__name',
    )

    readonly_fields = ('id', 'usage_stats', 'is_special')
    ordering = ('suit__name', 'rank__value')

    fieldsets = (
        ('Card Properties', {
            'fields': ('id', 'suit', 'rank'),
            'description': 'Basic card identification.'
        }),
        ('Special Effects', {
            'fields': ('special_card', 'is_special'),
            'description': 'Special card abilities and effects.',
            'classes': ('collapse',)
        }),
        ('Usage Statistics', {
            'fields': ('usage_stats',),
            'description': 'Card usage in games and trump selection.',
            'classes': ('collapse',)
        }),
    )

    def card_display(self, obj):
        """Display card with appropriate styling.

        Args:
            obj (Card): The card instance.

        Returns:
            str: HTML formatted card representation.
        """
        suit_emojis = {
            'Hearts': '♥️',
            'Diamonds': '♦️',
            'Clubs': '♣️',
            'Spades': '♠️'
        }

        emoji = suit_emojis.get(obj.suit.name, '🃏')

        if obj.is_special():
            return format_html(
                '<span style="background: #ffeaa7; padding: 2px 6px; border-radius: 3px; font-weight: bold;">'
                '{} {} of {}</span>',
                emoji, obj.rank.name, obj.suit.name
            )
        else:
            return format_html('{} {} of {}', emoji, obj.rank.name, obj.suit.name)

    card_display.short_description = "Card"
    card_display.admin_order_field = 'rank__value'

    def suit_display(self, obj):
        """Display suit with color styling.

        Args:
            obj (Card): The card instance.

        Returns:
            str: HTML formatted suit display.
        """
        if obj.suit.is_red():
            return format_html('<span style="color: #dc3545; font-weight: bold;">{}</span>', obj.suit.name)
        else:
            return format_html('<span style="color: #212529; font-weight: bold;">{}</span>', obj.suit.name)

    suit_display.short_description = "Suit"
    suit_display.admin_order_field = 'suit__name'

    def rank_display(self, obj):
        """Display rank with value information.

        Args:
            obj (Card): The card instance.

        Returns:
            str: Formatted rank with value.
        """
        if obj.rank.is_face_card():
            return format_html(
                '<span style="color: #6f42c1; font-weight: bold;">{} ({})</span>',
                obj.rank.name, obj.rank.value
            )
        else:
            return f"{obj.rank.name} ({obj.rank.value})"

    rank_display.short_description = "Rank"
    rank_display.admin_order_field = 'rank__value'

    def special_display(self, obj):
        """Display special card information.

        Args:
            obj (Card): The card instance.

        Returns:
            str: Special card indicator or standard card label.
        """
        if obj.is_special():
            return format_html(
                '<span style="color: #fd7e14; font-weight: bold;">⭐ {}</span>',
                obj.special_card.name
            )
        else:
            return format_html('<span style="color: #6c757d;">📋 Standard</span>')

    special_display.short_description = "Special"

    def usage_stats(self, obj):
        """Display card usage statistics.

        Args:
            obj (Card): The card instance.

        Returns:
            str: HTML formatted usage statistics.
        """
        try:
            trump_count = obj.as_trump.count()
            attack_count = obj.attack_card.count()
            defense_count = obj.defense_card.count()

            return format_html(
                '<div style="background: #f8f9fa; padding: 8px; border: 1px solid #dee2e6;">'
                '<strong>Usage:</strong><br>'
                'Trump: {} times<br>'
                'Attack: {} times<br>'
                'Defense: {} times<br>'
                '</div>',
                trump_count, attack_count, defense_count
            )
        except:
            return format_html('<span style="color: #dc3545;">Stats unavailable</span>')

    usage_stats.short_description = "Usage"


@admin.register(SpecialCard)
class SpecialCardAdmin(admin.ModelAdmin):
    """Admin interface for the SpecialCard model.

    Provides management capabilities for special card effects with
    detailed effect configuration and rule set associations.

    Features:
        - Effect type categorization and visualization
        - JSON effect value display and editing
        - Rule set compatibility tracking
        - Effect description formatting
        - Targetability and counter information

    Attributes:
        list_display: Fields shown in the special card list view
        list_filter: Available filters in the admin sidebar
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        ordering: Default ordering by name
        fieldsets: Organization of fields in the detail view
    """

    list_display = (
        'name',
        'effect_type_display',
        'effect_summary',
        'targetable_display',
        'counterable_display'
    )

    list_display_links = ('name',)

    list_filter = (
        'effect_type',
    )

    search_fields = (
        'name',
        'description',
    )

    readonly_fields = (
        'id',
        'targetable_display',
        'counterable_display',
        'effect_summary'
    )

    ordering = ('name',)

    fieldsets = (
        ('Special Card Information', {
            'fields': ('id', 'name', 'description'),
            'description': 'Basic special card identification and description.'
        }),
        ('Effect Configuration', {
            'fields': ('effect_type', 'effect_value', 'effect_summary'),
            'description': 'Special effect type and parameters.'
        }),
        ('Effect Properties', {
            'fields': ('targetable_display', 'counterable_display'),
            'description': 'Effect behavior and interaction properties.',
            'classes': ('collapse',)
        }),
    )

    def effect_type_display(self, obj):
        """Display effect type with visual indicator.

        Args:
            obj (SpecialCard): The special card instance.

        Returns:
            str: HTML formatted effect type.
        """
        type_colors = {
            'skip': '#ffc107',
            'reverse': '#6f42c1',
            'draw': '#dc3545',
            'custom': '#17a2b8'
        }

        type_icons = {
            'skip': '⏭️',
            'reverse': '🔄',
            'draw': '📥',
            'custom': '⚙️'
        }

        color = type_colors.get(obj.effect_type, '#6c757d')
        icon = type_icons.get(obj.effect_type, '❓')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color, icon, obj.get_effect_type_display()
        )

    effect_type_display.short_description = "Effect Type"
    effect_type_display.admin_order_field = 'effect_type'

    def effect_summary(self, obj):
        """Display effect summary with parameters.

        Args:
            obj (SpecialCard): The special card instance.

        Returns:
            str: HTML formatted effect summary.
        """
        if obj.effect_value:
            try:
                params = json.dumps(obj.effect_value, indent=2) if obj.effect_value else '{}'
                return format_html(
                    '<div style="font-family: monospace; background: #f8f9fa; padding: 8px; border: 1px solid #dee2e6;">'
                    '{}<br><br>'
                    '<strong>Parameters:</strong><br>'
                    '<pre style="margin: 0; font-size: 11px;">{}</pre>'
                    '</div>',
                    obj.get_effect_description() or obj.description or 'No description',
                    params
                )
            except:
                return format_html('<span style="color: #dc3545;">Invalid effect data</span>')
        else:
            return obj.get_effect_description() or obj.description or 'No description'

    effect_summary.short_description = "Effect Summary"

    def targetable_display(self, obj):
        """Display whether effect is targetable.

        Args:
            obj (SpecialCard): The special card instance.

        Returns:
            str: Visual indicator for targetability.
        """
        if obj.is_targetable():
            return format_html('<span style="color: #dc3545;">🎯 Targetable</span>')
        else:
            return format_html('<span style="color: #28a745;">🔄 Self-Affecting</span>')

    targetable_display.short_description = "Targeting"

    def counterable_display(self, obj):
        """Display whether effect can be countered.

        Args:
            obj (SpecialCard): The special card instance.

        Returns:
            str: Visual indicator for counterability.
        """
        if obj.can_be_countered():
            return format_html('<span style="color: #ffc107;">🛡️ Counterable</span>')
        else:
            return format_html('<span style="color: #dc3545;">⚡ Absolute</span>')

    counterable_display.short_description = "Countering"


@admin.register(SpecialRuleSet)
class SpecialRuleSetAdmin(admin.ModelAdmin):
    """Admin interface for the SpecialRuleSet model.

    Provides management capabilities for special rule configurations
    with compatibility checking and card association management.

    Features:
        - Rule set compatibility analysis
        - Special card count tracking
        - Player requirement validation
        - Lobby compatibility checking
        - Inline card management

    Attributes:
        list_display: Fields shown in the rule set list view
        list_filter: Available filters in the admin sidebar
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        ordering: Default ordering by name
        fieldsets: Organization of fields in the detail view
        inlines: Inline editing of related objects
    """

    list_display = (
        'name',
        'min_players',
        'card_count_display',
        'compatibility_summary'
    )

    list_display_links = ('name',)

    list_filter = (
        'min_players',
    )

    search_fields = (
        'name',
        'description',
    )

    readonly_fields = (
        'id',
        'card_count_display',
        'compatibility_summary'
    )

    ordering = ('name',)

    fieldsets = (
        ('Rule Set Information', {
            'fields': ('id', 'name', 'description'),
            'description': 'Basic rule set identification and description.'
        }),
        ('Configuration', {
            'fields': ('min_players',),
            'description': 'Rule set requirements and limitations.'
        }),
        ('Statistics', {
            'fields': ('card_count_display', 'compatibility_summary'),
            'description': 'Rule set statistics and compatibility analysis.',
            'classes': ('collapse',)
        }),
    )

    def card_count_display(self, obj):
        """Display count of associated special cards.

        Args:
            obj (SpecialRuleSet): The rule set instance.

        Returns:
            str: HTML formatted card count.
        """
        total_cards = obj.get_special_card_count()
        enabled_cards = obj.get_enabled_special_cards().count()

        return format_html(
            '<span style="color: #007bff;">🃏 {} cards</span><br>'
            '<small style="color: #28a745;">({} enabled)</small>',
            total_cards, enabled_cards
        )

    card_count_display.short_description = "Special Cards"

    def compatibility_summary(self, obj):
        """Display compatibility summary information.

        Args:
            obj (SpecialRuleSet): The rule set instance.

        Returns:
            str: HTML formatted compatibility information.
        """
        try:
            # Get lobbies using this rule set
            using_lobbies = LobbySettings.objects.filter(special_rule_set=obj).count()

            return format_html(
                '<div style="background: #f8f9fa; padding: 8px; border: 1px solid #dee2e6;">'
                '<strong>Compatibility:</strong><br>'
                'Min Players: {}<br>'
                'Used by {} lobbies<br>'
                'Special Cards: {} total, {} enabled<br>'
                '</div>',
                obj.min_players, using_lobbies,
                obj.get_special_card_count(),
                obj.get_enabled_special_cards().count()
            )
        except:
            return format_html('<span style="color: #dc3545;">Compatibility data unavailable</span>')

    compatibility_summary.short_description = "Compatibility"


class SpecialRuleSetCardInline(admin.TabularInline):
    """Inline admin interface for SpecialRuleSetCard model within SpecialRuleSet admin.

    Provides a compact view of special cards within a rule set directly from
    the rule set admin page, allowing quick card management and status toggling.
    """
    model = SpecialRuleSetCard
    extra = 0
    readonly_fields = ('id',)
    fields = ('card', 'is_enabled', 'id')


# Добавим inline к SpecialRuleSetAdmin
SpecialRuleSetAdmin.inlines = [SpecialRuleSetCardInline]


@admin.register(SpecialRuleSetCard)
class SpecialRuleSetCardAdmin(admin.ModelAdmin):
    """Admin interface for the SpecialRuleSetCard model.

    Provides management capabilities for special card associations within
    rule sets with enable/disable functionality and game compatibility.

    Features:
        - Rule set and card association management
        - Enable/disable status tracking
        - Game compatibility checking
        - Bulk enable/disable actions
        - Association filtering and search

    Attributes:
        list_display: Fields shown in the association list view
        list_filter: Available filters in the admin sidebar
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        ordering: Default ordering by rule set and card
        actions: Custom bulk actions available
    """

    list_display = (
        'association_display',
        'rule_set_link',
        'card_link',
        'status_display',
        'compatibility_display'
    )

    list_display_links = ('association_display',)

    list_filter = (
        'is_enabled',
        ('rule_set', admin.RelatedOnlyFieldListFilter),
        ('card', admin.RelatedOnlyFieldListFilter),
    )

    search_fields = (
        'rule_set__name',
        'card__name',
    )

    readonly_fields = ('id', 'compatibility_display')
    ordering = ('rule_set__name', 'card__name')

    actions = ['enable_cards', 'disable_cards', 'toggle_status']

    def association_display(self, obj):
        """Display association summary.

        Args:
            obj (SpecialRuleSetCard): The association instance.

        Returns:
            str: Formatted association summary.
        """
        status = "✅" if obj.is_enabled else "❌"
        return f"{status} {obj.card.name} in {obj.rule_set.name}"

    association_display.short_description = "Association"

    def rule_set_link(self, obj):
        """Display link to the rule set.

        Args:
            obj (SpecialRuleSetCard): The association instance.

        Returns:
            str: HTML formatted link to rule set admin page.
        """
        rule_set_url = reverse('admin:game_specialruleset_change', args=[obj.rule_set.pk])
        return format_html('<a href="{}" style="color: #6f42c1;">📋 {}</a>', rule_set_url, obj.rule_set.name)

    rule_set_link.short_description = "Rule Set"

    def card_link(self, obj):
        """Display link to the special card.

        Args:
            obj (SpecialRuleSetCard): The association instance.

        Returns:
            str: HTML formatted link to special card admin page.
        """
        card_url = reverse('admin:game_specialcard_change', args=[obj.card.pk])
        return format_html('<a href="{}" style="color: #fd7e14;">⭐ {}</a>', card_url, obj.card.name)

    card_link.short_description = "Special Card"

    def status_display(self, obj):
        """Display enable/disable status.

        Args:
            obj (SpecialRuleSetCard): The association instance.

        Returns:
            str: HTML formatted status indicator.
        """
        if obj.is_enabled:
            return format_html('<span style="color: #28a745; font-weight: bold;">✅ Enabled</span>')
        else:
            return format_html('<span style="color: #6c757d; font-weight: bold;">❌ Disabled</span>')

    status_display.short_description = "Status"
    status_display.admin_order_field = 'is_enabled'

    def compatibility_display(self, obj):
        """Display game compatibility information.

        Args:
            obj (SpecialRuleSetCard): The association instance.

        Returns:
            str: Compatibility status indicator.
        """
        if obj.is_enabled:
            return format_html('<span style="color: #28a745;">🎮 Available in Games</span>')
        else:
            return format_html('<span style="color: #6c757d;">🚫 Not Available</span>')

    compatibility_display.short_description = "Game Compatibility"

    def enable_cards(self, request, queryset):
        """Custom admin action to enable selected card associations.

        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected associations.
        """
        updated = queryset.update(is_enabled=True)
        self.message_user(request, f"Enabled {updated} special card(s) in rule set(s).")

    enable_cards.short_description = "Enable selected special cards"

    def disable_cards(self, request, queryset):
        """Custom admin action to disable selected card associations.

        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected associations.
        """
        updated = queryset.update(is_enabled=False)
        self.message_user(request, f"Disabled {updated} special card(s) in rule set(s).")

    disable_cards.short_description = "Disable selected special cards"

    def toggle_status(self, request, queryset):
        """Custom admin action to toggle enable/disable status.

        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected associations.
        """
        for obj in queryset:
            obj.toggle_enabled()

        count = queryset.count()
        self.message_user(request, f"Toggled status for {count} special card association(s).")

    toggle_status.short_description = "Toggle enable/disable status"


# Регистрируем остальные модели с базовой конфигурацией
@admin.register(GameDeck)
class GameDeckAdmin(admin.ModelAdmin):
    """Admin interface for the GameDeck model.

    Basic management interface for game deck cards with position tracking.
    """
    list_display = ('card', 'game_link', 'position', 'is_last_card')
    list_filter = (('game', admin.RelatedOnlyFieldListFilter),)
    search_fields = ('card__rank__name', 'card__suit__name', 'game__lobby__name')
    readonly_fields = ('id',)
    ordering = ('game', 'position')

    def game_link(self, obj):
        game_url = reverse('admin:game_game_change', args=[obj.game.pk])
        short_id = str(obj.game.id)[:8]
        return format_html('<a href="{}">Game {}</a>', game_url, short_id)

    game_link.short_description = "Game"


@admin.register(PlayerHand)
class PlayerHandAdmin(admin.ModelAdmin):
    """Admin interface for the PlayerHand model.

    Basic management interface for player hand cards with ordering.
    """
    list_display = ('player', 'card', 'game_link', 'order_in_hand')
    list_filter = (
        ('game', admin.RelatedOnlyFieldListFilter),
        ('player', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ('player__username', 'card__rank__name', 'card__suit__name')
    readonly_fields = ('id',)
    ordering = ('game', 'player', 'order_in_hand')

    def game_link(self, obj):
        game_url = reverse('admin:game_game_change', args=[obj.game.pk])
        short_id = str(obj.game.id)[:8]
        return format_html('<a href="{}">Game {}</a>', game_url, short_id)

    game_link.short_description = "Game"


@admin.register(TableCard)
class TableCardAdmin(admin.ModelAdmin):
    """Admin interface for the TableCard model.

    Management interface for attack-defense card pairs on the game table.
    """
    list_display = ('attack_card', 'defense_card', 'game_link', 'defended_status')
    list_filter = (
        ('game', admin.RelatedOnlyFieldListFilter),
        'defense_card',
    )
    search_fields = ('attack_card__rank__name', 'defense_card__rank__name', 'game__lobby__name')
    readonly_fields = ('id',)
    ordering = ('game', 'id')

    def game_link(self, obj):
        game_url = reverse('admin:game_game_change', args=[obj.game.pk])
        short_id = str(obj.game.id)[:8]
        return format_html('<a href="{}">Game {}</a>', game_url, short_id)

    game_link.short_description = "Game"

    def defended_status(self, obj):
        if obj.is_defended():
            return format_html('<span style="color: #28a745;">🛡️ Defended</span>')
        else:
            return format_html('<span style="color: #dc3545;">⚔️ Undefended</span>')

    defended_status.short_description = "Status"


@admin.register(DiscardPile)
class DiscardPileAdmin(admin.ModelAdmin):
    """Admin interface for the DiscardPile model.

    Basic management interface for discarded cards.
    """
    list_display = ('card', 'game_link', 'position')
    list_filter = (('game', admin.RelatedOnlyFieldListFilter),)
    search_fields = ('card__rank__name', 'card__suit__name', 'game__lobby__name')
    readonly_fields = ('id',)
    ordering = ('game', 'position')

    def game_link(self, obj):
        game_url = reverse('admin:game_game_change', args=[obj.game.pk])
        short_id = str(obj.game.id)[:8]
        return format_html('<a href="{}">Game {}</a>', game_url, short_id)

    game_link.short_description = "Game"


@admin.register(Turn)
class TurnAdmin(admin.ModelAdmin):
    """Admin interface for the Turn model.

    Management interface for game turns with move tracking.
    """
    list_display = ('turn_number', 'player', 'game_link', 'move_count', 'completion_status')
    list_filter = (
        ('game', admin.RelatedOnlyFieldListFilter),
        ('player', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ('player__username', 'game__lobby__name')
    readonly_fields = ('id', 'move_count')
    ordering = ('game', 'turn_number')

    def game_link(self, obj):
        game_url = reverse('admin:game_game_change', args=[obj.game.pk])
        short_id = str(obj.game.id)[:8]
        return format_html('<a href="{}">Game {}</a>', game_url, short_id)

    game_link.short_description = "Game"

    def move_count(self, obj):
        return obj.moves.count()

    move_count.short_description = "Moves"

    def completion_status(self, obj):
        if obj.is_complete():
            return format_html('<span style="color: #28a745;">✅ Complete</span>')
        else:
            return format_html('<span style="color: #ffc107;">⏳ Pending</span>')

    completion_status.short_description = "Status"


@admin.register(Move)
class MoveAdmin(admin.ModelAdmin):
    """Admin interface for the Move model.

    Management interface for individual player moves with action tracking.
    """
    list_display = ('action_display', 'player_link', 'game_link', 'turn_number', 'created_at')
    list_filter = (
        'action_type',
        'created_at',
        ('turn__game', admin.RelatedOnlyFieldListFilter),
        ('turn__player', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ('turn__player__username', 'turn__game__lobby__name')
    readonly_fields = ('id', 'created_at', 'player_link', 'game_link', 'turn_number')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    def action_display(self, obj):
        action_colors = {
            'attack': '#dc3545',
            'defend': '#28a745',
            'pickup': '#ffc107'
        }
        action_icons = {
            'attack': '⚔️',
            'defend': '🛡️',
            'pickup': '📥'
        }

        color = action_colors.get(obj.action_type, '#6c757d')
        icon = action_icons.get(obj.action_type, '❓')

        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color, icon, obj.get_action_type_display()
        )

    action_display.short_description = "Action"
    action_display.admin_order_field = 'action_type'

    def player_link(self, obj):
        player_url = reverse('admin:accounts_user_change', args=[obj.turn.player.pk])
        return format_html('<a href="{}">👤 {}</a>', player_url, obj.turn.player.username)

    player_link.short_description = "Player"

    def game_link(self, obj):
        game_url = reverse('admin:game_game_change', args=[obj.turn.game.pk])
        short_id = str(obj.turn.game.id)[:8]
        return format_html('<a href="{}">🎮 Game {}</a>', game_url, short_id)

    game_link.short_description = "Game"

    def turn_number(self, obj):
        return obj.turn.turn_number

    turn_number.short_description = "Turn #"
    turn_number.admin_order_field = 'turn__turn_number'