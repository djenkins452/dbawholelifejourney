"""
Whole Life Journey - User Admin Configuration

Project: Whole Life Journey
Path: apps/users/admin.py
Purpose: Django admin interface configuration for user-related models

Description:
    Configures the Django admin interface for managing users, their
    preferences, and terms acceptance records. Provides inline editing
    of user preferences directly on the user admin page.

Registered Models:
    - UserAdmin: Custom user admin with preferences inline
    - UserPreferencesAdmin: Standalone preferences management
    - TermsAcceptanceAdmin: Terms acceptance history

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    AllowedInternationalEmail,
    DisposableEmailDomain,
    ExternalLink,
    IPBlocklist,
    SignupAttempt,
    TermsAcceptance,
    User,
    UserPreferences,
)


class UserPreferencesInline(admin.StackedInline):
    model = UserPreferences
    can_delete = False
    verbose_name_plural = "Preferences"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "first_name", "last_name", "is_staff", "is_active", "date_joined"]
    list_filter = ["is_staff", "is_active", "date_joined"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["-date_joined"]
    inlines = [UserPreferencesInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important Dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2"),
        }),
    )


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ["user", "theme", "faith_enabled", "ai_enabled", "has_completed_onboarding"]
    list_filter = ["theme", "faith_enabled", "ai_enabled", "has_completed_onboarding"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]


@admin.register(TermsAcceptance)
class TermsAcceptanceAdmin(admin.ModelAdmin):
    list_display = ["user", "terms_version", "accepted_at", "ip_address"]
    list_filter = ["terms_version", "accepted_at"]
    search_fields = ["user__email"]
    readonly_fields = ["user", "terms_version", "accepted_at", "ip_address", "user_agent"]
    raw_id_fields = ["user"]


@admin.register(SignupAttempt)
class SignupAttemptAdmin(admin.ModelAdmin):
    """
    Admin for viewing signup attempts. Read-only to preserve audit trail.
    """

    list_display = [
        "id_short",
        "status",
        "risk_level",
        "risk_score",
        "block_reason",
        "created_at",
    ]
    list_filter = ["status", "risk_level", "block_reason", "created_at"]
    search_fields = ["email_hash", "ip_hash"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    # All fields are read-only - this is an audit log
    readonly_fields = [
        "id",
        "email_hash",
        "ip_hash",
        "fingerprint_hash",
        "user_agent",
        "country_code",
        "risk_score",
        "risk_level",
        "captcha_score",
        "ip_reputation_score",
        "email_risk_score",
        "behavioral_score",
        "device_score",
        "status",
        "block_reason",
        "captcha_verified",
        "phone_verified",
        "email_verified",
        "created_at",
        "completed_at",
        "user",
    ]

    def id_short(self, obj):
        """Display shortened UUID for readability."""
        return str(obj.id)[:8] + "..."

    id_short.short_description = "ID"

    def has_add_permission(self, request):
        """Prevent manual creation of signup attempts."""
        return False

    def has_change_permission(self, request, obj=None):
        """Allow viewing but not editing."""
        return True

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of audit records."""
        return False


@admin.register(IPBlocklist)
class IPBlocklistAdmin(admin.ModelAdmin):
    """
    Admin for managing IP blocklist entries.
    """

    list_display = [
        "ip_address",
        "block_type",
        "reason_truncated",
        "expires_at",
        "created_at",
    ]
    list_filter = ["block_type", "created_at"]
    search_fields = ["ip_address", "reason"]
    ordering = ["-created_at"]

    def reason_truncated(self, obj):
        """Display truncated reason for list view."""
        if obj.reason and len(obj.reason) > 50:
            return obj.reason[:50] + "..."
        return obj.reason or "-"

    reason_truncated.short_description = "Reason"


@admin.register(DisposableEmailDomain)
class DisposableEmailDomainAdmin(admin.ModelAdmin):
    """
    Admin for managing disposable email domain blocklist.
    """

    list_display = ["domain", "source", "confirmed", "added_at"]
    list_filter = ["source", "confirmed"]
    search_fields = ["domain"]
    ordering = ["domain"]
    actions = ["mark_confirmed", "mark_unconfirmed"]

    @admin.action(description="Mark selected domains as confirmed")
    def mark_confirmed(self, request, queryset):
        updated = queryset.update(confirmed=True)
        self.message_user(request, f"{updated} domain(s) marked as confirmed.")

    @admin.action(description="Mark selected domains as unconfirmed")
    def mark_unconfirmed(self, request, queryset):
        updated = queryset.update(confirmed=False)
        self.message_user(request, f"{updated} domain(s) marked as unconfirmed.")


@admin.register(AllowedInternationalEmail)
class AllowedInternationalEmailAdmin(admin.ModelAdmin):
    """
    Admin for managing international email whitelist.

    Add email addresses here BEFORE international friends/family attempt to sign up.
    This allows them to bypass the USA-only geo-blocking.
    """

    list_display = ["email", "name", "added_at", "used_at", "added_by"]
    list_filter = ["added_at", "used_at"]
    search_fields = ["email", "name", "note"]
    ordering = ["-added_at"]
    readonly_fields = ["used_at"]
    raw_id_fields = ["added_by"]

    fieldsets = (
        (None, {
            "fields": ("email", "name"),
            "description": "Add the email address of someone outside the USA who you want to allow to sign up.",
        }),
        ("Details", {
            "fields": ("note", "added_by"),
            "classes": ("collapse",),
        }),
        ("Status", {
            "fields": ("used_at",),
            "classes": ("collapse",),
            "description": "This is automatically set when the email is used to sign up.",
        }),
    )

    def save_model(self, request, obj, form, change):
        """Automatically set added_by to the current admin user."""
        if not change:  # Only on create
            obj.added_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ExternalLink)
class ExternalLinkAdmin(admin.ModelAdmin):
    """
    Admin for user Quick Links with deep linking support.
    """
    list_display = [
        "name", "user", "url", "mobile_app_url", "category",
        "usage_count", "sort_order", "created_at",
    ]
    list_filter = ["category", "created_at"]
    search_fields = ["name", "url", "mobile_app_url", "user__email"]
    readonly_fields = ["usage_count", "created_at"]
    ordering = ["-created_at"]
    fieldsets = (
        (None, {
            "fields": ("user", "name", "url", "sort_order"),
        }),
        ("Mobile Deep Linking", {
            "fields": ("mobile_app_url",),
            "description": (
                "Optional: Enter a mobile app deep link URL (e.g., 'chase://', "
                "'bofa://app'). On mobile devices, this URL is attempted first. "
                "If the app is not installed, falls back to the standard web URL."
            ),
        }),
        ("Display", {
            "fields": ("icon", "category", "open_in_new_tab"),
        }),
        ("Stats", {
            "fields": ("usage_count", "created_at"),
        }),
    )
