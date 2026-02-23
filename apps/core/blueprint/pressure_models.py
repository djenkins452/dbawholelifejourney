"""
Phase 4 — Pressure Modeling: PressureSnapshot & PressureWeightConfig.

Deterministic forward-looking pressure models for the Composite Pressure
Index (CPI). Stores periodic snapshots of per-user pressure state and
the active weight configuration for the composite formula.

Models:
    - PressureSnapshot: Immutable point-in-time pressure record
    - PressureWeightConfig: Active weight profile (singleton-ish)

Project: Whole Life Journey
Path: apps/core/blueprint/pressure_models.py
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class PressureSnapshot(models.Model):
    """
    Immutable point-in-time pressure snapshot.

    Created by update_pressure_snapshot() on every relevant event
    (commitment save/close, calendar change, goal update, Tier1 override)
    and by the daily ISE sweep. Previous snapshots are never overwritten.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pressure_snapshots',
    )

    # Composite index (0–100)
    pressure_index = models.PositiveSmallIntegerField(
        default=0,
        help_text="Composite Pressure Index (0–100)",
    )

    # Component scores (0.0–1.0)
    density_score = models.FloatField(
        default=0.0,
        help_text="Calendar density score (0.0–1.0)",
    )
    compression_score = models.FloatField(
        default=0.0,
        help_text="Workload compression score (0.0–1.0)",
    )
    breach_risk_score = models.FloatField(
        default=0.0,
        help_text="Habit breach probability (0.0–1.0)",
    )
    erosion_score = models.FloatField(
        default=0.0,
        help_text="Goal trajectory erosion score (0.0–1.0)",
    )
    collision_score = models.FloatField(
        default=0.0,
        help_text="Deadline collision score (0.0–1.0)",
    )

    horizon_days = models.PositiveSmallIntegerField(
        default=7,
        help_text="Forecast horizon in days (7, 14, or 30)",
    )

    computed_at = models.DateTimeField(default=timezone.now)

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Baseline variance, debug info, component details",
    )

    class Meta:
        ordering = ['-computed_at']
        indexes = [
            models.Index(fields=['user', '-computed_at']),
        ]
        verbose_name = "Pressure Snapshot"
        verbose_name_plural = "Pressure Snapshots"

    def __str__(self):
        return (
            f"PressureSnapshot user={self.user_id} "
            f"index={self.pressure_index} at {self.computed_at}"
        )

    @classmethod
    def latest_for_user(cls, user):
        """Get the most recent snapshot for a user, or None."""
        return cls.objects.filter(user=user).order_by('-computed_at').first()


class PressureWeightConfig(models.Model):
    """
    Active weight configuration for the Composite Pressure Index.

    Weights must sum to 100. Only one record should have active=True
    at a time. Default weights: 30 / 20 / 20 / 15 / 15.
    """

    density_weight = models.PositiveSmallIntegerField(
        default=30,
        help_text="Weight for calendar density (0–100)",
    )
    compression_weight = models.PositiveSmallIntegerField(
        default=20,
        help_text="Weight for workload compression (0–100)",
    )
    breach_weight = models.PositiveSmallIntegerField(
        default=20,
        help_text="Weight for habit breach risk (0–100)",
    )
    erosion_weight = models.PositiveSmallIntegerField(
        default=15,
        help_text="Weight for goal erosion (0–100)",
    )
    collision_weight = models.PositiveSmallIntegerField(
        default=15,
        help_text="Weight for deadline collision (0–100)",
    )

    active = models.BooleanField(
        default=True,
        help_text="Only one config should be active at a time",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pressure Weight Config"
        verbose_name_plural = "Pressure Weight Configs"

    def __str__(self):
        return (
            f"PressureWeightConfig "
            f"[{self.density_weight}/{self.compression_weight}/"
            f"{self.breach_weight}/{self.erosion_weight}/{self.collision_weight}] "
            f"{'(active)' if self.active else '(inactive)'}"
        )

    def clean(self):
        total = (
            self.density_weight
            + self.compression_weight
            + self.breach_weight
            + self.erosion_weight
            + self.collision_weight
        )
        if total != 100:
            raise ValidationError(
                f"Weights must sum to 100 (current sum: {total})"
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        """
        Get the active weight config, or create the default.

        Returns:
            PressureWeightConfig instance.
        """
        config = cls.objects.filter(active=True).first()
        if config is None:
            config = cls.objects.create(
                density_weight=30,
                compression_weight=20,
                breach_weight=20,
                erosion_weight=15,
                collision_weight=15,
                active=True,
            )
        return config
