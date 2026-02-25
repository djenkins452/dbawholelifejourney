"""
EAE — Executive Arbitration Engine Models.

Models:
- EAEState: Per-user arbitration state (escalation, focus, budget)
- EAEDecisionLog: Append-only audit of every arbitration decision
- EAEOverride: Per-user signal override/suppression state
- EAEEscalationEvent: Append-only escalation transition log
"""
import logging
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.ai_eae.constants import (
    BUDGET_CHAT,
    CHANNEL_CHOICES,
    ESCALATION_CHOICES,
    ESCALATION_NOMINAL,
    OVERRIDE_PERMANENT,
    OVERRIDE_TEMPORARY,
    PRIMARY_FOCUS_MAX_CHANGES,
    TONE_CHOICES,
    TONE_REFLECTIVE_GENTLE,
)

logger = logging.getLogger(__name__)


# =============================================================================
# EAE STATE (per-user singleton)
# =============================================================================


class EAEState(models.Model):
    """
    Per-user arbitration state. Tracks escalation level, primary focus,
    noise budget consumption, and last arbitration time.

    OneToOne with User — created on first arbitration.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='eae_state',
    )

    # Escalation
    escalation_level = models.IntegerField(
        default=ESCALATION_NOMINAL,
        choices=ESCALATION_CHOICES,
        help_text="Current escalation level (0=Nominal, 4=Override)",
    )
    escalation_since = models.DateTimeField(
        default=timezone.now,
        help_text="When the current escalation level was set",
    )
    escalation_peak_drift = models.FloatField(
        default=0.0,
        help_text="Peak drift severity since last escalation change (for de-escalation gate)",
    )

    # Drift
    drift_risk_severity = models.FloatField(
        default=0.0,
        help_text="Current drift risk severity (0-100)",
    )

    # Primary Focus
    primary_focus_label = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Current primary focus label (e.g., 'Medication Adherence')",
    )
    primary_focus_module = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Module of the primary focus (e.g., 'health')",
    )
    primary_focus_set_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the current primary focus was set",
    )
    focus_changes_today = models.IntegerField(
        default=0,
        help_text=f"Number of focus changes today (max {PRIMARY_FOCUS_MAX_CHANGES})",
    )
    focus_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date for daily focus reset tracking",
    )

    # Noise Budget
    noise_budget_used_today = models.IntegerField(
        default=0,
        help_text="Cognitive units consumed today across all channels",
    )
    noise_budget_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date for daily budget reset tracking",
    )

    # Timing
    last_arbitration_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of last arbitration run",
    )

    # Metadata
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "EAE State"
        verbose_name_plural = "EAE States"
        indexes = [
            models.Index(fields=['escalation_level'], name='eae_state_esc_level'),
        ]

    def __str__(self):
        return (
            f"EAE State for {self.user_id}: "
            f"L{self.escalation_level} / drift={self.drift_risk_severity:.0f}"
        )

    def reset_daily_counters(self, today):
        """Reset focus changes and budget if date has changed."""
        if self.focus_date != today:
            self.focus_changes_today = 0
            self.focus_date = today
        if self.noise_budget_date != today:
            self.noise_budget_used_today = 0
            self.noise_budget_date = today

    @property
    def focus_locked(self):
        """True if primary focus changes are exhausted for today."""
        return self.focus_changes_today >= PRIMARY_FOCUS_MAX_CHANGES


# =============================================================================
# EAE DECISION LOG (append-only audit)
# =============================================================================


class EAEDecisionLog(models.Model):
    """
    Append-only record of every EAE arbitration decision.
    Never updated after creation. Used for audit, analytics, and tuning.
    """

    decision_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='eae_decisions',
    )

    channel = models.CharField(
        max_length=20,
        choices=CHANNEL_CHOICES,
        help_text="Channel this decision was made for",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # State at decision time
    escalation_level = models.IntegerField(
        choices=ESCALATION_CHOICES,
        help_text="Escalation level when decision was made",
    )
    drift_risk_severity = models.FloatField(
        help_text="Drift risk severity at decision time (0-100)",
    )
    tone_band = models.CharField(
        max_length=30,
        choices=TONE_CHOICES,
        help_text="Tone band assigned for this decision",
    )

    # Focus
    primary_focus_label = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Primary focus at decision time",
    )

    # Intelligence output
    cognitive_units_json = models.JSONField(
        default=list,
        help_text="Full CognitiveUnit list that was surfaced",
    )
    suppressed_items_json = models.JSONField(
        default=list,
        help_text="Items that were suppressed with reason codes",
    )

    # Counts
    total_candidates = models.IntegerField(
        default=0,
        help_text="Total signals that entered arbitration",
    )
    surfaced_count = models.IntegerField(
        default=0,
        help_text="Number of cognitive units surfaced",
    )
    suppressed_count = models.IntegerField(
        default=0,
        help_text="Number of signals suppressed",
    )

    # Budget
    noise_budget_used = models.IntegerField(
        default=0,
        help_text="Cognitive units consumed by this decision",
    )
    noise_budget_max = models.IntegerField(
        default=BUDGET_CHAT,
        help_text="Budget cap that was applied",
    )

    # Overrides
    override_events_json = models.JSONField(
        default=list,
        blank=True,
        help_text="Override events applied during this decision",
    )

    # Audit trail
    reason_codes = models.JSONField(
        default=list,
        help_text="Machine-readable decision reason codes",
    )
    source_engines = models.JSONField(
        default=list,
        help_text="Engines that contributed signals to this decision",
    )
    arbitration_duration_ms = models.IntegerField(
        default=0,
        help_text="Time taken for arbitration in milliseconds",
    )

    class Meta:
        verbose_name = "EAE Decision Log"
        verbose_name_plural = "EAE Decision Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at'], name='eae_dec_user_time'),
            models.Index(fields=['channel', '-created_at'], name='eae_dec_chan_time'),
        ]

    def __str__(self):
        return (
            f"EAE Decision {self.decision_id!s:.8} "
            f"[{self.channel}] L{self.escalation_level} "
            f"surfaced={self.surfaced_count}"
        )


# =============================================================================
# EAE OVERRIDE (per-user, per-signal-type)
# =============================================================================


class EAEOverride(models.Model):
    """
    Tracks user overrides (suppression) of specific signal types.
    Implements the 3-strike doctrine: clarify → confirm → comply + suppress.
    """

    OVERRIDE_TYPE_CHOICES = [
        (OVERRIDE_PERMANENT, 'Permanent'),
        (OVERRIDE_TEMPORARY, 'Temporary'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='eae_overrides',
    )

    signal_type = models.CharField(
        max_length=100,
        help_text=(
            "Signal type being overridden. Format: 'ENGINE:type' "
            "e.g., 'PIE:medication_adherence', 'PGE:habit_streak'"
        ),
    )

    override_type = models.CharField(
        max_length=20,
        choices=OVERRIDE_TYPE_CHOICES,
        default=OVERRIDE_TEMPORARY,
        help_text="Whether this is a permanent or temporary suppression",
    )

    strike_count = models.IntegerField(
        default=1,
        help_text="Current strike count (1-3). At 3, suppression activates.",
    )

    cooldown_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="For temporary overrides: when the cooldown expires",
    )

    temporary_count_14d = models.IntegerField(
        default=0,
        help_text=(
            "Number of temporary cooldowns in last 14 days. "
            "At 3, auto-escalates to permanent."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "EAE Override"
        verbose_name_plural = "EAE Overrides"
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'signal_type'],
                name='unique_eae_override_per_user_signal',
            ),
        ]
        indexes = [
            models.Index(
                fields=['user', 'override_type'],
                name='eae_override_user_type',
            ),
        ]

    def __str__(self):
        status = self.override_type
        if self.override_type == OVERRIDE_TEMPORARY and self.cooldown_until:
            status = f"temp until {self.cooldown_until:%Y-%m-%d %H:%M}"
        return f"Override [{self.signal_type}] for user {self.user_id}: {status}"

    @property
    def is_active(self):
        """Check if this override is currently suppressing signals."""
        if self.override_type == OVERRIDE_PERMANENT:
            return True
        if self.override_type == OVERRIDE_TEMPORARY and self.cooldown_until:
            return timezone.now() < self.cooldown_until
        return False

    @property
    def is_expired(self):
        """Check if a temporary cooldown has expired."""
        if self.override_type == OVERRIDE_PERMANENT:
            return False
        if self.cooldown_until is None:
            return True
        return timezone.now() >= self.cooldown_until


# =============================================================================
# EAE ESCALATION EVENT (append-only)
# =============================================================================


class EAEEscalationEvent(models.Model):
    """
    Append-only log of every escalation level transition.
    Never updated after creation.
    """

    DIRECTION_UP = 'up'
    DIRECTION_DOWN = 'down'

    DIRECTION_CHOICES = [
        (DIRECTION_UP, 'Escalation'),
        (DIRECTION_DOWN, 'De-escalation'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='eae_escalation_events',
    )

    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        help_text="Whether this was an escalation or de-escalation",
    )

    from_level = models.IntegerField(
        choices=ESCALATION_CHOICES,
        help_text="Escalation level before this transition",
    )

    to_level = models.IntegerField(
        choices=ESCALATION_CHOICES,
        help_text="Escalation level after this transition",
    )

    trigger_reason = models.CharField(
        max_length=200,
        help_text="Human-readable reason for this transition",
    )

    drift_risk_at_event = models.FloatField(
        help_text="Drift risk severity at the time of this event",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "EAE Escalation Event"
        verbose_name_plural = "EAE Escalation Events"
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['user', '-created_at'],
                name='eae_esc_user_time',
            ),
        ]

    def __str__(self):
        arrow = "↑" if self.direction == self.DIRECTION_UP else "↓"
        return (
            f"EAE {arrow} L{self.from_level}→L{self.to_level} "
            f"for user {self.user_id}: {self.trigger_reason}"
        )
