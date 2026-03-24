# ==============================================================================
# File: apps/core/signals/tests/test_health_signals.py
# Description: Tests for deterministic health signal layer
# ==============================================================================

from datetime import timedelta
from django.test import TestCase
from django.utils import timezone

from apps.core.signals.health_signals import (
    build_health_signals,
    STRONG, MODERATE, POOR, LOW, STABLE, WATCH, UNSTABLE,
    IMPROVING, DECLINING, TREND_STABLE, UNKNOWN,
)


def _now():
    return timezone.now()


def _fresh(dt=None, hours_ago=1):
    base = dt or _now()
    return (base - timedelta(hours=hours_ago)).isoformat()


class TestBuildHealthSignals(TestCase):
    """Top-level builder tests."""

    def test_empty_state_returns_empty_list(self):
        result = build_health_signals({}, {}, _now())
        self.assertEqual(result, [])

    def test_none_inputs_handled(self):
        result = build_health_signals(None, None, _now())
        self.assertEqual(result, [])

    def test_all_signals_returned_when_data_exists(self):
        now = _now()
        health = {
            "sleep_avg_duration_7d": 450, "sleep_entries_7d": 5,
            "steps_avg_7d": 8000, "steps_entries_7d": 6,
            "bp_systolic": 118, "bp_diastolic": 76,
            "last_bp_entry": _fresh(now),
        }
        medicine = {"active_count": 2, "adherence_7d": 85}
        result = build_health_signals(health, medicine, now)
        keys = {s["key"] for s in result}
        self.assertIn("med_adherence", keys)
        self.assertIn("sleep_recovery", keys)
        self.assertIn("activity_momentum", keys)
        self.assertIn("cardio_stability", keys)

    def test_each_signal_has_required_fields(self):
        now = _now()
        health = {
            "sleep_avg_duration_7d": 450, "sleep_entries_7d": 5,
            "steps_avg_7d": 8000, "steps_entries_7d": 6,
        }
        medicine = {"active_count": 2, "adherence_7d": 92}
        result = build_health_signals(health, medicine, now)
        for sig in result:
            self.assertIn("key", sig)
            self.assertIn("state", sig)
            self.assertIn("insight", sig)


# ── Signal 1: Medication Adherence ──────────────────────────────────────────

class TestMedAdherence(TestCase):

    def test_strong_adherence(self):
        medicine = {"active_count": 3, "adherence_7d": 95}
        result = build_health_signals({}, medicine, _now())
        sig = next(s for s in result if s["key"] == "med_adherence")
        self.assertEqual(sig["state"], STRONG)
        self.assertEqual(sig["value"], 0.95)

    def test_moderate_adherence(self):
        medicine = {"active_count": 2, "adherence_7d": 78}
        result = build_health_signals({}, medicine, _now())
        sig = next(s for s in result if s["key"] == "med_adherence")
        self.assertEqual(sig["state"], MODERATE)

    def test_poor_adherence(self):
        medicine = {"active_count": 2, "adherence_7d": 55}
        result = build_health_signals({}, medicine, _now())
        sig = next(s for s in result if s["key"] == "med_adherence")
        self.assertEqual(sig["state"], POOR)

    def test_no_active_meds_no_signal(self):
        medicine = {"active_count": 0, "adherence_7d": 100}
        result = build_health_signals({}, medicine, _now())
        keys = {s["key"] for s in result}
        self.assertNotIn("med_adherence", keys)

    def test_no_adherence_data_no_signal(self):
        medicine = {"active_count": 2}
        result = build_health_signals({}, medicine, _now())
        keys = {s["key"] for s in result}
        self.assertNotIn("med_adherence", keys)

    def test_trend_unknown_without_prior(self):
        medicine = {"active_count": 2, "adherence_7d": 80}
        result = build_health_signals({}, medicine, _now())
        sig = next(s for s in result if s["key"] == "med_adherence")
        self.assertEqual(sig["trend"], UNKNOWN)

    def test_trend_declining_with_prior(self):
        medicine = {
            "active_count": 2,
            "adherence_7d": 62,
            "adherence_prior_7d": 88,
        }
        result = build_health_signals({}, medicine, _now())
        sig = next(s for s in result if s["key"] == "med_adherence")
        self.assertEqual(sig["trend"], DECLINING)

    def test_trend_improving_with_prior(self):
        medicine = {
            "active_count": 2,
            "adherence_7d": 90,
            "adherence_prior_7d": 70,
        }
        result = build_health_signals({}, medicine, _now())
        sig = next(s for s in result if s["key"] == "med_adherence")
        self.assertEqual(sig["trend"], IMPROVING)


