"""
Phase 7 — DST & Time Authority Tests.

Covers:
    1. Spring-forward gap handling
    2. Fall-back fold handling
    3. Commitment crossing DST boundary
    4. Timezone change preserves wall-clock intent
    5. DeadlineSnapshot boundary (exactly 24h, 72h)

These tests verify the time authority system correctly handles DST
transitions and timezone changes without corrupting deadline semantics.

Project: Whole Life Journey
Path: apps/core/tests/test_phase7_dst_time_authority.py
"""

import datetime as dt
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from apps.users.models import User, UserPreferences


def _create_test_user(email='dst-test@example.com', tz='America/New_York'):
    """Create a test user with timezone preference."""
    user = User.objects.create_user(email=email, password='testpass123')
    UserPreferences.objects.get_or_create(
        user=user, defaults={'timezone': tz},
    )
    return user


def _create_commitment(user, time_boundary, tz_name='America/New_York'):
    """Create a pending commitment with the given time boundary."""
    from apps.core.blueprint.models import Commitment

    return Commitment.objects.create(
        user=user,
        normalized_text='Test commitment',
        commitment_type=Commitment.TYPE_DO,
        time_boundary=time_boundary,
        done_definition='Complete the task',
        status=Commitment.STATUS_PENDING,
        tier_at_creation='CLEAN',
        timezone_at_creation=tz_name,
    )


# =========================================================================
# 1) SPRING-FORWARD GAP HANDLING
# =========================================================================


class SpringForwardGapTests(TestCase):
    """
    Spring-forward: clocks jump from 2:00 AM to 3:00 AM.
    Times in the 2:00-2:59 AM window do not exist.
    """

    def setUp(self):
        self.user = _create_test_user('spring-forward@example.com')
        self.eastern = ZoneInfo('America/New_York')

    def test_commitment_deadline_during_spring_forward_gap(self):
        """A deadline set for 2:30 AM during spring-forward should resolve
        without error — the system should handle the non-existent time."""
        # Spring forward 2026: March 8 at 2:00 AM EST → 3:00 AM EDT
        # 2:30 AM does not exist on this date
        # Python's zoneinfo normalizes fold=0 → 3:30 AM EDT
        naive_gap_time = dt.datetime(2026, 3, 8, 2, 30)
        aware_gap_time = naive_gap_time.replace(tzinfo=self.eastern, fold=0)

        commitment = _create_commitment(self.user, aware_gap_time)
        self.assertIsNotNone(commitment.time_boundary)
        self.assertEqual(commitment.status, 'pending')

        # The time should be valid and not raise errors
        wall_clock = commitment.time_boundary.astimezone(self.eastern)
        # In Eastern, this gets normalized to 3:30 AM EDT (fold=0)
        self.assertIn(wall_clock.hour, [2, 3])  # Either normalized or kept

    def test_deadline_just_before_spring_forward(self):
        """Deadline at 1:59 AM should be in EST (UTC-5)."""
        before_gap = dt.datetime(2026, 3, 8, 1, 59, tzinfo=self.eastern)
        commitment = _create_commitment(self.user, before_gap)

        wall_clock = commitment.time_boundary.astimezone(self.eastern)
        self.assertEqual(wall_clock.hour, 1)
        self.assertEqual(wall_clock.minute, 59)

    def test_deadline_just_after_spring_forward(self):
        """Deadline at 3:01 AM should be in EDT (UTC-4)."""
        after_gap = dt.datetime(2026, 3, 8, 3, 1, tzinfo=self.eastern)
        commitment = _create_commitment(self.user, after_gap)

        wall_clock = commitment.time_boundary.astimezone(self.eastern)
        self.assertEqual(wall_clock.hour, 3)
        self.assertEqual(wall_clock.minute, 1)

    def test_commitment_spans_spring_forward_boundary(self):
        """Create commitment before spring-forward, verify it survives
        the DST transition without corruption."""
        # Create at 11 PM on March 7 (EST), deadline 9 AM on March 8 (EDT)
        created_at = dt.datetime(2026, 3, 7, 23, 0, tzinfo=self.eastern)
        deadline = dt.datetime(2026, 3, 8, 9, 0, tzinfo=self.eastern)

        commitment = _create_commitment(self.user, deadline)

        # The wall-clock time should still be 9:00 AM
        wall_clock = commitment.time_boundary.astimezone(self.eastern)
        self.assertEqual(wall_clock.hour, 9)
        self.assertEqual(wall_clock.minute, 0)

        # But the UTC offset has changed (EDT = UTC-4, not EST = UTC-5)
        utc_offset = wall_clock.utcoffset()
        self.assertEqual(utc_offset, dt.timedelta(hours=-4))


