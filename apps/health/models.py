"""
Health Models - Physical wellness tracking.

Each metric is its own model for:
- Clean data structure
- Easy querying and analysis
- Independent archiving/deletion
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import SoftDeleteModel, UserOwnedModel
from apps.core.utils import get_user_today


class CycleSettings(SoftDeleteModel):
    """
    User preferences for menstrual cycle tracking.

    This is a OneToOne settings model that stores user preferences
    for cycle tracking features. Users must opt-in to enable tracking.

    Fields:
    - cycle_tracking_enabled: Master toggle for cycle tracking
    - average_cycle_length: Typical cycle length in days (default 28)
    - average_period_length: Typical period length in days (default 5)
    - notifications_enabled: Send reminders for period predictions
    - fertile_window_tracking_enabled: Track and show fertile window
    - last_period_start_date: Most recent period start date

    Note: This model uses SoftDeleteModel (not UserOwnedModel) because
    it's a OneToOne settings model, not a collection of user entries.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cycle_settings",
        help_text="User these cycle settings belong to",
    )

    # Master toggle - must be True to enable any cycle features
    cycle_tracking_enabled = models.BooleanField(
        default=False,
        help_text="Enable menstrual cycle tracking features",
    )

    # Cycle configuration
    average_cycle_length = models.PositiveSmallIntegerField(
        default=28,
        help_text="Average length of menstrual cycle in days (typically 21-35)",
    )
    average_period_length = models.PositiveSmallIntegerField(
        default=5,
        help_text="Average length of period in days (typically 3-7)",
    )

    # Notification preferences
    notifications_enabled = models.BooleanField(
        default=True,
        help_text="Send notifications for period predictions and reminders",
    )

    # Fertility tracking (optional sub-feature)
    fertile_window_tracking_enabled = models.BooleanField(
        default=False,
        help_text="Track and display fertile window predictions",
    )

    # Most recent period data
    last_period_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Start date of most recent period (used for predictions)",
    )

    class Meta:
        verbose_name = "cycle settings"
        verbose_name_plural = "cycle settings"

    def __str__(self):
        status = "enabled" if self.cycle_tracking_enabled else "disabled"
        return f"Cycle settings for {self.user.email} ({status})"

    @property
    def is_enabled(self):
        """
        Quick check if cycle tracking is enabled for this user.

        Returns True only if:
        1. The record is active (not soft deleted)
        2. cycle_tracking_enabled is True
        """
        return self.is_active and self.cycle_tracking_enabled


# =============================================================================
# Cycle Tracking Choice Definitions
# =============================================================================
# These choices are used by cycle-related models (CycleDay, etc.)
# Defined here for consistency and easy reference.

# Physical symptoms commonly experienced during menstrual cycle
CYCLE_SYMPTOM_CHOICES = [
    ("cramps", "Cramps"),
    ("headache", "Headache"),
    ("fatigue", "Fatigue"),
    ("bloating", "Bloating"),
    ("breast_tenderness", "Breast Tenderness"),
    ("acne", "Acne"),
    ("backache", "Backache"),
    ("nausea", "Nausea"),
    ("food_cravings", "Food Cravings"),
    ("insomnia", "Insomnia"),
]

# Emotional states for cycle tracking (more granular than journal moods)
CYCLE_MOOD_CHOICES = [
    ("happy", "Happy"),
    ("sad", "Sad"),
    ("irritable", "Irritable"),
    ("anxious", "Anxious"),
    ("calm", "Calm"),
    ("energetic", "Energetic"),
    ("tired", "Tired"),
    ("emotional", "Emotional"),
]

# Menstrual flow intensity levels
FLOW_LEVEL_CHOICES = [
    ("none", "None"),
    ("spotting", "Spotting"),
    ("light", "Light"),
    ("medium", "Medium"),
    ("heavy", "Heavy"),
]

# Emoji mappings for display (optional UI enhancement)
CYCLE_SYMPTOM_EMOJIS = {
    "cramps": "🔴",
    "headache": "🤕",
    "fatigue": "😴",
    "bloating": "🎈",
    "breast_tenderness": "💢",
    "acne": "😣",
    "backache": "🔙",
    "nausea": "🤢",
    "food_cravings": "🍫",
    "insomnia": "😵",
}

CYCLE_MOOD_EMOJIS = {
    "happy": "😊",
    "sad": "😢",
    "irritable": "😤",
    "anxious": "😰",
    "calm": "😌",
    "energetic": "⚡",
    "tired": "😩",
    "emotional": "🥺",
}

FLOW_LEVEL_EMOJIS = {
    "none": "⚪",
    "spotting": "🔸",
    "light": "🩸",
    "medium": "🩸🩸",
    "heavy": "🩸🩸🩸",
}

# Cervical mucus types for fertility tracking
CERVICAL_MUCUS_CHOICES = [
    ("dry", "Dry"),
    ("sticky", "Sticky"),
    ("creamy", "Creamy"),
    ("watery", "Watery"),
    ("egg_white", "Egg White (Fertile)"),
]


class CycleDailyLog(UserOwnedModel):
    """
    Daily cycle tracking entry.

    Records daily health data related to menstrual cycle including
    flow level, symptoms, mood, and optional fertility indicators.

    One entry per user per day (unique constraint).
    """

    # The date this log entry is for
    log_date = models.DateField(
        default=timezone.now,
        help_text="Date of this cycle log entry",
    )

    # Flow tracking
    flow_level = models.CharField(
        max_length=10,
        choices=FLOW_LEVEL_CHOICES,
        default="none",
        help_text="Menstrual flow intensity for this day",
    )

    # Symptoms (multi-select stored as JSON list)
    # Example: ["cramps", "headache", "fatigue"]
    symptoms = models.JSONField(
        default=list,
        blank=True,
        help_text="List of symptom keys from CYCLE_SYMPTOM_CHOICES",
    )

    # Mood tracking
    mood = models.CharField(
        max_length=20,
        choices=CYCLE_MOOD_CHOICES,
        blank=True,
        help_text="Primary emotional state for this day",
    )

    # Energy level (1-5 scale)
    energy_level = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Energy level from 1 (very low) to 5 (very high)",
    )

    # Optional fertility tracking fields
    cervical_mucus = models.CharField(
        max_length=20,
        choices=CERVICAL_MUCUS_CHOICES,
        blank=True,
        help_text="Cervical mucus type (optional, for fertility tracking)",
    )

    basal_temp = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Basal body temperature in Fahrenheit (e.g., 97.80)",
    )

    # General notes
    notes = models.TextField(
        blank=True,
        help_text="Additional notes or observations for this day",
    )

    class Meta:
        verbose_name = "cycle daily log"
        verbose_name_plural = "cycle daily logs"
        ordering = ["-log_date"]
        # One entry per user per day
        constraints = [
            models.UniqueConstraint(
                fields=["user", "log_date"],
                name="unique_cycle_log_per_user_per_day",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "log_date"]),
            models.Index(fields=["user", "flow_level"]),
        ]

    def __str__(self):
        return f"Cycle log for {self.user.email} on {self.log_date}"

    @property
    def is_period_day(self):
        """
        Check if this is a period day (any flow level other than 'none').

        Returns True if flow_level is spotting, light, medium, or heavy.
        """
        return self.flow_level != "none"

    @property
    def symptom_display_list(self):
        """
        Get human-readable symptom names.

        Returns list of display labels for the symptoms stored in JSON.
        """
        symptom_map = dict(CYCLE_SYMPTOM_CHOICES)
        return [symptom_map.get(s, s) for s in self.symptoms]

    @property
    def flow_emoji(self):
        """Get emoji representation of flow level."""
        return FLOW_LEVEL_EMOJIS.get(self.flow_level, "")

    @property
    def mood_emoji(self):
        """Get emoji representation of mood."""
        return CYCLE_MOOD_EMOJIS.get(self.mood, "")


class Cycle(UserOwnedModel):
    """
    A complete menstrual cycle record.

    Tracks the full cycle from start of one period to the start of the next.
    Cycles are auto-numbered per user for easy reference ("Cycle #5").

    Fields:
    - cycle_number: Auto-incremented per user
    - start_date: First day of period (cycle start)
    - end_date: Day before next period starts (nullable until next cycle begins)
    - period_end_date: Last day of period bleeding (nullable)
    - is_predicted: True if this cycle was AI-predicted (not user-confirmed)
    - notes: User notes about this cycle
    """

    cycle_number = models.PositiveIntegerField(
        help_text="Cycle number for this user (auto-incremented)",
    )

    start_date = models.DateField(
        help_text="First day of period (cycle start date)",
    )

    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Day before next period starts (set when next cycle begins)",
    )

    period_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Last day of period bleeding",
    )

    is_predicted = models.BooleanField(
        default=False,
        help_text="True if this cycle was AI-predicted rather than user-confirmed",
    )

    notes = models.TextField(
        blank=True,
        help_text="Notes about this cycle",
    )

    class Meta:
        verbose_name = "cycle"
        verbose_name_plural = "cycles"
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["user", "start_date"]),
            models.Index(fields=["user", "cycle_number"]),
        ]

    def __str__(self):
        return f"Cycle #{self.cycle_number} for {self.user.email} ({self.start_date})"

    def save(self, *args, **kwargs):
        """Auto-number cycles per user on first save."""
        if not self.pk and not self.cycle_number:
            # Get the highest cycle number for this user
            last_cycle = Cycle.objects.filter(user=self.user).order_by("-cycle_number").first()
            self.cycle_number = (last_cycle.cycle_number + 1) if last_cycle else 1
        super().save(*args, **kwargs)

    @property
    def cycle_length(self):
        """
        Calculate cycle length in days.

        Returns the number of days between start_date and end_date.
        Returns None if end_date is not set (cycle still ongoing).
        """
        if self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None

    @property
    def period_length(self):
        """
        Calculate period length in days.

        Returns the number of days between start_date and period_end_date.
        Returns None if period_end_date is not set.
        """
        if self.period_end_date:
            return (self.period_end_date - self.start_date).days + 1
        return None

    @property
    def is_complete(self):
        """Check if this cycle has ended (has an end_date)."""
        return self.end_date is not None

    @property
    def is_ongoing(self):
        """Check if this is the current/ongoing cycle."""
        return self.end_date is None


class CyclePrediction(UserOwnedModel):
    """
    Predicted cycle dates and fertility window.

    Stores AI-generated predictions for upcoming periods and fertile windows.
    Predictions are generated based on historical cycle data and can be
    verified against actual dates when they occur.

    Fields:
    - predicted_period_start/end: Expected period dates
    - predicted_fertile_window_start/end: Expected fertile window dates
    - prediction_confidence: Algorithm's confidence (0.0 to 1.0)
    - prediction_algorithm_version: Version string for traceability
    - generated_at: When this prediction was created
    - actual_period_start: Filled when period actually starts (for accuracy tracking)
    """

    predicted_period_start = models.DateField(
        help_text="Predicted first day of period",
    )

    predicted_period_end = models.DateField(
        help_text="Predicted last day of period",
    )

    predicted_fertile_window_start = models.DateField(
        null=True,
        blank=True,
        help_text="Predicted start of fertile window (ovulation window)",
    )

    predicted_fertile_window_end = models.DateField(
        null=True,
        blank=True,
        help_text="Predicted end of fertile window",
    )

    prediction_confidence = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        help_text="Algorithm confidence score (0.00 to 1.00)",
    )

    prediction_algorithm_version = models.CharField(
        max_length=50,
        help_text="Version of the prediction algorithm used (e.g., 'v1.0', 'v2.1-ml')",
    )

    generated_at = models.DateTimeField(
        default=timezone.now,
        help_text="When this prediction was generated",
    )

    actual_period_start = models.DateField(
        null=True,
        blank=True,
        help_text="Actual period start date (filled when verified for accuracy tracking)",
    )

    class Meta:
        verbose_name = "cycle prediction"
        verbose_name_plural = "cycle predictions"
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["user", "predicted_period_start"]),
            models.Index(fields=["user", "-generated_at"]),
        ]

    def __str__(self):
        return f"Prediction for {self.user.email}: period {self.predicted_period_start}"

    @classmethod
    def get_active_prediction(cls, user):
        """
        Get the most recent prediction for a user.

        Returns the latest prediction that hasn't been verified yet,
        or None if no active predictions exist.
        """
        return cls.objects.filter(
            user=user,
            actual_period_start__isnull=True,
        ).order_by("-generated_at").first()

    @property
    def accuracy(self):
        """
        Calculate prediction accuracy in days.

        Returns the difference (in days) between predicted and actual period start.
        Positive value means period came later than predicted.
        Negative value means period came earlier than predicted.
        Returns None if actual_period_start is not set.
        """
        if self.actual_period_start is None:
            return None
        return (self.actual_period_start - self.predicted_period_start).days

    @property
    def is_verified(self):
        """Check if this prediction has been verified with actual data."""
        return self.actual_period_start is not None

    @property
    def accuracy_percentage(self):
        """
        Calculate accuracy as a percentage based on how close the prediction was.

        Returns 100% if exact match, decreasing by 10% for each day off.
        Returns None if not verified.
        """
        if self.accuracy is None:
            return None
        days_off = abs(self.accuracy)
        return max(0, 100 - (days_off * 10))


class WeightEntry(UserOwnedModel):
    """
    Weight tracking entry.

    Supports both pounds and kilograms.
    """

    UNIT_CHOICES = [
        ("lb", "Pounds"),
        ("kg", "Kilograms"),
    ]

    value = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        help_text="Weight value",
    )
    unit = models.CharField(
        max_length=2,
        choices=UNIT_CHOICES,
        default="lb",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    # Body composition from HealthKit
    body_fat_percentage = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Body fat percentage from Apple Health or smart scale",
    )
    lean_body_mass = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Lean body mass in pounds from Apple Health or smart scale",
    )

    # Sync fields for Apple Health integration
    source = models.CharField(
        max_length=20,
        choices=[
            ("manual", "Manual Entry"),
            ("apple_health", "Apple Health"),
        ],
        default="manual",
    )
    sync_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Unique ID for deduplication during sync",
    )

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "weight entry"
        verbose_name_plural = "weight entries"

    def __str__(self):
        return f"{self.value} {self.unit} on {self.recorded_at.date()}"

    @property
    def value_in_kg(self):
        """Convert to kilograms for consistent comparison."""
        if self.unit == "kg":
            return float(self.value)
        return float(self.value) * 0.453592

    @property
    def value_in_lb(self):
        """Convert to pounds for consistent comparison."""
        if self.unit == "lb":
            return float(self.value)
        return float(self.value) * 2.20462


class FastingWindow(UserOwnedModel):
    """
    Intermittent fasting window tracking.
    
    Records start and end times of fasting periods.
    """

    FASTING_TYPE_CHOICES = [
        ("none", "No Fasting"),
        ("16:8", "16:8 (16 hours fast)"),
        ("18:6", "18:6 (18 hours fast)"),
        ("20:4", "20:4 (20 hours fast)"),
        ("OMAD", "OMAD (One Meal A Day)"),
        ("24h", "24 Hour Fast"),
        ("36h", "36 Hour Fast"),
        ("custom", "Custom"),
    ]

    fasting_type = models.CharField(
        max_length=10,
        choices=FASTING_TYPE_CHOICES,
        default="16:8",
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    target_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Target fasting duration in hours",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "fasting window"
        verbose_name_plural = "fasting windows"

    def __str__(self):
        status = "In progress" if self.is_active else f"Completed ({self.duration_hours:.1f}h)"
        return f"{self.fasting_type} started {self.started_at.date()} - {status}"

    @property
    def is_active(self):
        """Check if this fasting window is still in progress."""
        return self.ended_at is None

    @property
    def duration_hours(self):
        """Calculate duration in hours."""
        end = self.ended_at or timezone.now()
        delta = end - self.started_at
        return delta.total_seconds() / 3600

    @property
    def duration_display(self):
        """Human-readable duration."""
        hours = self.duration_hours
        if hours < 1:
            return f"{int(hours * 60)} min"
        return f"{hours:.1f} hours"

    @property
    def progress_percent(self):
        """Progress toward target as percentage."""
        if not self.target_hours:
            return None
        progress = (self.duration_hours / self.target_hours) * 100
        return min(100, progress)

    @property
    def target_end_time(self):
        """Calculate when the fast will reach its target."""
        if not self.target_hours:
            return None
        from datetime import timedelta
        return self.started_at + timedelta(hours=self.target_hours)

    @property
    def remaining_hours(self):
        """Calculate hours remaining until target is reached."""
        if not self.target_hours:
            return None
        remaining = self.target_hours - self.duration_hours
        return max(0, remaining)

    @property
    def remaining_display(self):
        """Human-readable remaining time."""
        if not self.target_hours:
            return None
        remaining = self.remaining_hours
        if remaining <= 0:
            return "Goal reached!"
        if remaining < 1:
            return f"{int(remaining * 60)} min remaining"
        hours = int(remaining)
        minutes = int((remaining - hours) * 60)
        if minutes > 0:
            return f"{hours}h {minutes}m remaining"
        return f"{hours}h remaining"

    @property
    def is_goal_reached(self):
        """Check if the fast has reached its target duration."""
        if not self.target_hours:
            return False
        return self.duration_hours >= self.target_hours

    def end_fast(self):
        """End the current fasting window."""
        if self.is_active:
            self.ended_at = timezone.now()
            self.save(update_fields=["ended_at", "updated_at"])


class HeartRateEntry(UserOwnedModel):
    """
    Heart rate tracking entry.
    
    Records BPM with context (resting, active, etc.)
    """

    CONTEXT_CHOICES = [
        ("resting", "Resting"),
        ("morning", "Morning (upon waking)"),
        ("active", "Active / Exercise"),
        ("post_exercise", "Post-Exercise"),
        ("stressed", "Stressed"),
        ("relaxed", "Relaxed"),
        ("other", "Other"),
    ]

    bpm = models.PositiveIntegerField(help_text="Beats per minute")
    context = models.CharField(
        max_length=20,
        choices=CONTEXT_CHOICES,
        default="resting",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    source = models.CharField(
        max_length=50,
        default="manual",
        help_text="Data source (manual, apple_health, etc.)"
    )
    sync_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        help_text="Unique sync ID to prevent duplicates"
    )

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "heart rate entry"
        verbose_name_plural = "heart rate entries"

    def __str__(self):
        return f"{self.bpm} BPM ({self.context}) on {self.recorded_at.date()}"


class StepsEntry(UserOwnedModel):
    """
    Daily step count tracking.

    Tracks daily steps with support for wearable/app sync.
    Designed to integrate with iOS/Android fitness apps via Connect API.
    """

    SOURCE_CHOICES = [
        ("manual", "Manual Entry"),
        ("apple_health", "Apple Health"),
        ("google_fit", "Google Fit"),
        ("fitbit", "Fitbit"),
        ("garmin", "Garmin"),
        ("samsung_health", "Samsung Health"),
        ("other", "Other App/Device"),
    ]

    count = models.PositiveIntegerField(
        help_text="Number of steps",
    )
    logged_date = models.DateField(
        help_text="Date the steps were logged for",
    )
    recorded_at = models.DateTimeField(
        default=timezone.now,
        help_text="When this entry was recorded",
    )
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="manual",
    )
    sync_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="External ID from synced source to prevent duplicates",
    )
    goal = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Daily step goal (optional)",
    )
    distance_miles = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Distance in miles (if available)",
    )
    calories_burned = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Active calories burned (if available)",
    )
    resting_calories = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Resting/basal calories burned (if available)",
    )
    flights_climbed = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Flights of stairs climbed (if available)",
    )
    exercise_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minutes of exercise (if available)",
    )
    stand_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Hours with standing activity (if available)",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-logged_date", "-recorded_at"]
        verbose_name = "steps entry"
        verbose_name_plural = "steps entries"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "logged_date", "source"],
                name="unique_steps_per_day_per_source",
            )
        ]

    def __str__(self):
        return f"{self.count:,} steps on {self.logged_date}"

    @property
    def goal_percentage(self):
        """Percentage of daily goal achieved."""
        if self.goal and self.goal > 0:
            return min(100, round((self.count / self.goal) * 100, 1))
        return None

    @property
    def goal_reached(self):
        """Whether the daily goal was met."""
        if self.goal:
            return self.count >= self.goal
        return None

    @property
    def distance_km(self):
        """Convert distance to kilometers."""
        if self.distance_miles:
            return round(float(self.distance_miles) * 1.60934, 2)
        return None


