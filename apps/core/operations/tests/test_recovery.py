"""
WLJ Operations — Recovery framework + pilot tests (Phase II).

Covers the Standard Recovery Lifecycle invariants (WLJ_OPERATIONS_VISION.md §5):
classification gate, verification-reuses-detection, finite bounds (R1 included),
cooldown/idempotency, recurrence → permanent-fix escalation, kill-switch no-op, and
the BeatTaskRetryHandler predicate reuse. Uses a controllable FakeHandler to drive
the engine deterministically without touching real Beat internals.
"""
from __future__ import annotations

from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.ai_observability.models import OpsAnomaly
from apps.core.operations.models import RecoveryAttempt
from apps.core.operations.recovery import engine as engine_mod
from apps.core.operations.recovery.base import (
    RecoveryDiagnosis,
    RecoveryHandler,
    RecoveryOutcome,
    VerificationResult,
    registry,
)
from apps.core.operations.recovery.engine import run_recovery_cycle
from apps.core.operations.recovery.policy import R1, RecoveryPolicy

TEST_TYPE = "TEST_ANOMALY"


class FakeHandler(RecoveryHandler):
    monitor_key = "test"
    handled_anomaly_types = frozenset({TEST_TYPE})

    def __init__(self, *, deferred=False, healthy=True, recoverable=True,
                 max_attempts=2, cooldown=0, recurrence_limit=None):
        self.policy = RecoveryPolicy(
            classification=R1, max_attempts=max_attempts, cooldown_seconds=cooldown,
            recurrence_limit=recurrence_limit,
        )
        self.deferred = deferred
        self.healthy = healthy
        self.recoverable = recoverable
        self.recover_calls = 0

    def diagnose(self, anomaly):
        return RecoveryDiagnosis(target=anomaly.engine_name or "", reason="test",
                                 recoverable=self.recoverable)

    def recover(self, diagnosis):
        self.recover_calls += 1
        return RecoveryOutcome(action_taken="fake recover",
                               verification_deferred=self.deferred)

    def verify(self, diagnosis):
        return VerificationResult(healthy=self.healthy, evidence={"h": self.healthy})


def _mk_anomaly(engine="task.x", atype=TEST_TYPE):
    return OpsAnomaly.objects.create(
        severity="P2", engine_name=engine, anomaly_type=atype,
        summary="test", is_active=True,
    )


@override_settings(OPS_RECOVERY_ENABLED=True)
class RecoveryEngineTests(TestCase):
    def setUp(self):
        # Isolate: force the engine to (re)register default handlers, then add ours.
        engine_mod._HANDLERS_READY = False
        self.handler = FakeHandler()
        registry.register(self.handler)

    def _register(self, handler):
        self.handler = handler
        registry.register(handler)

    def test_kill_switch_is_true_noop(self):
        _mk_anomaly()
        with override_settings(OPS_RECOVERY_ENABLED=False):
            summary = run_recovery_cycle()
        self.assertFalse(summary["enabled"])
        self.assertEqual(RecoveryAttempt.objects.count(), 0)

    def test_unhandled_anomaly_type_is_not_processed(self):
        _mk_anomaly(atype="TOTALLY_UNHANDLED")
        summary = run_recovery_cycle()
        self.assertEqual(summary["processed"], 0)
        self.assertEqual(RecoveryAttempt.objects.count(), 0)

    def test_unsafe_target_audited_once_as_R0(self):
        self._register(FakeHandler(recoverable=False))
        _mk_anomaly()
        run_recovery_cycle()
        run_recovery_cycle()  # second cycle must NOT add another skip row
        rows = RecoveryAttempt.objects.filter(phase=RecoveryAttempt.PHASE_SKIPPED_UNSAFE)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().classification, "R0")

    def test_happy_path_inline_verify_success(self):
        self._register(FakeHandler(deferred=False, healthy=True))
        _mk_anomaly()
        summary = run_recovery_cycle()
        self.assertEqual(summary["recovered"], 1)
        self.assertEqual(summary["verified"], 1)
        row = RecoveryAttempt.objects.get()
        self.assertEqual(row.phase, RecoveryAttempt.PHASE_VERIFIED)
        self.assertEqual(row.outcome, RecoveryAttempt.OUTCOME_SUCCESS)

    def test_deferred_verification_resolves_next_cycle(self):
        self._register(FakeHandler(deferred=True, healthy=True, cooldown=0))
        _mk_anomaly()
        run_recovery_cycle()  # attempt → PENDING
        pending = RecoveryAttempt.objects.get()
        self.assertEqual(pending.outcome, RecoveryAttempt.OUTCOME_PENDING)
        run_recovery_cycle()  # resolve pending → VERIFIED
        pending.refresh_from_db()
        self.assertEqual(pending.outcome, RecoveryAttempt.OUTCOME_SUCCESS)
        self.assertEqual(pending.phase, RecoveryAttempt.PHASE_VERIFIED)

    def test_verification_failure_never_succeeds_then_escalates(self):
        # The core safety test: a recovery that doesn't fix the signal never
        # records success, and exhausts to escalation.
        self._register(FakeHandler(deferred=False, healthy=False,
                                   max_attempts=2, cooldown=0))
        _mk_anomaly()
        run_recovery_cycle()  # attempt 1 → FAILED
        run_recovery_cycle()  # attempt 2 → FAILED
        run_recovery_cycle()  # exhausted → ESCALATED
        self.assertEqual(
            RecoveryAttempt.objects.filter(outcome=RecoveryAttempt.OUTCOME_SUCCESS).count(), 0
        )
        self.assertEqual(
            RecoveryAttempt.objects.filter(phase=RecoveryAttempt.PHASE_ESCALATED).count(), 1
        )

    def test_cooldown_enforces_idempotency(self):
        # With a positive cooldown, two back-to-back cycles produce ONE action.
        self._register(FakeHandler(deferred=True, healthy=True, cooldown=300))
        _mk_anomaly()
        run_recovery_cycle()
        run_recovery_cycle()
        self.assertEqual(self.handler.recover_calls, 1)

    def test_recurrence_triggers_permanent_fix_escalation(self):
        self._register(FakeHandler(deferred=False, healthy=True,
                                   max_attempts=10, cooldown=0, recurrence_limit=2))
        _mk_anomaly()
        run_recovery_cycle()  # success 1
        run_recovery_cycle()  # success 2
        run_recovery_cycle()  # recurrence >= limit → ESCALATED
        esc = RecoveryAttempt.objects.filter(phase=RecoveryAttempt.PHASE_ESCALATED)
        self.assertEqual(esc.count(), 1)
        self.assertIn("recurring", esc.first().action_taken.lower())

    def test_recovery_never_writes_incident_state(self):
        # Recovery must never flip is_active — the reconcile pipeline owns that.
        self._register(FakeHandler(deferred=False, healthy=True))
        anomaly = _mk_anomaly()
        run_recovery_cycle()
        anomaly.refresh_from_db()
        self.assertTrue(anomaly.is_active)


