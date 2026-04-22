"""
Phase 19.3 — Single-action fallback resolver tests.

Guarantees that when the main priority stack in
_build_focus_query_response returns None, the response is still:

* exactly ONE concrete action,
* never a category,
* never a multi-option list (no "A, B, or C"),
* never a debug string.
"""

from datetime import date
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from datetime import datetime

from apps.ai.deterministic_router import (
    _FINAL_DEFAULT_ACTION,
    _build_focus_query_response,
    _time_aware_final_default,
    _try_decision_query_route,
    resolve_fallback_action,
)
from apps.users.models import User


def _make_user(email):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(
        email=email, password="testpass123",
        date_of_birth=date(1990, 1, 1),
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _fake_execution(items):
    def builder(user):
        return {'items': items, 'summaries': {}}
    return builder


# ───────────────────────────────────────────────────────────────
# Resolver unit tests — don't need a real user / DB.
# ───────────────────────────────────────────────────────────────

class FallbackResolverHabitPickTests(TestCase):
    """resolve_fallback_action picks a single habit when habits exist."""

    def setUp(self):
        self.user = _make_user("resolver_habit@test.com")

    def _with_habits(self, streaks_per_habit):
        """Mock SAE habits state with the given streaks_per_habit list."""
        def fake(user, module):
            if module == 'habits':
                return {
                    'active_habit_count': len(streaks_per_habit),
                    'streaks_per_habit': streaks_per_habit,
                }
            return {}
        return patch(
            'apps.core.ai_state.state_engine.get_module_state',
            side_effect=fake,
        )

    def test_picks_foundational_habit_over_non_foundational(self):
        with self._with_habits([
            {
                'name': 'Workout', 'current_streak': 10,
                'is_foundational': False,
            },
            {
                'name': 'Prayer Time', 'current_streak': 3,
                'is_foundational': True,
            },
        ]):
            fb = resolve_fallback_action(self.user)
        self.assertEqual(fb['primary_action'], "Do your Prayer Time now")

    def test_picks_longest_streak_as_tiebreak(self):
        with self._with_habits([
            {
                'name': 'Daily Prayer', 'current_streak': 2,
                'is_foundational': True,
            },
            {
                'name': 'Scripture Reading', 'current_streak': 14,
                'is_foundational': True,
            },
        ]):
            fb = resolve_fallback_action(self.user)
        # 14-day streak wins.
        self.assertEqual(
            fb['primary_action'], "Do your Scripture Reading now",
        )
        self.assertEqual(fb['context_reason'], "Protect your 14-day streak")

    def test_short_streak_has_no_streak_context(self):
        with self._with_habits([
            {
                'name': 'Journal', 'current_streak': 1,
                'is_foundational': True,
            },
        ]):
            fb = resolve_fallback_action(self.user)
        self.assertEqual(fb['primary_action'], "Do your Journal now")
        # Streak < 3 — context suppressed.
        self.assertIsNone(fb['context_reason'])

    def test_no_habits_returns_final_default(self):
        with self._with_habits([]):
            fb = resolve_fallback_action(self.user)
        # Phase 19.4: default may carry a time-of-day suffix, but
        # always leads with the bare anchor string.
        self.assertTrue(
            fb['primary_action'].startswith(_FINAL_DEFAULT_ACTION),
            f"expected prefix {_FINAL_DEFAULT_ACTION!r}, got "
            f"{fb['primary_action']!r}",
        )
        self.assertIsNone(fb['context_reason'])

    def test_sae_exception_falls_back_to_final_default(self):
        with patch(
            'apps.core.ai_state.state_engine.get_module_state',
            side_effect=RuntimeError("SAE broken"),
        ):
            fb = resolve_fallback_action(self.user)
        self.assertTrue(
            fb['primary_action'].startswith(_FINAL_DEFAULT_ACTION),
        )


class FallbackResolverContractTests(SimpleTestCase):
    """Every resolver output must satisfy the one-action contract:
    no categories, no multi-option lists, no debug leakage."""

    _FORBIDDEN_FRAGMENTS = (
        # Multi-option markers that existed in the pre-19.3 fallback.
        ", or a quick journal entry",
        "prayer, movement,",
        "highest-priority foundational habit",
        # Debug line that also existed.
        "Decision-query fallback",
        "no concrete focus surfaced",
    )

    def test_final_default_has_no_forbidden_fragments(self):
        for fragment in self._FORBIDDEN_FRAGMENTS:
            self.assertNotIn(fragment, _FINAL_DEFAULT_ACTION)

    def test_final_default_is_concrete_and_singular(self):
        # Must be a single imperative sentence, not a list.
        self.assertNotIn(",", _FINAL_DEFAULT_ACTION)
        self.assertNotIn(" or ", _FINAL_DEFAULT_ACTION)
        # Starts with an imperative verb.
        self.assertTrue(
            _FINAL_DEFAULT_ACTION.split()[0] in (
                "Take", "Do", "Start", "Pray", "Write", "Pause",
            ),
            f"final default must start with an imperative, got "
            f"{_FINAL_DEFAULT_ACTION!r}",
        )


# ───────────────────────────────────────────────────────────────
# Integration: _build_focus_query_response never returns the old
# multi-option fallback, even with empty state.
# ───────────────────────────────────────────────────────────────

class BuildFocusQueryEmptyStateTests(TestCase):
    """Empty execution state + no habits → resolver fires, single
    concrete action surfaces."""

    def setUp(self):
        self.user = _make_user("empty_fallback@test.com")

    def test_no_exec_items_no_habits_returns_final_default(self):
        from apps.core.ai_state import state_builder
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution([])},
        ), patch(
            'apps.core.ai_state.state_engine.get_module_state',
            return_value={},
        ), patch(
            'apps.ai.deterministic_router._is_late_evening',
            return_value=False,
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn(_FINAL_DEFAULT_ACTION, resp)
        # No category / multi-option fallback.
        self.assertNotIn("highest-priority foundational habit", resp)
        self.assertNotIn("prayer, movement", resp)
        self.assertNotIn("or a quick journal entry", resp)
        self.assertNotIn("Decision-query fallback", resp)

    def test_no_exec_items_with_habits_surfaces_the_habit(self):
        from apps.core.ai_state import state_builder

        def fake_state(user, module):
            if module == 'habits':
                return {
                    'active_habit_count': 1,
                    'streaks_per_habit': [{
                        'name': 'Daily Prayer',
                        'current_streak': 7,
                        'is_foundational': True,
                    }],
                }
            return {}

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution([])},
        ), patch(
            'apps.core.ai_state.state_engine.get_module_state',
            side_effect=fake_state,
        ), patch(
            'apps.ai.deterministic_router._is_late_evening',
            return_value=False,
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("Do your Daily Prayer now", resp)
        # No multi-option wording — exactly one habit surfaced.
        self.assertNotIn(" or ", resp)
        self.assertNotIn(",", resp.split("\n")[0])


class TimeAwareFinalDefaultTests(SimpleTestCase):
    """Phase 19.4 — optional time-of-day suffix on the final default.

    The default never becomes a multi-option string. It only adds
    a short purpose clause using an em-dash.
    """

    def _at_hour(self, hour):
        from unittest.mock import MagicMock
        fake_now = datetime(2026, 4, 22, hour, 0)
        return patch(
            "apps.core.utils.get_user_now", return_value=fake_now,
        ), MagicMock()

    def test_morning_adds_set_the_tone(self):
        ctx, user = self._at_hour(8)
        with ctx:
            out = _time_aware_final_default(user)
        self.assertEqual(
            out, "Pause and pray now — set the tone for your day",
        )

    def test_evening_adds_close_out(self):
        ctx, user = self._at_hour(21)
        with ctx:
            out = _time_aware_final_default(user)
        self.assertEqual(
            out, "Pause and pray now — close out your day",
        )

    def test_early_morning_counts_as_evening_window(self):
        # The late-evening window wraps past midnight (< 5) so the
        # close-out phrasing is appropriate at 3am.
        ctx, user = self._at_hour(3)
        with ctx:
            out = _time_aware_final_default(user)
        self.assertEqual(
            out, "Pause and pray now — close out your day",
        )

    def test_midday_returns_bare_anchor(self):
        ctx, user = self._at_hour(14)
        with ctx:
            out = _time_aware_final_default(user)
        self.assertEqual(out, _FINAL_DEFAULT_ACTION)

    def test_morning_boundary_inclusive_at_5(self):
        ctx, user = self._at_hour(5)
        with ctx:
            out = _time_aware_final_default(user)
        self.assertTrue(out.endswith("set the tone for your day"))

    def test_morning_boundary_exclusive_at_12(self):
        ctx, user = self._at_hour(12)
        with ctx:
            out = _time_aware_final_default(user)
        self.assertEqual(out, _FINAL_DEFAULT_ACTION)

    def test_time_lookup_exception_falls_back_to_bare_anchor(self):
        from unittest.mock import MagicMock
        with patch(
            "apps.core.utils.get_user_now",
            side_effect=RuntimeError("tz broken"),
        ):
            out = _time_aware_final_default(MagicMock())
        self.assertEqual(out, _FINAL_DEFAULT_ACTION)

    def test_all_time_aware_variants_are_singular(self):
        """Every variant is still a single action — no 'or', no
        multi-option commas."""
        for hour in (3, 5, 8, 11, 12, 14, 19, 20, 23):
            with patch(
                "apps.core.utils.get_user_now",
                return_value=datetime(2026, 4, 22, hour, 0),
            ):
                from unittest.mock import MagicMock
                out = _time_aware_final_default(MagicMock())
            self.assertNotIn(" or ", out, f"hour={hour}: {out!r}")
            self.assertNotIn(",", out, f"hour={hour}: {out!r}")
            self.assertTrue(
                out.startswith("Pause and pray now"),
                f"hour={hour}: {out!r}",
            )


class TryDecisionRouteFallbackTests(TestCase):
    """_SAFE_FALLBACK in _try_decision_query_route must also use the
    resolver — no multi-option wording, no debug text."""

    def setUp(self):
        self.user = _make_user("route_fallback@test.com")

    def test_safe_fallback_on_handler_failure_is_concrete(self):
        # Force both primary handlers to raise so the route falls
        # into the _SAFE_FALLBACK path.
        with patch(
            "apps.ai.deterministic_router._build_biggest_risk_response",
            side_effect=RuntimeError("boom"),
        ), patch(
            "apps.ai.deterministic_router._build_focus_query_response",
            side_effect=RuntimeError("boom"),
        ), patch(
            "apps.ai.deterministic_router._build_fix_first_response",
            side_effect=RuntimeError("boom"),
        ):
            r = _try_decision_query_route(
                "what should i do right now", self.user,
            )

        self.assertIsNotNone(r)
        self.assertTrue(r.is_terminal)
        # Contract: no multi-option / debug fallback, no category.
        self.assertNotIn("highest-priority foundational habit", r.response)
        self.assertNotIn("prayer, movement", r.response)
        self.assertNotIn("or a quick journal entry", r.response)
        self.assertNotIn("Decision-query fallback", r.response)
        self.assertNotIn("no concrete focus surfaced", r.response)
