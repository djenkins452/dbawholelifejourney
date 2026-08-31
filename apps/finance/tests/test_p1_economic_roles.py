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
                      primary="GENERAL_MERCHANDISE",
                      detailed="GENERAL_MERCHANDISE_REFUND")
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
        self.assertEqual(assignment.reason, "ambiguous_credit")

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
                  primary="GENERAL_MERCHANDISE",
                  detailed="GENERAL_MERCHANDISE_REFUND")              # refund
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
        """A zero that means "not built yet" must never read as "none exist".

        Both measures that once lived here have graduated: `controllable_spending`
        when P2 landed, `recurring_obligations` when P3 did. Each now computes from
        real user decisions, and each keeps its own honesty test in its own file —
        `test_controllability.py` and `test_recurring.py`. The empty list is the point:
        no measure is currently reporting a placeholder zero as if it were a fact.
        """
        placeholders = []
        for name in M.ALL_MEASURES:
            result = self.m[name]
            if result.value == Decimal("0.00") and not result.inputs_missing \
                    and result.confidence == "low":
                placeholders.append(name)
        self.assertEqual(placeholders, [],
                         "a zero with no named missing input reads as a fact")


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

    def test_the_role_field_has_a_named_set_of_owners(self):
        """Shadow mode is over; uncontrolled sprawl is still forbidden.

        While P1 was inert this asserted that NOTHING read `economic_role` — absence of
        a reader was the activation gate. Activation deliberately added readers, so the
        guard becomes an allow-list: the role is written in exactly one place, read
        through `finance_calc`, and reached elsewhere only through that seam.

        Adding a file here should feel like a decision. If a view or a template starts
        classifying transactions for itself, this fails, and it should.
        """
        import subprocess
        out = subprocess.run(
            ["grep", "-rln", "economic_role", "apps/", "templates/"],
            capture_output=True, text=True).stdout.split()
        allowed = {
            "apps/finance/models.py",
            "apps/finance/services/finance_calc/roles.py",
            "apps/finance/services/finance_calc/measures.py",
            "apps/finance/services/finance_calc/dry_run.py",
            "apps/finance/services/finance_calc/backfill.py",
            # The sanctioned write path for newly synced rows. It NAMES the role but
            # never decides one — it delegates to `backfill.classify_one`.
            "apps/finance/services/sync_service.py",
            "apps/finance/tests/test_p1_economic_roles.py",

            "apps/finance/tests/test_controllability.py",
            "apps/finance/tests/test_recurring.py",
            "apps/finance/tests/test_cos_evidence.py",
            "apps/finance/tests/test_payoff.py",
            "apps/finance/tests/test_opportunities.py",
            # The review queue is where a person RESOLVES a held row, so it writes the
            # role — through the same user-authority rule everything else obeys.
            "apps/finance/views_money.py",
            "apps/finance/page_summaries_money.py",
            "apps/finance/services/finance_calc/cos_evidence.py",
            "apps/finance/services/finance_calc/pairing_rehearsal.py",
            "apps/finance/services/transfer_detection.py",
            "apps/finance/tests/test_liability_pairing.py",
            "apps/finance/tests/test_spending_bridge.py",
            "apps/finance/tests/test_net_worth.py",
            "apps/finance/services/finance_calc/review_queue.py",
            "apps/finance/tests/test_review_queue.py",
            "apps/finance/services/finance_calc/data_health.py",
            "apps/finance/tasks_intelligence.py",
            "apps/finance/tests/test_scheduled_intelligence.py",
            "apps/finance/tests/test_money_pages_complete.py",
            "apps/finance/tests/test_outcomes.py",
            "apps/finance/tests/test_forecast.py",
            "apps/finance/tests/test_debt_usability.py",
            "apps/finance/tests/test_money_workspaces.py",
            # The review queue template renders the CURRENT role in its select so the
            # person can see what WLJ decided before overriding it. It reads the field;
            # it does not decide one.
            "templates/finance/money_review.html",
        }
        unexpected = [p for p in out
                      if p not in allowed and "migrations" not in p]
        self.assertEqual(unexpected, [],
                         "classify through finance_calc; do not read the raw field")

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


