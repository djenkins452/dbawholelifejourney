"""
Executive Briefing coherence regression tests.

Proves the briefing presents ONE dominant narrative: the state badge and the
headline derive from a single dominant-state verdict (so they can never
contradict), "All clear" can't coexist with real concerns, forward-risk
predictions never override the current state, and risk predictions never
surface under "Biggest Opportunity".

These are presentation-layer tests against the deterministic helpers in
``apps.core.cos_briefing.executive_summary`` — no LLM, no network.

Incident origin: production briefing showed "STEADY" badge + "you're slipping
behind" headline + "All clear" + an "overload risk" labeled as Biggest
Opportunity simultaneously.
"""

from types import SimpleNamespace

from django.test import TestCase

from apps.core.cos_briefing.executive_summary import (
    _augment_attention_with_execution,
    _collect_biggest_opportunity,
    _derive_headline,
    _derive_overall_state,
    _is_risk_prediction,
)

ALL_STATES = ("improving", "steady", "slipping", "at_risk", "mixed", "unknown")

# Wording that may ONLY appear when the state is negative (slipping/at_risk).
_DECLINE_PHRASES = ("slipping", "past due", "at risk", "behind", "drifted", "drift")


def _exec_state(overdue=0, at_risk=0, recovery="NORMAL"):
    return {
        "overdue_actions": [{"title": f"item {i}"} for i in range(overdue)],
        "at_risk_actions": [{"title": f"risk {i}"} for i in range(at_risk)],
        "recovery_state": {"mode": recovery},
    }


def _phase_state(phase, **facts):
    """exec_state carrying an ``execution_phase`` facts dict — the truth the headline
    now grounds on."""
    pf = {"phase": phase, "overdue_count": facts.get("overdue_count", 0),
          "first_commitment": facts.get("first_commitment"),
          "minutes_until_first_commitment": facts.get("minutes_until_first_commitment")}
    return {"execution_phase": pf}


def _insights(n, severity="warning"):
    return [{"title": f"{severity} {i}", "severity": severity} for i in range(n)]


class DominantStateCoherenceTests(TestCase):
    """After the 2026-07-16 redesign the badge and headline carry DIFFERENT truths:
    the badge is the weekly trend; the headline is today's execution phase. The
    coherence guarantee is now: the headline never asserts a within-day decline
    unless `execution_phase == behind`, no matter what the weekly trend says."""

    def test_badge_is_weekly_trend_only(self):
        """The badge (trajectory) reflects the LONG-TERM trend and is NOT flipped by
        today's overdue/at-risk/recovery pressure — that's the headline's job now."""
        gw = [{"title": "win a"}, {"title": "win b"}]
        # Same positive weekly trend regardless of today's execution pressure.
        self.assertEqual(_derive_overall_state(gw, [], None, _exec_state()), "improving")
        self.assertEqual(
            _derive_overall_state(gw, [], None, _exec_state(overdue=3)), "improving")
        self.assertEqual(
            _derive_overall_state([], [], None, _exec_state(recovery="RECOVERY")),
            "unknown")

    def test_headline_grounded_in_phase_not_weekly_trend(self):
        """A 'slipping' weekly trend must NOT make the headline claim today is
        slipping when the day hasn't begun."""
        state = _phase_state(
            "before_first_commitment",
            first_commitment={"title": "Prayer Time", "time": "5:30 AM",
                              "minutes_until": 34},
            minutes_until_first_commitment=34,
        )
        headline = _derive_headline("slipping", [], [], state, focus_now=None).lower()
        self.assertIn("just beginning", headline)
        for phrase in _DECLINE_PHRASES:
            self.assertNotIn(phrase, headline, f"leaked decline word {phrase!r}: {headline!r}")

    def test_headline_only_declines_when_phase_is_behind(self):
        """Decline language ('past due', 'drifted') is allowed ONLY when the
        execution phase proves it. An on-track 'underway' day with a slipping
        weekly trend stays free of within-day decline words."""
        underway = _derive_headline("slipping", [], [], _phase_state("underway"), None).lower()
        for phrase in _DECLINE_PHRASES:
            self.assertNotIn(phrase, underway)
        behind = _derive_headline("steady", [], [], _phase_state("behind", overdue_count=2), None).lower()
        self.assertIn("drifted", behind)
        self.assertIn("past due", behind)

    def test_3_forward_risk_does_not_override_trend(self):
        """The badge reads only current insight signals, never forward-risk
        predictions — a stable trend stays stable."""
        gw = [{"title": "win a"}, {"title": "win b"}]
        self.assertEqual(_derive_overall_state(gw, [], None, _exec_state()), "improving")

    def test_5_plateau_and_calorie_dont_force_slipping(self):
        """Plateau / calorie concerns arrive as predictions and guidance (not warning
        insights). With primary signals stable, the trend must not be forced to
        'slipping'."""
        gw = [{"title": "consistent rhythm"}]
        state = _derive_overall_state(gw, [], None, _exec_state())
        self.assertEqual(state, "steady")

    def test_6_positive_momentum_recognized(self):
        """Clear improving insight signals with no concerns → improving trend."""
        gw = [{"title": "win a"}, {"title": "win b"}]
        self.assertEqual(_derive_overall_state(gw, [], None, _exec_state()), "improving")

    def test_7_mixed_trend(self):
        """Real wins + real drift → 'mixed' weekly trend."""
        gw = [{"title": "win"}]
        na = _insights(2)
        self.assertEqual(_derive_overall_state(gw, na, None, _exec_state()), "mixed")


