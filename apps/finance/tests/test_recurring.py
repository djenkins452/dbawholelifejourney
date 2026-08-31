# ==============================================================================
# File: apps/finance/tests/test_recurring.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P3 — recurrence detection, review workflow, and forward totals.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Detection proposes; the person disposes.

The asymmetry that shapes every test here: a MISSING bill shows up in a forecast as an
obvious gap, while an INVENTED one silently makes the plan unachievable and the
household cannot see why. So nothing detected reaches a forward-looking total until a
person has confirmed it.
"""
from datetime import date, timedelta
from decimal import Decimal

from apps.finance.models import RecurringSeries, Transaction
from apps.finance.services.finance_calc import measures as M
from apps.finance.services.finance_calc import recurring as REC
from apps.finance.tests.test_p1_economic_roles import RoleBase

START = date(2026, 1, 5)


class DetectionTests(RoleBase):
    def _monthly(self, payee, amount, months=6, jitter=None, primary="RENT_AND_UTILITIES"):
        for i in range(months):
            day = START + timedelta(days=30 * i + (jitter[i] if jitter else 0))
            value = amount[i] if isinstance(amount, list) else amount
            self._txn(value, on=day, description=payee, primary=primary)

    def test_a_steady_monthly_bill_is_detected(self):
        self._monthly("Filmflix", -15)
        proposals = REC.detect(self.user)
        self.assertEqual(len(proposals), 1)
        series = proposals[0]["series"]
        self.assertEqual(series.frequency, RecurringSeries.FREQ_MONTHLY)
        self.assertEqual(series.amount_expected, Decimal("15.00"))

    def test_two_occurrences_are_a_coincidence_not_a_schedule(self):
        self._monthly("Filmflix", -15, months=2)
        self.assertEqual(REC.detect(self.user), [])

    def test_a_few_days_of_drift_is_still_the_same_bill(self):
        """Bills land on weekends and processors take a day off."""
        self._monthly("Filmflix", -15, months=6, jitter=[0, 2, -1, 3, 0, -2])
        proposals = REC.detect(self.user)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["series"].frequency,
                         RecurringSeries.FREQ_MONTHLY)

    def test_a_moving_amount_is_variable_not_a_bad_match(self):
        self._monthly("Power Co", [-80, -140, -95, -210, -120, -160])
        series = REC.detect(self.user)[0]["series"]
        self.assertTrue(series.is_variable)
        self.assertIsNone(series.amount_expected,
                          "an averaged figure nobody was ever charged is not expected")
        self.assertEqual(series.amount_min, Decimal("80.00"))
        self.assertEqual(series.amount_max, Decimal("210.00"))

    def test_wildly_different_amounts_are_not_one_commitment(self):
        """A supermarket is not a subscription."""
        self._monthly("Supermarket", [-8, -240, -19, -310, -12, -175],
                      primary="FOOD_AND_DRINK")
        self.assertEqual(REC.detect(self.user), [])

    def test_recurring_income_is_recognised_as_income(self):
        self._monthly("Employer", 3000, primary="INCOME")
        self.assertEqual(REC.detect(self.user)[0]["series"].kind,
                         RecurringSeries.KIND_INCOME)

    def test_reference_numbers_do_not_split_one_series_into_many(self):
        for i in range(6):
            self._txn(-15, on=START + timedelta(days=30 * i),
                      description=f"FILMFLIX 4471{i} 2026", primary="ENTERTAINMENT")
        self.assertEqual(len(REC.detect(self.user)), 1)

    def test_confidence_is_allowed_to_be_low(self):
        self._monthly("Filmflix", -15, months=3)
        self.assertEqual(REC.detect(self.user)[0]["series"].confidence, "low")

    def test_a_long_steady_history_earns_high_confidence(self):
        self._monthly("Filmflix", -15, months=8)
        self.assertEqual(REC.detect(self.user)[0]["series"].confidence, "high")

    def test_the_proposal_carries_the_evidence_for_it(self):
        self._monthly("Filmflix", -15)
        evidence = REC.detect(self.user)[0]["evidence"]
        self.assertEqual(evidence["occurrences"], 6)
        self.assertIn("median_gap_days", evidence)
        self.assertIn("amount_spread_fraction", evidence)

    def test_uncertain_rows_are_never_the_basis_of_a_schedule(self):
        for i in range(6):
            self._txn(-500, on=START + timedelta(days=30 * i), description="Mystery",
                      state=Transaction.TRANSFER_STATE_CANDIDATE, primary="TRANSFER_OUT")
        self.assertEqual(REC.detect(self.user), [])


class ReviewWorkflowTests(RoleBase):
    def setUp(self):
        super().setUp()
        for i in range(6):
            self._txn(-15, on=START + timedelta(days=30 * i), description="Filmflix",
                      primary="ENTERTAINMENT")

    def test_persisting_creates_a_candidate_never_a_confirmation(self):
        REC.persist(self.user, REC.detect(self.user), commit=True)
        series = RecurringSeries.objects.get(user=self.user)
        self.assertEqual(series.review_state, RecurringSeries.REVIEW_CANDIDATE)
        self.assertFalse(series.is_counted)

    def test_occurrences_are_linked_back_to_the_series(self):
        REC.persist(self.user, REC.detect(self.user), commit=True)
        series = RecurringSeries.objects.get(user=self.user)
        self.assertEqual(series.transactions.count(), 6)

    def test_re_running_detection_does_not_duplicate(self):
        REC.persist(self.user, REC.detect(self.user), commit=True)
        report = REC.persist(self.user, REC.detect(self.user), commit=True)
        self.assertEqual(report["created"], 0)
        self.assertEqual(RecurringSeries.objects.count(), 1)

    def test_re_running_never_reopens_a_decision(self):
        REC.persist(self.user, REC.detect(self.user), commit=True)
        series = RecurringSeries.objects.get(user=self.user)
        series.review_state = RecurringSeries.REVIEW_IGNORED
        series.save()
        REC.persist(self.user, REC.detect(self.user), commit=True)
        series.refresh_from_db()
        self.assertEqual(series.review_state, RecurringSeries.REVIEW_IGNORED,
                         "re-proposing something the user dismissed is nagging")

    def test_re_running_still_refreshes_the_observations(self):
        REC.persist(self.user, REC.detect(self.user), commit=True)
        series = RecurringSeries.objects.get(user=self.user)
        series.review_state = RecurringSeries.REVIEW_CONFIRMED
        series.save()
        self._txn(-15, on=START + timedelta(days=30 * 6), description="Filmflix",
                  primary="ENTERTAINMENT")
        REC.persist(self.user, REC.detect(self.user), commit=True)
        series.refresh_from_db()
        self.assertEqual(series.occurrence_count, 7)
        self.assertEqual(series.review_state, RecurringSeries.REVIEW_CONFIRMED)

    def test_a_merged_series_stops_counting_but_is_not_deleted(self):
        REC.persist(self.user, REC.detect(self.user), commit=True)
        series = RecurringSeries.objects.get(user=self.user)
        series.review_state = RecurringSeries.REVIEW_CONFIRMED
        keeper = RecurringSeries.objects.create(
            user=self.user, name="Keeper", kind=RecurringSeries.KIND_SUBSCRIPTION,
            review_state=RecurringSeries.REVIEW_CONFIRMED)
        series.merged_into = keeper
        series.save()
        self.assertFalse(series.is_counted)
        self.assertTrue(RecurringSeries.objects.filter(pk=series.pk).exists())


class MonthlyEquivalentTests(RoleBase):
    def test_an_annual_premium_is_a_monthly_commitment(self):
        series = RecurringSeries(frequency=RecurringSeries.FREQ_ANNUAL,
                                 amount_expected=Decimal("1200"))
        self.assertEqual(series.monthly_equivalent(), Decimal("100.00"))

    def test_fortnightly_is_not_twice_monthly(self):
        """26 payments a year, not 24. The difference is a month's rent over a decade."""
        series = RecurringSeries(frequency=RecurringSeries.FREQ_BIWEEKLY,
                                 amount_expected=Decimal("100"))
        self.assertEqual(series.monthly_equivalent(), Decimal("216.67"))

    def test_an_irregular_series_returns_nothing_rather_than_a_guess(self):
        series = RecurringSeries(frequency=RecurringSeries.FREQ_IRREGULAR,
                                 amount_expected=Decimal("100"))
        self.assertIsNone(series.monthly_equivalent())


