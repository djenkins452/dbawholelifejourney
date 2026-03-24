# ==============================================================================
# File: apps/health/tests/test_health_priority_service.py
# Description: Tests for deterministic health priority summary builder
# ==============================================================================

from datetime import datetime, timedelta
from django.test import TestCase
from django.utils import timezone

from apps.health.services.health_priority_service import (
    build_health_priority_summary,
    MAX_ITEMS,
    MIN_ITEMS,
    HIGH,
    MEDIUM,
    LOW,
)


def _now():
    return timezone.now()


def _fresh(dt=None, hours_ago=1):
    """Return a fresh ISO timestamp relative to dt (default: now)."""
    base = dt or _now()
    return (base - timedelta(hours=hours_ago)).isoformat()


def _health_state(**overrides):
    """Build a minimal health state dict."""
    base = {}
    base.update(overrides)
    return base


def _medicine_state(**overrides):
    """Build a minimal medicine state dict."""
    base = {
        "active_count": 0,
        "today_taken": 0,
        "today_missed": 0,
        "expected_today": 0,
        "schedule_status_today": [],
        "_contract": {
            "alerts": {"overdue": [], "missed": [], "needs_refill": []},
            "summary": {},
            "today": {},
        },
    }
    base.update(overrides)
    return base


class TestContract(TestCase):
    """Verify the output contract shape."""

    def test_empty_state_returns_valid_contract(self):
        result = build_health_priority_summary({}, {}, _now())
        self.assertIn("items", result)
        self.assertIn("flags", result)
        self.assertIn("generated_at", result)
        self.assertIn("headline", result)
        self.assertIn("priority_level", result)
        self.assertIsInstance(result["items"], list)
        self.assertIsInstance(result["flags"], dict)

    def test_empty_state_has_no_items(self):
        result = build_health_priority_summary({}, {}, _now())
        self.assertEqual(len(result["items"]), 0)

    def test_none_inputs_handled(self):
        result = build_health_priority_summary(None, None, _now())
        self.assertEqual(len(result["items"]), 0)

    def test_max_four_items(self):
        """Even with many signals, max 4 items."""
        now = _now()
        health = _health_state(
            bp_systolic=190, bp_diastolic=130, last_bp_entry=_fresh(now),
            sleep_avg_duration_7d=300, sleep_entries_7d=5,
            last_sleep_entry=now.date().isoformat(),
            steps_avg_7d=1000, steps_entries_7d=5,
            latest_glucose=40, latest_glucose_unit="mg/dL",
            last_glucose_entry=_fresh(now),
            latest_blood_oxygen=85, last_blood_oxygen_entry=_fresh(now),
            latest_heart_rate=110, last_heart_rate_entry=_fresh(now),
        )
        meds = _medicine_state(
            active_count=3, expected_today=3,
            _contract={"alerts": {
                "overdue": [{"medicine_name": "Med1"}],
                "missed": [], "needs_refill": [],
            }},
        )
        result = build_health_priority_summary(health, meds, now)
        self.assertLessEqual(len(result["items"]), MAX_ITEMS)


# ── FIX 1: Medication dominance ─────────────────────────────────────────────

class TestMedicationDominance(TestCase):
    """Overdue medications MUST always be item[0]."""

    def test_overdue_meds_always_first(self):
        now = _now()
        health = _health_state(
            bp_systolic=190, bp_diastolic=130, last_bp_entry=_fresh(now),
            latest_blood_oxygen=85, last_blood_oxygen_entry=_fresh(now),
        )
        meds = _medicine_state(
            active_count=2,
            _contract={"alerts": {
                "overdue": [{"medicine_name": "Aspirin"}],
                "missed": [], "needs_refill": [],
            }},
        )
        result = build_health_priority_summary(health, meds, now)
        self.assertEqual(result["items"][0]["key"], "medications_overdue")

    def test_overdue_forces_high_priority_level(self):
        meds = _medicine_state(
            active_count=1,
            _contract={"alerts": {
                "overdue": [{"medicine_name": "X"}],
                "missed": [], "needs_refill": [],
            }},
        )
        result = build_health_priority_summary({}, meds, _now())
        self.assertEqual(result["priority_level"], HIGH)
        self.assertTrue(result["flags"]["has_medication_risk"])

    def test_overdue_count_in_message(self):
        meds = _medicine_state(
            active_count=3,
            _contract={"alerts": {
                "overdue": [
                    {"medicine_name": "A"},
                    {"medicine_name": "B"},
                    {"medicine_name": "C"},
                ],
                "missed": [], "needs_refill": [],
            }},
        )
        result = build_health_priority_summary({}, meds, _now())
        self.assertIn("3 medications overdue", result["items"][0]["message"])


