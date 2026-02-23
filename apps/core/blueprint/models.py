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

    # --- Governance Profile ---
    ACCOUNTABILITY_LIGHT = 'light'
    ACCOUNTABILITY_STANDARD = 'standard'
    ACCOUNTABILITY_FIRM = 'firm'
    ACCOUNTABILITY_CHOICES = [
        (ACCOUNTABILITY_LIGHT, 'Light'),
        (ACCOUNTABILITY_STANDARD, 'Standard'),
        (ACCOUNTABILITY_FIRM, 'Firm'),
    ]

    QUESTION_LOW = 'low'
    QUESTION_MEDIUM = 'medium'
    QUESTION_HIGH = 'high'
    QUESTION_FREQUENCY_CHOICES = [
        (QUESTION_LOW, 'Low'),
        (QUESTION_MEDIUM, 'Medium'),
        (QUESTION_HIGH, 'High'),
    ]

    accountability_style = models.CharField(
        max_length=10,
        choices=ACCOUNTABILITY_CHOICES,
        default=ACCOUNTABILITY_STANDARD,
        help_text="How firm the CoS should be (light/standard/firm)",
    )

    question_frequency = models.CharField(
        max_length=10,
        choices=QUESTION_FREQUENCY_CHOICES,
        default=QUESTION_MEDIUM,
        help_text="How often CoS asks questions (low/medium/high)",
    )

    relationship_suggestions_enabled = models.BooleanField(
        default=False,
        help_text="Whether CoS suggests relationship actions",
    )

    event_reflections_enabled = models.BooleanField(
        default=True,
        help_text="Whether CoS follows up after events with reflections",
    )

    sensitivity_tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Topics requiring sensitivity (e.g. ['medicine','relationships','faith'])",
    )

    cos_learning_mode_active = models.BooleanField(
        default=False,
        help_text=(
            "Independent Learning Mode toggle. When True, UAIO execution, "
            "PIE, PRIE, and domain writes are suppressed. SAE reads and "
            "governance evaluation remain active."
        ),
    )

    calibration_day = models.PositiveSmallIntegerField(
        default=0,
        help_text="Day counter for calibration mode (0-14)",
    )

    calibration_complete = models.BooleanField(
        default=False,
        help_text="Whether initial calibration period is complete",
    )

    governance_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text="User override history for CoS preferences",
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


# =============================================================================
# EVENT REFLECTION
# =============================================================================


class EventReflection(models.Model):
    """
    A pending or completed post-event reflection check-in.

    Created by the reflection engine after meetings, workouts, social events,
    and other meaningful activities. Delivered via Command Mode or chat.
    """

    SOURCE_CALENDAR = 'calendar'
    SOURCE_WORKOUT = 'workout'
    SOURCE_SOCIAL = 'social'
    SOURCE_HEALTH = 'health'

    SOURCE_TYPE_CHOICES = [
        (SOURCE_CALENDAR, 'Calendar Event'),
        (SOURCE_WORKOUT, 'Workout'),
        (SOURCE_SOCIAL, 'Social Event'),
        (SOURCE_HEALTH, 'Health Anomaly'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_DELIVERED = 'delivered'
    STATUS_COMPLETED = 'completed'
    STATUS_SKIPPED = 'skipped'
    STATUS_EXPIRED = 'expired'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_DELIVERED, 'Delivered'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_SKIPPED, 'Skipped'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='event_reflections',
    )

    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_TYPE_CHOICES,
    )

    source_id = models.CharField(
        max_length=100,
        help_text="ID of the source object (LifeEvent.id, WorkoutSession.id, etc.)",
    )

    source_title = models.CharField(max_length=200)
    event_date = models.DateField()

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    scheduled_for = models.DateTimeField(
        help_text="When to deliver this reflection (12-24h after event)",
    )

    questions = models.JSONField(
        default=list,
        blank=True,
        help_text="Pre-generated reflection questions",
    )

    answers = models.JSONField(
        default=dict,
        blank=True,
        help_text="User responses keyed by question index",
    )

    action_items_created = models.JSONField(
        default=list,
        blank=True,
        help_text="Task/event IDs created from reflection answers",
    )

    delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_for']
        verbose_name = "Event Reflection"
        verbose_name_plural = "Event Reflections"
        indexes = [
            models.Index(fields=['user', 'status', 'scheduled_for']),
        ]

    def __str__(self):
        return f"Reflection on '{self.source_title}' for {self.user.email} ({self.status})"

    def mark_delivered(self):
        """Mark this reflection as delivered to the user."""
        self.status = self.STATUS_DELIVERED
        self.delivered_at = timezone.now()
        self.save(update_fields=['status', 'delivered_at', 'updated_at'])

    def mark_completed(self, answers=None, action_items=None):
        """Mark this reflection as completed with optional answers and action items."""
        self.status = self.STATUS_COMPLETED
        self.completed_at = timezone.now()
        if answers:
            self.answers = answers
        if action_items:
            self.action_items_created = action_items
        self.save(update_fields=[
            'status', 'completed_at', 'answers',
            'action_items_created', 'updated_at',
        ])

    def mark_skipped(self):
        """Mark this reflection as skipped by the user."""
        self.status = self.STATUS_SKIPPED
        self.save(update_fields=['status', 'updated_at'])

    def expire_if_stale(self):
        """Expire if more than 48h past scheduled time and still pending."""
        if self.status == self.STATUS_PENDING:
            cutoff = self.scheduled_for + timezone.timedelta(hours=48)
            if timezone.now() > cutoff:
                self.status = self.STATUS_EXPIRED
                self.save(update_fields=['status', 'updated_at'])


