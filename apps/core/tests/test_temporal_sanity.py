# ==============================================================================
# File: apps/core/tests/test_temporal_sanity.py
# Description: Defect Class 1 BLOCKER — Temporal Sanity. A reading timestamped in the
#   FUTURE (sync/clock artifact) must be flagged, never reported as a real current
#   time. Origin: Beth reported glucose at 21:02 when it was ~20:05.
# ==============================================================================
from datetime import datetime, timedelta, timezone as _tz

from django.test import SimpleTestCase

from apps.core.truth import temporal as T
from apps.ai.cos_services.health_facts import get_foundational_health_facts
from unittest import mock


class ValidateTimestampTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 28, 20, 5, tzinfo=_tz.utc)

    def test_future_timestamp_flagged(self):
        future = self.now + timedelta(hours=1)            # 21:05 vs 20:05
        v = T.validate_timestamp(future, self.now)
        self.assertEqual(v["verdict"], T.FUTURE)
        self.assertFalse(v["ok"])
        self.assertIn("future", v["message"])
        self.assertTrue(T.is_future(future, self.now))

    def test_small_skew_is_ok(self):
        self.assertEqual(
            T.validate_timestamp(self.now + timedelta(minutes=2), self.now)["verdict"],
            T.OK)

    def test_past_is_ok_and_iso_string_parses(self):
        v = T.validate_timestamp("2026-06-28T18:00:00+00:00", self.now)
        self.assertEqual(v["verdict"], T.OK)

    def test_unparseable(self):
        self.assertEqual(T.validate_timestamp("not-a-date", self.now)["verdict"],
                         T.UNPARSEABLE)


_GMS = "apps.core.ai_state.state_engine.get_module_state"


class GlucoseFactTemporalGuardTests(SimpleTestCase):
    def test_future_glucose_timestamp_is_dropped_and_flagged(self):
        from django.utils import timezone
        future_iso = (timezone.now() + timedelta(hours=1)).isoformat()
        state = {"latest_glucose": 95, "latest_glucose_unit": "mg/dL",
                 "last_glucose_entry": future_iso}
        with mock.patch(_GMS, return_value=state):
            fact = get_foundational_health_facts(None, ["last_glucose_reading"])["last_glucose_reading"]
        self.assertIn("temporal_warning", fact)            # flagged
        self.assertNotIn("recorded_at", fact)              # impossible time dropped
        self.assertEqual(fact["value"], 95)                # the value still stands

    def test_sae_future_warning_is_surfaced_in_the_answer(self):
        # SAE removed the impossible time and left a warning — Beth must SAY it.
        from apps.ai.chatgpt_cos.foundational_facts import format_fact_sentence
        state = {"latest_glucose": 95, "latest_glucose_unit": "mg/dL",
                 "last_glucose_entry": None,
                 "last_glucose_entry_warning": "That timestamp appears to be in the "
                 "future, which shouldn't be possible. There may be a synchronization "
                 "or timezone issue, so the reading's time is unconfirmed."}
        with mock.patch(_GMS, return_value=state):
            fact = get_foundational_health_facts(None, ["last_glucose_reading"])["last_glucose_reading"]
        self.assertNotIn("recorded_at", fact)
        answer = format_fact_sentence("last_glucose_reading", fact).lower()
        self.assertIn("future", answer)
        self.assertIn("shouldn't be possible", answer)
