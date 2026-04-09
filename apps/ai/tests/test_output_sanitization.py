"""
Phase 14 — Output Sanitization tests.

Verifies that user-facing decision responses contain ONLY actionable,
relevant, current information. No internal scheduling diagnostics,
no completed items in "Next" lines, no slack/buffer calculations.
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
          execution_group_id=None, parent_title=None):
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


class NoScheduleOverlayTests(TestCase):
    """The output must never contain internal schedule diagnostics:
    'Schedule:', slack/buffer, minutes_until, or 'Next is <item>'."""

    def setUp(self):
        self.user = _make_user("no_schedule@test.com")

    def test_no_schedule_line(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Work on WLJ", scheduled_time='05:15'),
        ]
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertNotIn("Schedule:", resp)

    def test_no_slack_or_buffer(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Work on WLJ", scheduled_time='05:15'),
        ]
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertNotIn("slack", resp.lower())
        self.assertNotIn("buffer", resp.lower())
        self.assertNotIn("min remaining", resp.lower())

    def test_no_next_is_line(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Work on WLJ", scheduled_time='05:15'),
        ]
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertNotIn("Next is", resp)


class CompletedItemsNeverShownTests(TestCase):
    """Completed items must never appear in the output as suggestions
    or in 'Next' references."""

    def setUp(self):
        self.user = _make_user("no_completed@test.com")

    def test_completed_item_not_in_action(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Wake up", completed=True, scheduled_time='05:00',
                  source_type='routine_item', execution_group_id=1),
            _item("Prayer", completed=True, scheduled_time='05:30',
                  source_type='routine_item', execution_group_id=1),
            _item("Workout", scheduled_time='06:15',
                  source_type='routine_item', execution_group_id=1),
        ]
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # Wake up and Prayer are completed — must not appear as actions
        first_line = resp.split('\n')[0]
        self.assertNotIn("Wake up", first_line)
        self.assertNotIn("Prayer", first_line)
        self.assertIn("Workout", resp)


class OutputContainsOnlyActionableInfoTests(TestCase):
    """Every line in the output must serve the user's decision."""

    def setUp(self):
        self.user = _make_user("actionable_only@test.com")

    def test_output_shape_is_action_reason_priority(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _item("Work on WLJ", scheduled_time='05:15'),
        ]
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        lines = [l for l in resp.split('\n') if l.strip()]
        # First line: action
        self.assertTrue(
            lines[0].startswith("Do this next:"),
            f"expected action line, got: {lines[0]!r}",
        )
        # Must have Reason:
        self.assertIn("Reason:", resp)
        # Must NOT have any diagnostic line
        for line in lines:
            ll = line.lower()
            self.assertNotIn("schedule:", ll)
            self.assertNotIn("slack", ll)
            self.assertNotIn("buffer", ll)

    def test_all_intent_modes_are_clean(self):
        """All three intent modes must produce sanitized output."""
        from apps.ai.deterministic_router import _try_decision_query_route

        for q in [
            "what should i do right now",
            "what is my biggest risk",
            "what should i fix first",
        ]:
            r = _try_decision_query_route(q, self.user)
            self.assertIsNotNone(r)
            resp = r.response
            self.assertNotIn("Schedule:", resp)
            self.assertNotIn("slack", resp.lower())
            self.assertNotIn("buffer", resp.lower())
            self.assertNotIn("Next is", resp)
