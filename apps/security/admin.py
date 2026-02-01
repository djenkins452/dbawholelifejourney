# ==============================================================================
# File: apps/security/admin.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Django admin interface for security models
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-23
# ==============================================================================
"""
Security Admin Interface

Provides admin views for:
- SecurityRun: Assessment runs with scores and findings
- SecurityFinding: Individual findings with filtering and bulk actions
- SecurityTest: Test results
- AcknowledgedFinding: Risk acceptance tracking
- SecurityAuditLog: Access audit trail

NOTE: Encrypted fields show "[ENCRYPTED]" in list views to prevent
accidental exposure. Use detail view to see decrypted content.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from .models import (
    AcknowledgedFinding,
    SecurityAuditLog,
    SecurityFinding,
    SecurityRun,
    SecurityScore,
    SecurityTest,
)


# ==============================================================================
# Inline Admin Classes
# ==============================================================================

class SecurityScoreInline(admin.StackedInline):
    """Inline for SecurityScore on SecurityRun."""
    model = SecurityScore
    can_delete = False
    extra = 0
    readonly_fields = [
        'cvss_avg', 'cvss_critical_count', 'cvss_high_count',
        'cvss_medium_count', 'cvss_low_count', 'cvss_none_count',
        'securityscorecard_grade', 'bitsight_score', 'risk_score_0_100',
        'maturity_level', 'run_timestamp',
    ]


class SecurityTestInline(admin.TabularInline):
    """Inline for SecurityTest on SecurityRun."""
    model = SecurityTest
    can_delete = False
    extra = 0
    fields = ['test_id', 'category', 'title', 'result', 'duration_ms']
    readonly_fields = ['test_id', 'category', 'title', 'result', 'duration_ms']
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


class SecurityFindingInline(admin.TabularInline):
    """Inline for SecurityFinding on SecurityRun."""
    model = SecurityFinding
    can_delete = False
    extra = 0
    fields = ['finding_id', 'title', 'severity', 'cvss_score', 'is_quick_win', 'is_acknowledged']
    readonly_fields = ['finding_id', 'title', 'severity', 'cvss_score', 'is_quick_win', 'is_acknowledged']
    show_change_link = True
    ordering = ['-cvss_score']

    def has_add_permission(self, request, obj=None):
        return False


# ==============================================================================
# Filter Classes
# ==============================================================================

class SeverityFilter(admin.SimpleListFilter):
    """Filter findings by severity."""
    title = 'Severity'
    parameter_name = 'severity'

    def lookups(self, request, model_admin):
        return SecurityFinding.SEVERITY_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(severity=self.value())
        return queryset


class QuickWinFilter(admin.SimpleListFilter):
    """Filter findings by quick win status."""
    title = 'Quick Win'
    parameter_name = 'quick_win'

    def lookups(self, request, model_admin):
        return [
            ('yes', 'Quick Wins'),
            ('no', 'Not Quick Wins'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(is_quick_win=True)
        elif self.value() == 'no':
            return queryset.filter(is_quick_win=False)
        return queryset


class AcknowledgedFilter(admin.SimpleListFilter):
    """Filter findings by acknowledgment status."""
    title = 'Acknowledged'
    parameter_name = 'acknowledged'

    def lookups(self, request, model_admin):
        return [
            ('yes', 'Acknowledged'),
            ('no', 'Not Acknowledged'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(is_acknowledged=True)
        elif self.value() == 'no':
            return queryset.filter(is_acknowledged=False)
        return queryset


class FindingStatusFilter(admin.SimpleListFilter):
    """Filter findings by lifecycle status."""
    title = 'Status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return [
            ('new', 'New'),
            ('recurring', 'Recurring'),
            ('fixed', 'Fixed'),
            ('regressed', 'Regressed'),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


# ==============================================================================
# Admin Classes
# ==============================================================================

@admin.register(SecurityRun)
class SecurityRunAdmin(admin.ModelAdmin):
    """Admin for SecurityRun model."""

    list_display = [
        'run_timestamp', 'status', 'get_grade', 'get_bitsight',
        'total_findings', 'critical_findings', 'high_findings',
        'passed_tests', 'failed_tests', 'duration_seconds', 'triggered_by',
    ]
    list_filter = ['status', 'run_type', 'triggered_by']
    search_fields = ['id', 'triggered_by']
    date_hierarchy = 'run_timestamp'
    readonly_fields = [
        'id', 'run_timestamp', 'status', 'completed_at', 'duration_seconds',
        'run_type', 'triggered_by', 'total_tests', 'passed_tests', 'failed_tests',
        'total_findings', 'critical_findings', 'high_findings', 'medium_findings',
        'low_findings', 'new_findings', 'recurring_findings', 'fixed_findings',
        'regressed_findings', 'run_hash',
        # Report fields (show encrypted warning)
        'executive_summary_display', 'ciso_sleep_test_display',
        'remediation_prompt_display',
    ]
    inlines = [SecurityScoreInline, SecurityFindingInline]
    ordering = ['-run_timestamp']

    fieldsets = [
        ('Run Information', {
            'fields': [
                'id', 'run_timestamp', 'status', 'completed_at',
                'duration_seconds', 'run_type', 'triggered_by',
            ]
        }),
        ('Summary', {
            'fields': [
                ('total_tests', 'passed_tests', 'failed_tests'),
                ('total_findings', 'critical_findings', 'high_findings', 'medium_findings', 'low_findings'),
                ('new_findings', 'recurring_findings', 'fixed_findings', 'regressed_findings'),
            ]
        }),
        ('Reports', {
            'fields': ['executive_summary_display', 'ciso_sleep_test_display', 'remediation_prompt_display'],
            'classes': ['collapse'],
        }),
        ('Integrity', {
            'fields': ['run_hash'],
            'classes': ['collapse'],
        }),
    ]

    def has_add_permission(self, request):
        # Runs should be created via scanner, not admin
        return False

    def has_delete_permission(self, request, obj=None):
        # Append-only - don't allow deletion
        return False

    @admin.display(description='Grade')
    def get_grade(self, obj):
        """Display security grade with color."""
        try:
            score = obj.score
            grade = score.securityscorecard_grade
            colors = {'A': '#16a34a', 'B': '#2563eb', 'C': '#ca8a04', 'D': '#ea580c', 'F': '#dc2626'}
            color = colors.get(grade, '#6b7280')
            return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, grade)
        except SecurityScore.DoesNotExist:
            return '-'

    @admin.display(description='BitSight')
    def get_bitsight(self, obj):
        """Display BitSight score."""
        try:
            return obj.score.bitsight_score
        except SecurityScore.DoesNotExist:
            return '-'

    @admin.display(description='Executive Summary')
    def executive_summary_display(self, obj):
        """Display executive summary (decrypted)."""
        summary = obj.executive_summary
        if summary:
            return format_html('<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>', summary[:2000])
        return '-'

    @admin.display(description='CISO Sleep Test')
    def ciso_sleep_test_display(self, obj):
        """Display CISO sleep test (decrypted)."""
        ciso = obj.ciso_sleep_test
        if ciso:
            return format_html('<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>', ciso[:2000])
        return '-'

    @admin.display(description='Remediation Prompt')
    def remediation_prompt_display(self, obj):
        """Display remediation prompt (decrypted)."""
        prompt = obj.remediation_prompt
        if prompt:
            return format_html('<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>', prompt[:2000])
        return '-'


@admin.register(SecurityScore)
class SecurityScoreAdmin(admin.ModelAdmin):
    """Admin for SecurityScore model."""

    list_display = [
        'run_timestamp', 'securityscorecard_grade', 'bitsight_score',
        'risk_score_0_100', 'maturity_level', 'cvss_avg',
        'cvss_critical_count', 'cvss_high_count', 'cvss_medium_count',
    ]
    list_filter = ['securityscorecard_grade', 'maturity_level']
    search_fields = ['run__id']
    date_hierarchy = 'run_timestamp'
    readonly_fields = [
        'id', 'run', 'run_timestamp', 'cvss_avg',
        'cvss_critical_count', 'cvss_high_count', 'cvss_medium_count',
        'cvss_low_count', 'cvss_none_count',
        'securityscorecard_grade', 'bitsight_score', 'risk_score_0_100',
        'maturity_level',
    ]
    ordering = ['-run_timestamp']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SecurityTest)
class SecurityTestAdmin(admin.ModelAdmin):
    """Admin for SecurityTest model."""

    list_display = [
        'test_id', 'title', 'category', 'result_display', 'duration_ms', 'run_link',
    ]
    list_filter = ['category', 'result']
    search_fields = ['test_id', 'title', 'description']
    readonly_fields = [
        'id', 'run', 'test_id', 'category', 'title', 'description',
        'criteria', 'result', 'result_details', 'evidence_display',
        'executed_at', 'duration_ms',
    ]
    ordering = ['test_id']

    fieldsets = [
        ('Test Information', {
            'fields': ['id', 'run', 'test_id', 'category', 'title', 'description']
        }),
        ('Criteria & Result', {
            'fields': ['criteria', 'result', 'result_details']
        }),
        ('Evidence', {
            'fields': ['evidence_display'],
            'classes': ['collapse'],
        }),
        ('Timing', {
            'fields': ['executed_at', 'duration_ms']
        }),
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Result')
    def result_display(self, obj):
        """Display result with color coding."""
        colors = {
            'pass': '#16a34a',
            'fail': '#dc2626',
            'unknown': '#ca8a04',
            'skipped': '#6b7280',
        }
        color = colors.get(obj.result, '#6b7280')
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.result.upper())

    @admin.display(description='Run')
    def run_link(self, obj):
        """Link to parent run."""
        url = reverse('admin:security_securityrun_change', args=[obj.run.id])
        return format_html('<a href="{}">{}</a>', url, obj.run.run_timestamp.strftime('%Y-%m-%d %H:%M'))

    @admin.display(description='Evidence')
    def evidence_display(self, obj):
        """Display evidence (decrypted)."""
        import json
        evidence = obj.evidence
        if evidence:
            return format_html('<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                             json.dumps(evidence, indent=2)[:3000])
        return '-'


@admin.register(SecurityFinding)
class SecurityFindingAdmin(admin.ModelAdmin):
    """Admin for SecurityFinding model."""

    list_display = [
        'finding_id', 'title', 'severity_display', 'cvss_score',
        'status_display', 'is_quick_win_display', 'is_acknowledged_display',
        'remediation_effort', 'run_link',
    ]
    list_filter = [SeverityFilter, FindingStatusFilter, QuickWinFilter, AcknowledgedFilter, 'remediation_effort']
    search_fields = ['finding_id', 'title', 'finding_key']
    readonly_fields = [
        'id', 'run', 'test', 'finding_id', 'title',
        'severity', 'likelihood', 'impact', 'cvss_vector', 'cvss_score',
        'description_display', 'risk_reasoning_display', 'evidence_display',
        'affected_components_display', 'recommendations_display',
        'validation_steps_display',
        'is_quick_win', 'remediation_effort',
        'finding_key', 'is_acknowledged', 'acknowledgment_justification',
        'status', 'first_seen_run_id', 'occurrence_count',
    ]
    ordering = ['-cvss_score', 'finding_id']
    actions = ['mark_as_quick_win', 'unmark_as_quick_win']

    fieldsets = [
        ('Finding Information', {
            'fields': ['id', 'run', 'test', 'finding_id', 'title', 'finding_key']
        }),
        ('Severity & Scoring', {
            'fields': [
                ('severity', 'likelihood', 'impact'),
                ('cvss_vector', 'cvss_score'),
            ]
        }),
        ('Status Tracking', {
            'fields': [('status', 'occurrence_count', 'first_seen_run_id')]
        }),
        ('Details', {
            'fields': ['description_display', 'risk_reasoning_display']
        }),
        ('Evidence & Components', {
            'fields': ['evidence_display', 'affected_components_display'],
            'classes': ['collapse'],
        }),
        ('Remediation', {
            'fields': ['recommendations_display', 'validation_steps_display', 'is_quick_win', 'remediation_effort'],
        }),
        ('Acknowledgment', {
            'fields': ['is_acknowledged', 'acknowledgment_justification'],
        }),
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Severity')
    def severity_display(self, obj):
        """Display severity with color coding."""
        colors = {
            'critical': '#dc2626',
            'high': '#ea580c',
            'medium': '#ca8a04',
            'low': '#2563eb',
            'info': '#6b7280',
        }
        color = colors.get(obj.severity, '#6b7280')
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.severity.upper())

    @admin.display(description='Quick Win', boolean=True)
    def is_quick_win_display(self, obj):
        return obj.is_quick_win

    @admin.display(description='Acknowledged', boolean=True)
    def is_acknowledged_display(self, obj):
        return obj.is_acknowledged

    @admin.display(description='Status')
    def status_display(self, obj):
        """Display status with color coding."""
        colors = {
            'new': '#2563eb',
            'recurring': '#ca8a04',
            'fixed': '#16a34a',
            'regressed': '#dc2626',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.status.upper())

    @admin.display(description='Run')
    def run_link(self, obj):
        """Link to parent run."""
        url = reverse('admin:security_securityrun_change', args=[obj.run.id])
        return format_html('<a href="{}">{}</a>', url, obj.run.run_timestamp.strftime('%Y-%m-%d %H:%M'))

    @admin.display(description='Description')
    def description_display(self, obj):
        """Display description (decrypted)."""
        desc = obj.description
        if desc:
            return format_html('<div style="white-space: pre-wrap;">{}</div>', desc[:2000])
        return '-'

    @admin.display(description='Risk Reasoning')
    def risk_reasoning_display(self, obj):
        """Display risk reasoning (decrypted)."""
        reasoning = obj.risk_reasoning
        if reasoning:
            return format_html('<div style="white-space: pre-wrap;">{}</div>', reasoning[:2000])
        return '-'

    @admin.display(description='Evidence')
    def evidence_display(self, obj):
        """Display evidence (decrypted)."""
        import json
        evidence = obj.evidence
        if evidence:
            return format_html('<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                             json.dumps(evidence, indent=2)[:3000])
        return '-'

    @admin.display(description='Affected Components')
    def affected_components_display(self, obj):
        """Display affected components (decrypted)."""
        components = obj.affected_components
        if components:
            return format_html('<ul>{}</ul>', ''.join(f'<li>{c}</li>' for c in components))
        return '-'

    @admin.display(description='Recommendations')
    def recommendations_display(self, obj):
        """Display recommendations (decrypted)."""
        from django.utils.html import escape
        from django.utils.safestring import mark_safe
        recs = obj.recommendations
        if recs:
            items = ''.join(f'<li>{escape(r)}</li>' for r in recs)
            return mark_safe(f'<ol>{items}</ol>')
        return '-'

    @admin.display(description='Validation Steps')
    def validation_steps_display(self, obj):
        """Display validation steps (decrypted)."""
        steps = obj.validation_steps
        if steps:
            return format_html('<pre style="white-space: pre-wrap;">{}</pre>', steps[:2000])
        return '-'

    @admin.action(description='Mark selected as Quick Win')
    def mark_as_quick_win(self, request, queryset):
        updated = queryset.update(is_quick_win=True)
        self.message_user(request, f'{updated} finding(s) marked as quick win.')

    @admin.action(description='Unmark selected as Quick Win')
    def unmark_as_quick_win(self, request, queryset):
        updated = queryset.update(is_quick_win=False)
        self.message_user(request, f'{updated} finding(s) unmarked as quick win.')


@admin.register(AcknowledgedFinding)
class AcknowledgedFindingAdmin(admin.ModelAdmin):
    """Admin for AcknowledgedFinding model."""

    list_display = [
        'finding_id', 'title', 'status', 'accepted_risk_level',
        'acknowledged_by', 'acknowledged_at', 'is_expired_display',
    ]
    list_filter = ['status', 'accepted_risk_level']
    search_fields = ['finding_id', 'title', 'justification', 'acknowledged_by']
    date_hierarchy = 'acknowledged_at'
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['finding_id']

    fieldsets = [
        ('Finding', {
            'fields': ['finding_id', 'title']
        }),
        ('Risk Acceptance', {
            'fields': ['status', 'accepted_risk_level', 'justification', 'mitigating_controls']
        }),
        ('Approval', {
            'fields': ['acknowledged_by', 'acknowledged_at', 'expires_at']
        }),
        ('Notes', {
            'fields': ['notes'],
            'classes': ['collapse'],
        }),
        ('Metadata', {
            'fields': ['id', 'created_at', 'updated_at'],
            'classes': ['collapse'],
        }),
    ]

    @admin.display(description='Expired', boolean=True)
    def is_expired_display(self, obj):
        return obj.is_expired


@admin.register(SecurityAuditLog)
class SecurityAuditLogAdmin(admin.ModelAdmin):
    """Admin for SecurityAuditLog model (read-only)."""

    list_display = [
        'timestamp', 'user_email', 'action', 'resource_type',
        'resource_id', 'ip_address', 'success',
    ]
    list_filter = ['action', 'success', 'resource_type']
    search_fields = ['user_email', 'ip_address', 'resource_id']
    date_hierarchy = 'timestamp'
    readonly_fields = [
        'id', 'timestamp', 'user', 'user_email', 'ip_address',
        'user_agent', 'action', 'resource_type', 'resource_id',
        'success', 'details',
    ]
    ordering = ['-timestamp']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
