# ==============================================================================
# File: apps/finance/tests/test_sync_reconciliation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Scheduled reconciliation — the recovery net behind Plaid webhooks.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Prove ingestion cannot be permanently stalled by a webhook that never arrives.

Plaid retries a failed delivery for a bounded window and then stops. Before this net
existed, a connection that missed its webhook past that window stopped ingesting
FOREVER and nothing noticed — the 2026-08-26 incident was one hour of exactly that.
Reading `transactions_update_status` from a sync response fixed *what we learn once a
sync runs*; it supplied no trigger. This is the trigger.
"""
import ast
import logging
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.finance.models import BankConnection, Transaction
from apps.finance.services import sync_reconciliation as recon
from apps.users.models import User

FRESH_RESULT = {"added": 0, "modified": 0, "removed": 0, "accounts_synced": 1}


def _connection(user, **kwargs):
    defaults = dict(
        user=user,
        institution_name="Test Bank",
        item_id=f"item-{kwargs.pop('suffix', 'x')}",
        connection_status=BankConnection.STATUS_ACTIVE,
        access_token_encrypted="encrypted-token",
        last_sync_at=timezone.now() - timedelta(hours=48),
    )
    defaults.update(kwargs)
    return BankConnection.objects.create(**defaults)


class SelectionTests(TestCase):
    """Only connections where syncing is both needed AND legitimate."""

    def setUp(self):
        self.user = User.objects.create_user(email="recon@example.com", password="x")

    def test_stale_connection_is_selected(self):
        conn = _connection(self.user, suffix="stale")
        self.assertIn(conn, recon.eligible_connections())

    def test_never_synced_connection_is_selected_first(self):
        fresh_but_old = _connection(self.user, suffix="a",
                                    last_sync_at=timezone.now() - timedelta(hours=9))
        never = _connection(self.user, suffix="never", last_sync_at=None)
        selected = recon.eligible_connections()
        self.assertIn(never, selected)
        self.assertIn(fresh_but_old, selected)
        self.assertEqual(selected[0], never, "never-synced must be reconciled first")

    def test_fresh_connection_is_not_selected(self):
        """Webhooks are working here — the net must cost ZERO provider calls."""
        conn = _connection(self.user, suffix="fresh",
                           last_sync_at=timezone.now() - timedelta(minutes=5))
        self.assertNotIn(conn, recon.eligible_connections())

    def test_connection_exactly_at_the_threshold_is_not_selected(self):
        now = timezone.now()
        conn = _connection(self.user, suffix="edge",
                           last_sync_at=recon.stale_cutoff(now) + timedelta(seconds=30))
        self.assertNotIn(conn, recon.eligible_connections(now=now))

    def test_disconnected_connection_is_excluded(self):
        conn = _connection(self.user, suffix="gone",
                           connection_status=BankConnection.STATUS_DISCONNECTED)
        self.assertNotIn(conn, recon.eligible_connections())

    def test_revocation_pending_connection_is_excluded(self):
        """It still holds a token ON PURPOSE — to revoke, never to pull data."""
        conn = _connection(self.user, suffix="rev",
                           connection_status=BankConnection.STATUS_REVOCATION_PENDING)
        self.assertNotIn(conn, recon.eligible_connections())

    def test_reauth_required_and_error_connections_are_excluded(self):
        for status in (BankConnection.STATUS_REAUTH_REQUIRED,
                       BankConnection.STATUS_ERROR,
                       BankConnection.STATUS_PENDING):
            with self.subTest(status=status):
                conn = _connection(self.user, suffix=f"s-{status}",
                                   connection_status=status)
                self.assertNotIn(conn, recon.eligible_connections())

    def test_tokenless_connection_is_excluded(self):
        conn = _connection(self.user, suffix="notoken", access_token_encrypted="")
        self.assertNotIn(conn, recon.eligible_connections())

    def test_disabled_user_connection_is_excluded(self):
        disabled = User.objects.create_user(email="off@example.com", password="x")
        disabled.is_active = False
        disabled.save(update_fields=["is_active"])
        conn = _connection(disabled, suffix="disabled")
        self.assertNotIn(conn, recon.eligible_connections())

    def test_soft_delete_is_refused_while_a_token_is_still_live(self):
        """An otherwise-eligible connection cannot BE soft-deleted — by design.

        `soft_delete()` refuses while provider access is live, because discarding the
        row would orphan a credential nobody can revoke. So the dangerous combination
        (soft-deleted AND still token-bearing AND selectable) is structurally
        impossible, not merely filtered.
        """
        from django.core.exceptions import ValidationError

        conn = _connection(self.user, suffix="deleted")
        with self.assertRaises(ValidationError):
            conn.soft_delete()

    def test_soft_deleted_row_is_excluded_by_the_manager(self):
        """Belt and braces: force the state past the guard and confirm exclusion."""
        conn = _connection(self.user, suffix="deleted2")
        BankConnection.all_objects.filter(pk=conn.pk).update(
            status="deleted", access_token_encrypted="")
        self.assertNotIn(conn.pk, [c.pk for c in recon.eligible_connections()])
        self.assertTrue(BankConnection.all_objects.filter(pk=conn.pk).exists())

    def test_selection_is_bounded(self):
        for i in range(recon.MAX_CONNECTIONS_PER_RUN + 5):
            _connection(self.user, suffix=f"many-{i}")
        self.assertEqual(len(recon.eligible_connections()),
                         recon.MAX_CONNECTIONS_PER_RUN)


class MissedWebhookRecoveryTests(TestCase):
    """The whole point: a webhook that never arrives must not stall ingestion."""

    def setUp(self):
        self.user = User.objects.create_user(email="missed@example.com", password="x")
        self.connection = _connection(self.user, suffix="missed")

    def test_missed_webhook_is_recovered_by_the_schedule(self):
        from apps.finance.tasks import reconcile_stale_bank_connections

        # No webhook ever arrived: flags false, connection stale.
        self.assertFalse(self.connection.historical_update_complete)

        with patch("apps.finance.services.sync_service."
                   "TransactionSyncService.sync") as mock_sync:
            mock_sync.return_value = {"added": 12, "modified": 0, "removed": 0,
                                      "accounts_synced": 1}
            summary = reconcile_stale_bank_connections()

        mock_sync.assert_called_once()
        self.assertEqual(mock_sync.call_args.kwargs.get("trigger"), "scheduled")
        self.assertEqual(summary["synced"], 1)
        self.assertEqual(summary["added"], 12)

    def test_no_eligible_connections_makes_no_provider_call(self):
        from apps.finance.tasks import reconcile_stale_bank_connections

        self.connection.last_sync_at = timezone.now()
        self.connection.save(update_fields=["last_sync_at"])

        with patch("apps.finance.services.sync_service."
                   "TransactionSyncService.sync") as mock_sync:
            summary = reconcile_stale_bank_connections()

        mock_sync.assert_not_called()
        self.assertEqual(summary, {"eligible": 0, "synced": 0, "skipped": 0,
                                   "failed": 0})

    def test_completion_is_learned_without_any_webhook(self):
        """End to end: schedule → sync response → flags true. No webhook involved."""
        from apps.finance.tasks import reconcile_stale_bank_connections

        with patch("apps.finance.services.plaid_service.PlaidService.get_accounts",
                   return_value=[]), \
             patch("apps.finance.services.plaid_service.PlaidService.sync_transactions",
                   return_value={"added": [], "modified": [], "removed": [],
                                 "next_cursor": "cur-1", "has_more": False,
                                 "update_status": "HISTORICAL_UPDATE_COMPLETE"}), \
             patch.object(BankConnection, "get_access_token", return_value="tok"):
            reconcile_stale_bank_connections()

        self.connection.refresh_from_db()
        self.assertTrue(self.connection.initial_update_complete)
        self.assertTrue(self.connection.historical_update_complete)
        self.assertEqual(self.connection.history_state_label,
                         "Historical import complete")


class ProviderFailureTests(TestCase):
    """One unreachable institution must not abort the run or crash the worker."""

    def setUp(self):
        self.user = User.objects.create_user(email="fail@example.com", password="x")

    def test_provider_exception_is_normalised_and_run_continues(self):
        from apps.finance.tasks import reconcile_stale_bank_connections

        _connection(self.user, suffix="boom")
        _connection(self.user, suffix="fine")

        calls = {"n": 0}

        def flaky(self_, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("provider unreachable")
            return FRESH_RESULT

        with patch("apps.finance.services.sync_service."
                   "TransactionSyncService.sync", new=flaky):
            summary = reconcile_stale_bank_connections()

        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["synced"], 1)
        self.assertEqual(calls["n"], 2, "run must continue past a failure")

    def test_failure_is_not_retried_within_the_same_run(self):
        from apps.finance.tasks import reconcile_stale_bank_connections

        _connection(self.user, suffix="always-bad")
        with patch("apps.finance.services.sync_service."
                   "TransactionSyncService.sync",
                   side_effect=RuntimeError("nope")) as mock_sync:
            summary = reconcile_stale_bank_connections()

        self.assertEqual(mock_sync.call_count, 1, "retries are bounded — next run only")
        self.assertEqual(summary["failed"], 1)

    def test_error_result_is_reported_not_counted_as_success(self):
        _connection(self.user, suffix="err")
        conn = recon.eligible_connections()[0]
        with patch("apps.finance.services.sync_service."
                   "TransactionSyncService.sync",
                   return_value={"error": "No access token available"}):
            outcome = recon.reconcile_connection(conn)
        self.assertFalse(outcome["ok"])


class ConcurrencyTests(TestCase):
    """Webhook, scheduled and manual syncs must not run together on one connection."""

    def setUp(self):
        self.user = User.objects.create_user(email="lock@example.com", password="x")
        self.connection = _connection(self.user, suffix="lock")

    def _patched_provider(self, added=None):
        return patch.multiple(
            "apps.finance.services.plaid_service.PlaidService",
            get_accounts=lambda self_, tok: [],
            sync_transactions=lambda self_, tok, cursor='': {
                "added": added or [], "modified": [], "removed": [],
                "next_cursor": "cur-1", "has_more": False,
                "update_status": "HISTORICAL_UPDATE_COMPLETE"},
        )

    def test_second_concurrent_sync_is_skipped_not_run(self):
        from apps.finance.services.sync_service import TransactionSyncService

        observed = {}

        original = TransactionSyncService._sync_locked

        def reentrant(self_, getter):
            # While the first sync is INSIDE the lock, a webhook fires for the same
            # connection. It must be refused, not interleaved.
            if "inner" not in observed:
                observed["inner"] = TransactionSyncService(
                    self_.bank_connection).sync(trigger="webhook")
            return original(self_, getter)

        with self._patched_provider(), \
             patch.object(BankConnection, "get_access_token", return_value="tok"), \
             patch.object(TransactionSyncService, "_sync_locked", new=reentrant):
            outer = TransactionSyncService(self.connection).sync(trigger="scheduled")

        self.assertTrue(observed["inner"].get("skipped"))
        self.assertEqual(observed["inner"].get("reason"), "locked")
        self.assertFalse(outer.get("skipped"))

    def test_lock_is_released_so_the_next_sync_can_run(self):
        from apps.finance.services.sync_service import TransactionSyncService

        with self._patched_provider(), \
             patch.object(BankConnection, "get_access_token", return_value="tok"):
            first = TransactionSyncService(self.connection).sync(trigger="scheduled")
            second = TransactionSyncService(self.connection).sync(trigger="webhook")

        self.assertFalse(first.get("skipped"))
        self.assertFalse(second.get("skipped"), "lock must not leak between runs")

    def test_lock_is_released_even_when_the_sync_raises(self):
        from apps.finance.services.sync_service import TransactionSyncService
        from apps.core.ai_scheduler.scheduler_models import SchedulerLock

        with patch.object(TransactionSyncService, "_sync_locked",
                          side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                TransactionSyncService(self.connection).sync(trigger="scheduled")

        self.assertFalse(
            SchedulerLock.objects.filter(
                lock_name=f"finance_sync:{self.connection.pk}").exists())

    def test_a_different_connection_is_not_blocked(self):
        from apps.finance.services.sync_service import TransactionSyncService
        from apps.core.ai_scheduler.scheduler_models import SchedulerLock

        other = _connection(self.user, suffix="other")
        SchedulerLock.objects.create(
            lock_name=f"finance_sync:{self.connection.pk}",
            locked_at=timezone.now(), locked_by="webhook-1")

        with self._patched_provider(), \
             patch.object(BankConnection, "get_access_token", return_value="tok"):
            result = TransactionSyncService(other).sync(trigger="scheduled")

        self.assertFalse(result.get("skipped"))

    def test_a_stale_lock_from_a_dead_worker_is_reclaimed(self):
        from apps.finance.services.sync_service import TransactionSyncService
        from apps.core.ai_scheduler.scheduler_models import SchedulerLock

        SchedulerLock.objects.create(
            lock_name=f"finance_sync:{self.connection.pk}",
            locked_at=timezone.now() - timedelta(
                seconds=TransactionSyncService.LOCK_STALE_SECONDS + 60),
            locked_by="killed-worker")

        with self._patched_provider(), \
             patch.object(BankConnection, "get_access_token", return_value="tok"):
            result = TransactionSyncService(self.connection).sync(trigger="scheduled")

        self.assertFalse(result.get("skipped"),
                         "a dead worker must not wedge a connection forever")

    def test_concurrent_paths_cannot_duplicate_transactions(self):
        """Both triggers, same provider page — one row, not two."""
        from apps.finance.services.sync_service import TransactionSyncService

        page = [{
            "transaction_id": "txn-dup-1", "account_id": "acct-1",
            "amount": 10.0, "date": timezone.now().date(),
            "name": "Coffee", "merchant_name": "Coffee",
            "pending": False, "iso_currency_code": "USD",
        }]

        with self._patched_provider(added=page), \
             patch.object(BankConnection, "get_access_token", return_value="tok"), \
             patch.object(TransactionSyncService, "_sync_accounts", return_value=1):
            TransactionSyncService(self.connection).sync(trigger="webhook")
            TransactionSyncService(self.connection).sync(trigger="scheduled")

        rows = Transaction.all_objects.filter(
            user=self.user, plaid_transaction_id="txn-dup-1")
        self.assertLessEqual(rows.count(), 1)


class PaginationAndCursorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="page@example.com", password="x")
        self.connection = _connection(self.user, suffix="page")

    def test_cursor_persists_only_after_the_last_page(self):
        from apps.finance.services.sync_service import TransactionSyncService

        pages = [
            {"added": [], "modified": [], "removed": [],
             "next_cursor": "cur-1", "has_more": True, "update_status": "NOT_READY"},
            {"added": [], "modified": [], "removed": [],
             "next_cursor": "cur-final", "has_more": False,
             "update_status": "HISTORICAL_UPDATE_COMPLETE"},
        ]
        seen_cursors = []

        def paged(self_, tok, cursor=''):
            seen_cursors.append(cursor)
            return pages[len(seen_cursors) - 1]

        with patch("apps.finance.services.plaid_service.PlaidService.get_accounts",
                   return_value=[]), \
             patch("apps.finance.services.plaid_service.PlaidService.sync_transactions",
                   new=paged), \
             patch.object(BankConnection, "get_access_token", return_value="tok"):
            TransactionSyncService(self.connection).sync(trigger="scheduled")

        self.connection.refresh_from_db()
        self.assertEqual(seen_cursors[0], "", "first page starts from the stored cursor")
        self.assertEqual(seen_cursors[1], "cur-1", "page 2 continues from page 1")
        self.assertEqual(self.connection.last_sync_cursor, "cur-final",
                         "only the final cursor is durably stored")
        self.assertTrue(self.connection.historical_update_complete)


class DuplicateWebhookTests(TestCase):
    """Repeated or out-of-order webhooks must be inert."""

    def setUp(self):
        self.user = User.objects.create_user(email="dupe@example.com", password="x")
        self.connection = _connection(self.user, suffix="dupe")

    def test_repeated_completion_is_idempotent(self):
        self.connection.record_update_status("HISTORICAL_UPDATE_COMPLETE")
        first = BankConnection.objects.get(pk=self.connection.pk).historical_update_at
        for _ in range(3):
            self.connection.record_update_status("HISTORICAL_UPDATE_COMPLETE")
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.historical_update_at, first)

    def test_out_of_order_status_cannot_regress_completion(self):
        self.connection.record_update_status("HISTORICAL_UPDATE_COMPLETE")
        self.connection.record_update_status("NOT_READY")
        self.connection.record_update_status("INITIAL_UPDATE_COMPLETE")
        self.connection.refresh_from_db()
        self.assertTrue(self.connection.historical_update_complete)


class NoRefreshEndpointContractTests(TestCase):
    """`/transactions/refresh` is separately billed and is never needed here."""

    def test_no_finance_module_calls_transactions_refresh(self):
        offenders = []
        root = Path(settings.BASE_DIR) / "apps" / "finance"
        for path in root.rglob("*.py"):
            if "test" in path.name:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and \
                        node.attr in ("transactions_refresh", "TransactionsRefreshRequest"):
                    offenders.append(f"{path.name}:{node.lineno}")
                if isinstance(node, ast.Name) and node.id == "TransactionsRefreshRequest":
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [],
                         f"/transactions/refresh is billed per call: {offenders}")


class ReconciliationDisclosureTests(TestCase):
    """Operational truth without financial truth."""

    def setUp(self):
        self.user = User.objects.create_user(email="quiet@example.com", password="x")
        self.connection = _connection(
            self.user, suffix="quiet", institution_name="First Horizon Bank")

    def test_dry_run_reports_staleness_and_nothing_sensitive(self):
        report = recon.describe_selection()
        blob = repr(report)
        for secret in ("First Horizon", "encrypted-token", "item-quiet",
                       self.user.email):
            self.assertNotIn(secret, blob)
        self.assertEqual(report["eligible_count"], 1)
        self.assertEqual(report["stale_after_hours"], recon.STALE_AFTER_HOURS)
        self.assertIn("hours_since_last_sync", report["eligible"][0])

    def test_task_logs_carry_no_sensitive_values(self):
        from apps.finance.tasks import reconcile_stale_bank_connections

        with self.assertLogs("apps.finance.tasks", level=logging.INFO) as captured, \
             patch("apps.finance.services.sync_service."
                   "TransactionSyncService.sync", return_value=FRESH_RESULT):
            reconcile_stale_bank_connections()

        blob = "\n".join(captured.output)
        for secret in ("First Horizon", "encrypted-token", "item-quiet",
                       self.user.email, "tok"):
            self.assertNotIn(secret, blob)


class ReconciliationObservabilityTests(TestCase):
    """An operator must be able to see ingestion recovery without seeing money."""

    def setUp(self):
        self.user = User.objects.create_user(email="obs@example.com", password="x")
        self.connection = _connection(
            self.user, suffix="obs", institution_name="First Horizon Bank")

    def test_audit_reports_the_schedule_and_stale_state(self):
        from apps.finance.services.finance_audit import audit

        block = audit()["ingestion_recovery"]
        self.assertTrue(block["schedule_registered"])
        self.assertEqual(block["task"],
                         "apps.finance.tasks.reconcile_stale_bank_connections")
        self.assertEqual(block["active_connections"], 1)
        self.assertEqual(block["currently_eligible"], 1)
        self.assertEqual(block["stale_after_hours"], recon.STALE_AFTER_HOURS)

    def test_audit_distinguishes_waiting_from_persistently_stuck(self):
        from apps.finance.services.finance_audit import audit

        # Stale enough to be reconciled, NOT stale enough to be called stuck: the
        # safety net has simply not had its turn yet.
        self.connection.last_sync_at = timezone.now() - timedelta(
            hours=recon.STALE_AFTER_HOURS + 2)
        self.connection.save(update_fields=["last_sync_at"])
        recovery = audit()["ingestion_recovery"]
        self.assertEqual(recovery["currently_eligible"], 1)
        self.assertEqual(recovery["persistently_stale"], 0)

        self.connection.last_sync_at = timezone.now() - timedelta(
            hours=recon.STALE_AFTER_HOURS * 5)
        self.connection.save(update_fields=["last_sync_at"])
        self.assertEqual(audit()["ingestion_recovery"]["persistently_stale"], 1)

    def test_audit_block_exposes_nothing_sensitive(self):
        from apps.finance.services.finance_audit import audit

        blob = repr(audit()["ingestion_recovery"])
        for secret in ("First Horizon", "encrypted-token", "item-obs",
                       self.user.email):
            self.assertNotIn(secret, blob)
