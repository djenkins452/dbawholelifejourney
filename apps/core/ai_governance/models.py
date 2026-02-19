"""
Phase 5 — Governance Onboarding Models.

Per-user, per-module commitment classifications that drive strategy
selection, consistency monitoring, and recalibration.

Models:
    - GovernanceProfile: Per-module commitment classification
    - GovernanceAlignmentSession: Tracks onboarding conversation state
"""

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
