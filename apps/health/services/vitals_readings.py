# ==============================================================================
# File: apps/health/services/vitals_readings.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Intra-day reading-window producers for high-frequency VITALS —
#              heart rate, blood pressure (systolic), SpO2, body temperature.
#              Second+ adopters of the platform ReadingWindow capability (glucose was
#              first). Answers "what time of day is my BP highest", "my HR through the
#              day", "when did my SpO2 dip". Read-only, deterministic, request-path-safe.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Vitals reading-window producers.

Each is THE single producer of intra-day truth for its metric, consumed by the CoS
`get_readings` tool (via HealthDomainTruth.readings) — no parallel retrieval. Each
declares a `ReadingWindowSpec` (value getter normalized to the canonical unit + clinical
thresholds) and delegates to the platform `build_reading_series` with the hour-of-day
distribution enabled. Facts only; the model interprets.
"""
from apps.core.truth.reading_window import ReadingWindowSpec, build_reading_series


HEART_RATE_SPEC = ReadingWindowSpec(
    domain="health", metric="heart_rate", unit="bpm",
    value_getter=lambda e: float(e.bpm),
    time_getter=lambda e: e.recorded_at,
    low=60, high=100, urgent_low=40, urgent_high=150,
)

# Blood pressure is two numbers; the reading series carries systolic (the headline the
# model narrates with diastolic from record detail). Thresholds = ACC/AHA-ish bands.
BLOOD_PRESSURE_SPEC = ReadingWindowSpec(
    domain="health", metric="blood_pressure", unit="mmHg",
    value_getter=lambda e: float(e.systolic),
    time_getter=lambda e: e.recorded_at,
    low=90, high=130, urgent_low=80, urgent_high=180,
)

SPO2_SPEC = ReadingWindowSpec(
    domain="health", metric="spo2", unit="%",
    value_getter=lambda e: float(e.spo2),
    time_getter=lambda e: e.recorded_at,
    low=95, high=100, urgent_low=90,
)

BODY_TEMPERATURE_SPEC = ReadingWindowSpec(
    domain="health", metric="body_temperature", unit="°F",
    value_getter=lambda e: e.temperature_fahrenheit,   # normalizes mixed C/F
    time_getter=lambda e: e.recorded_at,
    low=97.0, high=99.5, urgent_low=95.0, urgent_high=100.4,
)


def _window_rows(model, user, window, fields):
    return list(
        model.objects.filter(user=user,
                             recorded_at__gte=window.start,
                             recorded_at__lte=window.end)
        .only(*fields).order_by("recorded_at"))


def heart_rate_reading_window(user, window) -> dict:
    from apps.health.models import HeartRateEntry
    rows = _window_rows(HeartRateEntry, user, window, ("bpm", "recorded_at"))
    return build_reading_series(HEART_RATE_SPEC, window, rows, with_by_hour=True).to_dict()


def blood_pressure_reading_window(user, window) -> dict:
    from apps.health.models import BloodPressureEntry
    rows = _window_rows(BloodPressureEntry, user, window,
                        ("systolic", "diastolic", "recorded_at"))
    return build_reading_series(BLOOD_PRESSURE_SPEC, window, rows,
                                with_by_hour=True).to_dict()


def spo2_reading_window(user, window) -> dict:
    from apps.health.models import BloodOxygenEntry
    rows = _window_rows(BloodOxygenEntry, user, window, ("spo2", "recorded_at"))
    return build_reading_series(SPO2_SPEC, window, rows, with_by_hour=True).to_dict()


def body_temperature_reading_window(user, window) -> dict:
    from apps.health.models import BodyTemperatureEntry
    rows = _window_rows(BodyTemperatureEntry, user, window,
                        ("temperature", "unit", "recorded_at"))
    return build_reading_series(BODY_TEMPERATURE_SPEC, window, rows,
                                with_by_hour=True).to_dict()