class BorrowedMoneyIsNotARefundTests(RoleBase):
    """The first defect the 2026-08-30 rehearsal caught, and its fix.

    `transfer_detection._looks_like_refund` calls ANY credit that is neither a transfer
    nor INCOME a refund. That is a reasonable answer to *its* question and a dangerous
    one to ours: 259,531.55 of loan disbursements were proposed as refunds against
    335,225.50 of purchases, and net spending went negative in 9 of 25 months. A refund
    now needs evidence.
    """

    def test_a_loan_disbursement_is_borrowing_not_a_refund(self):
        t = self._txn(5000, primary="LOAN_DISBURSEMENTS")
        t.transfer_kind = Transaction.TRANSFER_KIND_REFUND  # what upstream decided
        self.assertEqual(self._role(t), Transaction.ROLE_LOAN_PROCEEDS)

    def test_a_cash_advance_is_borrowing(self):
        t = self._txn(1200, primary="TRANSFER_IN",
                      detailed="TRANSFER_IN_CASH_ADVANCES_AND_LOANS")
        self.assertEqual(self._role(t), Transaction.ROLE_LOAN_PROCEEDS)

    def test_borrowing_is_cash_in_but_never_income(self):
        self._txn(5000, primary="LOAN_DISBURSEMENTS")
        m = M.all_measures(self.user)
        self.assertEqual(m["income"].value, Decimal("0.00"))
        self.assertEqual(m["cash_inflow"].value, Decimal("5000.00"))
        self.assertEqual(m["cash_inflow"].components["loan_proceeds"],
                         Decimal("5000.00"))

    def test_borrowing_does_not_offset_spending(self):
        self._txn(-300, primary="FOOD_AND_DRINK")
        self._txn(5000, primary="LOAN_DISBURSEMENTS")
        m = M.all_measures(self.user)
        self.assertEqual(m["net_spending"].value, Decimal("300.00"))

    def test_a_generic_credit_is_held_not_called_a_refund(self):
        t = self._txn(220, primary="GENERAL_MERCHANDISE")
        t.transfer_kind = Transaction.TRANSFER_KIND_REFUND
        a = R.classify(t)
        self.assertEqual(a.role, Transaction.ROLE_UNCERTAIN)
        self.assertEqual(a.reason, "ambiguous_credit")

    def test_a_generic_credit_offsets_nothing(self):
        self._txn(-300, primary="FOOD_AND_DRINK")
        self._txn(220, primary="GENERAL_MERCHANDISE")
        m = M.all_measures(self.user)
        self.assertEqual(m["net_spending"].value, Decimal("300.00"))
        self.assertEqual(m["income"].value, Decimal("0.00"))

    def test_an_explicit_provider_refund_still_offsets(self):
        self._txn(-300, primary="GENERAL_MERCHANDISE")
        t = self._txn(75, primary="GENERAL_MERCHANDISE",
                      detailed="GENERAL_MERCHANDISE_REFUND")
        self.assertEqual(self._role(t), Transaction.ROLE_REFUND)
        self.assertEqual(M.all_measures(self.user)["net_spending"].value,
                         Decimal("225.00"))

    def test_a_chargeback_is_a_reversal(self):
        t = self._txn(75, primary="GENERAL_MERCHANDISE",
                      detailed="GENERAL_MERCHANDISE_CHARGEBACK")
        self.assertEqual(self._role(t), Transaction.ROLE_REVERSAL)

    def test_a_proven_link_to_the_purchase_is_the_strongest_evidence(self):
        original = self._txn(-300, primary="GENERAL_MERCHANDISE")
        t = self._txn(300, primary="GENERAL_MERCHANDISE")
        t.refund_of = original
        a = R.classify(t)
        self.assertEqual(a.role, Transaction.ROLE_REFUND)
        self.assertEqual(a.reason, "linked_refund_of_purchase")
        self.assertEqual(a.source, Transaction.ROLE_SOURCE_PAIRING)

    def test_net_spending_cannot_go_negative_on_borrowing_alone(self):
        """The exact production shape: a large draw against modest purchases."""
        self._txn(-500, primary="FOOD_AND_DRINK")
        for _ in range(3):
            t = self._txn(9000, primary="LOAN_DISBURSEMENTS")
            t.transfer_kind = Transaction.TRANSFER_KIND_REFUND
            t.save()
        self.assertEqual(M.all_measures(self.user)["net_spending"].value,
                         Decimal("500.00"))


