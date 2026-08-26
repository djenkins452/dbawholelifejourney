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
    def test_update_mode_tokens_also_widen_the_window(self):
        """Update mode is how an EXISTING Item gets more history without removal."""
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
        self.assertEqual(captured["transactions"].days_requested,
                         TRANSACTION_HISTORY_DAYS_REQUESTED)

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

    def test_webhook_milestones_advance_coverage(self):
        """INITIAL_UPDATE and HISTORICAL_UPDATE mean different things; both are recorded."""
        source = open("apps/finance/views.py").read()
        self.assertIn("webhook_code == 'INITIAL_UPDATE'", source)
        self.assertIn("webhook_code == 'HISTORICAL_UPDATE'", source)
        self.assertIn("historical_update_complete = True", source)
