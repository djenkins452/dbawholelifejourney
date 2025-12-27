from django.contrib import admin
from .models import (
    HelpTopic, AdminHelpTopic,
    HelpCategory, HelpArticle, HelpConversation, HelpMessage
)


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


# =============================================================================
# WLJ ASSISTANT CHAT BOT ADMIN
# =============================================================================


@admin.register(HelpCategory)
class HelpCategoryAdmin(admin.ModelAdmin):
    """Admin interface for help article categories."""

    list_display = ['name', 'slug', 'icon', 'sort_order', 'is_active', 'article_count']
    list_filter = ['is_active']
    search_fields = ['name', 'slug', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['sort_order', 'name']

    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'description', 'icon'),
        }),
        ('Display', {
            'fields': ('sort_order', 'is_active'),
        }),
    )

    def article_count(self, obj):
        return obj.articles.count()
    article_count.short_description = 'Articles'


@admin.register(HelpArticle)
class HelpArticleAdmin(admin.ModelAdmin):
    """Admin interface for help articles."""

    list_display = ['title', 'category', 'module', 'sort_order', 'is_active', 'updated_at']
    list_filter = ['category', 'module', 'is_active']
    search_fields = ['title', 'slug', 'summary', 'content', 'keywords']
    prepopulated_fields = {'slug': ('title',)}
    ordering = ['category', 'sort_order', 'title']

    fieldsets = (
        (None, {
            'fields': ('title', 'slug'),
        }),
        ('Content', {
            'fields': ('summary', 'content'),
            'description': 'Summary is shown in chat responses. Content supports Markdown.',
        }),
        ('Organization', {
            'fields': ('category', 'module', 'keywords', 'sort_order', 'is_active'),
            'description': 'Keywords help the chat bot find this article. Use commas to separate.',
        }),
        ('Related Articles', {
            'fields': ('related_articles',),
            'classes': ('collapse',),
        }),
    )

    filter_horizontal = ['related_articles']


@admin.register(HelpConversation)
class HelpConversationAdmin(admin.ModelAdmin):
    """Admin interface for help chat conversations."""

    list_display = ['id', 'user', 'context_module', 'started_at', 'last_activity', 'message_count', 'emailed_at']
    list_filter = ['context_module', 'emailed_at']
    search_fields = ['user__email', 'context_url']
    readonly_fields = ['started_at', 'last_activity', 'message_count']
    ordering = ['-started_at']

    fieldsets = (
        (None, {
            'fields': ('user', 'context_module', 'context_url'),
        }),
        ('Timing', {
            'fields': ('started_at', 'last_activity', 'emailed_at'),
        }),
    )

    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Messages'


@admin.register(HelpMessage)
class HelpMessageAdmin(admin.ModelAdmin):
    """Admin interface for help chat messages."""

    list_display = ['id', 'conversation', 'is_user', 'content_preview', 'created_at']
    list_filter = ['is_user', 'created_at']
    search_fields = ['content']
    readonly_fields = ['created_at']
    ordering = ['-created_at']

    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'