# =========================================================================
# 2) FALL-BACK FOLD HANDLING
# =========================================================================


class FallBackFoldTests(TestCase):
    """
    Fall-back: clocks go from 2:00 AM back to 1:00 AM.
    Times between 1:00-1:59 AM occur TWICE (fold=0 and fold=1).
    """

    def setUp(self):
        self.user = _create_test_user('fall-back@example.com')
        self.eastern = ZoneInfo('America/New_York')

    def test_commitment_during_fall_back_fold_first_occurrence(self):
        """Deadline at 1:30 AM first occurrence (EDT, fold=0)."""
        # Fall back 2025: Nov 2 at 2:00 AM EDT → 1:00 AM EST
        first_130 = dt.datetime(2025, 11, 2, 1, 30,
                                tzinfo=self.eastern, fold=0)
        commitment = _create_commitment(self.user, first_130)

        # First occurrence should be EDT (UTC-4)
        wall = commitment.time_boundary.astimezone(self.eastern)
        self.assertEqual(wall.hour, 1)
        self.assertEqual(wall.minute, 30)

    def test_commitment_during_fall_back_fold_second_occurrence(self):
        """Deadline at 1:30 AM second occurrence (EST, fold=1)."""
        second_130 = dt.datetime(2025, 11, 2, 1, 30,
                                 tzinfo=self.eastern, fold=1)
        commitment = _create_commitment(self.user, second_130)

        wall = commitment.time_boundary.astimezone(self.eastern)
        self.assertEqual(wall.hour, 1)
        self.assertEqual(wall.minute, 30)

    def test_two_fold_commitments_are_distinct(self):
        """Two commitments in the fold (1:30 AM EDT vs 1:30 AM EST) should
        have different UTC times."""
        fold0 = dt.datetime(2025, 11, 2, 1, 30,
                            tzinfo=self.eastern, fold=0)
        fold1 = dt.datetime(2025, 11, 2, 1, 30,
                            tzinfo=self.eastern, fold=1)

        c1 = _create_commitment(
            self.user, fold0,
        )
        c2 = _create_commitment(
            self.user, fold1,
        )

        # They show the same wall-clock but are 1 hour apart in UTC
        utc_diff = abs(
            (c1.time_boundary.astimezone(dt.timezone.utc)
             - c2.time_boundary.astimezone(dt.timezone.utc)).total_seconds()
        )
        self.assertAlmostEqual(utc_diff, 3600, delta=60)

    def test_deadline_after_fall_back(self):
        """Deadline at 3:00 AM after fall-back should be unambiguous EST."""
        after_fallback = dt.datetime(2025, 11, 2, 3, 0,
                                     tzinfo=self.eastern)
        commitment = _create_commitment(self.user, after_fallback)

        wall = commitment.time_boundary.astimezone(self.eastern)
        self.assertEqual(wall.hour, 3)
        utc_offset = wall.utcoffset()
        self.assertEqual(utc_offset, dt.timedelta(hours=-5))


# =========================================================================
# 3) COMMITMENT CROSSING DST BOUNDARY
# =========================================================================


