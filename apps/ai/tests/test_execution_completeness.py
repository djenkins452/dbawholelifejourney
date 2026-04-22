"""
Phase 15 — Execution Completeness tests.

Verifies that medications and supplements are never incorrectly
blocked by the routine-sequence filter. Medication/supplement
windows are PARALLEL (all items independently actionable), not
sequential like routine groups.

Key bug: _filter_blocked was treating medication_window and
supplement_window groups the same as routine groups, causing all
morning meds/supps to be blocked by the earliest-scheduled
supplement (Perfect Amino at 05:45) even though they have no
dependency on each other.
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


def _routine_item(title, scheduled_time, completed=False,
                  importance='foundational', group_id=1):
    return {
        'source_type': 'routine_item',
        'source_id': hash(title) % 10000,
        'title': title,
        'domain': 'life',
        'importance': importance,
        'time_status': 'overdue',
        'scheduled_time': scheduled_time,
        'completed_today': completed,
        'is_actionable': True,
        'is_foundational': importance == 'foundational',
        'execution_group_type': 'routine',
        'execution_group_id': group_id,
        'parent_title': 'Morning Routine',
    }


def _med_dose(title, scheduled_time, completed=False,
              group_id='morning', group_type='medication_window',
              importance='foundational'):
    return {
        'source_type': 'medication_dose',
        'source_id': hash(title) % 10000,
        'title': title,
        'domain': 'health',
        'importance': importance,
        'time_status': 'overdue',
        'scheduled_time': scheduled_time,
        'completed_today': completed,
        'is_actionable': True,
        'is_foundational': importance == 'foundational',
        'execution_group_type': group_type,
        'execution_group_id': group_id,
        'parent_title': 'Morning Medications',
    }


def _supp_dose(title, scheduled_time, completed=False,
               group_id='morning', importance='standard'):
    return {
        'source_type': 'supplement_dose',
        'source_id': hash(title) % 10000,
        'title': title,
        'domain': 'health',
        'importance': importance,
        'time_status': 'overdue',
        'scheduled_time': scheduled_time,
        'completed_today': completed,
        'is_actionable': True,
        'is_foundational': False,
        'execution_group_type': 'supplement_window',
        'execution_group_id': group_id,
        'parent_title': 'Morning Supplements',
    }


class MedsNotBlockedBySequenceTests(TestCase):
    """Medications in the same window must ALL be selectable
    regardless of which one has the earliest scheduled_time."""

    def setUp(self):
        self.user = _make_user("meds_not_blocked@test.com")

    def test_creatine_selectable_when_routine_done(self):
        """The exact bug: after completing Shower, THORNE Creatine
        must be selectable — not blocked by Perfect Amino."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            # Morning routine — all done
            _routine_item("Shower", "07:00", completed=True,
                         importance='important'),
            # Morning meds/supps — Creatine is overdue
            _supp_dose("Perfect Amino", "05:45"),
            _supp_dose("THORNE Creatine", "07:15"),
            _med_dose("Mounjaro", "07:00"),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # System must select an actionable med/supp — not fall to signals
        from apps.ai.tests._cos_decision_helpers import assert_cos_action_first
        assert_cos_action_first(self, resp)
        # Must NOT fall through to signal layer (sleep trend, nutrition)
        self.assertNotIn("wind-down", resp.lower())
        self.assertNotIn("macro", resp.lower())
        self.assertNotIn("foundational task", resp)

    def test_mounjaro_not_blocked_by_perfect_amino(self):
        """Mounjaro (07:00) must not be blocked by Perfect Amino
        (05:45) — they're in the same window but are parallel."""
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _supp_dose("Perfect Amino", "05:45"),
            _med_dose("Mounjaro", "07:00"),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        # Mounjaro is foundational, Perfect Amino is standard.
        # Mounjaro should rank higher AND not be blocked.
        self.assertIn("Mounjaro", resp)


class RoutineSequenceStillEnforcedTests(TestCase):
    """Routines must STILL enforce sequence (Shower blocked by Workout)
    even after the medication fix."""

    def setUp(self):
        self.user = _make_user("routine_still_seq@test.com")

    def test_shower_still_blocked_by_workout(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _routine_item("Workout", "06:15"),
            _routine_item("Shower", "07:00", importance='important'),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        self.assertIn("Workout", resp)
        self.assertNotIn("Start Shower", resp)


class SignalLayerOnlyWhenTrulyEmptyTests(TestCase):
    """Signal layer must NEVER fire if any med/supp is pending."""

    def setUp(self):
        self.user = _make_user("never_signal_if_meds@test.com")

    def test_single_pending_supp_prevents_signal_fallthrough(self):
        from apps.ai.deterministic_router import _build_focus_query_response
        from apps.core.ai_state import state_builder

        items = [
            _supp_dose("THORNE Creatine", "07:15"),
        ]

        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ):
            resp = _build_focus_query_response(self.user)

        from apps.ai.tests._cos_decision_helpers import assert_cos_action_first
        assert_cos_action_first(self, resp, must_contain="THORNE Creatine")
