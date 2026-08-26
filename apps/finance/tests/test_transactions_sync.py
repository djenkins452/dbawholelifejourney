# ==============================================================================
# File: apps/finance/tests/test_transactions_sync.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: /transactions/sync — cursor contract, pagination, idempotency, states.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The first sync of a connection must be possible.

Root cause of the 2026-08-26 02:36:47 UTC failure: the SDK request was built with
`cursor=cursor if cursor else None`. plaid-python validates the TYPE of every optional
field that is PRESENT, so an explicit `None` fails client-side before the request is
sent. Since a first sync has no cursor, the first sync of every connection was
impossible.

All fixtures are synthetic. No Plaid call is made and no bank is contacted.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.finance.models import BankConnection, FinancialAccount, Transaction
from apps.finance.services.encryption import generate_encryption_key
from apps.finance.services.sync_service import TransactionSyncService

User = get_user_model()
TODAY = date.today()
KEY = generate_encryption_key()


def account_payload(plaid_id="pacct-1", name="Everyday Checking"):
    return {
        "id": plaid_id, "name": name, "official_name": name,
        "type": "depository", "subtype": "checking", "mask": "4242",
        "balance_available": 100.0, "balance_current": 120.0,
        "balance_limit": None, "currency": "USD",
    }


def txn_payload(txn_id="ptx-1", amount=54.0, **extra):
    payload = {
        "transaction_id": txn_id, "account_id": "pacct-1", "amount": amount,
        "date": TODAY, "name": "DESIGN TOOL", "merchant_name": "Design Tool",
        "pending": False, "category": [], "category_id": None,
        "pfc_primary": "GENERAL_SERVICES", "pfc_detailed": "", "pfc_confidence": "HIGH",
        "payment_channel": "online", "transaction_code": "",
        "pending_transaction_id": "", "authorized_date": None,
        "counterparties": [], "location": None,
    }
    payload.update(extra)
    return payload


class _MutationDuringPagination(Exception):
    error_type = "TRANSACTIONS_ERROR"
    error_code = "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION"
    request_id = "req-mutate"
    status = 400


class _FakePlaid:
    """Records how `sync_transactions` was called and replays scripted pages."""

    def __init__(self, pages=None, accounts=None, raise_on_call=None):
        self.pages = pages or [{"added": [], "modified": [], "removed": [],
                                "next_cursor": "", "has_more": False}]
        self.accounts = accounts or [account_payload()]
        self.calls = []
        self.raise_on_call = raise_on_call or {}
        self._page_index = 0

    def get_accounts(self, access_token):
        return self.accounts

    def sync_transactions(self, access_token, cursor=""):
        call_number = len(self.calls) + 1
        # Record EXACTLY what the service passed, so the contract can be asserted.
        self.calls.append(cursor)
        if call_number in self.raise_on_call:
            raise self.raise_on_call[call_number]
        if self._page_index >= len(self.pages):
            return {"added": [], "modified": [], "removed": [],
                    "next_cursor": cursor or "", "has_more": False}
        page = self.pages[self._page_index]
        self._page_index += 1
        return page


@override_settings(BANK_TOKEN_ENCRYPTION_KEY=KEY)
class SyncBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="sync@example.com", password="x" * 14)
        prefs = self.user.preferences
        prefs.finances_enabled = True
        prefs.save()
        self.connection = BankConnection.objects.create(
            user=self.user, item_id="item-1",
            institution_name="Test Bank",
            connection_status=BankConnection.STATUS_PENDING)
        self.connection.set_access_token("access-production-FAKE")
        self.connection.save()

    def _run(self, fake):
        service = TransactionSyncService(self.connection)
        import unittest.mock as mock
        with mock.patch("apps.finance.services.plaid_service.get_plaid_service",
                        return_value=fake):
            return service.sync()


class CursorContractTests(SyncBase):

    def test_first_call_omits_the_cursor_entirely(self):
        """The exact production failure: no cursor must mean NO cursor field."""
        fake = _FakePlaid()
        self._run(fake)
        self.assertEqual(fake.calls, [""], "the first call must carry no cursor")

    def test_the_sdk_request_never_receives_a_none_cursor(self):
        import inspect

        from apps.finance.services import plaid_service
        source = inspect.getsource(plaid_service.PlaidService.sync_transactions)
        self.assertNotIn("cursor=cursor if cursor else None", source)
        self.assertIn("if cursor:", source)
        self.assertIn("kwargs['cursor'] = cursor", source)

    def test_no_placeholder_cursor_is_ever_substituted(self):
        fake = _FakePlaid()
        self._run(fake)
        for call in fake.calls:
            self.assertNotIn("now", call.lower())
            self.assertFalse(call.startswith("cursor-"))

    def test_later_call_includes_the_persisted_cursor(self):
        self.connection.last_sync_cursor = "cursor-from-last-time"
        self.connection.save(update_fields=["last_sync_cursor"])
        fake = _FakePlaid(pages=[{"added": [], "modified": [], "removed": [],
                                  "next_cursor": "cursor-next", "has_more": False}])
        self._run(fake)
        self.assertEqual(fake.calls, ["cursor-from-last-time"])
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.last_sync_cursor, "cursor-next")


