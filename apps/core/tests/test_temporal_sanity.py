# ==============================================================================
# File: apps/core/tests/test_temporal_sanity.py
# Description: Defect Class 1 BLOCKER — Temporal Sanity. A reading timestamped in the
#   FUTURE (sync/clock artifact) must be flagged, never reported as a real current
#   time. Origin: Beth reported glucose at 21:02 when it was ~20:05.
# ==============================================================================
from datetime import datetime, timedelta, timezone as _tz

from django.test import SimpleTestCase, TestCase

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



class GlucoseFactTemporalGuardTests(TestCase):
    """CANONICAL-PATH temporal safety (2026-07-23).

    `last_glucose_reading` now DELEGATES to `glucose_queries.latest`; temporal safety
    is owned by the PLATFORM layer (`truth/integrity.attach`), not by the snapshot
    surface. These tests seed a REAL future-dated reading instead of mocking SAE state,
    and assert the INVARIANT — impossible time flagged and dropped, the value never
    presented as a sound current reading — not one implementation's wording.
    """

    def _user(self):
        from django.conf import settings
        from django.contrib.auth import get_user_model
        from apps.users.models import TermsAcceptance
        U = get_user_model()
        u = U.objects.create_user(email="temporal@example.com", password="x")
        TermsAcceptance.objects.create(
            user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        u.preferences.has_completed_onboarding = True
        u.preferences.save()
        return u

    def _future_reading(self):
        from decimal import Decimal
        from django.utils import timezone
        from apps.health.models import GlucoseEntry
        u = self._user()
        GlucoseEntry.objects.create(user=u, value=Decimal("95"), unit="mg/dL",
                                    recorded_at=timezone.now() + timedelta(hours=1))
        return get_foundational_health_facts(
            u, ["last_glucose_reading"])["last_glucose_reading"]

    def test_future_glucose_timestamp_is_dropped_and_flagged(self):
        from apps.core.truth import integrity as I
        fact = self._future_reading()
        self.assertTrue(I.failed(fact))                 # flagged as impossible
        self.assertNotIn("recorded_at", fact)           # impossible time dropped
        self.assertEqual(fact["value"], 95)             # the value still stands

    def test_future_reading_answer_investigates_instead_of_asserting(self):
        from apps.ai.chatgpt_cos.foundational_facts import format_fact_sentence
        fact = self._future_reading()
        self.assertNotIn("recorded_at", fact)
        answer = format_fact_sentence("last_glucose_reading", fact).lower()
        # Must NOT be the plain confident sentence.
        self.assertNotEqual(answer.strip(),
                            "your last glucose reading was 95 mg/dl.")
        self.assertTrue(answer.strip())
