# ==============================================================================
# File: apps/finance/tests/test_monthly_views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The three monthly questions must stay three questions.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Spending, liquid cash and card debt are different questions.

The defect these guard against is not an arithmetic slip. It is a label: one number
computed one way and described three ways, so a person reads "cash flow +$2,329" and
believes their bank balance went up by that, when what actually happened was that they
put a great deal on a card and have not paid for it yet.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.finance.models import FinancialAccount, Transaction
from apps.finance.services.asset_registry import liability_breakdown
from apps.finance.services.finance_calc import monthly_views as V
from apps.finance.tests.test_p1_economic_roles import RoleBase

JAN = date(2026, 1, 15)
MONTH_START = date(2026, 1, 1)
MONTH_END = date(2026, 1, 31)


class ViewsBase(RoleBase):
    def views(self, start=MONTH_START, end=MONTH_END, today=None):
        return V.monthly_views(self.user, start, end, today=today or end)

    def _matched(self, amount, *, liability, kind, cash_primary, credit_primary):
        """A matched pair: cash leaves chequing, a credit lands on the liability."""
        credit = self._txn(amount, account=liability,
                           state=Transaction.TRANSFER_STATE_CONFIRMED,
                           kind=kind, by=Transaction.TRANSFER_BY_PAIRING,
                           primary=credit_primary)
        cash = self._txn("-" + amount,
                         state=Transaction.TRANSFER_STATE_CONFIRMED,
                         kind=kind, by=Transaction.TRANSFER_BY_PAIRING,
                         primary=cash_primary)
        cash.transfer_pair = credit
        cash.save(update_fields=["transfer_pair"])
        return cash, credit

    def _card_payment(self, amount):
        return self._matched(
            amount, liability=self.card,
            kind=Transaction.TRANSFER_KIND_CARD_PAYMENT,
            cash_primary="LOAN_PAYMENTS", credit_primary="TRANSFER_IN")

    def _loan_payment(self, liability, amount):
        return self._matched(
            amount, liability=liability,
            kind=Transaction.TRANSFER_KIND_CARD_PAYMENT,
            cash_primary="LOAN_PAYMENTS", credit_primary="TRANSFER_IN")

    def _internal_transfer(self, amount):
        credit = self._txn(amount, account=self.savings,
                           state=Transaction.TRANSFER_STATE_CONFIRMED,
                           kind=Transaction.TRANSFER_KIND_INTERNAL,
                           by=Transaction.TRANSFER_BY_PAIRING,
                           primary="TRANSFER_IN")
        cash = self._txn("-" + amount,
                         state=Transaction.TRANSFER_STATE_CONFIRMED,
                         kind=Transaction.TRANSFER_KIND_INTERNAL,
                         by=Transaction.TRANSFER_BY_PAIRING,
                         primary="TRANSFER_OUT")
        cash.transfer_pair = credit
        cash.save(update_fields=["transfer_pair"])
        return cash, credit


