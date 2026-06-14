"""Biggest Opportunity → highest-leverage action redesign.

The tile must answer "what's the smartest thing to do next?" with a single
constructive ACTION (headline) + a one-sentence rationale (why), chosen by
LEVERAGE across both weakness signals (Insights) and the positive prediction.
Deterministic, no LLM.

Also locks the Recommended Focus dedup fix (no duplicate chips).
"""

from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_guidance.models import GuidanceItem
from apps.core.ai_insights.models import Insight
from apps.core.ai_predictions.models import Prediction
from apps.core.cos_briefing.executive_summary import (
    _collect_biggest_opportunity,
    _collect_recommendations,
    _LEVERS,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


def _make_user(email="exec-opp-leverage@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _insight(user, title, *, severity="warning", insight_type="generic",
             module="health", message="", key=None):
    return Insight.objects.create(
        user=user, module=module, insight_type=insight_type, severity=severity,
        title=title, message=message or title, status="new",
        dedupe_key=key or f"k-{title}-{insight_type}",
    )


def _prediction(user, ptype, conf, explanation, *, module="health", key=None):
    return Prediction.objects.create(
        user=user, prediction_type=ptype, module=module, confidence_score=conf,
        predicted_date=date.today() + timedelta(days=30),
        explanation=explanation, evidence={"outlook": "on track"},
        status="active", dedupe_key=key or f"p-{ptype}",
    )


def _guidance(user, title, priority, key):
    return GuidanceItem.objects.create(
        user=user, title=title, message=f"{title} detail", priority=priority,
        guidance_type="rule", module="health", is_active=True, dedupe_key=key,
    )


class BiggestOpportunityActionTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_weakness_produces_action_headline_not_observation(self):
        """A sleep concern becomes a constructive action, not a risk restatement."""
        _insight(self.user, "Sleep debt is rising", insight_type="sleep_quality",
                 message="Average sleep dropped below 6h this week.")
        opp = _collect_biggest_opportunity(self.user)
        self.assertIsNotNone(opp)
        self.assertEqual(opp["kind"], "weakness")
        self.assertEqual(opp["lever"], "sleep")
        self.assertEqual(opp["headline"], "Prioritize sleep tonight")
        # Action-oriented: never echoes the raw risk word as the headline.
        self.assertNotIn("debt", opp["headline"].lower())
        self.assertNotIn("rising", opp["headline"].lower())
        # Has a short supporting why.
        self.assertTrue(opp["why"])

    def test_highest_leverage_wins_over_lower_leverage(self):
        """Sleep (rank 100) must beat a weight concern (rank 50)."""
        _insight(self.user, "Weight loss has plateaued", insight_type="weight_plateau")
        _insight(self.user, "Poor sleep this week", insight_type="sleep_quality")
        opp = _collect_biggest_opportunity(self.user)
        self.assertEqual(opp["lever"], "sleep")
        self.assertEqual(opp["headline"], "Prioritize sleep tonight")

    def test_weakness_outranks_positive_prediction_when_higher_leverage(self):
        """A sleep weakness beats a positive weight-projection 'protect' lever."""
        _insight(self.user, "Sleep consistency slipping", insight_type="sleep_quality")
        _prediction(self.user, "weight_projection", 0.85,
                    "On pace to reach your goal weight.")
        opp = _collect_biggest_opportunity(self.user)
        self.assertEqual(opp["kind"], "weakness")
        self.assertEqual(opp["lever"], "sleep")

    def test_positive_prediction_used_when_no_weakness(self):
        """No concerns → protect what's working, still action-phrased."""
        _prediction(self.user, "weight_projection_30d", 0.85,
                    "Consistent logging is putting your goal weight in reach. "
                    "Keep the streak going.")
        opp = _collect_biggest_opportunity(self.user)
        self.assertIsNotNone(opp)
        self.assertEqual(opp["kind"], "positive")
        self.assertEqual(opp["headline"], "Lock in your weight-loss pace")
        # Back-compat: explanation observation preserved in title/message.
        self.assertIn("goal weight", opp["title"].lower())
        self.assertNotIn("30D", opp["title"])
        # Why is grounded in the user's own explanation.
        self.assertIn("goal weight", opp["why"].lower())

    def test_muscle_weakness_maps_to_protect_muscle_action(self):
        _insight(self.user, "Lean mass dropping during cut",
                 insight_type="lean_mass_loss",
                 message="Lean mass trending down while losing weight.")
        opp = _collect_biggest_opportunity(self.user)
        self.assertEqual(opp["lever"], "muscle")
        self.assertEqual(opp["headline"], "Protect muscle while you lose weight")

    def test_no_signal_returns_none(self):
        self.assertIsNone(_collect_biggest_opportunity(self.user))

    def test_only_risk_prediction_and_no_weakness_returns_none(self):
        """Risk predictions excluded; with no weaknesses there's no opportunity."""
        _prediction(self.user, "task_overdue_risk", 0.95, "Overload risk rising.")
        # evidence outlook on_track would un-risk it; force a risk slug only.
        Prediction.objects.filter(user=self.user).update(evidence={})
        self.assertIsNone(_collect_biggest_opportunity(self.user))

    def test_short_form_limits_preserved(self):
        """Headline and why stay tile-sized (one short line each)."""
        _insight(self.user, "Glucose volatility increasing", insight_type="glucose")
        opp = _collect_biggest_opportunity(self.user)
        self.assertLessEqual(len(opp["headline"]), 60)
        self.assertLessEqual(len(opp["why"]), 140)

    def test_unmapped_weakness_falls_through_to_positive_or_none(self):
        """A concern that maps to no lever doesn't crash; positive lever wins."""
        _insight(self.user, "Something unclassifiable", insight_type="misc_xyz",
                 message="No lever keywords here.")
        _prediction(self.user, "weight_projection", 0.8,
                    "On pace to reach your goal weight.")
        opp = _collect_biggest_opportunity(self.user)
        self.assertEqual(opp["kind"], "positive")

    def test_every_lever_has_headline_and_why(self):
        for key, spec in _LEVERS.items():
            self.assertTrue(spec["headline"], f"{key} missing headline")
            self.assertTrue(spec["why"], f"{key} missing why")
            self.assertLessEqual(len(spec["headline"]), 60)


class RecommendationDedupTests(TestCase):
    def setUp(self):
        self.user = _make_user("exec-rec-dedup@test.com")

    def test_duplicate_titles_collapse_to_one_chip(self):
        """Three 'Progression check-in' rows (different dedupe_keys) → one chip."""
        _guidance(self.user, "Progression check-in", 3, "g1")
        _guidance(self.user, "Progression check-in", 3, "g2")
        _guidance(self.user, "Progression check-in", 3, "g3")
        recs = _collect_recommendations(self.user)
        titles = [r["title"] for r in recs]
        self.assertEqual(titles.count("Progression check-in"), 1)
        self.assertEqual(len(recs), 1)

    def test_distinct_recommendations_value_ranked(self):
        """Priority (value) ordering preserved; duplicates removed."""
        _guidance(self.user, "Progression check-in", 3, "g1")
        _guidance(self.user, "Progression check-in", 3, "g2")
        _guidance(self.user, "Hydrate before training", 1, "g3")
        recs = _collect_recommendations(self.user)
        self.assertEqual(recs[0]["title"], "Hydrate before training")  # priority 1
        self.assertEqual(len(recs), 2)
        self.assertEqual(len({r["title"] for r in recs}), 2)

    def test_low_signal_yields_fewer_not_padded(self):
        recs = _collect_recommendations(self.user)
        self.assertEqual(recs, [])

    def test_cap_respected_with_distinct_items(self):
        for i in range(6):
            _guidance(self.user, f"Rec {i}", 2, f"g{i}")
        recs = _collect_recommendations(self.user)
        self.assertEqual(len(recs), 3)  # MAX_RECOMMENDATIONS
        self.assertEqual(len({r["title"] for r in recs}), 3)
