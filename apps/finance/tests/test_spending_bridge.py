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


class SixMeaningsTests(RoleBase):
    """One movement has several true descriptions. Each one gets its own name.

    A single card payment is two account movements, one household movement, zero
    spending, a real cash reduction, a real debt reduction, and zero change in net
    worth. Collapsing any two of those is what produced a transfer total roughly double
    what it should be and a cash figure that was neither of the things it might mean.
    """

    def setUp(self):
        super().setUp()
        from apps.finance.services import transfer_detection as TD
        from apps.finance.services.finance_calc import backfill

        # A card purchase, then the payment that settles it.
        self._txn(-1500, account=self.card, primary="GENERAL_MERCHANDISE")
        self.credit = self._txn(1500, account=self.card, primary="TRANSFER_IN",
                                detailed="TRANSFER_IN_ACCOUNT_TRANSFER")
        self.payment = self._txn(-1500, primary="LOAN_PAYMENTS",
                                 detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        TD.pair_all(self.user)
        backfill.run(self.user, commit=True)
        self.m = M.all_measures(self.user)

    def test_1_the_purchase_is_spending_exactly_once(self):
        self.assertEqual(self.m["gross_purchases"].value, Decimal("1500.00"))
        self.assertEqual(self.m["net_spending"].value, Decimal("1500.00"))

    def test_2_the_payment_is_a_real_reduction_in_liquid_cash(self):
        self.assertEqual(self.m["cash_outflow"].value, Decimal("1500.00"))
        self.assertEqual(
            self.m["cash_outflow"].components[Transaction.ROLE_CARD_PAYMENT],
            Decimal("1500.00"))

    def test_2b_the_card_purchase_is_NOT_liquid_cash(self):
        """Buying on a card moves no cash on the day it happens."""
        self.assertNotIn(Transaction.ROLE_PURCHASE,
                         self.m["cash_outflow"].components)

    def test_3_the_household_transfer_is_counted_once_not_twice(self):
        self.assertEqual(
            self.m["transfers_and_allocations"].components["card_payments"],
            Decimal("1500.00"), "two legs, one movement")

    def test_4_economic_outflow_holds_the_purchase_not_the_payment(self):
        self.assertEqual(self.m["economic_outflow"].components["purchases"],
                         Decimal("1500.00"))
        self.assertNotIn("card_payment", self.m["economic_outflow"].components)

    def test_5_both_account_movements_are_still_present(self):
        """Account-level truth keeps both legs — that is what ties to a statement."""
        legs = Transaction.objects.filter(
            user=self.user, economic_role=Transaction.ROLE_CARD_PAYMENT)
        self.assertEqual(legs.count(), 2)

    def test_6_net_cash_movement_reflects_the_payment(self):
        check = M.reconcile(self.m)["checks"]["net_cash_movement"]
        self.assertEqual(Decimal(check["actual"]), Decimal("-1500.00"))

    def test_the_payment_never_becomes_spending(self):
        """The purchase it settles was counted when it happened."""
        self.assertEqual(self.m["net_spending"].value, Decimal("1500.00"))

    def test_every_identity_still_holds(self):
        self.assertTrue(M.reconcile(self.m)["all_hold"])


class MortgageSemanticsTests(RoleBase):
    """A mortgage payment is cash out, debt service, and mostly not an expense."""

    def setUp(self):
        super().setUp()
        from apps.finance.models import FinancialAccount
        from apps.finance.services import transfer_detection as TD
        from apps.finance.services.finance_calc import backfill

        self.mortgage = FinancialAccount.objects.create(
            user=self.user, name="Mortgage", account_type="mortgage",
            current_balance=Decimal("-200000"))
        self._txn(2000, account=self.mortgage, primary="TRANSFER_IN",
                  detailed="TRANSFER_IN_ACCOUNT_TRANSFER")
        self._txn(-2000, primary="LOAN_PAYMENTS",
                  detailed="LOAN_PAYMENTS_MORTGAGE_PAYMENT")
        TD.pair_all(self.user)
        backfill.run(self.user, commit=True)
        self.m = M.all_measures(self.user)

    def test_the_cash_outflow_stays_visible_for_liquidity(self):
        self.assertEqual(self.m["cash_outflow"].value, Decimal("2000.00"))

    def test_it_remains_debt_service_counted_once(self):
        self.assertEqual(self.m["debt_service"].value, Decimal("2000.00"))

    def test_it_is_not_consumer_spending(self):
        self.assertEqual(self.m["net_spending"].value, Decimal("0.00"))

    def test_the_unsplit_payment_says_it_is_unsplit(self):
        debt = self.m["debt_service"]
        self.assertEqual(debt.components["unsplit"], Decimal("2000.00"))
        self.assertEqual(debt.components["principal_known"], Decimal("0.00"))
        self.assertIn("loan_terms", debt.inputs_missing)

    def test_identities_hold(self):
        self.assertTrue(M.reconcile(self.m)["all_hold"])


class MoneyBridgeTests(RoleBase):
    """Six views, and the sentence that stops a person concluding one is broken."""

    def setUp(self):
        super().setUp()
        from apps.finance.services import transfer_detection as TD
        from apps.finance.services.finance_calc import backfill
        self._txn(-1500, account=self.card, primary="GENERAL_MERCHANDISE")
        self._txn(1500, account=self.card, primary="TRANSFER_IN",
                  detailed="TRANSFER_IN_ACCOUNT_TRANSFER")
        self._txn(-1500, primary="LOAN_PAYMENTS",
                  detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        self._txn(4000, primary="INCOME")
        TD.pair_all(self.user)
        backfill.run(self.user, commit=True)
        self.bridge = M.money_bridge(self.user)

    def test_all_six_views_are_present(self):
        keys = {v["key"] for v in self.bridge["views"]}
        self.assertEqual(keys, {"net_spending", "debt_service",
                                "transfers_and_allocations", "cash_outflow",
                                "cash_inflow", "economic_outflow"})

    def test_every_view_says_what_it_means(self):
        for view in self.bridge["views"]:
            with self.subTest(view=view["key"]):
                self.assertTrue(view["means"])

    def test_it_reports_the_change_in_liquid_cash(self):
        self.assertEqual(self.bridge["net_liquid_cash_change"], Decimal("2500.00"))

    def test_it_reports_the_debt_reduced_once_not_twice(self):
        self.assertEqual(self.bridge["liability_reduction"], Decimal("1500.00"))

    def test_paying_principal_does_not_change_net_worth(self):
        self.assertEqual(self.bridge["net_worth_effect_of_debt_payments"],
                         Decimal("0.00"))
        self.assertIn("unchanged by it", self.bridge["explains_net_worth"])

    def test_it_explains_the_gap_rather_than_leaving_it(self):
        self.assertIn("answer different questions", self.bridge["explains_the_gap"])

    def test_the_page_renders_it(self):
        from django.urls import reverse
        response = self.client.get(reverse("finance:money_overview"))
        self.assertContains(response, 'data-testid="money-bridge"')
        self.assertContains(response, 'data-view="economic_outflow"')
        self.assertContains(response, "different on purpose")

    def test_the_cos_packet_carries_the_same_relationship(self):
        from apps.finance.services.finance_calc import cos_evidence as E
        packet = E.money_bridge_packet(self.user)
        self.assertEqual(len(packet["views"]), 6)
        self.assertEqual(packet["net_worth_effect_of_debt_payments"], "0.00")
        self.assertIn("Do not recompute", packet["envelope"]["arithmetic_note"])