# ── Signal 2: Sleep Recovery ────────────────────────────────────────────────

class TestSleepRecovery(TestCase):

    def test_strong_sleep(self):
        health = {"sleep_avg_duration_7d": 450, "sleep_entries_7d": 6}
        result = build_health_signals(health, {}, _now())
        sig = next(s for s in result if s["key"] == "sleep_recovery")
        self.assertEqual(sig["state"], STRONG)
        self.assertEqual(sig["value"], 7.5)

    def test_moderate_sleep(self):
        health = {"sleep_avg_duration_7d": 390, "sleep_entries_7d": 5}
        result = build_health_signals(health, {}, _now())
        sig = next(s for s in result if s["key"] == "sleep_recovery")
        self.assertEqual(sig["state"], MODERATE)

    def test_poor_sleep(self):
        health = {"sleep_avg_duration_7d": 300, "sleep_entries_7d": 5}
        result = build_health_signals(health, {}, _now())
        sig = next(s for s in result if s["key"] == "sleep_recovery")
        self.assertEqual(sig["state"], POOR)

    def test_no_sleep_data_no_signal(self):
        result = build_health_signals({}, {}, _now())
        keys = {s["key"] for s in result}
        self.assertNotIn("sleep_recovery", keys)

    def test_zero_entries_no_signal(self):
        health = {"sleep_avg_duration_7d": 450, "sleep_entries_7d": 0}
        result = build_health_signals(health, {}, _now())
        keys = {s["key"] for s in result}
        self.assertNotIn("sleep_recovery", keys)

    def test_trend_unknown_without_prior(self):
        health = {"sleep_avg_duration_7d": 450, "sleep_entries_7d": 5}
        result = build_health_signals(health, {}, _now())
        sig = next(s for s in result if s["key"] == "sleep_recovery")
        self.assertEqual(sig["trend"], UNKNOWN)


# ── Signal 3: Activity Momentum ────────────────────────────────────────────

class TestActivityMomentum(TestCase):

    def test_strong_activity(self):
        health = {"steps_avg_7d": 9000, "steps_entries_7d": 7}
        result = build_health_signals(health, {}, _now())
        sig = next(s for s in result if s["key"] == "activity_momentum")
        self.assertEqual(sig["state"], STRONG)
        self.assertEqual(sig["value"], 9000)

    def test_moderate_activity(self):
        health = {"steps_avg_7d": 5000, "steps_entries_7d": 6}
        result = build_health_signals(health, {}, _now())
        sig = next(s for s in result if s["key"] == "activity_momentum")
        self.assertEqual(sig["state"], MODERATE)

    def test_low_activity(self):
        health = {"steps_avg_7d": 1500, "steps_entries_7d": 4}
        result = build_health_signals(health, {}, _now())
        sig = next(s for s in result if s["key"] == "activity_momentum")
        self.assertEqual(sig["state"], LOW)

    def test_no_steps_no_signal(self):
        result = build_health_signals({}, {}, _now())
        keys = {s["key"] for s in result}
        self.assertNotIn("activity_momentum", keys)

    def test_trend_declining_with_prior(self):
        health = {
            "steps_avg_7d": 2000,
            "steps_entries_7d": 5,
            "steps_avg_prior_7d": 6000,
        }
        result = build_health_signals(health, {}, _now())
        sig = next(s for s in result if s["key"] == "activity_momentum")
        self.assertEqual(sig["trend"], DECLINING)
        self.assertIn("trending down", sig["insight"])


