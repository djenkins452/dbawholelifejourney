"""
Tests for build_locked_next_action — CoS Time/Sequence Integrity.

These tests enforce the contract documented in
`apps/core/execution/active_block.py`:

  - "Start with X" eligibility is restricted to overdue + now urgencies.
  - 'next' (within ~2h) appears only as follow-on context.
  - Items outside the active execution block are not primary even when
    scheduled within 30 min of now.
  - Behind-schedule users see overdue first; future blocks never override.

Regression scenario (NON-NEGOTIABLE):
  At 07:55, with a Measurements routine at 08:00 and a Fish Oil
  supplement at 09:00, the locked next action MUST start with
  Measurements. Fish Oil may be a follow-on or appear in an upcoming
  hint — but it MUST NOT be the "Start with X" recommendation.
"""

from datetime import date, datetime, time
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


def _routine_item(title, scheduled_time, time_status='upcoming',
                  is_foundational=False, completed=False):
    return {
        'source_type': 'routine_item',
        'source_id': abs(hash(title)) % 100000,
        'title': title,
        'domain': 'life',
        'importance': 'foundational' if is_foundational else 'flexible',
        'time_status': time_status,
        'scheduled_time': scheduled_time,
        'grace_minutes': 0,
        'completion_status': 'done' if completed else 'pending',
        'completed_today': completed,
        'is_actionable': not completed,
        'is_foundational': is_foundational,
        'execution_group_type': 'routine',
        'execution_group_id': 1,
        'parent_title': 'Test Routine',
        'toggle_url': '/dashboard/v2/routine/1/toggle/',
        'detail_url': '/life/routines/',
        'routine_type': 'binary',
        'activity_type': None,
    }


def _supplement_item(title, scheduled_time, window='mid_morning',
                     time_status='upcoming', is_foundational=True,
                     completed=False):
    return {
        'source_type': 'supplement_dose',
        'source_id': abs(hash(title)) % 100000,
        'title': title,
        'domain': 'health',
        'importance': 'foundational' if is_foundational else 'flexible',
        'time_status': time_status,
        'scheduled_time': scheduled_time,
        'grace_minutes': 0,
        'completion_status': 'done' if completed else 'pending',
        'completed_today': completed,
        'is_actionable': not completed,
        'is_foundational': is_foundational,
        'execution_group_type': 'supplement_window',
        'execution_group_id': window,
        'parent_title': window.replace('_', ' ').title(),
        'detail_url': '/health/intake/',
    }


def _patch_pipeline(user, items, now_dt):
    """Patch get_user_now and build_today_execution for build_locked_next_action.

    `now` is passed explicitly to get_active_block so its lazy
    `get_user_now` import never fires — no patch needed there.
    """
    return [
        patch(
            'apps.core.utils.get_user_now',
            return_value=now_dt,
        ),
        patch(
            'apps.core.execution.today_execution.build_today_execution',
            return_value={'items': items, 'summaries': {}},
        ),
    ]


def _run_with_patches(patches, fn):
    started = [p.start() for p in patches]
    try:
        return fn()
    finally:
        for p in patches:
            p.stop()


# ══════════════════════════════════════════════════════════════════════
# Scenario 1 (REGRESSION): 07:55 — Measurements at 08:00, Fish Oil at 09:00
# ══════════════════════════════════════════════════════════════════════

class Scenario1_MorningSequenceTests(TestCase):
    """The exact failure case from the bug report."""

    def setUp(self):
        self.user = _make_user("scenario1@test.com")

    def test_at_07_55_start_with_measurements_not_fish_oil(self):
        from apps.ai.cos_fact_statements import build_locked_next_action

        items = [
            _routine_item('Measurements', '08:00',
                          time_status='upcoming',
                          is_foundational=False),
            _supplement_item('Fish Oil', '09:00',
                             window='morning',
                             time_status='upcoming',
                             is_foundational=True),
        ]
        now_dt = datetime.combine(date.today(), time(7, 55))

        patches = _patch_pipeline(self.user, items, now_dt)
        result = _run_with_patches(
            patches,
            lambda: build_locked_next_action(self.user),
        )

        # NON-NEGOTIABLE: primary recommendation is Measurements.
        self.assertIn('Measurements', result,
                      f"Expected Measurements as primary; got: {result!r}")
        self.assertTrue(
            result.startswith('Start with Measurements'),
            f"Primary must be 'Start with Measurements...'; got: {result!r}",
        )

        # Fish Oil MUST NOT be the "Start with" recommendation.
        self.assertFalse(
            result.startswith('Start with Fish Oil'),
            f"Fish Oil must not be primary; got: {result!r}",
        )


# ══════════════════════════════════════════════════════════════════════
# Scenario 2: 08:50 — within lead-in to 09:00 mid_morning items
# ══════════════════════════════════════════════════════════════════════

class Scenario2_LeadInTests(TestCase):
    """At 08:50, 09:00 intake may begin to be referenced."""

    def setUp(self):
        self.user = _make_user("scenario2@test.com")

    def test_at_08_50_intake_referenced_when_morning_clear(self):
        from apps.ai.cos_fact_statements import build_locked_next_action

        items = [
            # Morning items already done
            _routine_item('Measurements', '08:00',
                          time_status='done', completed=True),
            # 09:00 supplement (still in 'morning' canonical [5,10)).
            # Supplements surface to the prioritizer as a window-grouped
            # intake action, so the title is the window label ("Morning"),
            # not the individual supplement name.
            _supplement_item('Fish Oil', '09:00',
                             window='morning',
                             time_status='upcoming',
                             is_foundational=True),
        ]
        now_dt = datetime.combine(date.today(), time(8, 50))

        patches = _patch_pipeline(self.user, items, now_dt)
        result = _run_with_patches(
            patches,
            lambda: build_locked_next_action(self.user),
        )

        # 09:00 intake group is delta=10min → "now" urgency, in active
        # morning block — it IS the right primary at 08:50.
        self.assertTrue(
            result.startswith('Start with Morning'),
            f"Expected morning intake group as primary at 08:50; "
            f"got: {result!r}",
        )


