"""
Whole Life Journey - Personal Operating Blueprint Models

Project: Whole Life Journey
Path: apps/core/blueprint/models.py
Purpose: Data models for the Chief of Staff blueprint system

Description:
    Implements the PersonalOperatingBlueprint (POB) - a single authoritative
    blueprint object per user that all intelligence engines consult. Also includes
    ArchitecturePlan for daily scheduling and DriftEvent/DriftScore for drift
    detection.

Models:
    - PersonalOperatingBlueprint: Core user blueprint (OneToOne)
    - NonNegotiable: Protected behaviors with scheduling metadata
    - ArchitecturePlan: Daily schedule architecture
    - ScheduledBlock: Individual time blocks within an architecture plan
    - DriftEvent: Individual drift event occurrence
    - DriftScore: Daily aggregate drift score
    - InterventionLog: Record of assistant interventions/escalations
    - FrictionGateLog: Record of friction gate interactions

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


# =============================================================================
# PERSONAL OPERATING BLUEPRINT
# =============================================================================


class PersonalOperatingBlueprint(models.Model):
    """
    Single authoritative blueprint per user. All engines consult this
    to understand user priorities, operating style, and constraints.

    The blueprint drives:
    - Priority tier assignments for behaviors
    - Daily architecture passes (scheduling)
    - Drift detection thresholds
    - Intervention escalation rules
    - Assistant tone and assertiveness
    """

    # Operating style choices
    STYLE_EXECUTIVE_COS = 'executive_cos'
    STYLE_CALM_GUIDE = 'calm_guide'
    STYLE_MINIMAL = 'minimal'
    STYLE_COACH = 'coach'
    STYLE_CUSTOM = 'custom'

    OPERATING_STYLE_CHOICES = [
        (STYLE_EXECUTIVE_COS, 'Executive Chief of Staff'),
        (STYLE_CALM_GUIDE, 'Calm Guide'),
        (STYLE_MINIMAL, 'Minimal'),
        (STYLE_COACH, 'Coach'),
        (STYLE_CUSTOM, 'Custom'),
    ]

    # Interruption tolerance
    TOLERANCE_LOW = 'low'
    TOLERANCE_MEDIUM = 'medium'
    TOLERANCE_HIGH = 'high'

    INTERRUPTION_TOLERANCE_CHOICES = [
        (TOLERANCE_LOW, 'Low - Minimal interruptions'),
        (TOLERANCE_MEDIUM, 'Medium - Balanced'),
        (TOLERANCE_HIGH, 'High - Keep me informed'),
    ]

    # Wake time policy
    WAKE_AUTO = 'auto'
    WAKE_SUGGEST = 'suggest'
    WAKE_MANUAL = 'manual'

    WAKE_TIME_POLICY_CHOICES = [
        (WAKE_AUTO, 'Auto - Assistant recommends based on schedule'),
        (WAKE_SUGGEST, 'Suggest - Show recommendation, I decide'),
        (WAKE_MANUAL, 'Manual - I set my own wake time'),
    ]

    # Override policy for non-tier1 items
    OVERRIDE_WITH_FRICTION = 'allow_with_friction'
    OVERRIDE_NO_FRICTION = 'allow_no_friction'

    OVERRIDE_POLICY_CHOICES = [
        (OVERRIDE_WITH_FRICTION, 'Allow with confirmation'),
        (OVERRIDE_NO_FRICTION, 'Allow without confirmation'),
    ]

    # --- Core fields ---
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='operating_blueprint',
    )

    operating_style = models.CharField(
        max_length=20,
        choices=OPERATING_STYLE_CHOICES,
        default=STYLE_EXECUTIVE_COS,
        help_text="How the assistant communicates and operates",
    )

    persona_id = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Persona profile ID (maps to PIL). Empty = use operating_style default.",
    )

    interruption_tolerance = models.CharField(
        max_length=10,
        choices=INTERRUPTION_TOLERANCE_CHOICES,
        default=TOLERANCE_MEDIUM,
        help_text="How aggressively the assistant can interrupt",
    )

    auto_architect_enabled = models.BooleanField(
        default=True,
        help_text="Enable nightly 'Tomorrow Architecture Pass' and real-time re-optimization",
    )

    # --- Identity & Priority ---
    tier1_protected_behaviors = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "List of behavior keys that are Tier 1 (identity-protected). "
            "e.g. ['MEDS_ADHERENCE', 'FAITH_BLOCK', 'WORKOUT', 'NUTRITION', 'GOAL_EXECUTION']"
        ),
    )

    pillars_ranked = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "User's life pillars ranked by importance. "
            "e.g. ['FAITH', 'HEALTH_DISCIPLINE', 'PURPOSE', 'ORGANIZE', 'REFLECTION']"
        ),
    )

    # --- Schedule & Capacity ---
    sleep_target_minutes = models.PositiveIntegerField(
        default=480,  # 8 hours
        help_text="Target sleep duration in minutes",
    )

    wake_time_policy = models.CharField(
        max_length=10,
        choices=WAKE_TIME_POLICY_CHOICES,
        default=WAKE_SUGGEST,
        help_text="How wake time recommendations work",
    )

    preferred_architecture_time = models.TimeField(
        default='21:00',
        help_text="When to run the nightly architecture pass (local time)",
    )

    override_policy = models.CharField(
        max_length=25,
        choices=OVERRIDE_POLICY_CHOICES,
        default=OVERRIDE_WITH_FRICTION,
        help_text="Policy for overriding non-Tier-1 scheduled items",
    )

    # --- Module/Feature snapshots ---
    module_flags_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Snapshot of enabled modules. "
            "e.g. {'journal': true, 'health': true, 'faith': false, ...}"
        ),
    )

    sub_feature_flags_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Snapshot of enabled sub-features. "
            "e.g. {'health.weight': true, 'health.cycle': false, ...}"
        ),
    )

    # --- Metadata ---
    last_architecture_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the last architecture pass completed",
    )

    version = models.PositiveIntegerField(
        default=1,
        help_text="Blueprint version for migration tracking",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Personal Operating Blueprint"
        verbose_name_plural = "Personal Operating Blueprints"

    def __str__(self):
        return f"Blueprint for {self.user.email} (v{self.version})"

    # --- Convenience methods ---

    def is_module_enabled(self, module_key):
        """Check if a module is enabled in the blueprint snapshot."""
        return self.module_flags_snapshot.get(module_key, False)

    def is_feature_enabled(self, feature_key):
        """Check if a sub-feature is enabled (e.g. 'health.weight')."""
        return self.sub_feature_flags_snapshot.get(feature_key, False)

    def get_tier_for_behavior(self, behavior_key):
        """
        Return the tier level for a behavior.
        Tier 1 = identity protected (from tier1_protected_behaviors)
        Tier 2 = directional (non-negotiables not in tier1)
        Tier 3 = administrative (scheduled but flexible)
        Tier 4 = optional
        """
        if behavior_key in (self.tier1_protected_behaviors or []):
            return 1
        # Check if it's a non-negotiable
        if self.non_negotiables.filter(behavior_key=behavior_key, is_active=True).exists():
            return 2
        return 4  # Default to optional; tier 3 assigned by architecture engine

    def get_pillar_weight(self, pillar_key):
        """
        Return a weight (0-1) for a pillar based on its rank position.
        First pillar = 1.0, last = lowest weight.
        """
        pillars = self.pillars_ranked or []
        if not pillars or pillar_key not in pillars:
            return 0.3  # Default weight for unranked
        index = pillars.index(pillar_key)
        total = len(pillars)
        return round(1.0 - (index * 0.8 / max(total - 1, 1)), 2)

    def sync_module_flags(self):
        """
        Sync module_flags_snapshot from the user's current preferences.
        Called when blueprint is saved or preferences change.
        """
        try:
            prefs = self.user.preferences
        except Exception:
            return

        self.module_flags_snapshot = {
            'journal': prefs.journal_enabled,
            'health': prefs.health_enabled,
            'faith': prefs.faith_enabled,
            'life': prefs.life_enabled,
            'purpose': prefs.purpose_enabled,
            'finance': prefs.finances_enabled,
            'capture': prefs.capture_enabled,
            'ai': prefs.ai_enabled,
        }

        # Sub-features
        sub_features = {}
        if hasattr(prefs, 'health_features') and prefs.health_features:
            for key, val in prefs.health_features.items():
                sub_features[f'health.{key}'] = val
        if hasattr(prefs, 'organize_features') and prefs.organize_features:
            for key, val in prefs.organize_features.items():
                sub_features[f'life.{key}'] = val
        if hasattr(prefs, 'goals_features') and prefs.goals_features:
            for key, val in prefs.goals_features.items():
                sub_features[f'purpose.{key}'] = val
        if hasattr(prefs, 'faith_features') and prefs.faith_features:
            for key, val in prefs.faith_features.items():
                sub_features[f'faith.{key}'] = val
        if hasattr(prefs, 'journal_features') and prefs.journal_features:
            for key, val in prefs.journal_features.items():
                sub_features[f'journal.{key}'] = val

        self.sub_feature_flags_snapshot = sub_features

    @classmethod
    def get_or_create_for_user(cls, user):
        """
        Get or create the blueprint for a user, syncing module flags on creation.
        """
        blueprint, created = cls.objects.get_or_create(user=user)
        if created:
            blueprint.sync_module_flags()
            # Set default pillars based on enabled modules
            pillars = []
            if blueprint.module_flags_snapshot.get('faith'):
                pillars.append('FAITH')
            if blueprint.module_flags_snapshot.get('health'):
                pillars.append('HEALTH_DISCIPLINE')
            if blueprint.module_flags_snapshot.get('purpose'):
                pillars.append('PURPOSE')
            if blueprint.module_flags_snapshot.get('life'):
                pillars.append('ORGANIZE')
            if blueprint.module_flags_snapshot.get('journal'):
                pillars.append('REFLECTION')
            blueprint.pillars_ranked = pillars
            blueprint.save()
        return blueprint


# =============================================================================
# NON-NEGOTIABLES
# =============================================================================


class NonNegotiable(models.Model):
    """
    A specific behavior the user has marked as non-negotiable.
    These carry scheduling metadata for the architecture engine.
    """

    FREQUENCY_DAILY = 'daily'
    FREQUENCY_WEEKDAYS = 'weekdays'
    FREQUENCY_WEEKLY = 'weekly'
    FREQUENCY_CUSTOM = 'custom'

    FREQUENCY_CHOICES = [
        (FREQUENCY_DAILY, 'Every day'),
        (FREQUENCY_WEEKDAYS, 'Weekdays only'),
        (FREQUENCY_WEEKLY, 'Weekly'),
        (FREQUENCY_CUSTOM, 'Custom days'),
    ]

    blueprint = models.ForeignKey(
        PersonalOperatingBlueprint,
        on_delete=models.CASCADE,
        related_name='non_negotiables',
    )

    behavior_key = models.CharField(
        max_length=50,
        help_text="Behavior identifier e.g. 'WORKOUT', 'MEDS_ADHERENCE', 'FAITH_BLOCK'",
    )

    display_name = models.CharField(
        max_length=100,
        help_text="Human-readable name shown to user",
    )

    pillar = models.CharField(
        max_length=30,
        blank=True,
        help_text="Which pillar this belongs to (e.g. 'HEALTH_DISCIPLINE', 'FAITH')",
    )

    min_duration_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Minimum time required for this behavior",
    )

    preferred_time_window_start = models.TimeField(
        null=True,
        blank=True,
        help_text="Earliest preferred start time",
    )

    preferred_time_window_end = models.TimeField(
        null=True,
        blank=True,
        help_text="Latest preferred end time",
    )

    frequency = models.CharField(
        max_length=10,
        choices=FREQUENCY_CHOICES,
        default=FREQUENCY_DAILY,
    )

    custom_days = models.JSONField(
        default=list,
        blank=True,
        help_text="List of day numbers (0=Mon, 6=Sun) for custom frequency",
    )

    hard_deadline = models.TimeField(
        null=True,
        blank=True,
        help_text="Hard deadline by which this must be completed",
    )

    module_key = models.CharField(
        max_length=30,
        blank=True,
        help_text="Module this behavior belongs to (for feature flag checking)",
    )

    feature_key = models.CharField(
        max_length=50,
        blank=True,
        help_text="Sub-feature key (for feature flag checking)",
    )

    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'behavior_key']
        unique_together = ['blueprint', 'behavior_key']
        verbose_name = "Non-Negotiable"
        verbose_name_plural = "Non-Negotiables"

    def __str__(self):
        return f"{self.display_name} ({self.behavior_key})"

    def is_applicable_today(self, date=None):
        """Check if this non-negotiable applies to a given date."""
        if not self.is_active:
            return False

        if date is None:
            date = timezone.localdate()

        weekday = date.weekday()  # 0=Monday

        if self.frequency == self.FREQUENCY_DAILY:
            return True
        elif self.frequency == self.FREQUENCY_WEEKDAYS:
            return weekday < 5
        elif self.frequency == self.FREQUENCY_WEEKLY:
            # Default to Monday if no custom days
            return weekday == 0
        elif self.frequency == self.FREQUENCY_CUSTOM:
            return weekday in (self.custom_days or [])
        return False

    def is_feature_enabled(self, blueprint):
        """Check if this non-negotiable's module/feature is enabled."""
        if self.module_key and not blueprint.is_module_enabled(self.module_key):
            return False
        if self.feature_key and not blueprint.is_feature_enabled(self.feature_key):
            return False
        return True


