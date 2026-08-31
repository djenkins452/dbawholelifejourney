# ==============================================================================
# File: apps/finance/tests/test_p1_economic_roles.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P1 — the role matrix, the nine measures, and shadow isolation.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""One classification, nine measures — and none of it may touch a live total yet.

The most important tests here are not the arithmetic. They are the SHADOW tests: proof
that a fully classified population cannot move a dashboard, a budget, a history, a
snapshot, or anything CoS reads. Until Danny approves activation, being right is not
enough — being inert is the requirement.
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.finance.models import (FinancialAccount, Transaction, TransactionCategory)
from apps.finance.services.finance_calc import measures as M
from apps.finance.services.finance_calc import roles as R
from apps.users.models import TermsAcceptance, User

JAN = date(2026, 1, 15)


def _usable(user):
    TermsAcceptance.objects.get_or_create(
        user=user,
        defaults={"terms_version": settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")})
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.finances_enabled = True
    prefs.save()
    return user


class RoleBase(TestCase):
    def setUp(self):
        self.user = _usable(User.objects.create_user(
            email="p1@example.com", password="pw"))
        self.checking = FinancialAccount.objects.create(
            user=self.user, name="Checking", account_type="checking",
            current_balance=Decimal("1000"))
        self.card = FinancialAccount.objects.create(
            user=self.user, name="Card", account_type="credit_card",
            current_balance=Decimal("500"))
        self.savings = FinancialAccount.objects.create(
            user=self.user, name="Savings", account_type="savings",
            current_balance=Decimal("2000"))
        self.client.force_login(self.user)

    def _txn(self, amount, *, account=None, on=JAN, primary="", detailed="",
             state=None, kind="", by="", description="row", **kw):
        from apps.finance.models import Transaction as T
        return Transaction.objects.create(
            user=self.user, account=account or self.checking, date=on,
            amount=Decimal(str(amount)), description=description,
            provider_category_primary=primary,
            provider_category_detailed=detailed,
            transfer_state=state or T.TRANSFER_STATE_NOT_TRANSFER,
            transfer_kind=kind, transfer_classified_by=by, **kw)

    def _role(self, txn):
        return R.classify(txn).role


class RoleMatrixTests(RoleBase):
    """One transaction per class from the architecture matrix."""

    def test_debit_card_purchase(self):
        t = self._txn(-50, primary="FOOD_AND_DRINK")
        self.assertEqual(self._role(t), Transaction.ROLE_PURCHASE)

    def test_credit_card_purchase(self):
        t = self._txn(-50, account=self.card, primary="FOOD_AND_DRINK")
        self.assertEqual(self._role(t), Transaction.ROLE_PURCHASE)

    def test_credit_card_payment(self):
        t = self._txn(-200, state=Transaction.TRANSFER_STATE_CONFIRMED,
                      kind=Transaction.TRANSFER_KIND_CARD_PAYMENT,
                      by=Transaction.TRANSFER_BY_PROVIDER)
        self.assertEqual(self._role(t), Transaction.ROLE_CARD_PAYMENT)

    def test_internal_transfer(self):
        t = self._txn(-300, state=Transaction.TRANSFER_STATE_CONFIRMED,
                      kind=Transaction.TRANSFER_KIND_INTERNAL,
                      by=Transaction.TRANSFER_BY_PAIRING)
        self.assertEqual(self._role(t), Transaction.ROLE_INTERNAL_TRANSFER)

    def test_unmatched_transfer_candidate_is_uncertain(self):
        t = self._txn(-300, state=Transaction.TRANSFER_STATE_CANDIDATE,
                      kind=Transaction.TRANSFER_KIND_INTERNAL)
        assignment = R.classify(t)
        self.assertEqual(assignment.role, Transaction.ROLE_UNCERTAIN)
        self.assertEqual(assignment.reason, "unmatched_transfer_candidate")

    def test_savings_allocation(self):
        t = self._txn(300, account=self.savings,
                      state=Transaction.TRANSFER_STATE_CONFIRMED,
                      kind=Transaction.TRANSFER_KIND_INTERNAL,
                      by=Transaction.TRANSFER_BY_PAIRING)
        self.assertEqual(self._role(t), Transaction.ROLE_SAVINGS_ALLOCATION)

    def test_loan_payment_is_debt_service(self):
        t = self._txn(-1500, primary="LOAN_PAYMENTS",
                      detailed="LOAN_PAYMENTS_MORTGAGE_PAYMENT")
        self.assertEqual(self._role(t), Transaction.ROLE_DEBT_SERVICE)

    def test_refund(self):
        t = self._txn(80, kind=Transaction.TRANSFER_KIND_REFUND,
                      primary="GENERAL_MERCHANDISE")
        self.assertEqual(self._role(t), Transaction.ROLE_REFUND)

    def test_reversal(self):
        t = self._txn(40, state=Transaction.TRANSFER_STATE_CONFIRMED,
                      kind=Transaction.TRANSFER_KIND_REVERSAL,
                      by=Transaction.TRANSFER_BY_PROVIDER)
        self.assertEqual(self._role(t), Transaction.ROLE_REVERSAL)

    def test_cash_withdrawal(self):
        t = self._txn(-100, detailed="TRANSFER_OUT_ATM_WITHDRAWAL")
        self.assertEqual(self._role(t), Transaction.ROLE_CASH_WITHDRAWAL)

    def test_bank_fee(self):
        t = self._txn(-35, primary="BANK_FEES", detailed="BANK_FEES_OVERDRAFT_FEES")
        self.assertEqual(self._role(t), Transaction.ROLE_FEE_INTEREST)

    def test_income(self):
        t = self._txn(3000, primary="INCOME", detailed="INCOME_WAGES")
        self.assertEqual(self._role(t), Transaction.ROLE_INCOME)

    def test_unclassified_credit_is_held_not_called_a_reimbursement(self):
        """WLJ cannot tell a reimbursement from a generic credit; claiming one
        would understate spending on evidence it does not have."""
        t = self._txn(120, primary="")
        assignment = R.classify(t)
        self.assertEqual(assignment.role, Transaction.ROLE_UNCERTAIN)
        self.assertEqual(assignment.reason, "unclassified_credit")

    def test_zero_amount_has_no_economic_meaning(self):
        self.assertEqual(self._role(self._txn(0)), Transaction.ROLE_UNCERTAIN)


class UserAuthorityTests(RoleBase):
    def test_a_user_confirmed_transfer_is_never_overwritten(self):
        t = self._txn(-300, primary="FOOD_AND_DRINK",
                      state=Transaction.TRANSFER_STATE_CONFIRMED,
                      kind=Transaction.TRANSFER_KIND_INTERNAL,
                      by=Transaction.TRANSFER_BY_USER)
        assignment = R.classify(t)
        self.assertEqual(assignment.role, Transaction.ROLE_INTERNAL_TRANSFER)
        self.assertEqual(assignment.source, Transaction.ROLE_SOURCE_USER)
        self.assertEqual(assignment.reason, "user_confirmed_transfer")

    def test_a_user_confirmed_card_payment_outranks_a_spending_category(self):
        t = self._txn(-300, primary="GENERAL_MERCHANDISE",
                      state=Transaction.TRANSFER_STATE_CONFIRMED,
                      kind=Transaction.TRANSFER_KIND_CARD_PAYMENT,
                      by=Transaction.TRANSFER_BY_USER)
        self.assertEqual(R.classify(t).source, Transaction.ROLE_SOURCE_USER)


class MeasureTests(RoleBase):
    def setUp(self):
        super().setUp()
        self._txn(-100, primary="FOOD_AND_DRINK")                     # purchase
        self._txn(-50, account=self.card, primary="GENERAL_MERCHANDISE")
        self._txn(-200, state=Transaction.TRANSFER_STATE_CONFIRMED,
                  kind=Transaction.TRANSFER_KIND_CARD_PAYMENT,
                  by=Transaction.TRANSFER_BY_PROVIDER)                # card payment
        self._txn(30, kind=Transaction.TRANSFER_KIND_REFUND,
                  primary="GENERAL_MERCHANDISE")                      # refund
        self._txn(3000, primary="INCOME")                             # income
        self._txn(-1500, primary="LOAN_PAYMENTS",
                  detailed="LOAN_PAYMENTS_MORTGAGE_PAYMENT")          # debt service
        self.m = M.all_measures(self.user)

    def test_card_purchase_counts_once_and_the_payment_is_not_spending(self):
        """The rule that must never break."""
        self.assertEqual(self.m["gross_purchases"].value, Decimal("150.00"))
        self.assertNotIn("200", str(self.m["gross_purchases"].value))
        self.assertEqual(self.m["transfers_and_allocations"]
                         .components["card_payments"], Decimal("200.00"))

    def test_refund_offsets_and_is_not_income(self):
        self.assertEqual(self.m["net_spending"].value, Decimal("120.00"))
        self.assertEqual(self.m["income"].value, Decimal("3000.00"))
        self.assertEqual(self.m["net_spending"].components["refunds"], Decimal("30.00"))

    def test_the_refund_row_keeps_its_own_identity(self):
        refunds = Transaction.objects.filter(
            user=self.user, transfer_kind=Transaction.TRANSFER_KIND_REFUND)
        self.assertEqual(refunds.count(), 1, "offset, never deleted")

    def test_debt_service_is_outflow_and_debt_but_not_spending(self):
        self.assertEqual(self.m["debt_service"].value, Decimal("1500.00"))
        self.assertIn("1500", str(self.m["cash_outflow"].components["debt_service"]))
        self.assertEqual(self.m["net_spending"].value, Decimal("120.00"))

    def test_unsplit_debt_service_states_its_limitation(self):
        ds = self.m["debt_service"]
        self.assertEqual(ds.components["unsplit"], Decimal("1500.00"))
        self.assertEqual(ds.components["principal_known"], Decimal("0.00"))
        self.assertIn("loan_terms", ds.inputs_missing)
        self.assertTrue(any("UNSPLIT" in a for a in ds.assumptions))

    def test_income_excludes_refunds(self):
        self.assertEqual(self.m["income"].value, Decimal("3000.00"))
        self.assertEqual(self.m["cash_inflow"].value, Decimal("3030.00"))

    def test_transfers_are_in_neither_spending_measure(self):
        self.assertNotIn("card_payments", self.m["gross_purchases"].components)
        self.assertIn("card_payments", self.m["net_spending"].exclusions)

    def test_all_reconciliation_identities_hold(self):
        report = M.reconcile(self.m)
        self.assertTrue(report["all_hold"], report["checks"])

    def test_measures_report_uncertainty(self):
        self._txn(-400, state=Transaction.TRANSFER_STATE_CANDIDATE)
        m = M.all_measures(self.user)
        self.assertEqual(m["net_spending"].uncertain_count, 1)
        self.assertEqual(m["net_spending"].uncertain_amount, Decimal("400.00"))

    def test_an_uncertain_row_keeps_cash_movement_out_of_spending(self):
        """It must not disappear; only its economic meaning is withheld."""
        self._txn(-400, state=Transaction.TRANSFER_STATE_CANDIDATE)
        m = M.all_measures(self.user)
        self.assertEqual(m["net_spending"].value, Decimal("120.00"))
        self.assertIn("uncertain", m["net_spending"].exclusions)
        self.assertEqual(m["net_spending"].exclusions["uncertain"], Decimal("400.00"))

    def test_cash_withdrawal_is_outflow_but_not_spending(self):
        self._txn(-100, detailed="TRANSFER_OUT_ATM_WITHDRAWAL")
        m = M.all_measures(self.user)
        self.assertEqual(m["cash_outflow"].components["cash_withdrawals"],
                         Decimal("100.00"))
        self.assertEqual(m["net_spending"].value, Decimal("120.00"))

    def test_savings_and_investment_allocations_are_not_consumption(self):
        self._txn(500, account=self.savings,
                  state=Transaction.TRANSFER_STATE_CONFIRMED,
                  kind=Transaction.TRANSFER_KIND_INTERNAL,
                  by=Transaction.TRANSFER_BY_PAIRING)
        m = M.all_measures(self.user)
        self.assertEqual(m["net_spending"].value, Decimal("120.00"))
        self.assertEqual(m["transfers_and_allocations"]
                         .components["savings_allocations"], Decimal("500.00"))

    def test_unimplemented_measures_say_so_instead_of_reporting_zero_as_fact(self):
        for name, missing in (("recurring_obligations", "recurring_detection (P4)"),
                              ("controllable_spending", "controllability_taxonomy (P2)")):
            with self.subTest(measure=name):
                result = self.m[name]
                self.assertEqual(result.confidence, "low")
                self.assertIn(missing, result.inputs_missing)


class OpeningBalanceTests(RoleBase):
    """Excluded by ROLE, never by a second copy of the activity filter.

    Two constitutional contract tests forbid any module outside
    `attribution_population` from re-deriving the activity exclusion. The first cut of
    `measures._population` filtered `is_opening_balance=False` and both guards caught
    it — correctly. The exclusion is now a role, which is also what the architecture's
    own principle demands: ask for a different measure, never a different filter.
    """

    def test_an_opening_balance_gets_its_own_role(self):
        t = self._txn(1000, is_opening_balance=True)
        self.assertEqual(self._role(t), Transaction.ROLE_OPENING_BALANCE)

    def test_it_enters_no_measure(self):
        self._txn(5000, is_opening_balance=True)
        self._txn(-100, primary="FOOD_AND_DRINK")
        m = M.all_measures(self.user)
        self.assertEqual(m["gross_purchases"].value, Decimal("100.00"))
        self.assertEqual(m["cash_inflow"].value, Decimal("0.00"))
        self.assertEqual(m["income"].value, Decimal("0.00"))

    def test_the_measures_module_does_not_re_derive_the_activity_exclusion(self):
        from pathlib import Path
        source = Path(M.__file__).read_text()
        self.assertNotIn("is_opening_balance=False", source,
                         "only attribution_population may define that exclusion")


class PendingTests(RoleBase):
    def test_a_posted_row_replacing_a_pending_one_is_counted_once(self):
        """`sync_service` promotes the pending row IN PLACE, so there is one row."""
        t = self._txn(-75, primary="FOOD_AND_DRINK", plaid_pending=True,
                      plaid_transaction_id="pending-1")
        t.plaid_pending = False
        t.plaid_transaction_id = "posted-1"
        t.provider_pending_transaction_id = "pending-1"
        t.save()
        m = M.all_measures(self.user)
        self.assertEqual(m["gross_purchases"].value, Decimal("75.00"))
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)


class DeterminismTests(RoleBase):
    def test_the_classifier_is_idempotent(self):
        t = self._txn(-100, primary="FOOD_AND_DRINK")
        first = R.classify(t)
        for _ in range(5):
            again = R.classify(t)
            self.assertEqual((again.role, again.confidence, again.source, again.reason),
                             (first.role, first.confidence, first.source, first.reason))

    def test_classification_writes_nothing(self):
        t = self._txn(-100, primary="FOOD_AND_DRINK")
        R.classify(t)
        M.all_measures(self.user)
        t.refresh_from_db()
        self.assertIsNone(t.economic_role)
        self.assertIsNone(t.role_source)
        self.assertEqual(t.role_classifier_version, "")

    def test_every_result_carries_its_versions(self):
        for name, result in M.all_measures(self.user).items():
            with self.subTest(measure=name):
                self.assertEqual(result.calculation_version, M.MEASURES_VERSION)
                self.assertEqual(result.classifier_version, R.CLASSIFIER_VERSION)

    def test_reasons_are_stable_keys_never_merchant_text(self):
        t = self._txn(-100, primary="FOOD_AND_DRINK", description="TOTALLY SECRET LLC")
        reason = R.classify(t).reason
        self.assertNotIn("SECRET", reason)
        self.assertRegex(reason, r"^[a-z0-9_]+$")


class ShadowIsolationTests(RoleBase):
    """The requirement that outranks correctness: none of this may move a live total."""

    def setUp(self):
        super().setUp()
        self._txn(-100, primary="FOOD_AND_DRINK")
        self._txn(-200, state=Transaction.TRANSFER_STATE_CONFIRMED,
                  kind=Transaction.TRANSFER_KIND_CARD_PAYMENT,
                  by=Transaction.TRANSFER_BY_PROVIDER)
        self._txn(3000, primary="INCOME")

    def test_the_live_authority_is_untouched_by_classification(self):
        from apps.finance.services.attribution_population import financial_activity

        before = [t.pk for t in financial_activity(self.user)]
        M.all_measures(self.user)
        after = [t.pk for t in financial_activity(self.user)]
        self.assertEqual(before, after)

    def test_dashboard_totals_are_unchanged_by_shadow_data(self):
        first = self.client.get(reverse("finance:dashboard")).context
        snapshot = (first["net_worth"], first["total_assets"],
                    first["total_liabilities"])
        M.all_measures(self.user)
        second = self.client.get(reverse("finance:dashboard")).context
        self.assertEqual(snapshot, (second["net_worth"], second["total_assets"],
                                    second["total_liabilities"]))

    def test_even_a_fully_populated_shadow_column_changes_nothing(self):
        """Simulates the post-backfill state and proves it is still inert."""
        from apps.finance.services.attribution_population import financial_activity

        before = [t.pk for t in financial_activity(self.user)]
        before_dash = self.client.get(reverse("finance:dashboard")).context["net_worth"]

        for txn in Transaction.objects.filter(user=self.user):
            assignment = R.classify(txn)
            Transaction.objects.filter(pk=txn.pk).update(**assignment.as_update_fields())

        self.assertEqual([t.pk for t in financial_activity(self.user)], before)
        self.assertEqual(
            self.client.get(reverse("finance:dashboard")).context["net_worth"],
            before_dash)

    def test_nothing_outside_finance_calc_reads_the_shadow_fields(self):
        """The activation gate is the ABSENCE of a reader, not a flag to forget."""
        import subprocess
        out = subprocess.run(
            ["grep", "-rln", "economic_role", "apps/", "templates/"],
            capture_output=True, text=True).stdout.split()
        allowed = {
            "apps/finance/models.py",
            "apps/finance/services/finance_calc/roles.py",
            "apps/finance/services/finance_calc/measures.py",
            "apps/finance/services/finance_calc/dry_run.py",
            "apps/finance/tests/test_p1_economic_roles.py",
        }
        unexpected = [p for p in out
                      if p not in allowed and "migrations" not in p]
        self.assertEqual(unexpected, [],
                         "a reader outside finance_calc would end shadow mode")

    def test_cos_truth_does_not_expose_the_new_measures(self):
        from apps.finance.services.finance_domain_truth import FinanceDomainTruth
        for name in M.ALL_MEASURES:
            with self.subTest(measure=name):
                self.assertNotIn(name, FinanceDomainTruth.entity_types)
                self.assertNotIn(name, FinanceDomainTruth.current_metrics)


class OwnershipTests(RoleBase):
    def test_measures_never_cross_users(self):
        other = _usable(User.objects.create_user(email="other@example.com",
                                                 password="pw"))
        account = FinancialAccount.objects.create(
            user=other, name="Theirs", account_type="checking")
        Transaction.objects.create(
            user=other, account=account, date=JAN, amount=Decimal("-9999"),
            description="theirs", provider_category_primary="FOOD_AND_DRINK")

        self._txn(-100, primary="FOOD_AND_DRINK")
        m = M.all_measures(self.user)
        self.assertEqual(m["gross_purchases"].value, Decimal("100.00"))

    def test_archived_and_deleted_rows_never_re_enter(self):
        t = self._txn(-100, primary="FOOD_AND_DRINK")
        dupe = self._txn(-100, primary="FOOD_AND_DRINK")
        dupe.status = "deleted"
        dupe.save(update_fields=["status"])
        m = M.all_measures(self.user)
        self.assertEqual(m["gross_purchases"].value, Decimal("100.00"))
