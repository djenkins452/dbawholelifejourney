"""
Phase 4 CoS — Conversational Learning Models.

UserLearnedProfile: User-visible, editable profile of learned values,
frustrations, goals, non-negotiables, and identity statements extracted
from assistant interactions.

LearningExtraction: Audit trail of individual extractions.

No hidden memory. Full transparency.
"""

from django.conf import settings
from django.db import models


class UserLearnedProfile(models.Model):
    """
    Transparent, user-visible profile of learned behavioral patterns.

    Populated by the LearningExtractor after every assistant interaction.
    User can view and edit all entries — nothing is hidden.

    Injected into assistant system prompt on next interaction.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learned_profile",
    )

    # Core learned attributes — all JSON lists of strings
    stated_values = models.JSONField(
        default=list,
        blank=True,
        help_text="Values the user has explicitly stated (e.g., 'family first', 'discipline').",
    )
    repeated_frustrations = models.JSONField(
        default=list,
        blank=True,
        help_text="Recurring frustrations across conversations.",
    )
    recurring_goals = models.JSONField(
        default=list,
        blank=True,
        help_text="Goals mentioned repeatedly.",
    )
    non_negotiables = models.JSONField(
        default=list,
        blank=True,
        help_text="Things the user has said they will never compromise on.",
    )
    relationship_priorities = models.JSONField(
        default=list,
        blank=True,
        help_text="People and relationships explicitly prioritized.",
    )
    identity_statements = models.JSONField(
        default=list,
        blank=True,
        help_text="'I am' statements the user has made.",
    )
    motivational_triggers = models.JSONField(
        default=list,
        blank=True,
        help_text="Things that energize or motivate the user.",
    )
    avoidance_patterns = models.JSONField(
        default=list,
        blank=True,
        help_text="Patterns or topics the user consistently avoids.",
    )

    # Extended recall categories (Executive Operator)
    health_concerns = models.JSONField(
        default=list,
        blank=True,
        help_text="Health issues, injuries, or physical concerns mentioned.",
    )
    life_event_mentions = models.JSONField(
        default=list,
        blank=True,
        help_text="Upcoming life events mentioned with date/context.",
    )
    commitments_made = models.JSONField(
        default=list,
        blank=True,
        help_text="Promises or commitments the user stated they would do.",
    )

    # Phase 3b: Expanded learned patterns
    explanation_preferences = models.JSONField(
        default=list,
        blank=True,
        help_text="Detected preferences for response depth: brief, detailed, etc.",
    )
    time_patterns = models.JSONField(
        default=list,
        blank=True,
        help_text="Time-of-day behavioral patterns (morning routines, evening reflections).",
    )

    # Metadata
    total_extractions = models.IntegerField(default=0)
    last_extraction_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_user_learned_profile"
        verbose_name = "User Learned Profile"
        verbose_name_plural = "User Learned Profiles"

    def __str__(self):
        return f"Learned profile for user {self.user_id} ({self.total_extractions} extractions)"

    def to_system_prompt_block(self):
        """
        Format the learned profile as a system prompt injection.

        Returns a string block that tells the LLM what it has learned
        about this user across conversations.

        Handles both legacy str items and new dict items (with confidence).
        Only includes active items with sufficient confidence.
        """
        lines = []
        lines.append("--- LEARNED USER PROFILE ---")

        _add_field(lines, "Core Values", self.stated_values, 8)
        _add_field(lines, "Non-Negotiables", self.non_negotiables, 8)
        _add_field(lines, "Identity", self.identity_statements, 5)
        _add_field(lines, "Recurring Goals", self.recurring_goals, 5)
        _add_field(lines, "Motivators", self.motivational_triggers, 5)
        _add_field(lines, "Key Relationships", self.relationship_priorities, 5)
        _add_field(lines, "Known Frustrations", self.repeated_frustrations, 5)
        _add_field(lines, "Avoidance Patterns", self.avoidance_patterns, 3)
        _add_field(lines, "Active Health Concerns", self.health_concerns, 5)
        _add_field(lines, "Upcoming Events Mentioned", self.life_event_mentions, 5)
        _add_field(lines, "Commitments Made", self.commitments_made, 5)
        _add_field(lines, "Response Preferences", self.explanation_preferences, 3)
        _add_field(lines, "Time Patterns", self.time_patterns, 5)

        if len(lines) == 1:
            return ""  # Nothing learned yet

        lines.append("(User can view and edit this profile in Settings)")
        lines.append("--- END LEARNED PROFILE ---")
        return "\n".join(lines)


def _get_item_text(item):
    """Get text from either a str or dict item."""
    if isinstance(item, dict):
        return item.get('text', '')
    return str(item) if item else ''


def _is_active_item(item):
    """Check if an item is active (not faded)."""
    if isinstance(item, dict):
        return item.get('status', 'active') == 'active'
    return True  # Legacy str items are always active


def _add_field(lines, label, items, limit):
    """Add a profile field to prompt lines, filtering active items only."""
    if not items:
        return
    active = [_get_item_text(i) for i in items if _is_active_item(i)]
    active = [t for t in active if t]  # Remove empty strings
    if active:
        lines.append(f"{label}: {', '.join(active[:limit])}")


class LearningExtraction(models.Model):
    """
    Audit trail of individual learning extractions.

    Each extraction records what was learned from a specific
    assistant interaction.
    """

    CATEGORY_CHOICES = [
        ("stated_value", "Stated Value"),
        ("frustration", "Frustration"),
        ("recurring_goal", "Recurring Goal"),
        ("non_negotiable", "Non-Negotiable"),
        ("relationship_priority", "Relationship Priority"),
        ("identity_statement", "Identity Statement"),
        ("motivational_trigger", "Motivational Trigger"),
        ("avoidance_pattern", "Avoidance Pattern"),
        ("health_concern", "Health Concern"),
        ("life_event_mention", "Life Event Mention"),
        ("commitment_made", "Commitment Made"),
        ("explanation_preference", "Explanation Preference"),
        ("time_pattern", "Time Pattern"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learning_extractions",
    )
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    extracted_text = models.TextField(
        help_text="The learned item text.",
    )
    source_message = models.TextField(
        blank=True,
        help_text="The user message this was extracted from (for transparency).",
    )
    confidence = models.FloatField(
        default=0.7,
        help_text="Extraction confidence 0-1.",
    )
    is_confirmed = models.BooleanField(
        default=False,
        help_text="Whether user has confirmed this extraction.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_learning_extraction"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "category"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"[{self.category}] {self.extracted_text[:60]}"
