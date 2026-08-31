# ==============================================================================
# File: apps/finance/tests/test_spending_bridge.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Proves why net spending differs from gross purchases, sign by sign.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Production reports gross purchases 335,318.34 and net spending 341,029.72.

Net being LARGER looks wrong until you know that fees are a cost of consumption and
not a purchase. These tests pin the composition and every sign, and reproduce the exact
production figures, so the relationship is proven rather than asserted.
"""
from decimal import Decimal

from apps.finance.models import Transaction
from apps.finance.services.finance_calc import measures as M
from apps.finance.tests.test_p1_economic_roles import RoleBase


class BridgeArithmeticTests(RoleBase):
    def _bridge(self):
        return M.spending_bridge(M.all_measures(self.user)["net_spending"])

    def test_purchases_alone_make_net_equal_gross(self):
        self._txn(-100, primary="FOOD_AND_DRINK")
        bridge = self._bridge()
        self.assertEqual(bridge["computed_total"], Decimal("100.00"))
        self.assertEqual(bridge["difference_from_gross"], Decimal("0.00"))

    def test_a_fee_raises_net_above_gross(self):
        """The whole point. A fee is spending, and it is not a purchase."""
        self._txn(-100, primary="FOOD_AND_DRINK")
        self._txn(-35, primary="BANK_FEES", detailed="BANK_FEES_OVERDRAFT")
        bridge = self._bridge()
        self.assertEqual(bridge["computed_total"], Decimal("135.00"))
        self.assertEqual(bridge["difference_from_gross"], Decimal("35.00"))

    def test_a_refund_lowers_net_below_gross(self):
        self._txn(-100, primary="GENERAL_MERCHANDISE")
        self._txn(30, primary="GENERAL_MERCHANDISE",
                  detailed="GENERAL_MERCHANDISE_REFUND")
        bridge = self._bridge()
        self.assertEqual(bridge["computed_total"], Decimal("70.00"))
        self.assertEqual(bridge["difference_from_gross"], Decimal("-30.00"))

    def test_every_step_carries_the_sign_it_is_applied_with(self):
        self._txn(-100, primary="FOOD_AND_DRINK")
        self._txn(-35, primary="BANK_FEES")
        self._txn(30, primary="GENERAL_MERCHANDISE",
                  detailed="GENERAL_MERCHANDISE_REFUND")
        signs = {s["key"]: s["sign"] for s in self._bridge()["steps"]}
        self.assertEqual(signs["gross_purchases"], +1)
        self.assertEqual(signs["fees_and_interest"], +1)
        self.assertEqual(signs["refunds"], -1)

    def test_the_running_total_lands_on_the_reported_value(self):
        self._txn(-100, primary="FOOD_AND_DRINK")
        self._txn(-35, primary="BANK_FEES")
        self._txn(30, primary="GENERAL_MERCHANDISE",
                  detailed="GENERAL_MERCHANDISE_REFUND")
        bridge = self._bridge()
        self.assertTrue(bridge["balances"])
        self.assertEqual(bridge["steps"][-1]["running_total"], bridge["reported_total"])

    def test_a_zero_step_is_not_shown_as_noise(self):
        self._txn(-100, primary="FOOD_AND_DRINK")
        keys = {s["key"] for s in self._bridge()["steps"]}
        self.assertEqual(keys, {"gross_purchases"})

    def test_gross_purchases_always_appears_even_at_zero(self):
        """The walk has to start somewhere, even in an empty month."""
        self.assertEqual(self._bridge()["steps"][0]["key"], "gross_purchases")

    def test_the_reconciliation_check_uses_the_same_walk(self):
        """The identity WLJ checks and the walk a person reads cannot drift apart."""
        self._txn(-100, primary="FOOD_AND_DRINK")
        self._txn(-35, primary="BANK_FEES")
        measures = M.all_measures(self.user)
        check = M.reconcile(measures)["checks"]["net_spending_identity"]
        self.assertTrue(check["passed"])
        self.assertEqual(Decimal(check["expected"]),
                         M.spending_bridge(measures["net_spending"])["computed_total"])


class ProductionFiguresTests(RoleBase):
    """Reproduces the exact production relationship in a controlled fixture.

    Any future change to the composition or a sign breaks this, and the failure names
    the real numbers a person can check against their own bank statements.
    """

    PROD_GROSS = Decimal("335318.34")
    PROD_FEES = Decimal("12331.38")
    PROD_REFUNDS = Decimal("6620.00")
    PROD_NET = Decimal("341029.72")

    def test_the_production_identity_holds(self):
        self.assertEqual(self.PROD_GROSS + self.PROD_FEES - self.PROD_REFUNDS,
                         self.PROD_NET)

    def test_the_engine_reproduces_it(self):
        self._txn(-self.PROD_GROSS, primary="GENERAL_MERCHANDISE")
        self._txn(-self.PROD_FEES, primary="BANK_FEES")
        self._txn(self.PROD_REFUNDS, primary="INCOME",
                  detailed="INCOME_TAX_REFUND")
        measures = M.all_measures(self.user)
        self.assertEqual(measures["gross_purchases"].value, self.PROD_GROSS)
        self.assertEqual(measures["net_spending"].value, self.PROD_NET)

    def test_the_excess_is_explained_in_words_not_only_in_numbers(self):
        self._txn(-self.PROD_GROSS, primary="GENERAL_MERCHANDISE")
        self._txn(-self.PROD_FEES, primary="BANK_FEES")
        self._txn(self.PROD_REFUNDS, primary="INCOME",
                  detailed="INCOME_TAX_REFUND")
        assumptions = " ".join(M.all_measures(self.user)["net_spending"].assumptions)
        self.assertIn("EXCEEDS gross purchases", assumptions)
        self.assertIn("are not purchases", assumptions)

    def test_the_gap_is_exactly_fees_less_refunds(self):
        self._txn(-self.PROD_GROSS, primary="GENERAL_MERCHANDISE")
        self._txn(-self.PROD_FEES, primary="BANK_FEES")
        self._txn(self.PROD_REFUNDS, primary="INCOME",
                  detailed="INCOME_TAX_REFUND")
        bridge = M.spending_bridge(M.all_measures(self.user)["net_spending"])
        self.assertEqual(bridge["difference_from_gross"],
                         self.PROD_FEES - self.PROD_REFUNDS)
        self.assertEqual(bridge["difference_from_gross"], Decimal("5711.38"))


class SignDefenceTests(RoleBase):
    """The signs are the part that would fail silently, so they get their own tests."""

    def test_a_fee_can_never_reduce_spending(self):
        self._txn(-100, primary="FOOD_AND_DRINK")
        before = M.all_measures(self.user)["net_spending"].value
        self._txn(-35, primary="BANK_FEES")
        self.assertGreater(M.all_measures(self.user)["net_spending"].value, before)

    def test_a_refund_can_never_increase_spending(self):
        self._txn(-100, primary="GENERAL_MERCHANDISE")
        before = M.all_measures(self.user)["net_spending"].value
        self._txn(30, primary="GENERAL_MERCHANDISE",
                  detailed="GENERAL_MERCHANDISE_REFUND")
        self.assertLess(M.all_measures(self.user)["net_spending"].value, before)

    def test_income_never_reduces_spending(self):
        """Earning money is not un-spending it."""
        self._txn(-100, primary="FOOD_AND_DRINK")
        before = M.all_measures(self.user)["net_spending"].value
        self._txn(5000, primary="INCOME")
        self.assertEqual(M.all_measures(self.user)["net_spending"].value, before)

    def test_a_debt_payment_never_enters_the_walk(self):
        self._txn(-100, primary="FOOD_AND_DRINK")
        self._txn(-1500, primary="LOAN_PAYMENTS",
                  detailed="LOAN_PAYMENTS_MORTGAGE_PAYMENT")
        bridge = M.spending_bridge(M.all_measures(self.user)["net_spending"])
        self.assertEqual(bridge["computed_total"], Decimal("100.00"))


class BridgeIsVisibleTests(RoleBase):
    """A proof nobody can see is not a proof."""

    def setUp(self):
        super().setUp()
        from django.urls import reverse
        self._txn(-100, primary="FOOD_AND_DRINK")
        self._txn(-35, primary="BANK_FEES")
        self._txn(30, primary="GENERAL_MERCHANDISE",
                  detailed="GENERAL_MERCHANDISE_REFUND")
        self.url = reverse("finance:money_overview")

    def test_the_page_renders_the_walk(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="spending-bridge"')
        self.assertContains(response, 'data-step="gross_purchases"')
        self.assertContains(response, 'data-step="fees_and_interest"')
        self.assertContains(response, 'data-step="refunds"')

    def test_it_says_in_words_why_net_is_higher(self):
        response = self.client.get(self.url)
        self.assertContains(response, "not an error")
        self.assertContains(response, "they are not purchases")

    def test_it_shows_the_total_the_walk_lands_on(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="bridge-total"')
        self.assertEqual(response.context["bridge"]["reported_total"],
                         Decimal("105.00"))

    def test_a_walk_that_does_not_balance_is_flagged_not_hidden(self):
        from unittest.mock import patch
        broken = M.spending_bridge(M.all_measures(self.user)["net_spending"])
        broken["balances"] = False
        with patch.object(M, "spending_bridge", return_value=broken):
            response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="bridge-unbalanced"')

    def test_the_page_and_the_service_agree(self):
        response = self.client.get(self.url)
        self.assertEqual(
            response.context["bridge"]["computed_total"],
            M.spending_bridge(M.all_measures(self.user)["net_spending"])["computed_total"])