class WaterEntry(UserOwnedModel):
    """
    Hydration tracking entry.

    Tracks daily fluid intake with drink type awareness and hydration
    coefficients. Supports different units, containers, and beverage types.
    Creatine drinks are tracked here (consumed as a drink, not a pill).
    """

    UNIT_CHOICES = [
        ("oz", "Ounces (oz)"),
        ("ml", "Milliliters (ml)"),
        ("cups", "Cups"),
        ("liters", "Liters"),
    ]

    CONTAINER_CHOICES = [
        ("glass", "Glass"),
        ("bottle", "Water Bottle"),
        ("cup", "Cup/Mug"),
        ("large_bottle", "Large Bottle (32oz+)"),
        ("other", "Other"),
    ]

    DRINK_TYPE_CHOICES = [
        ("water", "Water"),
        ("coffee", "Coffee"),
        ("tea", "Tea"),
        ("electrolyte", "Electrolyte Drink"),
        ("juice", "Juice"),
        ("milk", "Milk"),
        ("other", "Other"),
        # NOTE: "creatine" was removed in the Unified Intake System migration.
        # Historical rows with drink_type='creatine' are preserved in the DB.
        # Creatine is now tracked via the Medicine model (intake_type='supplement').
    ]

    # Conservative coefficients — understate rather than overstate.
    # 1.0 = fully hydrating. < 1.0 = mild diuretic effect.
    # > 1.0 = enhanced absorption. Differences are intentionally small.
    HYDRATION_COEFFICIENTS = {
        "water": 1.0,
        "coffee": 0.9,
        "tea": 0.95,
        "electrolyte": 1.05,
        "juice": 0.9,
        "milk": 0.9,
        "other": 0.9,
    }

    amount = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        help_text="Amount consumed",
    )
    unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default="oz",
    )
    drink_type = models.CharField(
        max_length=20,
        choices=DRINK_TYPE_CHOICES,
        default="water",
        help_text="Type of beverage consumed",
    )
    container = models.CharField(
        max_length=20,
        choices=CONTAINER_CHOICES,
        default="glass",
        blank=True,
    )
    logged_date = models.DateField(
        help_text="Date the fluid was logged for",
    )
    recorded_at = models.DateTimeField(
        default=timezone.now,
        help_text="When this entry was recorded",
    )
    notes = models.TextField(blank=True)

    # Sync fields for Apple Health integration
    source = models.CharField(
        max_length=20,
        choices=[
            ("manual", "Manual Entry"),
            ("apple_health", "Apple Health"),
            ("imported", "Imported"),
        ],
        default="manual",
    )
    sync_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="External ID from synced source to prevent duplicates",
    )

    class Meta:
        ordering = ["-logged_date", "-recorded_at"]
        verbose_name = "hydration entry"
        verbose_name_plural = "hydration entries"

    def __str__(self):
        dt = self.get_drink_type_display() if self.drink_type != "water" else ""
        prefix = f"{dt} " if dt else ""
        return f"{prefix}{self.amount} {self.unit} on {self.logged_date}"

    @property
    def amount_oz(self):
        """Convert amount to ounces (raw volume, no coefficient)."""
        conversions = {
            "oz": 1,
            "ml": 0.033814,
            "cups": 8,
            "liters": 33.814,
        }
        return round(float(self.amount) * conversions.get(self.unit, 1), 1)

    @property
    def amount_ml(self):
        """Convert amount to milliliters (raw volume, no coefficient)."""
        conversions = {
            "oz": 29.5735,
            "ml": 1,
            "cups": 236.588,
            "liters": 1000,
        }
        return round(float(self.amount) * conversions.get(self.unit, 1), 1)

    @property
    def effective_oz(self):
        """Amount adjusted by hydration coefficient.

        Coffee 12oz × 0.9 = 10.8 effective oz.
        Electrolyte 16oz × 1.05 = 16.8 effective oz.
        """
        coeff = self.HYDRATION_COEFFICIENTS.get(self.drink_type or "water", 0.9)
        return round(self.amount_oz * coeff, 1)

    @classmethod
    def get_daily_total(cls, user, date):
        """Get total EFFECTIVE hydration for a date in ounces.

        Uses hydration coefficients — coffee counts less, electrolytes more.
        """
        entries = cls.objects.filter(user=user, logged_date=date)
        return sum(entry.effective_oz for entry in entries)

    @classmethod
    def get_daily_total_raw(cls, user, date):
        """Get total RAW fluid intake (no coefficients) for display."""
        entries = cls.objects.filter(user=user, logged_date=date)
        return sum(entry.amount_oz for entry in entries)

    @classmethod
    def get_daily_goal_progress(cls, user, date, goal_oz=64):
        """Progress toward daily hydration goal (uses effective oz).

        Returns:
            dict with total_oz (effective), raw_total_oz, goal_oz,
            percentage, and goal_met.
        """
        total = cls.get_daily_total(user, date)
        raw_total = cls.get_daily_total_raw(user, date)
        percentage = min(100, round((total / goal_oz) * 100, 1)) if goal_oz > 0 else 0
        return {
            "total_oz": total,
            "raw_total_oz": raw_total,
            "goal_oz": goal_oz,
            "percentage": percentage,
            "goal_met": total >= goal_oz,
        }

    # NOTE: Creatine helpers (is_creatine_active, creatine_start_date,
    # has_creatine_today) were removed in the Unified Intake System migration.
    # Creatine is now tracked via the Medicine model (intake_type='supplement').
    # Use Medicine.objects.filter(intake_type='supplement', name__icontains='creatine').


class GlucoseEntry(UserOwnedModel):
    """
    Blood glucose tracking entry.

    Supports mg/dL and mmol/L units.
    Integrates with Dexcom CGM for automatic data import.
    """

    UNIT_CHOICES = [
        ("mg/dL", "mg/dL"),
        ("mmol/L", "mmol/L"),
    ]

    CONTEXT_CHOICES = [
        ("fasting", "Fasting"),
        ("before_meal", "Before Meal"),
        ("after_meal", "After Meal (2 hours)"),
        ("bedtime", "Bedtime"),
        ("random", "Random"),
        ("cgm", "CGM Reading"),
    ]

    SOURCE_CHOICES = [
        ("manual", "Manual Entry"),
        ("dexcom", "Dexcom CGM"),
        ("apple_health", "Apple Health"),
        ("imported", "Imported"),
    ]

    # Dexcom trend arrow values
    TREND_CHOICES = [
        ("", "N/A"),
        ("doubleUp", "Rising Rapidly"),
        ("singleUp", "Rising"),
        ("fortyFiveUp", "Rising Slowly"),
        ("flat", "Stable"),
        ("fortyFiveDown", "Falling Slowly"),
        ("singleDown", "Falling"),
        ("doubleDown", "Falling Rapidly"),
        ("none", "None"),
        ("notComputable", "Not Computable"),
        ("rateOutOfRange", "Rate Out of Range"),
    ]

    TREND_ARROWS = {
        "doubleUp": "⬆⬆",
        "singleUp": "⬆",
        "fortyFiveUp": "↗",
        "flat": "→",
        "fortyFiveDown": "↘",
        "singleDown": "⬇",
        "doubleDown": "⬇⬇",
        "none": "—",
        "notComputable": "?",
        "rateOutOfRange": "!",
    }

    value = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        help_text="Glucose reading",
    )
    unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default="mg/dL",
    )
    context = models.CharField(
        max_length=20,
        choices=CONTEXT_CHOICES,
        default="fasting",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    # Dexcom-specific fields
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="manual",
    )
    dexcom_record_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Dexcom recordId for sync tracking"
    )
    sync_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="External ID from synced source (HealthKit UUID) to prevent duplicates",
    )
    trend = models.CharField(
        max_length=20,
        choices=TREND_CHOICES,
        blank=True,
        help_text="Glucose trend direction from CGM"
    )
    trend_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Rate of change in mg/dL/min"
    )
    display_device = models.CharField(
        max_length=20,
        blank=True,
        help_text="Device type (receiver, iOS, android)"
    )

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "glucose entry"
        verbose_name_plural = "glucose entries"
        indexes = [
            models.Index(fields=['user', 'dexcom_record_id']),
            models.Index(fields=['user', 'source', 'recorded_at']),
        ]

    def __str__(self):
        trend_arrow = self.trend_arrow_display
        trend_str = f" {trend_arrow}" if trend_arrow else ""
        return f"{self.value} {self.unit}{trend_str} ({self.context}) on {self.recorded_at.date()}"

    @property
    def trend_arrow_display(self):
        """Get the trend arrow character for display."""
        return self.TREND_ARROWS.get(self.trend, "")

    @property
    def value_in_mg_dl(self):
        """Convert to mg/dL for consistent comparison."""
        if self.unit == "mg/dL":
            return float(self.value)
        return float(self.value) * 18.0182

    @property
    def value_in_mmol_l(self):
        """Convert to mmol/L for consistent comparison."""
        if self.unit == "mmol/L":
            return float(self.value)
        return float(self.value) / 18.0182

    @property
    def is_from_dexcom(self):
        """Check if this reading came from Dexcom."""
        return self.source == "dexcom"

    @property
    def glucose_status(self):
        """Categorize glucose level for display."""
        mg_dl = self.value_in_mg_dl
        if mg_dl < 54:
            return "very_low"
        elif mg_dl < 70:
            return "low"
        elif mg_dl <= 180:
            return "normal"
        elif mg_dl <= 250:
            return "high"
        else:
            return "very_high"

    @property
    def glucose_status_display(self):
        """Human-readable glucose status."""
        status_labels = {
            "very_low": "Very Low",
            "low": "Low",
            "normal": "In Range",
            "high": "High",
            "very_high": "Very High",
        }
        return status_labels.get(self.glucose_status, "Unknown")


class BloodPressureEntry(UserOwnedModel):
    """
    Blood pressure tracking entry.

    Records systolic and diastolic pressure with context.
    """

    CONTEXT_CHOICES = [
        ("resting", "Resting"),
        ("morning", "Morning (upon waking)"),
        ("evening", "Evening"),
        ("post_exercise", "Post-Exercise"),
        ("stressed", "Stressed"),
        ("relaxed", "Relaxed"),
        ("other", "Other"),
    ]

    ARM_CHOICES = [
        ("left", "Left Arm"),
        ("right", "Right Arm"),
    ]

    POSITION_CHOICES = [
        ("sitting", "Sitting"),
        ("standing", "Standing"),
        ("lying", "Lying Down"),
    ]

    systolic = models.PositiveIntegerField(
        help_text="Systolic pressure (top number) in mmHg"
    )
    diastolic = models.PositiveIntegerField(
        help_text="Diastolic pressure (bottom number) in mmHg"
    )
    pulse = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Pulse rate (if measured with BP)"
    )
    context = models.CharField(
        max_length=20,
        choices=CONTEXT_CHOICES,
        default="resting",
    )
    arm = models.CharField(
        max_length=10,
        choices=ARM_CHOICES,
        default="left",
    )
    position = models.CharField(
        max_length=10,
        choices=POSITION_CHOICES,
        default="sitting",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    source = models.CharField(
        max_length=50,
        default="manual",
        help_text="Data source (manual, apple_health, etc.)"
    )
    sync_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        help_text="Unique sync ID to prevent duplicates"
    )

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "blood pressure entry"
        verbose_name_plural = "blood pressure entries"

    def __str__(self):
        return f"{self.systolic}/{self.diastolic} mmHg on {self.recorded_at.date()}"

    @property
    def reading(self):
        """Return formatted blood pressure reading."""
        return f"{self.systolic}/{self.diastolic}"

    @property
    def category(self):
        """
        Categorize blood pressure according to AHA guidelines.
        Returns: normal, elevated, high_stage1, high_stage2, crisis
        """
        if self.systolic < 120 and self.diastolic < 80:
            return "normal"
        elif self.systolic < 130 and self.diastolic < 80:
            return "elevated"
        elif self.systolic < 140 or self.diastolic < 90:
            return "high_stage1"
        elif self.systolic < 180 or self.diastolic < 120:
            return "high_stage2"
        else:
            return "crisis"

    @property
    def category_display(self):
        """Human-readable category name."""
        categories = {
            "normal": "Normal",
            "elevated": "Elevated",
            "high_stage1": "High (Stage 1)",
            "high_stage2": "High (Stage 2)",
            "crisis": "Hypertensive Crisis",
        }
        return categories.get(self.category, "Unknown")


class BodyTemperatureEntry(UserOwnedModel):
    """
    Body temperature tracking entry.

    Records temperature readings with context.
    """

    UNIT_CHOICES = [
        ("fahrenheit", "Fahrenheit"),
        ("celsius", "Celsius"),
    ]

    CONTEXT_CHOICES = [
        ("oral", "Oral"),
        ("ear", "Ear (Tympanic)"),
        ("forehead", "Forehead"),
        ("armpit", "Armpit (Axillary)"),
        ("rectal", "Rectal"),
        ("other", "Other"),
    ]

    temperature = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        help_text="Temperature value"
    )
    unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default="fahrenheit",
    )
    context = models.CharField(
        max_length=20,
        choices=CONTEXT_CHOICES,
        default="oral",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    source = models.CharField(
        max_length=50,
        default="manual",
        help_text="Data source (manual, apple_health, etc.)"
    )
    sync_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        help_text="Unique sync ID to prevent duplicates"
    )

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "body temperature entry"
        verbose_name_plural = "body temperature entries"

    def __str__(self):
        return f"{self.temperature}°{'F' if self.unit == 'fahrenheit' else 'C'} on {self.recorded_at.date()}"

    @property
    def temperature_fahrenheit(self):
        """Return temperature in Fahrenheit."""
        if self.unit == "fahrenheit":
            return float(self.temperature)
        return float(self.temperature) * 9 / 5 + 32

    @property
    def temperature_celsius(self):
        """Return temperature in Celsius."""
        if self.unit == "celsius":
            return float(self.temperature)
        return (float(self.temperature) - 32) * 5 / 9

    @property
    def temperature_status(self):
        """
        Categorize temperature (based on Fahrenheit).
        Returns: low, normal, elevated, fever, high_fever
        """
        temp_f = self.temperature_fahrenheit
        if temp_f < 97.0:
            return "low"
        elif temp_f < 99.0:
            return "normal"
        elif temp_f < 100.4:
            return "elevated"
        elif temp_f < 103.0:
            return "fever"
        else:
            return "high_fever"


class BloodOxygenEntry(UserOwnedModel):
    """
    Blood oxygen (SpO2) tracking entry.

    Records oxygen saturation percentage with context.
    """

    CONTEXT_CHOICES = [
        ("resting", "Resting"),
        ("morning", "Morning (upon waking)"),
        ("active", "Active / Exercise"),
        ("post_exercise", "Post-Exercise"),
        ("sleeping", "During Sleep"),
        ("illness", "While Ill"),
        ("other", "Other"),
    ]

    MEASUREMENT_CHOICES = [
        ("finger", "Finger Pulse Oximeter"),
        ("wrist", "Wrist Device"),
        ("ear", "Ear Clip"),
        ("other", "Other"),
    ]

    spo2 = models.PositiveIntegerField(
        help_text="Blood oxygen saturation percentage (SpO2)"
    )
    pulse = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Pulse rate (if measured with SpO2)"
    )
    context = models.CharField(
        max_length=20,
        choices=CONTEXT_CHOICES,
        default="resting",
    )
    measurement_method = models.CharField(
        max_length=20,
        choices=MEASUREMENT_CHOICES,
        default="finger",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    # Sync fields for Apple Health integration
    source = models.CharField(
        max_length=20,
        choices=[
            ("manual", "Manual Entry"),
            ("apple_health", "Apple Health"),
            ("imported", "Imported"),
        ],
        default="manual",
    )
    sync_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="External ID from synced source to prevent duplicates",
    )

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "blood oxygen entry"
        verbose_name_plural = "blood oxygen entries"

    def __str__(self):
        return f"{self.spo2}% SpO2 on {self.recorded_at.date()}"

    @property
    def category(self):
        """
        Categorize blood oxygen level.
        Returns: normal, low, concerning, critical
        """
        if self.spo2 >= 95:
            return "normal"
        elif self.spo2 >= 90:
            return "low"
        elif self.spo2 >= 85:
            return "concerning"
        else:
            return "critical"

    @property
    def category_display(self):
        """Human-readable category name."""
        categories = {
            "normal": "Normal",
            "low": "Low",
            "concerning": "Concerning",
            "critical": "Critical",
        }
        return categories.get(self.category, "Unknown")


# =============================================================================
# Fitness Tracking Models
# =============================================================================


