# ==============================================================================
# File: apps/ai/tests/test_whole_life_intelligence.py
# Description: Whole-Life Executive Understanding, Stage 1. WLJ already COMPUTES the
#   intelligence a Chief of Staff lives on (Insight/Prediction/DomainCorrelation/
#   GuidanceItem) but it was stranded — Beth could neither reach nor synthesize it.
#   Stage 1 makes it (a) reachable every turn via build_cos_intelligence's narrative,
#   and (b) synthesized into the ONE executive understanding via interpret(). Persisted
#   records only — no request-path recompute. Honest when the intelligence is empty.
# ==============================================================================
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_intelligence import active_intelligence, cos_intelligence_narrative
from apps.ai.chatgpt_cos.executive_interpretation import interpret

User = get_user_model()
_GDS = "apps.ai.cos_services.get_domain_state"


def _empty_state(user, domain):
    return {"state": {}}


class WholeLifeIntelligenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="wlu@test.com", password="x")

    def _seed(self):
        from apps.core.ai_insights.models import Insight
        from apps.core.ai_predictions.models import Prediction
        from apps.core.ai_cross_domain.models import DomainCorrelation
        from apps.core.ai_guidance.models import GuidanceItem
        Insight.objects.create(
            user=self.user, module="nutrition", insight_type="trend", severity="critical",
            title="Protein trending well below target", message="3 weeks under 60% of target",
            explain_why="from your logged meals", dedupe_key="i1", confidence_score=0.82,
            status="new")
        Insight.objects.create(
            user=self.user, module="fitness", insight_type="trend", severity="positive",
            title="Workout consistency up 40%", message="best month this year",
            explain_why="from your workouts", dedupe_key="i2", confidence_score=0.7, status="new")
        Prediction.objects.create(
            user=self.user, prediction_type="weight_30d", module="health",
            predicted_date=timezone.now() + timedelta(days=30), confidence_score=0.66,
            explanation="on pace to reach 279 lb by month end", dedupe_key="p1", status="active")
        DomainCorrelation.objects.create(
            user=self.user, domain_a="sleep", domain_b="journal", correlation_type="mood",
            strength="strong", strength_score=0.81, narrative="On 7h+ nights your mood entries are more positive",
            evidence_summary="42 nights", dedupe_key="c1", status="active")
        GuidanceItem.objects.create(
            user=self.user, title="Hydrate after heat exposure", message="you sweat a lot in summer",
            guidance_type="health", module="health", dedupe_key="g1", priority=1, is_active=True)

    # ── The reader surfaces the persisted intelligence, with basis + confidence ──
    def test_active_intelligence_reads_persisted_records(self):
        self._seed()
        intel = active_intelligence(self.user)
        self.assertTrue(intel["risks"] and "protein" in intel["risks"][0]["text"].lower())
        self.assertEqual(intel["risks"][0]["confidence"], "high")     # 0.82
        self.assertTrue(intel["wins"])
        self.assertTrue(intel["predictions"] and intel["predictions"][0]["when"])
        self.assertTrue(intel["patterns"] and "mood" in intel["patterns"][0]["text"].lower())
        self.assertTrue(intel["guidance"])

    def test_dismissed_and_inactive_are_excluded(self):
        from apps.core.ai_insights.models import Insight
        Insight.objects.create(
            user=self.user, module="health", insight_type="t", severity="critical",
            title="dismissed risk", message="x", explain_why="y", dedupe_key="d1",
            confidence_score=0.9, status="dismissed")
        self.assertEqual(active_intelligence(self.user)["risks"], [])

    # ── REACHABLE: the standing narrative renders it, citing basis; empty ⇒ silent ──
    def test_narrative_surfaces_intelligence_with_basis(self):
        self._seed()
        text = cos_intelligence_narrative({"intelligence": active_intelligence(self.user)})
        self.assertIn("Risk to watch", text)
        self.assertIn("basis:", text)
        self.assertIn("What's going well", text)   # positive insights are WINS, not opportunities
        self.assertIn("Pattern", text)

    def test_narrative_never_invents_when_empty(self):
        text = cos_intelligence_narrative({"intelligence": active_intelligence(self.user)})
        self.assertIsNone(text)   # nothing grounded → no block, never fabricated

    # ── SYNTHESIZED: interpret() folds the intelligence into the one picture ──
    def test_interpret_synthesizes_intelligence(self):
        self._seed()
        with mock.patch(_GDS, side_effect=_empty_state):
            sig = interpret(self.user)
        # Structured intelligence is now on the ONE executive understanding.
        self.assertTrue(sig.risks and "protein" in sig.risks[0]["text"].lower())
        self.assertTrue(sig.patterns and sig.wins and sig.predictions)
        self.assertTrue(sig.biggest_risk)                      # a risk is surfaced
        # With no bigger headline today, the top risk drives the executive picture.
        self.assertIn("thing to watch", sig.executive_picture.lower())
        self.assertIn("protein", sig.executive_picture.lower())
