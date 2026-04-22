"""
Phase 12 — Dependency-Aware Action Selection tests.

Verifies that the selector respects routine sequence dependencies:
items in the same execution_group_id (routine) have an implied
order by scheduled_time. A later item is BLOCKED if an earlier
item in the same group is still incomplete.

Example: Shower (07:00) is blocked by Workout (06:15) in the
Morning Routine group. Even if Shower is overdue, it cannot be
the primary action while Workout is pending.
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
          scheduled_time='06:00', completed=False, source_type='routine_item',
          execution_group_id=1, parent_title='Morning Routine'):
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
        'is_foundational': importance == 'foundational',
        'execution_group_type': 'routine' if execution_group_id else 'standalone',
        'execution_group_id': execution_group_id,
        'parent_title': parent_title,
    }


class ShowerBlockedByWorkoutTests(TestCase):
    """The canonical case: Workout is pending → Shower is blocked."""

    def setUp(self):
        self.user = _make_user("shower_blocked@test.com")

    def test_workout_selected_not_shower(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Workout and Drink Protein Shake",
                  scheduled_time='06:15'),
            _item("Shower", importance='important',
                  scheduled_time='07:00'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("Workout", resp)
        self.assertNotIn("Start Shower", resp)

    def test_shower_selectable_when_workout_complete(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Workout and Drink Protein Shake",
                  scheduled_time='06:15', completed=True),
            _item("Shower", importance='important',
                  scheduled_time='07:00'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("Shower", resp)


class FixFirstRespectsPrerequisiteTests(TestCase):
    """FIX_FIRST must also respect sequence dependencies."""

    def setUp(self):
        self.user = _make_user("fix_first_deps@test.com")

    def test_fix_first_selects_workout_not_shower(self):
        from apps.ai.deterministic_router import _build_fix_first_response
        from apps.core.ai_state import state_builder
        from apps.core.ai_orchestrator import cos_context

        items = [
            _item("Workout and Drink Protein Shake",
                  scheduled_time='06:15'),
            _item("Shower", importance='important',
                  scheduled_time='07:00'),
        ]

        def fake_fresh(user, module):
            if module == 'medicine':
                return {'expected_today': 10, 'today_taken': 8,
                        'adherence_7d': 90}
            return {}

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ), patch.object(cos_context, '_fresh_module_state', fake_fresh):
            resp = _build_fix_first_response(self.user)

        self.assertIn("Workout", resp)
        self.assertNotIn("Start Shower", resp)
        self.assertNotIn("Close this gap — complete Shower", resp)


class RealMorningSequenceTests(TestCase):
    """Danny's exact scenario:
    - Work on WLJ: complete
    - Prayer: complete
    - Bible Reading: complete
    - Workout: pending (overdue)
    - Shower: overdue but BLOCKED by Workout

    Expected: Start Workout and Drink Protein Shake."""

    def setUp(self):
        self.user = _make_user("morning_seq@test.com")

    def test_workout_selected_when_earlier_items_done(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            # Standalone task — already done
            _item("Work on WLJ", source_type='task',
                  execution_group_id=None, parent_title=None,
                  scheduled_time='05:15', completed=True),
            # Morning routine — first 3 done
            _item("Prayer Time", scheduled_time='05:30',
                  completed=True),
            _item("Bible Reading", scheduled_time='05:45',
                  completed=True),
            # Workout is the gate — NOT done
            _item("Workout and Drink Protein Shake",
                  scheduled_time='06:15'),
            # Shower is blocked by Workout
            _item("Shower", importance='important',
                  scheduled_time='07:00'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # Phase 19.2: "Start" → "Go straight into".
        self.assertTrue(
            "Workout" in resp and "Go straight into" in resp,
            f"Expected Workout selection, got: {resp[:120]!r}",
        )
        self.assertNotIn("Start Shower", resp)
        self.assertNotIn("Go straight into Shower", resp)

    def test_all_morning_done_falls_through(self):
        """When the entire morning routine is complete, the selector
        should move to other buckets (upcoming/signal)."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Work on WLJ", source_type='task',
                  execution_group_id=None, parent_title=None,
                  scheduled_time='05:15', completed=True),
            _item("Prayer Time", scheduled_time='05:30',
                  completed=True),
            _item("Bible Reading", scheduled_time='05:45',
                  completed=True),
            _item("Workout and Drink Protein Shake",
                  scheduled_time='06:15', completed=True),
            _item("Shower", importance='important',
                  scheduled_time='07:00', completed=True),
            # Evening item — upcoming
            _item("Log Nutrition", time_status='upcoming',
                  execution_group_id=2, parent_title='Evening',
                  scheduled_time='18:00'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # Should NOT select any morning items (all complete)
        self.assertNotIn("Prayer", resp)
        self.assertNotIn("Workout", resp)
        self.assertNotIn("Shower", resp)


class StandaloneTasksNeverBlockedTests(TestCase):
    """Standalone tasks (no execution_group_id) have no predecessors
    and should never be blocked."""

    def setUp(self):
        self.user = _make_user("standalone@test.com")

    def test_standalone_task_always_selectable(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            # Routine group with pending items
            _item("Prayer Time", scheduled_time='05:30'),
            _item("Shower", importance='important',
                  scheduled_time='07:00'),
            # Standalone task — should NOT be blocked by routine
            _item("Work on WLJ", source_type='task',
                  execution_group_id=None, parent_title=None,
                  scheduled_time='05:15'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # Standalone task should win (task > routine_item rank)
        self.assertIn("Work on WLJ", resp)


class MultipleRoutineGroupsTests(TestCase):
    """Items in different routine groups don't block each other."""

    def setUp(self):
        self.user = _make_user("multi_group@test.com")

    def test_evening_item_not_blocked_by_morning_item(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            # Morning routine — incomplete
            _item("Workout", scheduled_time='06:15',
                  execution_group_id=1),
            _item("Shower", importance='important',
                  scheduled_time='07:00',
                  execution_group_id=1),
            # Evening routine — independent group
            _item("Log Nutrition", time_status='overdue',
                  scheduled_time='18:00',
                  execution_group_id=2,
                  parent_title='Evening'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # Workout (group 1, earliest) should be selected
        self.assertIn("Workout", resp)
        # But Log Nutrition (group 2) should NOT be blocked
        # by Workout (different group) — it should appear in
        # the "also behind" list if applicable