# =============================================================================
# ARCHITECTURE PLAN (DAILY SCHEDULING)
# =============================================================================


class ArchitecturePlan(models.Model):
    """
    A daily architecture plan generated by the nightly pass or curveball re-optimization.
    Contains the recommended schedule and risk warnings.
    """

    STATUS_DRAFT = 'draft'
    STATUS_ACTIVE = 'active'
    STATUS_SUPERSEDED = 'superseded'
    STATUS_COMPLETED = 'completed'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_SUPERSEDED, 'Superseded'),
        (STATUS_COMPLETED, 'Completed'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='architecture_plans',
    )

    date = models.DateField(
        help_text="The date this plan is for",
    )

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )

    # Schedule recommendations
    recommended_wake_time = models.TimeField(
        null=True,
        blank=True,
    )
    recommended_sleep_time = models.TimeField(
        null=True,
        blank=True,
    )

    # Risk and cost summary
    risk_warnings = models.JSONField(
        default=list,
        blank=True,
        help_text="List of risk warning strings",
    )
    identity_cost_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Summary of identity costs for this plan",
    )
    suggested_moves = models.JSONField(
        default=list,
        blank=True,
        help_text="List of suggested schedule modifications",
    )

    # Generation metadata
    generation_trigger = models.CharField(
        max_length=30,
        default='nightly',
        help_text="What triggered this plan: 'nightly', 'curveball', 'manual'",
    )
    curveball_description = models.TextField(
        blank=True,
        help_text="Description of the curveball event that triggered re-optimization",
    )

    # E3 evidence
    evidence_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="E3 evidence attached to this plan",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = "Architecture Plan"
        verbose_name_plural = "Architecture Plans"
        indexes = [
            models.Index(fields=['user', 'date', 'status']),
        ]

    def __str__(self):
        return f"Plan for {self.user.email} on {self.date} ({self.status})"

    def activate(self):
        """Activate this plan and supersede any previous active plan for this date."""
        ArchitecturePlan.objects.filter(
            user=self.user,
            date=self.date,
            status=self.STATUS_ACTIVE,
        ).exclude(pk=self.pk).update(status=self.STATUS_SUPERSEDED)

        self.status = self.STATUS_ACTIVE
        self.save(update_fields=['status', 'updated_at'])

    @classmethod
    def get_active_for_date(cls, user, date=None):
        """Get the currently active plan for a date."""
        if date is None:
            date = timezone.localdate()
        return cls.objects.filter(
            user=user,
            date=date,
            status=cls.STATUS_ACTIVE,
        ).first()