# =============================================================================
# USER PRIORITY PROFILE (Phase 1 — CoS Foundational Restructure)
# =============================================================================


class UserPriorityProfile(models.Model):
    """
    Per-module declared priority with importance weighting.

    This is an extension layer that complements (does NOT replace):
    - PersonalOperatingBlueprint.pillars_ranked
    - PersonalOperatingBlueprint.tier1_protected_behaviors
    - NonNegotiable model

    During Learning Mode onboarding, the user declares which modules and
    sub-modules matter most. The PriorityConflictDetector compares these
    declarations against actual 7-day behavior patterns.

    Internal tier mapping:
        1 = Non-Negotiable (weight 3.0)
        2 = Important (weight 2.0)
        3 = Flexible (weight 1.0)

    User-facing language never uses "tier" labels.
    """

    PRIORITY_NON_NEGOTIABLE = 1
    PRIORITY_IMPORTANT = 2
    PRIORITY_FLEXIBLE = 3

    PRIORITY_CHOICES = [
        (PRIORITY_NON_NEGOTIABLE, 'Non-Negotiable'),
        (PRIORITY_IMPORTANT, 'Important'),
        (PRIORITY_FLEXIBLE, 'Flexible'),
    ]

    WEIGHT_MAP = {
        PRIORITY_NON_NEGOTIABLE: 3.0,
        PRIORITY_IMPORTANT: 2.0,
        PRIORITY_FLEXIBLE: 1.0,
    }

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='priority_profiles',
    )

    module_key = models.CharField(
        max_length=30,
        help_text="Top-level module (e.g. 'health', 'faith', 'purpose')",
    )

    sub_module_key = models.CharField(
        max_length=60,
        blank=True,
        default='',
        help_text=(
            "Sub-module path (e.g. 'health.weight', 'health.cognitive.focus'). "
            "Empty string = module-level priority."
        ),
    )

    declared_priority_level = models.PositiveSmallIntegerField(
        choices=PRIORITY_CHOICES,
        default=PRIORITY_FLEXIBLE,
        help_text="1=Non-Negotiable, 2=Important, 3=Flexible",
    )

    importance_weight = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=1.0,
        help_text="Derived from priority level: 3.0 / 2.0 / 1.0",
    )

    declared_reason = models.TextField(
        blank=True,
        help_text="Why this matters to the user (from Learning Mode conversation)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-importance_weight', 'module_key', 'sub_module_key']
        unique_together = ['user', 'module_key', 'sub_module_key']
        verbose_name = "User Priority Profile"
        verbose_name_plural = "User Priority Profiles"

    def __str__(self):
        level = self.get_declared_priority_level_display()
        sub = f".{self.sub_module_key}" if self.sub_module_key else ""
        return f"{self.module_key}{sub} → {level} (w={self.importance_weight})"

    def save(self, *args, **kwargs):
        """Auto-set importance_weight from declared_priority_level."""
        self.importance_weight = self.WEIGHT_MAP.get(
            self.declared_priority_level, 1.0
        )
        super().save(*args, **kwargs)

    @classmethod
    def get_user_priorities(cls, user, module_key=None):
        """
        Get all declared priorities for a user, optionally filtered by module.

        Returns:
            QuerySet of UserPriorityProfile instances.
        """
        qs = cls.objects.filter(user=user)
        if module_key:
            qs = qs.filter(module_key=module_key)
        return qs

    @classmethod
    def get_non_negotiables(cls, user):
        """Get all priorities declared as non-negotiable."""
        return cls.objects.filter(
            user=user,
            declared_priority_level=cls.PRIORITY_NON_NEGOTIABLE,
        )


# =============================================================================
# EXECUTIVE COMMITMENT CONTRACT (ECC) — PERSISTENT MODELS
# =============================================================================


class Commitment(models.Model):
    """
    Persistent commitment record for the Executive Commitment Contract (ECC).

    Commitments are user-global — they belong to a user, not a conversation.
    The conversation FK is optional traceability for where the commitment
    was created. Closure allowed from any conversation.

    Hard limit: MAX 5 active pending commitments per user.
    """

    # Commitment types
    TYPE_DO = 'DO'
    TYPE_DECIDE = 'DECIDE'
    TYPE_SCHEDULE = 'SCHEDULE'
    TYPE_STOP = 'STOP'

    COMMITMENT_TYPE_CHOICES = [
        (TYPE_DO, 'Do'),
        (TYPE_DECIDE, 'Decide'),
        (TYPE_SCHEDULE, 'Schedule'),
        (TYPE_STOP, 'Stop'),
    ]

    # Status lifecycle
    STATUS_PENDING = 'pending'
    STATUS_CLOSED_SUCCESS = 'closed_success'
    STATUS_CLOSED_MISSED = 'closed_missed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_RENEGOTIATED = 'renegotiated'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_CLOSED_SUCCESS, 'Closed — Honored'),
        (STATUS_CLOSED_MISSED, 'Closed — Missed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_RENEGOTIATED, 'Renegotiated'),
    ]

    # Closure types
    CLOSURE_USER_CONFIRMED = 'user_confirmed'
    CLOSURE_USER_MISSED = 'user_missed'
    CLOSURE_CANCELLED = 'cancelled'
    CLOSURE_RENEGOTIATED = 'renegotiated'
    CLOSURE_EXPIRED = 'expired'

    CLOSURE_TYPE_CHOICES = [
        (CLOSURE_USER_CONFIRMED, 'User Confirmed Done'),
        (CLOSURE_USER_MISSED, 'User Confirmed Missed'),
        (CLOSURE_CANCELLED, 'Cancelled'),
        (CLOSURE_RENEGOTIATED, 'Replaced by Renegotiation'),
        (CLOSURE_EXPIRED, 'Expired Past Deadline'),
    ]

    MAX_PENDING_PER_USER = 5

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='commitments',
    )

    # Optional traceability — NOT ownership
    conversation = models.ForeignKey(
        'ai.AssistantConversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='commitments',
        help_text="Conversation where this commitment was created (traceability only)",
    )

    normalized_text = models.TextField(
        help_text="The commitment action text (case-preserved)",
    )

    commitment_type = models.CharField(
        max_length=10,
        choices=COMMITMENT_TYPE_CHOICES,
        default=TYPE_DO,
    )

    time_boundary = models.DateTimeField(
        help_text="Concrete deadline for this commitment",
    )

    time_boundary_display = models.CharField(
        max_length=100,
        blank=True,
        help_text="Human-readable time phrase (e.g., 'by tomorrow at 5pm')",
    )

    done_definition = models.TextField(
        blank=True,
        help_text="One-sentence definition of done. Required only for vague actions.",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    closure_type = models.CharField(
        max_length=20,
        choices=CLOSURE_TYPE_CHOICES,
        blank=True,
    )

    closed_at = models.DateTimeField(null=True, blank=True)

    # Tier at creation — for historical analysis
    tier_at_creation = models.CharField(
        max_length=20,
        blank=True,
        help_text="CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT at commitment time",
    )

    # Phase 2: Timezone tracking for local-intent preservation
    timezone_at_creation = models.CharField(
        max_length=50,
        blank=True,
        help_text="IANA timezone at commitment creation (e.g., 'America/New_York')",
    )

    timezone_at_last_recalculation = models.CharField(
        max_length=50,
        blank=True,
        help_text="IANA timezone when time_boundary was last recalculated due to timezone change",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Commitment"
        verbose_name_plural = "Commitments"
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'time_boundary']),
            models.Index(fields=['user', 'status', 'created_at']),
        ]

    def __str__(self):
        return f"[{self.commitment_type}] {self.normalized_text} ({self.status})"

    @classmethod
    def pending_for_user(cls, user):
        """Get all pending commitments for a user."""
        return cls.objects.filter(user=user, status=cls.STATUS_PENDING)

    @classmethod
    def can_create(cls, user):
        """Check if user can create another commitment (hard limit: 5)."""
        return cls.pending_for_user(user).count() < cls.MAX_PENDING_PER_USER

    def close(self, status, closure_type):
        """Close this commitment with given status and closure type."""
        self.status = status
        self.closure_type = closure_type
        self.closed_at = timezone.now()
        self.save(update_fields=['status', 'closure_type', 'closed_at', 'updated_at'])

    def recalculate_timezone(self, new_timezone_iana):
        """
        Phase 2: Local-intent preservation on timezone change.

        Preserves the original wall-clock time and recalculates the UTC
        value using the new timezone. Only affects pending commitments.

        Args:
            new_timezone_iana: str — new IANA timezone (e.g., 'America/Los_Angeles').

        Returns:
            bool — True if recalculated, False if skipped.
        """
        from zoneinfo import ZoneInfo

        if self.status != self.STATUS_PENDING:
            return False

        old_tz_name = self.timezone_at_creation or 'UTC'
        old_tz = ZoneInfo(old_tz_name)
        new_tz = ZoneInfo(new_timezone_iana)

        # Extract wall-clock time in the original timezone
        wall_clock = self.time_boundary.astimezone(old_tz)
        naive_wall = wall_clock.replace(tzinfo=None)

        # Reattach with new timezone (preserving wall-clock, fold=0)
        new_aware = naive_wall.replace(tzinfo=new_tz, fold=0)

        self.time_boundary = new_aware
        self.timezone_at_last_recalculation = new_timezone_iana
        self.save(update_fields=[
            'time_boundary', 'timezone_at_last_recalculation', 'updated_at',
        ])
        return True