class MortgageIsNotACardPaymentTests(RoleBase):
    """The second defect the rehearsal caught.

    `transfer_detection._transfer_kind` labels ANY transfer touching a liability a
    credit-card payment. For a card that is right — the purchases it settles were
    already counted. For a mortgage it removed the payment from spending AND from debt
    service, so the household appeared to service no mortgage at all.
    """

    def setUp(self):
        super().setUp()
        self.mortgage = FinancialAccount.objects.create(
            user=self.user, name="Mortgage", account_type="mortgage",
            current_balance=Decimal("-200000"))

    def _paid(self, liability, amount="2000"):
        """A matched payment: cash out of checking, credit onto the liability."""
        credit = self._txn(amount, account=liability,
                           state=Transaction.TRANSFER_STATE_CONFIRMED,
                           kind=Transaction.TRANSFER_KIND_CARD_PAYMENT,
                           by=Transaction.TRANSFER_BY_PAIRING,
                           primary="TRANSFER_IN")
        cash = self._txn("-" + amount, state=Transaction.TRANSFER_STATE_CONFIRMED,
                         kind=Transaction.TRANSFER_KIND_CARD_PAYMENT,
                         by=Transaction.TRANSFER_BY_PAIRING,
                         primary="LOAN_PAYMENTS")
        cash.transfer_pair = credit
        cash.save(update_fields=["transfer_pair"])
        return cash, credit

    def test_a_mortgage_payment_is_debt_service_from_the_cash_side(self):
        cash, _ = self._paid(self.mortgage)
        self.assertEqual(self._role(cash), Transaction.ROLE_DEBT_SERVICE)

    def test_a_mortgage_payment_is_debt_service_from_the_liability_side(self):
        _, credit = self._paid(self.mortgage)
        self.assertEqual(self._role(credit), Transaction.ROLE_DEBT_SERVICE)

    def test_a_real_card_payment_is_still_a_card_payment(self):
        cash, credit = self._paid(self.card)
        self.assertEqual(self._role(cash), Transaction.ROLE_CARD_PAYMENT)
        self.assertEqual(self._role(credit), Transaction.ROLE_CARD_PAYMENT)

    def test_the_payment_is_counted_once_not_twice(self):
        self._paid(self.mortgage, "2000")
        m = M.all_measures(self.user)
        self.assertEqual(m["debt_service"].value, Decimal("2000.00"))

    def test_the_cash_movement_is_still_visible(self):
        self._paid(self.mortgage, "2000")
        m = M.all_measures(self.user)
        self.assertEqual(m["cash_outflow"].components["debt_service"],
                         Decimal("2000.00"))

    def test_a_mortgage_payment_is_not_consumer_spending(self):
        self._paid(self.mortgage, "2000")
        self._txn(-40, primary="FOOD_AND_DRINK")
        m = M.all_measures(self.user)
        self.assertEqual(m["net_spending"].value, Decimal("40.00"))

    def test_an_unpaired_liability_credit_is_still_counted(self):
        """When the funding account is not connected, the visible leg is all there is."""
        self._txn(1500, account=self.mortgage,
                  state=Transaction.TRANSFER_STATE_CONFIRMED,
                  kind=Transaction.TRANSFER_KIND_CARD_PAYMENT,
                  by=Transaction.TRANSFER_BY_PROVIDER, primary="TRANSFER_IN")
        self.assertEqual(M.all_measures(self.user)["debt_service"].value,
                         Decimal("1500.00"))

    def test_debt_service_stays_unsplit_and_says_so(self):
        self._paid(self.mortgage, "2000")
        ds = M.all_measures(self.user)["debt_service"]
        self.assertEqual(ds.components["unsplit"], Decimal("2000.00"))
        self.assertEqual(ds.components["principal_known"], Decimal("0.00"))
        self.assertIn("loan_terms", ds.inputs_missing)

    def test_a_student_loan_payment_is_debt_service_too(self):
        loan = FinancialAccount.objects.create(
            user=self.user, name="Student", account_type="student_loan",
            current_balance=Decimal("-9000"))
        cash, _ = self._paid(loan, "300")
        self.assertEqual(self._role(cash), Transaction.ROLE_DEBT_SERVICE)