class ScheduledBlock(models.Model):
    """
    An individual time block within an architecture plan.
    """

    TIER_CHOICES = [
        (1, 'Tier 1 - Identity Protected'),
        (2, 'Tier 2 - Directional Commitment'),
        (3, 'Tier 3 - Administrative'),
        (4, 'Tier 4 - Optional'),
    ]

    SOURCE_NON_NEGOTIABLE = 'non_negotiable'
    SOURCE_CALENDAR = 'calendar'
    SOURCE_TASK = 'task'
    SOURCE_HEALTH = 'health'
    SOURCE_SLEEP = 'sleep'
    SOURCE_BUFFER = 'buffer'

    SOURCE_CHOICES = [
        (SOURCE_NON_NEGOTIABLE, 'Non-Negotiable'),
        (SOURCE_CALENDAR, 'Calendar Event'),
        (SOURCE_TASK, 'Task/Deadline'),
        (SOURCE_HEALTH, 'Health Commitment'),
        (SOURCE_SLEEP, 'Sleep'),
        (SOURCE_BUFFER, 'Buffer/Transition'),
    ]

    plan = models.ForeignKey(
        ArchitecturePlan,
        on_delete=models.CASCADE,
        related_name='blocks',
    )

    start_time = models.TimeField()
    end_time = models.TimeField()

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    tier = models.PositiveSmallIntegerField(
        choices=TIER_CHOICES,
        default=4,
    )

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_BUFFER,
    )

    source_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="ID of the source object (event ID, task ID, non-negotiable key)",
    )

    is_locked = models.BooleanField(
        default=False,
        help_text="Locked blocks cannot be moved by re-optimization",
    )

    rationale = models.TextField(
        blank=True,
        help_text="Why this block was placed here (E3 explanation)",
    )

    behavior_key = models.CharField(
        max_length=50,
        blank=True,
        help_text="Associated behavior key for drift tracking",
    )

    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['start_time']
        verbose_name = "Scheduled Block"
        verbose_name_plural = "Scheduled Blocks"

    def __str__(self):
        return f"{self.start_time}-{self.end_time}: {self.title} (T{self.tier})"


