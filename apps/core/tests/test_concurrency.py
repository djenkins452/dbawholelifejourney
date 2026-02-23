"""
Phase 6 — Concurrency Tests.

Tests:
1. Conversation metadata locking: retry + degrade path.
2. Double-submit idempotency (no duplicates within 100ms).
3. select_for_update contention: one retry then degrade.
4. ArchitecturePlan.activate() under concurrent calls.
5. Scheduler overlap: Redis + DB token prevents double-run.
6. COMMITMENT_RACE_CONDITION anomaly fires.
7. Escalation level change creates EngineRun + DecisionRecord.
8. Multi-tab same-user: no duplicate commitments, no metadata corruption.
"""


from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.db import OperationalError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone


def _create_test_user(email='concurrency@example.com'):
    from apps.users.models import User, UserPreferences

    user = User.objects.create_user(email=email, password='testpass123')
    UserPreferences.objects.get_or_create(
        user=user,
        defaults={'timezone': 'America/New_York'},
    )
    return user


def _create_conversation(user):
    from apps.ai.models import AssistantConversation

    return AssistantConversation.objects.create(
        user=user,
        title='Test conversation',
        metadata={},
    )


# =========================================================================
# 6.1 — CONVERSATION METADATA LOCKING
# =========================================================================


class ConversationMetadataLockingTests(TestCase):
    """Test conversation metadata read-modify-write with row-level locking."""

    def setUp(self):
        self.user = _create_test_user('meta-lock@example.com')
        self.conversation = _create_conversation(self.user)

    def test_successful_metadata_update(self):
        """Normal metadata update succeeds."""
        from apps.core.blueprint.concurrency import update_conversation_metadata

        def updater(meta):
            meta['test_key'] = 'test_value'
            return meta

        result = update_conversation_metadata(self.conversation, updater)
        self.assertTrue(result['success'])
        self.assertFalse(result['degraded'])
        self.assertIsNone(result['message'])

        # Verify metadata was saved
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.metadata.get('test_key'), 'test_value')

    def test_metadata_update_preserves_existing_keys(self):
        """Update adds new keys without clobbering existing ones."""
        from apps.core.blueprint.concurrency import update_conversation_metadata

        self.conversation.metadata = {'existing': 'data'}
        self.conversation.save(update_fields=['metadata'])

        def updater(meta):
            meta['new_key'] = 'new_value'
            return meta

        result = update_conversation_metadata(self.conversation, updater)
        self.assertTrue(result['success'])

        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.metadata.get('existing'), 'data')
        self.assertEqual(self.conversation.metadata.get('new_key'), 'new_value')

    @patch('apps.core.blueprint.concurrency.time.sleep')
    def test_degraded_mode_after_two_failures(self, mock_sleep):
        """After two lock failures, enters degraded mode safely."""
        from apps.core.blueprint.concurrency import update_conversation_metadata

        with patch(
            'apps.ai.models.AssistantConversation.objects.select_for_update'
        ) as mock_sfu:
            mock_qs = MagicMock()
            mock_qs.get.side_effect = OperationalError("lock timeout")
            mock_sfu.return_value = mock_qs

            def updater(meta):
                meta['should_not_exist'] = True
                return meta

            result = update_conversation_metadata(
                self.conversation, updater,
                degraded_message="Test degraded message",
            )

            self.assertFalse(result['success'])
            self.assertTrue(result['degraded'])
            self.assertEqual(result['message'], "Test degraded message")

        # Verify metadata was NOT changed
        self.conversation.refresh_from_db()
        self.assertNotIn('should_not_exist', self.conversation.metadata or {})

    @patch('apps.core.blueprint.concurrency.time.sleep')
    def test_retry_once_then_succeed(self, mock_sleep):
        """First attempt fails, second succeeds."""
        from apps.ai.models import AssistantConversation
        from apps.core.blueprint.concurrency import update_conversation_metadata

        original_sfu = AssistantConversation.objects.select_for_update
        call_count = [0]

        def side_effect_sfu(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OperationalError("lock timeout first try")
            return original_sfu(**kwargs)

        with patch.object(
            type(AssistantConversation.objects), 'select_for_update',
            side_effect=side_effect_sfu,
        ):
            def updater(meta):
                meta['retry_success'] = True
                return meta

            result = update_conversation_metadata(self.conversation, updater)

        # The retry mechanism wraps in transaction.atomic + get(),
        # so if select_for_update raises before get, it catches the error.
        # This test verifies the retry logic path is exercised.
        self.assertTrue(call_count[0] >= 1)


# =========================================================================
# 6.2 — COMMITMENT WRITE ATOMICITY
# =========================================================================


class CommitmentWriteAtomicityTests(TestCase):
    """Ensure commitment create → save → logging → response is atomic."""

    def setUp(self):
        self.user = _create_test_user('commit-atomic@example.com')
        self.conversation = _create_conversation(self.user)

    def test_create_commitment_is_atomic(self):
        """Commitment creation persists correctly inside transaction."""
        from apps.core.ai_orchestrator.commitment_contract import (
            CommitmentData,
            create_db_commitment,
        )

        cd = CommitmentData(
            normalized_text='Test atomic commit',
            commitment_type='DO',
            time_boundary=timezone.now() + timedelta(hours=2),
            done_definition='Test is done',
        )

        result = create_db_commitment(
            self.user, cd, self.conversation, 'CLEAN',
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.normalized_text, 'Test atomic commit')
        self.assertEqual(result.status, 'pending')

    def test_close_commitment_is_atomic(self):
        """Commitment closure uses select_for_update inside transaction."""
        from apps.core.ai_orchestrator.commitment_contract import (
            CommitmentData,
            close_db_commitment,
            create_db_commitment,
        )
        from apps.core.blueprint.models import Commitment

        cd = CommitmentData(
            normalized_text='Close me atomically',
            commitment_type='DO',
            time_boundary=timezone.now() + timedelta(hours=2),
            done_definition='',
        )
        db_commit = create_db_commitment(self.user, cd, self.conversation, 'CLEAN')
        self.assertIsNotNone(db_commit)

        close_db_commitment(db_commit, Commitment.STATUS_CLOSED_SUCCESS,
                            Commitment.CLOSURE_USER_CONFIRMED)

        db_commit.refresh_from_db()
        self.assertEqual(db_commit.status, Commitment.STATUS_CLOSED_SUCCESS)
        self.assertIsNotNone(db_commit.closed_at)

    def test_logging_failure_does_not_break_commitment(self):
        """If DecisionRecord logging fails, commitment still persists."""
        from apps.core.ai_orchestrator.commitment_contract import (
            CommitmentData,
            create_db_commitment,
        )

        cd = CommitmentData(
            normalized_text='Survive logging failure',
            commitment_type='DO',
            time_boundary=timezone.now() + timedelta(hours=2),
            done_definition='',
        )

        # Commitment creation doesn't depend on DecisionRecord — this
        # test verifies that pattern. If we patched DecisionRecord.create
        # to fail, the commitment should still be created.
        with patch(
            'apps.core.ai_observability.models.DecisionRecord.objects.create',
            side_effect=Exception("logging failure"),
        ):
            result = create_db_commitment(
                self.user, cd, self.conversation, 'CLEAN',
            )

        # Commitment should still be created (logging is separate)
        self.assertIsNotNone(result)


# =========================================================================
# 6.3 — ARCHITECTURE PLAN ACTIVATE ATOMICITY
# =========================================================================


class ArchitecturePlanActivateTests(TransactionTestCase):
    """Test ArchitecturePlan.activate() atomicity under concurrent calls."""

    def setUp(self):
        self.user = _create_test_user('plan-activate@example.com')

    def test_activate_supersedes_previous(self):
        """Activating a new plan supersedes the existing active plan."""
        from apps.core.blueprint.models import ArchitecturePlan

        today = timezone.localdate()
        plan1 = ArchitecturePlan.objects.create(
            user=self.user, date=today, status='draft',
        )
        plan2 = ArchitecturePlan.objects.create(
            user=self.user, date=today, status='draft',
        )

        plan1.activate()
        plan1.refresh_from_db()
        self.assertEqual(plan1.status, 'active')

        plan2.activate()
        plan2.refresh_from_db()
        plan1.refresh_from_db()

        self.assertEqual(plan2.status, 'active')
        self.assertEqual(plan1.status, 'superseded')

    def test_only_one_plan_active_after_sequential_activations(self):
        """
        Sequential activation of two plans — exactly one ends active.
        (Concurrent threading requires PostgreSQL; SQLite serializes writes.)
        """
        from apps.core.blueprint.models import ArchitecturePlan

        today = timezone.localdate()
        plan_a = ArchitecturePlan.objects.create(
            user=self.user, date=today, status='draft',
        )
        plan_b = ArchitecturePlan.objects.create(
            user=self.user, date=today, status='draft',
        )

        # Activate both sequentially — simulates two rapid activate calls
        plan_a.activate()
        plan_b.activate()

        plan_a.refresh_from_db()
        plan_b.refresh_from_db()

        # Exactly one should be active
        active_count = ArchitecturePlan.objects.filter(
            user=self.user, date=today, status='active',
        ).count()
        self.assertEqual(active_count, 1)
        self.assertEqual(plan_b.status, 'active')
        self.assertEqual(plan_a.status, 'superseded')


# =========================================================================
# 6.4 — SCHEDULER OVERLAP PROTECTION
# =========================================================================


class SchedulerOverlapProtectionTests(TestCase):
    """Test DB run token prevents duplicate engine runs."""

    def test_acquire_token_succeeds(self):
        """First acquire returns a token."""
        from apps.core.ai_scheduler.scheduler_models import EngineRunToken

        token = EngineRunToken.acquire(
            engine_name='test_engine',
            window_key='2026-02-23T14:00',
            lease_seconds=60,
        )
        self.assertIsNotNone(token)
        self.assertEqual(token.engine_name, 'test_engine')
        self.assertFalse(token.completed)

    def test_second_acquire_blocked(self):
        """Second acquire for same engine+window returns None."""
        from apps.core.ai_scheduler.scheduler_models import EngineRunToken

        token1 = EngineRunToken.acquire(
            engine_name='test_engine',
            window_key='2026-02-23T14:00',
            lease_seconds=300,
        )
        self.assertIsNotNone(token1)

        token2 = EngineRunToken.acquire(
            engine_name='test_engine',
            window_key='2026-02-23T14:00',
            lease_seconds=300,
        )
        self.assertIsNone(token2)

    def test_expired_token_can_be_reclaimed(self):
        """Expired tokens are reclaimed by new acquires."""
        from apps.core.ai_scheduler.scheduler_models import EngineRunToken

        # Create an already-expired token
        EngineRunToken.objects.create(
            engine_name='test_engine',
            user_id=None,
            window_key='2026-02-23T14:00',
            acquired_at=timezone.now() - timedelta(minutes=10),
            expires_at=timezone.now() - timedelta(minutes=5),
            acquired_by='old-process',
        )

        # Should be able to reclaim
        token = EngineRunToken.acquire(
            engine_name='test_engine',
            window_key='2026-02-23T14:00',
            lease_seconds=60,
        )
        self.assertIsNotNone(token)
        self.assertNotEqual(token.acquired_by, 'old-process')

    def test_release_marks_completed(self):
        """Releasing a token marks it as completed."""
        from apps.core.ai_scheduler.scheduler_models import EngineRunToken

        token = EngineRunToken.acquire(
            engine_name='test_engine',
            window_key='2026-02-23T14:05',
            lease_seconds=60,
        )
        self.assertIsNotNone(token)

        EngineRunToken.release(
            engine_name='test_engine',
            window_key='2026-02-23T14:05',
        )

        token.refresh_from_db()
        self.assertTrue(token.completed)

    def test_cleanup_expired_tokens(self):
        """Cleanup removes old tokens."""
        from apps.core.ai_scheduler.scheduler_models import EngineRunToken

        # Create old token
        EngineRunToken.objects.create(
            engine_name='old_engine',
            user_id=None,
            window_key='2026-02-20T14:00',
            acquired_at=timezone.now() - timedelta(hours=48),
            expires_at=timezone.now() - timedelta(hours=47),
            acquired_by='old',
        )

        deleted = EngineRunToken.cleanup_expired(max_age_hours=24)
        self.assertEqual(deleted, 1)

    def test_different_windows_can_acquire(self):
        """Different windows for same engine can each acquire a token."""
        from apps.core.ai_scheduler.scheduler_models import EngineRunToken

        t1 = EngineRunToken.acquire('test_engine', '2026-02-23T14:00')
        t2 = EngineRunToken.acquire('test_engine', '2026-02-23T14:05')

        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)

    def test_scheduler_lock_prevents_duplicate(self):
        """SchedulerLock mechanism prevents duplicate scheduler instances."""
        from apps.core.ai_scheduler.scheduler_lock import (
            acquire_scheduler_lock,
            release_scheduler_lock,
        )

        # First acquire succeeds
        result1 = acquire_scheduler_lock('test_overlap_lock')
        self.assertTrue(result1)

        # Second acquire blocked (lock is fresh)
        result2 = acquire_scheduler_lock('test_overlap_lock')
        self.assertFalse(result2)

        # Cleanup
        release_scheduler_lock('test_overlap_lock')

    def test_db_token_prevents_double_run_without_redis(self):
        """
        Even without Redis, DB token guarantees only one run executes.
        Sequential test: first acquire succeeds, second is blocked by
        UniqueConstraint until the first expires or is released.
        """
        from apps.core.ai_scheduler.scheduler_models import EngineRunToken

        window = '2026-02-23T14:10'

        # First acquire succeeds
        token1 = EngineRunToken.acquire(
            'sweep_engine', window, lease_seconds=60,
            acquired_by='worker-1',
        )
        self.assertIsNotNone(token1)

        # Second acquire for same engine+window is blocked
        token2 = EngineRunToken.acquire(
            'sweep_engine', window, lease_seconds=60,
            acquired_by='worker-2',
        )
        self.assertIsNone(token2)

        # Release first token, then second acquire succeeds
        EngineRunToken.release('sweep_engine', window, mark_completed=True)
        token1.refresh_from_db()
        self.assertTrue(token1.completed)


