# ==============================================================================
# File: apps/finance/tests/test_outcomes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P11 — did the saving happen? Observed, and honestly unmeasured.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Most systems never close this loop: they suggest, the user accepts, and the
suggestion quietly becomes a fact in every later total.

So the tests here are mostly about the answers that are NOT "it worked": too early,
unmeasurable, and did not happen. Especially the last one — the whole point of measuring
is to notice.
"""
from datetime import date, timedelta
from decimal import Decimal

from apps.finance.models import RecurringSeries, SavingsOpportunity, Transaction
from apps.finance.services.finance_calc import outcomes as OUT
from apps.finance.tests.test_p1_economic_roles import RoleBase

START = date(2026, 3, 1)
TODAY = date(2026, 8, 31)


class OutcomeBase(RoleBase):
    def _series(self, name="Filmflix"):
        return RecurringSeries.objects.create(
            user=self.user, name=name, payee=name.lower(),
            kind=RecurringSeries.KIND_SUBSCRIPTION,
            frequency=RecurringSeries.FREQ_MONTHLY,
            amount_expected=Decimal("50"),
            review_state=RecurringSeries.REVIEW_CONFIRMED)

    def _opportunity(self, series=None, **kw):
        kw.setdefault("kind", SavingsOpportunity.KIND_CANCEL)
        kw.setdefault("title", "Cancel Filmflix")
        kw.setdefault("projected_monthly_savings", Decimal("50"))
        kw.setdefault("decision", SavingsOpportunity.STATUS_ACCEPTED)
        kw.setdefault("started_on", START)
        return SavingsOpportunity.objects.create(
            user=self.user, series=series, **kw)

    def _occurrences(self, series, *, months, amount=50, ending):
        for i in range(months):
            txn = self._txn(-Decimal(str(amount)),
                            on=ending - timedelta(days=30 * i),
                            description=series.name, primary="ENTERTAINMENT")
            txn.recurring_series = series
            txn.save()


class LifecycleTests(OutcomeBase):
    def test_an_unaccepted_opportunity_is_not_tracked(self):
        opportunity = self._opportunity(
            self._series(), decision=SavingsOpportunity.STATUS_PROPOSED)
        self.assertFalse(opportunity.is_being_tracked)
        self.assertEqual(OUT.measure(opportunity, today=TODAY)["outcome"],
                         SavingsOpportunity.OUTCOME_PENDING)

    def test_an_accepted_one_without_a_start_date_is_not_tracked(self):
        opportunity = self._opportunity(self._series(), started_on=None)
        self.assertFalse(opportunity.is_being_tracked)

    def test_decision_and_outcome_are_different_fields(self):
        opportunity = self._opportunity(self._series())
        self.assertEqual(opportunity.decision, SavingsOpportunity.STATUS_ACCEPTED)
        self.assertEqual(opportunity.outcome, SavingsOpportunity.OUTCOME_PENDING)

    def test_the_lifecycle_covers_every_stage_the_domain_needs(self):
        decisions = dict(SavingsOpportunity.DECISION_CHOICES)
        for stage in ("proposed", "accepted", "rejected", "snoozed", "planned",
                      "done", "abandoned"):
            self.assertIn(stage, decisions)

    def test_savings_can_be_directed_without_moving_money(self):
        """A direction, never a payment. WLJ initiates nothing."""
        from apps.finance.models import FinancialAccount
        debt = FinancialAccount.objects.create(
            user=self.user, name="Truck", account_type="loan",
            current_balance=Decimal("-24000"))
        opportunity = self._opportunity(self._series(), target_debt=debt)
        self.assertEqual(opportunity.target_debt_id, debt.pk)


class MeasurementTests(OutcomeBase):
    def test_too_early_is_not_a_failure(self):
        series = self._series()
        opportunity = self._opportunity(series, started_on=TODAY - timedelta(days=10))
        result = OUT.measure(opportunity, today=TODAY)
        self.assertEqual(result["outcome"], SavingsOpportunity.OUTCOME_TOO_EARLY)
        self.assertIn("not the same as not working", result["note"])

    def test_no_series_means_unmeasurable_not_a_guess(self):
        opportunity = self._opportunity(None)
        result = OUT.measure(opportunity, today=TODAY)
        self.assertEqual(result["outcome"], SavingsOpportunity.OUTCOME_UNMEASURABLE)
        self.assertIn("will not guess", result["note"])

    def test_no_baseline_means_unmeasurable(self):
        series = self._series()
        opportunity = self._opportunity(series)
        result = OUT.measure(opportunity, today=TODAY)
        self.assertEqual(result["outcome"], SavingsOpportunity.OUTCOME_UNMEASURABLE)
        self.assertIn("no baseline", result["note"])

    def test_a_cancelled_subscription_is_achieved(self):
        series = self._series()
        self._occurrences(series, months=2, ending=START - timedelta(days=5))
        opportunity = self._opportunity(series)
        result = OUT.measure(opportunity, today=TODAY, commit=True)
        self.assertEqual(result["outcome"], SavingsOpportunity.OUTCOME_ACHIEVED)
        opportunity.refresh_from_db()
        self.assertIsNotNone(opportunity.realized_monthly_savings)

    def test_spending_that_never_stopped_says_so_plainly(self):
        """The whole point of measuring is to notice. Spend did not fall at all."""
        series = self._series()
        self._occurrences(series, months=2, ending=START - timedelta(days=5))
        self._occurrences(series, months=7, ending=TODAY)
        opportunity = self._opportunity(series)
        result = OUT.measure(opportunity, today=TODAY, commit=True)
        self.assertEqual(result["outcome"], SavingsOpportunity.OUTCOME_NOT_ACHIEVED)
        self.assertIn("still going out", result["note"])

    def test_a_saving_too_small_to_count_is_also_not_achieved(self):
        """Some money left, nowhere near the plan. Reported against the projection."""
        series = self._series()
        self._occurrences(series, months=2, ending=START - timedelta(days=5))
        self._occurrences(series, months=5, ending=TODAY)
        opportunity = self._opportunity(series)
        result = OUT.measure(opportunity, today=TODAY, commit=True)
        self.assertEqual(result["outcome"], SavingsOpportunity.OUTCOME_NOT_ACHIEVED)
        self.assertIn("50 projected", result["note"])

    def test_projected_and_realized_never_become_one_number(self):
        series = self._series()
        self._occurrences(series, months=2, ending=START - timedelta(days=5))
        opportunity = self._opportunity(series)
        OUT.measure(opportunity, today=TODAY, commit=True)
        opportunity.refresh_from_db()
        self.assertEqual(opportunity.projected_monthly_savings, Decimal("50"))
        self.assertIsNotNone(opportunity.variance)

    def test_measuring_writes_nothing_unless_asked(self):
        series = self._series()
        self._occurrences(series, months=2, ending=START - timedelta(days=5))
        opportunity = self._opportunity(series)
        OUT.measure(opportunity, today=TODAY)
        opportunity.refresh_from_db()
        self.assertEqual(opportunity.outcome, SavingsOpportunity.OUTCOME_PENDING)

    def test_the_measurement_shows_its_working(self):
        series = self._series()
        self._occurrences(series, months=2, ending=START - timedelta(days=5))
        opportunity = self._opportunity(series)
        evidence = OUT.measure(opportunity, today=TODAY)["evidence"]
        self.assertIn("monthly_before", evidence)
        self.assertIn("monthly_after", evidence)
        self.assertIn("days_observed", evidence)


class UnderperformingTests(OutcomeBase):
    def test_which_plan_is_not_working_has_an_answer(self):
        series = self._series()
        self._occurrences(series, months=2, ending=START - timedelta(days=5))
        self._occurrences(series, months=5, ending=TODAY)
        opportunity = self._opportunity(series)
        OUT.measure(opportunity, today=TODAY, commit=True)
        failing = OUT.underperforming(self.user)
        self.assertEqual(len(failing), 1)
        self.assertEqual(failing[0]["title"], "Cancel Filmflix")

    def test_a_working_plan_is_not_listed_as_failing(self):
        series = self._series()
        self._occurrences(series, months=2, ending=START - timedelta(days=5))
        opportunity = self._opportunity(series)
        OUT.measure(opportunity, today=TODAY, commit=True)
        self.assertEqual(OUT.underperforming(self.user), [])

    def test_measure_all_reports_nothing_when_nothing_is_tracked(self):
        result = OUT.measure_all(self.user, today=TODAY)
        self.assertEqual(result["measured"], 0)

    def test_one_household_never_measures_another(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="o9@example.com", password="pw"))
        self._opportunity(self._series())
        self.assertEqual(OUT.measure_all(other, today=TODAY)["measured"], 0)
