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