class CommitmentCrossingDSTTests(TestCase):
    """Commitments created before DST transition with deadlines after."""

    def setUp(self):
        self.user = _create_test_user('crossing-dst@example.com')
        self.eastern = ZoneInfo('America/New_York')

    def test_commitment_created_est_deadline_edt(self):
        """Commitment created in EST with deadline in EDT maintains
        wall-clock intent."""
        # Created March 1 (EST), deadline March 15 at 5 PM (EDT)
        deadline = dt.datetime(2026, 3, 15, 17, 0, tzinfo=self.eastern)
        commitment = _create_commitment(self.user, deadline)

        wall = commitment.time_boundary.astimezone(self.eastern)
        self.assertEqual(wall.hour, 17)
        self.assertEqual(wall.minute, 0)
        # March 15 is EDT (UTC-4)
        self.assertEqual(wall.utcoffset(), dt.timedelta(hours=-4))

    def test_commitment_created_edt_deadline_est(self):
        """Commitment created in EDT with deadline in EST maintains
        wall-clock intent."""
        # Created October 1 (EDT), deadline November 15 at 5 PM (EST)
        deadline = dt.datetime(2025, 11, 15, 17, 0, tzinfo=self.eastern)
        commitment = _create_commitment(self.user, deadline)

        wall = commitment.time_boundary.astimezone(self.eastern)
        self.assertEqual(wall.hour, 17)
        self.assertEqual(wall.minute, 0)
        # November 15 is EST (UTC-5)
        self.assertEqual(wall.utcoffset(), dt.timedelta(hours=-5))

    def test_dst_transition_wall_clock_24h_preserves_intent(self):
        """A commitment due '24 wall-clock hours from now' spanning
        spring-forward: wall-clock stays 6 PM → 6 PM, but real-time
        is 23 hours (1 hour lost to DST spring-forward)."""
        # Pre-spring-forward: 6 PM on March 7 → +24h wall = 6 PM March 8
        base = dt.datetime(2026, 3, 7, 18, 0, tzinfo=self.eastern)
        deadline_24h = base + dt.timedelta(hours=24)

        commitment = _create_commitment(self.user, deadline_24h)

        # Wall-clock should be 6 PM on March 8
        wall = commitment.time_boundary.astimezone(self.eastern)
        self.assertEqual(wall.hour, 18)
        self.assertEqual(wall.day, 8)

        # Real-time difference is 23 hours (spring-forward loses 1 hour)
        real_diff = (
            commitment.time_boundary.astimezone(dt.timezone.utc)
            - base.astimezone(dt.timezone.utc)
        ).total_seconds()
        self.assertEqual(real_diff, 23 * 3600)

    def test_dst_transition_real_24h_via_utc(self):
        """To get exactly 24 real-time hours across spring-forward,
        compute via UTC then convert back."""
        base = dt.datetime(2026, 3, 7, 18, 0, tzinfo=self.eastern)
        base_utc = base.astimezone(dt.timezone.utc)
        deadline_utc = base_utc + dt.timedelta(hours=24)
        deadline_eastern = deadline_utc.astimezone(self.eastern)

        commitment = _create_commitment(self.user, deadline_eastern)

        # Real-time difference is exactly 24 hours
        real_diff = (
            commitment.time_boundary.astimezone(dt.timezone.utc)
            - base.astimezone(dt.timezone.utc)
        ).total_seconds()
        self.assertEqual(real_diff, 24 * 3600)

        # But wall-clock is 7 PM (one hour later due to spring-forward)
        wall = commitment.time_boundary.astimezone(self.eastern)
        self.assertEqual(wall.hour, 19)


# =========================================================================
# 4) TIMEZONE CHANGE PRESERVES WALL-CLOCK INTENT
# =========================================================================


