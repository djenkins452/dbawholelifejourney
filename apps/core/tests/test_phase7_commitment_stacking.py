"""
Phase 7 — Commitment Stacking Tests.

Covers:
    1. Create 3 commitments → close 1 → others persist
    2. Close specific commitment by index
    3. Attempt close with no pending commitments
    4. Attempt create 6th commitment (blocked at 5 limit)

These tests verify the commitment stacking system correctly manages
multiple concurrent commitments per user.

Project: Whole Life Journey
Path: apps/core/tests/test_phase7_commitment_stacking.py
"""

import datetime as dt

from django.test import TestCase
from django.utils import timezone

from apps.users.models import User, UserPreferences


def _create_test_user(email='stacking@example.com'):
    """Create a test user with preferences."""
    user = User.objects.create_user(email=email, password='testpass123')
    UserPreferences.objects.get_or_create(
        user=user, defaults={'timezone': 'America/New_York'},
    )
    return user


def _create_commitment(user, text, hours_ahead=48, status='pending'):
    """Create a commitment with the given text and time boundary."""
    from apps.core.blueprint.models import Commitment

    return Commitment.objects.create(
        user=user,
        normalized_text=text,
        commitment_type=Commitment.TYPE_DO,
        time_boundary=timezone.now() + dt.timedelta(hours=hours_ahead),
        done_definition=f'Complete: {text}',
        status=status,
        tier_at_creation='CLEAN',
    )


# =========================================================================
# 1) CREATE 3 → CLOSE 1 → OTHERS PERSIST
# =========================================================================


class CommitmentStackingPersistenceTests(TestCase):
    """Test that closing one commitment doesn't affect others."""

    def setUp(self):
        self.user = _create_test_user('stack-persist@example.com')

    def test_close_one_of_three_others_remain_pending(self):
        """Create 3 commitments, close 1, verify 2 remain pending."""
        from apps.core.blueprint.models import Commitment

        c1 = _create_commitment(self.user, 'Exercise 30 min')
        c2 = _create_commitment(self.user, 'Read 20 pages')
        c3 = _create_commitment(self.user, 'Meditate 10 min')

        # Close c2
        c2.close(Commitment.STATUS_CLOSED_SUCCESS,
                 Commitment.CLOSURE_USER_CONFIRMED)

        # Verify c1 and c3 are still pending
        pending = Commitment.pending_for_user(self.user)
        pending_ids = set(pending.values_list('id', flat=True))
        self.assertEqual(len(pending_ids), 2)
        self.assertIn(c1.id, pending_ids)
        self.assertIn(c3.id, pending_ids)
        self.assertNotIn(c2.id, pending_ids)

    def test_close_first_of_three(self):
        """Close the first commitment, others remain."""
        from apps.core.blueprint.models import Commitment

        c1 = _create_commitment(self.user, 'Task A')
        c2 = _create_commitment(self.user, 'Task B')
        c3 = _create_commitment(self.user, 'Task C')

        c1.close(Commitment.STATUS_CLOSED_SUCCESS,
                 Commitment.CLOSURE_USER_CONFIRMED)

        self.assertEqual(Commitment.pending_for_user(self.user).count(), 2)

    def test_close_last_of_three(self):
        """Close the last commitment, others remain."""
        from apps.core.blueprint.models import Commitment

        c1 = _create_commitment(self.user, 'Task A')
        c2 = _create_commitment(self.user, 'Task B')
        c3 = _create_commitment(self.user, 'Task C')

        c3.close(Commitment.STATUS_CLOSED_MISSED,
                 Commitment.CLOSURE_USER_MISSED)

        self.assertEqual(Commitment.pending_for_user(self.user).count(), 2)
        c3.refresh_from_db()
        self.assertEqual(c3.status, Commitment.STATUS_CLOSED_MISSED)

    def test_close_all_three_results_in_zero_pending(self):
        """Close all 3 commitments, 0 pending remain."""
        from apps.core.blueprint.models import Commitment

        commitments = [
            _create_commitment(self.user, f'Task {i}')
            for i in range(3)
        ]

        for c in commitments:
            c.close(Commitment.STATUS_CLOSED_SUCCESS,
                    Commitment.CLOSURE_USER_CONFIRMED)

        self.assertEqual(Commitment.pending_for_user(self.user).count(), 0)

    def test_closing_commitment_sets_closed_at_timestamp(self):
        """Closing a commitment sets the closed_at timestamp."""
        from apps.core.blueprint.models import Commitment

        c = _create_commitment(self.user, 'Task A')
        self.assertIsNone(c.closed_at)

        c.close(Commitment.STATUS_CLOSED_SUCCESS,
                Commitment.CLOSURE_USER_CONFIRMED)

        c.refresh_from_db()
        self.assertIsNotNone(c.closed_at)
        self.assertEqual(c.status, Commitment.STATUS_CLOSED_SUCCESS)
        self.assertEqual(c.closure_type, Commitment.CLOSURE_USER_CONFIRMED)