class PreparingStateTests(SyncBase):

    def test_empty_initial_response_is_a_preparing_state_not_a_failure(self):
        result = self._run(_FakePlaid())
        self.assertTrue(result["preparing"])
        self.assertNotIn("error", result)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.connection_status,
                         BankConnection.STATUS_PENDING)
        self.assertEqual(self.connection.error_message, "")
        self.assertEqual(self.connection.error_code, "")

    def test_an_empty_next_cursor_is_not_persisted(self):
        self._run(_FakePlaid())
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.last_sync_cursor, "")

    def test_a_successful_sync_activates_the_connection(self):
        fake = _FakePlaid(pages=[{"added": [txn_payload()], "modified": [], "removed": [],
                                  "next_cursor": "cursor-1", "has_more": False}])
        result = self._run(fake)
        self.assertFalse(result["preparing"])
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.connection_status,
                         BankConnection.STATUS_ACTIVE)
        self.assertEqual(self.connection.last_sync_cursor, "cursor-1")


class PaginationTests(SyncBase):

    def test_pages_are_followed_and_the_final_cursor_persisted(self):
        fake = _FakePlaid(pages=[
            {"added": [txn_payload("ptx-1")], "modified": [], "removed": [],
             "next_cursor": "c1", "has_more": True},
            {"added": [txn_payload("ptx-2")], "modified": [], "removed": [],
             "next_cursor": "c2", "has_more": True},
            {"added": [txn_payload("ptx-3")], "modified": [], "removed": [],
             "next_cursor": "c3", "has_more": False},
        ])
        result = self._run(fake)
        self.assertEqual(fake.calls, ["", "c1", "c2"])
        self.assertEqual(result["added"], 3)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.last_sync_cursor, "c3",
                         "only the FINAL cursor is a safe boundary to persist")

    def test_mutation_during_pagination_restarts_from_the_durable_cursor(self):
        self.connection.last_sync_cursor = "start"
        self.connection.save(update_fields=["last_sync_cursor"])
        fake = _FakePlaid(
            pages=[
                {"added": [txn_payload("ptx-1")], "modified": [], "removed": [],
                 "next_cursor": "c1", "has_more": True},
                # call 2 raises (scripted below)
                {"added": [txn_payload("ptx-1")], "modified": [], "removed": [],
                 "next_cursor": "cfinal", "has_more": False},
            ],
            raise_on_call={2: _MutationDuringPagination()})
        result = self._run(fake)
        self.assertEqual(fake.calls[0], "start")
        self.assertEqual(fake.calls[-1], "start",
                         "a restart must resume from the last DURABLE cursor")
        self.assertNotIn("error", result)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.last_sync_cursor, "cfinal")

    def test_pagination_is_bounded(self):
        endless = [{"added": [], "modified": [], "removed": [],
                    "next_cursor": f"c{i}", "has_more": True} for i in range(200)]
        fake = _FakePlaid(pages=endless)
        self._run(fake)
        self.assertLessEqual(len(fake.calls),
                             TransactionSyncService.MAX_SYNC_PAGES + 1)


class IdempotencyTests(SyncBase):

    def test_rerunning_the_initial_sync_duplicates_nothing(self):
        pages = [{"added": [txn_payload("ptx-1"), txn_payload("ptx-2", amount=12.0)],
                  "modified": [], "removed": [], "next_cursor": "c1",
                  "has_more": False}]
        self._run(_FakePlaid(pages=list(pages)))
        first_accounts = FinancialAccount.objects.filter(user=self.user).count()
        first_txns = Transaction.objects.filter(user=self.user).count()

        # Replay the SAME page — a retry, a duplicate webhook, a manual sync.
        self._run(_FakePlaid(pages=list(pages)))
        self.assertEqual(FinancialAccount.objects.filter(user=self.user).count(),
                         first_accounts)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), first_txns)

    def test_accounts_are_matched_by_provider_id_not_recreated(self):
        fake = _FakePlaid(accounts=[account_payload("pacct-1"),
                                    account_payload("pacct-2", "Savings")])
        self._run(fake)
        self._run(_FakePlaid(accounts=[account_payload("pacct-1"),
                                       account_payload("pacct-2", "Savings")]))
        self.assertEqual(FinancialAccount.objects.filter(user=self.user).count(), 2)

    def test_a_failed_sync_does_not_advance_the_cursor(self):
        fake = _FakePlaid(raise_on_call={1: RuntimeError("boom")})
        self._run(fake)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.last_sync_cursor, "")


