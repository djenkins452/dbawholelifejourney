"""
WLJ Operations — Recovery Shadow Mode tests (Phase II-A validation).

Shadow Mode is the final validation stage before the first automatic production
recovery: the engine runs the ENTIRE deterministic lifecycle exactly as it would
live, then STOPS immediately before executing the recovery action. It records what
recovery WOULD have done and performs NO action, NO verification, NO state mutation,
NO incident closure, NO side effect.

These tests prove:
  * the mode resolver + precedence (DISABLED / SHADOW / ACTIVE, legacy bridge);
  * shadow runs every deterministic step but never calls recover()/verify();
  * no incident closes; incident state untouched;
  * the shadow audit row is correct + distinguishable from disabled/cooldown/unsafe/escalated;
  * shadow is idempotent (no 60s flood);
  * DISABLED remains a true no-op; ACTIVE behaviour is unchanged;
  * the SAME enqueue mirror stays in exact sync with the canonical resolver.
"""
from __future__ import annotations

from django.test import TestCase, override_settings

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
from apps.core.operations.recovery.mode import (
    ACTIVE,
    DISABLED,
    SHADOW,
    get_recovery_mode,
    recovery_is_enabled,
)
from apps.core.operations.recovery.policy import R1, RecoveryPolicy

TEST_TYPE = "TEST_ANOMALY_SHADOW"


class ShadowFakeHandler(RecoveryHandler):
    """Tracks whether the engine ever crossed the action/verification boundary."""

    monitor_key = "test_shadow"
    handled_anomaly_types = frozenset({TEST_TYPE})
    verification_predicate = "fake_predicate (test)"

    def __init__(self, *, recoverable=True):
        self.policy = RecoveryPolicy(classification=R1, max_attempts=2, cooldown_seconds=0)
        self.recoverable = recoverable
        self.diagnose_calls = 0
        self.recover_calls = 0
        self.verify_calls = 0

    def diagnose(self, anomaly):
        self.diagnose_calls += 1
        return RecoveryDiagnosis(
            target=anomaly.engine_name or "", reason="test reason",
            evidence={"probe": "value"}, recoverable=self.recoverable,
        )

    def describe_action(self, diagnosis):
        return f"re-enqueue '{diagnosis.target}'"

    def recover(self, diagnosis):
        self.recover_calls += 1
        return RecoveryOutcome(action_taken="fake recover")

    def verify(self, diagnosis):
        self.verify_calls += 1
        return VerificationResult(healthy=True, evidence={})


def _mk_anomaly(engine="task.x", atype=TEST_TYPE):
    return OpsAnomaly.objects.create(
        severity="P2", engine_name=engine, anomaly_type=atype,
        summary="test", is_active=True,
    )


# ── Mode resolver + precedence ─────────────────────────────────────────────
class RecoveryModeResolverTests(TestCase):
    def test_default_is_disabled(self):
        with override_settings(OPS_RECOVERY_MODE="DISABLED", OPS_RECOVERY_ENABLED=False):
            self.assertEqual(get_recovery_mode(), DISABLED)
            self.assertFalse(recovery_is_enabled())

    def test_explicit_shadow(self):
        with override_settings(OPS_RECOVERY_MODE="SHADOW", OPS_RECOVERY_ENABLED=False):
            self.assertEqual(get_recovery_mode(), SHADOW)
            self.assertTrue(recovery_is_enabled())

    def test_explicit_active(self):
        with override_settings(OPS_RECOVERY_MODE="ACTIVE", OPS_RECOVERY_ENABLED=False):
            self.assertEqual(get_recovery_mode(), ACTIVE)

    def test_legacy_enabled_bridges_to_active(self):
        # Original master switch still works: True → ACTIVE when mode is default.
        with override_settings(OPS_RECOVERY_MODE="DISABLED", OPS_RECOVERY_ENABLED=True):
            self.assertEqual(get_recovery_mode(), ACTIVE)

    def test_explicit_shadow_not_upgraded_by_legacy_flag(self):
        # A stray legacy True must NEVER upgrade an explicit SHADOW to ACTIVE.
        with override_settings(OPS_RECOVERY_MODE="SHADOW", OPS_RECOVERY_ENABLED=True):
            self.assertEqual(get_recovery_mode(), SHADOW)

    def test_unknown_mode_fails_safe_to_disabled(self):
        with override_settings(OPS_RECOVERY_MODE="BOGUS", OPS_RECOVERY_ENABLED=False):
            self.assertEqual(get_recovery_mode(), DISABLED)

    def test_case_insensitive(self):
        with override_settings(OPS_RECOVERY_MODE="shadow", OPS_RECOVERY_ENABLED=False):
            self.assertEqual(get_recovery_mode(), SHADOW)


