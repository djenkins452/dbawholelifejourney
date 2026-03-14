"""
EAE — Admin configuration.

Read-only admin for EAE models. Decision logs and escalation events
are append-only and should never be modified.
"""
from django.contrib import admin

from apps.core.ai_eae.models import (
    EAEDecisionLog,
    EAEEscalationEvent,
    EAEOverride,
    EAEState,
    SignalSnapshot,
)


@admin.register(SignalSnapshot)
class SignalSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'date',
        'signal_type',
        'domain',
        'signal_class',
        'score',
        'confidence',
        'updated_at',
    ]
    list_filter = ['signal_type', 'domain', 'signal_class', 'date']
    search_fields = ['user__email']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-date', 'signal_type']

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EAEState)
class EAEStateAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'escalation_level',
        'drift_risk_severity',
        'primary_focus_label',
        'focus_changes_today',
        'noise_budget_used_today',
        'last_arbitration_at',
        'updated_at',
    ]
    list_filter = ['escalation_level']
    search_fields = ['user__email']
    readonly_fields = [
        'user', 'escalation_since', 'escalation_peak_drift',
        'drift_risk_severity', 'primary_focus_set_at',
        'last_arbitration_at', 'updated_at',
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EAEDecisionLog)
class EAEDecisionLogAdmin(admin.ModelAdmin):
    list_display = [
        'short_id',
        'user',
        'channel',
        'escalation_level',
        'drift_risk_severity',
        'tone_band',
        'surfaced_count',
        'suppressed_count',
        'arbitration_duration_ms',
        'created_at',
    ]
    list_filter = ['channel', 'escalation_level', 'tone_band']
    search_fields = ['user__email']
    readonly_fields = [
        'decision_id', 'user', 'channel', 'created_at',
        'escalation_level', 'drift_risk_severity', 'tone_band',
        'primary_focus_label', 'cognitive_units_json',
        'suppressed_items_json', 'total_candidates',
        'surfaced_count', 'suppressed_count', 'noise_budget_used',
        'noise_budget_max', 'override_events_json', 'reason_codes',
        'source_engines', 'arbitration_duration_ms',
    ]
    ordering = ['-created_at']

    def short_id(self, obj):
        return str(obj.decision_id)[:8]
    short_id.short_description = 'ID'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EAEOverride)
class EAEOverrideAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'signal_type',
        'override_type',
        'strike_count',
        'cooldown_until',
        'temporary_count_14d',
        'is_active',
        'updated_at',
    ]
    list_filter = ['override_type', 'strike_count']
    search_fields = ['user__email', 'signal_type']
    readonly_fields = ['created_at', 'updated_at']

    def is_active(self, obj):
        return obj.is_active
    is_active.boolean = True
    is_active.short_description = 'Active?'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EAEEscalationEvent)
class EAEEscalationEventAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'direction',
        'from_level',
        'to_level',
        'trigger_reason',
        'drift_risk_at_event',
        'created_at',
    ]
    list_filter = ['direction', 'from_level', 'to_level']
    search_fields = ['user__email', 'trigger_reason']
    readonly_fields = [
        'user', 'direction', 'from_level', 'to_level',
        'trigger_reason', 'drift_risk_at_event', 'created_at',
    ]
    ordering = ['-created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