# ── FIX 2: Minimum item count ───────────────────────────────────────────────

class TestMinimumItems(TestCase):
    """Summary should have at least 2 items when possible."""

    def test_single_signal_gets_filled_if_others_available(self):
        """Overdue meds + BP available = should get 2+ items."""
        now = _now()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75, last_bp_entry=_fresh(now),
        )
        meds = _medicine_state(
            active_count=1,
            _contract={"alerts": {
                "overdue": [{"medicine_name": "X"}],
                "missed": [], "needs_refill": [],
            }},
        )
        result = build_health_priority_summary(health, meds, now)
        self.assertGreaterEqual(len(result["items"]), MIN_ITEMS)

    def test_truly_single_signal_allowed(self):
        """If only one signal exists in total, 1 item is OK."""
        meds = _medicine_state(
            active_count=1,
            _contract={"alerts": {
                "overdue": [{"medicine_name": "X"}],
                "missed": [], "needs_refill": [],
            }},
        )
        result = build_health_priority_summary({}, meds, _now())
        self.assertEqual(len(result["items"]), 1)


# ── FIX 3: Headline ─────────────────────────────────────────────────────────

class TestHeadline(TestCase):
    """Headline must always be present and match priority level."""

    def test_high_headline(self):
        meds = _medicine_state(
            active_count=1,
            _contract={"alerts": {
                "overdue": [{"medicine_name": "X"}],
                "missed": [], "needs_refill": [],
            }},
        )
        result = build_health_priority_summary({}, meds, _now())
        self.assertEqual(result["headline"], "Health needs attention")

    def test_medium_headline(self):
        now = _now()
        health = _health_state(
            sleep_avg_duration_7d=300, sleep_entries_7d=5,
            last_sleep_entry=now.date().isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        self.assertEqual(result["headline"], "A few things need attention")

    def test_low_headline(self):
        now = _now()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75, last_bp_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        self.assertEqual(result["headline"], "Health looks stable")

    def test_empty_headline(self):
        result = build_health_priority_summary({}, {}, _now())
        self.assertEqual(result["headline"], "Health looks stable")


# ── FIX 4: Activity signal correction ───────────────────────────────────────

class TestActivitySignal(TestCase):
    """Activity message must match available data."""

    def test_today_steps_with_afternoon_context(self):
        """With today_steps + hour >= 12, use 'so far today'."""
        now = _now().replace(hour=13, minute=0, second=0)
        health = _health_state(
            steps_avg_7d=2000, steps_entries_7d=5,
            today_steps=1500,
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "activity_low"]
        self.assertEqual(len(items), 1)
        self.assertIn("so far today", items[0]["message"])

    def test_no_today_steps_uses_lately(self):
        """Without today_steps, use 'lately'."""
        health = _health_state(steps_avg_7d=2000, steps_entries_7d=5)
        result = build_health_priority_summary(health, {}, _now())
        items = [i for i in result["items"] if i["key"] == "activity_low"]
        self.assertEqual(len(items), 1)
        self.assertIn("lately", items[0]["message"])

    def test_morning_with_today_steps_uses_lately(self):
        """Even with today_steps, morning hour < 12 uses 'lately'."""
        now = _now().replace(hour=9, minute=0, second=0)
        health = _health_state(
            steps_avg_7d=2000, steps_entries_7d=5,
            today_steps=500,
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "activity_low"]
        self.assertEqual(len(items), 1)
        self.assertIn("lately", items[0]["message"])


# ── FIX 5: Tone standardization ─────────────────────────────────────────────

class TestTone(TestCase):
    """Messages use coaching tone, not clinical."""

    def test_bp_normal_says_looks_good(self):
        now = _now()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75, last_bp_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "bp_normal"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["message"], "Blood pressure looks good")

    def test_spo2_low_surfaces_when_concerning(self):
        """SpO2 only surfaces when actually low (< 90)."""
        now = _now()
        health = _health_state(
            latest_blood_oxygen=87, last_blood_oxygen_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "spo2_low"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "high")

    def test_glucose_in_range_says_healthy_range(self):
        now = _now()
        health = _health_state(
            latest_glucose=100, latest_glucose_unit="mg/dL",
            last_glucose_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "glucose_normal"]
        self.assertEqual(len(items), 1)
        self.assertIn("healthy range", items[0]["message"])

    def test_no_message_contains_is_normal(self):
        """No message should use the clinical phrase 'is normal'."""
        now = _now()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75, last_bp_entry=_fresh(now),
            latest_blood_oxygen=98, last_blood_oxygen_entry=_fresh(now),
            latest_glucose=100, latest_glucose_unit="mg/dL",
            last_glucose_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        for item in result["items"]:
            self.assertNotIn("is normal", item["message"])