class SpendingResultTests(ViewsBase):
    """A — am I spending more than I earn?"""

    def test_a_card_purchase_counts_when_incurred(self):
        self._txn(3000, primary="INCOME")
        self._txn(-200, account=self.card, primary="FOOD_AND_DRINK")

        spending = self.views()["spending_result"]
        lines = {line["key"]: line["amount"] for line in spending["lines"]}
        self.assertEqual(lines["gross_purchases"], Decimal("200.00"),
                         "the card purchase is spending the day it happens")
        self.assertEqual(spending["amount"], Decimal("2800.00"))
        self.assertTrue(spending["is_surplus"])
        self.assertEqual(spending["label"], "Spending surplus")

    def test_paying_the_card_is_not_spending_again(self):
        self._txn(3000, primary="INCOME")
        self._txn(-200, account=self.card, primary="FOOD_AND_DRINK")
        payment_out, _ = self._card_payment("200")

        spending = self.views()["spending_result"]
        lines = {line["key"]: line["amount"] for line in spending["lines"]}
        self.assertEqual(lines["gross_purchases"], Decimal("200.00"),
                         "one purchase, counted once — not once more when paid")
        self.assertEqual(spending["amount"], Decimal("2800.00"))

    def test_a_deficit_is_called_a_deficit(self):
        self._txn(1000, primary="INCOME")
        self._txn(-1500, primary="FOOD_AND_DRINK")
        spending = self.views()["spending_result"]
        self.assertEqual(spending["amount"], Decimal("-500.00"))
        self.assertFalse(spending["is_surplus"])
        self.assertEqual(spending["label"], "Spending deficit")

    def test_refunds_reduce_spending(self):
        self._txn(3000, primary="INCOME")
        self._txn(-500, primary="GENERAL_MERCHANDISE")
        self._txn(120, account=self.card, primary="GENERAL_MERCHANDISE",
                  detailed="GENERAL_MERCHANDISE_REFUND")

        spending = self.views()["spending_result"]
        lines = {line["key"]: line["amount"] for line in spending["lines"]}
        self.assertEqual(lines["refunds"], Decimal("120.00"))
        self.assertEqual(lines["net_spending"], Decimal("380.00"),
                         "500 out, 120 back")

    def test_mortgage_principal_is_not_consumer_spending(self):
        mortgage = FinancialAccount.objects.create(
            user=self.user, name="Mortgage", account_type="mortgage",
            current_balance=Decimal("-200000"))
        self._txn(5000, primary="INCOME")
        self._loan_payment(mortgage, "1800")

        spending = self.views()["spending_result"]
        lines = {line["key"]: line["amount"] for line in spending["lines"]}
        self.assertEqual(lines["gross_purchases"], Decimal("0.00"))
        self.assertEqual(spending["amount"], Decimal("5000.00"),
                         "paying down a loan is not consumption")

    def test_internal_transfers_are_not_spending(self):
        self._txn(3000, primary="INCOME")
        self._internal_transfer("1000")

        spending = self.views()["spending_result"]
        self.assertEqual(spending["amount"], Decimal("3000.00"),
                         "moving your own money is not spending it")


class LiquidCashTests(ViewsBase):
    """B — did the money available to me go up or down?"""

    def test_a_card_purchase_does_not_touch_liquid_cash(self):
        self._txn(3000, primary="INCOME")
        self._txn(-200, account=self.card, primary="FOOD_AND_DRINK")

        cash = self.views()["liquid_cash"]
        self.assertEqual(cash["amount"], Decimal("3000.00"),
                         "the card was charged; the bank account was not")
        self.assertTrue(cash["is_increase"])

    def test_a_card_payment_reduces_liquid_cash(self):
        self._txn(3000, primary="INCOME")
        self._card_payment("200")

        cash = self.views()["liquid_cash"]
        lines = {line["key"]: line["amount"] for line in cash["lines"]}
        self.assertEqual(lines["cash_out"], Decimal("200.00"),
                         "the money genuinely left the chequing account")
        self.assertEqual(cash["amount"], Decimal("2800.00"))

    def test_a_mortgage_payment_reduces_liquid_cash(self):
        mortgage = FinancialAccount.objects.create(
            user=self.user, name="Mortgage", account_type="mortgage",
            current_balance=Decimal("-200000"))
        self._loan_payment(mortgage, "1800")

        cash = self.views()["liquid_cash"]
        lines = {line["key"]: line["amount"] for line in cash["lines"]}
        self.assertEqual(lines["cash_out"], Decimal("1800.00"))
        self.assertEqual(lines["cash_in"], Decimal("0.00"),
                         "the leg landing on the mortgage is not money arriving")
        self.assertEqual(cash["amount"], Decimal("-1800.00"))

    def test_an_internal_transfer_is_household_neutral(self):
        self._internal_transfer("1000")

        cash = self.views()["liquid_cash"]
        self.assertEqual(cash["amount"], Decimal("0.00"),
                         "chequing to savings changes nothing at household level")
        lines = {line["key"]: line["amount"] for line in cash["lines"]}
        self.assertEqual(lines["cash_in"], Decimal("1000.00"),
                         "still visible per account in the drill-down")
        self.assertEqual(lines["cash_out"], Decimal("1000.00"))

    def test_liquid_cash_is_not_income_minus_spending(self):
        """The whole point. Same month, two different true answers."""
        self._txn(3000, primary="INCOME")
        self._txn(-2500, account=self.card, primary="GENERAL_MERCHANDISE")

        views = self.views()
        self.assertEqual(views["spending_result"]["amount"], Decimal("500.00"))
        self.assertEqual(views["liquid_cash"]["amount"], Decimal("3000.00"))
        self.assertNotEqual(views["spending_result"]["amount"],
                            views["liquid_cash"]["amount"])


