# ==============================================================================
# File: apps/finance/tests/test_duplicate_transaction_prevention.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The 2026-08-27 duplicate-transaction incident, reproduced and closed.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Connecting a second institution produced 1,677 duplicate transactions.

Plaid delivers `SYNC_UPDATES_AVAILABLE` and the legacy `HISTORICAL_UPDATE` to this
sync integration about 20ms apart. Both codes triggered an inline sync, so every
provider notification launched TWO concurrent full syncs. Ingestion decided whether a
transaction already existed with a `.filter().first()` read followed by a separate
`.create()` — never one atomic step — and nothing at the database level forbade the
result. Both syncs read "not present" and both inserted.

Three independent defences are asserted here, because any one of them alone leaves the
class reachable:

1. the double trigger is gone (legacy codes record milestones, never fetch);
2. concurrent syncs of one connection serialise on a per-connection lock;
3. the database itself refuses a second active row — the only defence that holds if
   the other two are ever bypassed by a path nobody anticipated.
"""
from datetime import date, timedelta

from django.db import IntegrityError, transaction as db_transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.finance.models import (BankConnection, FinancialAccount, Transaction)
from apps.users.models import User


def _txn_payload(txn_id, account_id="acct-provider-1", **over):
    payload = {
        "transaction_id": txn_id,
        "account_id": account_id,
        "amount": 12.34,
        "date": date(2026, 8, 20),
        "name": "Coffee Shop",
        "merchant_name": "Coffee Shop",
        "pending": False,
        "iso_currency_code": "USD",
    }
    payload.update(over)
    return payload


class WebhookTriggerNarrowingTests(TestCase):
    """Defence 1 — the provider's own pairing must not double the work."""

    def test_legacy_codes_do_not_trigger_a_fetch(self):
        from apps.finance.views import SYNC_TRIGGERING_WEBHOOK_CODES

        for legacy in ("INITIAL_UPDATE", "HISTORICAL_UPDATE"):
            self.assertNotIn(
                legacy, SYNC_TRIGGERING_WEBHOOK_CODES,
                "Plaid sends the legacy pair ALONGSIDE SYNC_UPDATES_AVAILABLE ~20ms "
                "apart; triggering on both launches two concurrent syncs.")

    def test_sync_integration_codes_still_trigger(self):
        from apps.finance.views import SYNC_TRIGGERING_WEBHOOK_CODES

        for code in ("SYNC_UPDATES_AVAILABLE", "DEFAULT_UPDATE", "TRANSACTIONS_REMOVED"):
            self.assertIn(code, SYNC_TRIGGERING_WEBHOOK_CODES)

    def test_legacy_codes_still_record_completion(self):
        """Narrowing the FETCH trigger must not lose the milestone they carry."""
        user = User.objects.create_user(email="legacy@example.com", password="x")
        conn = BankConnection.objects.create(
            user=user, institution_name="B", item_id="item-legacy",
            connection_status=BankConnection.STATUS_ACTIVE)
        conn.record_update_status("HISTORICAL_UPDATE_COMPLETE")
        conn.refresh_from_db()
        self.assertTrue(conn.historical_update_complete)


