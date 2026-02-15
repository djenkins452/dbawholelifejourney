"""
SLCME Database Models — Persistent storage for learned meanings and context.

Three models:
- LearnedMapping: Phrase → meaning associations learned from user clarification
- ContextSnapshot: Current user context (what page, what entry they're viewing)
- ClarificationLog: Audit trail of all clarification exchanges
"""

from django.conf import settings
from django.db import models


class LearnedMapping(models.Model):
    """
    Stores a learned association between a user phrase and its resolved meaning.

    Example: "the scripture" → meaning_type="scripture", meaning_identifier="John 3:16"
    Confidence grows with each successful reuse.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learned_mappings",
    )
    phrase = models.CharField(
        max_length=255,
        help_text="The user's original phrase (e.g., 'the scripture', 'my goal')",
    )
    meaning_type = models.CharField(
        max_length=100,
        help_text="Category of meaning (e.g., 'scripture', 'goal', 'health_entry')",
    )
    meaning_identifier = models.CharField(
        max_length=255,
        help_text="Specific identifier (e.g., 'John 3:16', 'goal_id:42')",
    )
    confidence_score = models.FloatField(
        default=0.8,
        help_text="0.0 to 1.0 — grows with usage, must meet threshold to auto-use",
    )
    usage_count = models.IntegerField(
        default=1,
        help_text="Number of times this mapping has been used",
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this mapping was applied",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Soft disable without deleting",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_learned_mapping"
        indexes = [
            models.Index(fields=["user", "phrase"], name="idx_mapping_user_phrase"),
            models.Index(
                fields=["user", "confidence_score"],
                name="idx_mapping_user_confidence",
            ),
            models.Index(
                fields=["user", "meaning_type"],
                name="idx_mapping_user_type",
            ),
        ]
        ordering = ["-confidence_score", "-usage_count"]

    def __str__(self):
        return f"{self.phrase} → {self.meaning_type}:{self.meaning_identifier} ({self.confidence_score:.2f})"


class ContextSnapshot(models.Model):
    """
    Tracks the user's current context — what they're looking at right now.

    Examples:
    - context_type="scripture_page", context_identifier="John 3"
    - context_type="health_entry", context_identifier="weight_entry:123"
    - context_type="goal", context_identifier="goal:42"
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="context_snapshots",
    )
    context_type = models.CharField(
        max_length=100,
        help_text="Type of context (e.g., 'scripture_page', 'health_entry', 'goal')",
    )
    context_identifier = models.CharField(
        max_length=255,
        help_text="Specific identifier for this context",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context data (page title, entry details, etc.)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_context_snapshot"
        indexes = [
            models.Index(
                fields=["user", "context_type", "-created_at"],
                name="idx_ctx_user_type_date",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.context_type}:{self.context_identifier}"


class ClarificationLog(models.Model):
    """
    Audit trail of every clarification exchange between user and AI.

    This is write-only for audit purposes — never delete these records.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="clarification_logs",
    )
    original_input = models.TextField(
        help_text="What the user originally said",
    )
    clarification_question = models.TextField(
        help_text="What the AI asked for clarification",
    )
    user_response = models.TextField(
        help_text="The user's clarifying response",
    )
    resolved_meaning = models.TextField(
        help_text="The final resolved meaning after clarification",
    )
    learned_mapping = models.ForeignKey(
        LearnedMapping,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clarification_logs",
        help_text="The mapping created/updated from this clarification",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_clarification_log"
        indexes = [
            models.Index(
                fields=["user", "-created_at"],
                name="idx_clarify_user_date",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Clarification: {self.original_input[:50]}..."