# =========================================================================
# 2) CLOSE SPECIFIC COMMITMENT BY INDEX
# =========================================================================


class CloseSpecificCommitmentTests(TestCase):
    """Test closing a specific commitment from a stacked set."""

    def setUp(self):
        self.user = _create_test_user('close-specific@example.com')

    def test_close_middle_commitment_by_pk(self):
        """Close the middle commitment by its primary key."""
        from apps.core.blueprint.models import Commitment

        c1 = _create_commitment(self.user, 'First')
        c2 = _create_commitment(self.user, 'Second')
        c3 = _create_commitment(self.user, 'Third')

        # Close c2 specifically
        target = Commitment.objects.get(pk=c2.pk)
        target.close(Commitment.STATUS_CLOSED_SUCCESS,
                     Commitment.CLOSURE_USER_CONFIRMED)

        # Verify only c2 is closed
        pending = list(
            Commitment.pending_for_user(self.user)
            .values_list('normalized_text', flat=True)
        )
        self.assertIn('First', pending)
        self.assertIn('Third', pending)
        self.assertNotIn('Second', pending)

    def test_close_commitment_as_missed(self):
        """Close a specific commitment as missed."""
        from apps.core.blueprint.models import Commitment

        c = _create_commitment(self.user, 'Missed task')
        c.close(Commitment.STATUS_CLOSED_MISSED,
                Commitment.CLOSURE_USER_MISSED)

        c.refresh_from_db()
        self.assertEqual(c.status, Commitment.STATUS_CLOSED_MISSED)
        self.assertEqual(c.closure_type, Commitment.CLOSURE_USER_MISSED)

    def test_close_commitment_as_cancelled(self):
        """Cancel a specific commitment."""
        from apps.core.blueprint.models import Commitment

        c = _create_commitment(self.user, 'Cancelled task')
        c.close(Commitment.STATUS_CANCELLED,
                Commitment.CLOSURE_CANCELLED)

        c.refresh_from_db()
        self.assertEqual(c.status, Commitment.STATUS_CANCELLED)

    def test_close_commitment_as_renegotiated(self):
        """Renegotiate a specific commitment."""
        from apps.core.blueprint.models import Commitment

        c = _create_commitment(self.user, 'Renegotiated task')
        c.close(Commitment.STATUS_RENEGOTIATED,
                Commitment.CLOSURE_RENEGOTIATED)

        c.refresh_from_db()
        self.assertEqual(c.status, Commitment.STATUS_RENEGOTIATED)


# =========================================================================
# 3) ATTEMPT CLOSE WITH NO PENDING COMMITMENTS
# =========================================================================


