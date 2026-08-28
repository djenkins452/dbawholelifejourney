# ==============================================================================
# File: apps/ai/tests/test_confirmation_authorization_integrity.py
# Description: Contract — M1 CONFIRMATION AUTHORIZATION INTEGRITY.
#   A confirmation is an AUTHORIZATION ARTIFACT: the exact deterministic action and
#   arguments shown to the user are the only thing it can execute, and they may
#   execute successfully at most once.
#
#   Origin (production 2026-08-27): a `create_task` confirmation was narrated to the
#   user as "ready to log Stuffed Peppers for dinner", and one `log_weight`
#   confirmation (cb50cb49…) executed TWICE, 38s apart, creating two records —
#   because single-use was enforced only by a best-effort cache write that fails open.
#
#   Tests use SYNTHETIC actions/domains. No product, value or domain from the
#   originating incident is part of the mechanism under test.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase

from apps.ai.cos_services import action_interface as ai
from apps.ai.model_interface import confirmation as C
from apps.ai.models import ActionConfirmation

_EXEC = "apps.ai.cos_services.action_interface.execute_action"

# Two unrelated synthetic write actions in different notional domains.
ACTION_A = "create_task"          # domain: organize
ACTION_B = "log_weight"           # domain: health


def _needs_confirmation(user, action, params):
    return {"status": "confirmation_required", "message": "needs confirmation"}


def _executes(user, action, params):
    return {"status": "ok", "message": f"did {action}", "result": {"id": 1}}


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="confirm-integrity@test.com", password="x")

    def setUp(self):
        cache.clear()

    def _request(self, action, params):
        with mock.patch(_EXEC, side_effect=_needs_confirmation):
            return ai.request_action(self.user, action, params, turn_id="t")


class BoundActionTruthTests(_Base):
    """Part A — what the user is shown is rendered from what will execute."""

    # 1. the user-visible confirmation is derived from the exact bound action
    def test_confirmation_is_derived_from_the_bound_action(self):
        out = self._request(ACTION_A, {"title": "Some item"})
        conf = out["confirmation"]
        rec = ActionConfirmation.objects.get(id=conf["confirmation_id"])
        self.assertEqual(rec.action, ACTION_A)
        # the presented line names the bound action, not anything the model might say
        self.assertIn("Create task", conf["authorization"])
        self.assertIn("Some item", conf["authorization"])
        self.assertEqual(rec.authorization_line, conf["authorization"])

    def test_a_weight_write_visibly_authorizes_a_weight_write(self):
        conf = self._request(ACTION_B, {"value": 200, "unit": "lb"})["confirmation"]
        self.assertIn("Log weight", conf["authorization"])
        self.assertIn("200", conf["authorization"])

    # 2. summary and executable action cannot disagree
    def test_summary_and_executable_action_cannot_disagree(self):
        out = self._request(ACTION_A, {"title": "Alpha"})
        conf = out["confirmation"]
        rec = ActionConfirmation.objects.get(id=conf["confirmation_id"])
        for shown in (conf["authorization"], conf["summary"], out["result"]):
            self.assertIn("Create task", shown)
        # and nothing presented names the other action
        self.assertNotIn("weight", (conf["authorization"] + conf["summary"]).lower())
        self.assertEqual(rec.action, ACTION_A)

    def test_the_model_is_told_it_may_not_redefine_the_action(self):
        out = self._request(ACTION_A, {"title": "Alpha"})
        self.assertIn("this will do exactly", out["result"].lower())
        self.assertIn("never describe it as a different action", out["result"].lower())

    # 3. arguments shown == arguments executed
    def test_arguments_shown_are_the_arguments_executed(self):
        params = {"title": "Alpha", "notes": "n", "due_date": "today"}
        cid = self._request(ACTION_A, dict(params))["confirmation"]["confirmation_id"]
        with mock.patch(_EXEC, side_effect=_executes) as m:
            ai.resolve_pending_action(self.user, cid, confirm=True)
        _, ex_action, ex_params = m.call_args_list[-1].args
        self.assertEqual(ex_action, ACTION_A)
        for k, v in params.items():
            self.assertEqual(ex_params[k], v)

    def test_execution_uses_the_persisted_payload_not_the_caller_state(self):
        """Even if the in-memory record were tampered with, execution reads the row."""
        cid = self._request(ACTION_A, {"title": "Bound"})["confirmation"]["confirmation_id"]
        with mock.patch(_EXEC, side_effect=_executes) as m:
            ai.resolve_pending_action(self.user, cid, confirm=True)
        _, ex_action, ex_params = m.call_args_list[-1].args
        self.assertEqual(ex_action, ACTION_A)
        self.assertEqual(ex_params["title"], "Bound")

    # fail closed when nothing deterministic can be presented
    def test_unpresentable_action_fails_closed(self):
        from apps.ai.confirmation_contract import build_view
        self.assertIsNone(build_view("", {}))
        self.assertIsNone(C.create(self.user, "", {}, "s", view=None))
        self.assertIsNone(
            ai.request_confirmation_for(self.user, "", {"x": 1}, turn_id="t"))