class Exercise(models.Model):
    """
    Admin-configurable exercise library.

    Supports both resistance training and cardio exercises.
    """

    CATEGORY_CHOICES = [
        ("resistance", "Resistance Training"),
        ("cardio", "Cardio"),
        ("class", "Fitness Class"),
    ]

    MOVEMENT_TYPE_CHOICES = [
        ("weighted", "Weighted"),
        ("bodyweight", "Bodyweight"),
        ("time", "Time-Based"),
    ]

    LOAD_TYPE_CHOICES = [
        ("external", "External Weight"),
        ("bodyweight", "Bodyweight"),
        ("assisted", "Assisted"),
        ("band", "Band Resistance"),
        ("movement", "Movement / Skill"),
    ]

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    movement_type = models.CharField(
        max_length=20,
        choices=MOVEMENT_TYPE_CHOICES,
        default="weighted",
        help_text="Controls input fields: weighted (weight+reps), bodyweight (reps, optional weight), time (duration)",
    )
    load_type = models.CharField(
        max_length=20,
        choices=LOAD_TYPE_CHOICES,
        default="external",
        help_text="Controls volume calculation: external/bodyweight produce volume, others do not",
    )
    load_multiplier = models.FloatField(
        null=True,
        blank=True,
        help_text="Future: optional scaling factor for load (e.g., 0.4 for partial bodyweight). Not used in calculations yet.",
    )
    muscle_group = models.CharField(
        max_length=50,
        blank=True,
        help_text="Primary muscle group (for resistance exercises)",
    )
    description = models.TextField(blank=True)

    VIDEO_SOURCE_CHOICES = [
        ("athleanx", "AthleanX"),
        ("nippard", "Jeff Nippard"),
        ("ethier", "Jeremy Ethier"),
        ("custom", "Custom"),
    ]

    instructions = models.TextField(
        blank=True,
        help_text="Step-by-step exercise instructions and form cues",
    )
    youtube_url = models.URLField(
        blank=True,
        help_text="Direct YouTube video URL for exercise demonstration",
    )
    video_source = models.CharField(
        max_length=20,
        choices=VIDEO_SOURCE_CHOICES,
        blank=True,
        help_text="Source channel of the assigned video",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "exercise"
        verbose_name_plural = "exercises"

    def __str__(self):
        if self.muscle_group:
            return f"{self.name} ({self.muscle_group})"
        return self.name


SESSION_MODE_CHOICES = [
    ("structured", "Structured"),
    ("activity", "Activity"),
]

INTENSITY_CHOICES = [
    ("low", "Low"),
    ("moderate", "Moderate"),
    ("high", "High"),
]

# Common activity presets: (name, default_intensity)
ACTIVITY_PRESETS = [
    ("Pickleball", "high"),
    ("Walking", "low"),
    ("Running", "high"),
    ("Cycling", "moderate"),
    ("Swimming", "high"),
    ("Hiking", "moderate"),
    ("Yoga", "low"),
    ("Dance", "moderate"),
    ("Tennis", "high"),
    ("Golf", "low"),
    ("Rowing", "high"),
    ("Elliptical", "moderate"),
    ("Stair Climbing", "moderate"),
    ("Jump Rope", "high"),
]

# Minimum total daily workout minutes before routine auto-complete triggers
WORKOUT_COMPLETION_THRESHOLD_MINUTES = 10


class WorkoutSession(UserOwnedModel):
    """
    A single workout session.

    Groups multiple exercises performed in one workout.
    Supports two modes:
      - structured: traditional exercise-set driven (bench press 3x10)
      - activity: duration-driven (pickleball 90 min, walking 30 min)
    """

    SESSION_MODE_STRUCTURED = "structured"
    SESSION_MODE_ACTIVITY = "activity"
    SESSION_MODE_CHOICES = [
        (SESSION_MODE_STRUCTURED, "Structured"),
        (SESSION_MODE_ACTIVITY, "Activity"),
    ]

    INTENSITY_EASY = "easy"
    INTENSITY_MODERATE = "moderate"
    INTENSITY_HARD = "hard"
    INTENSITY_CHOICES = [
        (INTENSITY_EASY, "Easy"),
        (INTENSITY_MODERATE, "Moderate"),
        (INTENSITY_HARD, "Hard"),
    ]

    # Weights for training load calculation
    INTENSITY_WEIGHT = {
        INTENSITY_EASY: 0.5,
        INTENSITY_MODERATE: 0.75,
        INTENSITY_HARD: 1.0,
    }

    date = models.DateField()
    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional name like 'Push Day' or 'Morning Run'",
    )
    notes = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total workout duration in minutes",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    from_template = models.ForeignKey(
        "WorkoutTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workout_sessions",
        help_text="Template this workout was created from, if any",
    )

    # Session mode and intensity
    session_mode = models.CharField(
        max_length=20,
        choices=SESSION_MODE_CHOICES,
        default=SESSION_MODE_STRUCTURED,
        help_text="Whether this is a structured workout (sets/reps) or duration-based activity",
    )
    intensity = models.CharField(
        max_length=20,
        choices=INTENSITY_CHOICES,
        blank=True,
        default="",
        help_text="User-reported or derived intensity level",
    )

    # Workout type — used for both HealthKit imports and manual activity entries
    workout_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Activity type (e.g., Pickleball, Running, Strength Training)",
    )
    calories_burned = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total calories burned during workout",
    )
    distance_miles = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Distance for cardio workouts (in miles)",
    )
    avg_heart_rate = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Average heart rate during workout",
    )

    # Sync fields for Apple Health integration
    source = models.CharField(
        max_length=20,
        choices=[
            ("manual", "Manual Entry"),
            ("apple_health", "Apple Health"),
        ],
        default="manual",
    )
    sync_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Unique ID for deduplication during sync",
    )

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "workout session"
        verbose_name_plural = "workout sessions"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "sync_id"],
                name="unique_workout_sync_id",
                condition=models.Q(sync_id__gt=""),
            ),
        ]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["source", "sync_id"]),
        ]

    def __str__(self):
        if self.name:
            return f"{self.name} - {self.date}"
        if self.session_mode == "activity" and self.workout_type:
            return f"{self.workout_type} - {self.date}"
        return f"Workout on {self.date}"

    @property
    def is_activity(self):
        """Whether this is a duration-driven activity workout."""
        return self.session_mode == "activity"

    @property
    def exercise_count(self):
        """Number of exercises in this session."""
        return self.workout_exercises.count()

    @property
    def total_sets(self):
        """Total number of sets across all exercises."""
        return sum(ex.sets.count() for ex in self.workout_exercises.filter(exercise__category="resistance"))

    @property
    def total_volume(self):
        """Total volume for resistance exercises using load_type-aware calculation.

        Skips sets where volume is None (band, movement, assisted exercises).
        """
        total = 0
        for workout_ex in self.workout_exercises.filter(exercise__category="resistance"):
            for s in workout_ex.sets.all():
                v = s.volume
                if v is not None:
                    total += v
        return total

    @property
    def total_movement_work(self):
        """Total reps from non-load exercises (band, movement, assisted)."""
        total = 0
        for workout_ex in self.workout_exercises.filter(exercise__category="resistance"):
            for s in workout_ex.sets.all():
                r = s.movement_work
                if r is not None:
                    total += r
        return total

    @property
    def training_load(self):
        """
        Training load score (0.0 - 1.0).

        Combines duration and intensity into a single metric:
          duration_factor: 0 at 0 min, 1.0 at 60 min, capped at 1.0
          intensity_factor: easy=0.5, moderate=0.75, hard=1.0
        """
        if not self.duration_minutes:
            return 0.0
        duration_factor = min(self.duration_minutes / 60.0, 1.0)
        intensity_factor = self.INTENSITY_WEIGHT.get(self.intensity, 0.75)
        return round(duration_factor * intensity_factor, 2)

    @property
    def is_activity_workout(self):
        """Whether this is a duration-based activity (vs structured sets/reps)."""
        return self.session_mode == self.SESSION_MODE_ACTIVITY


class WorkoutExercise(models.Model):
    """
    An exercise within a workout session.

    Links a workout session to an exercise with ordering.
    """

    session = models.ForeignKey(
        WorkoutSession,
        on_delete=models.CASCADE,
        related_name="workout_exercises",
    )
    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.PROTECT,
        related_name="workout_instances",
    )
    order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "workout exercise"
        verbose_name_plural = "workout exercises"

    def __str__(self):
        return f"{self.exercise.name} in {self.session}"

    @property
    def total_volume(self):
        """Sum of volume across all non-warmup sets for this exercise.

        Skips sets where volume is None (band, movement, assisted exercises).
        """
        return sum(
            v for s in self.sets.filter(is_warmup=False)
            if (v := s.volume) is not None
        )

    @property
    def total_movement_work(self):
        """Sum of reps across all non-warmup sets for movement exercises.

        Returns 0 for load-based exercises (volume handles those).
        """
        return sum(
            r for s in self.sets.filter(is_warmup=False)
            if (r := s.movement_work) is not None
        )


class ExerciseSet(models.Model):
    """
    Individual set within a resistance exercise.

    Tracks weight, reps, and whether it's a warmup or PR.
    """

    workout_exercise = models.ForeignKey(
        WorkoutExercise,
        on_delete=models.CASCADE,
        related_name="sets",
    )
    set_number = models.PositiveIntegerField()
    weight = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Weight in pounds",
    )
    reps = models.PositiveIntegerField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duration in seconds for time-based exercises",
    )
    bodyweight_used = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="User's bodyweight at time of exercise (for volume calculation)",
    )
    is_warmup = models.BooleanField(default=False)
    is_pr = models.BooleanField(
        default=False,
        help_text="Personal record for this exercise",
    )
    notes = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["set_number"]
        verbose_name = "exercise set"
        verbose_name_plural = "exercise sets"

    def __str__(self):
        if self.duration_seconds:
            mins, secs = divmod(self.duration_seconds, 60)
            return f"Set {self.set_number}: {mins}:{secs:02d}"
        weight_str = f"{self.weight}lbs" if self.weight else "bodyweight"
        return f"Set {self.set_number}: {weight_str} x {self.reps}"

    @property
    def volume(self):
        """Calculate volume for this set based on exercise load_type.

        external: weight × reps (requires explicit weight)
        bodyweight: weight × reps if added weight, else bodyweight_used × reps
        band/movement/assisted: None (no meaningful volume)
        """
        load_type = self.workout_exercise.exercise.load_type
        if load_type == "external":
            return float(self.weight) * self.reps if self.weight and self.reps else 0
        elif load_type == "bodyweight":
            if self.weight and self.reps:
                return float(self.weight) * self.reps
            if self.bodyweight_used and self.reps:
                return float(self.bodyweight_used) * self.reps
            return 0
        else:  # band, movement, assisted
            return None

    @property
    def movement_work(self):
        """Reps for non-load exercises (band, movement, assisted).

        Returns reps as integer for movement exercises, None for load exercises.
        """
        load_type = self.workout_exercise.exercise.load_type
        if load_type in ("band", "movement", "assisted"):
            return self.reps or 0
        return None


class CardioDetails(models.Model):
    """
    Details specific to cardio exercises.

    Tracks duration, distance, intensity, and heart rate.
    """

    INTENSITY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    workout_exercise = models.OneToOneField(
        WorkoutExercise,
        on_delete=models.CASCADE,
        related_name="cardio_details",
    )
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duration in minutes",
    )
    distance = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Distance in miles",
    )
    intensity = models.CharField(
        max_length=10,
        choices=INTENSITY_CHOICES,
        default="medium",
    )
    calories_burned = models.PositiveIntegerField(null=True, blank=True)
    avg_heart_rate = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Average heart rate in BPM",
    )

    class Meta:
        verbose_name = "cardio details"
        verbose_name_plural = "cardio details"

    def __str__(self):
        parts = []
        if self.duration_minutes:
            parts.append(f"{self.duration_minutes} min")
        if self.distance:
            parts.append(f"{self.distance} mi")
        parts.append(self.intensity)
        return " - ".join(parts)


class ClassDetails(models.Model):
    """
    Details specific to fitness class exercises.

    For classes like F45, Orange Theory, yoga, spin, etc. where you
    don't track individual sets/reps - just attendance and duration.
    """

    INTENSITY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    workout_exercise = models.OneToOneField(
        WorkoutExercise,
        on_delete=models.CASCADE,
        related_name="class_details",
    )
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Class duration in minutes",
    )
    intensity = models.CharField(
        max_length=10,
        choices=INTENSITY_CHOICES,
        default="medium",
    )

    class Meta:
        verbose_name = "class details"
        verbose_name_plural = "class details"

    def __str__(self):
        parts = []
        if self.duration_minutes:
            parts.append(f"{self.duration_minutes} min")
        parts.append(self.intensity)
        return " - ".join(parts)


class PersonalRecord(UserOwnedModel):
    """
    Track personal records for exercises.

    Records the best performance for each exercise, with PR type
    and the previous best value that was surpassed.
    """

    PR_TYPE_CHOICES = [
        ("weight", "Max Weight"),
        ("reps", "Rep PR"),
        ("e1rm", "Estimated 1RM"),
        ("time", "Longest Hold"),
    ]

    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.CASCADE,
        related_name="personal_records",
    )
    weight = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Weight in pounds",
    )
    reps = models.PositiveIntegerField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duration in seconds for time-based PRs",
    )
    achieved_date = models.DateField()
    workout_session = models.ForeignKey(
        WorkoutSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personal_records",
    )
    pr_type = models.CharField(
        max_length=10,
        choices=PR_TYPE_CHOICES,
        default="weight",
        help_text="Type of PR: max weight, rep PR at same weight, or estimated 1RM",
    )
    previous_value = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Previous best value that was surpassed (weight in lbs, reps, or e1RM)",
    )

    class Meta:
        ordering = ["-achieved_date"]
        verbose_name = "personal record"
        verbose_name_plural = "personal records"
        indexes = [
            models.Index(
                fields=["user", "exercise"],
                name="pr_user_exercise_idx",
            ),
            models.Index(
                fields=["user", "achieved_date"],
                name="pr_user_date_idx",
            ),
        ]

    def __str__(self):
        if self.pr_type == "time" and self.duration_seconds:
            mins, secs = divmod(self.duration_seconds, 60)
            return f"PR: {self.exercise.name} - {mins}:{secs:02d} ({self.get_pr_type_display()})"
        weight_str = f"{self.weight}lbs" if self.weight else "bodyweight"
        return f"PR: {self.exercise.name} - {weight_str} x {self.reps} ({self.get_pr_type_display()})"

    @property
    def estimated_1rm(self):
        """Estimate 1 rep max using Brzycki formula."""
        if not self.weight or not self.reps:
            return None
        if self.reps == 1:
            return float(self.weight)
        reps_capped = min(self.reps, 36)
        return float(self.weight) * (36 / (37 - reps_capped))


class WorkoutTemplate(UserOwnedModel):
    """
    Saved workout routines for quick reuse.

    Users can save their favorite workout structures as templates.
    """

    name = models.CharField(
        max_length=100,
        help_text="Template name like 'Push Day' or 'Leg Day'",
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "workout template"
        verbose_name_plural = "workout templates"

    def __str__(self):
        return self.name

    @property
    def exercise_count(self):
        """Number of exercises in this template."""
        return self.template_exercises.count()


class TemplateExercise(models.Model):
    """
    Exercise within a workout template.

    Defines the default structure for each exercise in the template.
    """

    template = models.ForeignKey(
        WorkoutTemplate,
        on_delete=models.CASCADE,
        related_name="template_exercises",
    )
    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.CASCADE,
        related_name="template_instances",
    )
    order = models.PositiveIntegerField(default=0)
    default_sets = models.PositiveIntegerField(
        default=3,
        help_text="Default number of sets for this exercise",
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "template exercise"
        verbose_name_plural = "template exercises"

    def __str__(self):
        return f"{self.exercise.name} in {self.template.name}"


class TemplateExerciseSet(models.Model):
    """
    Default set configuration for an exercise in a template.

    Stores the last-used weight/reps for each set, auto-updated when
    a workout using this template is completed.
    """

    template_exercise = models.ForeignKey(
        TemplateExercise,
        on_delete=models.CASCADE,
        related_name="set_defaults",
    )
    set_number = models.PositiveIntegerField()
    weight = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Default weight in pounds",
    )
    reps = models.PositiveIntegerField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Default duration in seconds for time-based exercises",
    )

    class Meta:
        ordering = ["set_number"]
        unique_together = ["template_exercise", "set_number"]
        verbose_name = "template exercise set"
        verbose_name_plural = "template exercise sets"

    def __str__(self):
        if self.duration_seconds:
            mins, secs = divmod(self.duration_seconds, 60)
            return f"Set {self.set_number}: {mins}:{secs:02d}"
        weight_str = f"{self.weight}lbs" if self.weight else "bodyweight"
        return f"Set {self.set_number}: {weight_str} x {self.reps}"


# =============================================================================
# Medicine Tracking Models
# =============================================================================