class CashTruthTests(RoleBase):
    """Uncertainty may cost a measure its number. It may never cost the cash its row."""

    def test_an_uncertain_credit_keeps_its_row_and_its_reason(self):
        t = self._txn(220, primary="GENERAL_MERCHANDISE")
        a = R.classify(t)
        self.assertEqual(a.role, Transaction.ROLE_UNCERTAIN)
        self.assertTrue(a.reason)
        self.assertEqual(a.confidence, Transaction.ROLE_CONFIDENCE_LOW)

    def test_a_cash_withdrawal_leaves_the_account_but_buys_nothing_known(self):
        t = self._txn(-200, primary="TRANSFER_OUT", detailed="TRANSFER_OUT_ATM")
        self.assertEqual(self._role(t), Transaction.ROLE_CASH_WITHDRAWAL)
        m = M.all_measures(self.user)
        self.assertEqual(m["cash_outflow"].components["cash_withdrawals"],
                         Decimal("200.00"))
        self.assertEqual(m["net_spending"].value, Decimal("0.00"))

    def test_an_unmatched_transfer_candidate_keeps_its_cash_movement(self):
        self._txn(-500, state=Transaction.TRANSFER_STATE_CANDIDATE,
                  primary="TRANSFER_OUT")
        m = M.all_measures(self.user)
        self.assertEqual(m["net_spending"].value, Decimal("0.00"))
        self.assertEqual(m["net_spending"].exclusions["uncertain"], Decimal("500.00"))

    def test_every_uncertain_row_can_explain_itself(self):
        self._txn(220, primary="GENERAL_MERCHANDISE")
        self._txn(-500, state=Transaction.TRANSFER_STATE_CANDIDATE, primary="TRANSFER_OUT")
        for txn, a in R.classify_many(M._population(self.user)):
            if a.role == Transaction.ROLE_UNCERTAIN:
                self.assertIn(a.reason,
                              {"ambiguous_credit", "unmatched_transfer_candidate",
                               "zero_amount"})


class UserRoleAuthorityTests(RoleBase):
    """A decision the person made is not a hypothesis to be re-tested."""

    def test_a_user_set_role_survives_reclassification(self):
        t = self._txn(220, primary="GENERAL_MERCHANDISE")
        t.economic_role = Transaction.ROLE_REIMBURSEMENT
        t.role_source = Transaction.ROLE_SOURCE_USER
        t.role_reason = "danny_said_so"
        t.save()
        a = R.classify(t)
        self.assertEqual(a.role, Transaction.ROLE_REIMBURSEMENT)
        self.assertEqual(a.source, Transaction.ROLE_SOURCE_USER)

    def test_a_user_reimbursement_offsets_spending(self):
        self._txn(-300, primary="GENERAL_MERCHANDISE")
        t = self._txn(100, primary="GENERAL_MERCHANDISE")
        t.economic_role = Transaction.ROLE_REIMBURSEMENT
        t.role_source = Transaction.ROLE_SOURCE_USER
        t.save()
        self.assertEqual(M.all_measures(self.user)["net_spending"].value,
                         Decimal("200.00"))


class BackfillTests(RoleBase):
    """Writing four thousand financial rows is only safe if doing it twice is safe."""

    def setUp(self):
        super().setUp()
        from apps.finance.services.finance_calc import backfill
        self.backfill = backfill
        self._txn(-50, primary="FOOD_AND_DRINK")
        self._txn(3000, primary="INCOME")
        self._txn(5000, primary="LOAN_DISBURSEMENTS")

    def test_a_dry_run_writes_nothing(self):
        report = self.backfill.run(self.user, commit=False)
        self.assertEqual(report["scanned"], 3)
        self.assertEqual(report["written"], 0)
        self.assertEqual(
            Transaction.objects.filter(economic_role__isnull=False).count(), 0)

    def test_a_committed_run_classifies_every_row(self):
        report = self.backfill.run(self.user, commit=True)
        self.assertEqual(report["written"], 3)
        self.assertEqual(report["after"]["unclassified"], 0)
        self.assertEqual(report["before"]["classified"], 0)

    def test_running_it_again_changes_nothing(self):
        self.backfill.run(self.user, commit=True)
        second = self.backfill.run(self.user, commit=True)
        self.assertEqual(second["written"], 0)
        self.assertEqual(second["unchanged"], 3)

    def test_it_is_reversible(self):
        self.backfill.run(self.user, commit=True)
        self.backfill.clear(self.user, commit=True)
        self.assertEqual(
            Transaction.objects.filter(economic_role__isnull=False).count(), 0)

    def test_reversal_leaves_a_user_decision_alone(self):
        t = self._txn(120, primary="GENERAL_MERCHANDISE")
        t.economic_role = Transaction.ROLE_REIMBURSEMENT
        t.role_source = Transaction.ROLE_SOURCE_USER
        t.save()
        self.backfill.run(self.user, commit=True)
        self.backfill.clear(self.user, commit=True)
        t.refresh_from_db()
        self.assertEqual(t.economic_role, Transaction.ROLE_REIMBURSEMENT)

    def test_the_backfill_never_overwrites_a_user_decision(self):
        t = self._txn(120, primary="GENERAL_MERCHANDISE")
        t.economic_role = Transaction.ROLE_REIMBURSEMENT
        t.role_source = Transaction.ROLE_SOURCE_USER
        t.save()
        report = self.backfill.run(self.user, commit=True)
        t.refresh_from_db()
        self.assertEqual(t.economic_role, Transaction.ROLE_REIMBURSEMENT)
        self.assertEqual(report["user_protected"], 1)

    def test_it_records_before_and_after_counts_and_checkpoints(self):
        report = self.backfill.run(self.user, commit=True, batch_size=2)
        self.assertEqual(report["before"]["unclassified"], 3)
        self.assertEqual(report["after"]["classified"], 3)
        self.assertGreaterEqual(len(report["checkpoints"]), 2)

    def test_the_source_transaction_is_not_edited(self):
        """A role is an added opinion, never a change to the record."""
        before = list(Transaction.objects.values_list("id", "amount", "date",
                                                      "description"))
        self.backfill.run(self.user, commit=True)
        self.assertEqual(
            before,
            list(Transaction.objects.values_list("id", "amount", "date",
                                                 "description")))


