"""Admin configuration for the Durak card game application.

This module defines the Django admin interface configuration for all models
in the accounts app, providing a comprehensive management interface for
administrators.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin interface for the custom User model.
    
    Extends Django's built-in UserAdmin to handle the custom fields
    and provide enhanced functionality for managing users in the
    Durak card game application.
    
    Features:
        - Custom list display with avatar preview
        - Enhanced filtering and search capabilities
        - Readonly fields for system-generated data
        - Custom fieldsets for better organization
        - Avatar preview in detail view
        
    Attributes:
        list_display: Fields shown in the user list view
        list_filter: Available filters in the sidebar
        search_fields: Fields that can be searched
        readonly_fields: Fields that cannot be edited
        ordering: Default ordering for the user list
        fieldsets: Organization of fields in the detail view
    """

    # List view configuration
    list_display = (
        'username',
        'email',
        'get_full_display_name',
        'avatar_preview',
        'is_active',
        'is_staff',
        'created_at',
        'last_login'
    )

    list_display_links = ('username', 'email')

    list_filter = (
        'is_active',
        'is_staff',
        'is_superuser',
        'created_at',
        'last_login',
        'date_joined'
    )

    search_fields = ('username', 'email', 'first_name', 'last_name')

    readonly_fields = ('id', 'created_at', 'date_joined', 'last_login', 'avatar_display')

    ordering = ('-created_at',)

    # Detail view configuration
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'username', 'email', 'password'),
            'description': 'Core user identification and authentication fields.'
        }),
        ('Personal Information', {
            'fields': ('first_name', 'last_name'),
            'description': 'Optional personal details for display purposes.'
        }),
        ('Profile', {
            'fields': ('avatar_url', 'avatar_display'),
            'description': 'User profile customization options.'
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'description': 'User permissions and group memberships.',
            'classes': ('collapse',)
        }),
        ('Important Dates', {
            'fields': ('created_at', 'date_joined', 'last_login'),
            'description': 'System-generated timestamps for user activity.',
            'classes': ('collapse',)
        }),
    )

    # Add user form configuration
    add_fieldsets = (
        ('User Creation', {
            'fields': ('username', 'email', 'password1', 'password2'),
            'description': 'Create a new user account for the Durak game.'
        }),
        ('Optional Information', {
            'fields': ('first_name', 'last_name', 'avatar_url'),
            'classes': ('collapse',)
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser'),
            'classes': ('collapse',)
        }),
    )

    def avatar_preview(self, obj):
        """Display a small preview of the user's avatar in the list view.
        
        Args:
            obj (User): The user instance.
            
        Returns:
            str: HTML string with avatar image or placeholder text.
        """
        if obj.has_avatar():
            return format_html(
                '<img src="{}" width="30" height="30" style="border-radius: 50%; object-fit: cover;" />',
                obj.avatar_url
            )
        return "No avatar"

    avatar_preview.short_description = "Avatar"

    def avatar_display(self, obj):
        """Display a larger preview of the user's avatar in the detail view.
        
        Args:
            obj (User): The user instance.
            
        Returns:
            str: HTML string with avatar image or placeholder message.
        """
        if obj.has_avatar():
            return format_html(
                '<img src="{}" width="100" height="100" style="border-radius: 10px; object-fit: cover;" />'
                '<br><small><a href="{}" target="_blank">View full size</a></small>',
                obj.avatar_url,
                obj.avatar_url
            )
        return "No avatar uploaded"

    avatar_display.short_description = "Avatar Preview"

    def get_queryset(self, request):
        """Optimize queryset for the admin list view.
        
        Args:
            request: The HTTP request object.
            
        Returns:
            QuerySet: Optimized queryset with prefetched related objects.
        """
        return super().get_queryset(request).select_related()

    def has_delete_permission(self, request, obj=None):
        """Control delete permissions for user objects.
        
        Prevents deletion of superuser accounts by non-superusers
        and adds additional safety checks.
        
        Args:
            request: The HTTP request object.
            obj (User, optional): The user object being considered for deletion.
            
        Returns:
            bool: True if the user can delete the object, False otherwise.
        """
        if obj and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        """Custom save logic for user objects.
        
        Args:
            request: The HTTP request object.
            obj (User): The user object being saved.
            form: The admin form instance.
            change (bool): True if this is an update, False if creating new.
        """
        # Log user creation/updates for audit purposes
        if not change:
            # This is a new user
            obj.save()
        else:
            # This is an update to existing user
            obj.save()

        super().save_model(request, obj, form, change)


# Optional: Customize admin site headers
admin.site.site_header = "Durak Game Administration"
admin.site.site_title = "Durak Admin"
admin.site.index_title = "Welcome to Durak Game Administration"