class CloseWithNoPendingTests(TestCase):
    """Test behavior when trying to close with no pending commitments."""

    def setUp(self):
        self.user = _create_test_user('no-pending@example.com')

    def test_pending_for_user_returns_empty_qs(self):
        """pending_for_user returns empty queryset when no commitments."""
        from apps.core.blueprint.models import Commitment

        pending = Commitment.pending_for_user(self.user)
        self.assertEqual(pending.count(), 0)

    def test_pending_for_user_empty_after_all_closed(self):
        """After closing all commitments, pending returns empty."""
        from apps.core.blueprint.models import Commitment

        c = _create_commitment(self.user, 'Solo task')
        c.close(Commitment.STATUS_CLOSED_SUCCESS,
                Commitment.CLOSURE_USER_CONFIRMED)

        self.assertEqual(Commitment.pending_for_user(self.user).count(), 0)

    def test_can_create_returns_true_when_no_pending(self):
        """can_create returns True when user has no pending commitments."""
        from apps.core.blueprint.models import Commitment

        self.assertTrue(Commitment.can_create(self.user))

    def test_only_pending_status_counts_for_limit(self):
        """Cancelled, renegotiated, and closed commitments don't count."""
        from apps.core.blueprint.models import Commitment

        statuses = [
            Commitment.STATUS_CLOSED_SUCCESS,
            Commitment.STATUS_CLOSED_MISSED,
            Commitment.STATUS_CANCELLED,
            Commitment.STATUS_RENEGOTIATED,
        ]

        for i, status in enumerate(statuses):
            c = _create_commitment(self.user, f'Task {i}')
            c.status = status
            c.save(update_fields=['status'])

        # All 4 are non-pending, so can_create should be True
        self.assertTrue(Commitment.can_create(self.user))
        self.assertEqual(Commitment.pending_for_user(self.user).count(), 0)


# =========================================================================
# 4) ATTEMPT CREATE 6TH COMMITMENT (BLOCKED AT 5 LIMIT)
# =========================================================================


class CommitmentLimitTests(TestCase):
    """Test the hard limit of 5 pending commitments per user."""

    def setUp(self):
        self.user = _create_test_user('limit-test@example.com')

    def test_can_create_5_pending_commitments(self):
        """Creating exactly 5 pending commitments is allowed."""
        from apps.core.blueprint.models import Commitment

        for i in range(5):
            _create_commitment(self.user, f'Commitment {i+1}')

        self.assertEqual(Commitment.pending_for_user(self.user).count(), 5)

    def test_can_create_returns_false_at_5(self):
        """can_create returns False when 5 commitments exist."""
        from apps.core.blueprint.models import Commitment

        for i in range(5):
            _create_commitment(self.user, f'Commitment {i+1}')

        self.assertFalse(Commitment.can_create(self.user))

    def test_closing_one_allows_new_creation(self):
        """After closing one of 5, a new commitment can be created."""
        from apps.core.blueprint.models import Commitment

        commitments = []
        for i in range(5):
            c = _create_commitment(self.user, f'Commitment {i+1}')
            commitments.append(c)

        self.assertFalse(Commitment.can_create(self.user))

        # Close one
        commitments[0].close(Commitment.STATUS_CLOSED_SUCCESS,
                             Commitment.CLOSURE_USER_CONFIRMED)

        self.assertTrue(Commitment.can_create(self.user))

    def test_max_pending_per_user_constant_is_5(self):
        """Verify the constant is set to 5."""
        from apps.core.blueprint.models import Commitment

        self.assertEqual(Commitment.MAX_PENDING_PER_USER, 5)

    def test_different_users_have_independent_limits(self):
        """User A at 5 doesn't block User B from creating."""
        from apps.core.blueprint.models import Commitment

        user_b = _create_test_user('limit-b@example.com')

        for i in range(5):
            _create_commitment(self.user, f'Commitment {i+1}')

        self.assertFalse(Commitment.can_create(self.user))
        self.assertTrue(Commitment.can_create(user_b))

    def test_commitment_types_all_count_toward_limit(self):
        """All commitment types (DO, DECIDE, SCHEDULE, STOP) count."""
        from apps.core.blueprint.models import Commitment

        types = [
            Commitment.TYPE_DO,
            Commitment.TYPE_DECIDE,
            Commitment.TYPE_SCHEDULE,
            Commitment.TYPE_STOP,
            Commitment.TYPE_DO,  # 5th
        ]

        for i, ctype in enumerate(types):
            Commitment.objects.create(
                user=self.user,
                normalized_text=f'Commitment {i+1}',
                commitment_type=ctype,
                time_boundary=timezone.now() + dt.timedelta(hours=48),
                done_definition=f'Complete task {i+1}',
                status=Commitment.STATUS_PENDING,
                tier_at_creation='CLEAN',
            )

        self.assertFalse(Commitment.can_create(self.user))