class NewTransactionsAreClassifiedTests(RoleBase):
    """A partly classified population is worse than an unclassified one.

    Unclassified is visibly absent. Partly classified is silently incomplete — the
    totals look finished and are not. So a row synced after activation is classified on
    the same pass that stores it.
    """

    def test_the_sync_path_classifies_on_arrival(self):
        from apps.finance.services import sync_service
        source = open(sync_service.__file__).read()
        self.assertIn("_assign_economic_role", source)
        self.assertIn("classify_one", source)

    def test_classify_one_persists_and_is_idempotent(self):
        from apps.finance.services.finance_calc import backfill
        t = self._txn(-50, primary="FOOD_AND_DRINK")
        backfill.classify_one(t)
        t.refresh_from_db()
        self.assertEqual(t.economic_role, Transaction.ROLE_PURCHASE)
        self.assertEqual(t.role_classifier_version, R.CLASSIFIER_VERSION)
        stamped = t.role_classified_at
        backfill.classify_one(t)
        t.refresh_from_db()
        self.assertEqual(t.role_classified_at, stamped, "no needless rewrite")

    def test_classify_one_refuses_to_touch_a_user_decision(self):
        from apps.finance.services.finance_calc import backfill
        t = self._txn(120, primary="GENERAL_MERCHANDISE")
        t.economic_role = Transaction.ROLE_REIMBURSEMENT
        t.role_source = Transaction.ROLE_SOURCE_USER
        t.save()
        self.assertIsNone(backfill.classify_one(t))
        t.refresh_from_db()
        self.assertEqual(t.economic_role, Transaction.ROLE_REIMBURSEMENT)


class LiabilityCreditTests(RoleBase):
    """The third defect, found by the 2026-08-31 rehearsal on real history.

    249,246.70 of credits on a credit card carried the provider category
    LOAN_DISBURSEMENTS — which reads as borrowing — and every one matched, to the cent
    and to the month, a payment leaving chequing that the same provider called a
    credit-card payment. Removing them made cash inflow equal income plus refunds
    exactly: the arithmetic of money that never entered the household.

    The provider category cannot separate "a payment arrived" from "I borrowed more"
    on a revolving account. The instrument can.
    """

    def setUp(self):
        super().setUp()
        self.mortgage = FinancialAccount.objects.create(
            user=self.user, name="Mortgage", account_type="mortgage",
            current_balance=Decimal("-200000"))
        self.loan = FinancialAccount.objects.create(
            user=self.user, name="Auto", account_type="loan",
            current_balance=Decimal("-20000"))

    def test_a_credit_on_a_closed_end_loan_can_only_be_a_payment(self):
        t = self._txn(2388.95, account=self.mortgage, primary="TRANSFER_IN",
                      detailed="TRANSFER_IN_ACCOUNT_TRANSFER")
        a = R.classify(t)
        self.assertEqual(a.role, Transaction.ROLE_DEBT_SERVICE)
        self.assertEqual(a.reason, "payment_received_on_closed_end_loan")

    def test_the_same_holds_for_an_instalment_loan(self):
        t = self._txn(500, account=self.loan, primary="TRANSFER_IN")
        self.assertEqual(self._role(t), Transaction.ROLE_DEBT_SERVICE)

    def test_an_unmatched_credit_on_a_card_is_held_not_called_borrowing(self):
        t = self._txn(15000, account=self.card, primary="LOAN_DISBURSEMENTS",
                      detailed="LOAN_DISBURSEMENTS_OTHER_DISBURSEMENT")
        a = R.classify(t)
        self.assertEqual(a.role, Transaction.ROLE_UNCERTAIN)
        self.assertEqual(a.reason, "unmatched_liability_credit")

    def test_it_does_not_inflate_cash_inflow(self):
        self._txn(15000, account=self.card, primary="LOAN_DISBURSEMENTS",
                  detailed="LOAN_DISBURSEMENTS_OTHER_DISBURSEMENT")
        self._txn(3000, primary="INCOME")
        m = M.all_measures(self.user)
        self.assertEqual(m["cash_inflow"].value, Decimal("3000.00"))
        self.assertEqual(m["income"].value, Decimal("3000.00"))

    def test_a_loan_that_funds_a_cash_account_is_still_borrowing(self):
        """The role is not abolished — it is confined to where it can be true."""
        t = self._txn(9000, primary="LOAN_DISBURSEMENTS",
                      detailed="LOAN_DISBURSEMENTS_OTHER_DISBURSEMENT")
        self.assertEqual(self._role(t), Transaction.ROLE_LOAN_PROCEEDS)
        self.assertEqual(M.all_measures(self.user)["cash_inflow"].value,
                         Decimal("9000.00"))


