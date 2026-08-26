# ==============================================================================
# File: apps/finance/tests/test_history_coverage.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Request the maximum useful history, and never overstate what arrived.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Two separate obligations: ASK for enough history, and be honest about what is in.

The first live connection returned 87 days because `days_requested` was never sent, so
Plaid's 90-day default applied. The window is fixed when the Item is created, which makes
this a defect you cannot fix after the fact by syncing harder.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest import mock, skipUnless

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.finance.models import BankConnection, FinancialAccount, Transaction
from apps.finance.services.encryption import generate_encryption_key
from apps.finance.services.plaid_service import (
    TRANSACTION_HISTORY_DAYS_REQUESTED,
    PlaidService,
)

try:
    import plaid  # noqa: F401
    PLAID_SDK = True
except ImportError:              # the dev machine does not carry the SDK; prod does
    PLAID_SDK = False

User = get_user_model()
KEY = generate_encryption_key()
TODAY = date.today()


class DaysRequestedTests(TestCase):

    def test_the_maximum_supported_window_is_requested(self):
        self.assertEqual(TRANSACTION_HISTORY_DAYS_REQUESTED, 730,
                         "730 days is the provider maximum; the default of 90 cannot "
                         "answer a year-over-year question")

    @skipUnless(PLAID_SDK, "plaid-python not installed in this environment")
    @override_settings(PLAID_CLIENT_ID="cid", PLAID_SECRET="sec", PLAID_ENV="sandbox",
                       PLAID_REDIRECT_URI="")
    def test_new_item_tokens_send_days_requested(self):
        captured = {}

        class _Client:
            def link_token_create(self, request):
                captured["transactions"] = getattr(request, "transactions", None)
                return mock.Mock(link_token="link-sandbox-x", expiration="soon")

        service = PlaidService()
        service._client = _Client()
        user = User.objects.create_user(email="days@example.com", password="x" * 14)
        service.create_link_token(user)

        self.assertIsNotNone(captured["transactions"],
                             "omitting days_requested silently accepts 90 days")
        self.assertEqual(captured["transactions"].days_requested,
                         TRANSACTION_HISTORY_DAYS_REQUESTED)

    @skipUnless(PLAID_SDK, "plaid-python not installed in this environment")
    @override_settings(PLAID_CLIENT_ID="cid", PLAID_SECRET="sec", PLAID_ENV="sandbox")
    def test_update_mode_does_NOT_request_history(self):
        """Update mode repairs an Item; it cannot widen transaction history.

        Plaid's contract: once Transactions is initialized on an Item, `days_requested`
        HAS NO EFFECT (plaid.com/docs/transactions/troubleshooting/). Plaid will still
        ACCEPT a token carrying it — which is the trap. Sending it would encode a promise
        the provider does not make, and would make a partial history look fixable when
        it is not.
        """
        captured = {}

        class _Client:
            def link_token_create(self, request):
                captured["transactions"] = getattr(request, "transactions", None)
                captured["access_token"] = getattr(request, "access_token", None)
                return mock.Mock(link_token="link-sandbox-x", expiration="soon")

        service = PlaidService()
        service._client = _Client()
        user = User.objects.create_user(email="days2@example.com", password="x" * 14)
        service.create_link_token_for_update(user, "access-sandbox-FAKE")

        self.assertTrue(captured["access_token"], "update mode needs the access token")
        self.assertIsNone(
            captured["transactions"],
            "update mode must NOT carry days_requested — it cannot widen history")

    def test_no_code_path_sends_days_requested_in_update_mode(self):
        """AST-based: the comment above the code explains the rule and must name it;
        only EXECUTABLE references count."""
        import ast
        import inspect
        import textwrap

        from apps.finance.services import plaid_service
        tree = ast.parse(textwrap.dedent(inspect.getsource(
            plaid_service.PlaidService.create_link_token_for_update)))
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg in ("days_requested",
                                                              "transactions"):
                offenders.append(f"keyword {node.arg}")
            if isinstance(node, ast.Attribute) and node.attr == "transactions":
                offenders.append("attribute transactions")
            if isinstance(node, ast.Name) and node.id == "LinkTokenTransactions":
                offenders.append("LinkTokenTransactions")
        self.assertEqual(offenders, [],
                         f"update mode must not request history: {offenders}")

    def test_an_accepted_token_is_never_treated_as_backfill_evidence(self):
        """The reasoning error this suite exists to prevent.

        A 200 from /link/token/create means the REQUEST was valid. It says nothing about
        whether history will expand. Nothing in the codebase may infer coverage from a
        token being accepted.
        """
        from pathlib import Path

        finance_dir = Path(__file__).resolve().parents[1]
        offenders = []
        for path in list(finance_dir.rglob("*.py")) + [
                Path("templates/finance/bank_connection_list.html")]:
            parts = path.parts
            if any(skip in parts for skip in ("migrations", "__pycache__")):
                continue
            if path.name == Path(__file__).name:
                continue
            text = path.read_text(encoding="utf-8").lower()
            for phrase in ("update mode is also the supported way to widen",
                           "extend history", "widen an existing item",
                           "widening it requires re-running link"):
                if phrase in text:
                    offenders.append(f"{path.name}: {phrase}")
        self.assertEqual(offenders, [],
                         f"a false history-extension claim survives: {offenders}")

    def test_the_requested_window_is_recorded_on_the_connection(self):
        source = open("apps/finance/views.py").read()
        self.assertIn("history_days_requested = TRANSACTION_HISTORY_DAYS_REQUESTED",
                      source)


