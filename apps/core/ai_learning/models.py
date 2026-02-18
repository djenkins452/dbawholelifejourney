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
        """
        lines = []
        lines.append("--- LEARNED USER PROFILE ---")

        if self.stated_values:
            lines.append(f"Core Values: {', '.join(self.stated_values[:8])}")
        if self.non_negotiables:
            lines.append(f"Non-Negotiables: {', '.join(self.non_negotiables[:8])}")
        if self.identity_statements:
            lines.append(f"Identity: {', '.join(self.identity_statements[:5])}")
        if self.recurring_goals:
            lines.append(f"Recurring Goals: {', '.join(self.recurring_goals[:5])}")
        if self.motivational_triggers:
            lines.append(f"Motivators: {', '.join(self.motivational_triggers[:5])}")
        if self.relationship_priorities:
            lines.append(f"Key Relationships: {', '.join(self.relationship_priorities[:5])}")
        if self.repeated_frustrations:
            lines.append(f"Known Frustrations: {', '.join(self.repeated_frustrations[:5])}")
        if self.avoidance_patterns:
            lines.append(f"Avoidance Patterns: {', '.join(self.avoidance_patterns[:3])}")

        if len(lines) == 1:
            return ""  # Nothing learned yet

        lines.append("(User can view and edit this profile in Settings)")
        lines.append("--- END LEARNED PROFILE ---")
        return "\n".join(lines)


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
