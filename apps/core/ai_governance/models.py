"""
Governance Models.

Phase 5: Per-user, per-module commitment classifications that drive strategy
selection, consistency monitoring, and recalibration.

Phase 8: SelfError — append-only audit log of system self-detected errors
(banned-term leaks, numeric exposures, validator crashes).

Models:
    - GovernanceProfile: Per-module commitment classification
    - GovernanceAlignmentSession: Tracks onboarding conversation state
    - SelfError: Append-only system self-error log (Phase 8)
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class GovernanceProfile(models.Model):
    """
    Per-user commitment classification for each active module/area.

    Created during the Governance Alignment Session. Stores what the user
    declared as non-negotiable, important, or flexible — along with WHY
    it matters to them. This drives strategy selection (ALIGN/PROTECT/
    CHALLENGE/COMPRESS) and recalibration conversations.
    """

    COMMITMENT_NON_NEGOTIABLE = 'non_negotiable'
    COMMITMENT_IMPORTANT = 'important'
    COMMITMENT_FLEXIBLE = 'flexible'

    COMMITMENT_CHOICES = [
        (COMMITMENT_NON_NEGOTIABLE, 'Non-Negotiable'),
        (COMMITMENT_IMPORTANT, 'Important'),
        (COMMITMENT_FLEXIBLE, 'Flexible'),
    ]

    ESCALATION_GENTLE = 'gentle'
    ESCALATION_DIRECT = 'direct'
    ESCALATION_FIRM = 'firm'

    ESCALATION_CHOICES = [
        (ESCALATION_GENTLE, 'Gentle'),
        (ESCALATION_DIRECT, 'Direct'),
        (ESCALATION_FIRM, 'Firm'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='governance_profiles',
    )

    # Module/area this classification applies to
    module_key = models.CharField(
        max_length=50,
        help_text="Module or area key: 'faith', 'health.weight', 'journal', 'goals', etc.",
    )

    display_name = models.CharField(
        max_length=100,
        help_text="Human-readable name shown to user (e.g. 'Morning Prayer', 'Workout')",
    )

    # Commitment level
    commitment_level = models.CharField(
        max_length=15,
        choices=COMMITMENT_CHOICES,
        default=COMMITMENT_IMPORTANT,
    )

    # Weight multiplier for DriftPressure calculation
    importance_weight = models.FloatField(
        default=1.0,
        help_text="Multiplier for this area's impact on DriftPressure (0.3-2.0)",
    )

    # How the user wants to be reminded about this area
    escalation_preference = models.CharField(
        max_length=10,
        choices=ESCALATION_CHOICES,
        default=ESCALATION_DIRECT,
    )

    # Why this matters — in the user's own words
    declared_reason = models.TextField(
        blank=True,
        help_text="User's stated reason for this classification (their own words)",
    )

    # Optional FK to goals
    tied_goal_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="IDs of LifeGoal objects tied to this area",
    )

    # How often to re-check alignment
    review_interval_days = models.PositiveIntegerField(
        default=14,
        help_text="Days between recalibration checks",
    )

    # Tracking
    last_reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time user was asked about this classification",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'core'
        db_table = 'core_governanceprofile'
        unique_together = ['user', 'module_key']
        ordering = ['commitment_level', 'module_key']
        verbose_name = "Governance Profile"
        verbose_name_plural = "Governance Profiles"

    def __str__(self):
        return f"{self.display_name} [{self.commitment_level}] for {self.user.email}"

    @classmethod
    def get_for_user(cls, user):
        """Get all active governance profiles for a user."""
        return cls.objects.filter(user=user, is_active=True)

    @classmethod
    def has_completed_alignment(cls, user):
        """Check if user has completed initial governance alignment."""
        return cls.objects.filter(user=user, is_active=True).exists()

    @classmethod
    def get_non_negotiables(cls, user):
        """Get all non-negotiable areas for a user."""
        return cls.objects.filter(
            user=user,
            commitment_level=cls.COMMITMENT_NON_NEGOTIABLE,
            is_active=True,
        )

    @classmethod
    def get_importance_weight(cls, user, module_key):
        """Get importance weight for a specific module."""
        try:
            profile = cls.objects.get(user=user, module_key=module_key, is_active=True)
            return profile.importance_weight
        except cls.DoesNotExist:
            return 1.0


class GovernanceAlignmentSession(models.Model):
    """
    Tracks the state of a governance alignment conversation.

    The session progresses through stages:
    1. core_values — "What absolutely cannot slip?"
    2. success_definition — "What does a successful day look like?"
    3. chaos_protection — "If your week gets chaotic, what still has to happen?"
    4. top_three — "If I had to protect three areas no matter what?"
    5. module_classification — Per-module: "Is this non-negotiable, important, or flexible?"
    6. complete — All questions answered, profiles created
    """

    STAGE_CORE_VALUES = 'core_values'
    STAGE_SUCCESS_DEFINITION = 'success_definition'
    STAGE_CHAOS_PROTECTION = 'chaos_protection'
    STAGE_TOP_THREE = 'top_three'
    STAGE_MODULE_CLASSIFICATION = 'module_classification'
    STAGE_COMPLETE = 'complete'

    STAGE_CHOICES = [
        (STAGE_CORE_VALUES, 'Core Values'),
        (STAGE_SUCCESS_DEFINITION, 'Success Definition'),
        (STAGE_CHAOS_PROTECTION, 'Chaos Protection'),
        (STAGE_TOP_THREE, 'Top Three'),
        (STAGE_MODULE_CLASSIFICATION, 'Module Classification'),
        (STAGE_COMPLETE, 'Complete'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='governance_alignment_session',
    )

    current_stage = models.CharField(
        max_length=30,
        choices=STAGE_CHOICES,
        default=STAGE_CORE_VALUES,
    )

    # Responses collected during the session
    responses = models.JSONField(
        default=dict,
        blank=True,
        help_text="Collected responses by stage key",
    )

    # Which modules still need classification
    pending_modules = models.JSONField(
        default=list,
        blank=True,
        help_text="Module keys still awaiting classification",
    )

    is_complete = models.BooleanField(default=False)

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'core'
        db_table = 'core_governancealignmentsession'
        verbose_name = "Governance Alignment Session"
        verbose_name_plural = "Governance Alignment Sessions"

    def __str__(self):
        return f"Alignment for {self.user.email} [{self.current_stage}]"

    def advance_to_next_stage(self):
        """Advance to the next stage in the alignment flow."""
        stage_order = [
            self.STAGE_CORE_VALUES,
            self.STAGE_SUCCESS_DEFINITION,
            self.STAGE_CHAOS_PROTECTION,
            self.STAGE_TOP_THREE,
            self.STAGE_MODULE_CLASSIFICATION,
            self.STAGE_COMPLETE,
        ]
        try:
            idx = stage_order.index(self.current_stage)
            if idx < len(stage_order) - 1:
                self.current_stage = stage_order[idx + 1]
                if self.current_stage == self.STAGE_COMPLETE:
                    self.is_complete = True
                    self.completed_at = timezone.now()
                self.save(update_fields=[
                    'current_stage', 'is_complete', 'completed_at', 'updated_at',
                ])
        except ValueError:
            pass

    def record_response(self, stage_key, response_data):
        """Record a response for a stage.

        Args:
            stage_key: str — stage being answered.
            response_data: str or dict — if str, stored as {'text': str}.
        """
        responses = self.responses or {}
        if isinstance(response_data, dict):
            response_data['timestamp'] = timezone.now().isoformat()
            responses[stage_key] = response_data
        else:
            responses[stage_key] = {
                'text': response_data,
                'timestamp': timezone.now().isoformat(),
            }
        self.responses = responses
        self.save(update_fields=['responses', 'updated_at'])


# =========================================================================
# Phase 8 — Self-Error Audit Log
# =========================================================================


class SelfError(models.Model):
    """
    Append-only audit log of system self-detected errors.

    Logged when the pre-release validator gate detects a banned term,
    numeric leakage, or crashes. Never updated after creation.

    Levels:
        1 — Minor (numeric observe-only)
        2 — Moderate (structural violation, blocked)
        3 — Critical (validator crash, repeated escalation)

    Categories:
        STRUCTURAL — banned term leaked in response
        NUMERIC    — internal numeric/threshold exposed
        GOVERNANCE — validator crash or system-level failure
    """

    LEVEL_MINOR = 1
    LEVEL_MODERATE = 2
    LEVEL_CRITICAL = 3

    LEVEL_CHOICES = [
        (LEVEL_MINOR, 'Minor'),
        (LEVEL_MODERATE, 'Moderate'),
        (LEVEL_CRITICAL, 'Critical'),
    ]

    CATEGORY_STRUCTURAL = 'STRUCTURAL'
    CATEGORY_NUMERIC = 'NUMERIC'
    CATEGORY_GOVERNANCE = 'GOVERNANCE'

    CATEGORY_CHOICES = [
        (CATEGORY_STRUCTURAL, 'Structural'),
        (CATEGORY_NUMERIC, 'Numeric'),
        (CATEGORY_GOVERNANCE, 'Governance'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='self_errors',
        help_text="User context when error occurred (null for system-level).",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    level = models.IntegerField(
        choices=LEVEL_CHOICES,
        help_text="1=Minor, 2=Moderate, 3=Critical.",
    )

    category = models.CharField(
        max_length=15,
        choices=CATEGORY_CHOICES,
        help_text="STRUCTURAL, NUMERIC, or GOVERNANCE.",
    )

    trigger_code = models.CharField(
        max_length=50,
        db_index=True,
        help_text=(
            "Machine-readable trigger: BANNED_TERM_LEAKED, "
            "THRESHOLD_EXPOSED, VALIDATOR_CRASH, NUMERIC_DEVIATION."
        ),
    )

    trigger_detail = models.TextField(
        blank=True,
        help_text="What was detected (the specific term, pattern, or error).",
    )

    original_response_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 of original response for correlation (not the response itself).",
    )

    was_blocked = models.BooleanField(
        default=False,
        help_text="True = response was replaced; False = observe-only.",
    )

    engine_run_trace_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Links to EngineRun trace_id for full tracing.",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context (flexible).",
    )

    class Meta:
        app_label = 'core'
        db_table = 'core_selferror'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['trigger_code', 'created_at'],
                name='idx_selferror_trigger_time',
            ),
            models.Index(
                fields=['level', 'created_at'],
                name='idx_selferror_level_time',
            ),
        ]
        verbose_name = "Self-Error"
        verbose_name_plural = "Self-Errors"

    def __str__(self):
        return (
            f"SelfError L{self.level} {self.category}/{self.trigger_code} "
            f"at {self.created_at}"
        )


# ══════════════════════════════════════════════════════════════════════
# Pending Action — durable record of confirmation requests
# ══════════════════════════════════════════════════════════════════════


class PendingAction(models.Model):
    """
    Durable record of pending user confirmations.

    Primary storage is Django cache (fast reads, 300s TTL).
    This model provides:
    - Audit trail for all confirmation requests
    - Crash recovery (cache eviction protection)
    - Debugging / admin inspection
    """

    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_EXPIRED = 'expired'
    STATUS_EDITED = 'edited'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_EDITED, 'Edited'),
    ]

    ACTION_TYPE_CHOICES = [
        ('crud', 'CRUD Confirmation'),
        ('disambiguation', 'Disambiguation'),
        ('clarification', 'Entity Clarification'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pending_actions',
    )

    action_type = models.CharField(max_length=20, choices=ACTION_TYPE_CHOICES)
    intent_type = models.CharField(max_length=60)
    parameters = models.JSONField(default=dict)
    options = models.JSONField(default=list, blank=True)
    confirmation_message = models.TextField(blank=True)
    original_input = models.TextField(blank=True)

    # State
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    executed = models.BooleanField(default=False)
    resolved_action = models.CharField(
        max_length=20,
        blank=True,
        help_text="The option the user selected (confirm/cancel/edit/etc.)",
    )

    # Reconciliation context
    recon_decision = models.CharField(max_length=20, blank=True)
    recon_context = models.JSONField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        app_label = 'core'
        db_table = 'core_pendingaction'
        indexes = [
            models.Index(fields=['user', 'status', 'created_at']),
        ]
        ordering = ['-created_at']
        verbose_name = "Pending Action"
        verbose_name_plural = "Pending Actions"

    def __str__(self):
        return (
            f"PendingAction {self.id} ({self.intent_type}) "
            f"status={self.status} user={self.user_id}"
        )

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def resolve(self, action: str, status: str = None):
        """Mark this pending action as resolved."""
        from django.utils import timezone as tz
        self.resolved_action = action
        self.status = status or (
            self.STATUS_CONFIRMED if action == 'confirm'
            else self.STATUS_CANCELLED if action in ('cancel', 'edit')
            else self.STATUS_EDITED
        )
        self.resolved_at = tz.now()
        self.save(update_fields=[
            'resolved_action', 'status', 'resolved_at',
        ])


# ══════════════════════════════════════════════════════════════════════
# User Decision Preference — tracks repeated choice patterns
# ══════════════════════════════════════════════════════════════════════


class UserDecisionPreference(models.Model):
    """
    Tracks repeated user decision patterns for the same action context.

    When a user consistently makes the same choice for similar confirmations
    (sample_size >= 5, confidence >= 0.70), the system can SUGGEST the
    preferred option (shown first, highlighted) but NEVER auto-execute.

    Confidence decays by 0.02 per day after last_seen_at, allowing
    user behavior to drift over time without hard-freezing preferences.
    """

    CONFIDENCE_THRESHOLD = 0.70
    MIN_SAMPLE_SIZE = 5
    DECAY_PER_DAY = 0.02

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='decision_preferences',
    )

    # What pattern this tracks
    intent_type = models.CharField(max_length=60)
    context_key = models.CharField(
        max_length=120,
        help_text="Normalized context identifier (e.g., 'mutate_task:recurring')",
    )

    # What the user typically chooses
    preferred_action = models.CharField(max_length=20, blank=True)

    # Per-action counts
    confirm_count = models.PositiveIntegerField(default=0)
    cancel_count = models.PositiveIntegerField(default=0)
    edit_count = models.PositiveIntegerField(default=0)
    # For custom options (e.g., "single" vs "series")
    custom_counts = models.JSONField(
        default=dict,
        blank=True,
        help_text="Counts for custom option values beyond confirm/cancel/edit",
    )

    # Statistics
    sample_size = models.PositiveIntegerField(default=0)
    confidence = models.FloatField(default=0.0)

    # Timestamps
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'core'
        db_table = 'core_userdecisionpreference'
        unique_together = ['user', 'intent_type', 'context_key']
        indexes = [
            models.Index(fields=['user', 'intent_type']),
        ]
        verbose_name = "User Decision Preference"
        verbose_name_plural = "User Decision Preferences"

    def __str__(self):
        return (
            f"DecisionPref user={self.user_id} {self.intent_type}:"
            f"{self.context_key} → {self.preferred_action} "
            f"(conf={self.confidence:.2f}, n={self.sample_size})"
        )

    def get_effective_confidence(self):
        """Confidence with time decay applied."""
        from django.utils import timezone
        days_since = (timezone.now() - self.last_seen_at).days
        decayed = self.confidence - (days_since * self.DECAY_PER_DAY)
        return max(0.0, decayed)

    def record_decision(self, action: str):
        """
        Record a new decision and recompute confidence.

        Args:
            action: The action string (confirm, cancel, edit, or custom value).
        """
        self.sample_size += 1

        if action == 'confirm':
            self.confirm_count += 1
        elif action == 'cancel':
            self.cancel_count += 1
        elif action == 'edit':
            self.edit_count += 1
        else:
            # Custom option (e.g., 'single', 'series')
            counts = self.custom_counts or {}
            counts[action] = counts.get(action, 0) + 1
            self.custom_counts = counts

        # Recompute preferred action and confidence
        all_counts = {
            'confirm': self.confirm_count,
            'cancel': self.cancel_count,
            'edit': self.edit_count,
        }
        if self.custom_counts:
            all_counts.update(self.custom_counts)

        self.preferred_action = max(all_counts, key=all_counts.get)
        self.confidence = all_counts[self.preferred_action] / self.sample_size
        self.save()

    def is_reliable(self):
        """Whether this preference meets the threshold for suggestions."""
        return (
            self.sample_size >= self.MIN_SAMPLE_SIZE
            and self.get_effective_confidence() >= self.CONFIDENCE_THRESHOLD
        )
