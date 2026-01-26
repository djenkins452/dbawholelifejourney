"""
Brain Training Admin Configuration

Admin interfaces for managing brain training games, challenges, and viewing stats.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Game,
    Challenge,
    GameSession,
    DailyStats,
    UserGameStats,
    UserOverallStats,
    ChallengeQueue,
)


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    """Admin for Brain Training Games."""

    list_display = [
        'name',
        'slug',
        'category',
        'is_active',
        'sort_order',
        'challenge_count',
        'created_at',
    ]
    list_filter = ['is_active', 'category']
    search_fields = ['name', 'slug', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['sort_order', 'name']

    fieldsets = [
        (None, {
            'fields': ['name', 'slug', 'description', 'category']
        }),
        ('Display', {
            'fields': ['icon_svg', 'color_primary', 'color_secondary']
        }),
        ('Configuration', {
            'fields': ['difficulty_levels', 'default_difficulty', 'is_active', 'sort_order']
        }),
    ]

    def challenge_count(self, obj):
        return obj.challenges.count()
    challenge_count.short_description = 'Challenges'


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    """Admin for Challenges/Puzzles."""

    list_display = [
        'challenge_id_short',
        'game',
        'difficulty',
        'completion_count',
        'attempt_count',
        'avg_time_display',
        'created_at',
    ]
    list_filter = ['game', 'difficulty', 'is_pregenerated']
    search_fields = ['challenge_id']
    readonly_fields = [
        'challenge_id',
        'solution_hash',
        'average_time_seconds',
        'completion_count',
        'attempt_count',
        'created_at',
        'updated_at',
    ]
    ordering = ['-created_at']

    fieldsets = [
        (None, {
            'fields': ['game', 'challenge_id', 'difficulty']
        }),
        ('Puzzle Data', {
            'fields': ['puzzle_data', 'solution_data', 'solution_hash'],
            'classes': ['collapse'],
        }),
        ('Metrics', {
            'fields': [
                'completion_count',
                'attempt_count',
                'average_time_seconds',
                'is_pregenerated',
            ]
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse'],
        }),
    ]

    def challenge_id_short(self, obj):
        return obj.challenge_id[:12] + '...'
    challenge_id_short.short_description = 'Challenge ID'

    def avg_time_display(self, obj):
        if obj.average_time_seconds:
            mins = obj.average_time_seconds // 60
            secs = obj.average_time_seconds % 60
            return f"{mins}:{secs:02d}"
        return "-"
    avg_time_display.short_description = 'Avg Time'


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    """Admin for Game Sessions."""

    list_display = [
        'user_email',
        'game_name',
        'difficulty',
        'status',
        'score',
        'time_display',
        'mistakes',
        'hints_used',
        'started_at',
    ]
    list_filter = ['status', 'challenge__game', 'challenge__difficulty', 'platform']
    search_fields = ['user__email', 'challenge__challenge_id']
    readonly_fields = [
        'user',
        'challenge',
        'started_at',
        'completed_at',
        'time_spent_seconds',
        'status',
        'score',
        'mistakes',
        'hints_used',
        'platform',
        'created_at',
        'updated_at',
    ]
    ordering = ['-started_at']

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def game_name(self, obj):
        return obj.challenge.game.name
    game_name.short_description = 'Game'

    def difficulty(self, obj):
        return obj.challenge.get_difficulty_display()
    difficulty.short_description = 'Difficulty'

    def time_display(self, obj):
        mins = obj.time_spent_seconds // 60
        secs = obj.time_spent_seconds % 60
        return f"{mins}:{secs:02d}"
    time_display.short_description = 'Time'


@admin.register(DailyStats)
class DailyStatsAdmin(admin.ModelAdmin):
    """Admin for Daily Stats."""

    list_display = [
        'user_email',
        'game_name',
        'date',
        'sessions_completed',
        'total_score',
        'avg_time_display',
        'total_mistakes',
    ]
    list_filter = ['game', 'date']
    search_fields = ['user__email']
    date_hierarchy = 'date'
    ordering = ['-date']
    readonly_fields = [
        'user',
        'game',
        'date',
        'sessions_started',
        'sessions_completed',
        'total_time_seconds',
        'best_time_seconds',
        'total_score',
        'best_score',
        'total_mistakes',
        'total_hints',
        'easy_completed',
        'medium_completed',
        'hard_completed',
        'expert_completed',
    ]

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def game_name(self, obj):
        return obj.game.name
    game_name.short_description = 'Game'

    def avg_time_display(self, obj):
        avg = obj.average_time_seconds
        if avg:
            mins = avg // 60
            secs = avg % 60
            return f"{mins}:{secs:02d}"
        return "-"
    avg_time_display.short_description = 'Avg Time'


@admin.register(UserGameStats)
class UserGameStatsAdmin(admin.ModelAdmin):
    """Admin for User Game Stats."""

    list_display = [
        'user_email',
        'game_name',
        'total_completed',
        'best_score',
        'current_streak',
        'longest_streak',
        'last_played_date',
    ]
    list_filter = ['game']
    search_fields = ['user__email']
    ordering = ['-total_completed']

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def game_name(self, obj):
        return obj.game.name
    game_name.short_description = 'Game'


@admin.register(UserOverallStats)
class UserOverallStatsAdmin(admin.ModelAdmin):
    """Admin for User Overall Stats."""

    list_display = [
        'user_email',
        'total_completed',
        'total_minutes',
        'current_streak',
        'longest_streak',
        'favorite_game',
        'last_played_date',
    ]
    search_fields = ['user__email']
    ordering = ['-total_completed']

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def total_minutes(self, obj):
        return obj.total_minutes_trained
    total_minutes.short_description = 'Minutes Trained'


@admin.register(ChallengeQueue)
class ChallengeQueueAdmin(admin.ModelAdmin):
    """Admin for Challenge Queue."""

    list_display = [
        'user_email',
        'game_name',
        'position',
        'challenge_id_short',
        'added_at',
    ]
    list_filter = ['game']
    search_fields = ['user__email']
    ordering = ['user', 'game', 'position']

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def game_name(self, obj):
        return obj.game.name
    game_name.short_description = 'Game'

    def challenge_id_short(self, obj):
        return obj.challenge.challenge_id[:12] + '...'
    challenge_id_short.short_description = 'Challenge'
