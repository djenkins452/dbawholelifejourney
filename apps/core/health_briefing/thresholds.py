"""
HealthBriefing thresholds registry — registry-by-key.

All clinical and operational thresholds the composer needs to make
deterministic decisions live here. v1 ships a single ``"default"``
profile. Per-user / per-condition profiles (T1D, T2D, pregnancy,
prediabetic) become additional keys in later phases without changing
read paths or composer logic — the additivity discipline from the
Phase 0 lock.

Categories:
    staleness_seconds   — per-field freshness ceilings; inputs older
                          than the ceiling are flagged in
                          ``HealthBriefing.staleness_flags``.
    glucose_targets     — TIR band, with low/high cut points in mg/dL.
    acute_glucose       — severity cut points that promote a reading
                          into ``HealthBriefing.acute_alerts``.
    trend_magnitude     — slope cut points that decide whether a Trend
                          renders as ``up``/``down`` vs ``flat``.
    confidence_floors   — minimum confidence values that gate certain
                          composer behaviors (single-source cap,
                          narration floor, sufficient-data threshold).
    coverage_minimums   — minimum data coverage required before a
                          horizon or fact is considered computable.

This module is pure data + a tiny lookup function. No I/O, no Django
imports, no side effects on import. Frozen dataclasses guarantee the
registry cannot be mutated at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


DEFAULT_PROFILE_KEY = "default"


@dataclass(frozen=True)
class StalenessProfile:
    """Per-field freshness ceilings, in seconds."""

    latest_glucose: int
    glucose_avg_7d: int
    weight_current: int
    sleep_avg_duration: int
    workout_recent: int
    insulin_daily_total: int
    hba1c: int
    fasting_glucose_lab: int
    meal_response: int


@dataclass(frozen=True)
class GlucoseTargets:
    """Time-in-range band, in mg/dL. v1 uses ADA general T2D defaults."""

    tir_low_mg_dl: int
    tir_high_mg_dl: int


@dataclass(frozen=True)
class AcuteGlucose:
    """Cut points that elevate readings to acute alerts (mg/dL)."""

    critical_low_mg_dl: int
    low_mg_dl: int
    high_mg_dl: int
    critical_high_mg_dl: int


@dataclass(frozen=True)
class TrendMagnitude:
    """Magnitude cut points (0..100) that decide trend direction."""

    flat_max: int
    moderate_min: int
    strong_min: int


@dataclass(frozen=True)
class ConfidenceFloors:
    """Confidence values (0.0..1.0) that gate composer behaviors."""

    single_source_cap: float
    narration_floor: float
    sufficient_data_floor: float


@dataclass(frozen=True)
class CoverageMinimums:
    """Minimum data coverage required to compute facts and horizons."""

    glucose_min_readings_7d: int
    glucose_min_readings_30d: int
    glucose_min_readings_90d: int
    weight_min_readings_30d: int
    insulin_min_logs_30d: int
    meal_response_min_meals_7d: int


@dataclass(frozen=True)
class ThresholdProfile:
    """A complete set of thresholds keyed by profile name."""

    staleness_seconds: StalenessProfile
    glucose_targets: GlucoseTargets
    acute_glucose: AcuteGlucose
    trend_magnitude: TrendMagnitude
    confidence_floors: ConfidenceFloors
    coverage_minimums: CoverageMinimums


# Locked v1 defaults. ADA general T2D ranges where applicable. Staleness
# horizons match the Phase 0 lock: CGM ≤6h, weight ≤7d, HbA1c ≤120d, etc.
_DEFAULT_PROFILE = ThresholdProfile(
    staleness_seconds=StalenessProfile(
        latest_glucose=6 * 3600,
        glucose_avg_7d=24 * 3600,
        weight_current=7 * 86400,
        sleep_avg_duration=3 * 86400,
        workout_recent=14 * 86400,
        insulin_daily_total=2 * 86400,
        hba1c=120 * 86400,
        fasting_glucose_lab=90 * 86400,
        meal_response=14 * 86400,
    ),
    glucose_targets=GlucoseTargets(
        tir_low_mg_dl=70,
        tir_high_mg_dl=180,
    ),
    acute_glucose=AcuteGlucose(
        critical_low_mg_dl=54,
        low_mg_dl=70,
        high_mg_dl=250,
        critical_high_mg_dl=300,
    ),
    trend_magnitude=TrendMagnitude(
        flat_max=10,
        moderate_min=25,
        strong_min=50,
    ),
    confidence_floors=ConfidenceFloors(
        single_source_cap=0.75,
        narration_floor=0.5,
        sufficient_data_floor=0.3,
    ),
    coverage_minimums=CoverageMinimums(
        glucose_min_readings_7d=14,
        glucose_min_readings_30d=60,
        glucose_min_readings_90d=180,
        weight_min_readings_30d=3,
        insulin_min_logs_30d=15,
        meal_response_min_meals_7d=4,
    ),
)


_REGISTRY: Dict[str, ThresholdProfile] = {
    DEFAULT_PROFILE_KEY: _DEFAULT_PROFILE,
}


def get_profile(key: str = DEFAULT_PROFILE_KEY) -> ThresholdProfile:
    """
    Return the threshold profile for ``key``, falling back to default.

    Phase 6 will add per-user profile keys (T1D, T2D, pregnancy, etc.).
    The read path here will not change — callers always go through this
    function and never read ``_REGISTRY`` directly.
    """
    return _REGISTRY.get(key, _DEFAULT_PROFILE)


def profile_keys() -> tuple:
    """Snapshot of currently registered profile keys, sorted."""
    return tuple(sorted(_REGISTRY.keys()))
