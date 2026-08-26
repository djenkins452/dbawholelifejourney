# ==============================================================================
# File: apps/finance/tests/test_plaid_webhook_delivery.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Regression tests for the two defects that silently discarded every
#              real Plaid webhook (2026-08-26 production incident).
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Two proven production defects, each of which alone made webhooks useless.

**Defect 1 — the key fetch could never succeed.** `PlaidService.is_configured` is a
`@property`; `fetch_verification_key` called it as `is_configured()`. Every genuine
webhook therefore raised `TypeError` inside the broad `except`, and was rejected as
`unknown_or_unavailable_key` — a reason code that reads like "Plaid sent an unfamiliar
key", so the logs actively pointed away from the real cause. The existing suite never
caught it because every verification test injects `key_fetcher`, so the real function
body had no test coverage at all.

**Defect 2 — completion could never be recorded.** WLJ ingests via
`/transactions/sync`, for which Plaid sends `SYNC_UPDATES_AVAILABLE` carrying
`initial_update_complete` / `historical_update_complete` as boolean FIELDS. The handler
keyed the flags on the legacy `INITIAL_UPDATE` / `HISTORICAL_UPDATE` webhook codes,
which a sync integration never receives — so history was permanently reported as
"still running" even after Plaid finished.
"""
import ast
import json
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.finance.models import BankConnection
from apps.finance.services import plaid_webhook_verification as pwv
from apps.users.models import User


class FetchVerificationKeyTests(TestCase):
    """Exercise the REAL `fetch_verification_key` body — the untested gap."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    @override_settings(PLAID_CLIENT_ID="id", PLAID_SECRET="secret")
    def test_real_fetch_reaches_the_key_service_and_returns_the_jwk(self):
        """The regression: this failed with TypeError before the fix."""
        class StubService:
            is_configured = True          # a PROPERTY on the real service

            def get_webhook_verification_key(self, key_id):
                return {"kid": key_id, "kty": "EC", "crv": "P-256"}

        with patch("apps.finance.services.plaid_service.get_plaid_service",
                   return_value=StubService()):
            jwk = pwv.fetch_verification_key("kid-123")

        self.assertEqual(jwk["kid"], "kid-123")

    @override_settings(PLAID_CLIENT_ID="id", PLAID_SECRET="secret")
    def test_service_defect_is_reported_distinctly_from_an_unknown_key(self):
        """A WLJ-side error must never masquerade as 'Plaid sent an unknown kid'."""
        class ExplodingService:
            is_configured = True

            def get_webhook_verification_key(self, key_id):
                raise TypeError("'bool' object is not callable")

        with patch("apps.finance.services.plaid_service.get_plaid_service",
                   return_value=ExplodingService()):
            with self.assertRaises(pwv.KeyFetchError):
                pwv.fetch_verification_key("kid-123")

    @override_settings(PLAID_CLIENT_ID="id", PLAID_SECRET="secret")
    def test_verify_webhook_surfaces_key_fetch_error_reason(self):
        request = type("R", (), {
            "headers": {"Plaid-Verification": "x.y.z"}, "body": b"{}"})()

        def boom(_kid):
            raise pwv.KeyFetchError("service unreachable")

        with patch("jwt.get_unverified_header",
                   return_value={"alg": "ES256", "kid": "k"}):
            result = pwv.verify_webhook(request, key_fetcher=boom)

        self.assertFalse(result.verified)
        self.assertEqual(result.reason, pwv.REASON_KEY_FETCH_ERROR)

    @override_settings(PLAID_CLIENT_ID="id", PLAID_SECRET="secret")
    def test_genuinely_unknown_key_still_reports_unknown_key(self):
        request = type("R", (), {
            "headers": {"Plaid-Verification": "x.y.z"}, "body": b"{}"})()
        with patch("jwt.get_unverified_header",
                   return_value={"alg": "ES256", "kid": "k"}):
            result = pwv.verify_webhook(request, key_fetcher=lambda _k: None)
        self.assertFalse(result.verified)
        self.assertEqual(result.reason, pwv.REASON_UNKNOWN_KEY)