class DatabaseUniquenessTests(TestCase):
    """Defence 3 — the constraint, and the scope it is deliberately drawn at."""

    def setUp(self):
        self.user = User.objects.create_user(email="uniq@example.com", password="x")
        self.conn = BankConnection.objects.create(
            user=self.user, institution_name="Bank A", item_id="item-a",
            connection_status=BankConnection.STATUS_ACTIVE)
        self.account = FinancialAccount.objects.create(
            user=self.user, name="Checking", bank_connection=self.conn,
            plaid_account_id="acct-provider-1")

    def _txn(self, txn_id, account=None, **over):
        return Transaction.objects.create(
            user=self.user, account=account or self.account,
            date=date(2026, 8, 20), amount=-10, description="x",
            plaid_transaction_id=txn_id, **over)

    def test_a_second_active_row_is_refused(self):
        self._txn("txn-1")
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                self._txn("txn-1")

    def test_a_soft_deleted_row_does_not_block_a_new_active_one(self):
        """The constraint is partial so WLJ's soft-delete model still works."""
        first = self._txn("txn-2")
        first.status = "deleted"
        first.deleted_at = timezone.now()
        first.save(update_fields=["status", "deleted_at"])

        second = self._txn("txn-2")          # must not raise
        self.assertEqual(Transaction.all_objects.filter(
            plaid_transaction_id="txn-2").count(), 2)
        self.assertEqual(Transaction.objects.filter(
            plaid_transaction_id="txn-2").count(), 1)
        self.assertEqual(second.status, "active")

    def test_manual_transactions_without_a_provider_id_are_unconstrained(self):
        """Hand-entered and imported rows legitimately share a blank provider id."""
        for _ in range(3):
            self._txn("")
        self.assertEqual(
            Transaction.objects.filter(plaid_transaction_id="").count(), 3)

    def test_the_same_provider_id_is_allowed_on_a_DIFFERENT_account(self):
        """Scope is the account, because Plaid does not promise cross-Item uniqueness.

        Plaid documents `transaction_id` only as "the unique ID of the transaction" —
        it does NOT state the id is unique across unrelated Items. A user-scoped
        constraint would therefore reject a genuine transaction from a second
        institution that happened to reuse an id, silently losing real money data.
        """
        other_conn = BankConnection.objects.create(
            user=self.user, institution_name="Bank B", item_id="item-b",
            connection_status=BankConnection.STATUS_ACTIVE)
        other_account = FinancialAccount.objects.create(
            user=self.user, name="Other", bank_connection=other_conn,
            plaid_account_id="acct-provider-2")

        self._txn("collision")
        self._txn("collision", account=other_account)     # must not raise

        self.assertEqual(Transaction.objects.filter(
            plaid_transaction_id="collision").count(), 2)


