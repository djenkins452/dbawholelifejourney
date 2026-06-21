"""CoS recommendation tracking + effectiveness — outcome engine (2026-06-21).

Beth records the constraint she steers Danny toward (GuidanceItem, no schema
change) and later judges whether the metric moved. Grounded; honest when the
before/after metric isn't clean.
"""
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.ai import deterministic_router as dr
from apps.ai import cos_recommendations as cr
from apps.core.cos_briefing.executive_state import ExecutiveStateSignal

User = get_user_model()


def _opp(domain="sleep"):
    return ExecutiveStateSignal(
        domain=domain, lens="decline", direction="declining", magnitude=None,
        confidence="high", title=f"{domain} slipping",
        message=f"Your {domain} is trending down.", evidence=[],
        source=f"{domain}_state", leverage=True)


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class Matchers(SimpleTestCase):
    def test_effectiveness_matcher(self):
        for q in ("is your recommendation working", "is the advice working",
                  "has the recommendation been effective"):
            self.assertTrue(dr._match_rec_effectiveness_query(q), q)

    def test_list_matcher(self):
        for q in ("what advice have you given me lately",
                  "what have you been telling me", "what have you recommended"):
            self.assertTrue(dr._match_recommendation_list_query(q), q)

    def test_no_false_positives(self):
        for q in ("what is my weight", "how did i sleep", "what should i do next"):
            self.assertFalse(dr._match_rec_effectiveness_query(q), q)
            self.assertFalse(dr._match_recommendation_list_query(q), q)


class Tracking(TestCase):
    def setUp(self):
        self.user = _user("rec@test.com")

    def _patch_top(self, domain="sleep"):
        return (patch("apps.core.cos_briefing.executive_state."
                      "build_executive_state_signals", return_value=[]),
                patch("apps.core.cos_briefing.executive_state."
                      "select_executive_lenses",
                      return_value={"biggest_opportunity": _opp(domain),
                                    "biggest_decline": _opp(domain)}))

    def test_record_creates_with_baseline(self):
        p1, p2 = self._patch_top("sleep")
        with p1, p2, patch.object(cr, "_current_metric",
                                  return_value=(6.0, "h", False)):
            rec = cr.record_top_recommendation(self.user)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.guidance_type, "cos_constraint")
        self.assertEqual(rec.module, "sleep")
        self.assertEqual(rec.evidence["baseline_value"], 6.0)
        self.assertIn("baseline_date", rec.evidence)

    def test_record_is_idempotent_keeps_baseline(self):
        p1, p2 = self._patch_top("sleep")
        with p1, p2, patch.object(cr, "_current_metric",
                                  return_value=(6.0, "h", False)):
            r1 = cr.record_top_recommendation(self.user)
        p3, p4 = self._patch_top("sleep")
        with p3, p4, patch.object(cr, "_current_metric",
                                  return_value=(6.5, "h", False)):  # later value
            r2 = cr.record_top_recommendation(self.user)
        self.assertEqual(r1.pk, r2.pk)                 # same record
        self.assertEqual(r2.evidence["baseline_value"], 6.0)  # original baseline

    def _make_rec(self, domain, baseline, unit, lower_better, days_ago):
        from apps.core.ai_guidance.models import GuidanceItem
        return GuidanceItem.objects.create(
            user=self.user, title=f"Focus: {domain}", message="x",
            guidance_type="cos_constraint", source="composite", module=domain,
            priority=2, evidence={
                "domain": domain, "baseline_value": baseline, "unit": unit,
                "lower_better": lower_better,
                "baseline_date": (timezone.now().date()
                                  - timedelta(days=days_ago)).isoformat()})

    def test_evaluate_improving(self):
        self._make_rec("weight", 310.0, " lb", True, 21)
        with patch.object(cr, "_current_metric", return_value=(298.3, " lb", True)):
            out = cr.evaluate_active_recommendations(self.user)
        print(f"\n>>>REC-eval: {out}\n<<<")
        self.assertIn("21 days ago", out)
        self.assertIn("310.0 lb", out)
        self.assertIn("298.3 lb", out)
        self.assertIn("working", out.lower())

    def test_evaluate_flat_prompts_change(self):
        self._make_rec("weight", 300.0, " lb", True, 14)
        with patch.object(cr, "_current_metric", return_value=(300.0, " lb", True)):
            out = cr.evaluate_active_recommendations(self.user)
        self.assertIn("hasn't moved", out.lower())
        self.assertIn("different approach", out.lower())

    def test_evaluate_no_metric_is_honest(self):
        from apps.core.ai_guidance.models import GuidanceItem
        GuidanceItem.objects.create(
            user=self.user, title="Focus: sleep", message="x",
            guidance_type="cos_constraint", module="sleep", source="composite",
            evidence={"domain": "sleep", "baseline_date":
                      timezone.now().date().isoformat()})  # no baseline_value
        with patch.object(cr, "_current_metric", return_value=None):
            out = cr.evaluate_active_recommendations(self.user)
        self.assertIn("don't have a clean before/after", out.lower())

    def test_evaluate_none_when_no_recs(self):
        self.assertIsNone(cr.evaluate_active_recommendations(self.user))

    def test_list(self):
        self._make_rec("sleep", 6.0, "h", False, 5)
        out = cr.list_recommendations(self.user)
        self.assertIn("sleep", out)
        self.assertIn("steering you toward", out.lower())

    def test_list_empty_is_honest(self):
        self.assertIn("haven't locked in", cr.list_recommendations(self.user).lower())

    def test_routes(self):
        self._make_rec("weight", 305.0, " lb", True, 10)
        with patch.object(cr, "_current_metric", return_value=(298.0, " lb", True)):
            res = dr.classify_and_route("is your recommendation working", self.user)
        self.assertEqual(res.route_name, "rec_effectiveness_query")
        self.assertIn("working", res.response.lower())
        res2 = dr.classify_and_route("what advice have you given me", self.user)
        self.assertEqual(res2.route_name, "recommendation_list_query")