class Intake(UserOwnedModel):
    """
    A tracked intake item — medication, supplement, or performance substance.

    This is the unified intake system. All dosage-based substances are tracked
    here with intake_type for behavioral classification and category for
    fine-grained grouping.

    intake_type: 'medication' (prescribed/medical) vs 'supplement' (optimization)
    category: finer classification (prescription, vitamin, amino_acid, etc.)
    priority: 'critical' (health consequence if missed) vs 'optimization' (goal support)
    """

    # ── Intake classification ──
    INTAKE_TYPE_MEDICATION = "medication"
    INTAKE_TYPE_SUPPLEMENT = "supplement"
    INTAKE_TYPE_CHOICES = [
        (INTAKE_TYPE_MEDICATION, "Medication"),
        (INTAKE_TYPE_SUPPLEMENT, "Supplement"),
    ]

    PRIORITY_CRITICAL = "critical"
    PRIORITY_OPTIMIZATION = "optimization"
    PRIORITY_CHOICES = [
        (PRIORITY_CRITICAL, "Critical"),
        (PRIORITY_OPTIMIZATION, "Optimization"),
    ]

    CATEGORY_CHOICES = [
        ("prescription", "Prescription"),
        ("otc", "Over-the-Counter"),
        ("vitamin", "Vitamin"),
        ("mineral", "Mineral"),
        ("amino_acid", "Amino Acid"),
        ("performance", "Performance"),
        ("hormonal", "Hormonal"),
        ("herbal", "Herbal"),
        ("probiotic", "Probiotic"),
        ("other", "Other"),
    ]

    FREQUENCY_CHOICES = [
        ("daily", "Daily"),
        ("twice_daily", "Twice Daily"),
        ("three_daily", "Three Times Daily"),
        ("four_daily", "Four Times Daily"),
        ("weekly", "Weekly"),
        ("biweekly", "Every Two Weeks"),
        ("monthly", "Monthly"),
        ("as_needed", "As Needed (PRN)"),
        ("custom", "Custom Schedule"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_COMPLETED = "completed"

    MEDICINE_STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_COMPLETED, "Completed"),
    ]

    # Basic Info
    name = models.CharField(
        max_length=200,
        help_text="Medicine name (brand or generic)",
    )
    purpose = models.CharField(
        max_length=500,
        blank=True,
        help_text="What this medicine is for (e.g., 'blood pressure', 'allergies')",
    )

    # Dosage
    dose = models.CharField(
        max_length=100,
        help_text="Dose amount (e.g., '500mg', '1 tablet', '2 puffs')",
    )

    # Scheduling
    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default="daily",
    )
    is_prn = models.BooleanField(
        default=False,
        help_text="Take as-needed (PRN) rather than on a schedule",
    )

    # Dates
    start_date = models.DateField(
        help_text="When you started taking this medicine",
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Expected end date (optional)",
    )

    # Intake status (separate from soft-delete status)
    intake_status = models.CharField(
        max_length=20,
        choices=MEDICINE_STATUS_CHOICES,
        default=STATUS_ACTIVE,
        help_text="Current status of this intake regimen",
    )
    paused_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this intake was paused",
    )
    paused_reason = models.CharField(
        max_length=500,
        blank=True,
        help_text="Reason for pausing this intake",
    )

    # Refill Tracking
    current_supply = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Current number of doses remaining",
    )
    refill_threshold = models.PositiveIntegerField(
        default=7,
        help_text="Alert when supply drops to this many days",
    )

    # Optional Details
    prescribing_doctor = models.CharField(
        max_length=200,
        blank=True,
        help_text="Doctor who prescribed this medicine",
    )
    pharmacy = models.CharField(
        max_length=200,
        blank=True,
        help_text="Pharmacy where you fill this prescription",
    )
    rx_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="Prescription/Rx number",
    )

    # Instructions & Notes
    instructions = models.TextField(
        blank=True,
        help_text="Special instructions (e.g., 'take with food', 'avoid grapefruit')",
    )
    notes = models.TextField(
        blank=True,
        help_text="Personal notes about this medicine",
    )

    # Grace Period for Missed Doses
    grace_period_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Minutes after scheduled time before marking as overdue",
    )

    # ── Intake classification fields ──
    intake_type = models.CharField(
        max_length=20,
        choices=INTAKE_TYPE_CHOICES,
        default=INTAKE_TYPE_MEDICATION,
        help_text="Whether this is a medication or supplement",
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_CRITICAL,
        help_text="Critical (health consequence if missed) vs optimization (goal support)",
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="other",
        help_text="Finer classification (prescription, vitamin, amino_acid, etc.)",
    )
    dosage_unit = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Unit of measurement (mg, g, IU, mcg, ml)",
    )

    # Refill Request Tracking
    refill_requested = models.BooleanField(
        default=False,
        help_text="Has a refill been requested for this medicine?",
    )
    refill_requested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the refill was requested",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "intake"
        verbose_name_plural = "intake items"

    def __str__(self):
        return f"{self.name} ({self.dose})"

    @property
    def is_active(self):
        """Check if this intake item is actively being taken."""
        return self.intake_status == self.STATUS_ACTIVE

    @property
    def is_paused(self):
        """Check if this intake is temporarily paused."""
        return self.intake_status == self.STATUS_PAUSED

    @property
    def needs_refill(self):
        """Check if supply is low and needs refill (and refill not already requested)."""
        if self.current_supply is None:
            return False
        if self.refill_requested:
            return False  # Already requested, don't show as "needs refill"
        return self.current_supply <= self.refill_threshold

    @property
    def refill_status(self):
        """
        Get the refill status for display.
        Returns: 'requested', 'needed', or None
        """
        if self.refill_requested:
            return 'requested'
        if self.current_supply is not None and self.current_supply <= self.refill_threshold:
            return 'needed'
        return None

    @property
    def doses_per_day(self):
        """Calculate how many doses per day based on frequency."""
        frequency_map = {
            "daily": 1,
            "twice_daily": 2,
            "three_daily": 3,
            "four_daily": 4,
            "weekly": 0.14,  # Approximately 1/7
            "biweekly": 0.07,  # Approximately 1/14
            "monthly": 0.03,  # Approximately 1/30
            "as_needed": 0,
            "custom": 0,
        }
        return frequency_map.get(self.frequency, 1)

    @property
    def days_until_empty(self):
        """Estimate days until supply runs out."""
        if self.current_supply is None or self.doses_per_day == 0:
            return None
        return int(self.current_supply / self.doses_per_day)

    def pause(self, reason=""):
        """Pause this intake temporarily."""
        self.intake_status = self.STATUS_PAUSED
        self.paused_at = timezone.now()
        self.paused_reason = reason
        self.save(update_fields=["intake_status", "paused_at", "paused_reason", "updated_at"])

    def resume(self):
        """Resume a paused intake."""
        self.intake_status = self.STATUS_ACTIVE
        self.paused_at = None
        self.paused_reason = ""
        self.save(update_fields=["intake_status", "paused_at", "paused_reason", "updated_at"])

    def complete(self):
        """Mark this intake course as completed."""
        self.intake_status = self.STATUS_COMPLETED
        user_today = get_user_today(self.user) if self.user_id else timezone.now().date()
        self.end_date = user_today
        self.save(update_fields=["intake_status", "end_date", "updated_at"])

    def request_refill(self):
        """Mark that a refill has been requested."""
        self.refill_requested = True
        self.refill_requested_at = timezone.now()
        self.save(update_fields=["refill_requested", "refill_requested_at", "updated_at"])

    def clear_refill_request(self):
        """Clear the refill request (e.g., when refill is received)."""
        self.refill_requested = False
        self.refill_requested_at = None
        self.save(update_fields=["refill_requested", "refill_requested_at", "updated_at"])


class IntakeSchedule(models.Model):
    """
    Scheduled times for taking an intake item (medication or supplement).

    An intake item can have multiple scheduled times per day.
    For example, "twice daily" might be 8 AM and 8 PM.
    """

    # Time of day groupings for bulk actions
    TIME_MORNING = "morning"
    TIME_MID_MORNING = "mid_morning"
    TIME_LUNCH = "lunch"
    TIME_AFTERNOON = "afternoon"
    TIME_EVENING = "evening"
    TIME_NIGHTLY = "nightly"

    TIME_OF_DAY_CHOICES = [
        (TIME_MORNING, "Morning"),
        (TIME_MID_MORNING, "Mid-Morning"),
        (TIME_LUNCH, "Lunch"),
        (TIME_AFTERNOON, "Afternoon"),
        (TIME_EVENING, "Evening"),
        (TIME_NIGHTLY, "Nightly"),
    ]

    # Display order for time of day groupings
    TIME_OF_DAY_ORDER = {
        TIME_MORNING: 0,
        TIME_MID_MORNING: 1,
        TIME_LUNCH: 2,
        TIME_AFTERNOON: 3,
        TIME_EVENING: 4,
        TIME_NIGHTLY: 5,
    }

    intake = models.ForeignKey(
        Intake,
        on_delete=models.CASCADE,
        related_name="schedules",
    )

    scheduled_time = models.TimeField(
        help_text="Time of day to take this dose",
    )

    time_of_day = models.CharField(
        max_length=20,
        choices=TIME_OF_DAY_CHOICES,
        blank=True,
        help_text="Time period for grouping doses (Morning, Lunch, Evening, etc.)",
    )

    label = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional label like 'morning', 'bedtime', 'with dinner'",
    )

    # Days of week (for weekly/custom schedules)
    # Stored as comma-separated: "0,1,2,3,4,5,6" for every day
    # 0=Monday, 6=Sunday (Python weekday convention)
    days_of_week = models.CharField(
        max_length=20,
        default="0,1,2,3,4,5,6",
        help_text="Days to take this dose (0=Mon, 6=Sun)",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Is this schedule currently active?",
    )

    class Meta:
        ordering = ["scheduled_time"]
        verbose_name = "intake schedule"
        verbose_name_plural = "intake schedules"

    def save(self, *args, **kwargs):
        """
        Normalize scheduled_time to 15-minute increments, then
        auto-assign time_of_day based on scheduled_time if not set.
        """
        from apps.core.utils import normalize_to_quarter_hour

        self.scheduled_time = normalize_to_quarter_hour(self.scheduled_time)

        if not self.time_of_day and self.scheduled_time:
            from apps.core.time_windows import get_window_for_hour
            self.time_of_day = get_window_for_hour(self.scheduled_time.hour)
        super().save(*args, **kwargs)

    def __str__(self):
        time_str = self.scheduled_time.strftime("%I:%M %p")
        if self.label:
            return f"{self.intake.name} at {time_str} ({self.label})"
        return f"{self.intake.name} at {time_str}"

    @property
    def days_list(self):
        """Return days as a list of integers."""
        if not self.days_of_week:
            return []
        return [int(d) for d in self.days_of_week.split(",") if d.strip()]

    def applies_to_day(self, day_of_week):
        """Check if this schedule applies to a given day (0=Mon, 6=Sun)."""
        return day_of_week in self.days_list

    @property
    def time_of_day_display(self):
        """Return display name for time_of_day."""
        if self.time_of_day:
            return dict(self.TIME_OF_DAY_CHOICES).get(self.time_of_day, self.time_of_day)
        return None

    @property
    def time_of_day_order(self):
        """Return sort order for time_of_day grouping."""
        if self.time_of_day:
            return self.TIME_OF_DAY_ORDER.get(self.time_of_day, 99)
        return 99


class IntakeLog(UserOwnedModel):
    """
    Log of when an intake item (medication or supplement) was actually taken.

    Records both scheduled doses and PRN (as-needed) doses.
    """

    STATUS_TAKEN = "taken"
    STATUS_MISSED = "missed"
    STATUS_SKIPPED = "skipped"
    STATUS_LATE = "late"

    LOG_STATUS_CHOICES = [
        (STATUS_TAKEN, "Taken"),
        (STATUS_MISSED, "Missed"),
        (STATUS_SKIPPED, "Skipped"),
        (STATUS_LATE, "Taken Late"),
    ]

    # Source of the log entry — provenance for trust-critical auditing.
    # When debugging "did the user actually mark this complete?", the source
    # field answers "which code path created/updated this row?"
    #
    # Existing 3 values preserved for backward compat. Granular values added
    # 2026-05-23 (Phase 2 stabilization PR) so future incidents are debuggable
    # without DB forensics.
    SOURCE_MANUAL = "manual"             # Legacy: generic UI action
    SOURCE_COS = "cos"                   # Legacy: generic AI action
    SOURCE_ROUTINE = "routine"           # Legacy: routine completion bridge
    # ── Granular paths (added Phase 2) ────────────────────────────
    SOURCE_UI_PER_ITEM = "ui_per_item"           # Health/dashboard per-item checkbox
    SOURCE_UI_BLOCK_TOGGLE = "ui_block_toggle"   # Time-block bulk toggle (marks many)
    SOURCE_UI_SKIP = "ui_skip"                   # Explicit skip button
    SOURCE_LLM_ACTION = "llm_action"             # handle_take_medicine LLM tool call
    SOURCE_QUICK_REPLY = "quick_reply"           # Proactive check-in quick-reply button
    SOURCE_SMS_REPLY = "sms_reply"               # SMS reply handler
    SOURCE_CORRECTION = "correction"             # Retroactive user correction
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Manual (legacy)"),
        (SOURCE_COS, "CoS (legacy)"),
        (SOURCE_ROUTINE, "Routine (legacy)"),
        (SOURCE_UI_PER_ITEM, "UI — Per-Item Check"),
        (SOURCE_UI_BLOCK_TOGGLE, "UI — Block Toggle"),
        (SOURCE_UI_SKIP, "UI — Skip"),
        (SOURCE_LLM_ACTION, "LLM Action Handler"),
        (SOURCE_QUICK_REPLY, "Quick Reply"),
        (SOURCE_SMS_REPLY, "SMS Reply"),
        (SOURCE_CORRECTION, "User Correction"),
    ]

    intake = models.ForeignKey(
        Intake,
        on_delete=models.CASCADE,
        related_name="logs",
    )

    schedule = models.ForeignKey(
        IntakeSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
        help_text="Which scheduled dose this log is for",
    )

    # When the dose was due
    scheduled_date = models.DateField(
        help_text="Date this dose was scheduled for",
    )
    scheduled_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Time this dose was scheduled for",
    )

    # When the dose was actually taken
    taken_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the medicine was actually taken",
    )

    log_status = models.CharField(
        max_length=10,
        choices=LOG_STATUS_CHOICES,
        default=STATUS_TAKEN,
    )

    # For PRN doses
    is_prn_dose = models.BooleanField(
        default=False,
        help_text="Was this an as-needed (PRN) dose?",
    )
    prn_reason = models.CharField(
        max_length=500,
        blank=True,
        help_text="Reason for taking PRN dose (e.g., 'headache', 'anxiety')",
    )

    # Notes about this dose
    notes = models.TextField(
        blank=True,
        help_text="Notes about this dose (side effects, observations, etc.)",
    )

    is_user_corrected = models.BooleanField(
        default=False,
        help_text="True when user has manually edited a past log",
    )

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL,
        help_text="How this log was created (manual, CoS, routine bridge)",
    )

    class Meta:
        ordering = ["-scheduled_date", "-scheduled_time"]
        verbose_name = "intake log"
        verbose_name_plural = "intake logs"

    def __str__(self):
        status = self.get_log_status_display()
        return f"{self.intake.name} on {self.scheduled_date} - {status}"

    @property
    def was_on_time(self):
        """Check if the dose was taken within the grace period."""
        if self.log_status != self.STATUS_TAKEN or not self.taken_at:
            return False
        if not self.scheduled_time:
            return True  # PRN doses are always "on time"

        from datetime import datetime, timedelta
        import pytz

        # Get user's timezone for proper comparison (use timezone_iana for legacy format support)
        user_tz = pytz.timezone(self.user.preferences.timezone_iana)

        # Convert taken_at to user's local timezone
        taken_local = self.taken_at.astimezone(user_tz) if self.taken_at.tzinfo else user_tz.localize(self.taken_at)

        # Create scheduled datetime in user's timezone
        scheduled_dt = datetime.combine(self.scheduled_date, self.scheduled_time)
        scheduled_local = user_tz.localize(scheduled_dt)

        grace_minutes = self.intake.grace_period_minutes
        latest_ok = scheduled_local + timedelta(minutes=grace_minutes)

        return taken_local <= latest_ok

    @property
    def minutes_late(self):
        """Calculate how many minutes late the dose was taken."""
        if self.log_status not in [self.STATUS_TAKEN, self.STATUS_LATE] or not self.taken_at:
            return None
        if not self.scheduled_time:
            return 0  # PRN doses aren't late

        from datetime import datetime
        import pytz

        # Get user's timezone for proper comparison (use timezone_iana for legacy format support)
        user_tz = pytz.timezone(self.user.preferences.timezone_iana)

        # Convert taken_at to user's local timezone
        taken_local = self.taken_at.astimezone(user_tz) if self.taken_at.tzinfo else user_tz.localize(self.taken_at)

        # Create scheduled datetime in user's timezone
        scheduled_dt = datetime.combine(self.scheduled_date, self.scheduled_time)
        scheduled_local = user_tz.localize(scheduled_dt)

        diff = taken_local - scheduled_local
        return max(0, int(diff.total_seconds() / 60))

    def mark_taken(self, taken_at=None, source=None):
        """Mark this dose as taken.

        Args:
            taken_at: timestamp when dose was actually taken
                (defaults to now).
            source: provenance — one of IntakeLog.SOURCE_*. If provided,
                updates the source field so the most recent writer is
                recorded. If None, the existing source value is preserved
                (backward compatible with legacy callers).
        """
        self.taken_at = taken_at or timezone.now()

        # Check if it was late
        if self.scheduled_time:
            from datetime import datetime, timedelta
            import pytz

            # Get user's timezone for proper comparison (use timezone_iana for legacy format support)
            user_tz = pytz.timezone(self.user.preferences.timezone_iana)

            # Convert taken_at to user's local timezone
            taken_local = self.taken_at.astimezone(user_tz) if self.taken_at.tzinfo else user_tz.localize(self.taken_at)

            # Create scheduled datetime in user's timezone
            scheduled_dt = datetime.combine(self.scheduled_date, self.scheduled_time)
            scheduled_local = user_tz.localize(scheduled_dt)

            grace_minutes = self.intake.grace_period_minutes
            latest_ok = scheduled_local + timedelta(minutes=grace_minutes)

            if taken_local > latest_ok:
                self.log_status = self.STATUS_LATE
            else:
                self.log_status = self.STATUS_TAKEN
        else:
            self.log_status = self.STATUS_TAKEN

        update_fields = ["taken_at", "log_status", "updated_at"]
        if source is not None:
            self.source = source
            update_fields.append("source")
        self.save(update_fields=update_fields)

    def mark_skipped(self, reason="", source=None):
        """Mark this dose as intentionally skipped.

        Args:
            reason: optional skip reason stored in notes.
            source: provenance — one of IntakeLog.SOURCE_*. Updates the
                source field when provided; preserved otherwise.
        """
        self.log_status = self.STATUS_SKIPPED
        update_fields = ["log_status", "updated_at"]
        if reason:
            self.notes = reason
            update_fields.append("notes")
        if source is not None:
            self.source = source
            update_fields.append("source")
        self.save(update_fields=update_fields)

    def mark_missed(self):
        """Mark this dose as missed (not taken or skipped)."""
        self.log_status = self.STATUS_MISSED
        self.save(update_fields=["log_status", "updated_at"])


# =============================================================================
# Food Tracking Models
# =============================================================================


class FoodItem(models.Model):
    """
    Global food library - shared reference data, not user-specific.

    Contains nutritional information for common foods that all users can access.
    Data can come from manual entry, USDA database, barcode scanning, or AI recognition.
    """

    SOURCE_MANUAL = 'manual'
    SOURCE_USDA = 'usda'
    SOURCE_BARCODE = 'barcode'
    SOURCE_AI = 'ai'
    SOURCE_FATSECRET = 'fatsecret'
    SOURCE_OPENFOODFACTS = 'openfoodfacts'
    SOURCE_USER_CREATED = 'user_created'
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, 'Manual Entry'),
        (SOURCE_USDA, 'USDA Database'),
        (SOURCE_BARCODE, 'Barcode Scan'),
        (SOURCE_AI, 'AI Recognition'),
        (SOURCE_FATSECRET, 'FatSecret API'),
        (SOURCE_OPENFOODFACTS, 'Open Food Facts'),
        (SOURCE_USER_CREATED, 'User Created'),
    ]

    # Basic info
    name = models.CharField(max_length=300)
    brand = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    barcode = models.CharField(max_length=50, blank=True, db_index=True)
    fatsecret_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        db_index=True,
        help_text="FatSecret API food ID for re-verification",
    )

    # External IDs for cross-referencing multiple data sources
    external_ids = models.JSONField(
        default=dict,
        blank=True,
        help_text='{"fatsecret_id": "...", "off_barcode": "...", "usda_fdb_id": "..."}',
    )

    # Source & verification
    data_source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL,
    )
    source_reference = models.CharField(
        max_length=200,
        blank=True,
        help_text="USDA ID, API reference, etc.",
    )
    is_verified = models.BooleanField(default=False)

    # Version tracking — bumped on any nutrient change
    version = models.PositiveIntegerField(
        default=1,
        help_text="Incremented when nutrient values change",
    )

    # Verification by user
    verified_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_food_items',
        help_text="User who last verified/corrected this item",
    )

    # Serving information
    serving_size = models.DecimalField(max_digits=8, decimal_places=2)
    serving_unit = models.CharField(
        max_length=50,
        help_text="e.g., grams, oz, cups, pieces",
    )
    servings_per_container = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # Core Macronutrients (per serving)
    calories = models.DecimalField(max_digits=8, decimal_places=2)
    protein_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    carbohydrates_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fiber_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    sugar_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fat_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    saturated_fat_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    unsaturated_fat_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    trans_fat_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    # Micronutrients (per serving) - all nullable for flexibility
    sodium_mg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    cholesterol_mg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    potassium_mg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    calcium_mg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    iron_mg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    vitamin_a_iu = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    vitamin_c_mg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    vitamin_d_iu = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    vitamin_b12_mcg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # Dietary attributes
    is_vegan = models.BooleanField(default=False)
    is_vegetarian = models.BooleanField(default=False)
    is_keto_friendly = models.BooleanField(default=False)
    is_gluten_free = models.BooleanField(default=False)
    is_dairy_free = models.BooleanField(default=False)
    is_nut_free = models.BooleanField(default=False)
    is_low_sodium = models.BooleanField(default=False)
    is_low_carb = models.BooleanField(default=False)

    # Metadata
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When external API data was last verified/refreshed",
    )

    class Meta:
        ordering = ['name']
        verbose_name = "food item"
        verbose_name_plural = "food items"
        indexes = [
            models.Index(fields=['barcode']),
            models.Index(fields=['name']),
            models.Index(fields=['fatsecret_id']),
        ]

    def __str__(self):
        if self.brand:
            return f"{self.name} ({self.brand})"
        return self.name

    @property
    def net_carbs_g(self):
        """Calculate net carbs (total carbs - fiber)."""
        return self.carbohydrates_g - self.fiber_g