class PolicyTests(TestCase):
    def test_r1_bound_is_finite(self):
        with self.assertRaises(ValueError):
            RecoveryPolicy(classification=R1, max_attempts=0, cooldown_seconds=0)

    def test_unknown_classification_rejected(self):
        with self.assertRaises(ValueError):
            RecoveryPolicy(classification="R9", max_attempts=1, cooldown_seconds=0)

    def test_only_r1_r2_auto_executable(self):
        self.assertTrue(RecoveryPolicy("R1", 1, 0).auto_executable)
        self.assertTrue(RecoveryPolicy("R2", 1, 0).auto_executable)
        self.assertFalse(RecoveryPolicy("R0", 1, 0).auto_executable)
        self.assertFalse(RecoveryPolicy("R3", 1, 0).auto_executable)


class BeatTaskRetryHandlerTests(TestCase):
    def _handler(self):
        from apps.core.operations.recovery.handlers import BeatTaskRetryHandler
        return BeatTaskRetryHandler()

    @override_settings(OPS_RECOVERY_BEAT_RETRY=True,
                       OPS_RECOVERY_BEAT_RETRY_ALLOWLIST=["apps.core.tasks.some_idempotent"])
    def test_diagnose_allowlisted_is_recoverable(self):
        h = self._handler()
        a = _mk_anomaly(engine="apps.core.tasks.some_idempotent", atype="MISSED_RUN")
        self.assertTrue(h.diagnose(a).recoverable)

    @override_settings(OPS_RECOVERY_BEAT_RETRY=True, OPS_RECOVERY_BEAT_RETRY_ALLOWLIST=[])
    def test_diagnose_not_allowlisted_is_observe_only(self):
        h = self._handler()
        a = _mk_anomaly(engine="apps.core.tasks.not_listed", atype="MISSED_RUN")
        self.assertFalse(h.diagnose(a).recoverable)

    def test_verify_reuses_scheduled_task_predicate(self):
        h = self._handler()
        diag = RecoveryDiagnosis(target="apps.core.tasks.x", reason="")
        with mock.patch(
            "apps.core.ai_observability.scheduled_task_monitor.compute_scheduled_task_states",
            return_value=[{"task_name": "apps.core.tasks.x", "status": "OK"}],
        ):
            self.assertTrue(h.verify(diag).healthy)
        with mock.patch(
            "apps.core.ai_observability.scheduled_task_monitor.compute_scheduled_task_states",
            return_value=[{"task_name": "apps.core.tasks.x", "status": "MISSED"}],
        ):
            self.assertFalse(h.verify(diag).healthy)
