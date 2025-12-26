"""
Purpose Module Admin

Admin configuration for managing Purpose module models,
including the configurable lookup tables.
"""

from django.contrib import admin
from .models import (
    LifeDomain,
    ReflectionPrompt,
    AnnualDirection,
    LifeGoal,
    ChangeIntention,
    Reflection,
    ReflectionResponse,
    PlanningAction,
)


# =============================================================================
# Configuration / Lookup Tables
# =============================================================================

@admin.register(LifeDomain)
class LifeDomainAdmin(admin.ModelAdmin):
    """Admin for Life Domains - configurable goal categories."""
    list_display = ['name', 'slug', 'icon', 'color', 'sort_order', 'is_active']
    list_editable = ['sort_order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['sort_order', 'name']


@admin.register(ReflectionPrompt)
class ReflectionPromptAdmin(admin.ModelAdmin):
    """Admin for Reflection Prompts - configurable questions."""
    list_display = ['question_preview', 'prompt_type', 'sort_order', 'is_active']
    list_editable = ['sort_order', 'is_active']
    list_filter = ['prompt_type', 'is_active']
    search_fields = ['question', 'description']
    ordering = ['prompt_type', 'sort_order']
    
    def question_preview(self, obj):
        return obj.question[:75] + '...' if len(obj.question) > 75 else obj.question
    question_preview.short_description = 'Question'


# =============================================================================
# User Content
# =============================================================================

@admin.register(AnnualDirection)
class AnnualDirectionAdmin(admin.ModelAdmin):
    """Admin for Annual Directions."""
    list_display = ['user', 'year', 'word_of_year', 'theme', 'is_current']
    list_filter = ['year', 'is_current']
    search_fields = ['user__email', 'word_of_year', 'theme']
    ordering = ['-year', 'user']
    raw_id_fields = ['user']


@admin.register(LifeGoal)
class LifeGoalAdmin(admin.ModelAdmin):
    """Admin for Life Goals."""
    list_display = ['title', 'user', 'domain', 'timeframe', 'status', 'target_date']
    list_filter = ['status', 'domain', 'timeframe']
    search_fields = ['title', 'description', 'user__email']
    ordering = ['-created_at']
    raw_id_fields = ['user', 'annual_direction']


@admin.register(ChangeIntention)
class ChangeIntentionAdmin(admin.ModelAdmin):
    """Admin for Change Intentions."""
    list_display = ['intention', 'user', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['intention', 'description', 'user__email']
    ordering = ['-created_at']
    raw_id_fields = ['user', 'annual_direction']


class ReflectionResponseInline(admin.TabularInline):
    """Inline for Reflection Responses."""
    model = ReflectionResponse
    extra = 0
    fields = ['question_text', 'response', 'sort_order']


@admin.register(Reflection)
class ReflectionAdmin(admin.ModelAdmin):
    """Admin for Reflections."""
    list_display = ['__str__', 'user', 'reflection_type', 'year', 'is_complete']
    list_filter = ['reflection_type', 'year', 'is_complete']
    search_fields = ['user__email', 'title']
    ordering = ['-year', '-created_at']
    raw_id_fields = ['user']
    inlines = [ReflectionResponseInline]


@admin.register(PlanningAction)
class PlanningActionAdmin(admin.ModelAdmin):
    """Admin for Planning Actions."""
    list_display = ['description_preview', 'user', 'action_type', 'annual_direction']
    list_filter = ['action_type']
    search_fields = ['description', 'user__email']
    ordering = ['-created_at']
    raw_id_fields = ['user', 'annual_direction']
    
    def description_preview(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_preview.short_description = 'Description'