class PropertyCalledAsMethodContractTests(TestCase):
    """Eliminate the CLASS, repo-wide: `is_configured` is a property everywhere."""

    def test_is_configured_is_never_invoked_as_a_method(self):
        offenders = []
        root = Path(settings.BASE_DIR) / "apps"
        for path in root.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                # Matches `<anything>.is_configured(...)`, never the attribute read.
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "is_configured"):
                    offenders.append(f"{path.relative_to(settings.BASE_DIR)}:{node.lineno}")

        self.assertEqual(
            offenders, [],
            "`is_configured` is a @property — calling it raises TypeError at runtime "
            f"on a path tests may not cover. Drop the parentheses at: {offenders}")


class SyncWebhookCompletionTests(TestCase):
    """`SYNC_UPDATES_AVAILABLE` carries the milestones as boolean fields."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="webhook-test@example.com", password="x")
        self.connection = BankConnection.objects.create(
            user=self.user, institution_name="Test Bank",
            item_id="item-webhook-test", status=BankConnection.STATUS_ACTIVE)
        self.url = reverse("finance:plaid_webhook")

    def _post(self, payload):
        with patch("apps.finance.views.verify_plaid_webhook",
                   return_value=(True, None)), \
             patch("apps.finance.services.sync_service."
                   "TransactionSyncService.sync", return_value=None):
            return self.client.post(self.url, data=json.dumps(payload),
                                    content_type="application/json")

    def test_sync_webhook_records_initial_completion(self):
        self._post({"webhook_type": "TRANSACTIONS",
                    "webhook_code": "SYNC_UPDATES_AVAILABLE",
                    "item_id": "item-webhook-test",
                    "initial_update_complete": True,
                    "historical_update_complete": False})
        self.connection.refresh_from_db()
        self.assertTrue(self.connection.initial_update_complete)
        self.assertFalse(self.connection.historical_update_complete)
        self.assertEqual(self.connection.history_state_label,
                         "Initial data loaded — historical import still running")

    def test_sync_webhook_records_historical_completion(self):
        self._post({"webhook_type": "TRANSACTIONS",
                    "webhook_code": "SYNC_UPDATES_AVAILABLE",
                    "item_id": "item-webhook-test",
                    "initial_update_complete": True,
                    "historical_update_complete": True})
        self.connection.refresh_from_db()
        self.assertTrue(self.connection.historical_update_complete)
        self.assertIsNotNone(self.connection.historical_update_at)
        self.assertEqual(self.connection.history_state_label,
                         "Historical import complete")

    def test_a_later_webhook_never_un_completes_history(self):
        self._post({"webhook_type": "TRANSACTIONS",
                    "webhook_code": "SYNC_UPDATES_AVAILABLE",
                    "item_id": "item-webhook-test",
                    "initial_update_complete": True,
                    "historical_update_complete": True})
        self._post({"webhook_type": "TRANSACTIONS",
                    "webhook_code": "SYNC_UPDATES_AVAILABLE",
                    "item_id": "item-webhook-test",
                    "initial_update_complete": True,
                    "historical_update_complete": False})
        self.connection.refresh_from_db()
        self.assertTrue(self.connection.historical_update_complete)

    def test_legacy_historical_update_still_supported(self):
        self._post({"webhook_type": "TRANSACTIONS",
                    "webhook_code": "HISTORICAL_UPDATE",
                    "item_id": "item-webhook-test"})
        self.connection.refresh_from_db()
        self.assertTrue(self.connection.initial_update_complete)
        self.assertTrue(self.connection.historical_update_complete)

    def test_unverified_webhook_is_rejected_and_changes_nothing(self):
        """Signature verification is NOT weakened by this fix."""
        response = self.client.post(
            self.url,
            data=json.dumps({"webhook_type": "TRANSACTIONS",
                             "webhook_code": "SYNC_UPDATES_AVAILABLE",
                             "item_id": "item-webhook-test",
                             "historical_update_complete": True}),
            content_type="application/json")
        self.assertEqual(response.status_code, 401)
        self.connection.refresh_from_db()
        self.assertFalse(self.connection.historical_update_complete)
