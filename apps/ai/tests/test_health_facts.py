# ==============================================================================
# File: apps/ai/tests/test_health_facts.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for focused foundational health facts (Option A fix)
# ==============================================================================
"""
Proves the focused foundational-health-facts tool:
* tiny payload (< 2000 chars) — never hits the 8000-char dispatcher cap;
* current weight + glucose survive tool dispatch (the original failure);
* missing values are structured unknown; 0 is a valid value;
* the focused tool is advertised to the model, and get_domain_state's
  description steers scalar questions to it.
"""

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services import (
    SUPPORTED_FACTS,
    dispatch_tool_call,
    get_foundational_health_facts,
    get_tool_schemas,
)

User = get_user_model()

_GMS = "apps.core.ai_state.state_engine.get_module_state"

_FAKE_STATE = {
    "health": {
        "weight_current": 285.9, "weight_unit": "lb", "weight_trend": "down",
        "last_weight_entry": "2026-06-24T08:00:00+00:00",
        "latest_glucose": 110.0, "latest_glucose_unit": "mg/dL",
        "last_glucose_entry": "2026-06-24T07:00:00+00:00", "glucose_avg_7d": 124,
        "sleep_avg_hours_7d": 6.7, "sleep_trend": "stable",
        "last_sleep_entry": "2026-06-24",
        # weight_change_30d intentionally absent -> unknown
    },
    "medicine": {"active_medications": ["Metformin", "Valsartan"],
                 "medication_count": 2},
    "nutrition": {"daily_calories": 0.0, "calorie_target": 2000,
                  "daily_protein_g": 136.0, "protein_target": 180},
}


def _fake_module_state(user, module, allow_rebuild=False):
    return _FAKE_STATE.get(module, {})


class FoundationalHealthFactsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="facts@example.com", password="x")

    # 1. tiny payload
    def test_full_facts_payload_under_2000_chars(self):
        with mock.patch(_GMS, side_effect=_fake_module_state):
            facts = get_foundational_health_facts(self.user)  # all keys
        self.assertLess(len(json.dumps(facts)), 2000)

    # 2. current weight survives dispatch (the original failure)
    def test_current_weight_survives_dispatch(self):
        with mock.patch(_GMS, side_effect=_fake_module_state):
            env = dispatch_tool_call(
                self.user, "get_foundational_health_facts",
                {"keys": ["current_weight"]},
            )
        self.assertTrue(env["ok"])
        res = env["result"]
        self.assertIsNone(res.get("_truncated"))
        self.assertEqual(res["current_weight"]["value"], 285.9)
        self.assertEqual(res["current_weight"]["unit"], "lb")
        self.assertEqual(res["current_weight"]["source"],
                         "SAE.health.weight_current")

    # 3. glucose survives dispatch
    def test_glucose_survives_dispatch(self):
        with mock.patch(_GMS, side_effect=_fake_module_state):
            env = dispatch_tool_call(
                self.user, "get_foundational_health_facts",
                {"keys": ["last_glucose_reading"]},
            )
        res = env["result"]
        self.assertEqual(res["last_glucose_reading"]["value"], 110.0)
        self.assertEqual(res["last_glucose_reading"]["unit"], "mg/dL")

    # 4. missing values -> structured unknown
    def test_missing_value_is_structured_unknown(self):
        with mock.patch(_GMS, side_effect=_fake_module_state):
            facts = get_foundational_health_facts(
                self.user, ["weight_30_day_change"])
        self.assertEqual(facts["weight_30_day_change"]["status"], "unknown")
        self.assertIn("reason", facts["weight_30_day_change"])
        self.assertNotIn("data size", facts["weight_30_day_change"]["reason"])

    def test_zero_is_a_valid_value_not_unknown(self):
        with mock.patch(_GMS, side_effect=_fake_module_state):
            facts = get_foundational_health_facts(self.user, ["calories_today"])
        self.assertEqual(facts["calories_today"]["value"], 0.0)
        self.assertNotIn("status", facts["calories_today"])

    def test_medications_from_canonical_state(self):
        with mock.patch(_GMS, side_effect=_fake_module_state):
            facts = get_foundational_health_facts(self.user, ["current_medications"])
        self.assertEqual(facts["current_medications"]["value"],
                         ["Metformin", "Valsartan"])
        self.assertEqual(facts["current_medications"]["count"], 2)

    def test_unsupported_fact_is_explicit(self):
        facts = get_foundational_health_facts(self.user, ["telepathy_level"])
        self.assertEqual(facts["telepathy_level"]["status"], "unsupported_fact")

    # 5. model receives the focused tool schema
    def test_focused_tool_advertised_to_model(self):
        names = {s["function"]["name"] for s in get_tool_schemas(enabled_only=True)}
        self.assertIn("get_foundational_health_facts", names)
        schema = next(s for s in get_tool_schemas()
                      if s["function"]["name"] == "get_foundational_health_facts")
        enum = schema["function"]["parameters"]["properties"]["keys"]["items"]["enum"]
        for k in ("current_weight", "last_glucose_reading", "current_medications"):
            self.assertIn(k, enum)
        self.assertEqual(set(enum), set(SUPPORTED_FACTS))

    # 6. domain tool steers scalar questions to the focused tool
    def test_domain_state_description_points_to_focused_tool(self):
        schema = next(s for s in get_tool_schemas()
                      if s["function"]["name"] == "get_domain_state")
        self.assertIn("get_foundational_health_facts",
                      schema["function"]["description"])

    # 7. no truncation for foundational facts (even all keys)
    def test_no_truncation_for_all_foundational_facts(self):
        with mock.patch(_GMS, side_effect=_fake_module_state):
            env = dispatch_tool_call(
                self.user, "get_foundational_health_facts",
                {"keys": list(SUPPORTED_FACTS)},
            )
        self.assertTrue(env["ok"])
        self.assertIsNone(env["result"].get("_truncated"))
