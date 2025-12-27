from django.contrib import admin
from .models import HelpTopic, AdminHelpTopic


@admin.register(HelpTopic)
class HelpTopicAdmin(admin.ModelAdmin):
    """Admin interface for user-facing help topics."""

    list_display = ['context_id', 'title', 'app_name', 'order', 'is_active', 'updated_at']
    list_filter = ['app_name', 'is_active']
    search_fields = ['context_id', 'help_id', 'title', 'content']
    ordering = ['app_name', 'order', 'title']

    fieldsets = (
        ('Identification', {
            'fields': ('context_id', 'help_id'),
            'description': 'Context ID must match the HELP_CONTEXT_ID in templates.'
        }),
        ('Content', {
            'fields': ('title', 'description', 'content'),
            'description': 'Content supports Markdown formatting.'
        }),
        ('Organization', {
            'fields': ('app_name', 'order', 'is_active'),
        }),
        ('Related Topics', {
            'fields': ('related_topics',),
            'classes': ('collapse',),
        }),
    )

    filter_horizontal = ['related_topics']

    def get_readonly_fields(self, request, obj=None):
        if obj:
            # Can't change context_id after creation
            return ['context_id']
        return []


@admin.register(AdminHelpTopic)
class AdminHelpTopicAdmin(admin.ModelAdmin):
    """Admin interface for technical/admin help topics."""

    list_display = ['context_id', 'title', 'category', 'order', 'is_active', 'updated_at']
    list_filter = ['category', 'is_active']
    search_fields = ['context_id', 'help_id', 'title', 'content']
    ordering = ['category', 'order', 'title']

    fieldsets = (
        ('Identification', {
            'fields': ('context_id', 'help_id'),
            'description': 'Context ID must match the admin page identifier.'
        }),
        ('Content', {
            'fields': ('title', 'description', 'content'),
            'description': 'Content supports Markdown formatting.'
        }),
        ('Organization', {
            'fields': ('category', 'order', 'is_active'),
        }),
        ('Related Topics', {
            'fields': ('related_topics',),
            'classes': ('collapse',),
        }),
    )

    filter_horizontal = ['related_topics']

    def get_readonly_fields(self, request, obj=None):
        if obj:
            # Can't change context_id after creation
            return ['context_id']
        return []