class CustomFood(UserOwnedModel):
    """
    User-created food items (personal recipes, custom entries).

    Each user can create their own custom foods that only they can see and use.
    """

    name = models.CharField(max_length=300)
    description = models.TextField(blank=True)

    # Serving info
    serving_size = models.DecimalField(max_digits=8, decimal_places=2)
    serving_unit = models.CharField(max_length=50)

    # Macros (per serving)
    calories = models.DecimalField(max_digits=8, decimal_places=2)
    protein_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    carbohydrates_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fiber_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    sugar_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fat_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    saturated_fat_g = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    # Optional micronutrients
    sodium_mg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # For recipes - link to component foods (future enhancement)
    is_recipe = models.BooleanField(default=False)
    recipe_ingredients = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {food_id, quantity, unit} for recipe ingredients",
    )

    class Meta:
        ordering = ['name']
        verbose_name = "custom food"
        verbose_name_plural = "custom foods"

    def __str__(self):
        return self.name

    @property
    def net_carbs_g(self):
        """Calculate net carbs (total carbs - fiber)."""
        return self.carbohydrates_g - self.fiber_g


class FoodEntry(UserOwnedModel):
    """
    Individual food consumption log entry.

    Records what the user ate, when, and in what context.
    Stores a snapshot of nutritional data at the time of logging for historical accuracy.
    """

    # Entry source tracking
    SOURCE_MANUAL = 'manual'
    SOURCE_BARCODE = 'barcode'
    SOURCE_CAMERA = 'camera'
    SOURCE_VOICE = 'voice'
    SOURCE_QUICK_ADD = 'quick_add'
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, 'Manual Entry'),
        (SOURCE_BARCODE, 'Barcode Scan'),
        (SOURCE_CAMERA, 'Camera Recognition'),
        (SOURCE_VOICE, 'Voice Input'),
        (SOURCE_QUICK_ADD, 'Quick Add'),
    ]

    # Meal type
    MEAL_BREAKFAST = 'breakfast'
    MEAL_LUNCH = 'lunch'
    MEAL_DINNER = 'dinner'
    MEAL_SNACK = 'snack'
    MEAL_CHOICES = [
        (MEAL_BREAKFAST, 'Breakfast'),
        (MEAL_LUNCH, 'Lunch'),
        (MEAL_DINNER, 'Dinner'),
        (MEAL_SNACK, 'Snack'),
    ]

    # Food reference (one of these will be set, or none for quick-add)
    food_item = models.ForeignKey(
        FoodItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entries',
    )
    custom_food = models.ForeignKey(
        CustomFood,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entries',
    )

    # Snapshot of food data at time of logging (immutable record)
    food_name = models.CharField(max_length=300)
    food_brand = models.CharField(max_length=200, blank=True)

    # Quantity consumed
    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=1,
        help_text="Number of servings",
    )
    serving_size = models.DecimalField(max_digits=8, decimal_places=2)
    serving_unit = models.CharField(max_length=50)

    # Calculated totals (stored, not derived, for historical accuracy)
    total_calories = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_protein_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_carbohydrates_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_fiber_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_sugar_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_fat_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_saturated_fat_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Optional micronutrient totals
    total_sodium_mg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_cholesterol_mg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_potassium_mg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Timing & context
    logged_date = models.DateField()
    logged_time = models.TimeField(null=True, blank=True)
    meal_type = models.CharField(
        max_length=20,
        choices=MEAL_CHOICES,
        default=MEAL_SNACK,
    )

    # Location context (WLJ differentiator)
    LOCATION_HOME = 'home'
    LOCATION_RESTAURANT = 'restaurant'
    LOCATION_WORK = 'work'
    LOCATION_TRAVEL = 'travel'
    LOCATION_OTHER = 'other'
    LOCATION_CHOICES = [
        (LOCATION_HOME, 'Home'),
        (LOCATION_RESTAURANT, 'Restaurant'),
        (LOCATION_WORK, 'Work'),
        (LOCATION_TRAVEL, 'Travel'),
        (LOCATION_OTHER, 'Other'),
    ]
    location = models.CharField(
        max_length=20,
        choices=LOCATION_CHOICES,
        blank=True,
    )

    # Eating pace context
    PACE_RUSHED = 'rushed'
    PACE_NORMAL = 'normal'
    PACE_SLOW = 'slow'
    PACE_CHOICES = [
        (PACE_RUSHED, 'Rushed'),
        (PACE_NORMAL, 'Normal'),
        (PACE_SLOW, 'Slow/Mindful'),
    ]
    eating_pace = models.CharField(
        max_length=20,
        choices=PACE_CHOICES,
        blank=True,
    )

    # Hunger/fullness tracking
    hunger_level_before = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Hunger level before eating (1-5)",
    )
    fullness_level_after = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Fullness level after eating (1-5)",
    )

    # Emotional/contextual tags
    mood_tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tags like 'stressed', 'happy', 'tired'",
    )
    notes = models.TextField(blank=True)

    # Source tracking
    entry_source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL,
    )
    ai_confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="AI confidence score for camera/voice entries",
    )

    # === NEW: Hybrid History Model fields ===

    # Immutable snapshot of per-serving nutrients at log time
    snapshot_nutrients = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Per-serving nutrient values at time of logging. "
            "Format: {calories: 10, protein_g: 0, carbohydrates_g: 4, ...}"
        ),
    )

    # Reference to FoodItem version used at log time
    food_item_version = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="FoodItem.version at the time this entry was logged",
    )

    # Data source used for this specific entry (more granular than entry_source)
    DATA_SOURCE_LOCAL = 'local'
    DATA_SOURCE_FATSECRET = 'fatsecret'
    DATA_SOURCE_OPENFOODFACTS = 'openfoodfacts'
    DATA_SOURCE_AI_GUESS = 'ai_guess'
    DATA_SOURCE_USER_OVERRIDE = 'user_override'
    DATA_SOURCE_QUICK_ADD = 'quick_add'
    DATA_SOURCE_MANUAL = 'manual'
    DATA_SOURCE_CHOICES = [
        (DATA_SOURCE_LOCAL, 'Local Database'),
        (DATA_SOURCE_FATSECRET, 'FatSecret API'),
        (DATA_SOURCE_OPENFOODFACTS, 'Open Food Facts'),
        (DATA_SOURCE_AI_GUESS, 'AI Estimate'),
        (DATA_SOURCE_USER_OVERRIDE, 'User Override'),
        (DATA_SOURCE_QUICK_ADD, 'Quick Add'),
        (DATA_SOURCE_MANUAL, 'Manual Entry'),
    ]
    data_source_used = models.CharField(
        max_length=30,
        choices=DATA_SOURCE_CHOICES,
        default=DATA_SOURCE_MANUAL,
        blank=True,
        help_text="Which data source provided the nutrient values for this entry",
    )

    # Confidence score for nutrient accuracy (0-100)
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Confidence in nutrient accuracy (0-100)",
    )

    # Copy/template tracking
    copied_from_entry = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='copies',
        help_text="Entry this was copied from",
    )
    applied_template = models.ForeignKey(
        'MealTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='applied_entries',
        help_text="Meal template that was applied to create this entry",
    )

    # Favorite for quick re-logging
    is_favorite = models.BooleanField(
        default=False,
        help_text="Mark as favorite for quick access",
    )

    class Meta:
        ordering = ['-logged_date', '-logged_time', '-created_at']
        verbose_name = "food entry"
        verbose_name_plural = "food entries"
        indexes = [
            models.Index(fields=['user', 'logged_date']),
            models.Index(fields=['logged_date', 'meal_type']),
        ]

    def __str__(self):
        return f"{self.food_name} ({self.total_calories} cal) on {self.logged_date}"

    def calculate_totals(self):
        """
        Calculate total nutrition from snapshot_nutrients * quantity.

        Uses snapshot_nutrients (per-serving at log time) as the authoritative
        source. Falls back to food_item/custom_food if no snapshot exists
        (backward compat for pre-migration entries).
        """
        from apps.health.services.nutrition_calculator import compute_totals, build_snapshot

        # Use snapshot if available, otherwise build from source
        if self.snapshot_nutrients:
            snapshot = self.snapshot_nutrients
        else:
            source = self.food_item or self.custom_food
            if not source:
                return
            snapshot = build_snapshot(source)
            self.snapshot_nutrients = snapshot

        totals = compute_totals(snapshot, self.quantity)
        self.total_calories = totals.get('total_calories', 0) or 0
        self.total_protein_g = totals.get('total_protein_g', 0) or 0
        self.total_carbohydrates_g = totals.get('total_carbohydrates_g', 0) or 0
        self.total_fiber_g = totals.get('total_fiber_g', 0) or 0
        self.total_sugar_g = totals.get('total_sugar_g', 0) or 0
        self.total_fat_g = totals.get('total_fat_g', 0) or 0
        self.total_saturated_fat_g = totals.get('total_saturated_fat_g', 0) or 0
        self.total_sodium_mg = totals.get('total_sodium_mg')
        self.total_cholesterol_mg = totals.get('total_cholesterol_mg')
        self.total_potassium_mg = totals.get('total_potassium_mg')

    @property
    def total_net_carbs_g(self):
        """Calculate net carbs (total carbs - fiber)."""
        return self.total_carbohydrates_g - self.total_fiber_g


class DailyNutritionSummary(UserOwnedModel):
    """
    Aggregated daily nutrition totals.

    Versioned for potential AI reprocessing and recalculation.
    Auto-generated from FoodEntry records for a given day.
    """

    summary_date = models.DateField()

    # Totals
    total_calories = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_protein_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_carbohydrates_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_fiber_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_sugar_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_fat_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_saturated_fat_g = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_sodium_mg = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Meal counts
    breakfast_count = models.PositiveSmallIntegerField(default=0)
    lunch_count = models.PositiveSmallIntegerField(default=0)
    dinner_count = models.PositiveSmallIntegerField(default=0)
    snack_count = models.PositiveSmallIntegerField(default=0)

    # Macro percentages
    protein_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    carb_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    fat_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Versioning for recalculation
    calculation_version = models.PositiveSmallIntegerField(default=1)
    last_recalculated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-summary_date']
        verbose_name = "daily nutrition summary"
        verbose_name_plural = "daily nutrition summaries"
        unique_together = ['user', 'summary_date']

    def __str__(self):
        return f"{self.user.email} - {self.summary_date}: {self.total_calories} cal"

    def recalculate(self):
        """Recalculate summary from raw FoodEntry records."""
        from django.db.models import Sum, Count, Q

        entries = FoodEntry.objects.filter(
            user=self.user,
            logged_date=self.summary_date,
            status='active',
        )

        totals = entries.aggregate(
            cal=Sum('total_calories'),
            pro=Sum('total_protein_g'),
            carb=Sum('total_carbohydrates_g'),
            fib=Sum('total_fiber_g'),
            sug=Sum('total_sugar_g'),
            fat=Sum('total_fat_g'),
            sat=Sum('total_saturated_fat_g'),
            sod=Sum('total_sodium_mg'),
            breakfast=Count('id', filter=Q(meal_type=FoodEntry.MEAL_BREAKFAST)),
            lunch=Count('id', filter=Q(meal_type=FoodEntry.MEAL_LUNCH)),
            dinner=Count('id', filter=Q(meal_type=FoodEntry.MEAL_DINNER)),
            snack=Count('id', filter=Q(meal_type=FoodEntry.MEAL_SNACK)),
        )

        self.total_calories = totals['cal'] or 0
        self.total_protein_g = totals['pro'] or 0
        self.total_carbohydrates_g = totals['carb'] or 0
        self.total_fiber_g = totals['fib'] or 0
        self.total_sugar_g = totals['sug'] or 0
        self.total_fat_g = totals['fat'] or 0
        self.total_saturated_fat_g = totals['sat'] or 0
        self.total_sodium_mg = totals['sod'] or 0
        self.breakfast_count = totals['breakfast']
        self.lunch_count = totals['lunch']
        self.dinner_count = totals['dinner']
        self.snack_count = totals['snack']

        # Calculate macro percentages (protein/carbs = 4 cal/g, fat = 9 cal/g)
        total_macro_cals = (
            float(self.total_protein_g) * 4
            + float(self.total_carbohydrates_g) * 4
            + float(self.total_fat_g) * 9
        )
        if total_macro_cals > 0:
            self.protein_percentage = (float(self.total_protein_g) * 4 / total_macro_cals) * 100
            self.carb_percentage = (float(self.total_carbohydrates_g) * 4 / total_macro_cals) * 100
            self.fat_percentage = (float(self.total_fat_g) * 9 / total_macro_cals) * 100

        self.calculation_version += 1
        self.save()

    @property
    def total_entry_count(self):
        """Total number of food entries for this day."""
        return self.breakfast_count + self.lunch_count + self.dinner_count + self.snack_count


# =============================================================================
# Medical Provider Models
# =============================================================================


class MedicalProvider(UserOwnedModel):
    """
    Healthcare provider (doctor, clinic, specialist) contact information.

    Stores provider details with optional AI-assisted lookup for contact info.
    Each provider can have multiple associated staff members (PA, nurse, etc.)
    """

    SPECIALTY_CHOICES = [
        ("primary_care", "Primary Care / Family Medicine"),
        ("internal_medicine", "Internal Medicine"),
        ("pediatrics", "Pediatrics"),
        ("obgyn", "OB/GYN"),
        ("cardiology", "Cardiology"),
        ("dermatology", "Dermatology"),
        ("endocrinology", "Endocrinology"),
        ("gastroenterology", "Gastroenterology"),
        ("neurology", "Neurology"),
        ("oncology", "Oncology"),
        ("ophthalmology", "Ophthalmology"),
        ("orthopedics", "Orthopedics"),
        ("psychiatry", "Psychiatry"),
        ("pulmonology", "Pulmonology"),
        ("rheumatology", "Rheumatology"),
        ("urology", "Urology"),
        ("dentist", "Dentist"),
        ("optometrist", "Optometrist"),
        ("chiropractor", "Chiropractor"),
        ("physical_therapy", "Physical Therapy"),
        ("mental_health", "Mental Health / Therapist"),
        ("pharmacy", "Pharmacy"),
        ("urgent_care", "Urgent Care"),
        ("hospital", "Hospital"),
        ("lab", "Laboratory"),
        ("imaging", "Imaging / Radiology"),
        ("other", "Other"),
    ]

    # Basic Info
    name = models.CharField(
        max_length=200,
        help_text="Provider or practice name",
    )
    specialty = models.CharField(
        max_length=50,
        choices=SPECIALTY_CHOICES,
        default="primary_care",
    )
    credentials = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g., MD, DO, DDS, PhD, PA-C, NP",
    )

    # Contact Information
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Primary phone number",
    )
    phone_alt = models.CharField(
        max_length=20,
        blank=True,
        help_text="Alternate phone (scheduling, etc.)",
    )
    fax = models.CharField(
        max_length=20,
        blank=True,
    )
    email = models.EmailField(
        blank=True,
        help_text="Office email address",
    )
    website = models.URLField(
        blank=True,
        help_text="Practice website",
    )

    # Address
    address_line1 = models.CharField(
        max_length=200,
        blank=True,
    )
    address_line2 = models.CharField(
        max_length=200,
        blank=True,
    )
    city = models.CharField(
        max_length=100,
        blank=True,
    )
    state = models.CharField(
        max_length=50,
        blank=True,
    )
    postal_code = models.CharField(
        max_length=20,
        blank=True,
    )
    country = models.CharField(
        max_length=100,
        blank=True,
        default="USA",
    )

    # Patient Portal
    portal_url = models.URLField(
        blank=True,
        help_text="Link to patient portal",
    )
    portal_username = models.CharField(
        max_length=100,
        blank=True,
        help_text="Username for patient portal (stored locally only)",
    )

    # Additional Info
    npi_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="National Provider Identifier (10 digits)",
    )
    accepts_insurance = models.BooleanField(
        default=True,
        help_text="Does this provider accept insurance?",
    )
    insurance_notes = models.TextField(
        blank=True,
        help_text="Notes about accepted insurance plans",
    )

    # Office Hours (optional JSON for flexibility)
    office_hours = models.JSONField(
        default=dict,
        blank=True,
        help_text="Office hours by day: {'monday': '8am-5pm', ...}",
    )

    # Preferences
    is_primary = models.BooleanField(
        default=False,
        help_text="Is this your primary care provider?",
    )

    # Notes
    notes = models.TextField(
        blank=True,
        help_text="Personal notes about this provider",
    )

    # AI Lookup tracking
    ai_lookup_completed = models.BooleanField(
        default=False,
        help_text="Was AI used to populate provider info?",
    )
    ai_lookup_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When AI lookup was performed",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "medical provider"
        verbose_name_plural = "medical providers"

    def __str__(self):
        if self.credentials:
            return f"{self.name}, {self.credentials}"
        return self.name

    @property
    def full_address(self):
        """Return formatted full address."""
        parts = []
        if self.address_line1:
            parts.append(self.address_line1)
        if self.address_line2:
            parts.append(self.address_line2)
        city_state_zip = []
        if self.city:
            city_state_zip.append(self.city)
        if self.state:
            city_state_zip.append(self.state)
        if city_state_zip:
            line = ", ".join(city_state_zip)
            if self.postal_code:
                line += f" {self.postal_code}"
            parts.append(line)
        return "\n".join(parts) if parts else ""

    @property
    def staff_count(self):
        """Number of associated staff members."""
        return self.staff.count()


