# ==============================================================================
# File: apps/finance/tests/test_liability_pairing.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: ONE pairing authority — full population, both legs, no guessing.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""A wrong pair silently merges two unrelated movements.

Two defects are closed here and each gets its own tests. The 2,000-row cap dropped the
most recent third of a long history — the exact place unpaired legs collect. And
`_assess` read the OneToOne in one direction, so whichever leg did not carry the column
was never recognised as paired, and a settled card payment stayed classified as an
ordinary purchase.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import FinancialAccount, Transaction
from apps.finance.services import transfer_detection as TD
from apps.finance.services.finance_calc import measures as M
from apps.finance.services.finance_calc import pairing_rehearsal as PR
from apps.finance.tests.test_p1_economic_roles import RoleBase

User = get_user_model()

JAN = date(2026, 1, 15)


class PairingBase(RoleBase):
    def setUp(self):
        super().setUp()
        self.mortgage = FinancialAccount.objects.create(
            user=self.user, name="Mortgage", account_type="mortgage",
            current_balance=Decimal("-200000"))

    def _held_credit(self, amount, *, account=None, on=JAN):
        """A credit on a liability, held exactly as production holds them."""
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


class BothLegsTests(PairingBase):
    """Defect 2: a pair must be visible from EITHER side."""

    def setUp(self):
        super().setUp()
        self.credit = self._held_credit(1500)
        self.payment = self._payment(1500)
        TD.pair_all(self.user)
        self.credit.refresh_from_db()
        self.payment.refresh_from_db()

    def test_the_leg_holding_the_column_sees_its_pair(self):
        holder = self.payment if self.payment.transfer_pair_id else self.credit
        self.assertIsNotNone(TD.paired_counterpart(holder))

    def test_the_leg_WITHOUT_the_column_also_sees_its_pair(self):
        other = self.credit if self.payment.transfer_pair_id else self.payment
        self.assertIsNone(other.transfer_pair_id)
        self.assertIsNotNone(TD.paired_counterpart(other),
                             "reading one direction is how a card payment became "
                             "spending")

    def test_both_legs_are_confirmed_transfers(self):
        for leg in (self.credit, self.payment):
            with self.subTest(leg=leg.pk):
                self.assertEqual(leg.transfer_state,
                                 Transaction.TRANSFER_STATE_CONFIRMED)

    def test_the_kind_is_decided_by_the_pair_not_by_one_leg(self):
        """The chequing side of a card payment is not a plain internal transfer."""
        for leg in (self.credit, self.payment):
            with self.subTest(leg=leg.pk):
                self.assertEqual(leg.transfer_kind,
                                 Transaction.TRANSFER_KIND_CARD_PAYMENT)

    def test_an_unpaired_row_reports_no_counterpart(self):
        lonely = self._txn(-40, primary="FOOD_AND_DRINK")
        self.assertIsNone(TD.paired_counterpart(lonely))
        self.assertFalse(TD.is_paired(lonely))


class FullPopulationTests(PairingBase):
    """Defect 1: never silently stop reading."""

    def test_the_default_pass_reads_everything(self):
        for i in range(30):
            self._payment(100 + i, on=JAN + timedelta(days=i))
            self._held_credit(100 + i, on=JAN + timedelta(days=i))
        report = TD.pair_all(self.user)
        self.assertFalse(report["truncated"])
        self.assertEqual(report["skipped_over_limit"], 0)
        self.assertEqual(report["paired"], 30)

    def test_a_deliberate_limit_is_reported_never_silent(self):
        for i in range(10):
            self._payment(100 + i, on=JAN + timedelta(days=i))
            self._held_credit(100 + i, on=JAN + timedelta(days=i))
        report = TD.pair_all(self.user, limit=5)
        self.assertTrue(report["truncated"])
        self.assertGreater(report["skipped_over_limit"], 0)

    def test_the_report_exposes_every_count(self):
        self._payment(1500)
        self._held_credit(1500)
        report = TD.pair_all(self.user)
        for key in ("population", "eligible_outflows", "already_paired", "proposed",
                    "ambiguous", "unmatched", "paired", "lost_race",
                    "skipped_over_limit", "truncated", "skipped_user_confirmed"):
            with self.subTest(key=key):
                self.assertIn(key, report)

    def test_the_legacy_entry_point_no_longer_caps_at_2000(self):
        import inspect
        signature = inspect.signature(TD.pair_transfers)
        self.assertIsNone(signature.parameters["limit"].default)

    def test_batching_does_not_change_the_outcome(self):
        for i in range(12):
            self._payment(200 + i, on=JAN + timedelta(days=i))
            self._held_credit(200 + i, on=JAN + timedelta(days=i))
        report = TD.pair_all(self.user, batch_size=3)
        self.assertEqual(report["paired"], 12)


