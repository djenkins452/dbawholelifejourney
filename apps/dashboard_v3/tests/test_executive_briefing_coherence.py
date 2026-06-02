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


def _insights(n, severity="warning"):
    return [{"title": f"{severity} {i}", "severity": severity} for i in range(n)]


class DominantStateCoherenceTests(TestCase):
    def test_1_badge_and_headline_never_contradict(self):
        """Requirement 1: for every dominant state, the headline cannot use
        decline language unless the state is itself negative."""
        scenarios = [
            # (going_well, needs_attention, biggest_risk, exec_state)
            (_insights(2, "positive"), [], None, _exec_state()),          # improving
            ([{"title": "one win"}], [], None, _exec_state()),            # steady
            ([], _insights(1), None, _exec_state()),                      # slipping
            ([], [], None, _exec_state(overdue=4)),                       # at_risk
            (_insights(1, "positive"), _insights(1), None, _exec_state()),  # mixed
            ([], [], None, _exec_state()),                                # unknown
        ]
        for gw, na, risk, es in scenarios:
            state = _derive_overall_state(gw, na, risk, es)
            headline = _derive_headline(state, gw, na, es, focus_now=None).lower()
            if state in ("improving", "steady", "unknown"):
                for phrase in _DECLINE_PHRASES:
                    self.assertNotIn(
                        phrase, headline,
                        f"state={state} headline leaked decline word {phrase!r}: {headline!r}",
                    )

    def test_1b_steady_state_headline_is_not_slipping(self):
        """The exact production contradiction: STEADY badge must not pair with
        a 'you're slipping behind' headline."""
        gw = [{"title": "one win"}]
        state = _derive_overall_state(gw, [], None, _exec_state())
        self.assertEqual(state, "steady")
        headline = _derive_headline(state, gw, [], _exec_state(), focus_now=True)
        self.assertNotIn("slipping", headline.lower())

    def test_3_forward_risk_does_not_override_current_state(self):
        """Requirement 3: dominant state reads only current signals (insights +
        now-pressure), never forward-risk predictions — so a stable day stays
        stable even when a future-risk prediction exists."""
        gw = [{"title": "win a"}, {"title": "win b"}]
        # No exec pressure, no warning insights → improving regardless of any
        # forward-risk prediction (predictions are not an input here at all).
        state = _derive_overall_state(gw, [], None, _exec_state())
        self.assertEqual(state, "improving")

    def test_5_plateau_and_calorie_dont_force_slipping(self):
        """Requirement 5: plateau / calorie concerns arrive as predictions and
        guidance (not warning insights). With primary signals stable, the
        dominant state must not be forced to 'slipping'."""
        gw = [{"title": "consistent rhythm"}]
        state = _derive_overall_state(gw, [], None, _exec_state())
        self.assertEqual(state, "steady")
        self.assertNotEqual(state, "slipping")

    def test_6_positive_momentum_recognized(self):
        """Requirement 6: clear improving signals with no concerns → improving,
        and the headline reflects upward momentum."""
        gw = [{"title": "win a"}, {"title": "win b"}]
        state = _derive_overall_state(gw, [], None, _exec_state())
        self.assertEqual(state, "improving")
        headline = _derive_headline(state, gw, [], _exec_state(), focus_now=None)
        self.assertIn("trending up", headline.lower())

    def test_7_mixed_day_single_coherent_narrative(self):
        """Requirement 7: real wins + real drift, no now-pressure → 'mixed',
        and the headline names both without overclaiming either direction."""
        gw = [{"title": "win"}]
        na = _insights(2)
        state = _derive_overall_state(gw, na, None, _exec_state())
        self.assertEqual(state, "mixed")
        headline = _derive_headline(state, gw, na, _exec_state(), focus_now=None)
        self.assertIn("mixed signals", headline.lower())

    def test_now_pressure_outranks_positive_insights(self):
        """Overdue items right now make the day 'slipping' even with positive
        insights — current reality beats the weekly trend."""
        gw = [{"title": "win a"}, {"title": "win b"}]
        state = _derive_overall_state(gw, [], None, _exec_state(overdue=1))
        self.assertEqual(state, "slipping")

    def test_recovery_mode_is_at_risk(self):
        state = _derive_overall_state([], [], None, _exec_state(recovery="RECOVERY"))
        self.assertEqual(state, "at_risk")


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
