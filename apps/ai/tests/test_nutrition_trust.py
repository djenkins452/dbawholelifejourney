"""
Phase 5 — Nutrition trust regression tests.

Trust defect (2026-05-31): "I had 8 raw oysters. how much protein?" returned a
confident 0 cal / 0 protein status while the dashboard showed 1418 cal / 136g.
Three independent defects combined:

  FIX 1 (routing): 'how much protein' substring inside a food-estimate sentence
    hijacked the deterministic nutrition STATUS route, suppressing the log/estimate
    path. A specific-food estimate or consumption report must fall through.

  FIX 2 (grounding): build_nutrition_state computed "today" from the SERVER
    timezone (get_current_time().date()) while the dashboard uses the USER's
    timezone (get_user_today). Near midnight they disagree on which day's intake
    to show. Both must share one definition of "today".

  FIX 3 (freshness + confidence): the status handler read an unguarded SAE
    snapshot. Now it refreshes nutrition before reading, and refuses to assert a
    confident "0 calories today" when the snapshot contradicts itself.

Hard invariant under test: Beth and the dashboard can never diverge on nutrition.
"""

from datetime import time
from unittest.mock import patch

from django.conf import settings
from django.db.models import Sum
from django.test import TestCase

from apps.ai.deterministic_router import (
    _handle_nutrition_query,
    _is_food_estimate_query,
    _match_nutrition_query,
)
from apps.core.ai_state.state_builder import build_nutrition_state
from apps.core.utils import get_user_today
from apps.health.models import FoodEntry
from apps.health.services.nutrition_queries import NutritionQueries
from apps.users.models import TermsAcceptance, User


# ── FIX 1: routing ──────────────────────────────────────────────────


class TestNutritionRoutingSuppression(TestCase):
    """A specific-food estimate / consumption report must NOT route to the
    deterministic nutrition STATUS responder."""

    SUPPRESS = [
        'i had 8 oysters how much protein',
        'protein in a banana',
        'how many calories in steak',
        'i ate 2 eggs',
        'i just had a protein shake',
        'how much protein is in chicken breast',
        'calories of a bagel',
    ]

    # Genuine status questions — these stay on the status route. (Only the
    # phrases the deterministic nutrition matcher actually owns are asserted
    # True; the rest are asserted "not over-suppressed by my guard".)
    STATUS_STILL_MATCHES = [
        'how is my nutrition',
        'my macros',
        'calories today',
        'macros today',
        'how much protein',  # bare status question, no food entity
        'how are my calories today',
    ]

    NOT_OVER_SUPPRESSED = STATUS_STILL_MATCHES + [
        'nutrition today',
        'macro compliance',
        'how am i doing on protein?',
    ]

    def test_food_estimate_queries_suppressed(self):
        for q in self.SUPPRESS:
            self.assertTrue(
                _is_food_estimate_query(q),
                f"guard failed to recognise food estimate: {q!r}",
            )
            self.assertFalse(
                _match_nutrition_query(q),
                f"food estimate leaked into status route: {q!r}",
            )

    def test_status_queries_still_match(self):
        for q in self.STATUS_STILL_MATCHES:
            self.assertTrue(
                _match_nutrition_query(q),
                f"genuine status query lost its route: {q!r}",
            )

    def test_guard_does_not_over_suppress_status(self):
        for q in self.NOT_OVER_SUPPRESSED:
            self.assertFalse(
                _is_food_estimate_query(q),
                f"guard wrongly flagged a status query as estimate: {q!r}",
            )


# ── FIX 2 + trust invariant: grounding ──────────────────────────────


