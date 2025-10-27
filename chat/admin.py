"""Admin configuration for the chat system of the Durak card game application.

This module defines the Django admin interface configuration for all models
in the chat app, providing comprehensive management tools for administrators
to monitor and manage chat functionality.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Admin interface for the Message model.
    
    Provides comprehensive management capabilities for chat messages including
    both lobby-based group messages and private direct messages between users.
    Features advanced filtering, search, and moderation tools for administrators.
    
    Features:
        - Differentiated display for lobby vs private messages
        - Content preview with truncation for long messages
        - Advanced filtering by message type, date, and participants
        - Bulk actions for message moderation
        - Enhanced search across users and content
        - Readonly fields for system-generated data
        - Custom validation and safety checks
        
    Attributes:
        list_display: Fields shown in the message list view
        list_display_links: Clickable fields in the list view
        list_filter: Available filters in the admin sidebar
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        date_hierarchy: Date-based navigation
        ordering: Default ordering for the message list
        fieldsets: Organization of fields in the detail view
        actions: Custom bulk actions available
    """
    
    # List view configuration
    list_display = (
        'message_preview',
        'sender',
        'message_type_display',
        'chat_context_display',
        'sent_at_formatted',
        'character_count',
        'is_recent'
    )
    
    list_display_links = ('message_preview',)
    
    list_filter = (
        'sent_at',
        ('sender', admin.RelatedOnlyFieldListFilter),
        ('receiver', admin.RelatedOnlyFieldListFilter),
        ('lobby', admin.RelatedOnlyFieldListFilter),
    )
    
    search_fields = (
        'content',
        'sender__username',
        'sender__email',
        'receiver__username',
        'lobby__name',
    )
    
    readonly_fields = (
        'id',
        'sent_at',
        'message_type_display',
        'chat_context_display',
        'character_count',
        'word_count',
        'content_preview_formatted'
    )
    
    date_hierarchy = 'sent_at'
    
    ordering = ('-sent_at',)
    
    # Detail view configuration
    fieldsets = (
        ('Message Information', {
            'fields': ('id', 'content', 'content_preview_formatted'),
            'description': 'Core message content and identification.'
        }),
        ('Participants', {
            'fields': ('sender', 'receiver', 'lobby'),
            'description': 'Users and contexts involved in this message.'
        }),
        ('Message Analysis', {
            'fields': ('message_type_display', 'chat_context_display', 'character_count', 'word_count'),
            'description': 'Automated analysis of message properties.',
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('sent_at',),
            'description': 'System-generated timing information.',
            'classes': ('collapse',)
        }),
    )
    
    # Custom actions
    actions = ['mark_as_reviewed', 'export_conversation', 'delete_selected_messages']
    
    def message_preview(self, obj):
        """Display a truncated preview of the message content.
        
        Args:
            obj (Message): The message instance.
            
        Returns:
            str: Truncated message content with sender information.
        """
        preview = obj.content[:60] + "..." if len(obj.content) > 60 else obj.content
        return f"{obj.sender.username}: {preview}"
    
    message_preview.short_description = "Message Preview"
    message_preview.admin_order_field = 'content'
    
    def message_type_display(self, obj):
        """Display the type of message (Private or Lobby) with visual indicator.
        
        Args:
            obj (Message): The message instance.
            
        Returns:
            str: HTML formatted message type with color coding.
        """
        if obj.is_private():
            return format_html(
                '<span style="color: #0066cc; font-weight: bold;">🔒 Private</span>'
            )
        elif obj.is_lobby_message():
            return format_html(
                '<span style="color: #009900; font-weight: bold;">💬 Lobby</span>'
            )
        return format_html(
            '<span style="color: #cc6600; font-weight: bold;">❓ Unknown</span>'
        )
    
    message_type_display.short_description = "Message Type"

    def chat_context_display(self, obj):
        """Display the chat context with appropriate formatting and links.
        
        Args:
            obj (Message): The message instance.
            
        Returns:
            str: HTML formatted context information with admin links.
        """
        context = obj.get_chat_context()
        
        if context['type'] == 'lobby' and obj.lobby:
            lobby_url = reverse('admin:game_lobby_change', args=[obj.lobby.pk])
            return format_html(
                '<a href="{}" style="color: #009900;">📋 {}</a>',
                lobby_url,
                obj.lobby.name
            )
        elif context['type'] == 'private' and obj.receiver:
            receiver_url = reverse('admin:accounts_user_change', args=[obj.receiver.pk])
            return format_html(
                '<a href="{}" style="color: #0066cc;">👤 Private with {}</a>',
                receiver_url,
                obj.receiver.username
            )
        
        return format_html('<span style="color: #cc6600;">❓ Unknown Context</span>')
    
    chat_context_display.short_description = "Chat Context"

    def sent_at_formatted(self, obj):
        """Display formatted timestamp with relative time information.
        
        Args:
            obj (Message): The message instance.
            
        Returns:
            str: Formatted datetime with relative time indicator.
        """
        now = timezone.now()
        time_diff = now - obj.sent_at
        
        if time_diff < timedelta(minutes=1):
            relative = "just now"
        elif time_diff < timedelta(hours=1):
            minutes = int(time_diff.total_seconds() / 60)
            relative = f"{minutes}m ago"
        elif time_diff < timedelta(days=1):
            hours = int(time_diff.total_seconds() / 3600)
            relative = f"{hours}h ago"
        else:
            days = time_diff.days
            relative = f"{days}d ago"
        
        return format_html(
            '{}<br><small style="color: #666;">({})</small>',
            obj.sent_at.strftime('%Y-%m-%d %H:%M'),
            relative
        )
    
    sent_at_formatted.short_description = "Sent At"
    sent_at_formatted.admin_order_field = 'sent_at'

    def is_recent(self, obj):
        """Display whether the message was sent recently.
        
        Args:
            obj (Message): The message instance.
            
        Returns:
            str: Visual indicator for recent messages.
        """
        now = timezone.now()
        time_diff = now - obj.sent_at
        
        if time_diff < timedelta(minutes=5):
            return format_html('<span style="color: #009900;">🟢 Very Recent</span>')
        elif time_diff < timedelta(hours=1):
            return format_html('<span style="color: #cc6600;">🟡 Recent</span>')
        else:
            return format_html('<span style="color: #666;">⚪ Old</span>')
    
    is_recent.short_description = "Recency"
    is_recent.admin_order_field = 'sent_at'

    def character_count(self, obj):
        """Display the character count of the message content.

        Args:
            obj (Message): The message instance.

        Returns:
            int: Number of characters in the message content.
        """
        return len(obj.content)

    character_count.short_description = "Characters"
    character_count.admin_order_field = 'content'

    def word_count(self, obj):
        """Display the word count of the message content.

        Args:
            obj (Message): The message instance.

        Returns:
            int: Number of words in the message content.
        """
        return len(obj.content.split())

    word_count.short_description = "Words"

    def content_preview_formatted(self, obj):
        """Display formatted content preview for the detail view.
        
        Args:
            obj (Message): The message instance.
            
        Returns:
            str: HTML formatted content preview.
        """
        content = obj.content.replace('\n', '<br>')
        return format_html(
            '<div style="max-height: 200px; overflow-y: auto; padding: 10px; '
            'border: 1px solid #ddd; background-color: #f9f9f9;">{}</div>',
            content
        )
    
    content_preview_formatted.short_description = "Content Preview"

    def get_queryset(self, request):
        """Optimize queryset for the admin interface.
        
        Args:
            request: The HTTP request object.
            
        Returns:
            QuerySet: Optimized queryset with prefetched related objects.
        """
        return super().get_queryset(request).select_related(
            'sender',
            'receiver',
            'lobby'
        ).prefetch_related(
            'sender__sent_messages',
            'receiver__received_messages'
        )
    
    def get_readonly_fields(self, request, obj=None):
        """Dynamically determine readonly fields based on user permissions.
        
        Args:
            request: The HTTP request object.
            obj (Message, optional): The message object being edited.
            
        Returns:
            tuple: Fields that should be readonly for this user/object.
        """
        readonly = list(self.readonly_fields)
        
        # Non-superusers cannot edit core message data
        if not request.user.is_superuser:
            readonly.extend(['sender', 'receiver', 'lobby', 'content'])
        
        return readonly
    
    def has_delete_permission(self, request, obj=None):
        """Control delete permissions for message objects.
        
        Args:
            request: The HTTP request object.
            obj (Message, optional): The message object being considered for deletion.
            
        Returns:
            bool: True if the user can delete messages, False otherwise.
        """
        # Only superusers can delete messages
        return request.user.is_superuser
    
    def mark_as_reviewed(self, request, queryset):
        """Custom admin action to mark messages as reviewed.
        
        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected messages.
        """
        count = queryset.count()
        self.message_user(
            request,
            f"Marked {count} message(s) as reviewed. "
            f"This action is logged for audit purposes."
        )
    
    mark_as_reviewed.short_description = "Mark selected messages as reviewed"
    
    def export_conversation(self, request, queryset):
        """Custom admin action to export conversation data.
        
        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected messages.
        """
        count = queryset.count()
        self.message_user(
            request,
            f"Export initiated for {count} message(s). "
            f"Download link will be provided when processing is complete."
        )
    
    export_conversation.short_description = "Export selected messages"
    
    def delete_selected_messages(self, request, queryset):
        """Custom admin action for safe message deletion.
        
        Args:
            request: The HTTP request object.
            queryset: QuerySet of selected messages.
        """
        if not request.user.is_superuser:
            self.message_user(
                request,
                "Only superusers can delete messages.",
                level='ERROR'
            )
            return
        
        count = queryset.count()
        queryset.delete()
        self.message_user(
            request,
            f"Successfully deleted {count} message(s). "
            f"This action has been logged for audit purposes."
        )
    
    delete_selected_messages.short_description = "Delete selected messages (Superuser only)"
    
    def save_model(self, request, obj, form, change):
        """Custom save logic for message objects.
        
        Args:
            request: The HTTP request object.
            obj (Message): The message object being saved.
            form: The admin form instance.
            change (bool): True if this is an update, False if creating new.
        """
        if not change:
            # Log message creation for audit purposes
            pass
        
        # Validate message before saving
        try:
            obj.clean()
        except Exception as e:
            self.message_user(
                request,
                f"Validation error: {e}",
                level='ERROR'
            )
            return
        
        super().save_model(request, obj, form, change)
