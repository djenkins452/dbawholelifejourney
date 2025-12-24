"""
Journal Admin Configuration
"""

from django.contrib import admin

from .models import EntryLink, JournalEntry, JournalPrompt


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "user",
        "entry_date",
        "mood",
        "word_count",
        "status",
        "created_at",
    ]
    list_filter = ["status", "mood", "entry_date", "categories"]
    search_fields = ["title", "body", "user__email"]
    date_hierarchy = "entry_date"
    raw_id_fields = ["user", "prompt"]
    filter_horizontal = ["categories", "tags"]
    readonly_fields = ["word_count", "created_at", "updated_at", "deleted_at"]

    def get_queryset(self, request):
        # Show all entries including archived and deleted in admin
        return JournalEntry.all_objects.all()


@admin.register(JournalPrompt)
class JournalPromptAdmin(admin.ModelAdmin):
    list_display = [
        "text_preview",
        "category",
        "is_faith_specific",
        "is_active",
    ]
    list_filter = ["is_faith_specific", "is_active", "category"]
    list_editable = ["is_active"]
    search_fields = ["text", "scripture_reference"]

    def text_preview(self, obj):
        return obj.text[:60] + "..." if len(obj.text) > 60 else obj.text
    text_preview.short_description = "Prompt"


@admin.register(EntryLink)
class EntryLinkAdmin(admin.ModelAdmin):
    list_display = ["source", "target_type", "target_id", "link_type", "created_at"]
    list_filter = ["link_type", "target_type"]
    raw_id_fields = ["source"]