class CardActivityTests(ViewsBase):
    """C — did my card debt grow or shrink?"""

    def test_charges_grow_the_debt(self):
        self._txn(-300, account=self.card, primary="GENERAL_MERCHANDISE")
        card = self.views()["card_activity"]
        self.assertEqual(card["amount"], Decimal("300.00"))
        self.assertTrue(card["debt_grew"])
        self.assertEqual(card["label"], "Card debt grew")

    def test_payments_shrink_the_debt(self):
        self._txn(-300, account=self.card, primary="GENERAL_MERCHANDISE")
        self._card_payment("500")

        card = self.views()["card_activity"]
        lines = {line["key"]: line["amount"] for line in card["lines"]}
        self.assertEqual(lines["charges"], Decimal("300.00"))
        self.assertEqual(lines["payments"], Decimal("500.00"))
        self.assertEqual(card["amount"], Decimal("-200.00"), "300 on, 500 off")
        self.assertFalse(card["debt_grew"])

    def test_interest_and_fees_grow_the_debt(self):
        self._txn(-40, account=self.card, primary="BANK_FEES",
                  detailed="BANK_FEES_INTEREST_CHARGE")
        card = self.views()["card_activity"]
        lines = {line["key"]: line["amount"] for line in card["lines"]}
        self.assertEqual(lines["fees"], Decimal("40.00"))
        self.assertEqual(card["amount"], Decimal("40.00"))

    def test_a_refund_reduces_card_debt(self):
        self._txn(-300, account=self.card, primary="GENERAL_MERCHANDISE")
        self._txn(100, account=self.card, primary="GENERAL_MERCHANDISE",
                  detailed="GENERAL_MERCHANDISE_REFUND")
        card = self.views()["card_activity"]
        lines = {line["key"]: line["amount"] for line in card["lines"]}
        self.assertEqual(lines["credits"], Decimal("100.00"))
        self.assertEqual(card["amount"], Decimal("200.00"))

    def test_debit_spending_never_reaches_the_card_view(self):
        self._txn(-800, primary="GENERAL_MERCHANDISE")
        card = self.views()["card_activity"]
        self.assertEqual(card["amount"], Decimal("0.00"),
                         "a chequing purchase is not card activity")

    def test_it_says_it_is_activity_based(self):
        """WLJ has no statement-balance history, and must not imply it does."""
        card = self.views()["card_activity"]
        self.assertEqual(card["basis"], "activity_based")
        self.assertIn("not an opening-to-closing", card["basis_note"])

    def test_the_sign_convention_is_stated(self):
        card = self.views()["card_activity"]
        self.assertIn("Positive means the debt grew", card["sign_convention"])

    def test_current_balance_comes_from_the_accounts(self):
        card = self.views()["card_activity"]
        self.assertEqual(card["current_balance"], Decimal("500.00"))
        self.assertEqual(card["card_count"], 1)


