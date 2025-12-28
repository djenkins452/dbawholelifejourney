"""
Core Admin Configuration
"""

from django.contrib import admin

from .models import Category, ReleaseNote, Tag, UserReleaseNoteView


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "order", "icon"]
    list_editable = ["order"]
    prepopulated_fields = {"slug": ("name",)}
    ordering = ["order", "name"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "color", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["name", "user__email"]
    raw_id_fields = ["user"]


@admin.register(ReleaseNote)
class ReleaseNoteAdmin(admin.ModelAdmin):
    """
    Admin for managing What's New / Release Note entries.

    Use this to add new entries when features are deployed.
    """

    list_display = [
        "title",
        "entry_type",
        "release_date",
        "is_published",
        "is_major",
        "created_at",
    ]
    list_filter = ["entry_type", "is_published", "is_major", "release_date"]
    list_editable = ["is_published", "is_major"]
    search_fields = ["title", "description"]
    ordering = ["-release_date", "-created_at"]
    date_hierarchy = "release_date"

    fieldsets = (
        (None, {
            "fields": ("title", "description", "entry_type"),
        }),
        ("Publishing", {
            "fields": ("release_date", "is_published", "is_major"),
        }),
        ("Optional", {
            "fields": ("version", "learn_more_url"),
            "classes": ("collapse",),
        }),
    )


@admin.register(UserReleaseNoteView)
class UserReleaseNoteViewAdmin(admin.ModelAdmin):
    """
    Admin for viewing user's What's New view history.

    Read-only - shows when users last dismissed the What's New popup.
    """

    list_display = ["user", "last_viewed_at"]
    list_filter = ["last_viewed_at"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    readonly_fields = ["user", "last_viewed_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
