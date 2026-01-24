"""
Mobile App Admin Configuration

Admin interfaces for:
- MobileDevice: View/manage registered devices
- MobileAPIToken: View tokens (cannot see actual token values)
- HealthIngestionRun: Audit log for health data submissions
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    HealthIngestionRun,
    MobileAPIToken,
    MobileDevice,
    MobileTokenExchangeCode,
)


@admin.register(MobileDevice)
class MobileDeviceAdmin(admin.ModelAdmin):
    list_display = [
        "device_display",
        "user",
        "device_model",
        "os_version",
        "app_version",
        "is_active",
        "last_seen_at",
    ]
    list_filter = ["is_active", "device_model", "os_version"]
    search_fields = ["user__email", "device_name", "device_id"]
    readonly_fields = ["device_id", "created_at", "updated_at", "last_seen_at"]
    ordering = ["-last_seen_at"]

    fieldsets = [
        ("Device Info", {
            "fields": ["user", "device_id", "device_name", "device_model"]
        }),
        ("Version", {
            "fields": ["os_version", "app_version"]
        }),
        ("Status", {
            "fields": ["is_active", "last_seen_at"]
        }),
        ("Push Notifications", {
            "fields": ["push_token", "push_enabled"],
            "classes": ["collapse"],
        }),
        ("Timestamps", {
            "fields": ["created_at", "updated_at"],
            "classes": ["collapse"],
        }),
    ]

    def device_display(self, obj):
        name = obj.device_name or obj.device_model or "Unknown Device"
        return name
    device_display.short_description = "Device"


@admin.register(MobileAPIToken)
class MobileAPITokenAdmin(admin.ModelAdmin):
    list_display = [
        "token_display",
        "user",
        "device_name",
        "is_active",
        "expires_at",
        "last_used_at",
        "created_at",
    ]
    list_filter = ["is_active", "created_at"]
    search_fields = ["user__email", "device__device_name", "token_prefix"]
    readonly_fields = [
        "token_hash",
        "token_prefix",
        "created_at",
        "updated_at",
        "last_used_at",
        "created_ip",
    ]
    ordering = ["-created_at"]

    fieldsets = [
        ("Token Info", {
            "fields": ["user", "device", "token_prefix"]
        }),
        ("Status", {
            "fields": ["is_active", "expires_at", "last_used_at"]
        }),
        ("Audit", {
            "fields": ["created_ip", "created_at", "updated_at"],
            "classes": ["collapse"],
        }),
        ("Security (Read Only)", {
            "fields": ["token_hash"],
            "classes": ["collapse"],
        }),
    ]

    def token_display(self, obj):
        status_color = "green" if obj.is_active else "red"
        return format_html(
            '<span style="color: {};">{}</span>...',
            status_color,
            obj.token_prefix,
        )
    token_display.short_description = "Token"

    def device_name(self, obj):
        return obj.device.device_name or obj.device.device_model or "Unknown"
    device_name.short_description = "Device"


@admin.register(HealthIngestionRun)
class HealthIngestionRunAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "status_display",
        "metrics_summary",
        "payload_size_bytes",
        "duration",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["user__email"]
    readonly_fields = [
        "user",
        "device",
        "token",
        "status",
        "request_ip",
        "request_timestamp",
        "payload_size_bytes",
        "metrics_received",
        "metrics_created",
        "metrics_updated",
        "metrics_skipped",
        "started_at",
        "completed_at",
        "error_message",
        "validation_errors",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    fieldsets = [
        ("Request", {
            "fields": [
                "user",
                "device",
                "token",
                "request_ip",
                "request_timestamp",
                "payload_size_bytes",
            ]
        }),
        ("Results", {
            "fields": [
                "status",
                "metrics_received",
                "metrics_created",
                "metrics_updated",
                "metrics_skipped",
            ]
        }),
        ("Timing", {
            "fields": ["started_at", "completed_at", "created_at", "updated_at"]
        }),
        ("Errors", {
            "fields": ["error_message", "validation_errors"],
            "classes": ["collapse"],
        }),
    ]

    def status_display(self, obj):
        colors = {
            "pending": "orange",
            "processing": "blue",
            "completed": "green",
            "partial": "yellow",
            "failed": "red",
        }
        return format_html(
            '<span style="color: {};">{}</span>',
            colors.get(obj.status, "gray"),
            obj.get_status_display(),
        )
    status_display.short_description = "Status"

    def metrics_summary(self, obj):
        return f"+{obj.metrics_created} / ~{obj.metrics_updated} / -{obj.metrics_skipped}"
    metrics_summary.short_description = "Created/Updated/Skipped"

    def duration(self, obj):
        if obj.started_at and obj.completed_at:
            delta = obj.completed_at - obj.started_at
            return f"{delta.total_seconds():.2f}s"
        return "-"
    duration.short_description = "Duration"


@admin.register(MobileTokenExchangeCode)
class MobileTokenExchangeCodeAdmin(admin.ModelAdmin):
    list_display = [
        "code_prefix",
        "user",
        "is_used",
        "expires_at",
        "created_at",
    ]
    list_filter = ["is_used", "created_at"]
    search_fields = ["user__email"]
    readonly_fields = [
        "code",
        "is_used",
        "used_at",
        "used_by_device_id",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    def code_prefix(self, obj):
        return f"{obj.code[:8]}..."
    code_prefix.short_description = "Code"
