"""Grounded glucose proxy reasoning — trust tests.

The failure being fixed: asked for "fasting glucose over several months" Beth
said "I don't have the exact fasting data"; then asked for "wake-up" glucose
she returned the all-day 7-day average. Two breaks: (1) no pivot to the closest
grounded proxy, (2) silent substitution of a different metric.

Contracts under test (map to the four required cases):
  1. Exact metric exists            → use it, NOT flagged as a proxy.
  2. Exact absent but proxy exists  → transparently pivot (proxy acknowledged).
  3. No grounded proxy              → honest limitation, never a guess.
  4. Never silently substitute      → wake-up with no proxy ≠ the 7-day average.
"""

from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.health.services import glucose_snapshot as gs
from apps.health.services.glucose_snapshot import (
    build_glucose_proxy_answer,
    render_glucose_proxy_message,
)

User = get_user_model()

_MOD = "apps.health.services.glucose_snapshot"


class _StubUser:
    id = 7


USER = _StubUser()


class GlucoseProxyLogicTests(SimpleTestCase):
    """Proxy-selection branching, isolated from the DB via mocks."""

    def _summary(self, **kw):
        base = {"average_7d": 129, "overnight_avg": None}
        base.update(kw)
        return base

    # ── Case 1: exact metric exists ──────────────────────────────
    def test_fasting_exact_metric_used(self):
        with patch(f"{_MOD}.build_glucose_summary", return_value=self._summary()), \
             patch(f"{_MOD}._context_avg_90d", return_value=(112, 9)):
            ans = build_glucose_proxy_answer(USER, "fasting")
        self.assertTrue(ans["available"])
        self.assertFalse(ans["is_proxy"])
        self.assertEqual(ans["value"], 112)
        self.assertIn("fasting", ans["metric_label"].lower())

    # ── Case 2: exact absent, proxy exists → transparent pivot ───
    def test_fasting_pivots_to_overnight_proxy(self):
        with patch(f"{_MOD}.build_glucose_summary",
                   return_value=self._summary(overnight_avg=118.0)), \
             patch(f"{_MOD}._context_avg_90d", return_value=(None, 0)):
            ans = build_glucose_proxy_answer(USER, "fasting")
        self.assertTrue(ans["available"])
        self.assertTrue(ans["is_proxy"])
        self.assertEqual(ans["value"], 118)
        self.assertIn("overnight", ans["proxy_basis"].lower())

    # ── Case 3: no grounded proxy → honest limitation ────────────
    def test_fasting_no_proxy_unavailable(self):
        with patch(f"{_MOD}.build_glucose_summary",
                   return_value=self._summary(overnight_avg=None)), \
             patch(f"{_MOD}._context_avg_90d", return_value=(None, 0)):
            ans = build_glucose_proxy_answer(USER, "fasting")
        self.assertFalse(ans["available"])
        self.assertIsNone(ans["value"])

    # ── Case 4: never silently substitute the all-day average ────
    def test_wakeup_never_returns_7day_average(self):
        with patch(f"{_MOD}.build_glucose_summary",
                   return_value=self._summary(average_7d=129, overnight_avg=None)), \
             patch(f"{_MOD}._context_avg_90d", return_value=(None, 0)):
            ans = build_glucose_proxy_answer(USER, "wake_up")
        self.assertFalse(ans["available"])
        self.assertNotEqual(ans["value"], 129)
        self.assertIsNone(ans["value"])

    def test_wakeup_uses_overnight(self):
        with patch(f"{_MOD}.build_glucose_summary",
                   return_value=self._summary(overnight_avg=121.0)), \
             patch(f"{_MOD}._context_avg_90d", return_value=(None, 0)):
            ans = build_glucose_proxy_answer(USER, "wake_up")
        self.assertTrue(ans["available"])
        self.assertTrue(ans["is_proxy"])
        self.assertEqual(ans["value"], 121)

    def test_general_uses_7day(self):
        with patch(f"{_MOD}.build_glucose_summary", return_value=self._summary()):
            ans = build_glucose_proxy_answer(USER, "general")
        self.assertTrue(ans["available"])
        self.assertFalse(ans["is_proxy"])
        self.assertEqual(ans["value"], 129)

    def test_no_data_returns_none(self):
        with patch(f"{_MOD}.build_glucose_summary", return_value=None):
            self.assertIsNone(build_glucose_proxy_answer(USER, "fasting"))


class GlucoseProxyRenderTests(SimpleTestCase):
    def test_proxy_message_acknowledges_proxy(self):
        ans = {
            "available": True, "value": 118, "is_proxy": True,
            "metric_label": "overnight glucose average",
            "proxy_basis": "your overnight readings (midnight–6am)",
        }
        msg = render_glucose_proxy_message(ans, "fasting glucose")
        self.assertIn("don't have a strict fasting glucose", msg)
        self.assertIn("proxy", msg.lower())
        self.assertIn("118 mg/dL", msg)

    def test_exact_message_has_no_proxy_language(self):
        ans = {
            "available": True, "value": 112, "is_proxy": False,
            "metric_label": "fasting glucose average (last 90 days)",
            "proxy_basis": None,
        }
        msg = render_glucose_proxy_message(ans, "fasting glucose")
        self.assertIn("112 mg/dL", msg)
        self.assertNotIn("proxy", msg.lower())

    def test_unavailable_is_honest_not_a_guess(self):
        ans = {"available": False, "value": None, "is_proxy": False,
               "metric_label": "", "proxy_basis": None}
        msg = render_glucose_proxy_message(ans, "wake-up glucose")
        self.assertIn("won't guess", msg)
        self.assertIn("wake-up glucose", msg)

    def test_none_answer_renders_none(self):
        self.assertIsNone(render_glucose_proxy_message(None, "fasting glucose"))


class GlucoseConceptRoutingTests(SimpleTestCase):
    """Router pure functions — concept detection + deterministic routing."""

    def test_concept_detection(self):
        from apps.ai.deterministic_router import _glucose_concept
        self.assertEqual(
            _glucose_concept(
                "approximate fasting blood glucose over the last several months"),
            "fasting")
        self.assertEqual(
            _glucose_concept("average blood glucose shortly after i wake up"),
            "wake_up")
        self.assertEqual(
            _glucose_concept("how is my glucose this week"), "general")

    def test_fasting_and_wakeup_queries_route_deterministically(self):
        from apps.ai.deterministic_router import _match_glucose_query
        self.assertTrue(_match_glucose_query(
            "approximate fasting blood glucose over the last several months"))
        self.assertTrue(_match_glucose_query(
            "average blood glucose shortly after i wake up"))


class GlucoseProxyDbExactTests(TestCase):
    """Real-DB check that fasting-tagged readings produce the exact metric."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="gproxy@test.com", password="x" * 20)
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_fasting_context_readings_give_exact_metric(self):
        now = timezone.now()
        for v in (104, 110, 116):
            gs_obj = __import__(
                "apps.health.models", fromlist=["GlucoseEntry"]).GlucoseEntry
            gs_obj.objects.create(
                user=self.user, value=Decimal(str(v)), unit="mg/dL",
                context="fasting", source="manual", recorded_at=now,
            )
        ans = build_glucose_proxy_answer(self.user, "fasting")
        self.assertIsNotNone(ans)
        self.assertTrue(ans["available"])
        self.assertFalse(ans["is_proxy"])
        self.assertEqual(ans["value"], 110)  # mean(104,110,116)
        self.assertEqual(ans["sample_size"], 3)
