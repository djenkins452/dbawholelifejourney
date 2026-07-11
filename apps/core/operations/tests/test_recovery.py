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


# The Phase III controlled pilot task — the safest available (read-only recompute,
# zero post_save cascade, no user-facing output, OPS-1 monitored). This is exactly
# the task recommended for the first production allowlist entry.
PILOT_TASK = "apps.core.health_briefing.tasks.recompute_all_health_briefings_task"


@override_settings(
    OPS_RECOVERY_ENABLED=True,
    OPS_RECOVERY_BEAT_RETRY=True,
    OPS_RECOVERY_BEAT_RETRY_ALLOWLIST=[PILOT_TASK],
)
class BeatTaskRetryPilotE2ETests(TestCase):
    """Controlled end-to-end simulation of the REAL pilot handler through the REAL
    RecoveryEngine against a REAL MISSED_RUN incident — the 'smallest, safest
    scenario' for Phase III runtime verification. Only the enqueue boundary
    (safe_enqueue) and the post-recovery scheduled-state are mocked; gating,
    auditing, verification-reuse, lifecycle, and cooldown are all real."""

    def setUp(self):
        engine_mod._HANDLERS_READY = False  # force real default-handler registration

    def _backdate(self, row, seconds):
        # created_at is auto_now_add; .update() bypasses it to simulate elapsed time.
        RecoveryAttempt.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - __import__("datetime").timedelta(seconds=seconds)
        )

    def test_full_recovery_lifecycle_success(self):
        anomaly = _mk_anomaly(engine=PILOT_TASK, atype="MISSED_RUN")
        # Cycle 1 — recover: real handler resolves the real registered task and calls
        # safe_enqueue (mocked so no real task fires). Verification is deferred.
        with mock.patch(
            "apps.core.celery_utils.safe_enqueue", return_value=True
        ) as m_enq:
            run_recovery_cycle()
        self.assertEqual(m_enq.call_count, 1, "real pilot task must resolve + enqueue")
        row = RecoveryAttempt.objects.get()
        self.assertEqual(row.classification, "R1")
        self.assertEqual(row.phase, RecoveryAttempt.PHASE_RECOVER_ATTEMPTED)
        self.assertEqual(row.outcome, RecoveryAttempt.OUTCOME_PENDING)

        # Simulate the re-enqueued task having run: predicate now reports OK.
        self._backdate(row, 200)  # past the 120s cooldown
        with mock.patch(
            "apps.core.ai_observability.scheduled_task_monitor.compute_scheduled_task_states",
            return_value=[{"task_name": PILOT_TASK, "status": "OK"}],
        ):
            run_recovery_cycle()  # Cycle 2 — resolve deferred verification
        row.refresh_from_db()
        self.assertEqual(row.phase, RecoveryAttempt.PHASE_VERIFIED)
        self.assertEqual(row.outcome, RecoveryAttempt.OUTCOME_SUCCESS)
        # Incident lifecycle untouched by recovery (SAME owns it).
        anomaly.refresh_from_db()
        self.assertTrue(anomaly.is_active)

    def test_no_duplicate_execution_within_cooldown(self):
        _mk_anomaly(engine=PILOT_TASK, atype="MISSED_RUN")
        with mock.patch(
            "apps.core.celery_utils.safe_enqueue", return_value=True
        ) as m_enq:
            run_recovery_cycle()
            run_recovery_cycle()  # immediate re-run: pending + cooldown → no 2nd action
        self.assertEqual(m_enq.call_count, 1)

    @override_settings(OPS_RECOVERY_BEAT_RETRY_ALLOWLIST=[])
    def test_non_allowlisted_task_is_observe_only(self):
        _mk_anomaly(engine=PILOT_TASK, atype="MISSED_RUN")
        with mock.patch(
            "apps.core.celery_utils.safe_enqueue", return_value=True
        ) as m_enq:
            run_recovery_cycle()
        self.assertEqual(m_enq.call_count, 0, "no enqueue for a non-allowlisted task")
        self.assertEqual(
            RecoveryAttempt.objects.filter(
                phase=RecoveryAttempt.PHASE_SKIPPED_UNSAFE, classification="R0"
            ).count(), 1
        )

    @override_settings(OPS_RECOVERY_ENABLED=False)
    def test_rollback_disabled_performs_no_execution(self):
        _mk_anomaly(engine=PILOT_TASK, atype="MISSED_RUN")
        with mock.patch(
            "apps.core.celery_utils.safe_enqueue", return_value=True
        ) as m_enq:
            summary = run_recovery_cycle()
        self.assertFalse(summary["enabled"])
        self.assertEqual(m_enq.call_count, 0)
        self.assertEqual(RecoveryAttempt.objects.count(), 0)