# =============================================================================
# DRIFT DETECTION
# =============================================================================


class DriftEvent(models.Model):
    """
    An individual drift event - a deviation from the plan or expected behavior.
    """

    # Standard drift event types
    DRIFT_FAST_BREAK_EARLY = 'FAST_BREAK_EARLY'
    DRIFT_MED_MISSED = 'MED_MISSED'
    DRIFT_WORKOUT_SKIPPED = 'WORKOUT_SKIPPED'
    DRIFT_NUTRITION_OFF_TRACK = 'NUTRITION_OFF_TRACK'
    DRIFT_FAITH_BLOCK_MISSED = 'FAITH_BLOCK_MISSED'
    DRIFT_GOAL_SLIP = 'GOAL_SLIP'
    DRIFT_SLEEP_DEFICIT = 'SLEEP_DEFICIT'
    DRIFT_BLOCK_MISSED = 'BLOCK_MISSED'  # Generic scheduled block miss

    DRIFT_TYPE_CHOICES = [
        (DRIFT_FAST_BREAK_EARLY, 'Broke fast early'),
        (DRIFT_MED_MISSED, 'Medication missed'),
        (DRIFT_WORKOUT_SKIPPED, 'Workout skipped'),
        (DRIFT_NUTRITION_OFF_TRACK, 'Nutrition off track'),
        (DRIFT_FAITH_BLOCK_MISSED, 'Faith block missed'),
        (DRIFT_GOAL_SLIP, 'Goal progress slip'),
        (DRIFT_SLEEP_DEFICIT, 'Sleep deficit'),
        (DRIFT_BLOCK_MISSED, 'Scheduled block missed'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='drift_events',
    )

    drift_type = models.CharField(
        max_length=30,
        choices=DRIFT_TYPE_CHOICES,
        db_index=True,
    )

    date = models.DateField(db_index=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    behavior_key = models.CharField(
        max_length=50,
        blank=True,
        help_text="Associated behavior key",
    )

    tier = models.PositiveSmallIntegerField(
        default=4,
        help_text="Tier level of the drifted behavior",
    )

    pillar = models.CharField(
        max_length=30,
        blank=True,
        help_text="Pillar this drift impacts",
    )

    severity = models.FloatField(
        default=0.5,
        help_text="Severity score 0-1 (1 = most severe)",
    )

    description = models.TextField(
        blank=True,
        help_text="Human-readable description of the drift",
    )

    evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text="E3 evidence data",
    )

    # Was this drift acknowledged/resolved?
    is_acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    recovery_plan = models.TextField(
        blank=True,
        help_text="Recovery plan if tier 1 was impacted",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-occurred_at']
        verbose_name = "Drift Event"
        verbose_name_plural = "Drift Events"
        indexes = [
            models.Index(fields=['user', 'date', 'drift_type']),
        ]

    def __str__(self):
        return f"{self.get_drift_type_display()} for {self.user.email} on {self.date}"


class DriftScore(models.Model):
    """
    Daily aggregate drift score for a user.
    Weighted by pillar importance from the blueprint.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='drift_scores',
    )

    date = models.DateField(db_index=True)

    score = models.FloatField(
        default=0.0,
        help_text="Aggregate drift score 0-100 (100 = maximum drift)",
    )

    pillar_scores = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-pillar drift scores",
    )

    event_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of drift events this day",
    )

    # Predictive fields
    drift_probability_24h = models.FloatField(
        default=0.0,
        help_text="Predicted probability of drift in next 24h (0-1)",
    )
    drift_probability_72h = models.FloatField(
        default=0.0,
        help_text="Predicted probability of drift in next 72h (0-1)",
    )

    prediction_factors = models.JSONField(
        default=dict,
        blank=True,
        help_text="Factors contributing to drift prediction",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        unique_together = ['user', 'date']
        verbose_name = "Drift Score"
        verbose_name_plural = "Drift Scores"

    def __str__(self):
        return f"Drift {self.score:.0f}/100 for {self.user.email} on {self.date}"


# =============================================================================
# INTERVENTION & FRICTION
# =============================================================================


class InterventionLog(models.Model):
    """
    Record of assistant interventions (nudges, pings, interrupts, friction gates).
    """

    LEVEL_SILENT = 0
    LEVEL_NUDGE = 1
    LEVEL_PING = 2
    LEVEL_INTERRUPT = 3
    LEVEL_FRICTION_GATE = 4

    LEVEL_CHOICES = [
        (LEVEL_SILENT, 'Silent'),
        (LEVEL_NUDGE, 'Nudge'),
        (LEVEL_PING, 'Ping'),
        (LEVEL_INTERRUPT, 'Interrupt'),
        (LEVEL_FRICTION_GATE, 'Friction Gate'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='intervention_logs',
    )

    level = models.PositiveSmallIntegerField(
        choices=LEVEL_CHOICES,
        default=LEVEL_NUDGE,
    )

    trigger_type = models.CharField(
        max_length=50,
        help_text="What triggered this intervention (e.g. 'tier1_violation', 'drift_spike')",
    )

    behavior_key = models.CharField(
        max_length=50,
        blank=True,
    )

    message = models.TextField(
        help_text="The intervention message shown to user",
    )

    evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text="E3 evidence data for this intervention",
    )

    # User response
    RESPONSE_PENDING = 'pending'
    RESPONSE_ACCEPTED = 'accepted'
    RESPONSE_DISMISSED = 'dismissed'
    RESPONSE_PROCEEDED = 'proceeded'
    RESPONSE_ADJUSTED = 'adjusted'

    RESPONSE_CHOICES = [
        (RESPONSE_PENDING, 'Pending'),
        (RESPONSE_ACCEPTED, 'Accepted'),
        (RESPONSE_DISMISSED, 'Dismissed'),
        (RESPONSE_PROCEEDED, 'Proceeded Anyway'),
        (RESPONSE_ADJUSTED, 'Adjusted Plan'),
    ]

    user_response = models.CharField(
        max_length=15,
        choices=RESPONSE_CHOICES,
        default=RESPONSE_PENDING,
    )
    responded_at = models.DateTimeField(null=True, blank=True)

    # Delivery tracking
    delivered_via = models.CharField(
        max_length=30,
        blank=True,
        help_text="Channel: 'in_app', 'push', 'panel', 'modal'",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Intervention Log"
        verbose_name_plural = "Intervention Logs"
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['user', 'level', 'created_at']),
        ]

    def __str__(self):
        return f"L{self.level} intervention for {self.user.email}: {self.trigger_type}"

    def record_response(self, response, **kwargs):
        """Record the user's response to this intervention."""
        self.user_response = response
        self.responded_at = timezone.now()
        self.save(update_fields=['user_response', 'responded_at'])
