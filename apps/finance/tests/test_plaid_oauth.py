# ==============================================================================
# File: apps/finance/tests/test_plaid_oauth.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Plaid OAuth redirect-and-resume — binding, replay, expiry, isolation.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""An OAuth flow hands the browser to a bank and takes it back. Trust nothing on return.

Every test here is deterministic and synthetic: no Plaid call, no bank, no Link opened.
"""
from __future__ import annotations

import json
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.finance.models import BankConnection
from apps.finance.services import plaid_oauth
from apps.users.models import TermsAcceptance, User

REDIRECT_URI = "https://wholelifejourney.com/finance/plaid/oauth/"
FAKE_TOKEN = "link-production-FAKE-FOR-TESTS"


class _FakePlaid:
    def __init__(self, *, token=FAKE_TOKEN):
        self.token = token

    def create_link_token(self, user, request=None):
        return {"link_token": self.token, "expiration": "2026-08-26T12:00:00Z"}

    def exchange_public_token(self, public_token):
        return {"access_token": "access-production-FAKE", "item_id": "item-fake-1"}


@override_settings(PLAID_CLIENT_ID="cid", PLAID_SECRET="sec", PLAID_ENV="production",
                   PLAID_REDIRECT_URI=REDIRECT_URI)
class OAuthFlowBase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = self._user("oauth@example.com")
        self.other = self._user("oauth-other@example.com")
        self.client.login(email="oauth@example.com", password="testpass123")
        self._confirm_password()

    def _user(self, email, *, finance=True):
        user = User.objects.create_user(email=email, password="testpass123")
        TermsAcceptance.objects.create(
            user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        prefs = user.preferences
        prefs.has_completed_onboarding = True
        prefs.finances_enabled = finance
        prefs.save()
        return user

    def _confirm_password(self):
        session = self.client.session
        session["finance_last_activity"] = timezone.now().isoformat()
        session.save()

    def _patch(self, service=None):
        return mock.patch("apps.finance.services.plaid_service.get_plaid_service",
                          return_value=service or _FakePlaid())

    def _start(self):
        with self._patch():
            return self.client.get(reverse("finance:connection_start"),
                                   HTTP_ACCEPT="application/json")

    def _set_attempt(self, **overrides):
        session = self.client.session
        attempt = {
            "state_id": "state-1",
            "link_token": FAKE_TOKEN,
            "user_id": self.user.id,
            "started_at": timezone.now().isoformat(),
            "consumed": False,
        }
        attempt.update(overrides)
        session[plaid_oauth.SESSION_KEY] = attempt
        session.save()
        return attempt


class InitialLaunchTests(OAuthFlowBase):

    def test_link_start_binds_an_oauth_attempt(self):
        response = self._start()
        self.assertEqual(response.status_code, 200)
        attempt = self.client.session.get(plaid_oauth.SESSION_KEY)
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt["user_id"], self.user.id)
        self.assertFalse(attempt["consumed"])
        self.assertTrue(attempt["state_id"])

    @override_settings(PLAID_REDIRECT_URI="")
    def test_no_attempt_is_bound_when_oauth_is_not_configured(self):
        self._start()
        self.assertIsNone(self.client.session.get(plaid_oauth.SESSION_KEY))

    def test_the_token_never_reaches_a_log_or_a_url(self):
        import inspect
        source = inspect.getsource(plaid_oauth)
        self.assertNotIn("logger.info(\"...%s\", attempt", source)
        for line in source.splitlines():
            if "logger." in line:
                self.assertNotIn("link_token", line)
                self.assertNotIn("token)", line)


class OAuthReturnTests(OAuthFlowBase):

    def _return(self):
        return self.client.get(
            reverse("finance:plaid_oauth_return") + "?oauth_state_id=abc123")

    def test_valid_return_resumes_link_with_the_same_token(self):
        self._start()
        response = self._return()
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("receivedRedirectUri", body)
        self.assertIn("window.location.href", body)
        self.assertIn("Plaid.create", body)
        # The SAME token is handed to the page. It is `escapejs`-encoded in the markup
        # (Django escapes `-` as \u002D), so assert on the context rather than a
        # literal substring — the encoding is correct JS, not a missing value.
        self.assertEqual(response.context["link_token"], FAKE_TOKEN)

    def test_the_token_is_escaped_and_never_put_in_browser_storage(self):
        self._start()
        body = self._return().content.decode()
        self.assertIn("\\u002D", body, "the token must be JS-escaped in the page")

        # Scope to OUR <script> element: base.html legitimately uses localStorage for
        # the theme, and a character window would sweep that in.
        marker = body.index("receivedRedirectUri")
        block = body[body.rindex("<script", 0, marker):
                     body.index("</script>", marker)]
        # Assert on USAGE, not the word — the code comment above the token explains
        # that browser storage is never used, and prose is not behaviour.
        for forbidden in ("localStorage.setItem", "localStorage[",
                          "sessionStorage.setItem", "sessionStorage[",
                          "document.cookie ="):
            self.assertNotIn(forbidden, block)

    def test_return_page_is_accessible_and_offers_a_way_back(self):
        self._start()
        body = self._return().content.decode()
        self.assertIn('aria-live="polite"', body)
        self.assertIn('role="status"', body)
        self.assertIn(reverse("finance:connection_list"), body)

    def test_missing_state_is_refused_without_a_token(self):
        response = self._return()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["link_token"], "")
        self.assertIn("start again", response.content.decode().lower())

    def test_expired_attempt_is_refused_and_cleared(self):
        self._set_attempt(started_at=(
            timezone.now() - timedelta(minutes=plaid_oauth.ATTEMPT_TTL_MINUTES + 5)
        ).isoformat())
        response = self._return()
        self.assertEqual(response.context["link_token"], "")
        self.assertIn("timed out", response.content.decode().lower())
        self.assertIsNone(self.client.session.get(plaid_oauth.SESSION_KEY))

    def test_replayed_attempt_is_refused(self):
        self._set_attempt(consumed=True)
        response = self._return()
        self.assertEqual(response.context["link_token"], "")
        self.assertIn("already been used", response.content.decode().lower())

    def test_another_users_state_is_refused_and_destroyed(self):
        """The strongest binding: a session holding someone else's attempt gets nothing."""
        self._set_attempt(user_id=self.other.id)
        response = self._return()
        self.assertEqual(response.context["link_token"], "")
        self.assertIn("different account", response.content.decode().lower())
        self.assertIsNone(self.client.session.get(plaid_oauth.SESSION_KEY),
                          "a rejected state must not survive to be retried")

    def test_anonymous_visitors_are_not_served(self):
        self.client.logout()
        response = self._return()
        self.assertIn(response.status_code, (301, 302))

    def test_finance_disabled_user_is_refused(self):
        self._user("nofin@example.com", finance=False)
        self.client.logout()
        self.client.login(email="nofin@example.com", password="testpass123")
        self.assertEqual(self._return().status_code, 403)

    def test_no_open_redirect_is_possible(self):
        """The return path is derived from the URLconf, never from the request."""
        self._start()
        response = self.client.get(
            reverse("finance:plaid_oauth_return") + "?next=https://evil.example.com/")
        body = response.content.decode()
        self.assertNotIn("evil.example.com", body)
        self.assertIn(reverse("finance:connection_list"), body)