# ── Shadow lifecycle behaviour ─────────────────────────────────────────────
@override_settings(OPS_RECOVERY_MODE="SHADOW", OPS_RECOVERY_ENABLED=False)
class ShadowExecutionTests(TestCase):
    def setUp(self):
        engine_mod._HANDLERS_READY = False
        self.handler = ShadowFakeHandler()
        registry.register(self.handler)

    def test_shadow_runs_diagnose_but_never_acts_or_verifies(self):
        _mk_anomaly()
        summary = run_recovery_cycle()
        # Deterministic lifecycle ran...
        self.assertEqual(summary["mode"], SHADOW)
        self.assertEqual(self.handler.diagnose_calls, 1)
        # ...but stopped before the action/verification boundary.
        self.assertEqual(self.handler.recover_calls, 0)
        self.assertEqual(self.handler.verify_calls, 0)

    def test_shadow_records_one_distinct_shadow_row(self):
        _mk_anomaly()
        run_recovery_cycle()
        rows = RecoveryAttempt.objects.all()
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.phase, RecoveryAttempt.PHASE_SHADOW)
        self.assertEqual(row.outcome, RecoveryAttempt.OUTCOME_SHADOW)
        self.assertEqual(row.mode, RecoveryAttempt.MODE_SHADOW)
        self.assertEqual(row.classification, "R1")
        self.assertTrue(row.evidence_before["would_execute"])
        self.assertEqual(row.evidence_before["verification_predicate"], "fake_predicate (test)")
        self.assertEqual(row.evidence_before["skipped_because"], "Shadow Mode — simulated only")
        self.assertIn("would re-enqueue", row.action_taken.lower())

    def test_shadow_row_is_distinguishable_from_real_phases(self):
        _mk_anomaly()
        run_recovery_cycle()
        # No real lifecycle phase/outcome may appear in shadow.
        for phase in [RecoveryAttempt.PHASE_RECOVER_ATTEMPTED, RecoveryAttempt.PHASE_VERIFIED,
                      RecoveryAttempt.PHASE_ESCALATED, RecoveryAttempt.PHASE_SKIPPED_UNSAFE,
                      RecoveryAttempt.PHASE_CLOSED]:
            self.assertEqual(RecoveryAttempt.objects.filter(phase=phase).count(), 0)
        for outcome in [RecoveryAttempt.OUTCOME_SUCCESS, RecoveryAttempt.OUTCOME_FAILED,
                        RecoveryAttempt.OUTCOME_PENDING]:
            self.assertEqual(RecoveryAttempt.objects.filter(outcome=outcome).count(), 0)

    def test_shadow_never_closes_or_mutates_incident(self):
        anomaly = _mk_anomaly()
        run_recovery_cycle()
        anomaly.refresh_from_db()
        self.assertTrue(anomaly.is_active)  # incident lifecycle untouched

    def test_shadow_is_idempotent_no_flood(self):
        _mk_anomaly()
        run_recovery_cycle()
        run_recovery_cycle()
        run_recovery_cycle()
        # One SHADOW row per incident occurrence — never one per 60s cycle.
        self.assertEqual(
            RecoveryAttempt.objects.filter(phase=RecoveryAttempt.PHASE_SHADOW).count(), 1
        )

    def test_shadow_non_recoverable_records_observe_only(self):
        registry.register(ShadowFakeHandler(recoverable=False))
        _mk_anomaly()
        run_recovery_cycle()
        row = RecoveryAttempt.objects.get()
        self.assertEqual(row.phase, RecoveryAttempt.PHASE_SHADOW)
        self.assertEqual(row.classification, "R0")
        self.assertFalse(row.evidence_before["would_execute"])
        self.assertIn("would observe only", row.action_taken.lower())

    def test_summary_counts_would_recover(self):
        _mk_anomaly()
        summary = run_recovery_cycle()
        self.assertEqual(summary["shadowed"], 1)
        self.assertEqual(summary["would_recover"], 1)
        self.assertEqual(summary["would_observe"], 0)
        # Real counters stay zero in shadow.
        self.assertEqual(summary["recovered"], 0)
        self.assertEqual(summary["verified"], 0)


# ── DISABLED remains a true no-op ──────────────────────────────────────────
class DisabledModeTests(TestCase):
    def setUp(self):
        engine_mod._HANDLERS_READY = False
        registry.register(ShadowFakeHandler())

    @override_settings(OPS_RECOVERY_MODE="DISABLED", OPS_RECOVERY_ENABLED=False)
    def test_disabled_does_no_work(self):
        _mk_anomaly()
        summary = run_recovery_cycle()
        self.assertFalse(summary["enabled"])
        self.assertEqual(summary["mode"], DISABLED)
        self.assertEqual(RecoveryAttempt.objects.count(), 0)


# ── ACTIVE behaviour unchanged ─────────────────────────────────────────────
@override_settings(OPS_RECOVERY_MODE="ACTIVE", OPS_RECOVERY_ENABLED=False)
class ActiveModeUnchangedTests(TestCase):
    def setUp(self):
        engine_mod._HANDLERS_READY = False
        self.handler = ShadowFakeHandler()
        registry.register(self.handler)

    def test_active_actually_recovers_and_verifies(self):
        _mk_anomaly()
        summary = run_recovery_cycle()
        self.assertEqual(summary["mode"], ACTIVE)
        self.assertEqual(self.handler.recover_calls, 1)   # real action
        self.assertEqual(self.handler.verify_calls, 1)    # real verification
        row = RecoveryAttempt.objects.get()
        self.assertEqual(row.mode, RecoveryAttempt.MODE_ACTIVE)
        self.assertEqual(row.phase, RecoveryAttempt.PHASE_VERIFIED)
        self.assertEqual(RecoveryAttempt.objects.filter(
            phase=RecoveryAttempt.PHASE_SHADOW).count(), 0)