class ActiveRowPredicateInvariantTests(TestCase):
    """The constraint predicate must be the SAME predicate the manager uses.

    WLJ has THREE lifecycle states, not two: active / archived / deleted.

      * `SoftDeleteManager.get_queryset()` filters `status="active"` — it never reads
        `deleted_at`. `status` is therefore the authoritative visibility predicate.
      * `deleted_at` is purge metadata for the 30-day grace window, nothing more.
      * `archive()` sets `status="archived"` and `deleted_at=None`.

    So an **archived row has `deleted_at IS NULL` but is NOT active.** A constraint
    written as `deleted_at IS NULL` would be STRICTER than the manager: it would make
    archived rows contend for uniqueness and block a provider from re-delivering a
    transaction the user had archived. `status='active'` matches the manager exactly.
    """

    def setUp(self):
        self.user = User.objects.create_user(email="pred@example.com", password="x")
        self.conn = BankConnection.objects.create(
            user=self.user, institution_name="Bank", item_id="item-pred",
            connection_status=BankConnection.STATUS_ACTIVE)
        self.account = FinancialAccount.objects.create(
            user=self.user, name="Checking", bank_connection=self.conn,
            plaid_account_id="acct-provider-1")

    def _txn(self, txn_id="txn-pred"):
        return Transaction.objects.create(
            user=self.user, account=self.account, date=date(2026, 8, 20),
            amount=-10, description="x", plaid_transaction_id=txn_id)

    def test_the_manager_keys_visibility_on_status_not_deleted_at(self):
        t = self._txn()
        t.status = "deleted"
        t.deleted_at = None                      # deliberately inconsistent metadata
        t.save(update_fields=["status", "deleted_at"])

        self.assertEqual(Transaction.objects.filter(pk=t.pk).count(), 0,
                         "status alone decides visibility")
        self.assertEqual(Transaction.all_objects.filter(pk=t.pk).count(), 1)

    def test_an_archived_row_has_no_deleted_at_yet_is_not_active(self):
        t = self._txn()
        t.archive()
        t.refresh_from_db()
        self.assertEqual(t.status, "archived")
        self.assertIsNone(t.deleted_at,
                          "archive() clears deleted_at — a deleted_at IS NULL "
                          "predicate would wrongly treat this row as contending")
        self.assertEqual(Transaction.objects.filter(pk=t.pk).count(), 0)

    def test_archived_row_does_not_block_provider_re_ingestion(self):
        """The case a `deleted_at IS NULL` constraint would have broken."""
        first = self._txn()
        first.archive()

        second = self._txn()                      # must not raise
        self.assertEqual(second.status, "active")
        self.assertEqual(Transaction.objects.filter(
            plaid_transaction_id="txn-pred").count(), 1)
        self.assertEqual(Transaction.all_objects.filter(
            plaid_transaction_id="txn-pred").count(), 2)

    def test_soft_deleted_row_does_not_block_provider_re_ingestion(self):
        """A user deleting a transaction must not stop Plaid re-delivering it."""
        first = self._txn()
        first.soft_delete()

        second = self._txn()                      # must not raise
        self.assertEqual(second.status, "active")
        self.assertEqual(Transaction.objects.filter(
            plaid_transaction_id="txn-pred").count(), 1)

    def test_restoring_a_retired_duplicate_is_refused_while_a_survivor_lives(self):
        """This is the constraint working, not a lifecycle violation.

        Restoring a retired duplicate would recreate exactly the corruption the
        remediation removed: two identical active rows for one provider transaction.
        It fails loudly rather than silently re-duplicating.
        """
        survivor = self._txn()
        extra = Transaction.all_objects.create(
            user=self.user, account=self.account, date=date(2026, 8, 20),
            amount=-10, description="x", plaid_transaction_id="txn-pred",
            status="deleted", deleted_at=timezone.now())

        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                extra.restore()

        survivor.refresh_from_db()
        self.assertEqual(survivor.status, "active")

    def test_restoring_is_allowed_once_the_survivor_is_gone(self):
        """Lifecycle is preserved: the row is recoverable, just never as a twin."""
        survivor = self._txn()
        extra = Transaction.all_objects.create(
            user=self.user, account=self.account, date=date(2026, 8, 20),
            amount=-10, description="x", plaid_transaction_id="txn-pred",
            status="deleted", deleted_at=timezone.now())

        survivor.soft_delete()
        extra.restore()                            # must not raise

        extra.refresh_from_db()
        self.assertEqual(extra.status, "active")
        self.assertEqual(Transaction.objects.filter(
            plaid_transaction_id="txn-pred").count(), 1)

    def test_many_retired_rows_may_coexist_with_one_survivor(self):
        """The partial predicate means retired history never runs out of room."""
        self._txn()
        for _ in range(4):
            Transaction.all_objects.create(
                user=self.user, account=self.account, date=date(2026, 8, 20),
                amount=-10, description="x", plaid_transaction_id="txn-pred",
                status="deleted", deleted_at=timezone.now())

        self.assertEqual(Transaction.objects.filter(
            plaid_transaction_id="txn-pred").count(), 1)
        self.assertEqual(Transaction.all_objects.filter(
            plaid_transaction_id="txn-pred").count(), 5)


