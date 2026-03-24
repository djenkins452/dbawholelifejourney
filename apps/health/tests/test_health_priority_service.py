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
)


def _now():
    return timezone.now()


def _health_state(**overrides):
    """Build a minimal health state dict with sensible defaults."""
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


class TestHealthPrioritySummaryContract(TestCase):
    """Verify the output contract shape."""

    def test_empty_state_returns_valid_contract(self):
        result = build_health_priority_summary({}, {}, _now())
        self.assertIn("items", result)
        self.assertIn("flags", result)
        self.assertIn("generated_at", result)
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
        fresh = (now - timedelta(hours=1)).isoformat()
        health = _health_state(
            bp_systolic=190, bp_diastolic=130, last_bp_entry=fresh,
            sleep_avg_duration_7d=300, sleep_entries_7d=5, last_sleep_entry=now.date().isoformat(),
            steps_avg_7d=1000, steps_entries_7d=5,
            latest_glucose=40, latest_glucose_unit="mg/dL", last_glucose_entry=fresh,
            latest_blood_oxygen=85, last_blood_oxygen_entry=fresh,
            latest_heart_rate=110, last_heart_rate_entry=fresh,
        )
        meds = _medicine_state(
            active_count=3, expected_today=3,
            _contract={"alerts": {"overdue": [{"medicine_name": "Med1"}], "missed": [], "needs_refill": []}},
        )
        result = build_health_priority_summary(health, meds, now)
        self.assertLessEqual(len(result["items"]), MAX_ITEMS)


class TestMedications(TestCase):
    """Medication priority tests."""

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
        self.assertEqual(len(result["items"]), 1)
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
    """Blood pressure priority tests."""

    def test_normal_bp_fresh_is_low(self):
        now = _now()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75,
            last_bp_entry=(now - timedelta(hours=2)).isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "bp_normal"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "low")
        self.assertEqual(items[0]["message"], "Blood pressure is normal")

    def test_crisis_bp_is_high(self):
        now = _now()
        health = _health_state(
            bp_systolic=185, bp_diastolic=125,
            last_bp_entry=(now - timedelta(hours=1)).isoformat(),
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
            bp_systolic=155, bp_diastolic=95,
            last_bp_entry=(now - timedelta(hours=3)).isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "bp_elevated"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "medium")


class TestSleep(TestCase):
    """Sleep priority tests."""

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
    """Activity priority tests."""

    def test_low_steps_is_medium(self):
        health = _health_state(steps_avg_7d=2000, steps_entries_7d=5)
        result = build_health_priority_summary(health, {}, _now())
        items = [i for i in result["items"] if i["key"] == "activity_low"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["message"], "Activity has been low lately")

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
    """Glucose priority tests."""

    def test_severe_low_glucose_is_high(self):
        now = _now()
        health = _health_state(
            latest_glucose=45, latest_glucose_unit="mg/dL",
            last_glucose_entry=(now - timedelta(hours=1)).isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "glucose_severe"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "high")

    def test_in_range_glucose_is_low(self):
        now = _now()
        health = _health_state(
            latest_glucose=100, latest_glucose_unit="mg/dL",
            last_glucose_entry=(now - timedelta(hours=2)).isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "glucose_normal"]
        self.assertEqual(len(items), 1)

    def test_mmol_conversion(self):
        now = _now()
        health = _health_state(
            latest_glucose=2.5, latest_glucose_unit="mmol/L",  # = 45 mg/dL
            last_glucose_entry=(now - timedelta(hours=1)).isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "glucose_severe"]
        self.assertEqual(len(items), 1)


class TestBloodOxygen(TestCase):
    def test_low_spo2_is_high(self):
        now = _now()
        health = _health_state(
            latest_blood_oxygen=87,
            last_blood_oxygen_entry=(now - timedelta(hours=1)).isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "spo2_low"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "high")

    def test_normal_spo2_is_low(self):
        now = _now()
        health = _health_state(
            latest_blood_oxygen=98,
            last_blood_oxygen_entry=(now - timedelta(hours=1)).isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "spo2_normal"]
        self.assertEqual(len(items), 1)


class TestHeartRate(TestCase):
    def test_elevated_hr_is_medium(self):
        now = _now()
        health = _health_state(
            latest_heart_rate=110,
            last_heart_rate_entry=(now - timedelta(hours=1)).isoformat(),
        )
        result = build_health_priority_summary(health, {}, now)
        items = [i for i in result["items"] if i["key"] == "hr_elevated"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "medium")


class TestOrdering(TestCase):
    """Verify items are ordered by priority."""

    def test_high_before_medium_before_low(self):
        now = _now()
        fresh = (now - timedelta(hours=1)).isoformat()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75, last_bp_entry=fresh,
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
        # HIGH should come first
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
            bp_systolic=115, bp_diastolic=75,
            last_bp_entry=(now - timedelta(hours=1)).isoformat(),
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
        fresh = (now - timedelta(hours=1)).isoformat()
        health = _health_state(
            bp_systolic=115, bp_diastolic=75, last_bp_entry=fresh,
            latest_glucose=100, latest_glucose_unit="mg/dL", last_glucose_entry=fresh,
        )
        result = build_health_priority_summary(health, {}, now)
        vitals = [i for i in result["items"] if i["category"] == "vitals"]
        self.assertEqual(len(vitals), 1)
