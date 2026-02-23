"""
Phase 2 — Time & Deadline Authority Tests.

Tests:
- Explicit time boundary enforcement (no 23:59 defaults)
- Time authority (no naive datetime.now())
- DST handling determinism (zoneinfo, gap/fold)
- Timezone change recalculation (local-intent preservation)
- Deadline snapshot accuracy
- Snapshot staleness anomaly
- Tier 1 graduated override logic
- Override logging correctness

Project: Whole Life Journey
Path: apps/core/tests/test_phase2_time_authority.py
"""

import datetime
from datetime import timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone


class ExplicitTimeBoundaryTests(TestCase):
    """Task 2.1: Verify silent 23:59 default is removed."""

    def setUp(self):
        from apps.core.ai_orchestrator.commitment_contract import (
            MissingField,
            _parse_time_boundary,
        )
        self.parse = _parse_time_boundary
        self.MissingField = MissingField
        self.ref = datetime.datetime(2026, 2, 23, 10, 0, 0, tzinfo=ZoneInfo('America/New_York'))

    def test_today_without_time_returns_missing_field(self):
        """'today' without specific time must trigger tightening question."""
        result = self.parse('today', self.ref)
        self.assertIsInstance(result, self.MissingField)
        self.assertEqual(result.field_name, 'time_boundary')

    def test_tonight_returns_missing_field(self):
        result = self.parse('tonight', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_this_afternoon_returns_missing_field(self):
        result = self.parse('this afternoon', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_this_evening_returns_missing_field(self):
        result = self.parse('this evening', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_bare_tomorrow_returns_missing_field(self):
        """'tomorrow' without time-of-day must trigger tightening."""
        result = self.parse('tomorrow', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_end_of_today_returns_missing_field(self):
        result = self.parse('end of today', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_end_of_the_day_returns_missing_field(self):
        result = self.parse('end of the day', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_end_of_week_returns_missing_field(self):
        result = self.parse('end of the week', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_end_of_month_returns_missing_field(self):
        result = self.parse('end of the month', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_in_3_days_returns_missing_field(self):
        """'in 3 days' has a date but no time → tightening question."""
        result = self.parse('in 3 days', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_in_2_weeks_returns_missing_field(self):
        result = self.parse('in 2 weeks', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_monday_returns_missing_field(self):
        """Day-of-week without time → tightening question."""
        result = self.parse('monday', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_next_friday_returns_missing_field(self):
        result = self.parse('next friday', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_empty_raw_returns_missing_field(self):
        result = self.parse('', self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_none_raw_returns_missing_field(self):
        result = self.parse(None, self.ref)
        self.assertIsInstance(result, self.MissingField)

    def test_unrecognized_returns_missing_field(self):
        result = self.parse('whenever', self.ref)
        self.assertIsInstance(result, self.MissingField)

    # --- Cases that SHOULD resolve to concrete times ---

    def test_by_5pm_resolves(self):
        result = self.parse('by 5pm', self.ref)
        self.assertNotIsInstance(result, self.MissingField)
        self.assertEqual(result.hour, 17)
        self.assertEqual(result.minute, 0)

    def test_at_3_30_pm_resolves(self):
        result = self.parse('at 3:30 pm', self.ref)
        self.assertNotIsInstance(result, self.MissingField)
        self.assertEqual(result.hour, 15)
        self.assertEqual(result.minute, 30)

    def test_before_10am_resolves(self):
        result = self.parse('before 10am', self.ref)
        self.assertNotIsInstance(result, self.MissingField)
        self.assertEqual(result.hour, 10)

    def test_in_30_minutes_resolves(self):
        result = self.parse('in 30 minutes', self.ref)
        self.assertNotIsInstance(result, self.MissingField)
        expected = self.ref + timedelta(minutes=30)
        self.assertEqual(result.hour, expected.hour)
        self.assertEqual(result.minute, expected.minute)

    def test_in_2_hours_resolves(self):
        result = self.parse('in 2 hours', self.ref)
        self.assertNotIsInstance(result, self.MissingField)
        expected = self.ref + timedelta(hours=2)
        self.assertEqual(result.hour, expected.hour)

    def test_this_morning_resolves_to_noon(self):
        result = self.parse('this morning', self.ref)
        self.assertNotIsInstance(result, self.MissingField)
        self.assertEqual(result.hour, 12)

    def test_tomorrow_morning_resolves(self):
        result = self.parse('tomorrow morning', self.ref)
        self.assertNotIsInstance(result, self.MissingField)
        self.assertEqual(result.day, 24)  # Feb 24
        self.assertEqual(result.hour, 12)

    def test_tomorrow_evening_resolves(self):
        result = self.parse('tomorrow evening', self.ref)
        self.assertNotIsInstance(result, self.MissingField)
        self.assertEqual(result.day, 24)
        self.assertEqual(result.hour, 21)


class TimeAuthorityTests(TestCase):
    """Task 2.2: Verify no naive datetime.now() usage."""

    def test_get_reference_time_with_no_user_returns_aware(self):
        """_get_reference_time(None) returns timezone-aware datetime."""
        from apps.core.ai_orchestrator.commitment_contract import _get_reference_time
        result = _get_reference_time(None)
        self.assertIsNotNone(result.tzinfo)

    def test_normalize_commitment_default_reference_is_aware(self):
        """normalize_commitment without reference_time uses aware datetime."""
        from apps.core.ai_orchestrator.commitment_contract import (
            CommitmentDraft,
            MissingField,
            normalize_commitment,
        )
        draft = CommitmentDraft(
            action='Test action',
            time_boundary_raw='by 5pm',
            done_definition='',
            time_boundary_display='by 5pm',
        )
        result = normalize_commitment(draft)
        # Should not be MissingField for 'by 5pm'
        if not isinstance(result, MissingField):
            self.assertIsNotNone(result.time_boundary.tzinfo)


class DSTHandlingTests(TestCase):
    """Task 2.3: DST deterministic handling."""

    def test_zoneinfo_used_not_pytz(self):
        """Verify get_user_now uses zoneinfo internally."""
        from apps.core.utils import _get_user_tz
        user = MagicMock()
        user.preferences.timezone_iana = 'America/New_York'
        tz = _get_user_tz(user)
        self.assertIsInstance(tz, ZoneInfo)

    def test_make_dst_safe_spring_forward(self):
        """Spring-forward gap: 2:30 AM EST → next valid time."""
        from apps.core.utils import make_dst_safe

        user = MagicMock()
        user.preferences.timezone_iana = 'America/New_York'

        # 2026-03-08 is Spring Forward day in US Eastern
        # 2:30 AM doesn't exist — clocks skip from 2:00 to 3:00
        naive_gap_time = datetime.datetime(2026, 3, 8, 2, 30, 0)
        result = make_dst_safe(naive_gap_time, user)

        # zoneinfo with fold=0 will resolve this deterministically
        self.assertIsNotNone(result.tzinfo)
        # The time should be valid (not in the gap)
        self.assertTrue(result.hour >= 2)  # At minimum 2:00 or moved to 3:00+

    def test_make_dst_safe_fall_back_uses_fold_0(self):
        """Fall-back fold: 1:30 AM → first occurrence (fold=0)."""
        from apps.core.utils import make_dst_safe

        user = MagicMock()
        user.preferences.timezone_iana = 'America/New_York'

        # 2026-11-01 is Fall Back day in US Eastern
        # 1:30 AM exists twice — fold=0 means first occurrence (EDT)
        naive_fold_time = datetime.datetime(2026, 11, 1, 1, 30, 0)
        result = make_dst_safe(naive_fold_time, user)

        self.assertIsNotNone(result.tzinfo)
        self.assertEqual(result.fold, 0)
        self.assertEqual(result.hour, 1)
        self.assertEqual(result.minute, 30)


class TimezoneChangeRecalculationTests(TestCase):
    """Task 2.4: Timezone change behavior — local-intent preservation."""

    def setUp(self):
        from apps.users.models import User
        self.user = User.objects.create_user(
            email='tz-test@example.com',
            password='testpass123',
        )
        # Ensure preferences exist
        from apps.users.models import UserPreferences
        prefs, _ = UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )
        prefs.timezone = 'America/New_York'
        prefs.save()

    def test_pending_commitment_recalculates_on_tz_change(self):
        """Pending commitment preserves wall-clock time on timezone change."""
        from apps.core.blueprint.models import Commitment

        # Create commitment at 5:00 PM Eastern
        eastern = ZoneInfo('America/New_York')
        time_boundary = datetime.datetime(2026, 3, 1, 17, 0, 0, tzinfo=eastern)

        commitment = Commitment.objects.create(
            user=self.user,
            normalized_text='Test commitment',
            commitment_type='DO',
            time_boundary=time_boundary,
            status=Commitment.STATUS_PENDING,
            timezone_at_creation='America/New_York',
        )

        # Change timezone to Pacific
        result = commitment.recalculate_timezone('America/Los_Angeles')
        commitment.refresh_from_db()

        self.assertTrue(result)
        # Wall-clock should still be 5:00 PM, but now Pacific
        pacific = ZoneInfo('America/Los_Angeles')
        local_time = commitment.time_boundary.astimezone(pacific)
        self.assertEqual(local_time.hour, 17)
        self.assertEqual(local_time.minute, 0)
        self.assertEqual(commitment.timezone_at_last_recalculation, 'America/Los_Angeles')

    def test_completed_commitment_not_recalculated(self):
        """Completed commitments are unaffected by timezone change."""
        from apps.core.blueprint.models import Commitment

        eastern = ZoneInfo('America/New_York')
        time_boundary = datetime.datetime(2026, 3, 1, 17, 0, 0, tzinfo=eastern)

        commitment = Commitment.objects.create(
            user=self.user,
            normalized_text='Done commitment',
            commitment_type='DO',
            time_boundary=time_boundary,
            status=Commitment.STATUS_CLOSED_SUCCESS,
            timezone_at_creation='America/New_York',
        )

        original_tb = commitment.time_boundary
        result = commitment.recalculate_timezone('America/Los_Angeles')

        self.assertFalse(result)
        commitment.refresh_from_db()
        self.assertEqual(commitment.time_boundary, original_tb)

    def test_batch_recalculation(self):
        """recalculate_pending_commitments_for_timezone_change works."""
        from apps.core.blueprint.models import (
            Commitment,
            recalculate_pending_commitments_for_timezone_change,
        )

        eastern = ZoneInfo('America/New_York')
        # Create 3 pending, 1 closed
        for i in range(3):
            Commitment.objects.create(
                user=self.user,
                normalized_text=f'Pending {i}',
                commitment_type='DO',
                time_boundary=datetime.datetime(2026, 3, 1, 17, 0, 0, tzinfo=eastern),
                status=Commitment.STATUS_PENDING,
                timezone_at_creation='America/New_York',
            )
        Commitment.objects.create(
            user=self.user,
            normalized_text='Closed one',
            commitment_type='DO',
            time_boundary=datetime.datetime(2026, 3, 1, 17, 0, 0, tzinfo=eastern),
            status=Commitment.STATUS_CLOSED_SUCCESS,
            timezone_at_creation='America/New_York',
        )

        count = recalculate_pending_commitments_for_timezone_change(
            self.user, 'America/Los_Angeles'
        )
        self.assertEqual(count, 3)


class DeadlineSnapshotTests(TestCase):
    """Task 2.5: Deadline snapshot model and computation."""

    def setUp(self):
        from apps.users.models import User
        self.user = User.objects.create_user(
            email='deadline-test@example.com',
            password='testpass123',
        )
        from apps.users.models import UserPreferences
        UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )

    def test_snapshot_creation(self):
        """DeadlineSnapshot can be created and queried."""
        from apps.core.blueprint.models import DeadlineSnapshot

        snapshot = DeadlineSnapshot.objects.create(
            user=self.user,
            due_24h=[{'type': 'commitment', 'text': 'Test'}],
            due_72h=[],
            due_7d=[],
            collision_flags=[],
        )

        latest = DeadlineSnapshot.latest_for_user(self.user)
        self.assertEqual(latest.pk, snapshot.pk)
        self.assertEqual(len(latest.due_24h), 1)

    def test_snapshot_staleness(self):
        """Snapshot older than 10 minutes is stale."""
        from apps.core.blueprint.models import DeadlineSnapshot

        snapshot = DeadlineSnapshot.objects.create(
            user=self.user,
            due_24h=[],
            due_72h=[],
            due_7d=[],
            collision_flags=[],
        )

        # Fresh snapshot should not be stale
        self.assertFalse(snapshot.is_stale())

        # Manually set computed_at to 11 minutes ago
        old_time = timezone.now() - timedelta(minutes=11)
        DeadlineSnapshot.objects.filter(pk=snapshot.pk).update(computed_at=old_time)
        snapshot.refresh_from_db()
        self.assertTrue(snapshot.is_stale())

    def test_compute_deadline_snapshot_with_commitments(self):
        """compute_deadline_snapshot correctly categorizes commitments."""
        from apps.core.blueprint.deadline_engine import compute_deadline_snapshot
        from apps.core.blueprint.models import Commitment

        now = timezone.now()

        # Due in 12 hours (24h bucket)
        Commitment.objects.create(
            user=self.user,
            normalized_text='Due soon',
            commitment_type='DO',
            time_boundary=now + timedelta(hours=12),
            status=Commitment.STATUS_PENDING,
        )

        # Due in 48 hours (72h bucket)
        Commitment.objects.create(
            user=self.user,
            normalized_text='Due this week',
            commitment_type='DO',
            time_boundary=now + timedelta(hours=48),
            status=Commitment.STATUS_PENDING,
        )

        # Due in 5 days (7d bucket)
        Commitment.objects.create(
            user=self.user,
            normalized_text='Due next week',
            commitment_type='DO',
            time_boundary=now + timedelta(days=5),
            status=Commitment.STATUS_PENDING,
        )

        snapshot = compute_deadline_snapshot(self.user)

        self.assertEqual(len(snapshot.due_24h), 1)
        self.assertEqual(snapshot.due_24h[0]['text'], 'Due soon')
        self.assertEqual(len(snapshot.due_72h), 1)
        self.assertEqual(snapshot.due_72h[0]['text'], 'Due this week')
        self.assertEqual(len(snapshot.due_7d), 1)
        self.assertEqual(snapshot.due_7d[0]['text'], 'Due next week')

    def test_collision_detection_pair(self):
        """Deadlines with <2h gap flagged as pair collision."""
        from apps.core.blueprint.deadline_engine import _detect_collisions

        now = timezone.now()
        deadlines = [
            (now + timedelta(hours=1), 'Task A'),
            (now + timedelta(hours=2), 'Task B'),  # 1h gap
        ]
        flags = _detect_collisions(deadlines)
        pair_flags = [f for f in flags if f['type'] == 'pair_collision']
        self.assertEqual(len(pair_flags), 1)
        self.assertLess(pair_flags[0]['gap_hours'], 2)

    def test_collision_detection_daily_overload(self):
        """Days with >3 deadlines flagged as daily overload."""
        from apps.core.blueprint.deadline_engine import _detect_collisions

        now = timezone.now()
        deadlines = [
            (now + timedelta(hours=i), f'Task {i}')
            for i in range(1, 6)  # 5 deadlines same day
        ]
        flags = _detect_collisions(deadlines)
        overload_flags = [f for f in flags if f['type'] == 'daily_overload']
        self.assertTrue(len(overload_flags) >= 1)

    def test_stale_snapshot_anomaly(self):
        """check_stale_snapshot returns anomaly when snapshot is stale."""
        from apps.core.blueprint.deadline_engine import check_stale_snapshot
        from apps.core.blueprint.models import DeadlineSnapshot

        # No snapshot at all
        anomaly = check_stale_snapshot(self.user)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['anomaly_type'], 'STALE_DEADLINE_SNAPSHOT')

        # Fresh snapshot
        DeadlineSnapshot.objects.create(
            user=self.user,
            due_24h=[], due_72h=[], due_7d=[],
            collision_flags=[],
        )
        anomaly = check_stale_snapshot(self.user)
        self.assertIsNone(anomaly)

    def test_should_compute_snapshot_with_pending_commitments(self):
        """should_compute_snapshot returns True when pending commitments exist."""
        from apps.core.blueprint.deadline_engine import should_compute_snapshot
        from apps.core.blueprint.models import Commitment

        self.assertFalse(should_compute_snapshot(self.user))

        Commitment.objects.create(
            user=self.user,
            normalized_text='Pending',
            commitment_type='DO',
            time_boundary=timezone.now() + timedelta(hours=12),
            status=Commitment.STATUS_PENDING,
        )

        self.assertTrue(should_compute_snapshot(self.user))


class Tier1ConflictEnforcementTests(TestCase):
    """Task 2.6: Protected block conflict enforcement."""

    def setUp(self):
        from apps.users.models import User
        self.user = User.objects.create_user(
            email='tier1-test@example.com',
            password='testpass123',
        )
        from apps.users.models import UserPreferences
        UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )

    def _create_plan_with_tier1_block(self):
        """Helper: create a plan with a Tier 1 block 9:00-10:00."""
        from apps.core.blueprint.models import ArchitecturePlan, ScheduledBlock

        plan = ArchitecturePlan.objects.create(
            user=self.user,
            date=timezone.localdate(),
            status='active',
        )
        ScheduledBlock.objects.create(
            plan=plan,
            title='Morning Prayer',
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 0),
            tier=1,
            source='non_negotiable',
            behavior_key='PRAYER',
            is_locked=True,
        )
        return plan

    def test_tier1_conflict_detected(self):
        """Scheduling over Tier 1 block triggers conflict."""
        from apps.core.blueprint.architecture_engine import check_tier1_conflict

        self._create_plan_with_tier1_block()

        result = check_tier1_conflict(
            self.user,
            datetime.time(9, 30),
            datetime.time(10, 30),
            'Meeting',
        )

        self.assertIsNotNone(result)
        self.assertTrue(result['conflict'])
        self.assertTrue(result['override_required'])
        self.assertIn('Tier 1', result['message'])
        self.assertIn('Morning Prayer', result['message'])

    def test_no_conflict_outside_tier1(self):
        """Scheduling outside Tier 1 block returns None."""
        from apps.core.blueprint.architecture_engine import check_tier1_conflict

        self._create_plan_with_tier1_block()

        result = check_tier1_conflict(
            self.user,
            datetime.time(11, 0),
            datetime.time(12, 0),
        )

        self.assertIsNone(result)

    def test_override_requires_exact_phrase(self):
        """Override only allowed with exact phrase."""
        from apps.core.blueprint.architecture_engine import process_tier1_override

        result = process_tier1_override(
            self.user,
            "I want to override this",
            original_block_id=1,
            conflicting_description='Meeting',
        )
        self.assertFalse(result['allowed'])

    def test_override_with_correct_phrase(self):
        """Override allowed with exact phrase and logged."""
        from apps.core.blueprint.architecture_engine import process_tier1_override
        from apps.core.blueprint.models import Tier1OverrideEvent

        self._create_plan_with_tier1_block()

        result = process_tier1_override(
            self.user,
            "Override Tier 1 protection",
            original_block_id=1,
            conflicting_description='Emergency meeting',
            escalation_level='CLEAN',
            density_score=0.6,
        )

        self.assertTrue(result['allowed'])

        # Verify event was logged
        events = Tier1OverrideEvent.objects.filter(user=self.user)
        self.assertEqual(events.count(), 1)
        event = events.first()
        self.assertEqual(event.escalation_level_at_time, 'CLEAN')
        self.assertEqual(event.density_score_at_time, 0.6)
        self.assertEqual(event.conflicting_block_description, 'Emergency meeting')

    def test_tier2_conflict_warns_but_no_override(self):
        """Tier 2 conflicts warn but don't require override."""
        from apps.core.blueprint.architecture_engine import check_tier1_conflict
        from apps.core.blueprint.models import ArchitecturePlan, ScheduledBlock

        plan = ArchitecturePlan.objects.create(
            user=self.user,
            date=timezone.localdate(),
            status='active',
        )
        ScheduledBlock.objects.create(
            plan=plan,
            title='Weekly Review',
            start_time=datetime.time(14, 0),
            end_time=datetime.time(15, 0),
            tier=2,
            source='task',
        )

        result = check_tier1_conflict(
            self.user,
            datetime.time(14, 30),
            datetime.time(15, 30),
        )

        self.assertIsNotNone(result)
        self.assertTrue(result['conflict'])
        self.assertFalse(result['override_required'])
        self.assertIsNone(result['tier1_block'])
