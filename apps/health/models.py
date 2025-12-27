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