@override_settings(
    OPS_RECOVERY_ENABLED=True,
    OPS_RECOVERY_ENGINE_RETRIGGER=True,
    OPS_RECOVERY_ENGINE_ALLOWLIST=["SAE"],
)
class EngineStarvationPilotE2ETests(TestCase):
    """Controlled E2E for the re-trigger shape (ENGINE_STARVATION → async verify)."""

    def setUp(self):
        engine_mod._HANDLERS_READY = False

    def test_full_retrigger_lifecycle_success(self):
        anomaly = _mk_anomaly(engine="SAE", atype="ENGINE_STARVATION")
        with mock.patch(
            "apps.core.ai_observability.engine_registry.get_engine_meta",
            return_value={"can_manual_run": True},
        ), mock.patch(
            "apps.core.ai_observability.models.EngineExecutionLog.is_engine_active",
            return_value=False,
        ), mock.patch(
            "apps.core.celery_utils.safe_enqueue", return_value=True
        ) as m_enq:
            run_recovery_cycle()  # cycle 1 — re-trigger
        self.assertEqual(m_enq.call_count, 1, "starved engine must be re-triggered")
        row = RecoveryAttempt.objects.get()
        self.assertEqual(row.classification, "R1")
        self.assertEqual(row.outcome, RecoveryAttempt.OUTCOME_PENDING)

        self._backdate(row, 400)  # past the 300s cooldown
        with mock.patch(
            "apps.core.ai_observability.same_engine.engine_ran_within_24h",
            return_value=True,
        ):
            run_recovery_cycle()  # cycle 2 — deferred verify
        row.refresh_from_db()
        self.assertEqual(row.outcome, RecoveryAttempt.OUTCOME_SUCCESS)
        anomaly.refresh_from_db()
        self.assertTrue(anomaly.is_active)  # SAME owns lifecycle

    def _backdate(self, row, seconds):
        RecoveryAttempt.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - __import__("datetime").timedelta(seconds=seconds)
        )

    @override_settings(OPS_RECOVERY_ENGINE_ALLOWLIST=[])
    def test_non_allowlisted_engine_is_observe_only(self):
        _mk_anomaly(engine="SAE", atype="ENGINE_STARVATION")
        with mock.patch(
            "apps.core.celery_utils.safe_enqueue", return_value=True
        ) as m_enq:
            run_recovery_cycle()
        self.assertEqual(m_enq.call_count, 0)
        self.assertEqual(
            RecoveryAttempt.objects.filter(
                phase=RecoveryAttempt.PHASE_SKIPPED_UNSAFE, classification="R0"
            ).count(), 1
        )


@override_settings(OPS_RECOVERY_ENABLED=True, OPS_RECOVERY_MATURITY_SNAPSHOT=True)
class MaturitySnapshotPilotE2ETests(TestCase):
    """Controlled E2E for the recompute shape (MATURITY_SNAPSHOT_STALE → SYNC verify).

    Distinct from the re-trigger handlers: recompute runs synchronously so
    verification is immediate — the whole lifecycle completes in ONE cycle."""

    def setUp(self):
        engine_mod._HANDLERS_READY = False

    def test_synchronous_recompute_lifecycle_success(self):
        anomaly = _mk_anomaly(engine="SystemMaturitySnapshot", atype="MATURITY_SNAPSHOT_STALE")
        with mock.patch(
            "apps.core.ai_observability.maturity_engine.create_daily_snapshot"
        ) as m_recompute, mock.patch(
            "apps.core.ai_observability.same_engine.maturity_snapshot_age_days",
            return_value=0,  # fresh after recompute
        ):
            run_recovery_cycle()  # recover + verify in ONE cycle (synchronous)
        m_recompute.assert_called_once()
        row = RecoveryAttempt.objects.get()
        self.assertEqual(row.phase, RecoveryAttempt.PHASE_VERIFIED)
        self.assertEqual(row.outcome, RecoveryAttempt.OUTCOME_SUCCESS)
        anomaly.refresh_from_db()
        self.assertTrue(anomaly.is_active)

    @override_settings(OPS_RECOVERY_MATURITY_SNAPSHOT=False)
    def test_disabled_is_observe_only(self):
        _mk_anomaly(engine="SystemMaturitySnapshot", atype="MATURITY_SNAPSHOT_STALE")
        with mock.patch(
            "apps.core.ai_observability.maturity_engine.create_daily_snapshot"
        ) as m_recompute:
            run_recovery_cycle()
        m_recompute.assert_not_called()
        self.assertEqual(
            RecoveryAttempt.objects.filter(
                phase=RecoveryAttempt.PHASE_SKIPPED_UNSAFE
            ).count(), 1
        )


class MaturityStalenessDetectorTests(TestCase):
    """The new detector's threshold logic (fills the previously-unmonitored gap)."""

    def _detect(self, age):
        from apps.core.ai_observability import same_engine
        with mock.patch.object(same_engine, "maturity_snapshot_age_days", return_value=age):
            return same_engine._detect_stale_maturity_snapshot(timezone.now())

    def test_never_computed_does_not_flag(self):
        self.assertEqual(self._detect(None), [])

    def test_fresh_does_not_flag(self):
        self.assertEqual(self._detect(1), [])

    def test_stale_flags_maturity_snapshot_stale(self):
        out = self._detect(3)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["anomaly_type"], "MATURITY_SNAPSHOT_STALE")
        self.assertEqual(out[0]["severity"], "P3")

    def test_age_none_when_no_snapshot_rows(self):
        from apps.core.ai_observability.same_engine import maturity_snapshot_age_days
        self.assertIsNone(maturity_snapshot_age_days())
