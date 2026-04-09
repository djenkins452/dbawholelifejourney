"""
Phase 9 — Execution-First Decision Selection tests.

Verifies that the decision selector (_build_focus_query_response)
follows the strict priority stack:

    1. OVERDUE items (always win)
    2. UPCOMING items (0-90 min out)
    3. FOUNDATIONAL execution gaps (required items not done)
    4. ONLY THEN → signal-based focus

Time relevance overrides signal priority. A lower-priority task
happening now always beats a higher-priority trend happening later.

Also verifies the time-horizon validator (Rule 0-d) that rejects
future-tense actions when today's items exist.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase

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
    """Return a fake execution builder that produces the given items."""
    def builder(user):
        return {'items': items, 'summaries': {}}
    return builder


def _item(title, time_status, importance='foundational',
          scheduled_time='06:00', completed=False):
    return {
        'source_type': 'test',
        'source_id': 1,
        'title': title,
        'domain': 'test',
        'importance': importance,
        'time_status': time_status,
        'scheduled_time': scheduled_time,
        'grace_minutes': 15,
        'completion_status': 'done' if completed else 'pending',
        'completed_today': completed,
    }


# ══════════════════════════════════════════════════════════════
# Priority 1: OVERDUE wins over signals
# ══════════════════════════════════════════════════════════════

class OverdueOverridesSignalTests(TestCase):
    """When overdue items exist AND a high-priority signal exists,
    the system must pick the overdue item — not the signal."""

    def setUp(self):
        self.user = _make_user("overdue_wins@test.com")

    def test_overdue_task_selected_over_high_confidence_signal(self):
        """An overdue execution item must beat a 97% confidence signal.
        Phase 10 refinement: 'Wake up' is an implied-done status toggle
        so 'Prayer Time' (the next actionable item) is selected."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Wake up", "overdue", "foundational", "05:00"),
            _item("Prayer Time", "overdue", "foundational", "05:30"),
            _item("Workout", "upcoming", "foundational", "06:15"),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # Phase 10: "Wake up" is filtered out (implied-done); the
        # next valid overdue item (Prayer Time) is selected.
        self.assertIn("Prayer Time", resp)
        self.assertTrue(resp.startswith("Do this next:"))
        self.assertIn("overdue", resp.lower())
        # Must NOT contain signal-layer actions like "Log a meal"
        self.assertNotIn("Log a meal", resp)
        self.assertNotIn("macro", resp.lower())
        self.assertNotIn("wind-down", resp.lower())

    def test_overdue_selects_foundational_over_flexible(self):
        """Foundational overdue item beats a flexible overdue item."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Empty dishwasher", "overdue", "flexible", "05:00"),
            _item("Prayer Time", "overdue", "foundational", "05:30"),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # Foundational should come first even though dishwasher was
        # scheduled earlier.
        self.assertIn("Prayer Time", resp)

    def test_multiple_overdue_shows_count_in_reason(self):
        """Phase 10: 'Wake up' is filtered (implied-done), so only
        Prayer + Bible remain. The reason block should show '1 more'."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Wake up", "overdue", "foundational", "05:00"),
            _item("Prayer", "overdue", "foundational", "05:30"),
            _item("Bible", "overdue", "foundational", "05:45"),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # Phase 10: Wake up filtered → Prayer selected → 1 more (Bible)
        self.assertIn("Prayer", resp)
        self.assertIn("1 more", resp)
        self.assertIn("Bible", resp)


# ══════════════════════════════════════════════════════════════
# Priority 2: UPCOMING when no overdue
# ══════════════════════════════════════════════════════════════