class ProviderStaff(UserOwnedModel):
    """
    Supporting staff for a medical provider (PA, nurse, medical assistant, etc.)

    Manually entered by user - no AI lookup for staff members.
    """

    ROLE_CHOICES = [
        ("physician_assistant", "Physician Assistant (PA)"),
        ("nurse_practitioner", "Nurse Practitioner (NP)"),
        ("registered_nurse", "Registered Nurse (RN)"),
        ("licensed_nurse", "Licensed Practical Nurse (LPN)"),
        ("medical_assistant", "Medical Assistant (MA)"),
        ("front_desk", "Front Desk / Receptionist"),
        ("billing", "Billing Specialist"),
        ("scheduler", "Scheduler / Coordinator"),
        ("lab_tech", "Lab Technician"),
        ("xray_tech", "X-Ray Technician"),
        ("pharmacist", "Pharmacist"),
        ("pharmacy_tech", "Pharmacy Technician"),
        ("other", "Other"),
    ]

    # Link to provider
    provider = models.ForeignKey(
        MedicalProvider,
        on_delete=models.CASCADE,
        related_name="staff",
    )

    # Basic Info
    name = models.CharField(
        max_length=200,
        help_text="Staff member's name",
    )
    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default="other",
    )
    title = models.CharField(
        max_length=100,
        blank=True,
        help_text="Job title or role description",
    )

    # Contact (usually via main office, but could be direct)
    phone_extension = models.CharField(
        max_length=20,
        blank=True,
        help_text="Phone extension if applicable",
    )
    direct_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Direct phone number if different from office",
    )
    email = models.EmailField(
        blank=True,
        help_text="Direct email if available",
    )

    # Notes
    notes = models.TextField(
        blank=True,
        help_text="Notes about this staff member",
    )

    class Meta:
        ordering = ["provider", "name"]
        verbose_name = "provider staff"
        verbose_name_plural = "provider staff"

    def __str__(self):
        role_display = self.get_role_display()
        return f"{self.name} ({role_display}) - {self.provider.name}"


class NutritionGoals(UserOwnedModel):
    """
    User's personalized nutrition targets.

    Defines daily calorie, macro, and nutrient goals.
    Can have multiple goals over time with effective dates.
    """

    # Calorie target
    daily_calorie_target = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Daily calorie goal",
    )

    # Macro targets (grams)
    daily_protein_target_g = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Daily protein goal in grams",
    )
    daily_carb_target_g = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Daily carbohydrate goal in grams",
    )
    daily_fat_target_g = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Daily fat goal in grams",
    )
    daily_fiber_target_g = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Daily fiber goal in grams",
    )

    # Limits
    daily_sodium_limit_mg = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum daily sodium in mg",
    )
    daily_sugar_limit_g = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum daily sugar in grams",
    )

    # Dietary preferences
    dietary_preferences = models.JSONField(
        default=list,
        blank=True,
        help_text="e.g., ['vegan', 'gluten_free']",
    )
    allergies = models.JSONField(
        default=list,
        blank=True,
        help_text="e.g., ['nuts', 'dairy']",
    )

    # Active period
    effective_from = models.DateField(
        help_text="When these goals became active",
    )
    effective_until = models.DateField(
        null=True,
        blank=True,
        help_text="When these goals end (null = still active)",
    )

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-effective_from']
        verbose_name = "nutrition goals"
        verbose_name_plural = "nutrition goals"

    def __str__(self):
        return f"{self.user.email} goals from {self.effective_from}"

    @property
    def is_active(self):
        """Check if these goals are currently active."""
        user_today = get_user_today(self.user) if self.user_id else timezone.now().date()
        if self.effective_until:
            return self.effective_from <= user_today <= self.effective_until
        return self.effective_from <= user_today

    def save(self, *args, **kwargs):
        """Set default effective_from if not provided."""
        if not self.effective_from:
            user_today = get_user_today(self.user) if self.user_id else timezone.now().date()
            self.effective_from = user_today
        super().save(*args, **kwargs)


# =============================================================================
# Dexcom CGM Integration
# =============================================================================


class DexcomCredential(models.Model):
    """
    Store Dexcom OAuth credentials for CGM data access.

    Follows OAuth 2.0 pattern matching GoogleCalendarCredential.
    Dexcom API uses standard OAuth2 with access/refresh tokens.

    Security Note (CISO Review 2026-01-12):
        OAuth tokens are encrypted at rest using Fernet AES-256 encryption.
        Use the property accessors (access_token_decrypted, etc.) to get
        plaintext values. Raw database fields contain encrypted data.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dexcom_credential'
    )

    # OAuth tokens (encrypted at rest)
    # Use the _decrypted property accessors for plaintext values
    access_token = models.TextField(help_text="Encrypted access token")
    refresh_token = models.TextField(blank=True, help_text="Encrypted refresh token")
    token_expiry = models.DateTimeField(null=True, blank=True)

    # Dexcom user ID (hashed, returned by API)
    dexcom_user_id = models.CharField(max_length=255, blank=True)

    # Sync settings
    sync_enabled = models.BooleanField(
        default=True,
        help_text="Enable automatic glucose sync"
    )
    days_to_sync = models.PositiveIntegerField(
        default=7,
        help_text="Days of glucose history to sync"
    )

    # Tracking
    last_sync = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=50, blank=True)
    last_sync_message = models.TextField(blank=True)
    last_sync_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dexcom Credential"
        verbose_name_plural = "Dexcom Credentials"

    def __str__(self):
        return f"Dexcom for {self.user.email}"

    @property
    def is_token_expired(self):
        """Check if the access token has expired."""
        if not self.token_expiry:
            return True
        return timezone.now() >= self.token_expiry

    @property
    def is_connected(self):
        """Check if we have valid credentials."""
        return bool(self.access_token)

    # =========================================================================
    # Encrypted Token Accessors (CISO Review 2026-01-12)
    # =========================================================================

    @property
    def access_token_decrypted(self):
        """Get the decrypted access token."""
        from apps.core.encryption import decrypt_oauth_token_safe
        value, success = decrypt_oauth_token_safe(self.access_token)
        if not success:
            self._decryption_failed = True
        return value

    @property
    def refresh_token_decrypted(self):
        """Get the decrypted refresh token."""
        from apps.core.encryption import decrypt_oauth_token_safe
        value, success = decrypt_oauth_token_safe(self.refresh_token)
        if not success:
            self._decryption_failed = True
        return value

    def has_decryption_error(self):
        """
        Check if any token decryption has failed.

        This should be called after accessing decrypted properties to determine
        if the credentials need to be re-authenticated.

        Returns:
            bool: True if decryption failed, False otherwise
        """
        # Reset flag and test all tokens
        self._decryption_failed = False
        from apps.core.encryption import decrypt_oauth_token_safe

        for field in [self.access_token, self.refresh_token]:
            if field:
                _, success = decrypt_oauth_token_safe(field)
                if not success:
                    return True
        return False

    def set_access_token(self, plaintext):
        """Set and encrypt the access token."""
        from apps.core.encryption import encrypt_oauth_token
        self.access_token = encrypt_oauth_token(plaintext)

    def set_refresh_token(self, plaintext):
        """Set and encrypt the refresh token."""
        from apps.core.encryption import encrypt_oauth_token
        self.refresh_token = encrypt_oauth_token(plaintext) if plaintext else ''

    def get_credentials_dict(self):
        """Return credentials in format for API calls (decrypted)."""
        return {
            'access_token': self.access_token_decrypted,
            'refresh_token': self.refresh_token_decrypted,
            'token_expiry': self.token_expiry.isoformat() if self.token_expiry else None,
        }

    def update_from_credentials(self, credentials_dict):
        """Update model from credentials dictionary (encrypts tokens)."""
        if 'access_token' in credentials_dict:
            self.set_access_token(credentials_dict.get('access_token', ''))
        if 'refresh_token' in credentials_dict:
            self.set_refresh_token(credentials_dict.get('refresh_token', ''))

        # Handle expiry
        expiry = credentials_dict.get('token_expiry')
        if expiry:
            if isinstance(expiry, str):
                from datetime import datetime
                self.token_expiry = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            else:
                self.token_expiry = expiry

        if credentials_dict.get('dexcom_user_id'):
            self.dexcom_user_id = credentials_dict['dexcom_user_id']

        self.save()

    def record_sync(self, success=True, message='', count=0):
        """Record the result of a sync operation."""
        self.last_sync = timezone.now()
        self.last_sync_status = 'success' if success else 'error'
        self.last_sync_message = message
        self.last_sync_count = count
        self.save(update_fields=[
            'last_sync', 'last_sync_status', 'last_sync_message',
            'last_sync_count', 'updated_at'
        ])


# =============================================================================
# Sleep Tracking
# =============================================================================


class SleepEntry(UserOwnedModel):
    """
    Sleep tracking entry with wearable-grade data support.

    Designed to capture both manual entries and synced data from:
    - Apple HealthKit (via iOS app)
    - Google Fit (via Android app)
    - Fitbit, Garmin, Oura, etc.

    Sleep stages follow Apple Health conventions:
    - awake: Time spent awake during sleep session
    - rem: REM (rapid eye movement) sleep - dreams, memory consolidation
    - light: Light/Core sleep - transition sleep
    - deep: Deep/Slow-wave sleep - physical restoration

    Quality score is calculated from:
    - Sleep efficiency (time asleep / time in bed)
    - Stage distribution (enough deep & REM)
    - Interruption count
    """

    SOURCE_CHOICES = [
        ("manual", "Manual Entry"),
        ("apple_health", "Apple Health"),
        ("google_fit", "Google Fit"),
        ("fitbit", "Fitbit"),
        ("garmin", "Garmin"),
        ("oura", "Oura Ring"),
        ("samsung_health", "Samsung Health"),
        ("whoop", "WHOOP"),
        ("other", "Other App/Device"),
    ]

    QUALITY_CHOICES = [
        ("excellent", "Excellent - Woke refreshed"),
        ("good", "Good - Felt rested"),
        ("fair", "Fair - Okay"),
        ("poor", "Poor - Tired"),
        ("terrible", "Terrible - Exhausted"),
    ]

    # Core sleep times
    sleep_date = models.DateField(
        help_text="Date of sleep (the night of - e.g., sleep on Jan 5 night is Jan 5)",
    )
    bedtime = models.DateTimeField(
        help_text="When you went to bed / sleep session started",
    )
    wake_time = models.DateTimeField(
        help_text="When you woke up / sleep session ended",
    )

    # Duration metrics (in minutes for precision)
    total_duration_minutes = models.PositiveIntegerField(
        help_text="Total time in bed (bedtime to wake_time) in minutes",
    )
    asleep_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Actual time asleep in minutes (excludes awake periods)",
    )

    # Sleep stages (in minutes) - populated by wearables, optional for manual
    stage_awake_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time spent awake during sleep session",
    )
    stage_rem_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time in REM sleep (dreams, memory consolidation)",
    )
    stage_light_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time in light/core sleep",
    )
    stage_deep_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time in deep/slow-wave sleep (physical restoration)",
    )

    # Quality indicators
    quality_rating = models.CharField(
        max_length=20,
        choices=QUALITY_CHOICES,
        blank=True,
        help_text="Subjective quality rating (manual entry or morning check-in)",
    )
    quality_score = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Calculated quality score 0-100 (from stages, efficiency, etc.)",
    )
    sleep_efficiency = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Sleep efficiency percentage (time asleep / time in bed * 100)",
    )

    # Interruptions
    interruption_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times woken during the night",
    )
    total_awake_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total time spent awake after initially falling asleep",
    )

    # Heart rate during sleep (from wearables)
    heart_rate_avg = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Average heart rate during sleep (BPM)",
    )
    heart_rate_min = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum heart rate during sleep (BPM)",
    )
    heart_rate_max = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum heart rate during sleep (BPM)",
    )

    # Respiratory rate (some wearables track this)
    respiratory_rate = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Average breaths per minute during sleep",
    )

    # Heart Rate Variability (HRV SDNN in milliseconds)
    hrv_value = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Heart Rate Variability SDNN in milliseconds",
    )

    # VO2 Max (mL/kg/min - cardiorespiratory fitness)
    vo2_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="VO2 Max in mL/kg/min (cardio fitness level)",
    )

    # Caffeine intake (milligrams)
    caffeine_mg = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Daily caffeine intake in milligrams",
    )

    # Mindful minutes (meditation/mindfulness time)
    mindful_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Daily mindful minutes (meditation, breathing exercises)",
    )

    # Source tracking for wearable sync
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="manual",
    )
    sync_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="External ID from synced source to prevent duplicates",
    )
    recorded_at = models.DateTimeField(
        default=timezone.now,
        help_text="When this entry was recorded/synced",
    )

    # User notes for context
    notes = models.TextField(
        blank=True,
        help_text="Notes about sleep (e.g., 'took melatonin', 'stressed about work')",
    )

    # Factors that may have affected sleep
    factors = models.JSONField(
        default=list,
        blank=True,
        help_text="Factors affecting sleep: caffeine, alcohol, exercise, stress, etc.",
    )

    class Meta:
        ordering = ["-sleep_date", "-bedtime"]
        verbose_name = "sleep entry"
        verbose_name_plural = "sleep entries"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "sleep_date", "source", "sync_id"],
                name="unique_sleep_per_night_per_source",
                condition=models.Q(sync_id__gt=""),
            ),
        ]
        indexes = [
            models.Index(fields=["user", "sleep_date"]),
            models.Index(fields=["source", "sync_id"]),
        ]

    def __str__(self):
        hours = self.total_duration_minutes / 60 if self.total_duration_minutes else 0
        return f"{hours:.1f}h sleep on {self.sleep_date}"

    def save(self, *args, **kwargs):
        """Calculate derived fields before saving."""
        # Calculate total duration from times if not set
        if self.bedtime and self.wake_time and not self.total_duration_minutes:
            delta = self.wake_time - self.bedtime
            self.total_duration_minutes = int(delta.total_seconds() / 60)

        # Calculate sleep efficiency if we have the data
        if self.asleep_duration_minutes and self.total_duration_minutes:
            self.sleep_efficiency = (
                self.asleep_duration_minutes / self.total_duration_minutes
            ) * 100

        # Calculate quality score if we have stage data
        if self.has_stage_data:
            self.quality_score = self._calculate_quality_score()

        super().save(*args, **kwargs)

    @property
    def has_stage_data(self):
        """Check if sleep stage data is available."""
        return any([
            self.stage_rem_minutes,
            self.stage_light_minutes,
            self.stage_deep_minutes,
        ])

    @property
    def total_hours(self):
        """Total time in bed in hours."""
        if self.total_duration_minutes:
            return round(self.total_duration_minutes / 60, 1)
        return None

    @property
    def asleep_hours(self):
        """Actual time asleep in hours."""
        if self.asleep_duration_minutes:
            return round(self.asleep_duration_minutes / 60, 1)
        return None

    @property
    def deep_sleep_percentage(self):
        """Percentage of sleep spent in deep sleep."""
        if self.stage_deep_minutes and self.asleep_duration_minutes:
            return round((self.stage_deep_minutes / self.asleep_duration_minutes) * 100, 1)
        return None

    @property
    def rem_percentage(self):
        """Percentage of sleep spent in REM."""
        if self.stage_rem_minutes and self.asleep_duration_minutes:
            return round((self.stage_rem_minutes / self.asleep_duration_minutes) * 100, 1)
        return None

    @property
    def quality_display(self):
        """Human-readable quality description."""
        if self.quality_rating:
            return dict(self.QUALITY_CHOICES).get(self.quality_rating, self.quality_rating)
        if self.quality_score:
            if self.quality_score >= 85:
                return "Excellent"
            elif self.quality_score >= 70:
                return "Good"
            elif self.quality_score >= 50:
                return "Fair"
            else:
                return "Poor"
        return "Not rated"

    @property
    def source_display(self):
        """Human-readable source name."""
        return dict(self.SOURCE_CHOICES).get(self.source, self.source)

    def _calculate_quality_score(self):
        """
        Calculate sleep quality score (0-100) based on:
        - Sleep efficiency (40% weight)
        - Deep sleep percentage (25% weight) - target 15-20%
        - REM percentage (25% weight) - target 20-25%
        - Interruptions (10% weight)
        """
        score = 0

        # Efficiency component (40 points max)
        if self.sleep_efficiency:
            # 85%+ efficiency is excellent
            efficiency_score = min(100, float(self.sleep_efficiency)) / 100 * 40
            score += efficiency_score

        # Deep sleep component (25 points max)
        if self.deep_sleep_percentage:
            # Target: 15-20% deep sleep
            deep_pct = self.deep_sleep_percentage
            if deep_pct >= 15:
                deep_score = 25
            elif deep_pct >= 10:
                deep_score = 20
            elif deep_pct >= 5:
                deep_score = 15
            else:
                deep_score = 10
            score += deep_score

        # REM component (25 points max)
        if self.rem_percentage:
            # Target: 20-25% REM
            rem_pct = self.rem_percentage
            if rem_pct >= 20:
                rem_score = 25
            elif rem_pct >= 15:
                rem_score = 20
            elif rem_pct >= 10:
                rem_score = 15
            else:
                rem_score = 10
            score += rem_score

        # Interruption penalty (10 points max, lose points for interruptions)
        interruption_score = max(0, 10 - (self.interruption_count * 2))
        score += interruption_score

        return min(100, int(score))


# Sleep factor choices for the factors JSONField
SLEEP_FACTOR_CHOICES = [
    ("caffeine", "Had caffeine"),
    ("alcohol", "Had alcohol"),
    ("late_meal", "Ate late"),
    ("exercise", "Exercised"),
    ("stress", "Stressed/anxious"),
    ("screen_time", "Late screen time"),
    ("nap", "Took a nap"),
    ("travel", "Traveled/jet lag"),
    ("medication", "Took sleep aid"),
    ("illness", "Feeling unwell"),
    ("noise", "Noisy environment"),
    ("temperature", "Too hot/cold"),
]

SLEEP_FACTOR_EMOJIS = {
    "caffeine": "☕",
    "alcohol": "🍷",
    "late_meal": "🍽️",
    "exercise": "🏃",
    "stress": "😰",
    "screen_time": "📱",
    "nap": "😴",
    "travel": "✈️",
    "medication": "💊",
    "illness": "🤒",
    "noise": "🔊",
    "temperature": "🌡️",
}


# =============================================================================
# Body Composition Domain (Part 1)
# Separate from Labs and Vitals — performance-based measurements
# =============================================================================

# Common metric names for UI dropdowns (not enforced at DB level)
BODY_COMPOSITION_METRIC_CHOICES = [
    ("body_fat_pct", "Body Fat %"),
    ("lean_mass", "Lean Mass"),
    ("fat_mass", "Fat Mass"),
    ("skeletal_muscle_mass", "Skeletal Muscle Mass"),
    ("waist", "Waist"),
    ("chest", "Chest"),
    ("hips", "Hips"),
    ("arm_left", "Arm (Left)"),
    ("arm_right", "Arm (Right)"),
    ("thigh_left", "Thigh (Left)"),
    ("thigh_right", "Thigh (Right)"),
    ("neck", "Neck"),
    ("shoulders", "Shoulders"),
    ("calf_left", "Calf (Left)"),
    ("calf_right", "Calf (Right)"),
    ("forearm_left", "Forearm (Left)"),
    ("forearm_right", "Forearm (Right)"),
    ("bone_mass", "Bone Mass"),
    ("body_water_pct", "Body Water %"),
    ("visceral_fat", "Visceral Fat"),
    ("bmr", "Basal Metabolic Rate"),
    ("metabolic_age", "Metabolic Age"),
    ("bmi", "BMI"),
    ("custom", "Custom"),
]

BODY_COMPOSITION_UNIT_CHOICES = [
    ("pct", "%"),
    ("lb", "lb"),
    ("kg", "kg"),
    ("in", "in"),
    ("cm", "cm"),
    ("kcal", "kcal"),
    ("years", "years"),
    ("index", "index"),
    ("", "—"),
]


class BodyCompositionEntry(UserOwnedModel):
    """
    Flexible body composition measurement.

    Supports unlimited metric types without schema changes.
    Separate from Labs (clinical) and Vitals (vital signs).
    This is performance-based data: gym scans, smart scales, tape measurements.
    """

    SOURCE_CHOICES = [
        ("manual", "Manual Entry"),
        ("smart_scale", "Smart Scale"),
        ("dexa_scan", "DEXA Scan"),
        ("bod_pod", "Bod Pod"),
        ("inbody", "InBody Scanner"),
        ("gym_scan", "Gym Body Scan"),
        ("apple_health", "Apple Health"),
        ("other", "Other"),
    ]

    metric_name = models.CharField(
        max_length=50,
        help_text="Type of measurement (e.g. body_fat_pct, lean_mass, waist)",
        db_index=True,
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Measurement value",
    )
    unit = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="Unit of measurement (%, lb, in, cm, etc.)",
    )
    measurement_date = models.DateField(
        help_text="Date the measurement was taken",
    )
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="manual",
        blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-measurement_date", "-created_at"]
        verbose_name = "body composition entry"
        verbose_name_plural = "body composition entries"
        indexes = [
            models.Index(fields=["user", "metric_name", "-measurement_date"]),
        ]

    def __str__(self):
        unit_display = f" {self.unit}" if self.unit else ""
        return f"{self.get_metric_display()}: {self.value}{unit_display} ({self.measurement_date})"

    def get_metric_display(self):
        """Return human-readable metric name."""
        choices_dict = dict(BODY_COMPOSITION_METRIC_CHOICES)
        return choices_dict.get(self.metric_name, self.metric_name)


# =============================================================================
# Health Profile (Part 2)
# Height and Activity Level for mathematical modeling
# =============================================================================

class HealthProfile(models.Model):
    """
    Health-specific profile data used for mathematical modeling.

    Separate from UserPreferences — these are health-domain fields
    used for goal projections and body composition calculations.
    Not medical fields.
    """

    ACTIVITY_LEVEL_CHOICES = [
        ("sedentary", "Sedentary"),
        ("lightly_active", "Lightly Active"),
        ("moderately_active", "Moderately Active"),
        ("very_active", "Very Active"),
        ("highly_active", "Highly Active"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="health_profile",
    )
    height_inches = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Height in inches (used for projections and modeling)",
    )
    activity_level = models.CharField(
        max_length=20,
        choices=ACTIVITY_LEVEL_CHOICES,
        blank=True,
        default="",
        help_text="General activity level (used for caloric modeling)",
    )
    # Weight Goal
    weight_goal = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Target weight goal",
    )
    weight_goal_unit = models.CharField(
        max_length=2,
        choices=[("lb", "Pounds"), ("kg", "Kilograms")],
        default="lb",
        help_text="Unit for weight goal",
    )
    weight_goal_target_date = models.DateField(
        null=True,
        blank=True,
        help_text="Target date to achieve weight goal",
    )

    # Protein target override (default: 0.7g/lb body weight)
    protein_target_g_override = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Custom daily protein target (g). Overrides auto-calculated 0.7g/lb.",
    )
    protein_per_lb_target = models.DecimalField(
        max_digits=4, decimal_places=3, null=True, blank=True,
        help_text="Custom protein multiplier (g per lb body weight). Default: 0.7",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "health profile"
        verbose_name_plural = "health profiles"

    def __str__(self):
        return f"Health Profile: {self.user.email}"

    @property
    def has_weight_goal(self):
        """Check if user has a weight goal set."""
        return self.weight_goal is not None

    def get_weight_progress(self):
        """
        Calculate progress toward weight goal.
        Returns dict with current_weight, goal, progress_percent, remaining, on_track.
        """
        from apps.health.models import WeightEntry

        if not self.has_weight_goal:
            return None

        latest_weight = WeightEntry.objects.filter(
            user=self.user, status='active'
        ).order_by('-recorded_at').first()

        if not latest_weight:
            return {
                'current_weight': None,
                'goal': float(self.weight_goal),
                'unit': self.weight_goal_unit,
                'target_date': self.weight_goal_target_date,
                'progress_percent': 0,
                'remaining': None,
                'on_track': None,
            }

        # Get current weight in the goal's unit
        if self.weight_goal_unit == 'lb':
            current = latest_weight.value_in_lb
        else:
            current = latest_weight.value_in_kg

        goal = float(self.weight_goal)

        # Get starting weight (first entry)
        starting_weight = WeightEntry.objects.filter(
            user=self.user, status='active'
        ).order_by('recorded_at').first()

        if starting_weight:
            if self.weight_goal_unit == 'lb':
                start = starting_weight.value_in_lb
            else:
                start = starting_weight.value_in_kg
        else:
            start = current

        # Calculate progress
        total_change_needed = start - goal
        change_so_far = start - current

        if abs(total_change_needed) < 0.1:
            progress_percent = 100
        elif total_change_needed != 0:
            progress_percent = min(100, max(0, (change_so_far / total_change_needed) * 100))
        else:
            progress_percent = 100 if abs(current - goal) < 0.5 else 0

        remaining = current - goal

        # Determine if on track for target date
        on_track = None
        if self.weight_goal_target_date:
            from django.utils import timezone
            today = timezone.now().date()
            if self.weight_goal_target_date > today:
                days_remaining = (self.weight_goal_target_date - today).days
                if abs(remaining) <= 0.5:
                    on_track = True
                elif days_remaining > 0 and abs(remaining) > 0:
                    on_track = progress_percent >= 50 or remaining < abs(total_change_needed) / 2

        return {
            'current_weight': round(current, 1),
            'goal': goal,
            'unit': self.weight_goal_unit,
            'target_date': self.weight_goal_target_date,
            'progress_percent': round(progress_percent, 1),
            'remaining': round(remaining, 1) if remaining else 0,
            'on_track': on_track,
            'direction': 'lose' if remaining > 0 else 'gain' if remaining < 0 else 'maintain',
        }

    @property
    def height_feet_inches(self):
        """Return height as (feet, inches) tuple."""
        if not self.height_inches:
            return None
        total = float(self.height_inches)
        feet = int(total // 12)
        inches = round(total % 12, 1)
        return (feet, inches)

    @property
    def height_display(self):
        """Return formatted height string like 5'10\"."""
        result = self.height_feet_inches
        if not result:
            return ""
        feet, inches = result
        return f"{feet}'{int(inches)}\""

    @property
    def height_cm(self):
        """Return height in centimeters."""
        if not self.height_inches:
            return None
        return round(float(self.height_inches) * 2.54, 1)

    @staticmethod
    def get_for_user(user):
        """Get or create HealthProfile for a user. Safe to call anywhere."""
        profile, _ = HealthProfile.objects.get_or_create(user=user)
        return profile