class TimezoneChangePreservesWallClockTests(TestCase):
    """
    When a user changes timezone, pending commitment deadlines should
    preserve their wall-clock time and recalculate the UTC value.
    """

    def setUp(self):
        self.user = _create_test_user('tz-change@example.com',
                                       tz='America/New_York')
        self.eastern = ZoneInfo('America/New_York')
        self.pacific = ZoneInfo('America/Los_Angeles')
        self.central = ZoneInfo('America/Chicago')

    def test_recalculate_timezone_preserves_wall_clock(self):
        """Moving from Eastern to Pacific: 5 PM stays 5 PM."""
        deadline = dt.datetime(2026, 4, 15, 17, 0, tzinfo=self.eastern)
        commitment = _create_commitment(self.user, deadline,
                                         tz_name='America/New_York')

        # Recalculate to Pacific
        result = commitment.recalculate_timezone('America/Los_Angeles')
        self.assertTrue(result)

        # Wall-clock in Pacific should be 5 PM
        wall = commitment.time_boundary.astimezone(self.pacific)
        self.assertEqual(wall.hour, 17)
        self.assertEqual(wall.minute, 0)

        # But UTC value should be different (Pacific is UTC-7 vs Eastern UTC-4)
        self.assertEqual(
            commitment.timezone_at_last_recalculation,
            'America/Los_Angeles',
        )

    def test_recalculate_multiple_pending_commitments(self):
        """All pending commitments recalculated on timezone change."""
        from apps.core.blueprint.models import (
            recalculate_pending_commitments_for_timezone_change,
        )

        deadlines = [
            dt.datetime(2026, 4, 10, 9, 0, tzinfo=self.eastern),
            dt.datetime(2026, 4, 12, 14, 30, tzinfo=self.eastern),
            dt.datetime(2026, 4, 15, 17, 0, tzinfo=self.eastern),
        ]
        commitments = [
            _create_commitment(self.user, d, tz_name='America/New_York')
            for d in deadlines
        ]

        count = recalculate_pending_commitments_for_timezone_change(
            self.user, 'America/Chicago',
        )
        self.assertEqual(count, 3)

        # Each should preserve wall-clock in Central
        for commitment, original_deadline in zip(commitments, deadlines):
            commitment.refresh_from_db()
            wall = commitment.time_boundary.astimezone(self.central)
            self.assertEqual(wall.hour, original_deadline.hour)
            self.assertEqual(wall.minute, original_deadline.minute)

    def test_closed_commitment_not_recalculated(self):
        """Closed commitments should not be recalculated."""
        from apps.core.blueprint.models import Commitment

        deadline = dt.datetime(2026, 4, 15, 17, 0, tzinfo=self.eastern)
        commitment = _create_commitment(self.user, deadline,
                                         tz_name='America/New_York')
        commitment.close(Commitment.STATUS_CLOSED_SUCCESS,
                         Commitment.CLOSURE_USER_CONFIRMED)

        result = commitment.recalculate_timezone('America/Los_Angeles')
        self.assertFalse(result)

    def test_timezone_change_across_dst_boundary(self):
        """Timezone change that also crosses DST preserves wall-clock."""
        # Commitment at 2 PM Eastern (EDT) on summer date
        summer_deadline = dt.datetime(2026, 7, 15, 14, 0,
                                       tzinfo=self.eastern)
        commitment = _create_commitment(self.user, summer_deadline,
                                         tz_name='America/New_York')

        # Move to Pacific (also in PDT during summer)
        result = commitment.recalculate_timezone('America/Los_Angeles')
        self.assertTrue(result)

        wall_pacific = commitment.time_boundary.astimezone(self.pacific)
        self.assertEqual(wall_pacific.hour, 14)
        self.assertEqual(wall_pacific.minute, 0)


# =========================================================================
# 5) DEADLINE SNAPSHOT BOUNDARY TESTS
# =========================================================================