class CommitmentRenegotiation(models.Model):
    """
    Historical record of a renegotiation attempt on a commitment.

    Tracks both successful (CLEAN tier) and blocked (EROSION/DRIFT tier)
    renegotiations for accountability audit trails.
    """

    CHOICE_A = 'A'  # Keep with minimum version
    CHOICE_B = 'B'  # Cancel and accept consequence

    BLOCKED_CHOICE_CHOICES = [
        (CHOICE_A, 'Keep original with minimum version'),
        (CHOICE_B, 'Cancel and accept consequence'),
    ]

    commitment = models.ForeignKey(
        Commitment,
        on_delete=models.CASCADE,
        related_name='renegotiations',
    )

    original_time_boundary = models.DateTimeField(
        help_text="Time boundary before renegotiation attempt",
    )

    requested_time_boundary = models.DateTimeField(
        null=True,
        blank=True,
        help_text="New time boundary requested (null if no new time provided)",
    )

    tier_at_time = models.CharField(
        max_length=20,
        help_text="CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT at renegotiation time",
    )

    was_blocked = models.BooleanField(
        default=False,
        help_text="True if renegotiation was blocked due to tier",
    )

    blocked_choice_selected = models.CharField(
        max_length=1,
        choices=BLOCKED_CHOICE_CHOICES,
        blank=True,
        help_text="Which choice user selected when blocked (A or B)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Commitment Renegotiation"
        verbose_name_plural = "Commitment Renegotiations"
        indexes = [
            models.Index(fields=['commitment', 'created_at']),
        ]

    def __str__(self):
        status = "blocked" if self.was_blocked else "allowed"
        return f"Renegotiation ({status}) on {self.commitment}"


class CommitmentAnalytics(models.Model):
    """
    Daily rollup of commitment metrics per user.

    Computed by a daily management command or signal-driven update.
    Foundation for accountability dashboards and trend analysis.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='commitment_analytics',
    )

    date = models.DateField()

    commitments_made = models.PositiveIntegerField(default=0)
    commitments_honored = models.PositiveIntegerField(default=0)
    commitments_missed = models.PositiveIntegerField(default=0)
    commitments_renegotiated = models.PositiveIntegerField(default=0)
    commitments_cancelled = models.PositiveIntegerField(default=0)

    honor_rate = models.FloatField(
        default=0.0,
        help_text="Ratio of honored / (honored + missed), 0-1",
    )

    avg_time_to_closure_minutes = models.FloatField(
        default=0.0,
        help_text="Average minutes from creation to closure",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        unique_together = ['user', 'date']
        verbose_name = "Commitment Analytics"
        verbose_name_plural = "Commitment Analytics"

    def __str__(self):
        return f"Commitments for {self.user.email} on {self.date}: {self.honor_rate:.0%}"

    @classmethod
    def compute_for_date(cls, user, date):
        """Compute analytics for a specific date from Commitment records."""
        from django.db.models import Avg, F

        day_commitments = Commitment.objects.filter(
            user=user,
            created_at__date=date,
        )

        made = day_commitments.count()
        honored = day_commitments.filter(status=Commitment.STATUS_CLOSED_SUCCESS).count()
        missed = day_commitments.filter(status=Commitment.STATUS_CLOSED_MISSED).count()
        renegotiated = day_commitments.filter(status=Commitment.STATUS_RENEGOTIATED).count()
        cancelled = day_commitments.filter(status=Commitment.STATUS_CANCELLED).count()

        closed = honored + missed
        rate = honored / closed if closed > 0 else 0.0

        # Average time to closure in minutes
        closed_qs = day_commitments.filter(closed_at__isnull=False)
        avg_result = closed_qs.annotate(
            duration=F('closed_at') - F('created_at')
        ).aggregate(avg_duration=Avg('duration'))
        avg_duration = avg_result.get('avg_duration')
        avg_minutes = avg_duration.total_seconds() / 60.0 if avg_duration else 0.0

        analytics, _ = cls.objects.update_or_create(
            user=user,
            date=date,
            defaults={
                'commitments_made': made,
                'commitments_honored': honored,
                'commitments_missed': missed,
                'commitments_renegotiated': renegotiated,
                'commitments_cancelled': cancelled,
                'honor_rate': rate,
                'avg_time_to_closure_minutes': avg_minutes,
            },
        )
        return analytics


# =============================================================================
# PHASE 2 — TIME & DEADLINE AUTHORITY MODELS
# =============================================================================


def recalculate_pending_commitments_for_timezone_change(user, new_timezone_iana):
    """
    Phase 2: Recalculate all pending commitment time boundaries when user
    changes timezone. Preserves local wall-clock intent.

    Args:
        user: User instance.
        new_timezone_iana: str — new IANA timezone.

    Returns:
        int — number of commitments recalculated.
    """
    import logging
    logger = logging.getLogger(__name__)

    pending = Commitment.pending_for_user(user)
    recalculated = 0
    for commitment in pending:
        if commitment.recalculate_timezone(new_timezone_iana):
            recalculated += 1
            logger.info(
                "Phase 2: Recalculated commitment %d timezone %s → %s",
                commitment.pk,
                commitment.timezone_at_creation,
                new_timezone_iana,
            )

    return recalculated


class DeadlineSnapshot(models.Model):
    """
    Phase 2: ISE-driven deadline surfacing snapshot.

    Computed every 5 minutes by ISE. Read by build_cos_context().
    No deadline computation inside send_message().
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='deadline_snapshots',
    )

    due_24h = models.JSONField(
        default=list,
        help_text="Commitments/goals/blocks due within 24 hours",
    )

    due_72h = models.JSONField(
        default=list,
        help_text="Commitments/goals/blocks due within 72 hours (excluding 24h)",
    )

    due_7d = models.JSONField(
        default=list,
        help_text="Commitments/goals/blocks due within 7 days (excluding 72h)",
    )

    collision_flags = models.JSONField(
        default=list,
        help_text="Pairs of deadlines with <2h gap, or days with >3 hard deadlines",
    )

    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-computed_at']
        indexes = [
            models.Index(fields=['user', 'computed_at']),
        ]

    def __str__(self):
        total = len(self.due_24h) + len(self.due_72h) + len(self.due_7d)
        return f"DeadlineSnapshot for {self.user_id}: {total} items at {self.computed_at}"

    @classmethod
    def latest_for_user(cls, user):
        """Get the most recent snapshot for a user, or None."""
        return cls.objects.filter(user=user).order_by('-computed_at').first()

    def is_stale(self, max_age_minutes=10):
        """Check if this snapshot is older than max_age_minutes."""
        age = (timezone.now() - self.computed_at).total_seconds() / 60
        return age > max_age_minutes