class NutritionUserMixin:
    def setUp(self):
        self.user = User.objects.create_user(
            email='nutrition-trust@test.com', password='testpass123',
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.timezone = 'America/Chicago'
        self.user.preferences.save()

    def _log_food(self, calories, protein, on_date):
        return FoodEntry.objects.create(
            user=self.user,
            food_name='Raw oysters',
            quantity=8,
            serving_size=1,
            serving_unit='each',
            total_calories=calories,
            total_protein_g=protein,
            logged_date=on_date,
            logged_time=time(12, 0),
            meal_type=FoodEntry.MEAL_LUNCH,
        )


class TestNutritionGroundingInvariant(NutritionUserMixin, TestCase):
    """Beth and the dashboard derive "today's intake" from the same source and
    the same (user-local) definition of today."""

    def test_builder_uses_user_local_today(self):
        today = get_user_today(self.user)
        self._log_food(calories=140, protein=20, on_date=today)

        state = build_nutrition_state(self.user)
        self.assertTrue(state.get('enabled'))
        self.assertEqual(state['food_entries_today'], 1)
        self.assertAlmostEqual(state['daily_calories'], 140.0, places=1)
        self.assertAlmostEqual(state['daily_protein_g'], 20.0, places=1)

    def test_beth_and_dashboard_cannot_diverge(self):
        """Hard invariant: dashboard total == Beth/SAE total after logging."""
        from apps.core.ai_state.state_engine import get_module_state
        from apps.core.ai_state.state_freshness import ensure_fresh

        today = get_user_today(self.user)
        self._log_food(calories=900, protein=80, on_date=today)
        self._log_food(calories=518, protein=56, on_date=today)

        # Dashboard truth: raw FoodEntry aggregate for the user's today.
        dashboard_total = NutritionQueries.entries_on_date(
            self.user, today,
        ).aggregate(c=Sum('total_calories'))['c']

        # Beth's path: refresh then read the SAE snapshot.
        ensure_fresh(self.user, ['nutrition'])
        beth = get_module_state(self.user, 'nutrition') or {}

        self.assertAlmostEqual(
            float(dashboard_total), float(beth['daily_calories']), places=1,
            msg='Beth and dashboard diverged on nutrition totals',
        )


# ── FIX 3: freshness + confidence guard ─────────────────────────────


class TestNutritionConfidenceGuard(NutritionUserMixin, TestCase):
    """_handle_nutrition_query must never assert a confident "0 calories today"
    when the snapshot contradicts itself."""

    def _run_with_snapshot(self, snapshot):
        with patch(
            'apps.core.ai_state.state_freshness.ensure_fresh',
        ) as mock_fresh, patch(
            'apps.core.ai_state.state_engine.get_module_state',
            return_value=snapshot,
        ):
            mock_fresh.return_value = {'nutrition'}
            return _handle_nutrition_query(self.user)

    def test_contradictory_snapshot_refuses_answer(self):
        # Food logged today but zero calories → impossible → refuse.
        result = self._run_with_snapshot({
            'daily_calories': 0,
            'food_entries_today': 3,
            'food_entries_7d': 21,
        })
        self.assertIsNone(result)

    def test_suspicious_snapshot_refuses_answer(self):
        # No today-count key, zero calories, but weekly entries exist → suspect.
        result = self._run_with_snapshot({
            'daily_calories': 0,
            'food_entries_7d': 21,
        })
        self.assertIsNone(result)

    def test_legitimate_zero_today_still_answers(self):
        # Genuine "nothing logged yet today" — keys agree → answer truthfully.
        result = self._run_with_snapshot({
            'daily_calories': 0,
            'food_entries_today': 0,
            'food_entries_7d': 5,
        })
        self.assertIsNotNone(result)

    def test_refresh_is_invoked_before_read(self):
        with patch(
            'apps.core.ai_state.state_freshness.ensure_fresh',
        ) as mock_fresh, patch(
            'apps.core.ai_state.state_engine.get_module_state',
            return_value={'daily_calories': 200, 'food_entries_today': 2,
                          'food_entries_7d': 6},
        ):
            mock_fresh.return_value = {'nutrition'}
            _handle_nutrition_query(self.user)
            mock_fresh.assert_called_once()
            args, _ = mock_fresh.call_args
            self.assertIn('nutrition', args[1])


# ── Regression 2026-06-03: nutrition status routing precedence ──────


class TestNutritionStatusMatcherCoverage(TestCase):
    """The status matcher must recognise nutrient + status phrasing, not just
    a hand-curated phrase list. Regression: 'protein today' / 'nutrition today'
    / 'macro compliance' / 'how am I doing on protein today?' previously matched
    NOTHING and fell through to the LLM or execution coaching."""

    MUST_MATCH = [
        'how am i doing on protein today?',
        'how are my calories today?',
        'protein today',
        'calories today',
        'nutrition today',
        'macro compliance',
        'how much protein have i had?',
        'how am i doing on macros',
        'where am i on calories',
    ]

    # Not nutrition status — must NOT be hijacked by the broadened matcher.
    MUST_NOT_MATCH = [
        'i had 8 oysters how much protein',   # food estimate → log path
        'i ate 2 eggs',                       # consumption report
        'how many calories did i burn today',  # exercise, not intake
        'log my protein for today',           # logging intent
        "what's left today",                  # generic status
        'how am i doing today',               # no nutrient → not nutrition
        'other than nutrition, anything left?',  # qualified status
    ]

    def test_status_phrases_match(self):
        for q in self.MUST_MATCH:
            self.assertTrue(
                _match_nutrition_query(q),
                f"nutrition status query lost its route: {q!r}",
            )

    def test_non_status_phrases_do_not_match(self):
        for q in self.MUST_NOT_MATCH:
            self.assertFalse(
                _match_nutrition_query(q),
                f"non-nutrition query hijacked by status matcher: {q!r}",
            )


class TestNutritionStatusRoutePrecedence(NutritionUserMixin, TestCase):
    """End-to-end: a nutrition status query must resolve to the nutrition_query
    route, BEATING the decision/focus/execution routers.

    Production regression 2026-06-03: "How am I doing on protein today?" routed
    into execution coaching ("Go straight into Bike Ride…") because Phase 11.1
    (decision query, triggered by the embedded 'how am i doing') ran before the
    Phase 1 nutrition data route. Nutrition status now runs first.
    """

    def setUp(self):
        super().setUp()
        from apps.core.utils import get_user_today
        # Real food today so _handle_nutrition_query returns a response.
        self._log_food(calories=900, protein=80, on_date=get_user_today(self.user))

    def _route_name(self, message):
        from apps.ai.deterministic_router import classify_and_route
        result = classify_and_route(message, self.user, conversation=None)
        return result.route_name

    def test_status_queries_route_to_nutrition(self):
        for q in (
            'How am I doing on protein today?',
            'How are my calories today?',
            'Protein today',
            'Calories today',
            'Nutrition today',
        ):
            self.assertEqual(
                self._route_name(q), 'nutrition_query',
                f"nutrition status query did not win routing: {q!r}",
            )

    def test_food_estimate_does_not_route_to_nutrition_status(self):
        # Must still bypass the status route → goes to log/estimate path.
        self.assertNotEqual(
            self._route_name('I had 8 oysters how much protein?'),
            'nutrition_query',
        )


# ── Trust repair 2026-06-02: answer-first / response-shape contract ──


class TestNutritionAnswerFirstContract(NutritionUserMixin, TestCase):
    """A direct factual nutrition status question gets an ANSWER-FIRST
    response: grounded totals only. No cross-domain priority note, no
    macro-score interpretation, no execution coaching. The decision/coaching
    template is reserved for explicit "what should I do" requests.

    Production defect: "How am I doing on protein today?" returned a full
    Situation/Interpretation/Action decision block with a "Priority note:
    sleep" cross-domain overlay and "Macro compliance 23/100 — well off
    target" coaching, instead of just answering the protein question.
    """

    SNAPSHOT = {
        'daily_calories': 1418,
        'daily_protein_g': 136,
        'calorie_target': 2200,
        'protein_target': 180,
        'macro_compliance_score': 23,
        'food_entries_today': 3,
        'food_entries_7d': 18,
    }

    FACTUAL = [
        'how am i doing on protein today?',
        'protein today',
        'calories today',
        'how are my calories today?',
        'nutrition today',
        'how much protein have i had?',
    ]

    CONTAMINANTS = [
        'priority note', 'sleep', 'bike', 'macro compliance',
        '**action**', '**interpretation**', '**situation**',
    ]

    def _answer(self, msg_lower, snapshot=None):
        snap = self.SNAPSHOT if snapshot is None else snapshot
        with patch(
            'apps.core.ai_state.state_freshness.ensure_fresh',
        ) as mock_fresh, patch(
            'apps.core.ai_state.state_engine.get_module_state',
            return_value=snap,
        ):
            mock_fresh.return_value = {'nutrition'}
            return _handle_nutrition_query(self.user, msg_lower)

    def test_factual_query_has_no_contamination(self):
        for q in self.FACTUAL:
            resp = self._answer(q)
            self.assertIsNotNone(resp, f"no answer produced for {q!r}")
            low = resp.lower()
            for bad in self.CONTAMINANTS:
                self.assertNotIn(
                    bad, low,
                    f"contamination {bad!r} leaked into answer for {q!r}: {resp!r}",
                )

    def test_protein_query_answers_factually(self):
        resp = self._answer('how am i doing on protein today?')
        self.assertIn('136g', resp)   # grounded protein total
        self.assertIn('180g', resp)   # target comparison when grounded
        self.assertNotIn('1418', resp)  # narrow question: no calorie noise

    def test_calorie_query_answers_factually(self):
        resp = self._answer('calories today')
        self.assertIn('1418', resp)
        self.assertNotIn('136g', resp)  # narrow question: no protein noise

    def test_generic_nutrition_query_reports_both(self):
        resp = self._answer('nutrition today')
        self.assertIn('136g', resp)
        self.assertIn('1418', resp)

    def test_legitimate_zero_still_answers_without_coaching(self):
        resp = self._answer('calories today', snapshot={
            'daily_calories': 0,
            'food_entries_today': 0,
            'food_entries_7d': 5,
        })
        self.assertIsNotNone(resp)
        self.assertIn('0', resp)
        self.assertNotIn('**action**', resp.lower())

    def test_explicit_coaching_request_keeps_decision_template(self):
        # An explicit guidance request is NOT a bare factual question — it may
        # still use the Situation/Interpretation/Action coaching template.
        resp = self._answer('what should i do about my macros today?')
        self.assertIsNotNone(resp)
        self.assertIn('**Action**', resp)


class TestNutritionStatusBeatsCosModeShortcut(NutritionUserMixin, TestCase):
    """In non-streaming send_message, _cos_mode_shortcut runs BEFORE
    classify_and_route. "How am I doing on protein today?" matches the generic
    execution keyword "how am i doing", so the shortcut intercepted it and
    answered with the execution selector ("Nothing pending right now.")
    instead of the protein total.

    Production defect: short-form "Protein today" answered factually (no
    shortcut match) but the conversational "How am I doing on protein today?"
    was intercepted by the execution shortcut. Nutrition status asks must
    defer to the nutrition route — nutrition wins.
    """

    NUTRITION_PHRASES = [
        'How am I doing on protein today?',
        'Nutrition today',
        'How are my calories today?',
        'Calories today',
        'How much protein have I had?',
        'Macro intake today',
        'Protein today',
    ]

    def _shortcut(self, message):
        from apps.ai.personal_assistant import PersonalAssistant
        from apps.ai.models import AssistantConversation
        pa = PersonalAssistant(self.user)
        conv = AssistantConversation.objects.create(user=self.user)
        return pa._cos_mode_shortcut(message, conv)

    def test_nutrition_status_asks_bypass_execution_shortcut(self):
        for phrase in self.NUTRITION_PHRASES:
            self.assertIsNone(
                self._shortcut(phrase),
                f"nutrition status ask {phrase!r} was intercepted by the "
                f"cos_mode_shortcut instead of deferring to the nutrition route",
            )

    def test_non_nutrition_status_still_resolves_to_execution(self):
        # Guard against over-suppression: a status ask with NO nutrient term
        # must still reach the execution selector via the shortcut.
        result = self._shortcut('how am i doing today')
        self.assertIsNotNone(result)
        self.assertTrue(result.get('deterministic'))