class IdempotentIngestionTests(TestCase):
    """Defence 3, at the application seam: the loser of a race must not double-count."""

    def setUp(self):
        self.user = User.objects.create_user(email="ingest@example.com", password="x")
        self.conn = BankConnection.objects.create(
            user=self.user, institution_name="Bank A", item_id="item-i",
            connection_status=BankConnection.STATUS_ACTIVE,
            access_token_encrypted="tok")
        self.account = FinancialAccount.objects.create(
            user=self.user, name="Checking", bank_connection=self.conn,
            plaid_account_id="acct-provider-1")
        from apps.finance.services.sync_service import TransactionSyncService
        self.service = TransactionSyncService(self.conn)

    def test_processing_the_same_transaction_twice_creates_one_row(self):
        """Re-delivery is normal: Plaid resends in `modified`, and syncs overlap."""
        payload = _txn_payload("txn-same")
        self.assertTrue(self.service._create_or_update_transaction(payload))
        self.service._create_or_update_transaction(payload)

        # The second pass takes the UPDATE branch and legitimately reports handled;
        # what must never happen is a second ROW.
        self.assertEqual(Transaction.objects.filter(
            plaid_transaction_id="txn-same").count(), 1)

    def test_a_row_created_between_the_read_and_the_write_is_not_duplicated(self):
        """The exact production race, at the seam where it happened.

        The competing sync commits AFTER our existence check has already returned
        None. Before `get_or_create`, this reached a bare `.create()` and inserted a
        second row — 1,677 times on 2026-08-27.
        """
        payload = _txn_payload("txn-race")

        # The other sync's row is already committed...
        Transaction.objects.create(
            user=self.user, account=self.account, date=date(2026, 8, 20),
            amount=-12, description="Coffee Shop",
            plaid_transaction_id="txn-race")

        # ...but our lookup ran before that commit and saw nothing.
        real_filter = Transaction.objects.filter

        def stale_read(*args, **kwargs):
            if kwargs.get("plaid_transaction_id") == "txn-race":
                return real_filter(pk__in=[])          # the read that missed
            return real_filter(*args, **kwargs)

        Transaction.objects.filter = stale_read
        try:
            created = self.service._create_or_update_transaction(payload)
        finally:
            Transaction.objects.filter = real_filter

        self.assertFalse(created, "the loser of the race must not be counted as added")
        self.assertEqual(Transaction.objects.filter(
            plaid_transaction_id="txn-race").count(), 1)


