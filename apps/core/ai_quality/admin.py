"""
ICQG — Admin registration (read-only).
"""

from django.contrib import admin

from apps.core.ai_quality.quality_models import (
    QualityMetricAggregate,
    QualitySuppressionRecord,
)


@admin.register(QualitySuppressionRecord)
class QualitySuppressionRecordAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "signature_hash_short",
        "last_priority",
        "count",
        "suppressed_until",
        "last_seen_at",
    ]
    list_filter = ["last_priority", "suppressed_until"]
    search_fields = ["user__email", "signature_hash"]
    readonly_fields = [
        "user",
        "signature_hash",
        "suppressed_until",
        "last_seen_at",
        "last_priority",
        "count",
        "created_at",
    ]

    def signature_hash_short(self, obj):
        return obj.signature_hash[:16] + "..."
    signature_hash_short.short_description = "Signature"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(QualityMetricAggregate)
class QualityMetricAggregateAdmin(admin.ModelAdmin):
    list_display = [
        "week_start",
        "rule_type",
        "domain",
        "delivered_count",
        "acted_count",
        "dismissed_count",
        "usefulness_score",
    ]
    list_filter = ["week_start", "domain", "rule_type"]
    search_fields = ["rule_type", "domain"]
    readonly_fields = [
        "week_start",
        "rule_type",
        "domain",
        "delivered_count",
        "acted_count",
        "dismissed_count",
        "snoozed_count",
        "acknowledged_count",
        "suppressed_count",
        "avg_response_seconds",
        "usefulness_score",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
