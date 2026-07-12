"""
WLJ Operations — Recovery Engine DB-level concurrency test (Phase II-A hardening).

Proves that two overlapping recovery cycles (or two workers) can never act on the
SAME incident: an incident whose row is held under ``SELECT … FOR UPDATE`` by another
connection is skipped (``skip_locked``), not double-processed. Postgres-only (real row
locking); skipped on other backends. Uses ``TransactionTestCase`` because real
cross-connection locking needs committed transactions, not nested savepoints.
"""
from __future__ import annotations

from django.db import connection, connections
from django.test import TransactionTestCase, override_settings
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

TEST_TYPE = "TEST_ANOMALY_CONC"


class _FakeHandler(RecoveryHandler):
    monitor_key = "test_conc"
    handled_anomaly_types = frozenset({TEST_TYPE})

    def __init__(self):
        self.policy = RecoveryPolicy(classification=R1, max_attempts=2, cooldown_seconds=0)
        self.recover_calls = 0

    def diagnose(self, anomaly):
        return RecoveryDiagnosis(target=anomaly.engine_name or "", reason="t", recoverable=True)

    def recover(self, diagnosis):
        self.recover_calls += 1
        return RecoveryOutcome(action_taken="fake", verification_deferred=False)

    def verify(self, diagnosis):
        return VerificationResult(healthy=True, evidence={})


@override_settings(OPS_RECOVERY_ENABLED=True)
class ConcurrencyLockTests(TransactionTestCase):
    def setUp(self):
        engine_mod._HANDLERS_READY = False
        self.handler = _FakeHandler()
        registry.register(self.handler)

    def _mk(self, engine):
        return OpsAnomaly.objects.create(
            severity="P2", engine_name=engine, anomaly_type=TEST_TYPE,
            summary="t", is_active=True,
        )

    def test_locked_incident_is_skipped(self):
        if connection.vendor != "postgresql":
            self.skipTest("row locking requires PostgreSQL")
        anomaly = self._mk("locked.x")

        # Hold FOR UPDATE on the anomaly row in a SEPARATE connection.
        conn2 = connections.create_connection("default")
        try:
            cur = conn2.cursor()
            cur.execute("BEGIN")
            cur.execute(
                "SELECT id FROM core_ops_anomaly WHERE id = %s FOR UPDATE", [anomaly.id]
            )
            # While the row is locked elsewhere, the recovery cycle must skip it.
            summary = run_recovery_cycle()
            cur.execute("ROLLBACK")
        finally:
            conn2.close()

        self.assertEqual(summary["locked_skipped"], 1)
        self.assertEqual(self.handler.recover_calls, 0)
        self.assertEqual(
            RecoveryAttempt.objects.filter(engine_name="locked.x").count(), 0,
            "a locked incident must not be acted on or audited by a 2nd cycle",
        )

    def test_unlocked_incident_processes_normally(self):
        self._mk("free.y")
        summary = run_recovery_cycle()
        self.assertEqual(summary["locked_skipped"], 0)
        self.assertEqual(summary["processed"], 1)