class UpcomingSelectedWhenNoOverdueTests(TestCase):
    def setUp(self):
        self.user = _make_user("upcoming@test.com")

    def test_upcoming_item_selected(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Workout", "upcoming", "foundational", "06:15"),
            _item("Shower", "upcoming", "important", "07:00"),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("Workout", resp)
        self.assertTrue(resp.startswith("Do this next:"))
        self.assertIn("Nothing is overdue", resp)


# ══════════════════════════════════════════════════════════════
# Priority 3: FOUNDATIONAL gap when no schedule pressure
# ══════════════════════════════════════════════════════════════

class FoundationalGapSelectedTests(TestCase):
    def setUp(self):
        self.user = _make_user("foundational_gap@test.com")

    def test_incomplete_foundational_item_selected(self):
        """When no overdue, no upcoming, but there's an incomplete
        foundational item — pick it."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Wake up", "past", "foundational", "05:00", completed=True),
            _item("Journal", "past", "foundational", "20:00", completed=False),
        ]

        # "past" time_status items don't match overdue or upcoming checks
        # (they are only "overdue" when specifically flagged). But
        # completed_today=False means they're execution gaps. However
        # our code only considers overdue/upcoming/in_progress for
        # priority 1/2. For priority 3, ALL incomplete items qualify.
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("Journal", resp)
        self.assertIn("foundational", resp.lower())


# ══════════════════════════════════════════════════════════════
# Priority 4: SIGNAL only when no execution items
# ══════════════════════════════════════════════════════════════

class SignalOnlyWhenNoExecutionItemsTests(TestCase):
    def setUp(self):
        self.user = _make_user("signal_only@test.com")

    def test_signal_focus_when_all_complete(self):
        """When every execution item is completed_today, the signal
        layer fires. This is the only case where signal-based focus
        like 'Log a meal or check your macro targets' is appropriate."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Wake up", "past", "foundational", "05:00", completed=True),
            _item("Prayer", "past", "foundational", "05:30", completed=True),
            _item("Workout", "past", "foundational", "06:15", completed=True),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertTrue(resp.startswith("Do this next:"))
        # The signal layer should fire. The exact action depends on
        # the user's trust reports. We just verify the execution
        # layer didn't produce the action (none of the item titles).
        self.assertNotIn("Wake up", resp)
        self.assertNotIn("Prayer", resp)

    def test_signal_focus_when_no_execution_items(self):
        """Empty execution list → signal layer fires."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution([])},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertTrue(resp.startswith("Do this next:"))


# ══════════════════════════════════════════════════════════════
# Time-horizon validation (Rule 0-d)
# ══════════════════════════════════════════════════════════════

class TimeHorizonValidatorTests(TestCase):
    """Rule 0-d: if the first action line references future-tense
    words ('tonight', 'tomorrow', 'wind-down'), reject — even if
    the format is otherwise valid Action-First."""

    def _validate(self, text, is_decision=True):
        from apps.ai.deterministic_router import validate_response
        return validate_response(text, is_decision_query=is_decision)

    def test_rejects_wind_down_tonight(self):
        ok, reason = self._validate(
            "Do this next: Plan an earlier wind-down tonight.\n\n"
            "Reason:\nSleep trend is declining.",
        )
        self.assertFalse(ok)
        self.assertIn("time-horizon", reason)

    def test_rejects_tomorrow(self):
        ok, reason = self._validate(
            "Do this next: Try a new routine tomorrow.\n\n"
            "Reason:\nYour routines need adjustment.",
        )
        self.assertFalse(ok)
        self.assertIn("time-horizon", reason)

    def test_accepts_now_action(self):
        ok, reason = self._validate(
            "Do this next: Start Wake up.\n\n"
            "Reason:\nWake up (scheduled at 05:00) is overdue.",
        )
        self.assertTrue(ok, f"expected ok, got: {reason}")

    def test_accepts_current_task(self):
        ok, reason = self._validate(
            "Do this next: Take your morning medications.\n\n"
            "Reason:\n0 of 4 morning meds taken so far.",
        )
        self.assertTrue(ok, f"expected ok, got: {reason}")

    def test_future_words_ok_in_non_decision_query(self):
        """Time-horizon rule only applies to decision queries."""
        ok, reason = self._validate(
            "Your sleep is at 6.2h this week (high confidence). "
            "Plan an earlier wind-down tonight. ",
            is_decision=False,
        )
        # This response has interpretive language and is long enough
        # to pass the existing rules. Time-horizon rule shouldn't fire.
        self.assertTrue(ok, f"expected ok on non-decision, got: {reason}")


# ══════════════════════════════════════════════════════════════
# Regression guards
# ══════════════════════════════════════════════════════════════

class Phase8RegressionTests(TestCase):
    """Phase 8 enforcement must still work post-Phase 9."""

    def test_action_first_format_preserved(self):
        user = _make_user("phase8_regression@test.com")
        from apps.ai.deterministic_router import _build_focus_query_response
        resp = _build_focus_query_response(user)
        self.assertTrue(
            resp.startswith("Do this next:"),
            f"Action-First format broken, got: {resp[:80]}",
        )

    def test_never_none(self):
        user = _make_user("never_none@test.com")
        from apps.ai.deterministic_router import _build_focus_query_response
        resp = _build_focus_query_response(user)
        self.assertIsNotNone(resp)
        self.assertTrue(len(resp) > 0)

    def test_decision_query_route_still_terminal(self):
        user = _make_user("route_terminal@test.com")
        from apps.ai.deterministic_router import _try_decision_query_route
        result = _try_decision_query_route("what should i do", user)
        self.assertIsNotNone(result)
        self.assertTrue(result.is_terminal)
        self.assertIn("Do this next:", result.response)

    def test_validator_still_rejects_weasel(self):
        from apps.ai.deterministic_router import validate_response
        ok, reason = validate_response(
            "Your adherence is 62%. You might want to try setting reminders.",
        )
        self.assertFalse(ok)
        self.assertIn("weasel", reason)

    def test_validator_still_rejects_generic(self):
        from apps.ai.deterministic_router import validate_response
        ok, reason = validate_response(
            "Your adherence is 62%. Keep it up!",
        )
        self.assertFalse(ok)
        self.assertIn("generic", reason)
