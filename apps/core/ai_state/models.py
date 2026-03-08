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

    SITUATION_MODE_CHOICES = [
        (MODE_MORNING_ORIENTATION, 'Morning Orientation'),
        (MODE_MIDDAY_CHECKPOINT, 'Midday Checkpoint'),
        (MODE_AFTERNOON_FOCUS, 'Afternoon Focus'),
        (MODE_EVENING_REVIEW, 'Evening Review'),
        (MODE_WEEKEND_REFLECTION, 'Weekend Reflection'),
        (MODE_URGENT_INTERVENTION, 'Urgent Intervention'),
        (MODE_CELEBRATION, 'Celebration'),
        (MODE_RECOVERY, 'Recovery'),
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
