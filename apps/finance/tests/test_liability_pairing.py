# ==============================================================================
# File: apps/finance/tests/test_liability_pairing.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Pairing the residual liability credits — and refusing to guess.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""A wrong pair silently merges two unrelated movements.

So the tests that matter most are the refusals: two possible counterparts, a leg already
claimed, a closed-end loan, another user's row. Pairing more is only an improvement if
pairing WRONGLY remains impossible.
"""
from datetime import date, timedelta
from decimal import Decimal

from apps.finance.models import FinancialAccount, Transaction
from apps.finance.services import transfer_detection as TD
from apps.finance.services.finance_calc import measures as M
from apps.finance.services.finance_calc import pairing_rehearsal as PR
from apps.finance.tests.test_p1_economic_roles import RoleBase

JAN = date(2026, 1, 15)


class PairingBase(RoleBase):
    def setUp(self):
        super().setUp()
        self.mortgage = FinancialAccount.objects.create(
            user=self.user, name="Mortgage", account_type="mortgage",
            current_balance=Decimal("-200000"))

    def _held_credit(self, amount, *, account=None, on=JAN):
        """A credit on a revolving liability, held exactly as production holds them."""
        txn = self._txn(amount, account=account or self.card, on=on,
                        primary="LOAN_DISBURSEMENTS",
                        detailed="LOAN_DISBURSEMENTS_OTHER_DISBURSEMENT")
        txn.economic_role = Transaction.ROLE_UNCERTAIN
        txn.role_reason = "unmatched_liability_credit"
        txn.role_source = Transaction.ROLE_SOURCE_DERIVED
        txn.save()
        return txn

    def _payment(self, amount, *, on=JAN, account=None):
        return self._txn(-amount, account=account or self.checking, on=on,
                         primary="LOAN_PAYMENTS",
                         detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")


class RehearsalTests(PairingBase):
    def test_the_rehearsal_writes_nothing(self):
        self._held_credit(1500)
        self._payment(1500)
        before = Transaction.objects.filter(transfer_pair__isnull=False).count()
        PR.run(self.user)
        self.assertEqual(
            Transaction.objects.filter(transfer_pair__isnull=False).count(), before)

    def test_it_finds_the_single_counterpart(self):
        self._held_credit(1500)
        self._payment(1500)
        report = PR.run(self.user)
        self.assertEqual(report["would_pair"], 1)
        self.assertEqual(report["outcomes"]["exactly_one_counterpart"]["count"], 1)

    def test_it_reports_ambiguity_rather_than_picking(self):
        self._held_credit(1500)
        self._payment(1500, on=JAN)
        self._payment(1500, on=JAN + timedelta(days=1))
        report = PR.run(self.user)
        self.assertEqual(report["would_pair"], 0)
        self.assertEqual(report["outcomes"]["several_possible_counterparts"]["count"], 1)

    def test_it_reports_a_genuinely_unmatched_credit(self):
        self._held_credit(1500)
        report = PR.run(self.user)
        self.assertEqual(report["outcomes"]["no_counterpart_visible"]["count"], 1)

    def test_it_never_proposes_one_leg_for_two_rows(self):
        self._held_credit(1500, on=JAN)
        self._held_credit(1500, on=JAN)
        self._payment(1500)
        self.assertEqual(PR.run(self.user)["would_pair"], 1)

    def test_the_report_carries_no_descriptions(self):
        self._held_credit(1500)
        txn = self._payment(1500)
        txn.description = "ACME BANK PAYMENT 9931"
        txn.save()
        self.assertNotIn("ACME", str(PR.run(self.user)))

    def test_it_names_the_existing_authority_limit(self):
        limits = PR.existing_authority_limits(self.user)
        self.assertIn("2,000", limits["note"])
        self.assertIn("transactions", limits)


class ApplyTests(PairingBase):
    def test_a_single_counterpart_is_paired(self):
        credit = self._held_credit(1500)
        payment = self._payment(1500)
        report = TD.pair_liability_credits(self.user)
        self.assertEqual(report["paired"], 1)
        credit.refresh_from_db()
        self.assertIn(payment.pk,
                      {credit.transfer_pair_id,
                       getattr(getattr(credit, "transfer_counterpart", None), "pk", None)})

    def test_ambiguity_is_left_alone(self):
        self._held_credit(1500)
        self._payment(1500, on=JAN)
        self._payment(1500, on=JAN + timedelta(days=1))
        report = TD.pair_liability_credits(self.user)
        self.assertEqual(report["paired"], 0)
        self.assertEqual(report["ambiguous"], 1)

    def test_running_it_twice_pairs_nothing_the_second_time(self):
        self._held_credit(1500)
        self._payment(1500)
        TD.pair_liability_credits(self.user)
        self.assertEqual(TD.pair_liability_credits(self.user)["paired"], 0)

    def test_a_closed_end_loan_credit_is_never_touched(self):
        """A mortgage credit is already debt service. Pairing it away removed it once."""
        credit = self._held_credit(2388.95, account=self.mortgage)
        self._payment(2388.95)
        report = TD.pair_liability_credits(self.user)
        self.assertEqual(report["skipped_closed_end"], 1)
        self.assertEqual(report["paired"], 0)
        credit.refresh_from_db()
        self.assertIsNone(credit.transfer_pair_id)

    def test_one_leg_cannot_be_claimed_by_two_rows(self):
        self._held_credit(1500, on=JAN)
        self._held_credit(1500, on=JAN)
        self._payment(1500)
        self.assertEqual(TD.pair_liability_credits(self.user)["paired"], 1)

    def test_it_never_pairs_across_users(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="p2@example.com", password="pw"))
        their_account = FinancialAccount.objects.create(
            user=other, name="Theirs", account_type="checking",
            current_balance=Decimal("5000"))
        Transaction.objects.create(
            user=other, account=their_account, date=JAN,
            amount=Decimal("-1500"), description="theirs")
        self._held_credit(1500)
        self.assertEqual(TD.pair_liability_credits(self.user)["paired"], 0)

    def test_an_already_paired_row_is_skipped(self):
        credit = self._held_credit(1500)
        payment = self._payment(1500)
        credit.transfer_pair = payment
        credit.save()
        self.assertEqual(TD.pair_liability_credits(self.user)["skipped_already"], 1)


class MeasureImpactTests(PairingBase):
    """Pairing changes what things MEAN. It must not change what moved."""

    def test_pairing_turns_the_credit_into_a_card_payment(self):
        credit = self._held_credit(1500)
        self._payment(1500)
        TD.pair_liability_credits(self.user)
        from apps.finance.services.finance_calc import roles as R
        credit.refresh_from_db()
        self.assertEqual(R.classify(credit).role, Transaction.ROLE_CARD_PAYMENT)

    def test_the_cash_leg_still_leaves_the_account(self):
        self._held_credit(1500)
        self._payment(1500)
        TD.pair_liability_credits(self.user)
        from apps.finance.services.finance_calc import backfill
        backfill.run(self.user, commit=True)
        measures = M.all_measures(self.user)
        self.assertEqual(
            measures["transfers_and_allocations"].components["card_payments"],
            Decimal("3000.00"), "both legs of one payment, each seen once")

    def test_pairing_never_makes_a_card_payment_into_spending(self):
        self._held_credit(1500)
        self._payment(1500)
        self._txn(-40, primary="FOOD_AND_DRINK")
        TD.pair_liability_credits(self.user)
        from apps.finance.services.finance_calc import backfill
        backfill.run(self.user, commit=True)
        self.assertEqual(M.all_measures(self.user)["net_spending"].value,
                         Decimal("40.00"))

    def test_reconciliation_still_holds_after_pairing(self):
        self._held_credit(1500)
        self._payment(1500)
        self._txn(-40, primary="FOOD_AND_DRINK")
        self._txn(3000, primary="INCOME")
        TD.pair_liability_credits(self.user)
        from apps.finance.services.finance_calc import backfill
        backfill.run(self.user, commit=True)
        self.assertTrue(M.reconcile(M.all_measures(self.user))["all_hold"])

    def test_pairing_never_turns_borrowing_into_income(self):
        self._held_credit(1500)
        TD.pair_liability_credits(self.user)
        from apps.finance.services.finance_calc import backfill
        backfill.run(self.user, commit=True)
        self.assertEqual(M.all_measures(self.user)["income"].value, Decimal("0.00"))

    def test_a_user_decision_survives_pairing_and_reclassification(self):
        credit = self._held_credit(1500)
        credit.economic_role = Transaction.ROLE_REIMBURSEMENT
        credit.role_source = Transaction.ROLE_SOURCE_USER
        credit.save()
        self._payment(1500)
        TD.pair_liability_credits(self.user)
        from apps.finance.services.finance_calc import backfill
        backfill.run(self.user, commit=True)
        credit.refresh_from_db()
        self.assertEqual(credit.economic_role, Transaction.ROLE_REIMBURSEMENT)


class FundingLegTests(PairingBase):
    """The counterpart must look like the leg that FUNDED the payment.

    Every unambiguous match in the production rehearsal was a chequing outflow facing a
    card credit. Requiring that shape costs nothing there and refuses a class of wrong
    match: a card-to-card balance transfer is not a payment, and stays held.
    """

    def test_a_card_to_card_credit_is_not_treated_as_a_payment(self):
        second_card = FinancialAccount.objects.create(
            user=self.user, name="Other card", account_type="credit_card",
            current_balance=Decimal("200"))
        self._held_credit(1500)
        self._txn(-1500, account=second_card, on=JAN, primary="TRANSFER_OUT")
        report = TD.pair_liability_credits(self.user)
        self.assertEqual(report["paired"], 0)
        self.assertEqual(report["no_counterpart"], 1)

    def test_an_inflow_is_never_the_counterpart_of_an_inflow(self):
        self._held_credit(1500)
        self._txn(1500, on=JAN, primary="TRANSFER_IN")
        self.assertEqual(TD.pair_liability_credits(self.user)["paired"], 0)

    def test_a_chequing_outflow_still_pairs(self):
        self._held_credit(1500)
        self._payment(1500)
        self.assertEqual(TD.pair_liability_credits(self.user)["paired"], 1)

    def test_savings_can_fund_a_payment_too(self):
        self._held_credit(1500)
        self._payment(1500, account=self.savings)
        self.assertEqual(TD.pair_liability_credits(self.user)["paired"], 1)
