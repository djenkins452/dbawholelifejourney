from django.contrib import admin

from .models import DailyProgressSnapshot, GoalMomentumSnapshot, PreparedCelebration


@admin.register(GoalMomentumSnapshot)
class GoalMomentumSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "goal",
        "snapshot_date",
        "momentum_score",
        "progress_score",
        "momentum_trend",
    ]
    list_filter = ["snapshot_date", "momentum_trend"]
    search_fields = ["user__email", "goal__title"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["user", "goal"]


@admin.register(PreparedCelebration)
class PreparedCelebrationAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "celebration_type",
        "celebration_status",
        "headline",
        "generated_at",
        "expires_at",
    ]
    list_filter = ["celebration_type", "status"]
    search_fields = ["user__email", "headline"]
    readonly_fields = ["created_at", "updated_at", "generated_at"]
    raw_id_fields = ["user", "related_goal"]


@admin.register(DailyProgressSnapshot)
class DailyProgressSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "snapshot_date",
        "overall_score",
        "routines_score",
        "medicine_score",
        "tasks_score",
    ]
    list_filter = ["snapshot_date"]
    search_fields = ["user__email"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["user"]
