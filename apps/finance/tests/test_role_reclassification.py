# ==============================================================================
# File: apps/finance/tests/test_role_reclassification.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: A mass reclassification may never quietly raise someone's spending.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Rehearse, then apply only what is safe.

The persisted `economic_role` column had drifted 3,785 rows behind the classifier that
wrote it. Spending measures classify live and were never wrong, but the column bounds
the ranked-spend read and drives the review queue, so it has to be realigned.

Realigning it is a mass rewrite of financial meaning, and the directions are not
symmetric. Moving a row to `card_payment` or `uncertain` takes it OUT of spending —
recoverable, and visible on the review queue. Moving one INTO `purchase` puts money into
a total the person will read as theirs. These tests hold that asymmetry.
"""
from decimal import Decimal

from django.test import TestCase

from apps.finance.models import Transaction
from apps.finance.services.finance_calc import backfill as B
from apps.finance.tests.test_p1_economic_roles import RoleBase


class SafeDirectionTests(TestCase):
    """Which way a role may move without anyone looking."""

    def test_out_of_spending_is_safe(self):
        for target in ("card_payment", "debt_service", "internal_transfer",
                       "savings_allocation", "uncertain", "cash_withdrawal"):
            self.assertTrue(B._is_safe_transition("purchase", target), target)

    def test_into_spending_is_not(self):
        self.assertFalse(B._is_safe_transition("uncertain", "purchase"))
        self.assertFalse(B._is_safe_transition("card_payment", "purchase"))

    def test_into_income_or_a_refund_is_not(self):
        for target in ("income", "refund", "reversal_chargeback", "reimbursement"):
            self.assertFalse(B._is_safe_transition("purchase", target), target)

    def test_a_row_that_had_no_role_may_take_any(self):
        """It was nothing before; anything the classifier says is an improvement."""
        for target in ("purchase", "income", "refund", "card_payment"):
            self.assertTrue(B._is_safe_transition(None, target), target)

    def test_no_change_is_trivially_safe(self):
        self.assertTrue(B._is_safe_transition("purchase", "purchase"))

    def test_the_unsafe_targets_are_exactly_the_ones_that_add_money(self):
        for role in ("purchase", "income", "refund", "reimbursement",
                     "reversal_chargeback"):
            self.assertNotIn(role, B.SAFE_BACKFILL_TARGETS)


class RehearsalTests(RoleBase):
    def _stale(self, txn, role):
        Transaction.objects.filter(pk=txn.pk).update(
            economic_role=role, role_source=Transaction.ROLE_SOURCE_DERIVED,
            role_confidence="high", role_reason="stale",
            role_classifier_version="0.0.1")

    def test_the_rehearsal_writes_nothing(self):
        txn = self._txn(-500, primary="LOAN_PAYMENTS",
                        detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        self._stale(txn, Transaction.ROLE_PURCHASE)

        report = B.rehearse_and_apply(self.user, commit=False)
        self.assertFalse(report["committed"])
        txn.refresh_from_db()
        self.assertEqual(txn.economic_role, Transaction.ROLE_PURCHASE)

    def test_it_reports_which_role_becomes_which(self):
        txn = self._txn(-500, primary="LOAN_PAYMENTS",
                        detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        self._stale(txn, Transaction.ROLE_PURCHASE)

        report = B.rehearse_and_apply(self.user, commit=False)
        transitions = report["rehearsal"]["transitions"]
        self.assertIn("purchase -> card_payment", transitions)
        self.assertEqual(transitions["purchase -> card_payment"], 1)

    def test_it_reports_how_much_money_moves(self):
        txn = self._txn(-500, primary="LOAN_PAYMENTS",
                        detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        self._stale(txn, Transaction.ROLE_PURCHASE)

        report = B.rehearse_and_apply(self.user, commit=False)
        self.assertEqual(
            report["rehearsal"]["transition_amounts"]["purchase -> card_payment"],
            "500.00")

    def test_a_version_bump_alone_is_not_a_role_change(self):
        """`written` and `role_changes` must not be confused for each other."""
        txn = self._txn(-120, primary="GENERAL_MERCHANDISE")
        Transaction.objects.filter(pk=txn.pk).update(
            economic_role=Transaction.ROLE_PURCHASE,
            role_source=Transaction.ROLE_SOURCE_PROVIDER,
            role_confidence="high", role_reason="purchase",
            role_classifier_version="0.0.1")

        report = B.rehearse_and_apply(self.user, commit=False)
        self.assertGreaterEqual(report["rehearsal"]["would_write"], 1)
        self.assertEqual(report["rehearsal"]["role_changes"], 0,
                         "the meaning did not change, only the provenance")


class ApplyIsGatedTests(RoleBase):
    def _stale(self, txn, role):
        Transaction.objects.filter(pk=txn.pk).update(
            economic_role=role, role_source=Transaction.ROLE_SOURCE_DERIVED,
            role_confidence="high", role_reason="stale",
            role_classifier_version="0.0.1")

    def test_a_safe_correction_is_applied(self):
        txn = self._txn(-500, primary="LOAN_PAYMENTS",
                        detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        self._stale(txn, Transaction.ROLE_PURCHASE)

        report = B.rehearse_and_apply(self.user, commit=True)
        txn.refresh_from_db()
        self.assertEqual(txn.economic_role, Transaction.ROLE_CARD_PAYMENT)
        self.assertGreaterEqual(report["applied"]["written"], 1)

    def test_a_row_that_would_become_a_purchase_is_held_not_written(self):
        txn = self._txn(-120, primary="GENERAL_MERCHANDISE")
        self._stale(txn, Transaction.ROLE_UNCERTAIN)

        report = B.rehearse_and_apply(self.user, commit=True)
        txn.refresh_from_db()
        self.assertEqual(txn.economic_role, Transaction.ROLE_UNCERTAIN,
                         "a deploy may not raise what someone appears to have spent")
        self.assertGreaterEqual(report["applied"]["held_for_review"], 1)
        self.assertIn("uncertain -> purchase",
                      report["applied"]["held_transitions"])

    def test_a_user_decision_is_never_touched(self):
        txn = self._txn(-500, primary="LOAN_PAYMENTS",
                        detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        Transaction.objects.filter(pk=txn.pk).update(
            economic_role=Transaction.ROLE_PURCHASE,
            role_source=Transaction.ROLE_SOURCE_USER,
            role_reason="user_said_so", role_classifier_version="0.0.1")

        B.rehearse_and_apply(self.user, commit=True)
        txn.refresh_from_db()
        self.assertEqual(txn.economic_role, Transaction.ROLE_PURCHASE)
        self.assertEqual(txn.role_source, Transaction.ROLE_SOURCE_USER)

    def test_running_it_twice_changes_nothing_the_second_time(self):
        txn = self._txn(-500, primary="LOAN_PAYMENTS",
                        detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        self._stale(txn, Transaction.ROLE_PURCHASE)

        B.rehearse_and_apply(self.user, commit=True)
        second = B.rehearse_and_apply(self.user, commit=True)
        self.assertEqual(second["applied"]["written"], 0)
        self.assertEqual(second["rehearsal"]["role_changes"], 0)


class TheReportIsReadableWithoutRecomputingTests(TestCase):
    """The audit runs on a request path and must never classify to answer a question."""

    def test_publish_then_read(self):
        from django.core.cache import cache

        cache.delete(B.ROLE_REHEARSAL_CACHE_KEY)
        self.assertIsNone(B.read_rehearsal())
        B.publish_rehearsal({"classifier_version": "9.9.9"})
        self.assertEqual(B.read_rehearsal()["classifier_version"], "9.9.9")

    def test_the_audit_reads_the_cache_rather_than_classifying(self):
        import inspect

        from apps.finance.services import finance_audit

        source = inspect.getsource(finance_audit._role_state)
        self.assertIn("read_rehearsal", source)
        self.assertNotIn("classify", source,
                         "the audit must not classify on the request path")

    def test_an_absent_report_is_none_not_a_crash(self):
        from django.core.cache import cache

        cache.delete(B.ROLE_REHEARSAL_CACHE_KEY)
        from apps.finance.services.finance_audit import _role_state
        self.assertIsNone(_role_state()["last_reclassification"])


class DriftIsNotSelfHealedTests(TestCase):
    """The nightly sweep still REPORTS drift and does not rewrite it. Deliberate.

    `sweep_role_reconciliation` writes only genuinely unclassified rows; a row that
    merely disagrees with a newer classifier is reported and left alone, because a mass
    reclassification running unattended overnight could change what a person appears to
    have spent. `test_drift_is_reported_and_never_silently_rewritten` protects that.

    `rehearse_and_apply` was built with a gate that would make the risky direction
    impossible, which arguably answers the concern — but overturning an explicit,
    test-protected decision belongs to whoever made it, not to a passing change. So the
    one-time alignment is a migration a person chose to run, and drift after any FUTURE
    classifier bump still waits for a human.
    """

    def test_the_sweep_does_not_rewrite_drifted_rows(self):
        import inspect

        from apps.finance import tasks_intelligence

        source = inspect.getsource(tasks_intelligence.sweep_role_reconciliation)
        self.assertIn("REPORTED, never rewritten", source)
        self.assertNotIn("rehearse_and_apply", source,
                         "changing this is a decision, not a refactor — see the "
                         "docstring above")


class ATransferIsNeverASpendTests(RoleBase):
    """The classifier must not depend on another pass having run.

    `transfer_detection` sets `transfer_state`, but ONLY on the Plaid sync path. A row
    created any other way — manual entry, CSV import, a fixture, some future ingestion
    route — arrives here with the field at its default. Every transfer branch above the
    purchase default needs a confirmed state, a liability account or a loan-payment
    category, and a provider-labelled TRANSFER_OUT has none of them. So it fell through
    and became consumer spending.
    """

    def _unclassified_transfer(self, primary="TRANSFER_OUT", detailed="",
                               amount=-900):
        """A row exactly as a non-sync path leaves it: provider category, default state."""
        return self._txn(amount, primary=primary, detailed=detailed,
                         state=Transaction.TRANSFER_STATE_NOT_TRANSFER)

    def _role(self, txn):
        from apps.finance.services.finance_calc import roles as R
        return R.classify(txn).role

    def test_a_transfer_out_is_not_a_purchase(self):
        self.assertEqual(self._role(self._unclassified_transfer()),
                         Transaction.ROLE_UNCERTAIN)

    def test_an_account_transfer_is_not_a_purchase(self):
        self.assertEqual(
            self._role(self._unclassified_transfer(
                detailed="TRANSFER_OUT_ACCOUNT_TRANSFER")),
            Transaction.ROLE_UNCERTAIN)

    def test_a_transfer_to_savings_is_not_a_purchase(self):
        self.assertEqual(
            self._role(self._unclassified_transfer(detailed="TRANSFER_OUT_SAVINGS")),
            Transaction.ROLE_UNCERTAIN)

    def test_it_is_held_rather_than_called_an_internal_transfer(self):
        """Without the counterpart, money to your own account and money to someone
        else are indistinguishable — and they belong in different measures."""
        from apps.finance.services.finance_calc import roles as R

        assignment = R.classify(self._unclassified_transfer())
        self.assertEqual(assignment.role, Transaction.ROLE_UNCERTAIN)
        self.assertEqual(assignment.reason, "provider_transfer_uncorroborated")
        self.assertEqual(assignment.confidence, Transaction.ROLE_CONFIDENCE_LOW)

    def test_it_enters_no_spending_measure(self):
        from apps.finance.services.finance_calc import measures as M

        self._txn(4000, primary="INCOME")
        self._unclassified_transfer(amount=-900)
        self._txn(-60, primary="FOOD_AND_DRINK")

        measures = M.all_measures(self.user)
        self.assertEqual(measures["gross_purchases"].value, Decimal("60.00"))
        self.assertEqual(measures["net_spending"].value, Decimal("60.00"))

    def test_its_cash_movement_stays_real(self):
        """Held about its MEANING is not the same as pretending it did not happen."""
        from apps.finance.services.finance_calc import measures as M

        self._unclassified_transfer(amount=-900)
        self.assertEqual(M.all_measures(self.user)["cash_outflow"].value,
                         Decimal("900.00"))

    def test_it_cannot_be_ranked_as_a_spend(self):
        from apps.finance.services.finance_calc import measures as M

        self.assertIsNone(M.spend_magnitude(self._unclassified_transfer()))

    def test_a_real_purchase_is_untouched(self):
        self.assertEqual(
            self._role(self._txn(-60, primary="FOOD_AND_DRINK")),
            Transaction.ROLE_PURCHASE)

    def test_a_row_with_no_provider_category_is_still_a_purchase(self):
        """The fix keys on what the provider SAID, not on the sign or the wording."""
        self.assertEqual(self._role(self._txn(-60)), Transaction.ROLE_PURCHASE)

    def test_a_confirmed_transfer_still_gets_its_specific_role(self):
        """Holding is the fallback, not a replacement for evidence WLJ does have."""
        txn = self._txn(-900, primary="TRANSFER_OUT",
                        state=Transaction.TRANSFER_STATE_CONFIRMED,
                        kind=Transaction.TRANSFER_KIND_INTERNAL,
                        by=Transaction.TRANSFER_BY_PAIRING)
        self.assertEqual(self._role(txn), Transaction.ROLE_INTERNAL_TRANSFER)

    def test_a_transfer_in_was_already_held(self):
        """The inflow side already fell to `ambiguous_credit`; only outflow was open."""
        self.assertEqual(
            self._role(self._unclassified_transfer(primary="TRANSFER_IN",
                                                   amount=900)),
            Transaction.ROLE_UNCERTAIN)

    def test_the_primaries_come_from_the_one_module_that_owns_them(self):
        from apps.finance.services.finance_calc import roles as R
        from apps.finance.services.transfer_detection import (
            PROVIDER_TRANSFER_PRIMARIES,
        )

        self.assertIs(R._provider_transfer_primaries(), PROVIDER_TRANSFER_PRIMARIES,
                      "a second copy of this list is a second definition of 'transfer'")


class TheRecordSurvivesTests(RoleBase):
    """The cache is a convenience. The audit log is the record.

    The 2026-09-01 reclassification left no durable account of itself: Redis was
    `circuit_open` during the deploy, `publish_rehearsal` swallowed it by design, and
    what the run actually did survives only as a before/after count somebody happened to
    take by hand. "We think it moved seven rows" is not an audit trail.
    """

    def _report(self):
        return B.rehearse_and_apply(self.user, commit=False)

    def test_a_rehearsal_is_recorded(self):
        from apps.finance.models import FinanceAuditLog

        B.record_rehearsal(self._report(), mode="rehearsal")
        row = FinanceAuditLog.objects.filter(
            entity_type="module", details__operation="role_reclassification").first()
        self.assertIsNotNone(row)
        self.assertEqual(row.details["mode"], "rehearsal")

    def test_it_records_the_classifier_version(self):
        from apps.finance.services.finance_calc import roles as R

        B.record_rehearsal(self._report(), mode="applied")
        self.assertEqual(B.read_recorded_rehearsals()[0]["classifier_version"],
                         R.CLASSIFIER_VERSION)

    def test_it_records_a_timestamp_and_the_mode(self):
        B.record_rehearsal(self._report(), mode="applied")
        recorded = B.read_recorded_rehearsals()[0]
        self.assertIn("recorded_at", recorded)
        self.assertEqual(recorded["mode"], "applied")
        self.assertIn("at", recorded)

    def test_it_records_the_before_and_after_distributions(self):
        txn = self._txn(-500, primary="LOAN_PAYMENTS",
                        detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        Transaction.objects.filter(pk=txn.pk).update(
            economic_role=Transaction.ROLE_PURCHASE,
            role_source=Transaction.ROLE_SOURCE_DERIVED,
            role_confidence="high", role_reason="stale",
            role_classifier_version="0.0.1")

        report = B.rehearse_and_apply(self.user, commit=True)
        B.record_rehearsal(report, mode="applied")
        distribution = B.read_recorded_rehearsals()[0]["distribution"]
        self.assertEqual(distribution["before"].get(Transaction.ROLE_PURCHASE), 1)
        self.assertEqual(distribution["after"].get(Transaction.ROLE_CARD_PAYMENT), 1)

    def test_it_records_the_transition_counts(self):
        txn = self._txn(-500, primary="LOAN_PAYMENTS",
                        detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        Transaction.objects.filter(pk=txn.pk).update(
            economic_role=Transaction.ROLE_PURCHASE,
            role_source=Transaction.ROLE_SOURCE_DERIVED,
            role_confidence="high", role_reason="stale",
            role_classifier_version="0.0.1")

        B.record_rehearsal(B.rehearse_and_apply(self.user, commit=False),
                           mode="rehearsal")
        transitions = B.read_recorded_rehearsals()[0]["rehearsal"]["transitions"]
        self.assertEqual(transitions["purchase -> card_payment"], 1)

    def test_it_records_the_outcome_of_a_failure(self):
        B.record_rehearsal({"classifier_version": None}, mode="failed", success=False)
        recorded = B.read_recorded_rehearsals()[0]
        self.assertFalse(recorded["success"])
        self.assertEqual(recorded["mode"], "failed")

    def test_a_rehearsal_records_after_equal_to_before(self):
        """Stated rather than left null, so a reader never has to infer the mode."""
        report = self._report()
        self.assertEqual(report["distribution"]["after"],
                         report["distribution"]["before"])

    def test_it_never_records_a_transaction_detail(self):
        self._txn(-500, primary="LOAN_PAYMENTS", description="SECRET MERCHANT LLC",
                  detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        B.record_rehearsal(B.rehearse_and_apply(self.user, commit=False),
                           mode="rehearsal")
        blob = str(B.read_recorded_rehearsals())
        for forbidden in ("SECRET MERCHANT", "description", "payee", "account_id"):
            self.assertNotIn(forbidden, blob)

    def test_the_history_is_newest_first(self):
        B.record_rehearsal({"classifier_version": "1.0.0"}, mode="rehearsal")
        B.record_rehearsal({"classifier_version": "2.0.0"}, mode="applied")
        history = B.read_recorded_rehearsals()
        self.assertEqual(history[0]["classifier_version"], "2.0.0")

    def test_a_broken_audit_write_never_fails_the_reclassification(self):
        from unittest.mock import patch

        from apps.finance.models import FinanceAuditLog

        with patch.object(FinanceAuditLog.objects, "create",
                          side_effect=RuntimeError("db down")):
            B.record_rehearsal(self._report(), mode="applied")   # must not raise

    def test_the_audit_endpoint_exposes_the_durable_history(self):
        B.record_rehearsal(self._report(), mode="applied")
        from apps.finance.services.finance_audit import _role_state
        self.assertTrue(_role_state()["reclassification_history"])


class TheSweepStaysReportOnlyTests(TestCase):
    """Automatic role rewrites stay off. Explicitly."""

    def test_the_sweep_does_not_rewrite_drifted_rows(self):
        import inspect

        from apps.finance import tasks_intelligence

        source = inspect.getsource(tasks_intelligence.sweep_role_reconciliation)
        self.assertIn("REPORTED, never rewritten", source)
        self.assertNotIn("rehearse_and_apply", source)
