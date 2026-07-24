# ==============================================================================
# File: apps/ai/tests/test_foundation_validation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Foundation fact FAST PATH — deterministic, no tools, no agentic loop.
# ==============================================================================
"""
Validates the foundational-fact fast path:

    classify -> get_foundational_health_facts -> plain _call_api to phrase
    -> deterministic payload fallback if _call_api fails.

Success criteria: no _call_api_with_tools, no tools, no tool_choice, no legacy
Beth, exact fact returned (never empty).
"""

import datetime as _dt
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.chatgpt_cos.foundational_facts import (
    answer_foundational_fact,
    classify_foundational_fact,
    format_fact_sentence,
)

User = get_user_model()

_GMS = "apps.core.ai_state.state_engine.get_module_state"
_CALL_API = "apps.ai.services.ai_service._call_api"
_CALL_API_TOOLS = "apps.ai.services.ai_service._call_api_with_tools"

_FAKE_STATE = {
    "health": {
        "weight_current": 298.3, "weight_unit": "lb", "weight_trend": "decreasing",
        "last_weight_entry": "2026-04-07T16:00:00+00:00",
        "latest_glucose": 133.0, "latest_glucose_unit": "mg/dL",
        "last_glucose_entry": "2026-04-07T20:43:35+00:00",
        "sleep_avg_hours_7d": 6.7, "sleep_trend": "decreasing",
        "last_sleep_entry": "2026-04-07",
        "bp_systolic": 111, "bp_diastolic": 72,
        "last_bp_entry": "2026-04-07T08:55:45+00:00",
    },
    "medicine": {"active_medications": ["Metformin HCL ER", "Valsartan"],
                 "medication_count": 2},
    "nutrition": {"daily_calories": 1850.0, "calorie_target": 2000,
                  "daily_protein_g": 142.0, "protein_target": 180,
                  "last_food_entry": "2026-04-07"},
}

# prompt -> (fact key, substring that must appear in the deterministic answer)
PROMPTS = [
    ("What is my current weight?",                "current_weight",       "298.3"),
    ("What was my last glucose reading?",         "last_glucose_reading", "133"),
    ("What medications am I currently taking?",   "current_medications",  "Metformin"),
    ("How many calories have I consumed today?",  "calories_today",       "1,850"),
    ("How much protein have I consumed today?",   "protein_today",        "142"),
    # average_sleep_7d now delegates to get_history(last_7_days).average — a REAL
    # window, resolved at runtime (see _needle), not the mocked SAE value.
    ("What's my average sleep this week?",        "average_sleep_7d",     None),
    ("What was my last blood pressure reading?",   "last_blood_pressure_reading", "111/72"),
    # latest_meal_logged now delegates to NutritionQueries.last_entry, so the answer
    # is the REAL latest entry date (seeded at today) — resolved at runtime below.
    ("What was the last meal I logged?",           "latest_meal_logged",   None),
]


def _fake_module_state(user, module, allow_rebuild=False):
    return _FAKE_STATE.get(module, {})


