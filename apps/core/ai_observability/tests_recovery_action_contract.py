# ==============================================================================
# File: apps/core/ai_observability/tests_recovery_action_contract.py
# Description: Contract — OPERATIONS NEVER ADVERTISES A RECOVERY ACTION IT CANNOT RUN.
#
#   Production 2026-08-29: the Ops Wall recommended "Clear ICQG suppression cache";
#   clicking it returned "Cache clear failed: No module named
#   'apps.core.ai_quality.models'". That module HAS NEVER EXISTED (the module is
#   `quality_models`), and the handler also filtered on `suppressed_at`, a field that
#   has never existed on the model. The handler was dead from the day it was written
#   and had never once succeeded — nothing detected it, because no test ever asserted
#   that an advertised recovery action can actually execute.
#
#   Every `suggested_actions` entry renders as a clickable button on the Wall, and
#   `actions[0]` becomes the headline RECOMMENDED ACTION, so an unexecutable entry is
#   a customer-visible promise WLJ cannot keep.
# ==============================================================================
import ast
import inspect
from unittest import mock

from django.test import TestCase

from apps.core.ai_observability import ops_telemetry, same_engine
from apps.core.ai_observability import scheduled_task_monitor

# Signatures of a STRUCTURAL defect — the handler could not run at all, as opposed to
# a legitimate domain failure (wrong engine, nothing to do, a service being down).
_STRUCTURAL = ("no module named", "unknown action", "has no attribute",
               "cannot resolve keyword", "unexpected keyword", "not defined",
               "importerror", "fielderror", "attributeerror")


def _advertised_actions():
    """Every action string Operations can advertise, read from the SOURCE of the
    detectors rather than by running them — so a detector that only fires under rare
    production conditions is still covered."""
    found = set()
    for module in (same_engine, scheduled_task_monitor, ops_telemetry):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, val in zip(node.keys, node.values):
                if (isinstance(key, ast.Constant) and key.value == "action"
                        and isinstance(val, ast.Constant)
                        and isinstance(val.value, str)):
                    found.add(val.value)
    return found


class AdvertisedRecoveryActionsAreExecutableTests(TestCase):

    def test_detectors_advertise_at_least_the_known_actions(self):
        """Guard the guard: if the extraction silently found nothing, every other
        assertion below would vacuously pass."""
        actions = _advertised_actions()
        self.assertIn("clear_suppression_cache", actions)
        self.assertIn("rerun_engine", actions)
        self.assertGreaterEqual(len(actions), 5)

    def test_every_advertised_action_is_dispatchable(self):
        """1, 3 — recommendation and execution cannot drift apart."""
        undispatchable = []
        for action in sorted(_advertised_actions()):
            result = ops_telemetry._execute_action(action, "ICQG", "contract-trace")
            detail = str((result or {}).get("detail", "")).lower()
            if "unknown action" in detail:
                undispatchable.append(action)
        self.assertEqual(undispatchable, [],
                         f"Operations advertises actions it cannot execute: "
                         f"{undispatchable}")

    def test_no_advertised_action_fails_structurally(self):
        """2, 9 — a removed or renamed dependency breaks CI instead of silently
        leaving a dead button on the Wall. Each action is actually INVOKED against a
        clean database: a missing module, a renamed field or a vanished attribute
        surfaces here, while a legitimate domain outcome does not."""
        broken = {}
        for action in sorted(_advertised_actions()):
            with mock.patch.object(ops_telemetry, "_action_rerun_engine",
                                   return_value={"status": "success",
                                                 "detail": "stubbed (enqueue)"}):
                result = ops_telemetry._execute_action(action, "ICQG", "contract-trace")
            detail = str((result or {}).get("detail", "")).lower()
            if any(sig in detail for sig in _STRUCTURAL):
                broken[action] = (result or {}).get("detail")
        self.assertEqual(broken, {},
                         f"advertised recovery actions are structurally broken: {broken}")

    def test_every_action_returns_a_recognised_status(self):
        """4, 8 — the Wall renders from the deterministic result, so the result must
        always be one of the states the Wall understands."""
        for action in sorted(_advertised_actions()):
            with mock.patch.object(ops_telemetry, "_action_rerun_engine",
                                   return_value={"status": "success", "detail": "stub"}):
                result = ops_telemetry._execute_action(action, "ICQG", "t")
            self.assertIn((result or {}).get("status"),
                          {"success", "failure", "info"}, f"{action} -> {result}")