class RefusalTests(PairingBase):
    """Pairing MORE is only an improvement if pairing WRONGLY stays impossible."""

    def test_ambiguity_is_reported_not_resolved(self):
        self._held_credit(1500)
        self._payment(1500, on=JAN)
        self._payment(1500, on=JAN + timedelta(days=1))
        report = TD.pair_all(self.user)
        self.assertEqual(report["paired"], 0)
        self.assertGreaterEqual(report["ambiguous"], 1)

    def test_one_counterpart_is_never_reused(self):
        """Two identical credits and one payment is a contest, not a pair."""
        self._held_credit(1500, on=JAN)
        self._held_credit(1500, on=JAN)
        self._payment(1500)
        report = TD.pair_all(self.user)
        self.assertEqual(report["paired"], 0)
        self.assertEqual(
            Transaction.objects.filter(
                user=self.user, transfer_pair__isnull=False).count(), 0)

    def test_a_row_is_never_paired_twice(self):
        self._held_credit(1500)
        self._payment(1500)
        TD.pair_all(self.user)
        self.assertEqual(
            Transaction.objects.filter(
                user=self.user, transfer_pair__isnull=False).count(), 1,
            "one canonical link per pair")

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
        self.assertEqual(TD.pair_all(self.user)["paired"], 0)

    def test_a_user_confirmed_row_is_never_repaired(self):
        credit = self._held_credit(1500)
        credit.transfer_classified_by = Transaction.TRANSFER_BY_USER
        credit.transfer_state = Transaction.TRANSFER_STATE_NOT_TRANSFER
        credit.save()
        self._payment(1500)
        report = TD.pair_all(self.user)
        self.assertEqual(report["paired"], 0)
        credit.refresh_from_db()
        self.assertEqual(credit.transfer_state,
                         Transaction.TRANSFER_STATE_NOT_TRANSFER)

    def test_the_same_account_cannot_pair_with_itself(self):
        self._txn(-500, on=JAN, primary="TRANSFER_OUT")
        self._txn(500, on=JAN, primary="TRANSFER_IN")
        self.assertEqual(TD.pair_all(self.user)["paired"], 0)

    def test_outside_the_window_is_not_a_pair(self):
        self._held_credit(1500, on=JAN)
        self._payment(1500, on=JAN + timedelta(days=30))
        self.assertEqual(TD.pair_all(self.user)["paired"], 0)


class IdempotenceTests(PairingBase):
    def test_a_second_run_changes_nothing(self):
        for i in range(5):
            self._payment(300 + i, on=JAN + timedelta(days=i))
            self._held_credit(300 + i, on=JAN + timedelta(days=i))
        first = TD.pair_all(self.user)
        second = TD.pair_all(self.user)
        self.assertEqual(first["paired"], 5)
        self.assertEqual(second["paired"], 0)
        self.assertEqual(second["proposed"], 0)

    def test_already_paired_rows_are_counted_as_such(self):
        self._payment(1500)
        self._held_credit(1500)
        TD.pair_all(self.user)
        self.assertEqual(TD.pair_all(self.user)["already_paired"], 2)