class ClassifierTests(TestCase):
    def test_maps_each_foundational_prompt(self):
        for prompt, key, _ in PROMPTS:
            self.assertEqual(classify_foundational_fact(prompt), key, prompt)

    def test_non_foundational_returns_none(self):
        for prompt in ("How am I doing overall?",
                       "Help me think through my week.",
                       "What patterns do you see in my health?",
                       "What should I focus on today?"):
            self.assertIsNone(classify_foundational_fact(prompt), prompt)


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class FastPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="ff@example.com", password="x")
        cls.user.preferences.use_chatgpt_cos = True
        cls.user.preferences.save()
        # current_medications now reads the canonical Medicine Domain Truth (live from the
        # models), not the SAE snapshot — so a real PRESCRIPTION record is required.
        from datetime import date
        from apps.health.models import Intake
        Intake.objects.create(user=cls.user, name="Metformin", dose="500mg",
                              frequency="daily", start_date=date(2026, 1, 1),
                              intake_status="active", intake_type="medication",
                              category="prescription")
        # Same migration, continued (2026-07-22): `current_weight` and the per-day macro
        # facts now read the canonical date-scoped authority (live from the models)
        # instead of the SAE snapshot, so they need REAL records — a mocked SAE state no
        # longer feeds them. See docs/WLJ_WEIGHT_YESTERDAY_INVESTIGATION.md.
        from decimal import Decimal

        from django.utils import timezone as _tz

        from apps.core.utils import get_user_today
        from apps.health.models import FoodEntry, WeightEntry
        _today = get_user_today(cls.user)
        WeightEntry.objects.create(
            user=cls.user, value=Decimal("298.3"), unit="lb",
            recorded_at=_tz.make_aware(_dt.datetime.combine(_today, _dt.time(6, 30))))
        FoodEntry.objects.create(
            user=cls.user, food_name="Test day", serving_size=Decimal("1"),
            serving_unit="serving", total_calories=Decimal("1850"),
            total_protein_g=Decimal("142"), logged_date=_today, status="active")
        # Same migration, continued (2026-07-23, F6): `last_blood_pressure_reading` is
        # now a COMPOSITE PROJECTION over the canonical bp_systolic/bp_diastolic
        # history metrics, so it needs a REAL reading — a mocked SAE state no longer
        # feeds it. Systolic and diastolic must share ONE observation; the projection
        # refuses to compose components from different readings.
        # Same migration, continued (2026-07-23, F2): `last_glucose_reading` now
        # delegates to glucose_queries.latest, so it needs a REAL reading.
        from apps.health.models import BloodPressureEntry, GlucoseEntry
        GlucoseEntry.objects.create(
            user=cls.user, value=Decimal("133"), unit="mg/dL",
            recorded_at=_tz.now() - _dt.timedelta(minutes=20))
        # average_sleep_7d delegates to get_history(sleep, last_7_days) — seed a window.
        from apps.health.models import SleepEntry
        for _off in (1, 2, 3):
            _night = _today - _dt.timedelta(days=_off)
            SleepEntry.objects.create(
                user=cls.user, sleep_date=_night,
                bedtime=_tz.make_aware(_dt.datetime.combine(_night - _dt.timedelta(days=1), _dt.time(22, 30))),
                wake_time=_tz.make_aware(_dt.datetime.combine(_night, _dt.time(6, 30))),
                total_duration_minutes=480, asleep_duration_minutes=445,
                sleep_efficiency=Decimal("92.7"), quality_rating="good")
        BloodPressureEntry.objects.create(
            user=cls.user, systolic=111, diastolic=72, pulse=64,
            recorded_at=_tz.make_aware(_dt.datetime.combine(_today, _dt.time(6, 30))))

    def _needle(self, key, needle):
        """Delegated keys answer from REAL records, so their expected value is
        resolved at runtime rather than pinned to a mocked snapshot value."""
        if needle is None and key == "latest_meal_logged":
            from apps.core.utils import get_user_today
            return get_user_today(self.user).isoformat()
        if needle is None and key == "average_sleep_7d":
            from apps.ai.cos_services.domain_history import get_domain_history
            avg = get_domain_history(self.user, "health", "sleep",
                                     period="last_7_days").get("average")
            # the deterministic sentence humanizes the hours value; assert the integer part
            return str(int(avg)) if avg is not None else ""
        return needle

    def test_fast_path_never_uses_tool_loop(self):
        # The fast path NEVER uses the agentic tool loop. It is EITHER the plain
        # _call_api phrasing OR — for timestamped/clinical facts (Truth Consistency) —
        # the deterministic sentence (LLM bypassed so the value answer can't diverge
        # from a follow-up that reads the same struct).
        for prompt, key, needle in PROMPTS:
            needle = self._needle(key, needle)
            with self.subTest(prompt=prompt), \
                 mock.patch(_GMS, side_effect=_fake_module_state), \
                 mock.patch(_CALL_API, return_value="Phrased answer."), \
                 mock.patch(_CALL_API_TOOLS,
                            side_effect=AssertionError("tool loop used")) as cwt:
                out = answer_foundational_fact(self.user, prompt)

            self.assertIsNotNone(out, prompt)
            self.assertEqual(out["fact_key"], key)
            self.assertEqual(out["tools_advertised"], [])
            self.assertEqual(out["fast_path"], "foundational_fact")
            self.assertFalse(cwt.called)                     # NEVER the tool loop
            self.assertTrue(out["answer"])                   # never empty
            # Either LLM-phrased ("Phrased answer.") or the deterministic fact sentence.
            self.assertTrue(out["answer"] == "Phrased answer." or needle in out["answer"],
                            f"{prompt}: {out['answer']!r}")

    def test_deterministic_fallback_when_call_api_returns_none(self):
        for prompt, key, needle in PROMPTS:
            needle = self._needle(key, needle)
            with self.subTest(prompt=prompt), \
                 mock.patch(_GMS, side_effect=_fake_module_state), \
                 mock.patch(_CALL_API, return_value=None):
                out = answer_foundational_fact(self.user, prompt)
            self.assertTrue(out["answer"])                  # never empty
            self.assertIn(needle, out["answer"])            # exact fact present

    def test_deterministic_fallback_when_call_api_raises(self):
        with mock.patch(_GMS, side_effect=_fake_module_state), \
             mock.patch(_CALL_API, side_effect=RuntimeError("boom")):
            out = answer_foundational_fact(self.user, "What is my current weight?")
        self.assertIn("298.3", out["answer"])

    def test_non_foundational_prompt_returns_none(self):
        self.assertIsNone(
            answer_foundational_fact(self.user, "How am I doing overall?"))

    def test_generate_takes_fast_path_not_tool_loop(self):
        from apps.ai.chatgpt_cos.service import ChatGPTCoSService
        from apps.ai.models import AssistantConversation

        conv = AssistantConversation.get_or_create_active(self.user)
        with mock.patch(_GMS, side_effect=_fake_module_state), \
             mock.patch("apps.core.ai_state.state_engine.get_user_state",
                        return_value={}), \
             mock.patch(_CALL_API, return_value="Your weight is 298.3 lb."), \
             mock.patch(_CALL_API_TOOLS,
                        side_effect=AssertionError("tool loop used")):
            result = ChatGPTCoSService(self.user).generate(
                conv, "What is my current weight?")
        self.assertEqual(result.get("fast_path"), "foundational_fact")
        # weight carries a timestamp → deterministic answer (LLM bypassed); the value
        # is still present and correct.
        self.assertIn("298.3", result["answer"])
        self.assertIsNone(result.get("empty_reason"))