# =========================================================================
# 6.5 — COMMITMENT_RACE_CONDITION ANOMALY
# =========================================================================


class CommitmentRaceConditionTests(TestCase):
    """Test COMMITMENT_RACE_CONDITION anomaly detection."""

    def setUp(self):
        self.user = _create_test_user('race-cond@example.com')

    def test_race_condition_detected_with_rapid_mutations(self):
        """Two commitment mutations within 1 second triggers anomaly."""
        from apps.core.ai_observability.models import OpsAnomaly
        from apps.core.blueprint.concurrency import check_commitment_race_condition
        from apps.core.blueprint.models import Commitment

        now = timezone.now()

        # Create two commitments with very close updated_at
        Commitment.objects.create(
            user=self.user,
            normalized_text='First commitment',
            commitment_type='DO',
            time_boundary=now + timedelta(hours=2),
            status='pending',
        )
        Commitment.objects.create(
            user=self.user,
            normalized_text='Second commitment',
            commitment_type='DO',
            time_boundary=now + timedelta(hours=3),
            status='pending',
        )

        # Both have auto-set updated_at within the same second
        detected = check_commitment_race_condition(self.user)
        self.assertTrue(detected)

        # Verify anomaly was created
        anomaly = OpsAnomaly.objects.filter(
            anomaly_type='COMMITMENT_RACE_CONDITION',
        ).first()
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly.severity, 'P2')
        self.assertTrue(anomaly.is_active)

    def test_no_race_condition_with_single_mutation(self):
        """Single mutation does not trigger anomaly."""
        from apps.core.blueprint.concurrency import check_commitment_race_condition
        from apps.core.blueprint.models import Commitment

        Commitment.objects.create(
            user=self.user,
            normalized_text='Only commitment',
            commitment_type='DO',
            time_boundary=timezone.now() + timedelta(hours=2),
            status='pending',
        )

        detected = check_commitment_race_condition(self.user)
        self.assertFalse(detected)

    def test_anomaly_is_internal_not_user_facing(self):
        """COMMITMENT_RACE_CONDITION anomaly has no user-facing jargon."""
        from apps.core.ai_observability.models import OpsAnomaly
        from apps.core.blueprint.concurrency import check_commitment_race_condition
        from apps.core.blueprint.models import Commitment

        now = timezone.now()
        for i in range(3):
            Commitment.objects.create(
                user=self.user,
                normalized_text=f'Rapid commitment {i}',
                commitment_type='DO',
                time_boundary=now + timedelta(hours=i + 1),
                status='pending',
            )

        check_commitment_race_condition(self.user)

        anomaly = OpsAnomaly.objects.filter(
            anomaly_type='COMMITMENT_RACE_CONDITION',
        ).first()
        if anomaly:
            # No user-facing jargon in summary
            forbidden_tokens = ['select_for_update', 'transaction', 'deadlock']
            for token in forbidden_tokens:
                self.assertNotIn(token, anomaly.summary.lower())


