from django.contrib import admin
from .models import CoachingStyle, AIInsight, AIUsageLog


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