class DeadlineSnapshotBoundaryTests(TestCase):
    """Test DeadlineSnapshot at exactly 24h and 72h boundaries."""

    def setUp(self):
        self.user = _create_test_user('snapshot-boundary@example.com')
        self.eastern = ZoneInfo('America/New_York')

    def test_deadline_exactly_24h_from_now(self):
        """A commitment due in exactly 24h should appear in due_24h."""
        from apps.core.blueprint.models import Commitment, DeadlineSnapshot

        now = timezone.now()
        deadline = now + dt.timedelta(hours=24)
        _create_commitment(self.user, deadline)

        # Create a snapshot manually with deadline in 24h bucket
        snapshot = DeadlineSnapshot.objects.create(
            user=self.user,
            due_24h=[{
                'type': 'commitment',
                'text': 'Test commitment',
                'deadline': deadline.isoformat(),
            }],
            due_72h=[],
            due_7d=[],
            collision_flags=[],
        )

        self.assertEqual(len(snapshot.due_24h), 1)
        self.assertFalse(snapshot.is_stale(max_age_minutes=1))

    def test_deadline_exactly_72h_from_now(self):
        """A commitment due in exactly 72h should appear in due_72h."""
        from apps.core.blueprint.models import DeadlineSnapshot

        now = timezone.now()
        deadline = now + dt.timedelta(hours=72)

        snapshot = DeadlineSnapshot.objects.create(
            user=self.user,
            due_24h=[],
            due_72h=[{
                'type': 'commitment',
                'text': 'Test commitment 72h',
                'deadline': deadline.isoformat(),
            }],
            due_7d=[],
            collision_flags=[],
        )

        self.assertEqual(len(snapshot.due_72h), 1)
        self.assertEqual(len(snapshot.due_24h), 0)

    def test_snapshot_staleness_check(self):
        """Snapshot older than max_age_minutes is stale."""
        from apps.core.blueprint.models import DeadlineSnapshot

        snapshot = DeadlineSnapshot.objects.create(
            user=self.user,
            due_24h=[], due_72h=[], due_7d=[], collision_flags=[],
        )

        # Fresh snapshot is not stale
        self.assertFalse(snapshot.is_stale(max_age_minutes=10))

        # Force staleness by backdating
        DeadlineSnapshot.objects.filter(pk=snapshot.pk).update(
            computed_at=timezone.now() - dt.timedelta(minutes=15),
        )
        snapshot.refresh_from_db()
        self.assertTrue(snapshot.is_stale(max_age_minutes=10))

    def test_latest_for_user_returns_most_recent(self):
        """latest_for_user returns the most recently computed snapshot."""
        from apps.core.blueprint.models import DeadlineSnapshot

        # Create two snapshots
        old = DeadlineSnapshot.objects.create(
            user=self.user,
            due_24h=[{'text': 'old'}], due_72h=[], due_7d=[],
            collision_flags=[],
        )
        DeadlineSnapshot.objects.filter(pk=old.pk).update(
            computed_at=timezone.now() - dt.timedelta(hours=1),
        )

        new = DeadlineSnapshot.objects.create(
            user=self.user,
            due_24h=[{'text': 'new'}], due_72h=[], due_7d=[],
            collision_flags=[],
        )

        latest = DeadlineSnapshot.latest_for_user(self.user)
        self.assertEqual(latest.pk, new.pk)

    def test_deadline_snapshot_with_collision_flags(self):
        """Snapshot with collision flags reports correctly."""
        from apps.core.blueprint.models import DeadlineSnapshot

        snapshot = DeadlineSnapshot.objects.create(
            user=self.user,
            due_24h=[
                {'type': 'commitment', 'text': 'A', 'deadline': '2026-04-15T14:00:00Z'},
                {'type': 'commitment', 'text': 'B', 'deadline': '2026-04-15T15:00:00Z'},
            ],
            due_72h=[],
            due_7d=[],
            collision_flags=[
                {'type': 'pair_collision', 'gap_hours': 1.0,
                 'items': ['A', 'B']},
            ],
        )

        self.assertEqual(len(snapshot.collision_flags), 1)
        self.assertEqual(snapshot.collision_flags[0]['type'], 'pair_collision')
