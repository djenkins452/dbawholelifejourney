"""
IOCD — Admin registration (read-only for diagnostics, editable for cadence config).
"""

from django.contrib import admin

from apps.core.ai_observability.models import (
    AdminIntervention,
    DecisionRecord,
    EngineExpectedCadence,
    EngineHeartbeat,
    EngineRun,
    EngineSpan,
    IntelligenceMetricsSnapshot,
    OpsAnomaly,
    OpsNarrativeSnapshot,
)


@admin.register(IntelligenceMetricsSnapshot)
class IntelligenceMetricsSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "snapshot_date",
        "guidance_total",
        "guidance_action_rate",
        "deliveries_success_rate",
        "avg_usefulness_score",
        "active_users_count",
    ]
    list_filter = ["snapshot_date"]
    readonly_fields = [
        "snapshot_date",
        "guidance_total",
        "guidance_acknowledged",
        "guidance_dismissed",
        "guidance_acted",
        "guidance_expired",
        "guidance_acceptance_rate",
        "guidance_action_rate",
        "guidance_avg_response_seconds",
        "predictions_total",
        "predictions_active",
        "predictions_expired",
        "predictions_avg_confidence",
        "deliveries_total",
        "deliveries_sent",
        "deliveries_skipped",
        "deliveries_failed",
        "deliveries_success_rate",
        "deliveries_by_channel",
        "active_users_count",
        "avg_responsiveness_score",
        "avg_usefulness_score",
        "total_suppressed",
        "persona_effectiveness_scores",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(EngineRun)
class EngineRunAdmin(admin.ModelAdmin):
    list_display = [
        "engine_name",
        "phase",
        "status",
        "duration_ms",
        "user_id",
        "trace_id",
        "started_at",
    ]
    list_filter = ["engine_name", "status", "phase"]
    search_fields = ["trace_id", "error_message"]
    readonly_fields = [
        "trace_id",
        "engine_name",
        "phase",
        "started_at",
        "ended_at",
        "duration_ms",
        "status",
        "error_type",
        "error_message",
        "input_fingerprint",
        "output_fingerprint",
        "user_id",
        "metadata",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EngineSpan)
class EngineSpanAdmin(admin.ModelAdmin):
    list_display = ["engine_name", "span_name", "status", "duration_ms", "trace_id", "started_at"]
    list_filter = ["engine_name", "status"]
    search_fields = ["trace_id"]
    readonly_fields = [
        "trace_id",
        "engine_name",
        "span_name",
        "started_at",
        "ended_at",
        "duration_ms",
        "status",
        "metadata",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DecisionRecord)
class DecisionRecordAdmin(admin.ModelAdmin):
    list_display = [
        "engine_name",
        "decision_type",
        "decision",
        "user_id",
        "confidence",
        "trace_id",
        "created_at",
    ]
    list_filter = ["engine_name", "decision_type"]
    search_fields = ["trace_id", "decision", "rationale"]
    readonly_fields = [
        "trace_id",
        "engine_name",
        "decision_type",
        "decision",
        "rationale",
        "inputs_summary",
        "affected_items",
        "user_id",
        "confidence",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# --- Vegas Ops Wall v2 Models ---


@admin.register(EngineExpectedCadence)
class EngineExpectedCadenceAdmin(admin.ModelAdmin):
    list_display = [
        "engine_name",
        "expected_interval_seconds",
        "expected_jitter_seconds",
        "is_enabled",
    ]
    list_filter = ["is_enabled"]
    search_fields = ["engine_name"]


@admin.register(EngineHeartbeat)
class EngineHeartbeatAdmin(admin.ModelAdmin):
    list_display = [
        "engine_name",
        "status",
        "observed_at",
        "last_run_at",
        "lateness_seconds",
    ]
    list_filter = ["engine_name", "status"]
    readonly_fields = [
        "engine_name",
        "observed_at",
        "status",
        "last_run_at",
        "next_expected_at",
        "lateness_seconds",
        "metadata",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AdminIntervention)
class AdminInterventionAdmin(admin.ModelAdmin):
    list_display = [
        "action_type",
        "engine_name",
        "admin_user",
        "result_status",
        "created_at",
    ]
    list_filter = ["action_type", "result_status"]
    search_fields = ["engine_name", "trace_id", "notes"]
    readonly_fields = [
        "created_at",
        "admin_user",
        "action_type",
        "engine_name",
        "trace_id",
        "notes",
        "result_status",
        "result_detail",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OpsAnomaly)
class OpsAnomalyAdmin(admin.ModelAdmin):
    list_display = [
        "severity",
        "anomaly_type",
        "engine_name",
        "is_active",
        "created_at",
    ]
    list_filter = ["severity", "anomaly_type", "is_active"]
    search_fields = ["engine_name", "summary"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "severity",
        "engine_name",
        "anomaly_type",
        "summary",
        "evidence",
        "suggested_actions",
        "is_active",
        "resolved_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OpsNarrativeSnapshot)
class OpsNarrativeSnapshotAdmin(admin.ModelAdmin):
    list_display = ["posture", "headline", "created_at"]
    list_filter = ["posture"]
    readonly_fields = [
        "created_at",
        "posture",
        "headline",
        "bullets_now",
        "recommendations",
        "watching_next",
        "supporting_metrics",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
