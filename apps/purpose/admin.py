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
    GoalMilestone,
    ChangeIntention,
    Reflection,
    ReflectionResponse,
    PlanningAction,
    HabitGoal,
    HabitEntry,
    GoalInsight,
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


class GoalMilestoneInline(admin.TabularInline):
    """Inline for Goal Milestones."""
    model = GoalMilestone
    extra = 0
    fields = ['title', 'target_date', 'completed', 'completed_date', 'sort_order']
    readonly_fields = ['completed_date']


@admin.register(LifeGoal)
class LifeGoalAdmin(admin.ModelAdmin):
    """Admin for Life Goals."""
    list_display = ['title', 'user', 'domain', 'timeframe', 'status', 'is_primary_mission', 'target_date', 'milestone_progress']
    list_filter = ['status', 'domain', 'timeframe', 'is_primary_mission']
    search_fields = ['title', 'description', 'user__email']
    ordering = ['-created_at']
    raw_id_fields = ['user', 'annual_direction']
    inlines = [GoalMilestoneInline]

    def milestone_progress(self, obj):
        if not obj.has_milestones:
            return '-'
        return f"{obj.completed_milestone_count}/{obj.milestone_count}"
    milestone_progress.short_description = 'Milestones'


@admin.register(GoalMilestone)
class GoalMilestoneAdmin(admin.ModelAdmin):
    """Admin for Goal Milestones."""
    list_display = ['title', 'goal', 'target_date', 'completed', 'completed_date', 'is_overdue']
    list_filter = ['completed', 'goal__user']
    search_fields = ['title', 'description', 'goal__title']
    ordering = ['-created_at']
    raw_id_fields = ['goal']

    def is_overdue(self, obj):
        return obj.is_overdue
    is_overdue.boolean = True
    is_overdue.short_description = 'Overdue'


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


# =============================================================================
# Habit Goals & Goal Engine
# =============================================================================

class HabitEntryInline(admin.TabularInline):
    """Inline for Habit Entries."""
    model = HabitEntry
    extra = 0
    fields = ['date', 'completed', 'duration_minutes', 'count_value', 'target_value', 'session_number', 'notes']
    readonly_fields = ['created_at']


@admin.register(HabitGoal)
class HabitGoalAdmin(admin.ModelAdmin):
    """Admin for Habit Goals with measurement types."""
    list_display = [
        'name', 'user', 'measurement_type', 'frequency_type',
        'status', 'start_date', 'end_date', 'target_value', 'target_unit',
    ]
    list_filter = ['measurement_type', 'frequency_type', 'status']
    search_fields = ['name', 'purpose', 'user__email']
    raw_id_fields = ['user', 'annual_direction']
    date_hierarchy = 'start_date'
    inlines = [HabitEntryInline]

    def get_queryset(self, request):
        return HabitGoal.all_objects.all()


@admin.register(HabitEntry)
class HabitEntryAdmin(admin.ModelAdmin):
    """Admin for Habit Entries (Goal Logs)."""
    list_display = [
        'goal', 'date', 'completed', 'session_number',
        'duration_minutes', 'count_value', 'target_value', 'created_at',
    ]
    list_filter = ['completed', 'date']
    search_fields = ['goal__name', 'notes']
    raw_id_fields = ['goal']
    date_hierarchy = 'date'


@admin.register(GoalInsight)
class GoalInsightAdmin(admin.ModelAdmin):
    """Admin for Goal Insights."""
    list_display = ['goal', 'insight_type', 'title', 'is_dismissed', 'is_applied', 'created_at']
    list_filter = ['insight_type', 'is_dismissed', 'is_applied']
    search_fields = ['title', 'message', 'goal__name']
    raw_id_fields = ['goal']
