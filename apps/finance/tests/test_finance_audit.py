# ==============================================================================
# File: apps/finance/tests/test_finance_audit.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Finance audit is read-only, aggregate-only, and key-protected.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""An operator audit must never become a data leak."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.finance.models import FinancialAccount, FinancialEntity, Transaction
from apps.finance.services import finance_entities as entity_service
from apps.finance.services.finance_audit import audit, redact

User = get_user_model()


class AuditShapeTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="audit@example.com", password="x" * 14)
        self.personal, _ = entity_service.ensure_default_entities(self.user)
        self.account = FinancialAccount.objects.create(
            user=self.user, name="Secret Bank Checking", account_type="checking",
            institution="Very Private Bank", account_number_last4="4242",
        )
        entity_service.assign_account_entity(self.user, self.account, self.personal)
        Transaction.objects.create(
            user=self.user, account=self.account, date=date.today(),
            amount=Decimal("-1234.56"), description="Deeply personal purchase",
            payee="Embarrassing Vendor LLC",
        )

    def test_audit_leaks_no_sensitive_detail(self):
        blob = json.dumps(audit(), default=str).lower()
        for secret in ("deeply personal purchase", "embarrassing vendor",
                       "secret bank checking", "very private bank", "4242",
                       "1234.56", "audit@example.com"):
            self.assertNotIn(secret.lower(), blob,
                             f"the audit leaked {secret!r}")

    def test_audit_reports_the_expected_aggregates(self):
        result = audit()
        self.assertEqual(result["environment"]["finance_active_users"], 1)
        self.assertEqual(result["accounts"]["total"], 1)
        self.assertEqual(result["accounts"]["without_entity_assignment"], 0)
        self.assertEqual(result["transactions"]["total_active"], 1)
        self.assertIn("by_type", result["entities"])
        self.assertIn("plaid_env", result["environment"]["provider"])

    def test_integrity_section_is_all_zero_on_clean_data(self):
        self.assertEqual(set(audit()["integrity"].values()), {0})

    def test_integrity_detects_a_cross_user_reference(self):
        """The services forbid this; the audit must still be able to SEE it."""
        from apps.finance.models import TransactionAttribution
        other = User.objects.create_user(email="audit2@example.com", password="x" * 14)
        their_entity = entity_service.create_entity(
            other, entity_type=FinancialEntity.TYPE_BUSINESS, name="Theirs")
        txn = Transaction.objects.get(user=self.user)
        TransactionAttribution.objects.create(
            user=self.user, transaction=txn, attributed_entity=their_entity,
            paid_by_entity=self.personal,
            source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
            actor=TransactionAttribution.ACTOR_SYSTEM,
        )
        result = audit()
        self.assertEqual(result["integrity"]["attribution_entity_mismatch"], 1)
        self.assertEqual(result["readiness"]["status"], "unhealthy")

    def test_readiness_reports_thin_data_honestly(self):
        result = audit()
        self.assertEqual(result["readiness"]["status"], "thin",
                         "one transaction is not enough history to trust a finding")

    def test_redaction(self):
        self.assertEqual(redact("danny@example.com"), "d***@example.com")
        self.assertEqual(redact(""), "***")

    def test_audit_makes_no_provider_or_model_call(self):
        import inspect

        from apps.finance.services import finance_audit
        source = inspect.getsource(finance_audit)
        for token in ("_call_api", "OpenAI", "AIService", "requests.", "PlaidService"):
            self.assertNotIn(token, source)


@override_settings(CLAUDE_API_KEY="test-audit-key")
class AuditEndpointTests(TestCase):

    def test_requires_the_operator_key(self):
        url = reverse("admin_console:api_claude_finance_audit")
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(
            self.client.get(url, HTTP_X_CLAUDE_API_KEY="wrong").status_code, 401)
        response = self.client.get(url, HTTP_X_CLAUDE_API_KEY="test-audit-key")
        self.assertEqual(response.status_code, 200)
        self.assertIn("readiness", response.json())
