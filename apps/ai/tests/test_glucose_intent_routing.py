"""Glucose intent routing — Phase 2a DIAGNOSTIC (2026-06-18).

Trust bug: "why is my fasting glucose elevated?" matched the glucose STATUS
route (glucose token + "fasting"/"overnight" summary anchor) and returned a bare
number. Diagnostic (cause-seeking) questions must route to
`glucose_diagnostic_query` and answer with a GROUNDED explanation (trend
direction, overnight/fasting proxy, time-in-range, sample-size caveat) or honest
uncertainty — never a bare number, never speculative physiology. Mirrors the
sleep diagnostic split; the shared `classify_query_intent` is unchanged in shape
(only additive 'driving' cues), proving the architecture is reusable.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.ai import deterministic_router as dr

User = get_user_model()

_SPECULATIVE = ("stress", "hormone", "cortisol", "dawn phenomenon", "dawn effect",
                "probably", "might be", "could be due to", "liver dump")


class GlucoseDiagnosticMatchers(SimpleTestCase):
    def test_diagnostic_detected(self):
        for q in (
            "why is my fasting glucose elevated",
            "what's causing my blood sugar to be high overnight",
            "why is my glucose still high",
            "what is driving my fasting glucose",
        ):
            self.assertTrue(dr._is_glucose_diagnostic_request(q), q)
            self.assertTrue(dr._match_glucose_diagnostic_query(q), q)
            # Diagnostic must be EXCLUDED from both status matchers.
            self.assertFalse(dr._match_glucose_query(q), q)
            self.assertFalse(dr._match_glucose_latest_query(q), q)

    def test_status_still_matches(self):
        for q in (
            "what's my glucose this week",
            "glucose average",
            "my blood sugar",
            "what is my estimated a1c",
        ):
            self.assertFalse(dr._is_glucose_diagnostic_request(q), q)
            self.assertTrue(dr._match_glucose_query(q), q)
            self.assertFalse(dr._match_glucose_diagnostic_query(q), q)

    def test_latest_still_matches(self):
        for q in ("what was my last glucose reading", "glucose right now"):
            self.assertFalse(dr._is_glucose_diagnostic_request(q), q)
            self.assertTrue(dr._match_glucose_latest_query(q), q)

    def test_non_glucose_diagnostic_not_matched(self):
        # A diagnostic question about another domain must not match glucose.
        self.assertFalse(dr._is_glucose_diagnostic_request("why is my sleep poor"))
        self.assertFalse(dr._is_glucose_diagnostic_request("what's causing my low energy"))


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class GlucoseDiagnosticHandler(TestCase):
    def setUp(self):
        self.user = _user("gd@test.com")

    def _reading(self, value, days_ago, hour):
        from apps.health.models import GlucoseEntry
        ts = (timezone.now() - timedelta(days=days_ago)).replace(
            hour=hour, minute=0, second=0, microsecond=0)
        GlucoseEntry.objects.create(user=self.user, value=value, recorded_at=ts)

    def _seed_worsening_overnight(self):
        # Recent 6 days, overnight (3-4am), high → 7d avg high + overnight proxy.
        for d in range(0, 6):
            self._reading(150, d, 3)
            self._reading(150, d, 4)
        # 14 older days (10-23 ago), daytime, lower → 30d avg lower → worsening.
        for d in range(10, 24):
            self._reading(118, d, 14)

    def test_grounded_explanation_fasting_elevated(self):
        self._seed_worsening_overnight()
        out = dr._handle_glucose_diagnostic_query(
            self.user, "why is my fasting glucose elevated")
        print(f"\n>>>GLU-DIAG-1: {out}\n<<<")
        self.assertIn("Looking at your glucose data", out)
        self.assertIn("upward", out.lower())              # grounded trend direction
        self.assertIn("150", out)                          # overnight/fasting proxy
        self.assertIn("in range", out.lower())             # time-in-range
        for bad in _SPECULATIVE:
            self.assertNotIn(bad, out.lower())             # no invented physiology

    def test_grounded_explanation_high_overnight(self):
        self._seed_worsening_overnight()
        out = dr._handle_glucose_diagnostic_query(
            self.user, "what's causing my blood sugar to be high overnight")
        print(f"\n>>>GLU-DIAG-2: {out}\n<<<")
        self.assertIn("overnight", out.lower())
        self.assertIn("150", out)
        for bad in _SPECULATIVE:
            self.assertNotIn(bad, out.lower())

    def test_no_data_is_honest(self):
        out = dr._handle_glucose_diagnostic_query(
            self.user, "why is my fasting glucose elevated")
        print(f"\n>>>GLU-DIAG-NODATA: {out}\n<<<")
        self.assertIn("don't have enough grounded glucose signal", out.lower())
        for bad in _SPECULATIVE:
            self.assertNotIn(bad, out.lower())

    def test_thin_data_declines_to_attribute_cause(self):
        # Some readings but < 14 in 30d → no trend signal → honest, no causation.
        for d in range(0, 6):
            self._reading(132, d, 3)   # 6 overnight readings, no 14-in-30d trend
        out = dr._handle_glucose_diagnostic_query(
            self.user, "why is my fasting glucose elevated")
        print(f"\n>>>GLU-DIAG-THIN: {out}\n<<<")
        self.assertIn("don't have a strong enough trend signal", out.lower())
        self.assertNotIn("upward", out.lower())            # never claims a direction
        for bad in _SPECULATIVE:
            self.assertNotIn(bad, out.lower())


class GlucoseDiagnosticRouting(TestCase):
    def setUp(self):
        self.user = _user("gdr@test.com")

    def _reading(self, value, days_ago, hour):
        from apps.health.models import GlucoseEntry
        ts = (timezone.now() - timedelta(days=days_ago)).replace(
            hour=hour, minute=0, second=0, microsecond=0)
        GlucoseEntry.objects.create(user=self.user, value=value, recorded_at=ts)

    def _seed(self):
        for d in range(0, 6):
            self._reading(150, d, 3)
            self._reading(150, d, 4)
        for d in range(10, 24):
            self._reading(118, d, 14)

    def test_diagnostic_routes_not_to_status(self):
        self._seed()
        res = dr.classify_and_route("why is my fasting glucose elevated", self.user)
        self.assertIsNotNone(res)
        self.assertEqual(res.route_name, "glucose_diagnostic_query")
        resp = (res.response or "")
        # Not a bare number / status summary — a grounded explanation.
        self.assertIn("Looking at your glucose data", resp)
        for bad in _SPECULATIVE:
            self.assertNotIn(bad, resp.lower())

    def test_overnight_diagnostic_routes_deterministically(self):
        self._seed()
        res = dr.classify_and_route(
            "what's causing my blood sugar to be high overnight", self.user)
        self.assertIsNotNone(res)
        self.assertEqual(res.route_name, "glucose_diagnostic_query")

    def test_status_glucose_still_works(self):
        self._seed()
        res = dr.classify_and_route("what's my glucose this week", self.user)
        self.assertIsNotNone(res)
        self.assertEqual(res.route_name, "glucose_query")
