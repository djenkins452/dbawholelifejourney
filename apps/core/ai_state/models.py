"""
SAE — State Awareness Engine Models.

UserState stores a structured JSON snapshot of each user's current
life state. This is a OneToOneField per user — one row per user.

CoSSituationState stores pre-computed CoS awareness — the persistent
"what does the Chief of Staff know right now?" snapshot. Computed every
15 minutes by a scheduled task. No LLM calls — pure logic from engine
outputs. Eliminates the statelessness problem where CoS rebuilds
context from scratch every message.
"""

from django.conf import settings
from django.db import models


class UserState(models.Model):
    """
    Persistent user state snapshot.

    Contains a structured JSON blob with current values for each
    domain module (health, goals, habits, faith, journal).
    Updated incrementally after every successful action.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sae_state",
    )
    state_data = models.JSONField(
        default=dict,
        help_text="Structured state snapshot keyed by module.",
    )

    # Phase 10 — Schedule instability (rolling 7-day total)
    schedule_instability_score = models.IntegerField(
        default=0,
        help_text="Rolling 7-day schedule instability points total.",
    )
    schedule_instability_last_updated = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When schedule_instability_score was last recalculated.",
    )

    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_user_state"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["last_updated"]),
        ]
        verbose_name = "User State"
        verbose_name_plural = "User States"

    def __str__(self):
        modules = list(self.state_data.keys()) if self.state_data else []
        return f"State for {self.user} ({', '.join(modules) or 'empty'})"

    def get_module(self, module):
        """Get state data for a specific module."""
        return self.state_data.get(module, {})

    def set_module(self, module, data):
        """Set state data for a specific module."""
        self.state_data[module] = data


class CoSSituationState(models.Model):
    """
    Persistent CoS awareness state — pre-computed every 15 minutes.

    Represents "what CoS currently knows" about a user's situation.
    Eliminates per-request context rebuilding and enables delta tracking,
    situation-mode-appropriate responses, and pre-interpreted narratives.

    Computed by pure logic (no LLM calls) from engine outputs.
    """

    # ── Situation modes ──
    MODE_MORNING_ORIENTATION = 'morning_orientation'
    MODE_MIDDAY_CHECKPOINT = 'midday_checkpoint'
    MODE_AFTERNOON_FOCUS = 'afternoon_focus'
    MODE_EVENING_REVIEW = 'evening_review'
    MODE_WEEKEND_REFLECTION = 'weekend_reflection'
    MODE_URGENT_INTERVENTION = 'urgent_intervention'
    MODE_CELEBRATION = 'celebration'
    MODE_RECOVERY = 'recovery'
    MODE_OFF_RHYTHM = 'off_rhythm'
    MODE_RETURNING = 'returning'

    SITUATION_MODE_CHOICES = [
        (MODE_MORNING_ORIENTATION, 'Morning Orientation'),
        (MODE_MIDDAY_CHECKPOINT, 'Midday Checkpoint'),
        (MODE_AFTERNOON_FOCUS, 'Afternoon Focus'),
        (MODE_EVENING_REVIEW, 'Evening Review'),
        (MODE_WEEKEND_REFLECTION, 'Weekend Reflection'),
        (MODE_URGENT_INTERVENTION, 'Urgent Intervention'),
        (MODE_CELEBRATION, 'Celebration'),
        (MODE_RECOVERY, 'Recovery'),
        (MODE_OFF_RHYTHM, 'Off Rhythm'),
        (MODE_RETURNING, 'Returning'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cos_situation",
    )
    computed_at = models.DateTimeField(
        auto_now=True,
        help_text="When this situation state was last computed.",
    )

    # ── Pre-interpreted state (not raw metrics) ──
    dominant_concern = models.TextField(
        blank=True,
        default='',
        help_text=(
            "The single most important thing CoS should communicate. "
            "e.g. 'Medication gap: morning dose 3h overdue'"
        ),
    )
    top_priority = models.TextField(
        blank=True,
        default='',
        help_text=(
            "The recommended next action. "
            "e.g. 'Log morning medications before anything else'"
        ),
    )
    situation_mode = models.CharField(
        max_length=30,
        choices=SITUATION_MODE_CHOICES,
        default=MODE_MORNING_ORIENTATION,
        help_text="Current interaction mode based on time, state, and signals.",
    )

    # ── Delta tracking ──
    changes_since_last_interaction = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {what, when, significance} dicts since last user interaction.",
    )
    escalations = models.JSONField(
        default=list,
        blank=True,
        help_text="Things getting worse since last check.",
    )
    resolutions = models.JSONField(
        default=list,
        blank=True,
        help_text="Things resolved since last check.",
    )

    # ── Narrative frame ──
    opening_sentence = models.TextField(
        blank=True,
        default='',
        help_text=(
            "Pre-computed first sentence for CoS response. "
            "e.g. 'Good morning. Quick overview: 2 tasks due, medication not logged yet.'"
        ),
    )
    suppressed_signals = models.JSONField(
        default=list,
        blank=True,
        help_text="Signals filtered by EAE noise budget (transparency).",
    )

    # ── Awareness metadata ──
    last_user_interaction = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user last interacted with the system.",
    )
    messages_since_briefing = models.IntegerField(
        default=0,
        help_text="Number of messages exchanged since last daily briefing.",
    )
    user_acknowledged_signals = models.JSONField(
        default=list,
        blank=True,
        help_text="Signal IDs the user has acknowledged/responded to.",
    )

    # ── Previous state for diff computation ──
    previous_dominant_concern = models.TextField(
        blank=True,
        default='',
        help_text="Previous dominant concern for delta detection.",
    )

    class Meta:
        app_label = "core"
        db_table = "core_cos_situation_state"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["computed_at"]),
            models.Index(fields=["situation_mode"]),
        ]
        verbose_name = "CoS Situation State"
        verbose_name_plural = "CoS Situation States"

    def __str__(self):
        return (
            f"CoS Situation for {self.user} — "
            f"mode={self.situation_mode}, concern={self.dominant_concern[:50]}"
        )


class UserOperatingProfile(models.Model):
    """
    Personal Operating Context — pre-computed behavioral synthesis.

    Stores how this user typically operates: productive time windows,
    task deferral patterns, and momentum phase. Computed daily from
    a 30-day sliding window of existing activity data.

    This is NOT an engine. It is a lightweight synthesis layer that
    Beth reads when framing guidance. It influences HOW she communicates,
    not WHAT she decides.

    Follows the CoSSituationState pattern:
        PRECOMPUTE (nightly task) → STORE (this model) → READ (CoS builder) → INJECT (prompt)
    """

    # Current profile schema version — increment when profile_data structure changes
    SCHEMA_VERSION = 2

    # Minimum days of data for the profile to be considered reliable
    MIN_CONFIDENCE_DAYS = 14

    # ── Per-dimension confidence gates for injection ──
    # Each dimension must meet its own threshold to be injected into the
    # CoS prompt. Stored here (not in cos_context.py) so they're centrally
    # tunable. Higher thresholds for dimensions that make specific claims
    # (timing, deferral rates), lower for broader signals (momentum).
    CONFIDENCE_GATES = {
        'productive_windows': 0.60,
        'deferral_patterns': 0.60,
        'momentum_phase': 0.40,
    }

    # ── Drift detection thresholds ──
    # Minimum change between consecutive profiles to flag as behavioral shift.
    DRIFT_THRESHOLDS = {
        'peak_hours_shift': 2,      # hours — median peak moved by 2+ hours
        'deferral_rate_shift': 0.15, # 15 percentage points
        'momentum_phase_change': True,  # any phase transition is a drift signal
    }

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="operating_profile",
    )
    profile_data = models.JSONField(
        default=dict,
        help_text=(
            "Structured behavioral synthesis keyed by dimension. "
            "Phase 1 dimensions: productive_windows, deferral_patterns, momentum_phase. "
            "Also contains 'behavior_drift' metadata when shifts are detected."
        ),
    )
    previous_profile_data = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Snapshot of the prior profile_data before recomputation. "
            "Used for drift detection — comparing old vs new profiles."
        ),
    )
    sample_days = models.IntegerField(
        default=0,
        help_text="Number of days of usable activity data in the computation window.",
    )
    last_computed = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this profile was last recomputed.",
    )
    version = models.IntegerField(
        default=SCHEMA_VERSION,
        help_text="Schema version of profile_data structure.",
    )

    class Meta:
        app_label = "core"
        db_table = "core_user_operating_profile"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["last_computed"]),
        ]
        verbose_name = "User Operating Profile"
        verbose_name_plural = "User Operating Profiles"

    def __str__(self):
        phase = self.get_dimension("momentum_phase", {}).get("current_phase", "unknown")
        drift = " [DRIFT]" if self.has_drift else ""
        return (
            f"Operating Profile for {self.user} — "
            f"sample_days={self.sample_days}, phase={phase}{drift}"
        )

    def get_dimension(self, dimension, default=None):
        """Get a specific behavioral dimension from profile_data."""
        return self.profile_data.get(dimension, default or {})

    def dimension_meets_gate(self, dimension):
        """Check if a dimension's confidence meets its injection threshold."""
        gate = self.CONFIDENCE_GATES.get(dimension, 0.60)
        dim_data = self.get_dimension(dimension)
        return dim_data.get('confidence', 0) >= gate

    @property
    def is_reliable(self):
        """Whether this profile has enough data to be useful."""
        return self.sample_days >= self.MIN_CONFIDENCE_DAYS

    @property
    def has_drift(self):
        """Whether a behavioral shift was detected in the last computation."""
        drift = self.profile_data.get('behavior_drift', {})
        return drift.get('detected', False)
