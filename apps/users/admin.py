"""
Users Admin Configuration
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import TermsAcceptance, User, UserPreferences


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