class ObligationTotalTests(RoleBase):
    def _series(self, **kw):
        kw.setdefault("name", "Bill")
        kw.setdefault("kind", RecurringSeries.KIND_BILL)
        kw.setdefault("frequency", RecurringSeries.FREQ_MONTHLY)
        kw.setdefault("review_state", RecurringSeries.REVIEW_CONFIRMED)
        return RecurringSeries.objects.create(user=self.user, **kw)

    def test_no_confirmations_reports_an_absence_of_decisions(self):
        result = M.all_measures(self.user)["recurring_obligations"]
        self.assertEqual(result.value, Decimal("0.00"))
        self.assertEqual(result.confidence, "low")
        self.assertIn("NOT a household with no bills", " ".join(result.assumptions))

    def test_a_candidate_does_not_count(self):
        self._series(amount_expected=Decimal("100"),
                     review_state=RecurringSeries.REVIEW_CANDIDATE, payee="a")
        result = M.all_measures(self.user)["recurring_obligations"]
        self.assertEqual(result.value, Decimal("0.00"))
        self.assertIn("waiting for review", " ".join(result.assumptions))

    def test_a_confirmed_obligation_counts(self):
        self._series(amount_expected=Decimal("100"), payee="a")
        self.assertEqual(M.all_measures(self.user)["recurring_obligations"].value,
                         Decimal("100.00"))

    def test_a_transfer_is_not_an_obligation(self):
        """Moving your own money is not a bill you have to find."""
        self._series(amount_expected=Decimal("500"), payee="b",
                     kind=RecurringSeries.KIND_TRANSFER)
        self.assertEqual(M.all_measures(self.user)["recurring_obligations"].value,
                         Decimal("0.00"))

    def test_a_variable_obligation_is_counted_at_its_ceiling(self):
        self._series(payee="c", is_variable=True, amount_min=Decimal("80"),
                     amount_max=Decimal("210"))
        result = M.all_measures(self.user)["recurring_obligations"]
        self.assertEqual(result.value, Decimal("210.00"))
        self.assertIn("TOP of its observed range", " ".join(result.assumptions))

    def test_an_irregular_confirmed_obligation_is_named_not_guessed(self):
        self._series(payee="d", frequency=RecurringSeries.FREQ_IRREGULAR,
                     amount_expected=Decimal("300"))
        self._series(payee="e", amount_expected=Decimal("100"))
        result = M.all_measures(self.user)["recurring_obligations"]
        self.assertEqual(result.value, Decimal("100.00"))
        self.assertIn("expected_amount_for_irregular_series", result.inputs_missing)

    def test_one_user_never_sees_another_households_bills(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="r2@example.com", password="pw"))
        RecurringSeries.objects.create(
            user=other, name="Theirs", amount_expected=Decimal("999"),
            review_state=RecurringSeries.REVIEW_CONFIRMED)
        self.assertEqual(M.all_measures(self.user)["recurring_obligations"].value,
                         Decimal("0.00"))