class NoDoubleCountingTests(ViewsBase):
    """One purchase paid by card, then settled. Each view counts it once, its own way."""

    def setUp(self):
        super().setUp()
        self._txn(4000, primary="INCOME")
        self._txn(-1000, account=self.card, primary="GENERAL_MERCHANDISE")
        self._card_payment("1000")
        self.v = self.views()

    def test_spending_counts_the_purchase_once(self):
        lines = {l["key"]: l["amount"] for l in self.v["spending_result"]["lines"]}
        self.assertEqual(lines["gross_purchases"], Decimal("1000.00"))
        self.assertEqual(self.v["spending_result"]["amount"], Decimal("3000.00"))

    def test_liquid_cash_counts_the_payment_once(self):
        lines = {l["key"]: l["amount"] for l in self.v["liquid_cash"]["lines"]}
        self.assertEqual(lines["cash_out"], Decimal("1000.00"),
                         "the payment left; the purchase never touched cash")
        self.assertEqual(self.v["liquid_cash"]["amount"], Decimal("3000.00"))

    def test_card_debt_nets_to_zero(self):
        self.assertEqual(self.v["card_activity"]["amount"], Decimal("0.00"),
                         "charged 1000, paid 1000")

    def test_every_view_walks_to_its_own_total(self):
        report = V.reconcile_views(self.v)
        self.assertTrue(report["all_hold"],
                        [k for k, c in report["checks"].items()
                         if not c.get("passed")])

    def test_the_superseded_figure_double_counts_as_documented(self):
        """Proof of WHY the old number was replaced, not just an assertion."""
        old = self.v["superseded_account_movement"]
        # 4000 in + 1000 card credit - 1000 card charge - 1000 payment = 3000, which
        # only lands on the right answer by coincidence of the legs cancelling. What
        # matters is that it is a different QUESTION, and it says so.
        self.assertIn("counts the same consumption twice", old["why_superseded"])
        self.assertIn("old \"Monthly Cash Flow\"", old["means"])


class PartialMonthTests(ViewsBase):
    def test_an_incomplete_month_is_labelled_month_to_date(self):
        period = self.views(start=MONTH_START, end=date(2026, 1, 9))["period"]
        self.assertTrue(period["is_partial"])
        self.assertEqual(period["qualifier"], "month to date")
        self.assertEqual(period["days_elapsed"], 9)
        self.assertEqual(period["days_in_month"], 31)

    def test_a_finished_month_carries_no_qualifier(self):
        period = self.views(start=MONTH_START, end=MONTH_END)["period"]
        self.assertFalse(period["is_partial"])
        self.assertEqual(period["qualifier"], "")