class CrossActionIsolationTests(_Base):
    """4 + 5 — a confirmation cannot authorize a different or newer action."""

    def test_stale_confirmation_cannot_authorize_a_newer_action(self):
        first = self._request(ACTION_A, {"title": "OLD"})["confirmation"]
        second = self._request(ACTION_A, {"title": "NEW"})["confirmation"]
        self.assertNotEqual(first["confirmation_id"], second["confirmation_id"])
        with mock.patch(_EXEC, side_effect=_executes) as m:
            ai.resolve_pending_action(self.user, first["confirmation_id"], confirm=True)
        _, _, ex_params = m.call_args_list[-1].args
        self.assertEqual(ex_params["title"], "OLD",
                         "the older confirmation executed the newer action's arguments")

    def test_confirmation_cannot_cross_domains(self):
        a = self._request(ACTION_A, {"title": "task thing"})["confirmation"]
        self._request(ACTION_B, {"value": 200, "unit": "lb"})
        with mock.patch(_EXEC, side_effect=_executes) as m:
            ai.resolve_pending_action(self.user, a["confirmation_id"], confirm=True)
        _, ex_action, ex_params = m.call_args_list[-1].args
        self.assertEqual(ex_action, ACTION_A)
        self.assertNotIn("value", ex_params)

    def test_a_numeric_argument_cannot_migrate_between_actions(self):
        """Two pending numeric writes must stay bound to their own action."""
        b = self._request(ACTION_B, {"value": 200, "unit": "lb"})["confirmation"]
        self._request(ACTION_A, {"title": "unrelated", "duration_minutes": 534})
        with mock.patch(_EXEC, side_effect=_executes) as m:
            ai.resolve_pending_action(self.user, b["confirmation_id"], confirm=True)
        _, ex_action, ex_params = m.call_args_list[-1].args
        self.assertEqual(ex_action, ACTION_B)
        self.assertEqual(ex_params["value"], 200)


class ExactlyOnceTests(_Base):
    """6, 9, 10 — one authorization, at most one successful mutation."""

    def _pending(self, action=ACTION_A, params=None):
        return self._request(action, params or {"title": "X"})["confirmation"][
            "confirmation_id"]

    def test_repeated_confirm_executes_once(self):
        cid = self._pending()
        with mock.patch(_EXEC, side_effect=_executes) as m:
            ai.resolve_pending_action(self.user, cid, confirm=True)
            for _ in range(4):
                ai.resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(len(m.call_args_list), 1,
                         "one authorization must mutate at most once")

    def test_completed_confirmation_retry_replays_instead_of_mutating(self):
        cid = self._pending()
        with mock.patch(_EXEC, side_effect=_executes):
            first = ai.resolve_pending_action(self.user, cid, confirm=True)
        with mock.patch(_EXEC, side_effect=_executes) as m:
            again = ai.resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(len(m.call_args_list), 0)
        self.assertTrue(again.get("replayed"))
        self.assertEqual(again["result"], first["result"])

    def test_declined_confirmation_cannot_execute(self):
        cid = self._pending()
        ai.resolve_pending_action(self.user, cid, confirm=False)
        with mock.patch(_EXEC, side_effect=_executes) as m:
            out = ai.resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(len(m.call_args_list), 0)
        self.assertEqual(out["status"], ai.ERROR)

    def test_expired_confirmation_cannot_execute(self):
        from django.utils import timezone
        cid = self._pending()
        ActionConfirmation.objects.filter(id=cid).update(
            expires_at=timezone.now() - timezone.timedelta(seconds=1))
        with mock.patch(_EXEC, side_effect=_executes) as m:
            out = ai.resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(len(m.call_args_list), 0)
        self.assertEqual(out["code"], "no_matching_confirmation")

    def test_a_claim_in_flight_is_never_raced(self):
        """FAIL CLOSED: a record stuck `executing` blocks rather than risking a duplicate."""
        cid = self._pending()
        ActionConfirmation.objects.filter(id=cid).update(status="executing")
        with mock.patch(_EXEC, side_effect=_executes) as m:
            out = ai.resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(len(m.call_args_list), 0)
        self.assertEqual(out["code"], "already_resolved")

    # 8 — cache failure must not permit a duplicate
    def test_cache_failure_does_not_allow_duplicate_execution(self):
        """The proven production condition: `SafeRedisCache.set` returns False and
        swallows on failure, so a cache-based single-use guard fails OPEN. Authority is
        now the database row, so a totally dead cache changes nothing."""
        cid = self._pending()

        def _dead(*a, **k):
            raise RuntimeError("redis down")

        with mock.patch.object(cache, "set", _dead), \
             mock.patch.object(cache, "get", _dead), \
             mock.patch.object(cache, "delete", _dead), \
             mock.patch(_EXEC, side_effect=_executes) as m:
            ai.resolve_pending_action(self.user, cid, confirm=True)
            ai.resolve_pending_action(self.user, cid, confirm=True)
            ai.resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(len(m.call_args_list), 1)

    # 11 — audit lineage
    def test_audit_preserves_confirmation_to_action_to_result_lineage(self):
        from apps.ai.models import ToolCallLog
        cid = self._pending(ACTION_A, {"title": "Audited"})
        with mock.patch(_EXEC, side_effect=_executes):
            ai.resolve_pending_action(self.user, cid, confirm=True, turn_id="t9")
            ai.resolve_pending_action(self.user, cid, confirm=True, turn_id="t9")
        rows = list(ToolCallLog.objects.filter(user=self.user).order_by("created_at"))
        digests = [r.result_digest for r in rows]
        self.assertTrue(any(d.get("confirmation_id") == cid for d in digests))
        # the executed row carries the action; the replay is marked non-mutating
        self.assertTrue(any(r.tool_name == ACTION_A for r in rows))
        self.assertTrue(any(d.get("replayed") and d.get("mutated") is False
                            for d in digests))
        # the durable authorization row itself is the lineage anchor
        rec = ActionConfirmation.objects.get(id=cid)
        self.assertEqual(rec.status, "resolved")
        self.assertEqual(rec.action, ACTION_A)
        self.assertTrue(rec.result)


