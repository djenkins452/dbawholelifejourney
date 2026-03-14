"""
Dashboard V2 — Life Command Center Models

Three models that support the dashboard_v2 intelligence layer:
- GoalMomentumSnapshot: Nightly persisted momentum scores per goal
- PreparedCelebration: System-detected celebration events
- DailyProgressSnapshot: Daily execution completeness tracking
"""

from django.db import models
from django.utils import timezone

from apps.core.models import UserOwnedModel


class GoalMomentumSnapshot(UserOwnedModel):
    """
    Persisted computation of goal momentum.
    One row per user per goal per date.

    Momentum (0-100): "How strongly am I moving toward this goal RIGHT NOW?"
    Progress (0-100): "How far along the journey?" (milestone-based)

    Computed nightly by Celery task; also computed live for real-time display.
    """

    goal = models.ForeignKey(
        "purpose.LifeGoal",
        on_delete=models.CASCADE,
        related_name="momentum_snapshots",
    )
    snapshot_date = models.DateField(db_index=True)

    # Core scores
    momentum_score = models.PositiveSmallIntegerField(
        help_text="0-100: How strongly moving toward this goal RIGHT NOW"
    )
    progress_score = models.PositiveSmallIntegerField(
        help_text="0-100: How far along the journey (milestone-based)"
    )

    # Momentum drivers (explainability)
    drivers = models.JSONField(
        default=dict,
        help_text=(
            "Breakdown of momentum components. "
            "Example: {'habits': {'score': 28, 'label': '4/5 habits completed'}, ...}"
        ),
    )

    # Signal-based scores (Architecture Evolution Phase 5)
    signal_scores = models.JSONField(
        default=dict,
        help_text=(
            "Per-signal-type scores from GoalSignalSource weighting. "
            "Example: {'health_activity': 0.85, 'medication_adherence': 1.0}"
        ),
    )

    # Trend
    momentum_7d_avg = models.PositiveSmallIntegerField(null=True, blank=True)
    momentum_trend = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("rising", "Rising"),
            ("stable", "Stable"),
            ("falling", "Falling"),
        ],
    )

    class Meta:
        unique_together = ["user", "goal", "snapshot_date"]
        ordering = ["-snapshot_date"]
        indexes = [
            models.Index(fields=["user", "snapshot_date"]),
        ]

    def __str__(self):
        return (
            f"{self.user} — {self.goal.title} — "
            f"{self.snapshot_date} (M:{self.momentum_score} P:{self.progress_score})"
        )


class PreparedCelebration(UserOwnedModel):
    """
    System-detected meaningful progress worthy of celebration.
    Generated in background, revealed only when earned.

    Rules:
    - Max 1 ready celebration per user at a time
    - Expires after 7 days if not revealed
    - Template-based narratives (no OpenAI call)
    - Cooldown periods per celebration type
    """

    CELEBRATION_TYPES = [
        ("streak_milestone", "Consistency Milestone"),
        ("goal_milestone", "Goal Milestone Completed"),
        ("weekly_discipline", "Strong Weekly Discipline"),
        ("momentum_surge", "Momentum Surge"),
        ("health_breakthrough", "Health Breakthrough"),
        ("consistency_pattern", "Consistency Pattern"),
        ("cross_domain", "Cross-Domain Win"),
    ]

    STATUS_CHOICES = [
        ("ready", "Ready to Reveal"),
        ("revealed", "Revealed"),
        ("dismissed", "Dismissed"),
        ("expired", "Expired"),
    ]

    celebration_type = models.CharField(max_length=30, choices=CELEBRATION_TYPES)
    # Named celebration_status to avoid shadowing SoftDeleteModel.status
    celebration_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ready")

    # Content
    headline = models.CharField(max_length=200, help_text="Bold celebration headline")
    narrative = models.TextField(help_text="Full celebration narrative with specifics")
    evidence = models.JSONField(
        default=dict, help_text="Data backing the celebration"
    )

    # Metadata
    domain = models.CharField(
        max_length=50, blank=True, help_text="Life domain (e.g., health, faith)"
    )
    related_goal = models.ForeignKey(
        "purpose.LifeGoal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="celebrations",
    )

    # Timing
    generated_at = models.DateTimeField(default=timezone.now)
    revealed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        help_text="Celebration expires if not revealed within 7 days"
    )

    # Cooldown tracking
    dedupe_key = models.CharField(max_length=255, db_index=True)

    class Meta:
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["user", "celebration_status"]),
            models.Index(fields=["user", "celebration_type", "generated_at"]),
        ]

    def __str__(self):
        return f"{self.user} — {self.headline} ({self.celebration_status})"

    def reveal(self):
        self.celebration_status = "revealed"
        self.revealed_at = timezone.now()
        self.save(update_fields=["celebration_status", "revealed_at", "updated_at"])

    def dismiss(self):
        self.celebration_status = "dismissed"
        self.save(update_fields=["celebration_status", "updated_at"])

    def expire(self):
        self.celebration_status = "expired"
        self.save(update_fields=["celebration_status", "updated_at"])


class DailyProgressSnapshot(UserOwnedModel):
    """
    Tracks daily execution completeness for the progress indicator.
    One row per user per day. Updated incrementally as user takes actions.

    Component weights (sum = 100):
    - Routines: 25%
    - Medicine: 20%
    - Tasks: 20%
    - Workout: 15%
    - Journaling: 10%
    - Faith: 10%
    """

    snapshot_date = models.DateField(db_index=True)

    # Component scores (each 0-100)
    routines_score = models.PositiveSmallIntegerField(default=0)
    medicine_score = models.PositiveSmallIntegerField(default=0)
    tasks_score = models.PositiveSmallIntegerField(default=0)
    journaling_score = models.PositiveSmallIntegerField(default=0)
    workout_score = models.PositiveSmallIntegerField(default=0)
    faith_score = models.PositiveSmallIntegerField(default=0)

    # Composite (weighted average of component scores)
    overall_score = models.PositiveSmallIntegerField(
        default=0,
        help_text="Weighted average of component scores, 0-100",
    )

    # Raw counts for display
    components = models.JSONField(
        default=dict,
        help_text=(
            "Raw component data for display. "
            "Example: {'routines_done': 3, 'routines_total': 5, 'meds_taken': 4, ...}"
        ),
    )

    class Meta:
        unique_together = ["user", "snapshot_date"]
        ordering = ["-snapshot_date"]
        indexes = [
            models.Index(fields=["user", "snapshot_date"]),
        ]

    def __str__(self):
        return f"{self.user} — {self.snapshot_date} (Score: {self.overall_score})"