# =============================================================================
# Insight Engine Results (Part 4)
# Persisted descriptive insights generated by the Insight Engine
# =============================================================================

class InsightResult(UserOwnedModel):
    """
    A descriptive, non-directive insight generated by the Insight Engine.

    Insights are observational, pattern-based, neutral, and encouraging.
    They MUST NOT contain advice, recommendations, medical interpretation,
    risk assessment, diagnosis, or prescriptions.
    """

    INSIGHT_TYPE_CHOICES = [
        ("trend", "Trend"),
        ("consistency", "Consistency"),
        ("gap", "Gap"),
        ("correlation", "Correlation"),
    ]

    insight_type = models.CharField(
        max_length=20,
        choices=INSIGHT_TYPE_CHOICES,
        db_index=True,
    )
    text = models.TextField(
        help_text="The insight text shown to the user",
    )
    related_domains = models.JSONField(
        default=list,
        help_text='Domains this insight spans, e.g. ["weight", "body_composition"]',
    )
    confidence_score = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        help_text="0.00-1.00 confidence based on data density",
    )
    generated_at = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional structured data about the insight",
    )
    is_dismissed = models.BooleanField(
        default=False,
        help_text="User has dismissed this insight",
    )

    class Meta:
        ordering = ["-generated_at"]
        verbose_name = "insight result"
        verbose_name_plural = "insight results"
        indexes = [
            models.Index(fields=["user", "insight_type", "-generated_at"]),
        ]

    def __str__(self):
        return f"[{self.insight_type}] {self.text[:60]}..."


# =============================================================================
# Transformation Protocol
# =============================================================================

PROTOCOL_TYPE_CHOICES = [
    ("cut", "Cut"),
    ("bulk", "Bulk"),
    ("recomp", "Recomposition"),
    ("maintenance", "Maintenance"),
    ("custom", "Custom"),
]


class TransformationProtocol(UserOwnedModel):
    """
    A body transformation protocol tracking the user's transformation journey.

    Links to LifeGoal for goal engine integration and provides
    protocol-level metadata for the transformation dashboard and AI engines.
    """

    name = models.CharField(
        max_length=200,
        help_text="Protocol name (e.g., '12-Week Cut', 'Summer Bulk')",
    )
    protocol_type = models.CharField(
        max_length=20,
        choices=PROTOCOL_TYPE_CHOICES,
        default="custom",
        help_text="Type of transformation protocol",
    )
    start_date = models.DateField(
        help_text="When the protocol starts",
    )
    target_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Target completion date",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this protocol is currently active",
    )

    # ── Goals ────────────────────────────────────────────────────
    goal_weight = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target weight (in user's preferred unit)",
    )
    goal_weight_unit = models.CharField(
        max_length=5,
        choices=[("lb", "Pounds"), ("kg", "Kilograms")],
        default="lb",
    )
    goal_body_fat = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target body fat percentage",
    )

    # ── Integration ──────────────────────────────────────────────
    life_goal = models.ForeignKey(
        "purpose.LifeGoal",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transformation_protocols",
        help_text="Linked life goal for goal engine tracking",
    )

    notes = models.TextField(blank=True, help_text="Protocol notes")

    # ── Lifecycle ────────────────────────────────────────────────
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the protocol was completed",
    )

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "transformation protocol"
        verbose_name_plural = "transformation protocols"
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["user", "-start_date"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_protocol_type_display()})"

    @property
    def is_complete(self):
        return self.completed_at is not None

    @property
    def duration_days(self):
        """Total planned duration in days."""
        if self.target_end_date:
            return (self.target_end_date - self.start_date).days
        return None

    @property
    def days_remaining(self):
        """Days remaining until target end date."""
        if not self.target_end_date:
            return None
        from apps.core.time.system_clock import get_current_time
        remaining = (self.target_end_date - get_current_time().date()).days
        return max(0, remaining)

    @property
    def progress_percent(self):
        """Progress as percentage of total duration."""
        if not self.target_end_date:
            return None
        total = (self.target_end_date - self.start_date).days
        if total <= 0:
            return 100
        from apps.core.time.system_clock import get_current_time
        elapsed = (get_current_time().date() - self.start_date).days
        return min(100, round(elapsed / total * 100))


# =============================================================================
# Workout Planning Models
# =============================================================================

DAY_OF_WEEK_CHOICES = [
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
    (6, "Sunday"),
]


class WorkoutPlan(UserOwnedModel):
    """
    A structured workout plan grouping multiple templates into a split.

    Links templates into a named program (e.g., '2-Group Strength Split')
    and optionally ties to a TransformationProtocol.
    """

    name = models.CharField(
        max_length=200,
        help_text="Plan name (e.g., '2-Group Strength Split')",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this plan is currently active",
    )
    days_per_week = models.PositiveIntegerField(
        default=4,
        help_text="Target training days per week",
    )
    goal = models.CharField(
        max_length=100,
        blank=True,
        help_text="Primary goal (e.g., 'fat loss', 'muscle gain')",
    )
    transformation_protocol = models.ForeignKey(
        "TransformationProtocol",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workout_plans",
        help_text="Linked transformation protocol",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "workout plan"
        verbose_name_plural = "workout plans"
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return self.name

    @property
    def template_count(self):
        """Number of unique templates in schedule."""
        return self.schedule_entries.values("template").distinct().count()

    @property
    def scheduled_days(self):
        """List of scheduled day names."""
        days = self.schedule_entries.order_by("day_of_week").values_list(
            "day_of_week", flat=True
        )
        day_names = dict(DAY_OF_WEEK_CHOICES)
        return [day_names[d] for d in days]


class WorkoutSchedule(models.Model):
    """
    Maps a day of the week to a workout template within a plan.

    Defines the recurring weekly rotation (e.g., Mon→Group A, Tue→Group B).
    """

    plan = models.ForeignKey(
        WorkoutPlan,
        on_delete=models.CASCADE,
        related_name="schedule_entries",
    )
    day_of_week = models.IntegerField(
        choices=DAY_OF_WEEK_CHOICES,
        help_text="0=Monday through 6=Sunday",
    )
    template = models.ForeignKey(
        WorkoutTemplate,
        on_delete=models.CASCADE,
        related_name="schedule_entries",
        help_text="Workout template for this day",
    )
    preferred_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Preferred workout time (e.g., 17:00)",
    )
    is_rest_day = models.BooleanField(
        default=False,
        help_text="Mark as rest day (template ignored if True)",
    )
    grace_period_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Minutes after preferred_time before marking late",
    )

    class Meta:
        ordering = ["day_of_week"]
        unique_together = ["plan", "day_of_week"]
        verbose_name = "workout schedule entry"
        verbose_name_plural = "workout schedule entries"

    def __str__(self):
        day_name = dict(DAY_OF_WEEK_CHOICES).get(self.day_of_week, "?")
        if self.is_rest_day:
            return f"{day_name}: Rest"
        return f"{day_name}: {self.template.name}"

    def applies_to_day(self, day_of_week):
        """Check if this schedule entry applies to a given day (0=Mon, 6=Sun)."""
        return self.day_of_week == day_of_week and not self.is_rest_day


class WorkoutScheduleLog(UserOwnedModel):
    """
    Tracks schedule adherence for a workout obligation.

    Represents the OUTCOME of a scheduled workout slot:
    - completed / completed_late must link to a WorkoutSession
    - skipped must NOT create a fake WorkoutSession

    This model is separate from WorkoutSession to preserve domain integrity:
    WorkoutSession = actual workout data. WorkoutScheduleLog = schedule outcome.
    """

    STATUS_COMPLETED = "completed"
    STATUS_COMPLETED_LATE = "completed_late"
    STATUS_SKIPPED = "skipped"

    STATUS_CHOICES = [
        (STATUS_COMPLETED, "Completed"),
        (STATUS_COMPLETED_LATE, "Completed Late"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    schedule = models.ForeignKey(
        WorkoutSchedule,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    scheduled_date = models.DateField(
        help_text="The date this schedule entry was for",
    )
    log_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
    )
    session = models.ForeignKey(
        "WorkoutSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedule_logs",
        help_text="The actual workout session (null for skipped)",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the workout was completed",
    )
    is_user_corrected = models.BooleanField(
        default=False,
        help_text="True when user has manually edited a past log",
    )

    class Meta:
        ordering = ["-scheduled_date"]
        unique_together = ["schedule", "scheduled_date"]
        verbose_name = "workout schedule log"
        verbose_name_plural = "workout schedule logs"

    def __str__(self):
        return f"{self.schedule} on {self.scheduled_date}: {self.log_status}"


# =============================================================================
# Nutrition Upgrade: Audit, Templates, Overrides, Label Evidence
# =============================================================================


class NutritionEntryAudit(models.Model):
    """
    Audit trail for changes to FoodEntry records.

    Tracks every meaningful change: quantity updates, nutrient overrides,
    source changes, copy actions, and template applications.
    """

    CHANGE_QUANTITY = 'quantity_change'
    CHANGE_OVERRIDE = 'override_nutrients'
    CHANGE_SOURCE = 'source_change'
    CHANGE_COPY = 'copy_action'
    CHANGE_TEMPLATE = 'template_apply'
    CHANGE_EDIT = 'edit'
    CHANGE_CREATE = 'create'
    CHANGE_TYPE_CHOICES = [
        (CHANGE_QUANTITY, 'Quantity Changed'),
        (CHANGE_OVERRIDE, 'Nutrients Overridden'),
        (CHANGE_SOURCE, 'Source Changed'),
        (CHANGE_COPY, 'Copied from Another Entry'),
        (CHANGE_TEMPLATE, 'Template Applied'),
        (CHANGE_EDIT, 'General Edit'),
        (CHANGE_CREATE, 'Entry Created'),
    ]

    entry = models.ForeignKey(
        FoodEntry,
        on_delete=models.CASCADE,
        related_name='audit_trail',
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='nutrition_audit_actions',
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    change_type = models.CharField(max_length=30, choices=CHANGE_TYPE_CHOICES)
    before_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="State before the change",
    )
    after_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="State after the change",
    )
    notes = models.TextField(blank=True, help_text="Optional description of the change")

    class Meta:
        ordering = ['-changed_at']
        verbose_name = "nutrition entry audit"
        verbose_name_plural = "nutrition entry audits"
        indexes = [
            models.Index(fields=['entry', '-changed_at']),
        ]

    def __str__(self):
        return f"Audit: {self.get_change_type_display()} on {self.entry} at {self.changed_at}"


class MealTemplate(UserOwnedModel):
    """
    Named meal template (recipe) — a group of food items the user logs together.

    Examples: "Turkey Sandwich", "Morning Smoothie", "Post-Workout Shake".
    Users can apply a template to log all items in one action.
    """

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    default_meal_type = models.CharField(
        max_length=20,
        choices=FoodEntry.MEAL_CHOICES,
        default=FoodEntry.MEAL_SNACK,
    )
    is_favorite = models.BooleanField(default=False)
    use_count = models.PositiveIntegerField(
        default=0,
        help_text="How many times this template has been applied",
    )

    class Meta:
        ordering = ['-is_favorite', '-use_count', 'name']
        verbose_name = "meal template"
        verbose_name_plural = "meal templates"

    def __str__(self):
        return self.name

    @property
    def total_calories(self):
        """Sum of all template item calories."""
        total = 0
        for item in self.items.all():
            snap = item.snapshot_nutrients or {}
            cal = snap.get('calories', 0) or 0
            total += float(cal) * float(item.quantity)
        return round(total, 1)

    @property
    def item_count(self):
        """Number of items in this template."""
        return self.items.count()


class MealTemplateItem(models.Model):
    """
    Individual food item within a meal template.

    Stores a snapshot of per-serving nutrients so templates remain accurate
    even if the source FoodItem changes later.
    """

    template = models.ForeignKey(
        MealTemplate,
        on_delete=models.CASCADE,
        related_name='items',
    )
    food_item = models.ForeignKey(
        FoodItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='template_items',
    )
    custom_food = models.ForeignKey(
        CustomFood,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='template_items',
    )

    # Snapshot for display even if FK is deleted
    food_name = models.CharField(max_length=300)
    food_brand = models.CharField(max_length=200, blank=True)

    # Quantity and serving
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    serving_size = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    serving_unit = models.CharField(max_length=50, default='serving')

    # Per-serving nutrients snapshot at time of template creation
    snapshot_nutrients = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-serving nutrient values when this item was added to the template",
    )

    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = "meal template item"
        verbose_name_plural = "meal template items"

    def __str__(self):
        return f"{self.food_name} (x{self.quantity}) in {self.template.name}"