# ══════════════════════════════════════════════════════════════════════
# Scenario 3: Multiple intake windows — only the correct one shows
# ══════════════════════════════════════════════════════════════════════

class Scenario3_MultiWindowIntakeTests(TestCase):
    """At 08:00, only the morning intake should drive the recommendation —
    the 18:00 evening intake must not be primary."""

    def setUp(self):
        self.user = _make_user("scenario3@test.com")

    def test_morning_intake_chosen_over_evening_at_08_00(self):
        from apps.ai.cos_fact_statements import build_locked_next_action

        # Window labels become the action title (intake is grouped).
        items = [
            _supplement_item('Morning Fish Oil', '08:30',
                             window='morning',
                             time_status='upcoming',
                             is_foundational=True),
            _supplement_item('Evening Fish Oil', '18:00',
                             window='evening',
                             time_status='upcoming',
                             is_foundational=True),
        ]
        now_dt = datetime.combine(date.today(), time(8, 0))

        patches = _patch_pipeline(self.user, items, now_dt)
        result = _run_with_patches(
            patches,
            lambda: build_locked_next_action(self.user),
        )

        # 08:30 supplement is delta=30 → "now" → eligible primary.
        # Group title is the window label "Morning".
        self.assertTrue(
            result.startswith('Start with Morning'),
            f"Expected Morning intake group primary; got: {result!r}",
        )
        # Evening (18:00) is "upcoming" and far outside the morning block —
        # must not be primary, must not appear as a follow-on.
        self.assertNotIn('Evening', result,
                         f"Evening intake must not surface at 08:00; "
                         f"got: {result!r}")


# ══════════════════════════════════════════════════════════════════════
# Scenario 4: Behind schedule — overdue takes priority, no future skip
# ══════════════════════════════════════════════════════════════════════

class Scenario4_OverduePriorityTests(TestCase):
    def setUp(self):
        self.user = _make_user("scenario4@test.com")

    def test_overdue_morning_routine_wins_at_10_30(self):
        from apps.ai.cos_fact_statements import build_locked_next_action

        items = [
            _routine_item('Morning Prayer', '06:00',
                          time_status='overdue',
                          is_foundational=True),
            _supplement_item('Mid-morning Vitamin', '10:30',
                             window='mid_morning',
                             time_status='upcoming',
                             is_foundational=True),
        ]
        # 10:30 = 'mid_morning' canonical block
        now_dt = datetime.combine(date.today(), time(10, 30))

        patches = _patch_pipeline(self.user, items, now_dt)
        result = _run_with_patches(
            patches,
            lambda: build_locked_next_action(self.user),
        )

        # Overdue must be primary; future block never overrides.
        self.assertTrue(
            result.startswith('Start with Morning Prayer'),
            f"Overdue must be primary; got: {result!r}",
        )

    def test_future_block_does_not_jump_unfinished_current_block(self):
        """At 09:55 (in 'morning' canonical [5,10)): an unfinished 09:30
        morning item must beat a 10:30 mid_morning item, even if mid_morning
        is in lead-in."""
        from apps.ai.cos_fact_statements import build_locked_next_action

        items = [
            _routine_item('Stretch', '09:30',
                          time_status='upcoming',
                          is_foundational=False),
            _supplement_item('Mid-morning Vitamin', '10:30',
                             window='mid_morning',
                             time_status='upcoming',
                             is_foundational=True),
        ]
        now_dt = datetime.combine(date.today(), time(9, 55))

        patches = _patch_pipeline(self.user, items, now_dt)
        result = _run_with_patches(
            patches,
            lambda: build_locked_next_action(self.user),
        )

        # Stretch at 09:30 is overdue (delta=-25), so it wins as overdue.
        # Even if not overdue, it's at urgency 'now' (delta within ±30).
        # Mid-morning vitamin is at 10:30 (delta=35) → "next" → not primary.
        self.assertTrue(
            result.startswith('Start with Stretch'),
            f"Current-block unfinished item must win; got: {result!r}",
        )
        # Vitamin must not lead even though it's foundational.
        self.assertFalse(
            result.startswith('Start with Mid-morning Vitamin'),
            f"Foundational future-block item must not jump; got: {result!r}",
        )


# ══════════════════════════════════════════════════════════════════════
# Out-of-window primary eligibility — extra invariant
# ══════════════════════════════════════════════════════════════════════

class FollowOnContextTests(TestCase):
    def setUp(self):
        self.user = _make_user("followon@test.com")

    def test_clear_now_surfaces_next_upcoming(self):
        """When nothing is in the now/overdue window, surface forward
        context — 'You're clear right now. Next up is X at HH:MM.'"""
        from apps.ai.cos_fact_statements import build_locked_next_action

        items = [
            # Something far in the future only
            _supplement_item('Evening Vitamin', '18:00',
                             window='evening',
                             time_status='upcoming',
                             is_foundational=True),
        ]
        now_dt = datetime.combine(date.today(), time(8, 0))

        patches = _patch_pipeline(self.user, items, now_dt)
        result = _run_with_patches(
            patches,
            lambda: build_locked_next_action(self.user),
        )

        self.assertIn("clear right now", result.lower(),
                      f"Expected 'clear right now' phrasing; got: {result!r}")