class LiabilityBreakdownTests(TestCase):
    def setUp(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from django.contrib.auth import get_user_model
        self.user = _usable(get_user_model().objects.create_user(
            email="liab@example.com", password="pw"))
        self.client.force_login(self.user)

    def _account(self, name, kind, balance, last4=""):
        return FinancialAccount.objects.create(
            user=self.user, name=name, account_type=kind,
            current_balance=Decimal(balance), account_number_last4=last4)

    def test_it_reconciles_to_the_total(self):
        self._account("Mortgage", "mortgage", "-405507.93")
        self._account("Card", "credit_card", "-37638.70", last4="4321")
        self._account("Chequing", "checking", "25805.45")

        breakdown = liability_breakdown(self.user)
        self.assertEqual(breakdown["total"], Decimal("443146.63"))
        self.assertEqual(breakdown["shown_total"], Decimal("443146.63"))
        self.assertTrue(breakdown["reconciles"])
        self.assertFalse(breakdown["has_more"])

    def test_it_sorts_by_balance_descending(self):
        self._account("Card", "credit_card", "-37638.70")
        self._account("Mortgage", "mortgage", "-405507.93")
        names = [i["type"] for i in liability_breakdown(self.user)["items"]]
        self.assertEqual(names, ["Mortgage", "Credit Card"])

    def test_it_shows_at_most_four_and_accounts_for_the_rest(self):
        for i in range(6):
            self._account(f"Loan {i}", "loan", f"-{(i + 1) * 1000}")

        breakdown = liability_breakdown(self.user)
        self.assertEqual(len(breakdown["items"]), 4)
        self.assertTrue(breakdown["has_more"])
        self.assertEqual(breakdown["remaining_count"], 2)
        self.assertEqual(breakdown["remaining_total"], Decimal("3000.00"),
                         "the two smallest: 1000 + 2000")
        self.assertEqual(breakdown["shown_total"] + breakdown["remaining_total"],
                         breakdown["total"])
        self.assertTrue(breakdown["reconciles"])

    def test_it_masks_rather_than_exposing_an_account_number(self):
        self._account("Card", "credit_card", "-100", last4="4321")
        item = liability_breakdown(self.user)["items"][0]
        self.assertEqual(item["mask"], "••4321")

    def test_it_never_exposes_a_provider_identifier(self):
        card = self._account("Card", "credit_card", "-100")
        card.plaid_account_id = "acc-secret-xyz"
        card.save(update_fields=["plaid_account_id"])
        blob = str(liability_breakdown(self.user))
        self.assertNotIn("acc-secret-xyz", blob)

    def test_no_liabilities_is_an_empty_list_not_a_crash(self):
        self._account("Chequing", "checking", "500")
        breakdown = liability_breakdown(self.user)
        self.assertEqual(breakdown["items"], [])
        self.assertEqual(breakdown["total"], Decimal("0.00"))
        self.assertTrue(breakdown["reconciles"])


class DashboardRenderTests(ViewsBase):
    def test_the_dashboard_renders_the_three_views_and_the_debts(self):
        FinancialAccount.objects.create(
            user=self.user, name="Mortgage", account_type="mortgage",
            current_balance=Decimal("-405507.93"))
        self._txn(3000, primary="INCOME")
        self._txn(-500, account=self.card, primary="GENERAL_MERCHANDISE")

        response = self.client.get(reverse("finance:dashboard"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('data-testid="monthly-views"', body)
        self.assertIn('data-testid="liability-breakdown"', body)
        self.assertIn('data-view="spending_result"', body)
        self.assertIn('data-view="liquid_cash"', body)
        self.assertIn('data-view="card_activity"', body)

    def test_the_card_is_no_longer_called_cash_flow(self):
        response = self.client.get(reverse("finance:dashboard"))
        body = response.content.decode()
        self.assertNotIn("Monthly Cash Flow", body,
                         "the figure is income less net spending, not cash flow")
        self.assertIn('data-testid="spending-result"', body)

    def test_no_inline_handlers(self):
        """CSP: the dashboard must not grow one while being edited."""
        body = self.client.get(reverse("finance:dashboard")).content.decode()
        for handler in ("onclick=", "onchange=", "onsubmit=", "onload="):
            self.assertNotIn(handler, body)

    def test_it_renders_at_375px_without_fixed_widths(self):
        """375px is the iPhone SE. A fixed width here is a horizontal scrollbar there.

        Scoped to the dashboard's OWN stylesheet — the rendered page also carries the
        shared chat widget, whose 420px is its business and has its own breakpoint.
        """
        import re
        from pathlib import Path

        template = (Path(__file__).resolve().parents[3]
                    / "templates" / "finance" / "dashboard.html").read_text()
        css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", template, re.S))
        self.assertTrue(css)
        # Bare `width:` only — `max-width`/`min-width` are the fix, not the problem.
        offenders = [m for m in re.findall(r"(?<![a-z-])width:\s*(\d+)px", css)
                     if int(m) > 375]
        self.assertEqual(offenders, [], f"fixed widths wider than 375px: {offenders}")
        self.assertIn("max-width: 480px", css, "a mobile breakpoint must exist")
        self.assertIn("min-height: 44px", css, "touch targets must clear 44px")

    def test_it_still_renders_when_the_month_is_empty(self):
        """The 1st of the month, before anything has happened."""
        response = self.client.get(reverse("finance:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-testid="monthly-views"', response.content.decode())


class CoSEvidenceTests(ViewsBase):
    def test_the_packet_keeps_the_three_apart(self):
        from apps.finance.services.finance_calc import cos_evidence as E
        self._txn(3000, primary="INCOME")
        self._txn(-2500, account=self.card, primary="GENERAL_MERCHANDISE")

        packet = E.monthly_views_packet(self.user, MONTH_START, MONTH_END)
        self.assertEqual(packet["packet"], "monthly_views")
        for key in ("spending_result", "liquid_cash", "card_activity"):
            self.assertIn("answers", packet[key],
                          "every view arrives with the question it answers")
        self.assertNotEqual(packet["spending_result"]["amount"],
                            packet["liquid_cash"]["amount"])
        guidance = packet["never_do_this"].lower()
        self.assertIn("do not describe", guidance)
        self.assertIn("different questions", guidance)

    def test_the_packet_forbids_calling_one_the_other(self):
        from apps.finance.services.finance_calc import cos_evidence as E
        packet = E.monthly_views_packet(self.user, MONTH_START, MONTH_END)
        guidance = packet["never_do_this"].lower()
        self.assertIn("cash flow", guidance)
        self.assertIn("do not describe", guidance)

    def test_the_packet_reconciles(self):
        from apps.finance.services.finance_calc import cos_evidence as E
        self._txn(3000, primary="INCOME")
        self._txn(-400, primary="GENERAL_MERCHANDISE")
        packet = E.monthly_views_packet(self.user, MONTH_START, MONTH_END)
        self.assertTrue(packet["reconciliation"]["all_hold"])

    def test_the_domain_exposes_it_as_truth(self):
        from apps.finance.services.finance_domain_truth import FinanceDomainTruth
        truth = FinanceDomainTruth(self.user)
        self.assertIn("monthly_views", truth.entity_types)
        described = truth.describe(entity_type="monthly_views")
        self.assertEqual(described[0]["packet"], "monthly_views")

    def test_the_packet_never_carries_a_description(self):
        from apps.finance.services.finance_calc import cos_evidence as E
        self._txn(-90, primary="FOOD_AND_DRINK", description="SECRET MERCHANT LLC")
        blob = str(E.monthly_views_packet(self.user, MONTH_START, MONTH_END))
        self.assertNotIn("SECRET MERCHANT", blob)


class CardRefundClassificationTests(ViewsBase):
    """The defect this upgrade's inspection found, and the shadow that bounds the fix.

    A return credited back to a credit card carries the provider's own REFUND detail,
    but the rule that separates "a payment arrived" from "I borrowed more" on a
    revolving account fired first and held the row as `uncertain`. Money genuinely came
    back and no measure showed it: net spending did not fall, and card debt did not
    fall.
    """

    def test_a_card_refund_is_a_refund(self):
        t = self._txn(120, account=self.card, primary="GENERAL_MERCHANDISE",
                      detailed="GENERAL_MERCHANDISE_REFUND")
        self.assertEqual(self._role(t), Transaction.ROLE_REFUND)

    def test_a_card_refund_reduces_both_spending_and_card_debt(self):
        self._txn(-500, account=self.card, primary="GENERAL_MERCHANDISE")
        self._txn(120, account=self.card, primary="GENERAL_MERCHANDISE",
                  detailed="GENERAL_MERCHANDISE_REFUND")

        views = self.views()
        lines = {l["key"]: l["amount"] for l in views["spending_result"]["lines"]}
        self.assertEqual(lines["net_spending"], Decimal("380.00"))
        self.assertEqual(views["card_activity"]["amount"], Decimal("380.00"))

    def test_a_card_refund_does_not_touch_liquid_cash(self):
        self._txn(120, account=self.card, primary="GENERAL_MERCHANDISE",
                  detailed="GENERAL_MERCHANDISE_REFUND")
        self.assertEqual(self.views()["liquid_cash"]["amount"], Decimal("0.00"),
                         "a credit on a card is not money arriving in the bank")

    # ---- the shadow: what the fix must NOT have changed -----------------------

    def test_an_unexplained_card_credit_is_still_held(self):
        """The rule this exemption narrows must still catch what it was built for."""
        t = self._txn(2000, account=self.card, primary="LOAN_DISBURSEMENTS")
        self.assertEqual(self._role(t), Transaction.ROLE_UNCERTAIN,
                         "no refund evidence, no counterpart — WLJ cannot tell a "
                         "payment from a draw, and must not guess")

    def test_a_matched_card_payment_is_still_a_card_payment(self):
        _, credit = self._card_payment("300")
        self.assertEqual(self._role(credit), Transaction.ROLE_CARD_PAYMENT)

    def test_card_rewards_are_still_income(self):
        t = self._txn(35, account=self.card, primary="INCOME")
        self.assertEqual(self._role(t), Transaction.ROLE_INCOME)

    def test_a_payment_received_on_a_closed_end_loan_is_still_debt_service(self):
        mortgage = FinancialAccount.objects.create(
            user=self.user, name="Mortgage", account_type="mortgage",
            current_balance=Decimal("-200000"))
        t = self._txn(1800, account=mortgage, primary="LOAN_PAYMENTS")
        self.assertEqual(self._role(t), Transaction.ROLE_DEBT_SERVICE)

    def test_the_exemption_needs_evidence_not_a_shape(self):
        """A bare positive on a card, with no provider word, stays held."""
        t = self._txn(75, account=self.card, primary="GENERAL_MERCHANDISE")
        self.assertEqual(self._role(t), Transaction.ROLE_UNCERTAIN)

    def test_identities_still_hold_with_a_card_refund_present(self):
        from apps.finance.services.finance_calc import measures as M
        self._txn(3000, primary="INCOME")
        self._txn(-500, account=self.card, primary="GENERAL_MERCHANDISE")
        self._txn(120, account=self.card, primary="GENERAL_MERCHANDISE",
                  detailed="GENERAL_MERCHANDISE_REFUND")
        self._card_payment("400")
        self._internal_transfer("250")

        report = M.reconcile(M.all_measures(self.user))
        self.assertTrue(report["all_hold"],
                        [k for k, c in report["checks"].items()
                         if not c.get("passed")])


class MoneyPageDrillDownTests(ViewsBase):
    """Each dashboard figure must lead somewhere that explains it."""

    def test_the_money_page_shows_all_three_walks(self):
        self._txn(3000, primary="INCOME")
        self._txn(-400, account=self.card, primary="GENERAL_MERCHANDISE")
        body = self.client.get(reverse("finance:money_overview")).content.decode()
        self.assertIn('data-testid="monthly-answers"', body)
        for key in ("spending_result", "liquid_cash", "card_activity"):
            self.assertIn(f'data-answer="{key}"', body)

    def test_the_card_walk_says_it_is_activity_based(self):
        body = self.client.get(reverse("finance:money_overview")).content.decode()
        self.assertIn('data-testid="card-basis"', body)
        self.assertIn("not an opening-to-closing", body)

    def test_the_old_figure_is_explained_rather_than_vanished(self):
        body = self.client.get(reverse("finance:money_overview")).content.decode()
        self.assertIn('data-testid="superseded"', body)
        self.assertIn("Monthly Cash Flow", body)

    def test_the_dashboard_links_to_the_reconciliation(self):
        body = self.client.get(reverse("finance:dashboard")).content.decode()
        self.assertIn(reverse("finance:money_overview"), body)
        self.assertIn('data-testid="monthly-views-drill"', body)

    def test_no_inline_handlers_on_the_money_page(self):
        body = self.client.get(reverse("finance:money_overview")).content.decode()
        for handler in ("onclick=", "onchange=", "onsubmit=", "onload="):
            self.assertNotIn(handler, body)