# ── Signal 4: Cardiometabolic Stability ─────────────────────────────────────

class TestCardioStability(TestCase):

    def test_stable_all_normal(self):
        now = _now()
        health = {
            "bp_systolic": 118, "bp_diastolic": 76,
            "last_bp_entry": _fresh(now),
            "latest_glucose": 95, "latest_glucose_unit": "mg/dL",
            "last_glucose_entry": _fresh(now),
            "latest_heart_rate": 72,
            "last_heart_rate_entry": _fresh(now),
        }
        result = build_health_signals(health, {}, now)
        sig = next(s for s in result if s["key"] == "cardio_stability")
        self.assertEqual(sig["state"], STABLE)
        self.assertEqual(sig["value"], 0)

    def test_watch_one_elevated(self):
        now = _now()
        health = {
            "bp_systolic": 155, "bp_diastolic": 95,
            "last_bp_entry": _fresh(now),
            "latest_glucose": 95, "latest_glucose_unit": "mg/dL",
            "last_glucose_entry": _fresh(now),
        }
        result = build_health_signals(health, {}, now)
        sig = next(s for s in result if s["key"] == "cardio_stability")
        self.assertEqual(sig["state"], WATCH)
        self.assertEqual(sig["value"], 1)

    def test_unstable_multiple_abnormal(self):
        now = _now()
        health = {
            "bp_systolic": 160, "bp_diastolic": 100,
            "last_bp_entry": _fresh(now),
            "latest_glucose": 220, "latest_glucose_unit": "mg/dL",
            "last_glucose_entry": _fresh(now),
            "latest_heart_rate": 110,
            "last_heart_rate_entry": _fresh(now),
        }
        result = build_health_signals(health, {}, now)
        sig = next(s for s in result if s["key"] == "cardio_stability")
        self.assertEqual(sig["state"], UNSTABLE)
        self.assertGreaterEqual(sig["value"], 2)

    def test_no_fresh_data_no_signal(self):
        now = _now()
        health = {
            "bp_systolic": 118, "bp_diastolic": 76,
            "last_bp_entry": (now - timedelta(days=10)).isoformat(),
        }
        result = build_health_signals(health, {}, now)
        keys = {s["key"] for s in result}
        self.assertNotIn("cardio_stability", keys)

    def test_partial_data_still_emits(self):
        """Even with only BP (1 metric), signal should emit."""
        now = _now()
        health = {
            "bp_systolic": 118, "bp_diastolic": 76,
            "last_bp_entry": _fresh(now),
        }
        result = build_health_signals(health, {}, now)
        sig = next(s for s in result if s["key"] == "cardio_stability")
        self.assertEqual(sig["state"], STABLE)

    def test_mmol_glucose_conversion(self):
        now = _now()
        health = {
            "latest_glucose": 12.0, "latest_glucose_unit": "mmol/L",
            "last_glucose_entry": _fresh(now),
        }
        result = build_health_signals(health, {}, now)
        sig = next(s for s in result if s["key"] == "cardio_stability")
        # 12 mmol/L = 216 mg/dL → elevated
        self.assertEqual(sig["state"], WATCH)


class TestSignalDeterminism(TestCase):
    """Signals must be deterministic — same inputs = same outputs."""

    def test_same_inputs_same_outputs(self):
        now = _now()
        health = {
            "sleep_avg_duration_7d": 400, "sleep_entries_7d": 5,
            "steps_avg_7d": 5000, "steps_entries_7d": 6,
        }
        medicine = {"active_count": 2, "adherence_7d": 82}
        r1 = build_health_signals(health, medicine, now)
        r2 = build_health_signals(health, medicine, now)
        self.assertEqual(r1, r2)