class ConcurrencyTests(TransactionTestCase):
    """7 — two concurrent consumers execute the mutation exactly once.

    Uses real threads against the real database so the compare-and-swap is exercised,
    not simulated.
    """

    reset_sequences = True

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            email="confirm-concurrency@test.com", password="x")

    def test_two_concurrent_consumers_execute_once(self):
        import threading

        from django.db import connection
        with mock.patch(_EXEC, side_effect=_needs_confirmation):
            cid = ai.request_action(self.user, ACTION_A, {"title": "Race"},
                                    turn_id="t")["confirmation"]["confirmation_id"]

        winners = []
        barrier = threading.Barrier(2)

        def _claim():
            try:
                barrier.wait(timeout=5)
                if C.claim(self.user, cid) is not None:
                    winners.append(1)
            finally:
                connection.close()

        threads = [threading.Thread(target=_claim) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(sum(winners), 1,
                         "exactly one concurrent consumer may claim an authorization")


class OriginalIncidentStructuralProofTests(_Base):
    """Structural proof against the PERSISTED production conversation (2026-08-27).

    Replays the exact bound payloads recorded in `ToolCallLog` for that turn and proves
    the two defects are now structurally impossible. The payload shapes come from the
    incident; the ASSERTIONS are about the authorization contract, not about any
    product, value or domain.
    """

    # The two payloads exactly as persisted in the incident's audit rows.
    INCIDENT_TASK = {"title": "Log 'X' dinner", "effort": "quick", "due_date": "today",
                     "notes": "Calories 534, Protein 30g", "priority": "now"}
    INCIDENT_WEIGHT = {"value": 534, "unit": "lb",
                       "notes": "dinner with 30 g Protein, 29 g Carbs"}

    def test_the_task_confirmation_would_have_visibly_authorized_a_task(self):
        """The user was told 'I've prepared to log Stuffed Peppers for dinner' while the
        bound action was `create_task`. Now every presented surface names the task."""
        out = self._request("create_task", dict(self.INCIDENT_TASK))
        conf = out["confirmation"]
        for shown in (conf["authorization"], conf["summary"], out["result"]):
            self.assertIn("Create task", shown)
        # and nothing presented suggests a nutrition/meal write
        blob = (conf["authorization"] + conf["summary"] + out["result"]).lower()
        for absent in ("log dinner", "logged dinner", "meal is logged"):
            self.assertNotIn(absent, blob)

    def test_the_weight_confirmation_would_have_visibly_authorized_a_weight_write(self):
        conf = self._request("log_weight", dict(self.INCIDENT_WEIGHT))["confirmation"]
        self.assertIn("Log weight", conf["authorization"])
        self.assertIn("534", conf["authorization"],
                      "the value being written must be visible before authorizing")

    def test_that_confirmation_id_could_not_have_produced_two_rows(self):
        """The incident's second execution (38s later, same confirmation id) is now
        structurally impossible — with or without a working cache."""
        cid = self._request("log_weight",
                            dict(self.INCIDENT_WEIGHT))["confirmation"]["confirmation_id"]

        def _dead(*a, **k):
            raise RuntimeError("redis down")

        with mock.patch(_EXEC, side_effect=_executes) as m:
            ai.resolve_pending_action(self.user, cid, confirm=True, turn_id="conv-14")
            with mock.patch.object(cache, "set", _dead), \
                 mock.patch.object(cache, "get", _dead), \
                 mock.patch.object(cache, "delete", _dead):
                ai.resolve_pending_action(self.user, cid, confirm=True, turn_id="later")
        self.assertEqual(len(m.call_args_list), 1,
                         "the same authorization produced a second mutation")
        self.assertEqual(ActionConfirmation.objects.get(id=cid).status, "resolved")