class SafeFailureStateTests(SyncBase):

    def test_an_sdk_validation_error_never_reaches_the_user(self):
        """The literal production failure, replayed."""
        message = ("Invalid type for variable 'cursor'. Required value type is str and "
                   "passed type was NoneType at ['cursor']")
        result = self._run(_FakePlaid(raise_on_call={1: TypeError(message)}))
        self.connection.refresh_from_db()
        self.assertNotIn("NoneType", self.connection.error_message)
        self.assertEqual(self.connection.error_message, "")
        self.assertEqual(self.connection.connection_status,
                         BankConnection.STATUS_PENDING,
                         "our own bug is not the user's actionable problem")
        self.assertEqual(result["error"], "sync_incomplete")

    def test_a_genuine_auth_problem_asks_for_reconnection(self):
        class _LoginRequired(Exception):
            error_type = "ITEM_ERROR"
            error_code = "ITEM_LOGIN_REQUIRED"
            request_id = "req-auth"
            status = 400

        result = self._run(_FakePlaid(raise_on_call={1: _LoginRequired()}))
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.connection_status,
                         BankConnection.STATUS_REAUTH_REQUIRED)
        self.assertEqual(result["error"], "reauth_required")

    def test_the_audit_log_keeps_codes_not_payloads(self):
        from apps.finance.models import BankIntegrationLog

        self._run(_FakePlaid(raise_on_call={1: TypeError("secret detail here")}))
        entry = BankIntegrationLog.objects.filter(success=False).first()
        self.assertIsNotNone(entry)
        self.assertNotIn("secret detail", str(entry.details))

    def test_the_connection_page_shows_a_truthful_preparing_message(self):
        source = open("templates/finance/bank_connection_list.html").read()
        self.assertIn("still being prepared", source)
        self.assertIn("connection.connection_status == 'pending'", source)


class NullProviderFieldTests(SyncBase):
    """Plaid routinely returns null for fields it could not resolve.

    `.get(key, default)` returns None when the key EXISTS and is null — the default only
    applies to a MISSING key. `payee` is non-null in the schema, so an unresolved
    merchant produced an IntegrityError and aborted the whole sync mid-page. This is the
    second failure the first live connection hit, after the cursor.
    """

    def test_a_null_merchant_name_does_not_break_the_sync(self):
        page = {"added": [txn_payload("ptx-null", merchant_name=None,
                                      name="VENMO PAYMENT")],
                "modified": [], "removed": [], "next_cursor": "c1", "has_more": False}
        result = self._run(_FakePlaid(pages=[page]))
        self.assertEqual(result["added"], 1)
        txn = Transaction.objects.get(plaid_transaction_id="ptx-null")
        self.assertEqual(txn.payee, "")
        self.assertEqual(txn.description, "VENMO PAYMENT")

    def test_null_account_fields_do_not_break_account_import(self):
        account = account_payload()
        account.update({"mask": None, "currency": None, "official_name": None,
                        "subtype": None})
        result = self._run(_FakePlaid(accounts=[account]))
        self.assertEqual(result["accounts_synced"], 1)
        created = FinancialAccount.objects.get(plaid_account_id="pacct-1")
        self.assertEqual(created.currency, "USD")
        self.assertEqual(created.account_number_last4, "")

    def test_one_bad_row_cannot_abort_the_whole_page(self):
        """Even if a row fails, the rest of the page must still land."""
        page = {"added": [txn_payload("ptx-a"), txn_payload("ptx-b", merchant_name=None),
                          txn_payload("ptx-c")],
                "modified": [], "removed": [], "next_cursor": "c1", "has_more": False}
        result = self._run(_FakePlaid(pages=[page]))
        self.assertEqual(result["added"], 3)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 3)


class ConnectionLifecycleTests(SyncBase):

    def test_preparing_clears_any_previous_error(self):
        self.connection.mark_error("SYNC_ERROR", "old raw message")
        self.connection.mark_preparing()
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.connection_status,
                         BankConnection.STATUS_PENDING)
        self.assertEqual(self.connection.error_message, "")
        self.assertEqual(self.connection.error_code, "")

    def test_preparing_then_active_after_data_arrives(self):
        self._run(_FakePlaid())
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.connection_status,
                         BankConnection.STATUS_PENDING)
        self._run(_FakePlaid(pages=[{"added": [txn_payload()], "modified": [],
                                     "removed": [], "next_cursor": "c1",
                                     "has_more": False}]))
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.connection_status,
                         BankConnection.STATUS_ACTIVE)

    def test_the_token_stays_encrypted_throughout(self):
        self._run(_FakePlaid())
        self.connection.refresh_from_db()
        self.assertTrue(self.connection.access_token_encrypted)
        self.assertNotIn("access-production-FAKE",
                         self.connection.access_token_encrypted)
        self.assertEqual(self.connection.get_access_token(), "access-production-FAKE")