class RehearsalTests(PairingBase):
    def test_the_rehearsal_writes_nothing(self):
        self._held_credit(1500)
        self._payment(1500)
        before = Transaction.objects.filter(transfer_pair__isnull=False).count()
        TD.rehearse_pairing(self.user)
        self.assertEqual(
            Transaction.objects.filter(transfer_pair__isnull=False).count(), before)

    def test_it_predicts_exactly_what_the_apply_pass_does(self):
        for i in range(4):
            self._payment(400 + i, on=JAN + timedelta(days=i))
            self._held_credit(400 + i, on=JAN + timedelta(days=i))
        predicted = TD.rehearse_pairing(self.user)["counts"]["proposed"]
        self.assertEqual(TD.pair_all(self.user)["paired"], predicted)

    def test_it_reports_ambiguity_without_resolving_it(self):
        self._held_credit(1500)
        self._payment(1500, on=JAN)
        self._payment(1500, on=JAN + timedelta(days=1))
        report = TD.rehearse_pairing(self.user)
        self.assertGreaterEqual(report["counts"]["ambiguous"], 1)
        self.assertEqual(report["counts"]["proposed"], 0)

    def test_the_report_carries_no_descriptions(self):
        self._held_credit(1500)
        payment = self._payment(1500)
        payment.description = "ACME BANK PAYMENT 9931"
        payment.save()
        self.assertNotIn("ACME", str(TD.rehearse_pairing(self.user)))

    def test_coverage_no_longer_advertises_a_cap(self):
        coverage = TD.pairing_coverage(self.user)
        self.assertTrue(coverage["reads_full_population"])
        self.assertNotIn("pass_reads_at_most", coverage)

    def test_the_diagnostic_module_uses_the_authority_definition(self):
        self._held_credit(1500)
        self._payment(1500)
        TD.pair_all(self.user)
        self.assertEqual(PR.run(self.user)["would_pair"], 0)


class MeasureImpactTests(PairingBase):
    """Pairing changes what things MEAN. It must not change what moved."""

    def test_pairing_turns_the_credit_into_a_card_payment(self):
        from apps.finance.services.finance_calc import roles as R
        credit = self._held_credit(1500)
        self._payment(1500)
        TD.pair_all(self.user)
        credit.refresh_from_db()
        self.assertEqual(R.classify(credit).role, Transaction.ROLE_CARD_PAYMENT)

    def test_the_payment_leg_is_not_spending(self):
        from apps.finance.services.finance_calc import backfill
        self._held_credit(1500)
        self._payment(1500)
        self._txn(-40, primary="FOOD_AND_DRINK")
        TD.pair_all(self.user)
        backfill.run(self.user, commit=True)
        self.assertEqual(M.all_measures(self.user)["net_spending"].value,
                         Decimal("40.00"))

    def test_a_mortgage_payment_stays_debt_service(self):
        from apps.finance.services.finance_calc import backfill
        self._held_credit(2388.95, account=self.mortgage)
        self._payment(2388.95)
        TD.pair_all(self.user)
        backfill.run(self.user, commit=True)
        self.assertEqual(M.all_measures(self.user)["debt_service"].value,
                         Decimal("2388.95"))

    def test_reconciliation_still_holds_after_pairing(self):
        from apps.finance.services.finance_calc import backfill
        self._held_credit(1500)
        self._payment(1500)
        self._txn(-40, primary="FOOD_AND_DRINK")
        self._txn(3000, primary="INCOME")
        TD.pair_all(self.user)
        backfill.run(self.user, commit=True)
        self.assertTrue(M.reconcile(M.all_measures(self.user))["all_hold"])

    def test_pairing_never_turns_borrowing_into_income(self):
        from apps.finance.services.finance_calc import backfill
        self._held_credit(1500)
        TD.pair_all(self.user)
        backfill.run(self.user, commit=True)
        self.assertEqual(M.all_measures(self.user)["income"].value, Decimal("0.00"))

    def test_a_user_decision_survives_pairing_and_reclassification(self):
        from apps.finance.services.finance_calc import backfill
        credit = self._held_credit(1500)
        credit.economic_role = Transaction.ROLE_REIMBURSEMENT
        credit.role_source = Transaction.ROLE_SOURCE_USER
        credit.save()
        self._payment(1500)
        TD.pair_all(self.user)
        backfill.run(self.user, commit=True)
        credit.refresh_from_db()
        self.assertEqual(credit.economic_role, Transaction.ROLE_REIMBURSEMENT)