# ── Telemetry surfaces mode + shadow counts ────────────────────────────────
@override_settings(OPS_RECOVERY_MODE="SHADOW", OPS_RECOVERY_ENABLED=False)
class ShadowTelemetryTests(TestCase):
    def setUp(self):
        engine_mod._HANDLERS_READY = False
        registry.register(ShadowFakeHandler())

    def test_telemetry_reports_shadow_mode_and_counts(self):
        from apps.core.operations.recovery.telemetry import build_recovery_telemetry

        _mk_anomaly()
        run_recovery_cycle()
        section = build_recovery_telemetry()
        self.assertEqual(section["mode"], SHADOW)
        self.assertTrue(section["enabled"])
        self.assertEqual(section["counts"]["shadowed_24h"], 1)
        self.assertEqual(section["counts"]["would_recover_24h"], 1)
        # A simulated row is flagged for the Command Center.
        self.assertTrue(section["recent"][0]["simulated"])
        self.assertEqual(section["recent"][0]["mode"], RecoveryAttempt.MODE_SHADOW)


# ── Telemetry exposes recovery CONFIG truth even when DISABLED ──────────────
@override_settings(
    OPS_RECOVERY_MODE="DISABLED",
    OPS_RECOVERY_ENABLED=False,
    OPS_RECOVERY_BEAT_RETRY=True,
    OPS_RECOVERY_BEAT_RETRY_ALLOWLIST=["apps.core.tasks.some_task"],
    OPS_RECOVERY_ENGINE_RETRIGGER=False,
    OPS_RECOVERY_ENGINE_ALLOWLIST=[],
    OPS_RECOVERY_MATURITY_SNAPSHOT=False,
)
class RecoveryConfigTelemetryTests(TestCase):
    """Config visibility must NOT depend on recovery being enabled — an operator
    needs mode source, handler roster, and allowlists precisely when DISABLED."""

    def test_config_block_present_when_disabled(self):
        from apps.core.operations.recovery.handlers import register_default_handlers
        from apps.core.operations.recovery.telemetry import build_recovery_telemetry

        register_default_handlers()  # idempotent — ensure the real handlers exist
        section = build_recovery_telemetry()

        self.assertEqual(section["mode"], DISABLED)
        self.assertEqual(section["mode_source"], "OPS_RECOVERY_MODE")
        cfg = section["config"]
        self.assertIsNotNone(cfg, "config block must be present even when DISABLED")
        # The three real handlers are always CONFIGURED (registered), even off.
        self.assertGreaterEqual(cfg["handlers_configured"], 3)
        # Only the beat-retry flag is on in this scenario.
        self.assertTrue(cfg["beat_retry_enabled"])
        self.assertEqual(cfg["beat_retry_allowlist_count"], 1)
        self.assertFalse(cfg["engine_retrigger_enabled"])
        self.assertFalse(cfg["maturity_snapshot_enabled"])
        self.assertGreaterEqual(cfg["handlers_enabled"], 1)
        # Facts-only: every handler row carries its enabled flag + allowlist count.
        beat = next(h for h in cfg["handlers"] if h["monitor_key"] == "scheduled_task")
        self.assertTrue(beat["enabled"])
        self.assertEqual(beat["allowlist_count"], 1)

    def test_describe_mode_source_reflects_legacy_bridge(self):
        from apps.core.operations.recovery.mode import describe_mode_source

        with override_settings(OPS_RECOVERY_MODE="", OPS_RECOVERY_ENABLED=True):
            self.assertEqual(describe_mode_source(), "OPS_RECOVERY_ENABLED (legacy bridge)")


# ── SAME enqueue mirror stays in exact sync with the canonical resolver ─────
class MirrorSyncTests(TestCase):
    """The SAME enqueue gate mirrors get_recovery_mode() via settings only (import
    boundary). This proves the mirror agrees with the canonical resolver for every
    (mode, legacy-flag) combination — so the two can never silently drift."""

    def test_mirror_matches_canonical_resolver(self):
        from apps.core.ai_observability.same_engine import _recovery_enqueue_enabled

        matrix = [
            ("DISABLED", False), ("DISABLED", True),
            ("SHADOW", False), ("SHADOW", True),
            ("ACTIVE", False), ("ACTIVE", True),
            ("BOGUS", False), ("BOGUS", True),
            ("shadow", False),
        ]
        for mode_val, legacy in matrix:
            with override_settings(OPS_RECOVERY_MODE=mode_val, OPS_RECOVERY_ENABLED=legacy):
                from django.conf import settings
                self.assertEqual(
                    _recovery_enqueue_enabled(settings),
                    recovery_is_enabled(),
                    f"mirror drift at OPS_RECOVERY_MODE={mode_val!r}, ENABLED={legacy}",
                )