class FoodItemOverride(UserOwnedModel):
    """
    Per-user nutrient correction for a FoodItem.

    When a user scans a barcode and the API returns wrong data, they can
    override the nutrients. This override applies only to that user's future
    logs of the same FoodItem, without polluting the global database.
    """

    food_item = models.ForeignKey(
        FoodItem,
        on_delete=models.CASCADE,
        related_name='user_overrides',
    )
    overridden_nutrients = models.JSONField(
        help_text=(
            "Per-serving nutrient values corrected by the user. "
            "Format: {calories: 10, protein_g: 0, carbohydrates_g: 4, ...}"
        ),
    )
    override_reason = models.TextField(
        blank=True,
        help_text="Why the user corrected these values (e.g., 'Label says 10 cal not 3')",
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "food item override"
        verbose_name_plural = "food item overrides"
        unique_together = ['user', 'food_item']

    def __str__(self):
        return f"Override for {self.food_item.name} by user {self.user_id}"


class NutritionLabelEvidence(models.Model):
    """
    Photo evidence of a nutrition label uploaded by a user.

    Attached to a FoodItem to support user overrides with visual proof.
    """

    food_item = models.ForeignKey(
        FoodItem,
        on_delete=models.CASCADE,
        related_name='label_evidence',
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='uploaded_label_evidence',
    )
    image = models.ImageField(upload_to='nutrition_labels/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = "nutrition label evidence"
        verbose_name_plural = "nutrition label evidence"

    def __str__(self):
        return f"Label photo for {self.food_item.name} by user {self.uploaded_by_id}"


# =============================================================================
# Mobility & Gait Metrics (from Apple HealthKit)
# =============================================================================


class MobilityEntry(UserOwnedModel):
    """
    Mobility and gait metrics from Apple Watch / HealthKit.

    Tracks walking quality indicators that are strong predictors of
    overall health decline, injury risk, and neurological conditions.

    Metrics tracked:
    - Walking asymmetry: Left/right step imbalance (%) — injury/gait issues
    - Walking steadiness: Apple's fall risk classification
    - Walking speed: Average speed during walks (mph)
    - Walking step length: Average step length (inches)
    - Walking double support: Time both feet on ground (%) — balance indicator
    - Stair ascent speed: Flights per minute going up
    - Stair descent speed: Flights per minute going down
    - Six minute walk distance: Estimated distance in 6-min walk test (meters)
    """

    SOURCE_CHOICES = [
        ("manual", "Manual Entry"),
        ("apple_health", "Apple Health"),
        ("imported", "Imported"),
    ]

    metric_date = models.DateField(
        help_text="Date these mobility metrics were recorded",
    )

    # Walking asymmetry (percentage, 0-100)
    walking_asymmetry = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Walking asymmetry percentage (left/right imbalance, 0-50%)",
    )

    # Walking steadiness classification
    STEADINESS_CHOICES = [
        ("ok", "OK"),
        ("low", "Low"),
        ("very_low", "Very Low"),
    ]
    walking_steadiness = models.CharField(
        max_length=10,
        choices=STEADINESS_CHOICES,
        blank=True,
        help_text="Apple Watch walking steadiness classification",
    )
    walking_steadiness_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Walking steadiness numeric score (0-100, if available)",
    )

    # Walking speed (mph)
    walking_speed = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average walking speed in mph",
    )

    # Step length (inches)
    step_length = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average step length in inches",
    )

    # Double support time (percentage of walking cycle)
    double_support_time = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Double support time as percentage of walking cycle",
    )

    # Stair metrics (flights per minute)
    stair_ascent_speed = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Stair ascent speed (flights per minute)",
    )
    stair_descent_speed = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Stair descent speed (flights per minute)",
    )

    # Six minute walk test estimate
    six_min_walk_distance = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated six-minute walk distance in meters",
    )

    # Sync fields
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="apple_health",
    )
    sync_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="External ID from synced source to prevent duplicates",
    )

    class Meta:
        ordering = ["-metric_date"]
        verbose_name = "mobility entry"
        verbose_name_plural = "mobility entries"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "metric_date", "source"],
                name="unique_mobility_per_day_per_source",
            )
        ]
        indexes = [
            models.Index(fields=["user", "metric_date"]),
        ]

    def __str__(self):
        parts = []
        if self.walking_speed:
            parts.append(f"{self.walking_speed} mph")
        if self.walking_asymmetry:
            parts.append(f"{self.walking_asymmetry}% asymmetry")
        if self.walking_steadiness:
            parts.append(f"steadiness: {self.walking_steadiness}")
        detail = ", ".join(parts) if parts else "no data"
        return f"Mobility ({detail}) on {self.metric_date}"


class HeartRateEventEntry(UserOwnedModel):
    """
    Heart rate events / notifications from Apple Watch.

    Captures clinically significant cardiac events:
    - High heart rate alerts (resting HR exceeds threshold)
    - Low heart rate alerts (resting HR drops below threshold)
    - Irregular rhythm notifications (possible AFib detection)

    These are event-based (not daily aggregates) — each record
    represents a single alert/notification from the device.
    """

    SOURCE_CHOICES = [
        ("manual", "Manual Entry"),
        ("apple_health", "Apple Health"),
        ("imported", "Imported"),
    ]

    EVENT_TYPE_CHOICES = [
        ("high_hr", "High Heart Rate"),
        ("low_hr", "Low Heart Rate"),
        ("irregular_rhythm", "Irregular Rhythm (AFib)"),
    ]

    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES,
        help_text="Type of heart rate event",
    )
    heart_rate = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Heart rate at time of event (BPM)",
    )
    threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Threshold that was crossed (BPM, for high/low HR events)",
    )
    recorded_at = models.DateTimeField(
        help_text="When the event was detected",
    )
    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duration of the event in seconds (if applicable)",
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional context about the event",
    )

    # Sync fields
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="apple_health",
    )
    sync_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="External ID from synced source to prevent duplicates",
    )

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "heart rate event"
        verbose_name_plural = "heart rate events"
        indexes = [
            models.Index(fields=["user", "event_type"]),
            models.Index(fields=["user", "recorded_at"]),
        ]

    def __str__(self):
        hr_str = f" ({self.heart_rate} BPM)" if self.heart_rate else ""
        return f"{self.get_event_type_display()}{hr_str} on {self.recorded_at}"


class AudioExposureEntry(UserOwnedModel):
    """
    Audio exposure metrics from Apple Watch / HealthKit.

    Tracks environmental and headphone audio levels for hearing health.
    Long-term exposure above 80 dB can cause gradual hearing loss.
    CoS can detect patterns of sustained high exposure and alert the user.

    Metrics tracked:
    - Headphone audio level (dB) — from AirPods / connected headphones
    - Environmental audio level (dB) — ambient noise from Apple Watch mic
    """

    SOURCE_CHOICES = [
        ("manual", "Manual Entry"),
        ("apple_health", "Apple Health"),
        ("imported", "Imported"),
    ]

    metric_date = models.DateField(
        help_text="Date these audio metrics were recorded",
    )

    # Headphone audio exposure (daily average in dB)
    headphone_level_db = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average headphone audio level in decibels (dB)",
    )
    headphone_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total headphone listening time in minutes",
    )

    # Environmental audio exposure (daily average in dB)
    environmental_level_db = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average environmental sound level in decibels (dB)",
    )

    # Sync fields
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="apple_health",
    )
    sync_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="External ID from synced source to prevent duplicates",
    )

    class Meta:
        ordering = ["-metric_date"]
        verbose_name = "audio exposure entry"
        verbose_name_plural = "audio exposure entries"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "metric_date", "source"],
                name="unique_audio_per_day_per_source",
            )
        ]

    def __str__(self):
        parts = []
        if self.headphone_level_db:
            parts.append(f"headphone: {self.headphone_level_db} dB")
        if self.environmental_level_db:
            parts.append(f"env: {self.environmental_level_db} dB")
        detail = ", ".join(parts) if parts else "no data"
        return f"Audio ({detail}) on {self.metric_date}"

    @property
    def headphone_risk_level(self):
        """
        Assess hearing risk from headphone exposure.
        WHO guidelines: 80 dB for 40 hrs/week max.
        """
        if not self.headphone_level_db:
            return None
        level = float(self.headphone_level_db)
        if level < 70:
            return "safe"
        elif level < 80:
            return "moderate"
        elif level < 90:
            return "elevated"
        else:
            return "high"


class DietaryNutrientEntry(UserOwnedModel):
    """
    Dietary nutrient data from Apple HealthKit.

    Captures macronutrient and micronutrient data that flows through
    Apple Health from food-logging apps (MyFitnessPal, Cronometer,
    Lose It!, etc.). This is separate from WLJ's own FoodEntry/nutrition
    system — it captures what other apps report to Apple Health.

    CoS can use this for cross-referencing with energy levels, sleep
    quality, glucose patterns, and exercise performance.
    """

    SOURCE_CHOICES = [
        ("manual", "Manual Entry"),
        ("apple_health", "Apple Health"),
        ("imported", "Imported"),
    ]

    metric_date = models.DateField(
        help_text="Date these dietary metrics were recorded",
    )

    # Macronutrients (grams)
    calories = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total dietary energy in kilocalories",
    )
    protein_g = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total protein in grams",
    )
    carbohydrates_g = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total carbohydrates in grams",
    )
    fat_g = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total fat in grams",
    )
    fiber_g = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total dietary fiber in grams",
    )
    sugar_g = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total sugar in grams",
    )

    # Key micronutrients
    sodium_mg = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Sodium in milligrams",
    )
    cholesterol_mg = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Dietary cholesterol in milligrams",
    )
    saturated_fat_g = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Saturated fat in grams",
    )
    potassium_mg = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Potassium in milligrams",
    )
    calcium_mg = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Calcium in milligrams",
    )
    iron_mg = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Iron in milligrams",
    )
    vitamin_d_mcg = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Vitamin D in micrograms",
    )

    # Sync fields
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="apple_health",
    )
    sync_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="External ID from synced source to prevent duplicates",
    )

    class Meta:
        ordering = ["-metric_date"]
        verbose_name = "dietary nutrient entry"
        verbose_name_plural = "dietary nutrient entries"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "metric_date", "source"],
                name="unique_dietary_nutrients_per_day_per_source",
            )
        ]

    def __str__(self):
        parts = []
        if self.calories:
            parts.append(f"{self.calories} cal")
        if self.protein_g:
            parts.append(f"{self.protein_g}g protein")
        detail = ", ".join(parts) if parts else "no data"
        return f"Dietary ({detail}) on {self.metric_date}"


# =============================================================================
# Health Intelligence Engine — Daily Summary & Recovery
# =============================================================================


class DailyHealthSummary(UserOwnedModel):
    """
    Pre-computed daily health rollup — the keystone for fast dashboards
    and multi-week CoS intelligence.

    One row per user per day. Aggregated from 15+ source tables via the
    DailyHealthSummaryBuilder service. Recomputed nightly and on data changes.

    Fields are nullable because not every signal is available every day.
    The health_score and recovery_score require baseline_ready=True (14+ days).
    """

    summary_date = models.DateField(
        db_index=True,
        help_text="Date this summary covers",
    )
    baseline_ready = models.BooleanField(
        default=False,
        help_text="True if user has >=14 days of core health signals",
    )

    # --- Scores (require baseline) ---
    health_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Composite health score 0-100 (null if baseline not ready)",
    )
    health_score_drivers = models.JSONField(
        default=dict,
        blank=True,
        help_text="Explainable breakdown: strongest_positive, primary_risk, etc.",
    )
    recovery_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Recovery readiness score 0-100",
    )
    recovery_drivers = models.JSONField(
        default=dict,
        blank=True,
        help_text="Recovery score driver breakdown",
    )

    # --- Sleep (previous night) ---
    sleep_hours = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text="Total sleep duration in hours",
    )
    sleep_quality_score = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Sleep quality 0-100 derived from stages + efficiency",
    )
    sleep_debt_minutes = models.IntegerField(
        null=True, blank=True,
        help_text="Minutes of sleep debt (target - actual, positive = deficit)",
    )
    deep_sleep_minutes = models.PositiveIntegerField(null=True, blank=True)
    rem_sleep_minutes = models.PositiveIntegerField(null=True, blank=True)
    sleep_efficiency_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
    )

    # --- Vitals ---
    resting_hr = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Resting heart rate (bpm)",
    )
    hrv = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Heart rate variability (ms)",
    )
    blood_pressure_systolic = models.PositiveSmallIntegerField(
        null=True, blank=True,
    )
    blood_pressure_diastolic = models.PositiveSmallIntegerField(
        null=True, blank=True,
    )
    spo2_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
    )

    # --- Activity ---
    steps = models.PositiveIntegerField(null=True, blank=True)
    active_minutes = models.PositiveIntegerField(null=True, blank=True)
    calories_burned = models.PositiveIntegerField(
        null=True, blank=True, help_text="Active calories burned",
    )
    stand_hours = models.PositiveSmallIntegerField(null=True, blank=True)
    flights_climbed = models.PositiveSmallIntegerField(null=True, blank=True)

    # --- Workouts ---
    workout_count = models.PositiveSmallIntegerField(default=0)
    workout_minutes = models.PositiveIntegerField(null=True, blank=True)
    training_load = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Volume-based training load score for the day",
    )

    # --- Weight & Body Composition ---
    weight = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Latest weight reading in lbs",
    )
    body_fat_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
    )
    skeletal_muscle_mass = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Skeletal muscle mass in lbs (when available)",
    )
    lean_mass = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )

    # --- Body Composition Intelligence (computed by BodyCompositionIntelligence) ---
    fat_mass = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Computed: weight * (body_fat_pct / 100) in lbs",
    )
    fat_loss_quality_label = models.CharField(
        max_length=20, blank=True, default="",
        help_text="EXCELLENT/GOOD/MIXED/MUSCLE_LOSS_RISK/INSUFFICIENT_DATA",
    )
    fat_loss_ratio_14d = models.DecimalField(
        max_digits=4, decimal_places=3, null=True, blank=True,
        help_text="abs(fat_mass_delta) / abs(weight_delta) over 14d window",
    )
    recomposition_flag_14d = models.BooleanField(
        null=True, blank=True,
        help_text="True if fat down + muscle up + weight flat over 14d",
    )
    plateau_status = models.CharField(
        max_length=20, blank=True, default="",
        help_text="TRUE_PLATEAU/RECOMP/WATER/INSUFFICIENT_DATA",
    )
    fat_loss_speed_pct_per_week = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Pct of body weight lost per week over 14d window",
    )
    fat_loss_speed_label = models.CharField(
        max_length=10, blank=True, default="",
        help_text="SAFE/FAST/TOO_FAST/SLOW/GAINING",
    )
    muscle_loss_risk_score = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Composite 0-100 risk score for muscle loss",
    )
    muscle_loss_risk_level = models.CharField(
        max_length=10, blank=True, default="",
        help_text="LOW/MED/HIGH",
    )
    body_comp_drivers = models.JSONField(
        default=dict, blank=True,
        help_text="Explainable drivers for body comp intelligence",
    )

    # --- Plateau Early Warning (computed by BodyCompositionIntelligence) ---
    plateau_risk_score = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Predictive plateau risk 0-100",
    )
    plateau_prediction_window_days = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Estimated days until plateau onset",
    )
    plateau_risk_label = models.CharField(
        max_length=10, blank=True, default="",
        help_text="LOW / RISING / HIGH",
    )

    # --- Fat Loss Phase Detection (computed by BodyCompositionIntelligence) ---
    fat_loss_phase = models.CharField(
        max_length=25, blank=True, default="",
        help_text="RAPID_INITIAL_LOSS / STABLE_FAT_LOSS / RECOMPOSITION / PLATEAU / REBOUND_RISK",
    )
    phase_confidence = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Confidence 0-100 in phase classification",
    )
    phase_start_date = models.DateField(
        null=True, blank=True,
        help_text="Estimated date current phase began",
    )

    # --- Muscle Preservation Status (alias for CoS readability) ---
    muscle_preservation_status = models.CharField(
        max_length=20, blank=True, default="",
        help_text="HIGH_QUALITY / MODERATE_QUALITY / MUSCLE_RISK / INSUFFICIENT_DATA",
    )

    # --- Glucose ---
    glucose_avg = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Average glucose mg/dL for the day",
    )
    glucose_min = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    glucose_max = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    glucose_variability = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Glucose coefficient of variation (%)",
    )
    time_in_range_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="% of readings in 70-180 mg/dL range",
    )

    # --- Nutrition ---
    calories_consumed = models.PositiveIntegerField(null=True, blank=True)
    protein_g = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
    )
    carbs_g = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
    )
    fat_g = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
    )
    fiber_g = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
    )
    water_oz = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
    )
    nutrition_logged = models.BooleanField(
        default=False,
        help_text="True if at least one food entry was logged",
    )
    meals_logged = models.PositiveSmallIntegerField(default=0)

    # --- Protein Intelligence ---
    protein_target_g = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Daily protein target (LBM×1.0/1.1 or fallback 0.7g/lb)",
    )
    protein_consumed_g = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
        help_text="Total protein consumed today (mirrors protein_g for clarity)",
    )
    protein_ratio = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text="protein_consumed / protein_target (1.0 = 100% of target)",
    )
    protein_score = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Protein adequacy score 0-100",
    )
    protein_per_lb = models.DecimalField(
        max_digits=4, decimal_places=3, null=True, blank=True,
        help_text="Grams of protein per pound of body weight",
    )
    protein_method = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Target method: 'lean_body_mass', 'body_weight', or 'override'",
    )

    # --- Medication ---
    medication_adherence_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Medication adherence rate 0-100 for the day",
    )
    doses_taken = models.PositiveSmallIntegerField(default=0)
    doses_expected = models.PositiveSmallIntegerField(default=0)

    # --- Fasting ---
    fasting_hours = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Total fasting hours during this day",
    )

    # --- Caffeine & Mindfulness ---
    caffeine_mg = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
    )
    mindful_minutes = models.PositiveIntegerField(null=True, blank=True)

    # --- Meta ---
    data_completeness_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="% of trackable domains with data today",
    )
    signals_present = models.JSONField(
        default=list, blank=True,
        help_text="List of domain names that have data for this day",
    )
    last_computed = models.DateTimeField(
        auto_now=True,
        help_text="When this summary was last recomputed",
    )

    class Meta:
        ordering = ["-summary_date"]
        verbose_name = "daily health summary"
        verbose_name_plural = "daily health summaries"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "summary_date"],
                name="unique_health_summary_per_day",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-summary_date"]),
            models.Index(fields=["user", "summary_date"]),
            models.Index(fields=["user", "baseline_ready", "-summary_date"]),
        ]

    def __str__(self):
        score = f"HS:{self.health_score}" if self.health_score else "no score"
        return f"Health Summary {self.user.email} {self.summary_date} ({score})"