@override_settings(BANK_TOKEN_ENCRYPTION_KEY=KEY)
class CoverageHonestyTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="cov@example.com", password="x" * 14)
        prefs = self.user.preferences
        prefs.finances_enabled = True
        prefs.save()
        self.connection = BankConnection.objects.create(
            user=self.user, item_id="item-cov", institution_name="Test Bank",
            connection_status=BankConnection.STATUS_ACTIVE,
            history_days_requested=730)
        self.connection.set_access_token("access-production-FAKE")
        self.connection.save()

    def test_partial_history_is_never_labelled_complete(self):
        self.assertFalse(self.connection.history_import_complete)
        self.assertIn("Connected", self.connection.history_state_label)

        self.connection.initial_update_complete = True
        self.connection.save(update_fields=["initial_update_complete"])
        label = self.connection.history_state_label
        self.assertIn("Initial data loaded", label)
        self.assertIn("historical import still running", label.lower())
        self.assertFalse(self.connection.history_import_complete)

    def test_only_the_historical_milestone_marks_it_complete(self):
        self.connection.historical_update_complete = True
        self.connection.save(update_fields=["historical_update_complete"])
        self.assertTrue(self.connection.history_import_complete)
        self.assertEqual(self.connection.history_state_label,
                         "Historical import complete")

    def test_the_dashboard_calls_provisional_totals_provisional(self):
        from apps.finance.services.finance_intelligence_summary import (
            build_finance_intelligence,
            summary_lines,
        )
        account = FinancialAccount.objects.create(
            user=self.user, name="Checking", account_type="checking")
        Transaction.objects.create(
            user=self.user, account=account, date=TODAY - timedelta(days=30),
            amount=Decimal("-10.00"), description="x")

        data = build_finance_intelligence(self.user)
        self.assertTrue(data["freshness"]["history_incomplete"])
        joined = " ".join(summary_lines(self.user, data)).lower()
        self.assertIn("provisional", joined)
        self.assertIn("historical import is still in progress", joined)

        self.connection.historical_update_complete = True
        self.connection.save(update_fields=["historical_update_complete"])
        data = build_finance_intelligence(self.user)
        self.assertFalse(data["freshness"]["history_incomplete"])
        self.assertNotIn("provisional",
                         " ".join(summary_lines(self.user, data)).lower())

    def test_the_connections_page_states_coverage_separately_from_health(self):
        source = open("templates/finance/bank_connection_list.html").read()
        self.assertIn("history_state_label", source)
        self.assertIn("days requested", source)
        self.assertIn("provisional until the import finishes", source)

    def test_the_ui_never_offers_history_extension(self):
        """There is no honest 'extend history' button — the operation does not exist."""
        source = open("templates/finance/bank_connection_list.html").read().lower()
        for forbidden in ("extend history", "extend-history", "get more history",
                          "expand history"):
            self.assertNotIn(forbidden, source)

    def test_a_ninety_day_item_is_never_relabelled_as_seven_thirty(self):
        """The recorded window is what was ASKED FOR at creation, not today's constant."""
        self.assertEqual(self.connection.history_days_requested, 730)
        legacy = BankConnection.objects.create(
            user=self.user, item_id="item-legacy", institution_name="Older Bank",
            connection_status=BankConnection.STATUS_ACTIVE,
            history_days_requested=90, initial_update_complete=True,
            historical_update_complete=True)
        self.assertEqual(legacy.history_days_requested, 90)
        self.assertEqual(legacy.history_state_label, "Historical import complete")
        self.assertTrue(legacy.history_import_complete,
                        "complete for the window it requested — which is the truth")

    def test_webhook_milestones_advance_coverage(self):
        """INITIAL_UPDATE and HISTORICAL_UPDATE mean different things; both are recorded."""
        source = open("apps/finance/views.py").read()
        self.assertIn("webhook_code == 'INITIAL_UPDATE'", source)
        self.assertIn("webhook_code == 'HISTORICAL_UPDATE'", source)
        self.assertIn("historical_update_complete = True", source)