class QueryCostTests(PairingBase):
    def test_pairing_does_not_issue_one_query_per_row(self):
        """Deciding "already paired?" reads the reverse OneToOne — lazily that is N+1."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        for i in range(40):
            self._payment(500 + i, on=JAN + timedelta(days=i))
            self._held_credit(500 + i, on=JAN + timedelta(days=i))

        with CaptureQueriesContext(connection) as captured:
            TD.rehearse_pairing(self.user)
        self.assertLess(len(captured.captured_queries), 15,
                        "the rehearsal must not scale its queries with the ledger")


class MutualUniquenessTests(PairingBase):
    """A match must be unambiguous from BOTH sides, or it is a guess.

    Checking only the outflow's view makes pairing order-dependent: one credit that
    could belong to either of two payments gets attached to whichever payment happens to
    be processed first.
    """

    def test_two_payments_and_one_credit_is_ambiguous(self):
        self._held_credit(1500)
        self._payment(1500, on=JAN)
        self._payment(1500, on=JAN + timedelta(days=1))
        report = TD.pair_all(self.user)
        self.assertEqual(report["paired"], 0)
        self.assertEqual(report["ambiguous"], 2,
                         "both payments see the same contested credit")

    def test_two_credits_and_one_payment_is_ambiguous(self):
        self._held_credit(1500, on=JAN)
        self._held_credit(1500, on=JAN + timedelta(days=1))
        self._payment(1500)
        self.assertEqual(TD.pair_all(self.user)["paired"], 0)

    def test_a_genuinely_unique_match_still_pairs(self):
        self._held_credit(1500)
        self._payment(1500)
        self.assertEqual(TD.pair_all(self.user)["paired"], 1)

    def test_the_outcome_does_not_depend_on_processing_order(self):
        """Same rows, inserted in the opposite order, must give the same answer."""
        self._payment(1500, on=JAN)
        self._payment(1500, on=JAN + timedelta(days=1))
        self._held_credit(1500)
        self.assertEqual(TD.pair_all(self.user)["paired"], 0)

    def test_distinct_amounts_pair_independently(self):
        self._held_credit(1500, on=JAN)
        self._payment(1500, on=JAN)
        self._held_credit(2500, on=JAN)
        self._payment(2500, on=JAN)
        self.assertEqual(TD.pair_all(self.user)["paired"], 2)


class IncomeIsNeverPairedAwayTests(PairingBase):
    """Pairing must never delete earnings.

    A credit the provider calls INCOME, matched to an outflow of the same size, is
    either a transfer the provider mislabelled or a genuine salary that happens to equal
    a payment made days earlier. WLJ cannot tell those apart, and one of the two
    mistakes silently removes real income from every total. So it is held.
    """

    def test_an_income_counterpart_is_held_not_paired(self):
        self._payment(3000)
        self._txn(3000, account=self.savings, on=JAN, primary="INCOME",
                  detailed="INCOME_WAGES")
        report = TD.pair_all(self.user)
        self.assertEqual(report["paired"], 0)
        self.assertEqual(report["held_income_counterpart"], 1)

    def test_income_survives_a_full_pairing_pass(self):
        from apps.finance.services.finance_calc import backfill
        self._payment(3000)
        self._txn(3000, account=self.savings, on=JAN, primary="INCOME",
                  detailed="INCOME_WAGES")
        TD.pair_all(self.user)
        backfill.run(self.user, commit=True)
        self.assertEqual(M.all_measures(self.user)["income"].value,
                         Decimal("3000.00"))

    def test_a_plain_transfer_counterpart_still_pairs(self):
        self._payment(3000)
        self._txn(3000, account=self.savings, on=JAN, primary="TRANSFER_IN")
        self.assertEqual(TD.pair_all(self.user)["paired"], 1)

    def test_the_rehearsal_reports_what_it_held_and_why(self):
        self._payment(3000)
        self._txn(3000, account=self.savings, on=JAN, primary="INCOME")
        report = TD.rehearse_pairing(self.user)
        self.assertEqual(report["counts"]["held_income_counterpart"], 1)
        self.assertEqual(len(report["samples"]["held_income_counterpart"]), 1)


class OneCanonicalPairPredicateTests(TestCase):
    """"Is this row paired?" may be written in exactly one place.

    The second pairing defect was not that someone misunderstood the OneToOne — it was
    that five different modules each wrote `transfer_pair__isnull=False` by hand, so the
    misunderstanding had to be found and fixed five times. Correcting the five readers
    without removing the condition that produced them leaves the sixth free to appear.
    """

    #: The pairing authority defines the predicate; the audit command deliberately
    #: compares the OLD single-signal definition against the new one, which is its
    #: entire purpose.
    ALLOWED = {
        "apps/finance/services/transfer_detection.py",
        "apps/finance/management/commands/finance_population_audit.py",
    }

    def test_no_module_writes_the_pair_predicate_by_hand(self):
        import ast
        from pathlib import Path

        finance_dir = Path(__file__).resolve().parents[1]
        repo_root = finance_dir.parents[1]
        offenders = []

        for path in finance_dir.rglob("*.py"):
            if any(skip in path.parts
                   for skip in ("migrations", "tests", "__pycache__")):
                continue
            rel = path.relative_to(repo_root).as_posix()
            if rel in self.ALLOWED:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                for keyword in node.keywords:
                    name = (keyword.arg or "").split("__")
                    if "transfer_pair" in name or "transfer_counterpart" in name:
                        offenders.append(f"{rel}:{node.lineno} {keyword.arg}")

        self.assertEqual(
            offenders, [],
            "A hand-written pair predicate reappeared. `transfer_pair` is a OneToOne to "
            "self, so only one leg carries the column and this reads as 'is this the "
            f"holding leg', not 'is this paired'. Use paired_q(): {offenders}")

    def test_the_predicate_finds_both_legs(self):
        """The property the hand-written version got wrong, asserted directly."""
        out = self._txn(Decimal("-500.00"), self.checking)
        back = self._txn(Decimal("500.00"), self.card)
        out.transfer_pair = back
        out.save(update_fields=["transfer_pair"])

        found = set(Transaction.objects.filter(
            user=self.user).filter(TD.paired_q()).values_list("id", flat=True))
        self.assertEqual(found, {out.id, back.id},
                         "the counterpart leg is paired too — it just does not hold "
                         "the column")

    def test_coverage_reports_rows_and_pairs_separately(self):
        out = self._txn(Decimal("-500.00"), self.checking)
        back = self._txn(Decimal("500.00"), self.card)
        out.transfer_pair = back
        out.save(update_fields=["transfer_pair"])

        coverage = TD.pairing_coverage(self.user)
        self.assertEqual(coverage["pairs"], 1)
        self.assertEqual(coverage["paired_rows"], 2, "two legs make one pair")
        self.assertEqual(coverage["unpaired"],
                         coverage["transactions"] - 2)

    def setUp(self):
        self.user = User.objects.create_user(
            email="pairpredicate@example.com", password="x")
        self.checking = FinancialAccount.objects.create(
            user=self.user, name="Chequing", account_type=FinancialAccount.TYPE_CHECKING,
            current_balance=Decimal("1000.00"))
        self.card = FinancialAccount.objects.create(
            user=self.user, name="Card", account_type=FinancialAccount.TYPE_CREDIT_CARD,
            current_balance=Decimal("-500.00"))

    def _txn(self, amount, account, when=None):
        return Transaction.objects.create(
            user=self.user, account=account, amount=amount,
            date=when or date(2026, 6, 1), description="x")
