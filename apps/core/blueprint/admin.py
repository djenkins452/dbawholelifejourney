"""
Whole Life Journey - Blueprint Admin Configuration

Project: Whole Life Journey
Path: apps/core/blueprint/admin.py
Purpose: Django admin interface for blueprint models

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.contrib import admin

from .models import (
    ArchitecturePlan,
    DriftEvent,
    DriftScore,
    InterventionLog,
    NonNegotiable,
    PersonalOperatingBlueprint,
    ScheduledBlock,
)


class NonNegotiableInline(admin.TabularInline):
    model = NonNegotiable
    extra = 0
    fields = [
        'behavior_key', 'display_name', 'pillar', 'frequency',
        'min_duration_minutes', 'is_active', 'sort_order',
    ]


@admin.register(PersonalOperatingBlueprint)
class PersonalOperatingBlueprintAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'operating_style', 'interruption_tolerance',
        'auto_architect_enabled', 'version', 'updated_at',
    ]
    list_filter = ['operating_style', 'interruption_tolerance', 'auto_architect_enabled']
    search_fields = ['user__email']
    raw_id_fields = ['user']
    readonly_fields = ['version', 'created_at', 'updated_at', 'last_architecture_run_at']
    inlines = [NonNegotiableInline]

    fieldsets = (
        ('User', {
            'fields': ('user',),
        }),
        ('Operating Style', {
            'fields': (
                'operating_style', 'persona_id', 'interruption_tolerance',
                'override_policy',
            ),
        }),
        ('Identity & Priority', {
            'fields': ('tier1_protected_behaviors', 'pillars_ranked'),
        }),
        ('Schedule & Capacity', {
            'fields': (
                'auto_architect_enabled', 'sleep_target_minutes',
                'wake_time_policy', 'preferred_architecture_time',
            ),
        }),
        ('Module Flags (Auto-Synced)', {
            'fields': ('module_flags_snapshot', 'sub_feature_flags_snapshot'),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('version', 'last_architecture_run_at', 'created_at', 'updated_at'),
        }),
    )


@admin.register(NonNegotiable)
class NonNegotiableAdmin(admin.ModelAdmin):
    list_display = [
        'display_name', 'behavior_key', 'pillar', 'frequency',
        'min_duration_minutes', 'is_active', 'blueprint',
    ]
    list_filter = ['pillar', 'frequency', 'is_active']
    search_fields = ['behavior_key', 'display_name', 'blueprint__user__email']
    raw_id_fields = ['blueprint']


class ScheduledBlockInline(admin.TabularInline):
    model = ScheduledBlock
    extra = 0
    fields = [
        'start_time', 'end_time', 'title', 'tier', 'source',
        'is_locked', 'is_completed',
    ]


@admin.register(ArchitecturePlan)
class ArchitecturePlanAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'date', 'status', 'generation_trigger',
        'recommended_wake_time', 'created_at',
    ]
    list_filter = ['status', 'generation_trigger', 'date']
    search_fields = ['user__email']
    raw_id_fields = ['user']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ScheduledBlockInline]


@admin.register(DriftEvent)
class DriftEventAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'drift_type', 'date', 'tier', 'severity',
        'is_acknowledged', 'occurred_at',
    ]
    list_filter = ['drift_type', 'tier', 'is_acknowledged', 'date']
    search_fields = ['user__email']
    raw_id_fields = ['user']
    readonly_fields = ['created_at']


@admin.register(DriftScore)
class DriftScoreAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'date', 'score', 'event_count',
        'drift_probability_24h', 'drift_probability_72h',
    ]
    list_filter = ['date']
    search_fields = ['user__email']
    raw_id_fields = ['user']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(InterventionLog)
class InterventionLogAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'level', 'trigger_type', 'behavior_key',
        'user_response', 'delivered_via', 'created_at',
    ]
    list_filter = ['level', 'trigger_type', 'user_response']
    search_fields = ['user__email', 'trigger_type']
    raw_id_fields = ['user']
    readonly_fields = ['created_at']