class SecondInstitutionConcurrencyTests(TransactionTestCase):
    """Defence 2 — the exact production path, with real threads and real commits.

    `TransactionTestCase` (not `TestCase`) on purpose: the lock and the constraint are
    both enforced at COMMIT boundaries, which a wrapping test transaction hides.
    """
    reset_sequences = True

    def setUp(self):
        self.user = User.objects.create_user(email="conc@example.com", password="x")
        self.conn = BankConnection.objects.create(
            user=self.user, institution_name="Chase", item_id="item-second",
            connection_status=BankConnection.STATUS_ACTIVE,
            access_token_encrypted="tok")
        self.account = FinancialAccount.objects.create(
            user=self.user, name="Checking", bank_connection=self.conn,
            plaid_account_id="acct-provider-1")
        self.page = [_txn_payload(f"txn-{i}") for i in range(25)]

    def tearDown(self):
        Transaction.all_objects.all().delete()
        FinancialAccount.all_objects.all().delete()
        BankConnection.all_objects.all().delete()
        from apps.core.ai_scheduler.scheduler_models import SchedulerLock
        SchedulerLock.objects.filter(lock_name__startswith="finance_sync:").delete()

    def _run_two_syncs_concurrently(self):
        import threading
        from unittest.mock import patch

        from apps.finance.services.sync_service import TransactionSyncService

        barrier = threading.Barrier(2)
        errors = []

        def one(trigger):
            from django.db import connection as dbconn
            try:
                with patch("apps.finance.services.plaid_service.PlaidService."
                           "get_accounts", return_value=[]), \
                     patch("apps.finance.services.plaid_service.PlaidService."
                           "sync_transactions",
                           return_value={"added": list(self.page), "modified": [],
                                         "removed": [], "next_cursor": "c1",
                                         "has_more": False,
                                         "update_status": "HISTORICAL_UPDATE_COMPLETE"}), \
                     patch.object(BankConnection, "get_access_token",
                                  return_value="tok"):
                    barrier.wait(timeout=10)          # start together
                    TransactionSyncService(self.conn).sync(trigger=trigger)
            except Exception as exc:                  # recorded, not swallowed
                errors.append(f"{trigger}: {type(exc).__name__}: {exc}")
            finally:
                dbconn.close()

        threads = [threading.Thread(target=one, args=(t,))
                   for t in ("webhook", "scheduled")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        return errors

    def test_two_simultaneous_syncs_cannot_duplicate_transactions(self):
        errors = self._run_two_syncs_concurrently()
        self.assertEqual(errors, [], f"a concurrent sync raised: {errors}")

        stored = Transaction.all_objects.filter(user=self.user)
        ids = list(stored.values_list("plaid_transaction_id", flat=True))
        self.assertEqual(len(ids), len(set(ids)),
                         "the 2026-08-27 incident: two syncs, one transaction, two rows")
        self.assertEqual(stored.count(), len(self.page))

    def test_no_duplicates_even_when_the_lock_is_bypassed(self):
        """Belt and braces: the DB must hold the line without the lock."""
        import threading
        from unittest.mock import patch

        from apps.finance.services.sync_service import TransactionSyncService

        barrier = threading.Barrier(2)
        errors = []

        def one(trigger):
            from django.db import connection as dbconn
            try:
                with patch("apps.finance.services.plaid_service.PlaidService."
                           "get_accounts", return_value=[]), \
                     patch("apps.finance.services.plaid_service.PlaidService."
                           "sync_transactions",
                           return_value={"added": list(self.page), "modified": [],
                                         "removed": [], "next_cursor": "c1",
                                         "has_more": False, "update_status": ""}), \
                     patch.object(BankConnection, "get_access_token",
                                  return_value="tok"), \
                     patch("apps.finance.services.sync_service._ConnectionSyncLock."
                           "acquire", return_value=True), \
                     patch("apps.finance.services.sync_service._ConnectionSyncLock."
                           "release"):
                    barrier.wait(timeout=10)
                    TransactionSyncService(self.conn).sync(trigger=trigger)
            except Exception as exc:
                errors.append(f"{trigger}: {type(exc).__name__}")
            finally:
                dbconn.close()

        threads = [threading.Thread(target=one, args=(t,))
                   for t in ("webhook", "scheduled")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        ids = list(Transaction.all_objects.filter(user=self.user)
                   .values_list("plaid_transaction_id", flat=True))
        self.assertEqual(len(ids), len(set(ids)),
                         "the database must refuse duplicates even with no lock")


class SoftDeleteExclusionTests(TestCase):
    """Post-cleanup: every Finance total must ignore retired rows."""

    def setUp(self):
        self.user = User.objects.create_user(email="totals@example.com", password="x")
        self.conn = BankConnection.objects.create(
            user=self.user, institution_name="Bank", item_id="item-t",
            connection_status=BankConnection.STATUS_ACTIVE)
        self.account = FinancialAccount.objects.create(
            user=self.user, name="Checking", bank_connection=self.conn,
            plaid_account_id="acct-provider-1")
        self.keeper = Transaction.objects.create(
            user=self.user, account=self.account, date=date(2026, 8, 20),
            amount=-50, description="Real", plaid_transaction_id="keep-1")
        self.retired = Transaction.objects.create(
            user=self.user, account=self.account, date=date(2026, 8, 20),
            amount=-50, description="Real", plaid_transaction_id="dupe-1")
        self.retired.status = "deleted"
        self.retired.deleted_at = timezone.now()
        self.retired.save(update_fields=["status", "deleted_at"])

    def test_default_manager_excludes_retired_rows(self):
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Transaction.all_objects.filter(user=self.user).count(), 2)

    def test_the_population_authority_excludes_retired_rows(self):
        from apps.finance.services.attribution_population import financial_activity

        rows = financial_activity(self.user)
        self.assertNotIn(self.retired.pk, [t.pk for t in rows])

    def test_account_inception_date_is_unaffected_by_retirement(self):
        """`finance_entities` reads `all_objects` for MIN(date) on purpose.

        A retired duplicate always shares its survivor's date, so the earliest date an
        account can be said to have existed cannot move — which is why that one
        deliberate `all_objects` read stays correct after the cleanup.
        """
        from apps.finance.services.finance_entities import earliest_account_activity

        self.assertEqual(earliest_account_activity(self.account), date(2026, 8, 20))
