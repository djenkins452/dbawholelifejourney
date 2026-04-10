"""
Phase 10 — Action Selection (no ambiguity) tests.

Verifies that the decision selector picks the CORRECT specific item
inside a priority bucket, not just the correct bucket. Tests the
intelligent filtering + anchor-task ranking logic added to
_build_focus_query_response.

Rules enforced:
1. Completed items never selected
2. Status-toggle routine items ("Wake up") filtered out
3. Tasks (explicit commitments) win over routine_items
4. Foundational beats flexible within each group
5. Scheduled_time is tiebreaker only
"""

from datetime import date
from unittest.mock import patch

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
    def builder(user):
        return {'items': items, 'summaries': {}}
    return builder


def _item(title, time_status='overdue', importance='foundational',
          scheduled_time='06:00', completed=False, source_type='task',
          is_foundational=True, execution_group_type='standalone',
          parent_title=None, routine_type=None):
    return {
        'source_type': source_type,
        'source_id': hash(title) % 10000,
        'title': title,
        'domain': 'life',
        'importance': importance,
        'time_status': time_status,
        'scheduled_time': scheduled_time,
        'grace_minutes': 0,
        'completion_status': 'done' if completed else 'pending',
        'completed_today': completed,
        'is_actionable': True,
        'is_foundational': is_foundational,
        'execution_group_type': execution_group_type,
        'execution_group_id': None,
        'parent_title': parent_title,
        'routine_type': routine_type,
    }


# ══════════════════════════════════════════════════════════════
# 1. Completed items never selected
# ══════════════════════════════════════════════════════════════

