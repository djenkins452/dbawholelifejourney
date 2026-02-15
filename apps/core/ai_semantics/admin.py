"""
SUE -- Admin Registration.

Read-only display for inspection and debugging.
"""

from django.contrib import admin

from apps.core.ai_semantics.semantic_models import SemanticDecisionLog


@admin.register(SemanticDecisionLog)
class SemanticDecisionLogAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "short_text",
        "parsed_intent",
        "parsed_domain",
        "overall_confidence",
        "is_ambiguous",
        "was_correct",
        "created_at",
    )
    list_filter = (
        "parsed_domain",
        "is_ambiguous",
        "was_correct",
        "created_at",
    )
    search_fields = ("user__email", "raw_text", "parsed_intent")
    readonly_fields = (
        "user",
        "raw_text",
        "page_context",
        "parsed_intent",
        "parsed_domain",
        "parsed_entities",
        "parsed_time_expression",
        "overall_confidence",
        "intent_confidence",
        "entity_confidence",
        "is_ambiguous",
        "ambiguity_type",
        "clarification_question",
        "alternative_intents",
        "used_slcme",
        "used_sae",
        "used_context",
        "was_correct",
        "correction_applied",
        "created_at",
    )

    def short_text(self, obj):
        return obj.raw_text[:60] + ("..." if len(obj.raw_text) > 60 else "")

    short_text.short_description = "Input"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
