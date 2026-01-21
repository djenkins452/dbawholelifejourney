from django.contrib import admin
from .models import (
    CoachingStyle, AIInsight, AIUsageLog, AIPromptConfig,
    ValuesGuardrailPattern, ValuesRedirectSuggestion
)


@admin.register(CoachingStyle)
class CoachingStyleAdmin(admin.ModelAdmin):
    list_display = ['name', 'key', 'is_active', 'is_default', 'sort_order']
    list_filter = ['is_active', 'is_default']
    list_editable = ['is_active', 'is_default', 'sort_order']
    search_fields = ['name', 'key', 'description']
    ordering = ['sort_order', 'name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        (None, {
            'fields': ('key', 'name', 'description')
        }),
        ('AI Instructions', {
            'fields': ('prompt_instructions',),
            'description': 'The full prompt instructions sent to the AI for this coaching style.'
        }),
        ('Settings', {
            'fields': ('is_active', 'is_default', 'sort_order')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AIInsight)
class AIInsightAdmin(admin.ModelAdmin):
    list_display = ['insight_type', 'user', 'coaching_style', 'created_at', 'was_helpful']
    list_filter = ['insight_type', 'coaching_style', 'was_helpful', 'created_at']
    search_fields = ['user__email', 'content']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'


@admin.register(AIUsageLog)
class AIUsageLogAdmin(admin.ModelAdmin):
    list_display = ['endpoint', 'user', 'model_used', 'total_tokens', 'success', 'created_at']
    list_filter = ['endpoint', 'model_used', 'success', 'created_at']
    search_fields = ['user__email', 'endpoint']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'


@admin.register(AIPromptConfig)
class AIPromptConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'prompt_type', 'refresh_frequency', 'min_sentences', 'max_sentences', 'is_active', 'updated_at']
    list_filter = ['prompt_type', 'refresh_frequency', 'is_active']
    list_editable = ['is_active', 'refresh_frequency']
    search_fields = ['name', 'system_instructions']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        (None, {
            'fields': ('prompt_type', 'name', 'description')
        }),
        ('Prompt Instructions', {
            'fields': ('system_instructions',),
            'description': 'The main instructions sent to the AI. You can use {variables} for dynamic content.'
        }),
        ('Refresh Settings', {
            'fields': ('refresh_frequency',),
            'description': 'How often the insight should be refreshed. "Daily + on data change" is recommended for most insights.'
        }),
        ('Response Length', {
            'fields': (('min_sentences', 'max_sentences'), 'max_tokens'),
            'description': 'Control how long the AI responses should be.'
        }),
        ('Additional Guidance', {
            'fields': ('tone_guidance', 'things_to_avoid', 'example_responses'),
            'classes': ('collapse',),
            'description': 'Fine-tune the AI behavior with additional guidance.'
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ValuesGuardrailPattern)
class ValuesGuardrailPatternAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'category', 'severity', 'is_active',
        'applies_to_input', 'applies_to_output', 'sort_order'
    ]
    list_filter = ['category', 'severity', 'is_active', 'applies_to_input', 'applies_to_output']
    list_editable = ['is_active', 'sort_order']
    search_fields = ['name', 'pattern', 'refusal_message']
    ordering = ['sort_order', 'category', 'name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        (None, {
            'fields': ('name', 'category', 'severity')
        }),
        ('Pattern', {
            'fields': ('pattern',),
            'description': 'Regex pattern to match. Case-insensitive. Use \\b for word boundaries.'
        }),
        ('Response', {
            'fields': ('refusal_message',),
            'description': 'Custom message for refusals. Leave blank for default.'
        }),
        ('Scope', {
            'fields': (('applies_to_input', 'applies_to_output'),),
            'description': 'Where this pattern should be applied.'
        }),
        ('Settings', {
            'fields': ('is_active', 'sort_order')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ValuesRedirectSuggestion)
class ValuesRedirectSuggestionAdmin(admin.ModelAdmin):
    list_display = ['module', 'trigger_keywords_preview', 'is_active', 'sort_order']
    list_filter = ['module', 'is_active']
    list_editable = ['is_active', 'sort_order']
    search_fields = ['trigger_keywords', 'suggestion_text', 'follow_up_prompt']
    ordering = ['sort_order', 'module']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        (None, {
            'fields': ('module',)
        }),
        ('Triggers', {
            'fields': ('trigger_keywords',),
            'description': 'Comma-separated keywords that trigger this suggestion (case-insensitive).'
        }),
        ('Response', {
            'fields': ('suggestion_text', 'follow_up_prompt'),
            'description': 'The redirect message. Use {module_name} placeholder for module name.'
        }),
        ('Settings', {
            'fields': ('is_active', 'sort_order')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def trigger_keywords_preview(self, obj):
        """Show first 50 chars of keywords."""
        return obj.trigger_keywords[:50] + ('...' if len(obj.trigger_keywords) > 50 else '')
    trigger_keywords_preview.short_description = 'Keywords'