class CashMovementSurvivesUncertaintyTests(RoleBase):
    """Not knowing WHY the money moved is not doubt about WHETHER it moved."""

    def test_an_unresolved_outflow_still_leaves_the_account(self):
        self._txn(-2388.95, state=Transaction.TRANSFER_STATE_CANDIDATE,
                  primary="TRANSFER_OUT", detailed="TRANSFER_OUT_WITHDRAWAL")
        m = M.all_measures(self.user)
        self.assertEqual(m["cash_outflow"].value, Decimal("2388.95"))
        self.assertEqual(m["cash_outflow"].components["unresolved_movement"],
                         Decimal("2388.95"))

    def test_but_it_is_not_spending(self):
        self._txn(-2388.95, state=Transaction.TRANSFER_STATE_CANDIDATE,
                  primary="TRANSFER_OUT")
        self.assertEqual(M.all_measures(self.user)["net_spending"].value,
                         Decimal("0.00"))

    def test_an_unresolved_credit_to_a_cash_account_is_money_received(self):
        self._txn(5392.80, primary="TRANSFER_IN", detailed="TRANSFER_IN_DEPOSIT")
        m = M.all_measures(self.user)
        self.assertEqual(m["cash_inflow"].value, Decimal("5392.80"))
        self.assertEqual(m["income"].value, Decimal("0.00"))

    def test_an_unresolved_credit_on_a_LIABILITY_is_not_cash_received(self):
        self._txn(15000, account=self.card, primary="LOAN_DISBURSEMENTS")
        self.assertEqual(M.all_measures(self.user)["cash_inflow"].value,
                         Decimal("0.00"))

    def test_the_cash_measures_still_reconcile(self):
        self._txn(-2388.95, state=Transaction.TRANSFER_STATE_CANDIDATE,
                  primary="TRANSFER_OUT")
        self._txn(5392.80, primary="TRANSFER_IN", detailed="TRANSFER_IN_DEPOSIT")
        self._txn(-50, primary="FOOD_AND_DRINK")
        self._txn(3000, primary="INCOME")
        self.assertTrue(M.reconcile(M.all_measures(self.user))["all_hold"])


class IncomeOnALiabilityTests(RoleBase):
    """Card rewards land as a credit on a card. They are still earnings.

    The liability-credit rule exists because the provider cannot tell a payment from a
    draw. "This is income" is a different claim, and is not confusable with either — so
    it is exempt, or the rule would quietly eat real income.
    """

    def test_provider_income_on_a_card_is_still_income(self):
        t = self._txn(45, account=self.card, primary="INCOME",
                      detailed="INCOME_OTHER_INCOME")
        self.assertEqual(self._role(t), Transaction.ROLE_INCOME)

    def test_it_counts_as_income_in_the_measures(self):
        self._txn(45, account=self.card, primary="INCOME")
        self.assertEqual(M.all_measures(self.user)["income"].value, Decimal("45.00"))

    def test_a_disbursement_on_the_same_card_is_still_held(self):
        t = self._txn(15000, account=self.card, primary="LOAN_DISBURSEMENTS")
        self.assertEqual(self._role(t), Transaction.ROLE_UNCERTAIN)
