"""
Phase 16 — Quick Action Priority Override tests.

Overdue medications and supplements (≤2 minute actions) must be
selected BEFORE any task or routine item. "Knock out the 30-second
health action first, then move on."
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


def _task(title, scheduled_time='05:15'):
    return {
        'source_type': 'task',
        'source_id': hash(title) % 10000,
        'title': title,
        'domain': 'life',
        'importance': 'foundational',
        'time_status': 'overdue',
        'scheduled_time': scheduled_time,
        'completed_today': False,
        'is_actionable': True,
        'is_foundational': True,
        'execution_group_type': 'standalone',
        'execution_group_id': None,
        'parent_title': None,
    }


def _med(title, scheduled_time='07:00', importance='foundational',
         completed=False, time_status='overdue'):
    return {
        'source_type': 'medication_dose',
        'source_id': hash(title) % 10000,
        'title': title,
        'domain': 'health',
        'importance': importance,
        'time_status': time_status,
        'scheduled_time': scheduled_time,
        'completed_today': completed,
        'is_actionable': True,
        'is_foundational': importance == 'foundational',
        'execution_group_type': 'medication_window',
        'execution_group_id': 'morning',
        'parent_title': 'Morning Medications',
    }


def _supp(title, scheduled_time='07:15', completed=False,
          time_status='overdue'):
    return {
        'source_type': 'supplement_dose',
        'source_id': hash(title) % 10000,
        'title': title,
        'domain': 'health',
        'importance': 'standard',
        'time_status': time_status,
        'scheduled_time': scheduled_time,
        'completed_today': completed,
        'is_actionable': True,
        'is_foundational': False,
        'execution_group_type': 'supplement_window',
        'execution_group_id': 'morning',
        'parent_title': 'Morning Supplements',
    }


class QuickActionOverridesTaskTests(TestCase):
    """Overdue quick health actions beat overdue tasks."""

    def setUp(self):
        self.user = _make_user("quick_override@test.com")

    def test_creatine_overrides_task(self):
        """THORNE Creatine (supplement, overdue) must beat Work on WLJ
        (task, overdue, foundational) because it's a quick action."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _task("Work on WLJ"),
            _supp("THORNE Creatine"),
        ]
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("THORNE Creatine", resp)
        self.assertIn("quick", resp.lower())
        self.assertNotIn("Work on WLJ", resp.split('\n')[0])

    def test_medication_overrides_task(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _task("Work on WLJ"),
            _med("Mounjaro"),
        ]
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("Mounjaro", resp)


class MultipleQuickActionsTests(TestCase):
    """When multiple quick actions are overdue, meds before supps."""

    def setUp(self):
        self.user = _make_user("multi_quick@test.com")

    def test_med_before_supp(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _supp("THORNE Creatine", "07:15"),
            _med("Mounjaro", "07:00"),
        ]
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # Mounjaro (medication, foundational) should outrank
        # Creatine (supplement, standard)
        first_line = resp.split('\n')[0]
        self.assertIn("Mounjaro", first_line)

    def test_shows_count_of_pending(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _med("Mounjaro", "07:00"),
            _supp("THORNE Creatine", "07:15"),
            _supp("Perfect Amino", "05:45"),
        ]
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("2 more", resp)


class NoQuickActionFallsBackTests(TestCase):
    """When no quick actions exist, normal Phase 10+ logic runs."""

    def setUp(self):
        self.user = _make_user("no_quick@test.com")

    def test_no_overdue_meds_selects_task(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _task("Work on WLJ"),
            _supp("THORNE Creatine", time_status='upcoming'),  # NOT overdue
        ]
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        first_line = resp.split('\n')[0]
        self.assertIn("Work on WLJ", first_line)


class CompletedQuickActionSkippedTests(TestCase):
    """Completed meds/supps must NOT be selected."""

    def setUp(self):
        self.user = _make_user("completed_quick@test.com")

    def test_completed_supp_not_selected(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _task("Work on WLJ"),
            _supp("THORNE Creatine", completed=True),
        ]
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        first_line = resp.split('\n')[0]
        self.assertNotIn("THORNE Creatine", first_line)
        self.assertIn("Work on WLJ", first_line)


class FixFirstQuickActionTests(TestCase):
    """FIX_FIRST must also respect quick-action override."""

    def setUp(self):
        self.user = _make_user("fix_first_quick@test.com")

    def test_fix_first_selects_overdue_med(self):
        from apps.ai.deterministic_router import _build_fix_first_response
        from apps.core.ai_state import state_builder
        from apps.core.ai_orchestrator import cos_context

        items = [
            _task("Work on WLJ"),
            _med("Mounjaro"),
        ]

        def fake_fresh(user, module):
            if module == 'medicine':
                return {'expected_today': 10, 'today_taken': 5,
                        'adherence_7d': 80}
            return {}

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ), patch.object(cos_context, '_fresh_module_state', fake_fresh):
            resp = _build_fix_first_response(self.user)

        self.assertIn("Mounjaro", resp)
        self.assertIn("quick", resp.lower())
