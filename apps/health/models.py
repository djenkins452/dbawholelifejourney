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

from apps.core.models import UserOwnedModel
from apps.core.utils import get_user_today


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

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "heart rate entry"
        verbose_name_plural = "heart rate entries"

    def __str__(self):
        return f"{self.bpm} BPM ({self.context}) on {self.recorded_at.date()}"


class GlucoseEntry(UserOwnedModel):
    """
    Blood glucose tracking entry.
    
    Supports mg/dL and mmol/L units.
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
    ]

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

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "glucose entry"
        verbose_name_plural = "glucose entries"

    def __str__(self):
        return f"{self.value} {self.unit} ({self.context}) on {self.recorded_at.date()}"

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
    ]

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    muscle_group = models.CharField(
        max_length=50,
        blank=True,
        help_text="Primary muscle group (for resistance exercises)",
    )
    description = models.TextField(blank=True)
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


class WorkoutSession(UserOwnedModel):
    """
    A single workout session.

    Groups multiple exercises performed in one workout.
    """

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

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "workout session"
        verbose_name_plural = "workout sessions"

    def __str__(self):
        if self.name:
            return f"{self.name} - {self.date}"
        return f"Workout on {self.date}"

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
        """Total volume (weight x reps) for resistance exercises."""
        total = 0
        for workout_ex in self.workout_exercises.filter(exercise__category="resistance"):
            for s in workout_ex.sets.all():
                if s.weight and s.reps:
                    total += float(s.weight) * s.reps
        return total


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
        weight_str = f"{self.weight}lbs" if self.weight else "bodyweight"
        return f"Set {self.set_number}: {weight_str} x {self.reps}"

    @property
    def volume(self):
        """Calculate volume (weight x reps) for this set."""
        if self.weight and self.reps:
            return float(self.weight) * self.reps
        return 0


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


class PersonalRecord(UserOwnedModel):
    """
    Track personal records for exercises.

    Records the best performance for each exercise.
    """

    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.CASCADE,
        related_name="personal_records",
    )
    weight = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        help_text="Weight in pounds",
    )
    reps = models.PositiveIntegerField()
    achieved_date = models.DateField()
    workout_session = models.ForeignKey(
        WorkoutSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personal_records",
    )

    class Meta:
        ordering = ["-achieved_date"]
        verbose_name = "personal record"
        verbose_name_plural = "personal records"

    def __str__(self):
        return f"PR: {self.exercise.name} - {self.weight}lbs x {self.reps}"

    @property
    def estimated_1rm(self):
        """Estimate 1 rep max using Brzycki formula."""
        if self.reps == 1:
            return float(self.weight)
        return float(self.weight) * (36 / (37 - self.reps))


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


# =============================================================================
# Medicine Tracking Models
# =============================================================================


class Medicine(UserOwnedModel):
    """
    A medicine/medication the user takes regularly or as-needed.

    Tracks the master list of medicines with dosage and scheduling info.
    Supports both scheduled medicines and PRN (as-needed) medicines.
    """

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

    # Medicine status (separate from soft-delete status)
    medicine_status = models.CharField(
        max_length=20,
        choices=MEDICINE_STATUS_CHOICES,
        default=STATUS_ACTIVE,
        help_text="Current status of this medicine regimen",
    )
    paused_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this medicine was paused",
    )
    paused_reason = models.CharField(
        max_length=500,
        blank=True,
        help_text="Reason for pausing this medicine",
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
        verbose_name = "medicine"
        verbose_name_plural = "medicines"

    def __str__(self):
        return f"{self.name} ({self.dose})"

    @property
    def is_active_medicine(self):
        """Check if this medicine is actively being taken."""
        return self.medicine_status == self.STATUS_ACTIVE

    @property
    def is_paused(self):
        """Check if this medicine is temporarily paused."""
        return self.medicine_status == self.STATUS_PAUSED

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
        """Pause this medicine temporarily."""
        self.medicine_status = self.STATUS_PAUSED
        self.paused_at = timezone.now()
        self.paused_reason = reason
        self.save(update_fields=["medicine_status", "paused_at", "paused_reason", "updated_at"])

    def resume(self):
        """Resume a paused medicine."""
        self.medicine_status = self.STATUS_ACTIVE
        self.paused_at = None
        self.paused_reason = ""
        self.save(update_fields=["medicine_status", "paused_at", "paused_reason", "updated_at"])

    def complete(self):
        """Mark this medicine course as completed."""
        self.medicine_status = self.STATUS_COMPLETED
        user_today = get_user_today(self.user) if self.user_id else timezone.now().date()
        self.end_date = user_today
        self.save(update_fields=["medicine_status", "end_date", "updated_at"])

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


class MedicineSchedule(models.Model):
    """
    Scheduled times for taking a medicine.

    A medicine can have multiple scheduled times per day.
    For example, "twice daily" might be 8 AM and 8 PM.
    """

    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.CASCADE,
        related_name="schedules",
    )

    scheduled_time = models.TimeField(
        help_text="Time of day to take this dose",
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
        verbose_name = "medicine schedule"
        verbose_name_plural = "medicine schedules"

    def __str__(self):
        time_str = self.scheduled_time.strftime("%I:%M %p")
        if self.label:
            return f"{self.medicine.name} at {time_str} ({self.label})"
        return f"{self.medicine.name} at {time_str}"

    @property
    def days_list(self):
        """Return days as a list of integers."""
        if not self.days_of_week:
            return []
        return [int(d) for d in self.days_of_week.split(",") if d.strip()]

    def applies_to_day(self, day_of_week):
        """Check if this schedule applies to a given day (0=Mon, 6=Sun)."""
        return day_of_week in self.days_list


class MedicineLog(UserOwnedModel):
    """
    Log of when medicines were actually taken.

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

    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.CASCADE,
        related_name="logs",
    )

    schedule = models.ForeignKey(
        MedicineSchedule,
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

    class Meta:
        ordering = ["-scheduled_date", "-scheduled_time"]
        verbose_name = "medicine log"
        verbose_name_plural = "medicine logs"

    def __str__(self):
        status = self.get_log_status_display()
        return f"{self.medicine.name} on {self.scheduled_date} - {status}"

    @property
    def was_on_time(self):
        """Check if the dose was taken within the grace period."""
        if self.log_status != self.STATUS_TAKEN or not self.taken_at:
            return False
        if not self.scheduled_time:
            return True  # PRN doses are always "on time"

        from datetime import datetime, timedelta
        scheduled_dt = datetime.combine(self.scheduled_date, self.scheduled_time)
        grace_minutes = self.medicine.grace_period_minutes
        latest_ok = scheduled_dt + timedelta(minutes=grace_minutes)

        # Compare without timezone for simplicity
        taken_naive = self.taken_at.replace(tzinfo=None) if self.taken_at.tzinfo else self.taken_at
        return taken_naive <= latest_ok

    @property
    def minutes_late(self):
        """Calculate how many minutes late the dose was taken."""
        if self.log_status not in [self.STATUS_TAKEN, self.STATUS_LATE] or not self.taken_at:
            return None
        if not self.scheduled_time:
            return 0  # PRN doses aren't late

        from datetime import datetime
        scheduled_dt = datetime.combine(self.scheduled_date, self.scheduled_time)
        taken_naive = self.taken_at.replace(tzinfo=None) if self.taken_at.tzinfo else self.taken_at

        diff = taken_naive - scheduled_dt
        return max(0, int(diff.total_seconds() / 60))

    def mark_taken(self, taken_at=None):
        """Mark this dose as taken."""
        self.taken_at = taken_at or timezone.now()

        # Check if it was late
        if self.scheduled_time:
            from datetime import datetime, timedelta
            scheduled_dt = datetime.combine(self.scheduled_date, self.scheduled_time)
            grace_minutes = self.medicine.grace_period_minutes
            latest_ok = scheduled_dt + timedelta(minutes=grace_minutes)

            taken_naive = self.taken_at.replace(tzinfo=None) if self.taken_at.tzinfo else self.taken_at
            if taken_naive > latest_ok:
                self.log_status = self.STATUS_LATE
            else:
                self.log_status = self.STATUS_TAKEN
        else:
            self.log_status = self.STATUS_TAKEN

        self.save(update_fields=["taken_at", "log_status", "updated_at"])

    def mark_skipped(self, reason=""):
        """Mark this dose as intentionally skipped."""
        self.log_status = self.STATUS_SKIPPED
        if reason:
            self.notes = reason
        self.save(update_fields=["log_status", "notes", "updated_at"])

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
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, 'Manual Entry'),
        (SOURCE_USDA, 'USDA Database'),
        (SOURCE_BARCODE, 'Barcode Scan'),
        (SOURCE_AI, 'AI Recognition'),
    ]

    # Basic info
    name = models.CharField(max_length=300)
    brand = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    barcode = models.CharField(max_length=50, blank=True, db_index=True)

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

    class Meta:
        ordering = ['name']
        verbose_name = "food item"
        verbose_name_plural = "food items"
        indexes = [
            models.Index(fields=['barcode']),
            models.Index(fields=['name']),
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
        """Calculate total nutrition based on quantity and serving."""
        source = self.food_item or self.custom_food
        if not source:
            return

        multiplier = self.quantity
        self.total_calories = source.calories * multiplier
        self.total_protein_g = source.protein_g * multiplier
        self.total_carbohydrates_g = source.carbohydrates_g * multiplier
        self.total_fiber_g = source.fiber_g * multiplier
        self.total_sugar_g = source.sugar_g * multiplier
        self.total_fat_g = source.fat_g * multiplier
        self.total_saturated_fat_g = source.saturated_fat_g * multiplier

        # Calculate optional micronutrients if available
        if hasattr(source, 'sodium_mg') and source.sodium_mg is not None:
            self.total_sodium_mg = source.sodium_mg * multiplier
        if hasattr(source, 'cholesterol_mg') and source.cholesterol_mg is not None:
            self.total_cholesterol_mg = source.cholesterol_mg * multiplier
        if hasattr(source, 'potassium_mg') and source.potassium_mg is not None:
            self.total_potassium_mg = source.potassium_mg * multiplier

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