class FormatFactSentenceTests(TestCase):
    def test_each_key_surfaces_value(self):
        cases = {
            "current_weight": ({"value": 298.3, "unit": "lb",
                                "trend": "decreasing"}, "298.3"),
            "last_glucose_reading": ({"value": 133.0, "unit": "mg/dL"}, "133"),
            "current_medications": ({"value": ["Metformin", "Valsartan"],
                                     "count": 2}, "Metformin"),
            "calories_today": ({"value": 1850.0, "target": 2000}, "1,850"),
            "protein_today": ({"value": 142.0, "target": 180}, "142"),
            "sleep_last_night": ({"value": 6.7, "unit": "hours",
                                  "trend": "decreasing"}, "6.7"),
            "average_sleep_7d": ({"value": 6.7, "unit": "hours"}, "6.7"),
            "sleep_trend": ({"value": "decreasing"}, "decreasing"),
            "last_blood_pressure_reading": ({"value": 111, "diastolic": 72},
                                            "111/72"),
            "latest_meal_logged": ({"value": "2026-04-07"}, "2026-04-07"),
        }
        for key, (fact, needle) in cases.items():
            self.assertIn(needle, format_fact_sentence(key, fact), key)

    def test_unknown_status_is_explicit(self):
        s = format_fact_sentence("current_weight",
                                 {"status": "unknown", "reason": "x"})
        self.assertIn("don't have", s)

    def test_zero_is_a_valid_value(self):
        # 0 is a real total (no food logged), rendered as a clean integer.
        s = format_fact_sentence("calories_today", {"value": 0.0, "target": 2000})
        self.assertIn("Calories: 0", s)            # 0 is a real total, clean integer
        self.assertNotIn("0.0", s)
        self.assertNotIn("haven't", s.lower())
