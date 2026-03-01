"""
Whole Life Journey - Notes Admin

Project: Whole Life Journey
Path: apps/notes/admin.py
Purpose: Admin registration for Note and NoteAttachment models
"""

from django.contrib import admin, messages

from .models import Note, NoteAttachment


class NoteAttachmentInline(admin.TabularInline):
    model = NoteAttachment
    extra = 0
    fields = ["content_type", "object_id", "created_at"]
    readonly_fields = ["created_at"]


@admin.action(description="Repair index for selected notes")
def repair_index_for_selected(modeladmin, request, queryset):
    """Rebuild attachments_text + tags_text + search_vector for selected notes."""
    count = 0
    for note in queryset.prefetch_related("attachments__content_type", "tags"):
        note.rebuild_tags_text()
        note.rebuild_attachments_text()
        note._refresh_search_vector()
        count += 1
    messages.success(request, f"Repaired index for {count} note(s).")


@admin.action(description="Refresh attachments index for selected notes")
def refresh_attachments_for_selected(modeladmin, request, queryset):
    """Rebuild attachments_text + search_vector for selected notes."""
    count = 0
    for note in queryset.prefetch_related("attachments__content_type"):
        note.rebuild_attachments_text()
        note._refresh_search_vector()
        count += 1
    messages.success(request, f"Refreshed attachments index for {count} note(s).")


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = [
        "display_title_admin",
        "user",
        "color",
        "is_pinned",
        "word_count",
        "status",
        "created_at",
    ]
    list_filter = ["status", "color", "is_pinned", "created_at"]
    search_fields = ["title", "body", "user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at", "deleted_at", "word_count", "search_vector", "tags_text", "attachments_text", "embedding_updated_at"]
    filter_horizontal = ["tags"]
    inlines = [NoteAttachmentInline]
    actions = [repair_index_for_selected, refresh_attachments_for_selected]

    def display_title_admin(self, obj):
        return obj.display_title

    display_title_admin.short_description = "Title"

    def get_queryset(self, request):
        return Note.all_objects.all()


@admin.register(NoteAttachment)
class NoteAttachmentAdmin(admin.ModelAdmin):
    list_display = ["note", "content_type", "object_id", "created_at"]
    list_filter = ["content_type"]
    raw_id_fields = ["note"]
