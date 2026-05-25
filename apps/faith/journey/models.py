"""
Whole Life Journey — Journey Models (Walking With God Through Scripture)

Project: Whole Life Journey
Path: apps/faith/journey/models.py
Purpose: Isolated data layer for the Journey feature.

Description:
    Five models defining the Journey feature. Fully isolated from the
    existing reading-plan system. No imports from apps.faith.models.
    No coupling to ReadingPlanTemplate, ReadingPlanDay, UserReadingPlan,
    UserReadingProgress, or ReadingPlanAssessment.

    See docs/CLAUDE_WALKING_WITH_GOD.md for the full spec.

Naming notes:
    - JourneyPath / JourneyArc / JourneyDay extend TimeStampedModel (not
      SoftDeleteModel). This matches the existing ReadingPlanTemplate
      precedent: content models use plain models.Model variants with an
      `is_active` boolean for publish gating.
    - UserJourney and UserJourneyDayProgress extend UserOwnedModel
      (which is SoftDeleteModel + user FK).
    - UserJourney lifecycle field is `journey_status`, not `status`, to
      avoid collision with SoftDeleteModel.status. Same pattern as
      UserReadingPlan.plan_status.

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel, UserOwnedModel


DIFFICULTY_TIERS = [
    ("simple", "Simple"),
    ("standard", "Standard"),
    ("deeper", "Deeper"),
]


# ---------------------------------------------------------------------------
# Content models (admin-authored; loaded from JSON content packs)
# ---------------------------------------------------------------------------

class JourneyPath(TimeStampedModel):
    """A curated multi-arc journey through Scripture.

    Phase 1 ships exactly one instance: "Walking With God Through Scripture".
    """

    slug = models.SlugField(unique=True, max_length=100)
    name = models.CharField(max_length=200)
    narrative_overview = models.TextField()
    cover_image_url = models.URLField(blank=True)
    estimated_weeks = models.PositiveIntegerField(default=0)
    difficulty_default = models.CharField(
        max_length=20,
        choices=DIFFICULTY_TIERS,
        default="standard",
    )
    is_active = models.BooleanField(
        default=False,
        help_text=(
            "When True, the path is available to users. Defaults False so "
            "newly loaded paths require explicit publish."
        ),
    )
    is_featured = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        verbose_name = "journey path"
        verbose_name_plural = "journey paths"

    def __str__(self):
        return self.name


class JourneyArc(TimeStampedModel):
    """A narratively coherent span within a JourneyPath."""

    journey_path = models.ForeignKey(
        JourneyPath,
        on_delete=models.CASCADE,
        related_name="arcs",
    )
    slug = models.SlugField(max_length=100)
    name = models.CharField(max_length=200)
    era_label = models.CharField(max_length=80, blank=True)
    order = models.PositiveIntegerField()
    opening_note = models.TextField()
    closing_note = models.TextField()
    estimated_days = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(
        default=False,
        help_text=(
            "When True, the arc is available to users. The loader's "
            "sequence/gap validation (no missing day_numbers from 1 to N) "
            "runs only when is_active=True, so an arc may be authored "
            "incrementally while inactive."
        ),
    )

    class Meta:
        ordering = ["journey_path", "order"]
        unique_together = [
            ("journey_path", "order"),
            ("journey_path", "slug"),
        ]
        verbose_name = "journey arc"
        verbose_name_plural = "journey arcs"

    def __str__(self):
        return f"{self.journey_path.name} — {self.name}"


class JourneyDay(TimeStampedModel):
    """The atomic content unit of a JourneyArc.

    All seven authored elements (context_before, three tiers of plain English,
    key insight, reflection prompt, application action) are required.
    confusion_topics is enforced at the loader level (min 3 per day).
    retention_anchor is required for chronological arcs (loader-enforced).
    """

    arc = models.ForeignKey(
        JourneyArc,
        on_delete=models.CASCADE,
        related_name="days",
    )
    day_number = models.PositiveIntegerField()

    # Scripture
    scripture_refs = models.JSONField(
        help_text="List of reference strings, e.g., ['Leviticus 1:1-17'].",
    )
    scripture_content = models.JSONField(
        help_text=(
            "Translation + ordered verse blocks. Shape: "
            "{'translation': 'WEB', 'blocks': [{ref, verse, text, red_letter}, ...]}"
        ),
    )

    # Seven authored content elements
    context_before = models.TextField(
        help_text="Plain-English orientation before the reading.",
    )
    plain_english_simple = models.TextField(
        help_text="Tier 1 — approachable, accessible commentary.",
    )
    plain_english_standard = models.TextField(
        help_text="Tier 2 — default reading depth.",
    )
    plain_english_deeper = models.TextField(
        help_text="Tier 3 — historical, linguistic, cross-references.",
    )
    key_insight = models.CharField(
        max_length=200,
        help_text="One-sentence takeaway. Loader validates ≤ 200 chars.",
    )
    reflection_prompt = models.TextField(
        help_text="Single personal question — not guilt-inducing.",
    )
    application_action = models.CharField(
        max_length=280,
        help_text="One small concrete action. Loader validates ≤ 280 chars.",
    )
    confusion_topics = models.JSONField(
        default=list,
        help_text=(
            "List of {topic, plain_english_answer} objects. "
            "Loader validates ≥ 3 entries per day."
        ),
    )
    retention_anchor = models.TextField(
        help_text=(
            "Connection to story arc (yesterday → today → tomorrow). "
            "Required for chronological arcs."
        ),
    )

    class Meta:
        ordering = ["arc", "day_number"]
        unique_together = [("arc", "day_number")]
        verbose_name = "journey day"
        verbose_name_plural = "journey days"

    def __str__(self):
        return f"{self.arc.name} — Day {self.day_number}"

    def plain_english_for_tier(self, tier):
        """Return the commentary string matching the requested difficulty tier."""
        mapping = {
            "simple": self.plain_english_simple,
            "standard": self.plain_english_standard,
            "deeper": self.plain_english_deeper,
        }
        return mapping.get(tier, self.plain_english_standard)


# ---------------------------------------------------------------------------
# User-state models
# ---------------------------------------------------------------------------

class UserJourney(UserOwnedModel):
    """A user's instance of a JourneyPath.

    One active journey per user per path is enforced at the service layer
    (not via DB unique constraint) so historical (paused / completed /
    abandoned) rows are preserved.
    """

    JOURNEY_STATUS_CHOICES = [
        ("active", "Active"),
        ("paused", "Paused"),
        ("completed", "Completed"),
        ("abandoned", "Abandoned"),
    ]

    journey_path = models.ForeignKey(
        JourneyPath,
        on_delete=models.PROTECT,
        related_name="user_journeys",
    )
    current_arc = models.ForeignKey(
        JourneyArc,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="current_user_journeys",
    )
    current_day_number = models.PositiveIntegerField(default=1)

    # Named journey_status to avoid SoftDeleteModel.status collision
    # (same pattern as UserReadingPlan.plan_status).
    journey_status = models.CharField(
        max_length=20,
        choices=JOURNEY_STATUS_CHOICES,
        default="active",
    )
    preferred_difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_TIERS,
        default="standard",
    )
    reminder_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Off by default; user opts in.",
    )

    started_at = models.DateTimeField(default=timezone.now)
    # Updated on day completion only — drives days_since_last_read.
    last_engaged_at = models.DateTimeField(null=True, blank=True)
    # Updated on every today/ page view — drives welcome-back trigger.
    # Separate from last_engaged_at so opening the page doesn't mask a real reading gap.
    last_visited_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Internal observability only. Never displayed to user. Computed lazily in state.py.
    momentum_score = models.FloatField(default=1.0)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "user journey"
        verbose_name_plural = "user journeys"

    def __str__(self):
        return f"{self.user.email}: {self.journey_path.name}"


class UserJourneyDayProgress(UserOwnedModel):
    """Per-day completion record for a UserJourney.

    Unique per (user_journey, journey_day).
    """

    user_journey = models.ForeignKey(
        UserJourney,
        on_delete=models.CASCADE,
        related_name="day_progress",
    )
    journey_day = models.ForeignKey(
        JourneyDay,
        on_delete=models.CASCADE,
        related_name="user_progress",
    )

    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    reflection_notes = models.TextField(blank=True)
    application_committed = models.BooleanField(default=False)
    difficulty_at_completion = models.CharField(
        max_length=20,
        choices=DIFFICULTY_TIERS,
        blank=True,
        help_text="Snapshot of difficulty tier at the moment the day was marked complete.",
    )

    class Meta:
        ordering = ["user_journey", "journey_day"]
        unique_together = [("user_journey", "journey_day")]
        verbose_name = "user journey day progress"
        verbose_name_plural = "user journey day progress records"

    def __str__(self):
        return f"{self.user_journey} — Day {self.journey_day.day_number}"
