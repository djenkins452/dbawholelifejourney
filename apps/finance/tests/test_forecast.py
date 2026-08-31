# ==============================================================================
# File: apps/finance/tests/test_forecast.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P4 — reserves, sinking funds, and a forecast that degrades honestly.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Danny has zero confirmed obligations, which is the case that matters most.

A forecast built on WLJ's own guesses looks identical to a real one, so with nothing
confirmed the engine reports the balance, says what is missing, and refuses to project.
The feature exists; the projection does not pretend to.
"""
from datetime import date, timedelta
from decimal import Decimal

from apps.finance.models import (CashReserve, FinancialAccount, FinancialGoal,
                                 LoanTerms, RecurringSeries)
from apps.finance.services.finance_calc import forecast as F
from apps.finance.tests.test_p1_economic_roles import RoleBase


class ForecastBase(RoleBase):
    def _series(self, name, amount, kind=RecurringSeries.KIND_BILL,
                state=RecurringSeries.REVIEW_CONFIRMED):
        return RecurringSeries.objects.create(
            user=self.user, name=name, payee=name.lower(), kind=kind,
            frequency=RecurringSeries.FREQ_MONTHLY,
            amount_expected=Decimal(str(amount)), review_state=state)

    def _reserve(self, name, target, kind=CashReserve.KIND_RESERVE, **kw):
        return CashReserve.objects.create(
            user=self.user, name=name, kind=kind,
            target_amount=Decimal(str(target)), **kw)


class EmptySetupTests(ForecastBase):
    """The state Danny is actually in."""

    def test_it_still_produces_a_forecast_object(self):
        result = F.build(self.user)
        self.assertEqual(result["horizon_days"], 30)
        self.assertIn("starting_liquid", result)

    def test_the_starting_balance_is_real(self):
        self.assertEqual(F.build(self.user)["starting_liquid"], Decimal("3000"))

    def test_it_refuses_to_project(self):
        result = F.build(self.user)
        self.assertFalse(result["projectable"])
        self.assertEqual(result["expected_inflow"], Decimal("0.00"))
        self.assertEqual(result["committed_outflow"], Decimal("0.00"))

    def test_it_says_why_rather_than_showing_zero(self):
        assumptions = " ".join(F.build(self.user)["assumptions"])
        self.assertIn("would be WLJ's guess", assumptions)
        self.assertIn("looks exactly like a fact", assumptions)

    def test_it_names_every_missing_input(self):
        missing = F.build(self.user)["inputs_missing"]
        self.assertIn("confirmed_recurring_income", missing)
        self.assertIn("confirmed_recurring_obligations", missing)
        self.assertIn("reserve_target", missing)

    def test_confidence_is_low(self):
        self.assertEqual(F.build(self.user)["confidence"], "low")

    def test_setup_state_offers_the_next_action(self):
        self._series("Filmflix", 15, state=RecurringSeries.REVIEW_CANDIDATE)
        state = F.setup_state(self.user)
        self.assertFalse(state["ready"])
        whats = [s["what"] for s in state["steps"]]
        self.assertIn("confirm_recurring", whats)
        self.assertEqual(state["steps"][0]["route"], "finance:money_review")

    def test_with_no_candidates_it_offers_detection_instead(self):
        whats = [s["what"] for s in F.setup_state(self.user)["steps"]]
        self.assertIn("detect_recurring", whats)


class ProjectionTests(ForecastBase):
    def setUp(self):
        super().setUp()
        self._series("Salary", 4000, kind=RecurringSeries.KIND_INCOME)
        self._series("Rent", 1200)

    def test_a_confirmed_pair_makes_it_projectable(self):
        result = F.build(self.user)
        self.assertTrue(result["projectable"])
        self.assertGreater(result["expected_inflow"], Decimal("0.00"))
        self.assertGreater(result["committed_outflow"], Decimal("0.00"))

    def test_the_four_numbers_stay_apart(self):
        """Balance, income, spending and free cash are different questions.

        Free cash equals projected cash only when no floor is set — which is itself a
        fact worth seeing, so the reserve is added to separate them.
        """
        self._reserve("Emergency", 2000)
        result = F.build(self.user)
        self.assertEqual(result["starting_liquid"], Decimal("3000"))
        self.assertNotEqual(result["expected_inflow"], result["starting_liquid"])
        self.assertNotEqual(result["committed_outflow"], result["expected_inflow"])
        self.assertNotEqual(result["free_cash_flow"], result["projected_ending_cash"])
        self.assertEqual(result["free_cash_flow"],
                         result["projected_ending_cash"] - Decimal("2000"))

    def test_a_reserve_floor_reduces_free_cash_but_not_the_balance(self):
        before = F.build(self.user)
        self._reserve("Emergency", 2000)
        after = F.build(self.user)
        self.assertEqual(after["projected_ending_cash"],
                         before["projected_ending_cash"])
        self.assertEqual(after["free_cash_flow"],
                         before["free_cash_flow"] - Decimal("2000"))

    def test_a_sinking_fund_is_committed_cash(self):
        before = F.build(self.user)["committed_outflow"]
        self._reserve("Insurance", 1200, kind=CashReserve.KIND_SINKING,
                      monthly_contribution=Decimal("100"))
        self.assertGreater(F.build(self.user)["committed_outflow"], before)

    def test_debt_minimums_are_committed(self):
        account = FinancialAccount.objects.create(
            user=self.user, name="Truck", account_type="loan",
            current_balance=Decimal("-24000"))
        LoanTerms.objects.create(user=self.user, account=account,
                                 apr=Decimal("7.25"),
                                 minimum_payment=Decimal("450"))
        result = F.build(self.user)
        self.assertGreater(result["committed_breakdown"]["debt_minimums"],
                           Decimal("0.00"))

    def test_a_debt_without_a_minimum_is_named_not_assumed(self):
        FinancialAccount.objects.create(
            user=self.user, name="Truck", account_type="loan",
            current_balance=Decimal("-24000"))
        result = F.build(self.user)
        self.assertIn("Truck", result["debts_without_a_minimum"])
        self.assertIn("debt_minimum_payments", result["inputs_missing"])
        self.assertIn("NOT in the committed figure", " ".join(result["assumptions"]))

    def test_the_low_point_assumes_the_unfriendly_ordering(self):
        """Rent on the 1st and pay on the 28th is a real shape."""
        result = F.build(self.user)
        self.assertLess(result["lowest_projected_balance"],
                        result["projected_ending_cash"])

    def test_longer_horizons_scale_the_flows(self):
        thirty = F.build(self.user, horizon_days=30)
        ninety = F.build(self.user, horizon_days=90)
        self.assertGreater(ninety["expected_inflow"], thirty["expected_inflow"])

    def test_a_monthly_bill_lands_a_whole_number_of_times(self):
        """0.9856 of a rent payment is not a thing, and understating it flatters."""
        self.assertEqual(F.build(self.user, horizon_days=30)
                         ["committed_breakdown"]["recurring_obligations"],
                         Decimal("1200.00"))
        self.assertEqual(F.build(self.user, horizon_days=90)
                         ["committed_breakdown"]["recurring_obligations"],
                         Decimal("3600.00"))

    def test_all_horizons_are_offered(self):
        self.assertEqual(sorted(F.all_horizons(self.user)), [30, 60, 90])


class ProvisionalTests(ForecastBase):
    def setUp(self):
        super().setUp()
        self._series("Salary", 4000, kind=RecurringSeries.KIND_INCOME)
        self._series("Rent", 1200)
        self._series("Maybe gym", 60, state=RecurringSeries.REVIEW_CANDIDATE)

    def test_an_unconfirmed_bill_never_enters_the_committed_figure(self):
        result = F.build(self.user)
        committed = result["committed_breakdown"]["recurring_obligations"]
        self.assertEqual(committed, Decimal("1200.00"))

    def test_but_it_is_shown_so_the_person_can_see_what_would_change(self):
        result = F.build(self.user)
        self.assertGreater(result["provisional_outflow"], Decimal("0.00"))
        self.assertEqual(result["provisional_count"], 1)

    def test_the_separation_is_explained_where_it_is_read(self):
        result = F.build(self.user)
        self.assertIn("nobody confirmed", result["provisional_note"])
        self.assertIn("excluded from every committed total",
                      " ".join(result["assumptions"]))


class ReserveTests(ForecastBase):
    def test_a_reserve_reads_its_linked_goal_rather_than_copying_it(self):
        goal = FinancialGoal.objects.create(
            user=self.user, name="Emergency Fund",
            goal_type=FinancialGoal.GOAL_TYPE_EMERGENCY,
            target_amount=Decimal("6000"), linked_account=self.savings)
        reserve = self._reserve("Emergency", 6000, goal=goal)
        self.assertEqual(reserve.effective_balance, Decimal("2000"))
        self.savings.current_balance = Decimal("5000")
        self.savings.save()
        reserve.refresh_from_db()
        self.assertEqual(reserve.effective_balance, Decimal("5000"))

    def test_the_existing_emergency_goal_is_reused_not_hardcoded(self):
        goal = FinancialGoal.objects.create(
            user=self.user, name="Emergency Fund",
            goal_type=FinancialGoal.GOAL_TYPE_EMERGENCY,
            target_amount=Decimal("1000"), linked_account=self.savings)
        self._reserve("Emergency", goal.target_amount, goal=goal)
        floor, rows = F.reserve_floor(self.user)
        self.assertEqual(floor, Decimal("1000"))
        self.assertEqual(rows[0]["source"], "goal")

    def test_shortfall_is_none_when_no_target_was_set(self):
        reserve = CashReserve.objects.create(
            user=self.user, name="Someday", kind=CashReserve.KIND_SINKING)
        self.assertIsNone(reserve.shortfall)
        self.assertFalse(reserve.is_funded)

    def test_a_funded_reserve_says_so(self):
        reserve = self._reserve("Emergency", 1000, account=self.savings)
        self.assertTrue(reserve.is_funded)
        self.assertEqual(reserve.shortfall, Decimal("0.00"))

    def test_no_reserve_means_no_floor_and_the_forecast_says_it(self):
        self._series("Salary", 4000, kind=RecurringSeries.KIND_INCOME)
        result = F.build(self.user)
        self.assertEqual(result["reserve_floor"], Decimal("0.00"))
        self.assertIn("absent decision", " ".join(result["assumptions"]))


class OwnershipTests(ForecastBase):
    def test_a_forecast_never_reaches_another_household(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="f2@example.com", password="pw"))
        FinancialAccount.objects.create(
            user=other, name="Theirs", account_type="checking",
            current_balance=Decimal("999999"))
        RecurringSeries.objects.create(
            user=other, name="Theirs", amount_expected=Decimal("500"),
            review_state=RecurringSeries.REVIEW_CONFIRMED)
        result = F.build(self.user)
        self.assertEqual(result["starting_liquid"], Decimal("3000"))
        self.assertFalse(result["projectable"])