class ReauthLoopTests(OAuthFlowBase):
    """A bank login that takes longer than 15 minutes must not strand the user."""

    def test_a_live_attempt_satisfies_the_recency_control(self):
        self._start()
        session = self.client.session
        session["finance_last_activity"] = (
            timezone.now() - timedelta(hours=3)).isoformat()
        session.save()

        with self._patch():
            response = self.client.post(
                reverse("finance:connection_complete"),
                data=json.dumps({"public_token": "public-fake",
                                 "metadata": {"institution": {"name": "Test Bank"}}}),
                content_type="application/json")
        self.assertNotEqual(response.status_code, 403,
                            "a long bank login must not become an unsatisfiable loop")

    def test_without_a_live_attempt_the_control_still_bites(self):
        session = self.client.session
        session["finance_last_activity"] = (
            timezone.now() - timedelta(hours=3)).isoformat()
        session.save()
        with self._patch():
            response = self.client.get(reverse("finance:connection_start"),
                                       HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json()["require_reauth"])


class CompletionTests(OAuthFlowBase):

    def test_successful_exchange_consumes_and_clears_the_attempt(self):
        self._start()
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=self._key()):
            with self._patch():
                response = self.client.post(
                    reverse("finance:connection_complete"),
                    data=json.dumps({"public_token": "public-fake",
                                     "metadata": {"institution": {"name": "Test Bank"}}}),
                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get(plaid_oauth.SESSION_KEY))
        self.assertEqual(BankConnection.objects.filter(user=self.user).count(), 1)

    def test_a_replayed_completion_cannot_reuse_the_state(self):
        self._start()
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=self._key()):
            with self._patch():
                self.client.post(
                    reverse("finance:connection_complete"),
                    data=json.dumps({"public_token": "public-fake",
                                     "metadata": {"institution": {"name": "Test Bank"}}}),
                    content_type="application/json")
        self.assertIsNone(self.client.session.get(plaid_oauth.SESSION_KEY))
        with self.assertRaises(plaid_oauth.OAuthStateError):
            request = mock.Mock()
            request.session = self.client.session
            request.user = self.user
            plaid_oauth.resolve(request)

    def test_abandoning_drops_the_attempt_and_connects_nothing(self):
        self._start()
        response = self.client.post(reverse("finance:plaid_oauth_abandon"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get(plaid_oauth.SESSION_KEY))
        self.assertEqual(BankConnection.objects.count(), 0)

    @staticmethod
    def _key():
        from apps.finance.services.encryption import generate_encryption_key
        return generate_encryption_key()


class RedirectUriConfigCheckTests(TestCase):
    """A misconfigured redirect URI must fail the DEPLOY, not the user."""

    def _ids(self, uri):
        from apps.finance.checks import plaid_redirect_uri_check
        with override_settings(PLAID_REDIRECT_URI=uri):
            return [e.id for e in plaid_redirect_uri_check(None)]

    def test_unset_is_valid(self):
        self.assertEqual(self._ids(""), [])

    def test_the_canonical_uri_passes(self):
        self.assertEqual(self._ids(REDIRECT_URI), [])

    def test_non_https_is_rejected(self):
        self.assertIn("finance.E003",
                      self._ids("http://wholelifejourney.com/finance/plaid/oauth/"))

    def test_foreign_origin_is_rejected(self):
        self.assertIn("finance.E004",
                      self._ids("https://evil.example.com/finance/plaid/oauth/"))

    def test_an_unrouted_path_is_rejected(self):
        self.assertIn("finance.E005",
                      self._ids("https://wholelifejourney.com/finance/plaid/nope/"))

    def test_the_canonical_path_is_actually_routed(self):
        from django.urls import resolve
        match = resolve("/finance/plaid/oauth/")
        self.assertEqual(match.view_name, "finance:plaid_oauth_return")
