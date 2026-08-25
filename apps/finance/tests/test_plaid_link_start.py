# ==============================================================================
# File: apps/finance/tests/test_plaid_link_start.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Plaid Link start path — the 2026-08-25 21:01 UTC failure and its fix.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Starting a bank connection must succeed, or fail in a way the user can act on.

Root cause of the production failure, proven from the log line at 21:01:40 UTC:

    Error creating link token: type object 'Environment' has no attribute 'Development'

`plaid.Environment.Development` was removed in plaid-python 43.x, and the old code
evaluated it while BUILDING the environment dict — so it raised on every call regardless
of which environment was configured. Link could not start in sandbox or production.
"""
from __future__ import annotations

import json
from unittest import mock, skipUnless

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

try:
    import plaid  # noqa: F401
    PLAID_SDK = True
except ImportError:                      # local dev may not have the SDK installed
    PLAID_SDK = False

from apps.finance.services.plaid_service import (
    PlaidEnvironmentError,
    _resolve_plaid_host,
)
from apps.finance.services.provider_diagnostics import safe_provider_diagnostics
from apps.users.models import TermsAcceptance, User

CONFIRM_KEY = "finance_last_activity"


class PlaidEnvironmentResolutionTests(TestCase):
    """The exact defect: resolve by NAME, never by attribute access while building."""

    @skipUnless(PLAID_SDK, "plaid-python not installed in this environment")
    def test_sandbox_and_production_resolve(self):
        self.assertIsNotNone(_resolve_plaid_host("sandbox"))
        self.assertIsNotNone(_resolve_plaid_host("production"))
        self.assertIsNotNone(_resolve_plaid_host("  Production  "))

    def test_retired_development_environment_explains_itself(self):
        with self.assertRaises(PlaidEnvironmentError) as ctx:
            _resolve_plaid_host("development")
        self.assertIn("retired", str(ctx.exception))

    def test_unknown_environment_is_rejected_clearly(self):
        with self.assertRaises(PlaidEnvironmentError):
            _resolve_plaid_host("staging")

    @skipUnless(PLAID_SDK, "plaid-python not installed in this environment")
    def test_resolution_never_touches_a_missing_sdk_attribute(self):
        """A future SDK removal must surface as configuration advice, not AttributeError."""
        import plaid

        class Shrunk:
            Sandbox = "https://sandbox.plaid.com"

        with mock.patch.object(plaid, "Environment", Shrunk):
            self.assertEqual(_resolve_plaid_host("sandbox"),
                             "https://sandbox.plaid.com")
            with self.assertRaises(PlaidEnvironmentError) as ctx:
                _resolve_plaid_host("production")
            self.assertIn("does not provide", str(ctx.exception))

    def test_no_code_accesses_a_retired_sdk_environment_attribute(self):
        """Regression guard for the precise shape of the bug.

        AST-based: the comment above the fix explains the defect and necessarily names
        it, but no EXECUTABLE attribute access may reach a retired environment.
        """
        import ast

        from apps.finance.services import plaid_service
        tree = ast.parse(open(plaid_service.__file__).read())
        offenders = [
            node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "Development"
        ]
        self.assertEqual(offenders, [],
                         f"retired SDK environment accessed at line(s) {offenders}")


class _FakePlaidService:
    def __init__(self, *, token="link-sandbox-REDACTED", error=None):
        self.token = token
        self.error = error

    def create_link_token(self, user, request=None):
        if self.error:
            raise self.error
        return {"link_token": self.token, "expiration": "2026-08-26T00:00:00Z"}


class _PlaidApiError(Exception):
    def __init__(self):
        super().__init__("provider failure")
        self.error_type = "INVALID_REQUEST"
        self.error_code = "INVALID_FIELD"
        self.request_id = "req-abc123"
        self.status = 400
        self.body = json.dumps({
            "error_type": "INVALID_REQUEST",
            "error_code": "INVALID_FIELD",
            "request_id": "req-abc123",
            "display_message": "Your balance is $4,214.11",
            "access_token": "access-production-SUPERSECRET",
        })


@override_settings(PLAID_CLIENT_ID="cid", PLAID_SECRET="sec", PLAID_ENV="sandbox")
class LinkTokenStartTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = self._user("link@example.com", finance=True)
        self.client.login(email="link@example.com", password="testpass123")
        self.url = reverse("finance:connection_start")
        self._confirm_recent_auth()

    def _user(self, email, *, finance):
        user = User.objects.create_user(email=email, password="testpass123")
        TermsAcceptance.objects.create(
            user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        prefs = user.preferences
        prefs.has_completed_onboarding = True
        prefs.finances_enabled = finance
        prefs.save()
        return user

    def _confirm_recent_auth(self):
        session = self.client.session
        session[CONFIRM_KEY] = timezone.now().isoformat()
        session.save()

    def _patch(self, service):
        return mock.patch("apps.finance.services.plaid_service.get_plaid_service",
                          return_value=service)

    # -- success ---------------------------------------------------------
    def test_successful_link_token_creation(self):
        with self._patch(_FakePlaidService()):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["link_token"])

    # -- expired recent authentication ------------------------------------
    def test_expired_recent_auth_returns_a_usable_path(self):
        session = self.client.session
        session[CONFIRM_KEY] = (timezone.now() - timezone.timedelta(hours=2)).isoformat()
        session.save()
        with self._patch(_FakePlaidService()):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertTrue(body["require_reauth"])
        self.assertEqual(body["reauth_url"], reverse("users:confirm_password"))
        self.assertIn("password", body["error"].lower())
        # And it remembers where to bring the user back to.
        self.assertTrue(
            self.client.session["finance_return_url"].startswith("/finance/"))

    def test_confirming_the_password_restores_access(self):
        session = self.client.session
        session[CONFIRM_KEY] = (timezone.now() - timezone.timedelta(hours=2)).isoformat()
        session.save()
        with self._patch(_FakePlaidService()):
            self.assertEqual(self.client.get(self.url).status_code, 403)
        response = self.client.post(reverse("users:confirm_password"),
                                    {"password": "testpass123"})
        self.assertIn(response.status_code, (302, 200))
        with self._patch(_FakePlaidService()):
            self.assertEqual(self.client.get(self.url).status_code, 200)

    # -- access denial ----------------------------------------------------
    def test_finance_disabled_user_is_denied(self):
        self._user("nofinance@example.com", finance=False)
        self.client.logout()
        self.client.login(email="nofinance@example.com", password="testpass123")
        # Mirrors the real client, which asks for JSON.
        response = self.client.get(self.url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_anonymous_is_not_served(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (301, 302, 401, 403))

    # -- rate limiting ----------------------------------------------------
    def test_rate_limit_stops_a_burst_with_a_retry_hint(self):
        with self._patch(_FakePlaidService()):
            for _ in range(5):
                self.assertEqual(self.client.get(self.url).status_code, 200)
            blocked = self.client.get(self.url)
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("retry_after", blocked.json())

    # -- safe provider failure --------------------------------------------
    def test_provider_failure_is_a_502_with_safe_diagnostics_only(self):
        with self._patch(_FakePlaidService(error=_PlaidApiError())):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertTrue(body["retryable"])
        self.assertEqual(body["provider"]["error_code"], "INVALID_FIELD")
        self.assertEqual(body["provider"]["request_id"], "req-abc123")
        blob = json.dumps(body)
        self.assertNotIn("SUPERSECRET", blob)
        self.assertNotIn("4,214.11", blob)

    def test_misconfigured_environment_says_retrying_will_not_help(self):
        error = PlaidEnvironmentError("PLAID_ENV='development' refers to ... retired")
        with self._patch(_FakePlaidService(error=error)):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertFalse(body["retryable"])
        self.assertIn("contact support", body["error"].lower())

    def test_the_original_production_defect_now_surfaces_honestly(self):
        """The literal 21:01 UTC exception, replayed."""
        error = AttributeError("type object 'Environment' has no attribute 'Development'")
        with self._patch(_FakePlaidService(error=error)):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 502)
        blob = json.dumps(response.json())
        self.assertNotIn("Environment", blob,
                         "raw exception text must not reach the user")


class ProviderDiagnosticsRedactionTests(TestCase):

    def test_only_safe_fields_survive(self):
        diagnostics = safe_provider_diagnostics(_PlaidApiError())
        self.assertEqual(diagnostics["error_type"], "INVALID_REQUEST")
        self.assertEqual(diagnostics["error_code"], "INVALID_FIELD")
        self.assertEqual(diagnostics["request_id"], "req-abc123")
        self.assertEqual(diagnostics["status"], 400)
        blob = json.dumps(diagnostics)
        for secret in ("SUPERSECRET", "access-production", "4,214.11", "display_message"):
            self.assertNotIn(secret, blob)

    def test_free_text_values_are_dropped_not_truncated(self):
        class Chatty(Exception):
            error_code = "Your account ending 4242 was declined"
        self.assertNotIn("error_code", safe_provider_diagnostics(Chatty()))

    def test_a_bare_exception_still_yields_something_useful(self):
        diagnostics = safe_provider_diagnostics(ValueError("boom"))
        self.assertEqual(diagnostics["exception"], "ValueError")
        self.assertNotIn("boom", json.dumps(diagnostics))


class ConnectButtonRecoveryTests(TestCase):
    """Every failure must hand the button back — the 'stuck on Connecting…' symptom."""

    TEMPLATE = "templates/finance/bank_connection_list.html"

    def setUp(self):
        self.source = open(self.TEMPLATE).read()

    def test_no_blocking_alerts_remain(self):
        self.assertNotIn("alert(", self.source,
                         "alert() blocks the page and reads as a frozen button")

    def test_button_reset_is_centralised_and_used_on_every_exit(self):
        self.assertIn("function resetConnectButton()", self.source)
        self.assertGreaterEqual(self.source.count("resetConnectButton()"), 4)

    def test_reauth_response_redirects_to_the_real_flow(self):
        self.assertIn("require_reauth", self.source)
        self.assertIn("reauth_url", self.source)
        self.assertIn("window.location.assign", self.source)

    def test_status_region_is_accessible(self):
        self.assertIn('aria-live', self.source)
        self.assertIn("role', 'status'", self.source.replace('"', "'"))

    def test_unparseable_response_still_shows_a_message(self):
        self.assertIn("catch (parseError)", self.source)