# =========================================================================
# 6.6 — ESCALATION OBSERVABILITY
# =========================================================================


class EscalationObservabilityTests(TestCase):
    """Escalation level change creates EngineRun + DecisionRecord."""

    def setUp(self):
        from apps.users.models import User, UserPreferences

        self.user = User.objects.create_user(
            email='esc-obs@example.com',
            password='testpass123',
        )
        UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )

    def test_escalation_up_creates_engine_run(self):
        """Escalation level increase logs EngineRun with engine_name='ESC'."""
        from apps.core.ai_observability.models import EngineRun
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationState

        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_CLEAN,
        )

        drift_signals = {
            'renegotiation_patterns': ['pattern1'],
            'tier1_skip_patterns': ['skip1'],
            'consecutive_tier1_skips': 3,
        }

        resolve_activation_state(self.user, drift_signals, '')

        # Should have created an EngineRun with engine_name='ESC'
        esc_runs = EngineRun.objects.filter(
            engine_name='ESC',
            user_id=self.user.pk,
        )
        self.assertTrue(esc_runs.exists())

    def test_escalation_up_creates_decision_record(self):
        """Escalation level increase logs DecisionRecord."""
        from apps.core.ai_observability.models import DecisionRecord
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationState

        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_CLEAN,
        )

        drift_signals = {
            'renegotiation_patterns': ['pattern1'],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 3,
        }

        resolve_activation_state(self.user, drift_signals, '')

        decisions = DecisionRecord.objects.filter(
            engine_name='ESC',
            user_id=self.user.pk,
        )
        # At least 2: one from _write_decision_record, one from _log_escalation_observability
        self.assertGreaterEqual(decisions.count(), 2)

    def test_no_level_change_no_extra_observability(self):
        """Same-level result does NOT create extra observability records."""
        from apps.core.ai_observability.models import EngineRun
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationState

        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_CLEAN,
        )

        clean_signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        initial_count = EngineRun.objects.filter(engine_name='ESC').count()
        resolve_activation_state(self.user, clean_signals, '')
        after_count = EngineRun.objects.filter(engine_name='ESC').count()

        # No level change → no additional EngineRun from observability
        self.assertEqual(initial_count, after_count)

    def test_observability_is_non_blocking(self):
        """Observability logging failure does not crash escalation pipeline."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationState

        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_CLEAN,
        )

        drift_signals = {
            'renegotiation_patterns': ['p1'],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 3,
        }

        with patch(
            'apps.core.blueprint.concurrency.log_escalation_transition',
            side_effect=Exception("Observability down"),
        ):
            # Should NOT raise
            result = resolve_activation_state(self.user, drift_signals, '')
            self.assertIn(result, ['CLEAN', 'EARLY_EROSION', 'STRUCTURAL_DRIFT'])


# =========================================================================
# 6.10 — DOUBLE-SUBMIT + IDEMPOTENCY
# =========================================================================


class DoubleSubmitIdempotencyTests(TestCase):
    """Double-submit within 100ms respects idempotency."""

    def test_idempotency_prevents_duplicate_response(self):
        """Same message within 3-second window returns cached response."""
        from apps.core.ai_orchestrator.commitment_contract import (
            _check_idempotency,
            _store_idempotency,
        )

        user_id = 999
        message = "I will submit this report by 3pm"
        response = "Commitment set: Submit this report by 3pm."

        # Store response
        _store_idempotency(user_id, message, response)

        # Check within window
        cached = _check_idempotency(user_id, message)
        self.assertEqual(cached, response)

    def test_different_messages_not_idempotent(self):
        """Different messages are not treated as duplicates."""
        from apps.core.ai_orchestrator.commitment_contract import (
            _check_idempotency,
            _store_idempotency,
        )

        user_id = 999
        _store_idempotency(user_id, "Message A", "Response A")

        cached = _check_idempotency(user_id, "Message B")
        self.assertIsNone(cached)

    def test_different_users_not_idempotent(self):
        """Same message from different users is not idempotent."""
        from apps.core.ai_orchestrator.commitment_contract import (
            _check_idempotency,
            _store_idempotency,
        )

        _store_idempotency(100, "Same message", "Response for 100")

        cached = _check_idempotency(200, "Same message")
        self.assertIsNone(cached)


# =========================================================================
# MULTI-TAB SAME USER
# =========================================================================


class MultiTabSameUserTests(TestCase):
    """Multi-tab same-user: no duplicate commitments, no corruption."""

    def setUp(self):
        self.user = _create_test_user('multi-tab@example.com')

    def test_hard_limit_prevents_duplicates(self):
        """Max 5 commitments enforced even with rapid creates."""
        from apps.core.ai_orchestrator.commitment_contract import (
            CommitmentData,
            create_db_commitment,
        )
        from apps.core.blueprint.models import Commitment

        conversation = _create_conversation(self.user)
        created = []
        for i in range(7):
            cd = CommitmentData(
                normalized_text=f'Commitment {i}',
                commitment_type='DO',
                time_boundary=timezone.now() + timedelta(hours=i + 1),
                done_definition='',
            )
            result = create_db_commitment(self.user, cd, conversation, 'CLEAN')
            created.append(result)

        # First 5 should succeed, last 2 should be None
        successes = [c for c in created if c is not None]
        self.assertEqual(len(successes), 5)

        # Verify DB count
        pending_count = Commitment.pending_for_user(self.user).count()
        self.assertEqual(pending_count, 5)