class AllClearGateTests(TestCase):
    def test_2_all_clear_cannot_coexist_with_overdue(self):
        """Requirement 2: empty insights + overdue execution must surface a
        concern row so the template can't render 'All clear.'"""
        augmented = _augment_attention_with_execution([], _exec_state(overdue=2))
        self.assertTrue(augmented, "overdue items must populate needs_attention")
        self.assertEqual(augmented[0]["severity"], "warning")

    def test_2_all_clear_cannot_coexist_with_at_risk(self):
        augmented = _augment_attention_with_execution([], _exec_state(at_risk=1))
        self.assertTrue(augmented)

    def test_existing_insights_are_not_duplicated(self):
        """If insights already populate the column, leave it untouched."""
        existing = _insights(2)
        augmented = _augment_attention_with_execution(existing, _exec_state(overdue=3))
        self.assertEqual(augmented, existing)

    def test_truly_clear_day_stays_empty(self):
        self.assertEqual(_augment_attention_with_execution([], _exec_state()), [])


class OpportunityPolarityTests(TestCase):
    def test_risk_slug_is_classified_as_risk(self):
        for slug in ("task_overdue_risk", "emotional_overload_7d", "weight_decline"):
            p = SimpleNamespace(prediction_type=slug, evidence={})
            self.assertTrue(_is_risk_prediction(p), slug)

    def test_risk_outlook_is_classified_as_risk(self):
        p = SimpleNamespace(
            prediction_type="habit_continuation",
            evidence={"outlook": "at risk of dropping off"},
        )
        self.assertTrue(_is_risk_prediction(p))

    def test_positive_prediction_is_not_risk(self):
        p = SimpleNamespace(
            prediction_type="weight_projection",
            evidence={"outlook": "on track"},
        )
        self.assertFalse(_is_risk_prediction(p))


class OpportunityIntegrationTests(TestCase):
    def setUp(self):
        from django.conf import settings

        from apps.users.models import TermsAcceptance, User

        self.user = User.objects.create_user(
            email="exec-coherence@example.com", password="x",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def _mk_prediction(self, ptype, conf, explanation="", evidence=None):
        from django.utils import timezone

        from apps.core.ai_predictions.models import Prediction

        return Prediction.objects.create(
            user=self.user,
            prediction_type=ptype,
            module="health",
            confidence_score=conf,
            predicted_date=timezone.now(),
            explanation=explanation,
            evidence=evidence or {},
            status="active",
        )

    def test_4_risk_prediction_never_surfaces_as_opportunity(self):
        """Requirement 4: a high-confidence risk prediction must not appear in
        the Biggest Opportunity slot; a weaker positive one wins instead."""
        self._mk_prediction(
            "task_overdue_risk", 0.95, explanation="Overload risk is rising.",
        )
        self._mk_prediction(
            "weight_projection", 0.70,
            explanation="On pace to reach your goal weight.",
            evidence={"outlook": "on track"},
        )
        opp = _collect_biggest_opportunity(self.user)
        self.assertIsNotNone(opp)
        self.assertNotIn("overload", opp["title"].lower())
        self.assertIn("goal weight", (opp["title"] + opp["message"]).lower())

    def test_4_only_risk_predictions_yields_no_opportunity(self):
        self._mk_prediction(
            "emotional_overload_7d", 0.92, explanation="Overload risk rising.",
        )
        self.assertIsNone(_collect_biggest_opportunity(self.user))


class TruthfulnessContractTests(TestCase):
    def test_8_no_llm_in_briefing_module(self):
        """Requirement 8: the briefing stays deterministic — zero LLM imports."""
        import apps.core.cos_briefing.executive_summary as es

        src = open(es.__file__).read().lower()
        for token in ("import openai", "from openai", "chatcompletion", "client.chat"):
            self.assertNotIn(token, src, f"LLM token {token!r} leaked into briefing")

    def test_8_state_derivation_is_deterministic(self):
        gw, na, es = [{"title": "win"}], _insights(1), _exec_state(overdue=2)
        first = _derive_overall_state(gw, na, None, es)
        second = _derive_overall_state(gw, na, None, es)
        self.assertEqual(first, second)
        self.assertIn(first, ALL_STATES)