# ── FIX 6: Balanced output ──────────────────────────────────────────────────

class TestBalancedOutput(TestCase):
    """Summary should include a positive if room and data exist."""

    def test_positive_added_when_room_exists(self):
        """Medium concern + available positive = include positive."""
        now = _now()
        health = _health_state(
            sleep_avg_duration_7d=300, sleep_entries_7d=5,
            last_sleep_entry=now.date().isoformat(),
            bp_systolic=115, bp_diastolic=75, last_bp_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        has_positive = any(i["priority"] == LOW for i in result["items"])
        self.assertTrue(has_positive)

    def test_no_false_positives_injected(self):
        """Don't inject positive if no positive data exists."""
        now = _now()
        health = _health_state(
            sleep_avg_duration_7d=300, sleep_entries_7d=5,
            last_sleep_entry=now.date().isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        # Only sleep_short should exist — no positive data available
        positives = [i for i in result["items"] if i["priority"] == LOW]
        self.assertEqual(len(positives), 0)


# ── Original tests (preserved) ──────────────────────────────────────────────

class TestMedications(TestCase):

    def test_overdue_meds_are_high_priority(self):
        meds = _medicine_state(
            active_count=2,
            _contract={"alerts": {
                "overdue": [
                    {"medicine_name": "Aspirin", "status": "overdue"},
                    {"medicine_name": "Metformin", "status": "overdue"},
                ],
                "missed": [], "needs_refill": [],
            }},
        )
        result = build_health_priority_summary({}, meds, _now())
        item = result["items"][0]
        self.assertEqual(item["priority"], "high")
        self.assertEqual(item["key"], "medications_overdue")
        self.assertIn("2 medications overdue", item["message"])
        self.assertTrue(result["flags"]["has_urgent"])
        self.assertTrue(result["flags"]["has_medication_risk"])

    def test_low_adherence_is_medium_priority(self):
        meds = _medicine_state(
            active_count=3, adherence_7d=55,
            _contract={"alerts": {"overdue": [], "missed": [], "needs_refill": []}},
        )
        result = build_health_priority_summary({}, meds, _now())
        items = [i for i in result["items"] if i["key"] == "medication_adherence_low"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "medium")

    def test_all_taken_is_low_reassurance(self):
        meds = _medicine_state(
            active_count=2, expected_today=4, today_taken=4,
            _contract={"alerts": {"overdue": [], "missed": [], "needs_refill": []}},
        )
        result = build_health_priority_summary({}, meds, _now())
        items = [i for i in result["items"] if i["key"] == "medications_on_track"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "low")

    def test_no_active_meds_no_item(self):
        meds = _medicine_state(active_count=0)
        result = build_health_priority_summary({}, meds, _now())
        med_items = [i for i in result["items"] if i["category"] == "medical"]
        self.assertEqual(len(med_items), 0)


class TestBloodPressure(TestCase):

    def test_crisis_bp_is_high(self):
        now = _now()
        health = _health_state(
            bp_systolic=185, bp_diastolic=125, last_bp_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "bp_crisis"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "high")

    def test_stale_bp_suppressed(self):
        now = _now()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75,
            last_bp_entry=(now - timedelta(days=10)).isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        bp_items = [i for i in result["items"] if "bp" in i["key"]]
        self.assertEqual(len(bp_items), 0)

    def test_elevated_bp_is_medium(self):
        now = _now()
        health = _health_state(
            bp_systolic=155, bp_diastolic=95, last_bp_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "bp_elevated"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "medium")


class TestSleep(TestCase):

    def test_strong_sleep_fresh_is_low(self):
        now = _now()
        health = _health_state(
            sleep_avg_duration_7d=450, sleep_entries_7d=6,
            last_sleep_entry=now.date().isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "sleep_strong"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["message"], "Sleep has been strong")

    def test_short_sleep_is_medium(self):
        now = _now()
        health = _health_state(
            sleep_avg_duration_7d=310, sleep_entries_7d=5,
            last_sleep_entry=now.date().isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "sleep_short"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "medium")

    def test_stale_sleep_suppressed(self):
        now = _now()
        health = _health_state(
            sleep_avg_duration_7d=450, sleep_entries_7d=3,
            last_sleep_entry=(now - timedelta(days=5)).date().isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        sleep_items = [i for i in result["items"] if "sleep" in i["key"]]
        self.assertEqual(len(sleep_items), 0)


class TestSteps(TestCase):

    def test_low_steps_is_medium(self):
        health = _health_state(steps_avg_7d=2000, steps_entries_7d=5)
        result = build_health_priority_summary(health, {}, _now())
        items = [i for i in result["items"] if i["key"] == "activity_low"]
        self.assertEqual(len(items), 1)

    def test_good_steps_is_low(self):
        health = _health_state(steps_avg_7d=9000, steps_entries_7d=6)
        result = build_health_priority_summary(health, {}, _now())
        items = [i for i in result["items"] if i["key"] == "activity_on_track"]
        self.assertEqual(len(items), 1)

    def test_no_step_entries_suppressed(self):
        health = _health_state(steps_avg_7d=2000, steps_entries_7d=0)
        result = build_health_priority_summary(health, {}, _now())
        step_items = [i for i in result["items"] if "activity" in i["key"]]
        self.assertEqual(len(step_items), 0)


class TestGlucose(TestCase):

    def test_severe_low_glucose_is_high(self):
        now = _now()
        health = _health_state(
            latest_glucose=45, latest_glucose_unit="mg/dL",
            last_glucose_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "glucose_severe"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "high")

    def test_mmol_conversion(self):
        now = _now()
        health = _health_state(
            latest_glucose=2.5, latest_glucose_unit="mmol/L",  # = 45 mg/dL
            last_glucose_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "glucose_severe"]
        self.assertEqual(len(items), 1)


class TestBloodOxygen(TestCase):
    def test_low_spo2_is_high(self):
        now = _now()
        health = _health_state(
            latest_blood_oxygen=87, last_blood_oxygen_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "spo2_low"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "high")

    def test_normal_spo2_suppressed(self):
        """Normal SpO2 is trivial — not worth a summary slot."""
        now = _now()
        health = _health_state(
            latest_blood_oxygen=98, last_blood_oxygen_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        spo2_items = [i for i in result["items"] if "spo2" in i["key"]]
        self.assertEqual(len(spo2_items), 0)


class TestHeartRate(TestCase):
    def test_elevated_hr_is_medium(self):
        now = _now()
        health = _health_state(
            latest_heart_rate=110, last_heart_rate_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "hr_elevated"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "medium")


class TestOrdering(TestCase):
    def test_high_before_medium_before_low(self):
        now = _now()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75, last_bp_entry=_fresh(now),
            sleep_avg_duration_7d=300, sleep_entries_7d=5,
            last_sleep_entry=now.date().isoformat(),
        )
        meds = _medicine_state(
            active_count=2,
            _contract={"alerts": {
                "overdue": [{"medicine_name": "Med1"}],
                "missed": [], "needs_refill": [],
            }},
        )
        result = build_health_priority_summary(health, meds, now)
        priorities = [i["priority"] for i in result["items"]]
        self.assertEqual(priorities[0], "high")


class TestFlags(TestCase):
    def test_urgent_flag_set(self):
        meds = _medicine_state(
            active_count=1,
            _contract={"alerts": {
                "overdue": [{"medicine_name": "X"}],
                "missed": [], "needs_refill": [],
            }},
        )
        result = build_health_priority_summary({}, meds, _now())
        self.assertTrue(result["flags"]["has_urgent"])

    def test_positive_flag_set(self):
        now = _now()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75, last_bp_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        self.assertTrue(result["flags"]["has_positive"])

    def test_no_flags_when_empty(self):
        result = build_health_priority_summary({}, {}, _now())
        self.assertFalse(result["flags"]["has_urgent"])
        self.assertFalse(result["flags"]["has_positive"])


class TestNoDuplicateCategories(TestCase):
    def test_only_one_vitals_item_when_not_both_high(self):
        """BP (low) and glucose (low) are both vitals — only first kept."""
        now = _now()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75, last_bp_entry=_fresh(now),
            latest_glucose=100, latest_glucose_unit="mg/dL",
            last_glucose_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        vitals = [i for i in result["items"] if i["category"] == "vitals"]
        self.assertEqual(len(vitals), 1)


# ── Phase C: Signal → Summary Integration ───────────────────────────────────

class TestSignalIntegration(TestCase):
    """Signal injection into summary."""

    def test_concerning_signal_injected(self):
        """A 'poor' signal appears in summary."""
        now = _now()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75, last_bp_entry=_fresh(now),
        )
        signals = [
            {"key": "activity_momentum", "state": "low", "trend": "declining",
             "value": 1500, "insight": "Activity levels are trending down this week"},
        ]
        result = build_health_priority_summary(health, {}, now, signals=signals)
        signal_items = [i for i in result["items"] if i["key"].startswith("signal_")]
        self.assertEqual(len(signal_items), 1)
        self.assertEqual(signal_items[0]["key"], "signal_activity_momentum")
        self.assertIn("trending down", signal_items[0]["message"])

    def test_stable_signal_not_injected(self):
        """A 'strong' signal should NOT appear in summary."""
        now = _now()
        signals = [
            {"key": "sleep_recovery", "state": "strong", "trend": "stable",
             "value": 7.5, "insight": "Sleep has been strong this week"},
        ]
        result = build_health_priority_summary({}, {}, now, signals=signals)
        signal_items = [i for i in result["items"] if i["key"].startswith("signal_")]
        self.assertEqual(len(signal_items), 0)

    def test_signal_does_not_duplicate_existing_item(self):
        """If activity_low already in summary, activity_momentum signal skipped."""
        now = _now()
        health = _health_state(steps_avg_7d=2000, steps_entries_7d=5)
        signals = [
            {"key": "activity_momentum", "state": "low", "trend": "declining",
             "value": 2000, "insight": "Activity levels are trending down this week"},
        ]
        result = build_health_priority_summary(health, {}, now, signals=signals)
        signal_items = [i for i in result["items"] if i["key"].startswith("signal_")]
        self.assertEqual(len(signal_items), 0)

    def test_signal_after_medications(self):
        """Signal injected at index 1 when meds are at index 0."""
        now = _now()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75, last_bp_entry=_fresh(now),
        )
        meds = _medicine_state(
            active_count=2,
            _contract={"alerts": {
                "overdue": [{"medicine_name": "Aspirin"}],
                "missed": [], "needs_refill": [],
            }},
        )
        signals = [
            {"key": "sleep_recovery", "state": "poor", "trend": "declining",
             "value": 4.5, "insight": "Sleep has been short this week"},
        ]
        result = build_health_priority_summary(health, meds, now, signals=signals)
        # Meds still first
        self.assertEqual(result["items"][0]["key"], "medications_overdue")
        # Signal at index 1
        self.assertEqual(result["items"][1]["key"], "signal_sleep_recovery")

    def test_max_one_signal(self):
        """Only ONE signal injected even if multiple are concerning."""
        now = _now()
        signals = [
            {"key": "med_adherence", "state": "poor", "trend": "declining",
             "value": 0.55, "insight": "Medication adherence has been declining"},
            {"key": "cardio_stability", "state": "unstable",
             "value": 2, "insight": "Multiple vital signs need attention"},
            {"key": "sleep_recovery", "state": "poor", "trend": "declining",
             "value": 4.5, "insight": "Sleep has been short this week"},
        ]
        result = build_health_priority_summary({}, {}, now, signals=signals)
        signal_items = [i for i in result["items"] if i["key"].startswith("signal_")]
        self.assertLessEqual(len(signal_items), 1)

    def test_max_4_items_with_signal(self):
        """Signal counts toward max 4."""
        now = _now()
        health = _health_state(
            bp_systolic=155, bp_diastolic=95, last_bp_entry=_fresh(now),
            sleep_avg_duration_7d=300, sleep_entries_7d=5,
            last_sleep_entry=now.date().isoformat(),
            steps_avg_7d=2000, steps_entries_7d=5,
        )
        meds = _medicine_state(
            active_count=1,
            _contract={"alerts": {
                "overdue": [{"medicine_name": "X"}],
                "missed": [], "needs_refill": [],
            }},
        )
        signals = [
            {"key": "cardio_stability", "state": "watch",
             "value": 1, "insight": "One vital sign is outside the normal range"},
        ]
        result = build_health_priority_summary(health, meds, now, signals=signals)
        self.assertLessEqual(len(result["items"]), 4)

    def test_no_signals_backward_compatible(self):
        """Without signals param, summary works as before."""
        now = _now()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75, last_bp_entry=_fresh(now),
        )
        result = build_health_priority_summary(health, {}, now)
        self.assertTrue(len(result["items"]) >= 1)
        signal_items = [i for i in result["items"] if i["key"].startswith("signal_")]
        self.assertEqual(len(signal_items), 0)

    def test_signal_priority_order(self):
        """med_adherence chosen over sleep_recovery when both concern."""
        signals = [
            {"key": "sleep_recovery", "state": "poor", "trend": "declining",
             "value": 4.5, "insight": "Sleep has been short"},
            {"key": "med_adherence", "state": "poor", "trend": "declining",
             "value": 0.55, "insight": "Medication adherence declining"},
        ]
        result = build_health_priority_summary({}, {}, _now(), signals=signals)
        signal_items = [i for i in result["items"] if i["key"].startswith("signal_")]
        self.assertEqual(len(signal_items), 1)
        self.assertEqual(signal_items[0]["key"], "signal_med_adherence")

    def test_unstable_cardio_gets_high_priority(self):
        """Unstable cardio signal maps to HIGH priority."""
        signals = [
            {"key": "cardio_stability", "state": "unstable",
             "value": 2, "insight": "Multiple vital signs need attention"},
        ]
        result = build_health_priority_summary({}, {}, _now(), signals=signals)
        signal_items = [i for i in result["items"] if i["key"].startswith("signal_")]
        self.assertEqual(len(signal_items), 1)
        self.assertEqual(signal_items[0]["priority"], "high")