class Tier1OverrideEvent(models.Model):
    """
    Phase 2: Audit log for Tier 1 protected block overrides.

    Created when a user explicitly states "Override Tier 1 protection"
    to schedule over a Tier 1 block. Feeds into drift and pressure modeling.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tier1_overrides',
    )

    original_block = models.ForeignKey(
        'ScheduledBlock',
        on_delete=models.SET_NULL,
        null=True,
        related_name='override_events_original',
        help_text="The Tier 1 block that was overridden",
    )

    conflicting_block_description = models.TextField(
        help_text="Description of the block that was scheduled over Tier 1",
    )

    escalation_level_at_time = models.CharField(
        max_length=20,
        blank=True,
        help_text="CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT at override time",
    )

    density_score_at_time = models.FloatField(
        default=0.0,
        help_text="Calendar density score (0.0-1.0) at override time",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"Tier1Override by {self.user_id} at {self.created_at}"


# =========================================================================
# PHASE 3 — ESCALATION CONTINUITY MODELS
# =========================================================================


class EscalationState(models.Model):
    """
    Phase 3: Persistent per-user escalation state.

    Provides cross-session enforcement memory. The current_level acts as
    a FLOOR — activation can only decrease through the Hybrid Recovery Rule.
    """

    LEVEL_CLEAN = 0
    LEVEL_EARLY_EROSION = 1
    LEVEL_STRUCTURAL_DRIFT = 2

    LEVEL_CHOICES = [
        (LEVEL_CLEAN, 'CLEAN'),
        (LEVEL_EARLY_EROSION, 'EARLY_EROSION'),
        (LEVEL_STRUCTURAL_DRIFT, 'STRUCTURAL_DRIFT'),
    ]

    LEVEL_TO_STATE = {
        LEVEL_CLEAN: 'CLEAN',
        LEVEL_EARLY_EROSION: 'EARLY_EROSION',
        LEVEL_STRUCTURAL_DRIFT: 'STRUCTURAL_DRIFT',
    }

    STATE_TO_LEVEL = {v: k for k, v in LEVEL_TO_STATE.items()}

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='escalation_state',
    )

    current_level = models.PositiveSmallIntegerField(
        default=LEVEL_CLEAN,
        choices=LEVEL_CHOICES,
        help_text="Current escalation level (0=CLEAN, 1=EARLY_EROSION, 2=STRUCTURAL_DRIFT)",
    )

    peak_level_7d = models.PositiveSmallIntegerField(
        default=LEVEL_CLEAN,
        choices=LEVEL_CHOICES,
        help_text="Peak escalation level in last 7 days",
    )

    consecutive_clean_days = models.PositiveIntegerField(
        default=0,
        help_text="Number of consecutive clean days for recovery gate",
    )

    last_escalation_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When escalation last increased",
    )

    last_de_escalation_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When escalation last decreased (recovery gate passed)",
    )

    window_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Start of current recovery evaluation window",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Extra state metadata (recovery reasons, etc.)",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "escalation state"
        verbose_name_plural = "escalation states"
        indexes = [
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return (
            f"EscalationState user={self.user_id} "
            f"level={self.get_current_level_display()}"
        )

    @property
    def current_state_label(self):
        """Return string label for current_level."""
        return self.LEVEL_TO_STATE.get(self.current_level, 'CLEAN')

    @classmethod
    def get_or_create_for_user(cls, user):
        """Get or create EscalationState, returning (instance, created)."""
        return cls.objects.get_or_create(user=user)


class EscalationEvent(models.Model):
    """
    Phase 3: Immutable audit trail of escalation transitions.

    Every level change (up or down) is logged with trigger and rationale.
    """

    TRIGGER_THRESHOLD_OVERRIDE = 'THRESHOLD_OVERRIDE'
    TRIGGER_RECOVERY_DECAY = 'RECOVERY_DECAY'
    TRIGGER_EROSION_DETECTED = 'EROSION_DETECTED'
    TRIGGER_FLOOR_APPLIED = 'FLOOR_APPLIED'
    TRIGGER_DAILY_UPDATE = 'DAILY_UPDATE'

    TRIGGER_CHOICES = [
        (TRIGGER_THRESHOLD_OVERRIDE, 'Threshold Override'),
        (TRIGGER_RECOVERY_DECAY, 'Recovery Decay'),
        (TRIGGER_EROSION_DETECTED, 'Erosion Detected'),
        (TRIGGER_FLOOR_APPLIED, 'Floor Applied'),
        (TRIGGER_DAILY_UPDATE, 'Daily Update'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='escalation_events',
    )

    from_level = models.PositiveSmallIntegerField(
        help_text="Level before transition",
    )

    to_level = models.PositiveSmallIntegerField(
        help_text="Level after transition",
    )

    trigger = models.CharField(
        max_length=30,
        choices=TRIGGER_CHOICES,
        help_text="What caused this transition",
    )

    behavior_key = models.CharField(
        max_length=100,
        blank=True,
        help_text="Behavior key that triggered the event (if applicable)",
    )

    rationale = models.JSONField(
        default=dict,
        help_text="Detailed rationale for transition (recovery reasons, thresholds, etc.)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['user', 'to_level']),
        ]

    def __str__(self):
        return (
            f"EscalationEvent user={self.user_id} "
            f"{self.from_level}→{self.to_level} ({self.trigger})"
        )


class BehavioralTrend(models.Model):
    """
    Phase 3: Per-behavior-key trend tracking.

    Computed daily (deterministic). Stores latest trend per behavior_key
    per user, overwritten on each computation.
    """

    TREND_IMPROVING = 'improving'
    TREND_STABLE = 'stable'
    TREND_DECLINING = 'declining'

    TREND_CHOICES = [
        (TREND_IMPROVING, 'Improving'),
        (TREND_STABLE, 'Stable'),
        (TREND_DECLINING, 'Declining'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='behavioral_trends',
    )

    behavior_key = models.CharField(
        max_length=100,
        help_text="Behavior key being tracked (e.g., PRAYER, WORKOUT)",
    )

    trend_direction = models.CharField(
        max_length=10,
        choices=TREND_CHOICES,
        default=TREND_STABLE,
    )

    confidence = models.FloatField(
        default=0.0,
        help_text="Confidence in trend assessment (0.0-1.0)",
    )

    data_points = models.PositiveIntegerField(
        default=0,
        help_text="Number of events considered in computation",
    )

    window_start = models.DateField(
        help_text="Start of evaluation window",
    )

    window_end = models.DateField(
        help_text="End of evaluation window",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "behavioral trend"
        verbose_name_plural = "behavioral trends"
        unique_together = [('user', 'behavior_key')]
        indexes = [
            models.Index(fields=['user', 'behavior_key']),
        ]

    def __str__(self):
        return (
            f"BehavioralTrend user={self.user_id} "
            f"{self.behavior_key}={self.trend_direction}"
        )