class SuppressionReleaseTests(TestCase):
    """The ICQG operation itself, against its CURRENT canonical authority."""

    def _record(self, *, hours_ahead, count=3):
        from datetime import timedelta

        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from apps.core.ai_quality.quality_models import QualitySuppressionRecord
        user = get_user_model().objects.create_user(
            email=f"supp{hours_ahead}-{count}@test.com", password="x")
        now = timezone.now()
        return QualitySuppressionRecord.objects.create(
            user=user, signature_hash=f"sig-{hours_ahead}-{count}",
            suppressed_until=now + timedelta(hours=hours_ahead),
            last_seen_at=now, last_priority=3, count=count)

    def test_it_releases_active_suppression_windows(self):
        from django.utils import timezone
        rec = self._record(hours_ahead=48)
        out = ops_telemetry._action_clear_suppression_cache("ICQG")
        self.assertEqual(out["status"], "success")
        rec.refresh_from_db()
        self.assertLessEqual(rec.suppressed_until, timezone.now(),
                             "the suppression gate was not released")

    def test_it_preserves_suppression_history(self):
        """The count/last_seen record is the operator's evidence WHILE diagnosing a
        suppression storm — releasing the gate must not destroy the diagnosis."""
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord
        rec = self._record(hours_ahead=48, count=11)
        ops_telemetry._action_clear_suppression_cache("ICQG")
        self.assertTrue(QualitySuppressionRecord.objects.filter(pk=rec.pk).exists(),
                        "suppression evidence was deleted")
        rec.refresh_from_db()
        self.assertEqual(rec.count, 11)

    def test_it_is_idempotent(self):
        """7 — a retry releases nothing further and says so."""
        self._record(hours_ahead=48)
        first = ops_telemetry._action_clear_suppression_cache("ICQG")
        second = ops_telemetry._action_clear_suppression_cache("ICQG")
        self.assertEqual(first["status"], "success")
        self.assertEqual(second["status"], "success")
        self.assertIn("Released 0", second["detail"])

    def test_it_refuses_a_non_icqg_engine(self):
        out = ops_telemetry._action_clear_suppression_cache("PGE")
        self.assertEqual(out["status"], "failure")

    def test_it_uses_the_canonical_authority(self):
        """The exact regression: the handler must reference the live module."""
        src = inspect.getsource(ops_telemetry._action_clear_suppression_cache)
        self.assertIn("apps.core.ai_quality.quality_models", src)
        self.assertNotIn("apps.core.ai_quality.models import", src)


class RecoveringIsIndependentOfActionOutcomeTests(TestCase):
    """5, 6 — a failed recovery action can never fabricate RECOVERING, and genuine
    signal improvement can still produce it independently.

    `stabilize_status` is a pure function of (previous state, raw status, incidents).
    It takes no action result, so the production Wall showing RECOVERING while the
    button showed Failed was legitimate: the raw health score had independently gone
    HEALTHY-eligible and was inside its stability window.
    """

    def test_stabilize_status_cannot_see_action_results(self):
        from apps.core.ai_observability.ops_executive import stabilize_status
        params = set(inspect.signature(stabilize_status).parameters)
        self.assertEqual(params, {"prev", "raw", "incidents"})

    def test_a_degraded_signal_never_becomes_recovering(self):
        from apps.core.ai_observability.ops_executive import stabilize_status
        status, _, _ = stabilize_status({"status": "DEGRADED", "healthy_cycles": 0},
                                        "DEGRADED", [])
        self.assertEqual(status, "DEGRADED")

    def test_genuine_improvement_produces_recovering_with_no_action_at_all(self):
        from apps.core.ai_observability.ops_executive import RECOVERING, stabilize_status
        status, state, _ = stabilize_status({"status": "DEGRADED", "healthy_cycles": 0},
                                            "HEALTHY", [])
        self.assertEqual(status, RECOVERING)
        self.assertEqual(state["healthy_cycles"], 1)

    def test_a_significant_active_incident_blocks_confirmed_recovery(self):
        from apps.core.ai_observability.ops_executive import RECOVERING, stabilize_status
        prev = {"status": RECOVERING, "healthy_cycles": 9}
        status, _, meta = stabilize_status(prev, "HEALTHY", [{"severity": "P2"}])
        self.assertEqual(status, RECOVERING)
        self.assertTrue(meta["blocked_by_incidents"])