class CompletedItemsExcludedTests(TestCase):
    def setUp(self):
        self.user = _make_user("completed_excl@test.com")

    def test_completed_item_skipped(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Wake up", completed=True, source_type='routine_item',
                  scheduled_time='05:00'),
            _item("Work on WLJ", completed=False, scheduled_time='05:15'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("Work on WLJ", resp)
        # "Wake up" must NOT appear as the selected action
        self.assertFalse(
            resp.startswith("Do this next: Start Wake up"),
            "completed item was selected as the primary action",
        )

    def test_all_completed_falls_through(self):
        """When all overdue items are completed, the system should
        move to the next priority bucket."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Wake up", completed=True, scheduled_time='05:00'),
            _item("Prayer", completed=True, scheduled_time='05:30'),
            _item("Workout", time_status='upcoming', completed=False,
                  scheduled_time='06:15'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("Workout", resp)


# ══════════════════════════════════════════════════════════════
# 2. Anchor task (explicit commitment) wins over routine toggle
# ══════════════════════════════════════════════════════════════

class AnchorTaskSelectedTests(TestCase):
    def setUp(self):
        self.user = _make_user("anchor_task@test.com")

    def test_faith_tier_wins_over_work_tier(self):
        """Phase 18.2 governance: Prayer Time (faith, tier 0) outranks
        Work on WLJ (work, tier 2) even though Work is a task and
        Prayer is a routine_item. Governance tier is the primary sort."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Wake up", source_type='routine_item',
                  scheduled_time='05:00',
                  execution_group_type='routine',
                  parent_title='Morning Routine',
                  routine_type='binary'),
            _item("Work on WLJ", source_type='task',
                  scheduled_time='05:15'),
            _item("Prayer Time", source_type='routine_item',
                  scheduled_time='05:30',
                  execution_group_type='routine',
                  parent_title='Morning Routine',
                  routine_type='binary'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # Phase 18.2: Prayer Time (faith, tier 0) outranks Work on WLJ
        # (work, tier 2). Wake up is filtered out (implied-done).
        self.assertIn("Prayer Time", resp)

    def test_foundational_task_beats_important_task(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Church Study", importance='important',
                  scheduled_time='05:00'),
            _item("Work on WLJ", importance='foundational',
                  scheduled_time='05:15'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("Work on WLJ", resp)


# ══════════════════════════════════════════════════════════════
# 3. Status-toggle routine items filtered out
# ══════════════════════════════════════════════════════════════

class StatusToggleFilteredTests(TestCase):
    def setUp(self):
        self.user = _make_user("status_toggle@test.com")

    def test_wake_up_filtered_out(self):
        """'Wake up' is an implied-done status toggle — if the user
        is interacting with CoS, they're already awake."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Wake up", source_type='routine_item',
                  scheduled_time='05:00'),
            _item("Prayer Time", source_type='routine_item',
                  scheduled_time='05:30'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # "Wake up" must not be the selected action
        self.assertNotIn("Start Wake up", resp)
        # Prayer should be selected instead
        self.assertIn("Prayer Time", resp)

    def test_go_to_bed_filtered_out(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Go to bed", source_type='routine_item',
                  scheduled_time='22:00'),
            _item("Journal", source_type='routine_item',
                  scheduled_time='20:00', importance='flexible',
                  is_foundational=False),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertNotIn("Go to bed", resp)
        self.assertIn("Journal", resp)


# ══════════════════════════════════════════════════════════════
# 4. Sequence order: tasks before routine items
# ══════════════════════════════════════════════════════════════

class SequenceOrderTests(TestCase):
    def setUp(self):
        self.user = _make_user("sequence@test.com")

    def test_tasks_before_routine_items_same_importance(self):
        """Two foundational items — one task, one routine. Task wins."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Prayer", source_type='routine_item',
                  scheduled_time='05:00'),
            _item("Work on project", source_type='task',
                  scheduled_time='05:30'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("Work on project", resp)


# ══════════════════════════════════════════════════════════════
# 5. Real morning scenario (the user's exact test case)
# ══════════════════════════════════════════════════════════════

class RealMorningScenarioTests(TestCase):
    """Danny's exact scenario:
    - Wake up: completed (or implied-done)
    - Work on WLJ: overdue, not done
    - Prayer: overdue, not done
    - Bible: overdue, not done
    - Shower: upcoming, not done

    Expected: "Do this next: Start Work on WLJ."
    """

    def setUp(self):
        self.user = _make_user("morning_scenario@test.com")

    def test_prayer_selected_over_work(self):
        """Phase 18.2: Prayer Time (faith, tier 0) outranks Work on
        WLJ (work, tier 2) even with all items overdue."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Wake up", source_type='routine_item',
                  time_status='overdue', scheduled_time='05:00',
                  execution_group_type='routine',
                  parent_title='Morning Routine'),
            _item("Work on WLJ", source_type='task',
                  time_status='overdue', scheduled_time='05:15'),
            _item("Prayer Time", source_type='routine_item',
                  time_status='overdue', scheduled_time='05:30',
                  execution_group_type='routine',
                  parent_title='Morning Routine'),
            _item("Bible Reading", source_type='routine_item',
                  time_status='overdue', scheduled_time='05:45',
                  execution_group_type='routine',
                  parent_title='Morning Routine'),
            _item("Shower", source_type='routine_item',
                  time_status='upcoming', scheduled_time='07:00',
                  importance='important', is_foundational=False,
                  execution_group_type='routine',
                  parent_title='Morning Routine'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # Phase 18.2: Prayer Time (faith, tier 0, 05:30) outranks
        # Work on WLJ (work, tier 2, 05:15). Wake up filtered.
        self.assertIn("Prayer Time", resp)
        self.assertIn("overdue", resp.lower())
        self.assertNotIn("Start Wake up", resp)
        self.assertNotIn("Start Shower", resp)

    def test_with_wake_up_explicitly_completed(self):
        """With Wake up completed, Prayer Time (faith) still wins."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Wake up", source_type='routine_item',
                  time_status='overdue', scheduled_time='05:00',
                  completed=True),
            _item("Work on WLJ", source_type='task',
                  time_status='overdue', scheduled_time='05:15'),
            _item("Prayer Time", source_type='routine_item',
                  time_status='overdue', scheduled_time='05:30'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("Prayer Time", resp)


# ══════════════════════════════════════════════════════════════
# Regression guards
# ══════════════════════════════════════════════════════════════

class Phase9RegressionTests(TestCase):
    def test_action_first_format_preserved(self):
        user = _make_user("p9_regression@test.com")
        from apps.ai.deterministic_router import _build_focus_query_response
        resp = _build_focus_query_response(user)
        self.assertTrue(resp.startswith("Do this next:"))

    def test_never_none(self):
        user = _make_user("p9_never_none@test.com")
        from apps.ai.deterministic_router import _build_focus_query_response
        resp = _build_focus_query_response(user)
        self.assertIsNotNone(resp)
        self.assertTrue(len(resp) > 0)

    def test_overdue_still_beats_signal(self):
        """Phase 9 overdue-over-signal rule must still hold."""
        user = _make_user("p9_overdue_signal@test.com")
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Work on WLJ", source_type='task',
                  time_status='overdue', scheduled_time='05:15'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(user)

        self.assertIn("Work on WLJ", resp)
        self.assertNotIn("macro", resp.lower())
        self.assertNotIn("wind-down", resp.lower())
