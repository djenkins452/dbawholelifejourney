# ==============================================================================
# File: apps/finance/tests/test_money_pages_complete.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P10 completion — budgets, net worth and data health as real pages.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Every capability has to be reachable by an ordinary user, not only by the assistant.

And every empty state has to say what to do next: a page that shows $0.00 and stops is
indistinguishable from a broken one.
"""
from datetime import date
from decimal import Decimal

from django.urls import reverse

from apps.finance.models import (CashReserve, FinancialAccount, FinancialGoal,
                                 NetWorthSnapshot, RecurringSeries, TangibleAsset)
from apps.finance.tests.test_p1_economic_roles import RoleBase


class BudgetPageTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("finance:money_budget")

    def test_with_nothing_confirmed_it_shows_setup_not_a_fake_forecast(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="forecast-setup"')
        self.assertContains(response, "looks exactly like a real one")

    def test_the_setup_steps_link_to_the_page_that_supplies_them(self):
        response = self.client.get(self.url)
        self.assertContains(response, reverse("finance:money_review"))

    def test_the_real_balance_is_still_shown(self):
        response = self.client.get(self.url)
        self.assertContains(response, "3,000.00")

    def test_confirming_income_makes_it_project(self):
        RecurringSeries.objects.create(
            user=self.user, name="Salary", payee="salary",
            kind=RecurringSeries.KIND_INCOME, amount_expected=Decimal("4000"),
            review_state=RecurringSeries.REVIEW_CONFIRMED)
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="forecast-figures"')
        self.assertContains(response, 'data-testid="free-cash"')

    def test_no_reserves_says_free_cash_has_no_floor(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="no-reserves"')
        self.assertContains(response, "absent decision")

    def test_a_reserve_can_be_created(self):
        self.client.post(reverse("finance:money_save_reserve"), {
            "name": "Emergency fund", "kind": CashReserve.KIND_RESERVE,
            "target_amount": "6000"})
        reserve = CashReserve.objects.get(user=self.user)
        self.assertEqual(reserve.target_amount, Decimal("6000"))

    def test_a_blank_target_stays_unknown_rather_than_zero(self):
        self.client.post(reverse("finance:money_save_reserve"),
                         {"name": "Someday", "kind": CashReserve.KIND_SINKING,
                          "target_amount": ""})
        self.assertIsNone(CashReserve.objects.get(user=self.user).target_amount)

    def test_a_reserve_can_link_an_existing_goal_rather_than_restating_it(self):
        goal = FinancialGoal.objects.create(
            user=self.user, name="Emergency Fund",
            goal_type=FinancialGoal.GOAL_TYPE_EMERGENCY,
            target_amount=Decimal("1000"), linked_account=self.savings)
        self.client.post(reverse("finance:money_save_reserve"), {
            "name": "Emergency", "kind": CashReserve.KIND_RESERVE,
            "target_amount": "1000", "goal": str(goal.pk)})
        reserve = CashReserve.objects.get(user=self.user)
        self.assertEqual(reserve.goal_id, goal.pk)
        self.assertEqual(reserve.effective_balance, Decimal("2000"))

    def test_a_nameless_reserve_is_refused(self):
        self.client.post(reverse("finance:money_save_reserve"), {"name": ""})
        self.assertEqual(CashReserve.objects.count(), 0)

    def test_archiving_stops_it_affecting_free_cash(self):
        self.client.post(reverse("finance:money_save_reserve"),
                         {"name": "Emergency", "kind": CashReserve.KIND_RESERVE,
                          "target_amount": "6000"})
        reserve = CashReserve.objects.get(user=self.user)
        self.client.post(reverse("finance:money_archive_reserve", args=[reserve.pk]))
        reserve.refresh_from_db()
        self.assertEqual(reserve.status, "archived")

    def test_one_user_cannot_archive_anothers_reserve(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="b2@example.com", password="pw"))
        reserve = CashReserve.objects.create(
            user=other, name="Theirs", kind=CashReserve.KIND_RESERVE)
        response = self.client.post(
            reverse("finance:money_archive_reserve", args=[reserve.pk]))
        self.assertEqual(response.status_code, 404)

    def test_a_reserve_cannot_link_another_users_goal(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="b3@example.com", password="pw"))
        goal = FinancialGoal.objects.create(
            user=other, name="Theirs", target_amount=Decimal("100"))
        self.client.post(reverse("finance:money_save_reserve"), {
            "name": "Mine", "kind": CashReserve.KIND_RESERVE,
            "goal": str(goal.pk)})
        self.assertIsNone(CashReserve.objects.get(user=self.user).goal_id)

    def test_an_unsupported_horizon_falls_back_rather_than_breaking(self):
        response = self.client.get(self.url, {"horizon": "9999"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["horizon"], 30)


class NetWorthPageTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("finance:money_networth")

    def test_the_position_is_shown(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="net-worth"')

    def test_an_unvalued_asset_is_reported_as_understating(self):
        TangibleAsset.objects.create(user=self.user, name="House",
                                     asset_type="real_estate")
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="nw-gaps"')
        self.assertContains(response, "understated")

    def test_equity_is_shown_but_the_rule_is_stated(self):
        from apps.finance.models import AssetLoanLink, AssetValuation
        asset = TangibleAsset.objects.create(
            user=self.user, name="House", asset_type="real_estate")
        AssetValuation.objects.create(
            user=self.user, asset=asset, amount=Decimal("400000"),
            effective_date=date(2026, 8, 1), source="user")
        mortgage = FinancialAccount.objects.create(
            user=self.user, name="Mortgage", account_type="mortgage",
            current_balance=Decimal("-250000"))
        AssetLoanLink.objects.create(user=self.user, asset=asset, account=mortgage)
        response = self.client.get(self.url)
        self.assertContains(response, "never")
        self.assertContains(response, "largest debt")

    def test_no_history_explains_rather_than_drawing_a_line(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="no-history"')
        self.assertContains(response, "fiction")

    def test_a_snapshot_can_be_taken_from_the_page(self):
        self.client.post(reverse("finance:money_take_snapshot"))
        self.assertEqual(NetWorthSnapshot.objects.filter(user=self.user).count(), 1)

    def test_taking_it_twice_in_a_day_does_not_duplicate(self):
        self.client.post(reverse("finance:money_take_snapshot"))
        self.client.post(reverse("finance:money_take_snapshot"))
        self.assertEqual(NetWorthSnapshot.objects.filter(user=self.user).count(), 1)

    def test_the_page_never_shows_a_vin_or_an_address(self):
        TangibleAsset.objects.create(
            user=self.user, name="Truck", asset_type="vehicle",
            vin="1FTFW1ET5DFA12345", street_address="12 Elm Street")
        body = self.client.get(self.url).content.decode()
        self.assertNotIn("1FTFW1ET5DFA12345", body)
        self.assertNotIn("Elm Street", body)

    def test_an_empty_registry_offers_the_next_action(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="no-assets"')
        self.assertContains(response, reverse("finance:asset_create"))


class DataHealthPageTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("finance:money_health")

    def test_issues_are_listed_with_somewhere_to_go(self):
        self._txn(-50, primary="FOOD_AND_DRINK")
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="health-issue"')
        self.assertContains(response, "Fix this")

    def test_a_clean_account_says_so(self):
        """Genuinely clean: no transactions AND no untermed liabilities.

        The base fixture's credit card counts as a debt with no recorded terms, which
        the health check is right to flag — so it has to go for this to be clean.
        """
        from apps.finance.models import Transaction
        Transaction.objects.all().delete()
        FinancialAccount.objects.filter(
            user=self.user,
            account_type__in=FinancialAccount.LIABILITY_TYPES).delete()
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="dh-healthy"')

    def test_a_liability_with_no_terms_is_flagged_even_with_no_transactions(self):
        """The base fixture's card. An untermed debt is a real gap on its own."""
        from apps.finance.models import Transaction
        Transaction.objects.all().delete()
        response = self.client.get(self.url)
        self.assertContains(response, 'data-code="loan_terms_missing"')

    def test_it_never_claims_a_figure_is_wrong(self):
        self._txn(-50, primary="FOOD_AND_DRINK")
        response = self.client.get(self.url)
        self.assertContains(response, "does not tell you a figure is wrong")

    def test_a_route_that_cannot_be_reversed_does_not_break_the_page(self):
        from unittest.mock import patch
        from apps.finance.services.finance_calc import data_health as DH
        broken = {"as_of": "2026-08-31", "healthy": False,
                  "counts": {"high": 1, "medium": 0, "low": 0},
                  "issues": [{"code": "x", "severity": "high", "title": "t",
                              "detail": "d", "count": 1, "amount": "0.00",
                              "route": "finance:no_such_route_at_all"}],
                  "version": "1.0.0"}
        with patch.object(DH, "evaluate", return_value=broken):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)


class ResponsiveTests(RoleBase):
    PAGES = ("finance:money_budget", "finance:money_networth", "finance:money_health")

    def test_no_page_uses_an_inline_handler(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                for handler in ("onclick=", "onchange=", "onsubmit="):
                    self.assertNotIn(handler, body)

    def test_touch_targets_and_input_sizing_are_declared(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                self.assertIn("min-height: 44px", body)

    def test_each_page_requires_a_signed_in_owner(self):
        self.client.logout()
        for name in self.PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertIn(response.status_code, (301, 302, 403))
