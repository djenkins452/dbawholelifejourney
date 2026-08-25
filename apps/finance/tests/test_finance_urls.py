# ==============================================================================
# File: apps/finance/tests/test_finance_urls.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F-1 — the retired legacy Finance AI routes stay retired.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The four legacy Finance AI endpoints are gone, and the real Finance surface is not.

They had ZERO callers (no template, JS, test, or Python import outside their own views) —
their only effect was an unreviewed request-path provider call from a domain-local
reasoning service. This test keeps them gone AND proves the retirement did not take any
live Finance route with it.
"""
from __future__ import annotations

from django.test import SimpleTestCase, TestCase
from django.urls import NoReverseMatch, resolve, reverse
from django.urls.exceptions import Resolver404

RETIRED_ROUTE_NAMES = (
    "finance:api_spending_insight",
    "finance:api_subscription_review",
    "finance:api_budget_alert",
    "finance:api_goal_encouragement",
)

RETIRED_PATHS = (
    "/finance/api/insights/spending/",
    "/finance/api/insights/subscriptions/",
    "/finance/api/insights/budget/1/",
    "/finance/api/insights/goal/1/",
)

# The live Finance surface F-1 must not disturb — pages, JSON APIs, and Plaid.
PRESERVED_ROUTE_NAMES = (
    "finance:dashboard",
    "finance:api_payees",
    "finance:api_account_balance",
    "finance:connection_list",
    "finance:connection_start",
    "finance:connection_complete",
    "finance:plaid_webhook",
)


class RetiredLegacyAIRoutesTests(SimpleTestCase):

    def test_legacy_ai_route_names_are_unreversible(self):
        for name in RETIRED_ROUTE_NAMES:
            with self.subTest(route=name):
                with self.assertRaises(NoReverseMatch):
                    reverse(name)

    def test_legacy_ai_paths_do_not_resolve(self):
        for path in RETIRED_PATHS:
            with self.subTest(path=path):
                with self.assertRaises(Resolver404):
                    resolve(path)


class PreservedFinanceRoutesTests(SimpleTestCase):

    def test_live_finance_routes_still_resolve(self):
        for name in PRESERVED_ROUTE_NAMES:
            with self.subTest(route=name):
                try:
                    reverse(name)
                except NoReverseMatch:
                    # pk-carrying routes still prove registration with an argument.
                    reverse(name, args=[1])


class FinancePageSmokeTests(TestCase):
    """The Finance pages still render after the retirement (nothing broke)."""

    def setUp(self):
        from django.conf import settings

        from apps.users.models import TermsAcceptance, User

        self.user = User.objects.create_user(
            email="finance-smoke@example.com", password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        prefs = self.user.preferences
        prefs.has_completed_onboarding = True
        prefs.finances_enabled = True
        prefs.save()
        self.client.login(email="finance-smoke@example.com", password="testpass123")

    def test_finance_pages_render(self):
        for name in ("finance:dashboard", "finance:account_list",
                     "finance:transaction_list", "finance:budget_list",
                     "finance:goal_list", "finance:recurring_list",
                     "finance:connection_list"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(
                    response.status_code, 200,
                    f"{name} returned {response.status_code} after F-1",
                )
