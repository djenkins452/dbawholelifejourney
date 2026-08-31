# ==============================================================================
# File: apps/finance/tests/test_payoff.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P7 — payoff scenarios, and the refusal to invent a term.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""A payoff plan is a number a household reorganises its life around.

Which makes the tests about MISSING data the important ones: a plausible invented APR
produces a plausible invented answer, and nobody can tell it from a real one.
"""
from datetime import date
from decimal import Decimal

from apps.finance.models import FinancialAccount, LoanTerms
from apps.finance.services.finance_calc import payoff as P
from apps.finance.tests.test_p1_economic_roles import RoleBase

START = date(2026, 1, 1)


class PayoffBase(RoleBase):
    def _debt(self, name, balance, apr=None, minimum=None):
        return P.Debt(key=name, name=name, balance=Decimal(str(balance)),
                      apr=None if apr is None else Decimal(str(apr)),
                      minimum_payment=None if minimum is None else Decimal(str(minimum)))


class ArithmeticTests(PayoffBase):
    def test_a_single_zero_rate_debt_clears_on_schedule(self):
        debts = [self._debt("Card", 1200, apr=0, minimum=100)]
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START)
        self.assertEqual(s.months, 12)
        self.assertEqual(s.total_interest, Decimal("0.00"))
        self.assertEqual(s.debt_free_date, date(2027, 1, 1))

    def test_interest_makes_it_take_longer(self):
        debts = [self._debt("Card", 1200, apr=24, minimum=100)]
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START)
        self.assertGreater(s.months, 12)
        self.assertGreater(s.total_interest, Decimal("0.00"))

    def test_extra_payments_shorten_it(self):
        debts = [self._debt("Card", 1200, apr=24, minimum=100)]
        base = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START)
        faster = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START,
                            extra_monthly=Decimal("300"))
        self.assertLess(faster.months, base.months)
        self.assertLess(faster.total_interest, base.total_interest)

    def test_a_lump_sum_is_applied_immediately(self):
        debts = [self._debt("Card", 1200, apr=0, minimum=100)]
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START,
                       lump_sum=Decimal("600"))
        self.assertEqual(s.months, 6)

    def test_the_final_payment_is_not_an_overpayment(self):
        debts = [self._debt("Card", 250, apr=0, minimum=100)]
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START)
        self.assertEqual(s.total_paid, Decimal("250.00"))

    def test_a_payment_below_the_interest_is_reported_not_looped(self):
        debts = [self._debt("Card", 10000, apr=30, minimum=10)]
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START)
        self.assertFalse(s.converged)
        self.assertIsNone(s.months)
        self.assertIn("not falling", " ".join(s.limitations))

    def test_no_debts_is_an_answer_not_an_error(self):
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=[], start=START)
        self.assertEqual(s.months, 0)


class StrategyTests(PayoffBase):
    def setUp(self):
        super().setUp()
        # Small-and-expensive vs large-and-cheap: the case where the two disagree.
        self.debts = [
            self._debt("Store card", 800, apr=27, minimum=40),
            self._debt("Car loan", 9000, apr=4, minimum=250),
        ]

    def test_snowball_takes_the_smallest_first(self):
        s = P.simulate(self.user, P.STRATEGY_SNOWBALL, debts=self.debts, start=START)
        self.assertEqual(s.order[0], "Store card")

    def test_avalanche_takes_the_dearest_first(self):
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=self.debts, start=START)
        self.assertEqual(s.order[0], "Store card")

    def test_avalanche_prefers_rate_over_size(self):
        debts = [self._debt("Big cheap", 20000, apr=3, minimum=300),
                 self._debt("Small dear", 900, apr=29, minimum=40)]
        self.assertEqual(
            P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts,
                       start=START).order[0], "Small dear")
        self.assertEqual(
            P.simulate(self.user, P.STRATEGY_SNOWBALL, debts=debts,
                       start=START).order[0], "Small dear")

    def test_a_custom_order_is_honoured(self):
        s = P.simulate(self.user, P.STRATEGY_CUSTOM, debts=self.debts, start=START,
                       custom_order=["Car loan", "Store card"])
        self.assertEqual(s.order, ["Car loan", "Store card"])

    def test_a_cleared_debt_releases_its_payment(self):
        s = P.simulate(self.user, P.STRATEGY_SNOWBALL, debts=self.debts, start=START)
        self.assertTrue(s.released_schedule)
        self.assertEqual(s.released_schedule[0]["debt"], "Store card")

    def test_without_roll_forward_it_takes_longer(self):
        rolling = P.simulate(self.user, P.STRATEGY_SNOWBALL, debts=self.debts,
                             start=START)
        flat = P.simulate(self.user, P.STRATEGY_SNOWBALL, debts=self.debts,
                          start=START, roll_forward=False)
        self.assertLessEqual(rolling.months, flat.months)

    def test_comparison_states_a_trade_not_a_winner(self):
        result = P.compare(self.user, debts=self.debts)
        self.assertTrue(result["comparable"])
        self.assertIn("does not declare a winner", result["trade_off"]["note"])

    def test_comparison_measures_against_minimums(self):
        result = P.compare(self.user, extra_monthly=Decimal("200"), debts=self.debts)
        self.assertIn("versus_minimums", result)
        self.assertGreaterEqual(result["versus_minimums"]["months_saved"], 0)


class MissingTermTests(PayoffBase):
    """The tests that stop WLJ inventing the most consequential number it holds."""

    def test_no_minimum_payment_means_no_timeline(self):
        debts = [self._debt("Truck", 24000, apr=7)]
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START)
        self.assertIsNone(s.months)
        self.assertIn("minimum_payment:Truck", s.inputs_missing)
        self.assertIn("no minimum payment recorded", " ".join(s.limitations))

    def test_but_the_order_is_still_given(self):
        """Half an answer, clearly labelled, beats no answer."""
        debts = [self._debt("Truck", 24000, apr=7),
                 self._debt("Card", 800, apr=27)]
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START)
        self.assertEqual(s.order, ["Card", "Truck"])

    def test_a_missing_apr_gives_balance_only_mode_not_zero_percent(self):
        debts = [self._debt("Truck", 2400, minimum=200)]
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START)
        self.assertEqual(s.months, 12)
        self.assertIsNone(s.total_interest,
                          "unknown interest must not be reported as zero")
        self.assertIn("Balance-only mode", " ".join(s.limitations))
        self.assertIn("apr:Truck", s.inputs_missing)

    def test_an_unknown_rate_is_ranked_last_not_treated_as_free(self):
        debts = [self._debt("Known", 5000, apr=5, minimum=100),
                 self._debt("Unknown", 5000, minimum=100)]
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START)
        self.assertEqual(s.order, ["Known", "Unknown"])

    def test_comparison_refuses_when_nothing_can_be_scheduled(self):
        debts = [self._debt("Truck", 24000, apr=7)]
        result = P.compare(self.user, debts=debts)
        self.assertFalse(result["comparable"])
        self.assertIn("no debt has a recorded minimum payment", result["trade_off"])


class PromotionalRateTests(PayoffBase):
    def test_an_unexpired_promotional_rate_is_the_rate_in_force(self):
        account = FinancialAccount.objects.create(
            user=self.user, name="Card", account_type="credit_card",
            current_balance=Decimal("-1000"))
        terms = LoanTerms.objects.create(
            user=self.user, account=account, apr=Decimal("24.99"),
            promotional_apr=Decimal("0"), promotional_apr_ends=date(2030, 1, 1))
        self.assertEqual(terms.effective_apr, Decimal("0"))

    def test_an_expired_one_is_not(self):
        account = FinancialAccount.objects.create(
            user=self.user, name="Card2", account_type="credit_card",
            current_balance=Decimal("-1000"))
        terms = LoanTerms.objects.create(
            user=self.user, account=account, apr=Decimal("24.99"),
            promotional_apr=Decimal("0"), promotional_apr_ends=date(2020, 1, 1))
        self.assertEqual(terms.effective_apr, Decimal("24.99"))


class ProvenanceTests(PayoffBase):
    def setUp(self):
        super().setUp()
        self.account = FinancialAccount.objects.create(
            user=self.user, name="Truck loan", account_type="loan",
            current_balance=Decimal("-24000"))
        self.terms = LoanTerms.objects.create(user=self.user, account=self.account)

    def test_a_term_cannot_be_set_without_saying_where_it_came_from(self):
        self.terms.record("apr", Decimal("7.25"), source="statement",
                          as_of=date(2026, 3, 1))
        self.assertEqual(self.terms.apr, Decimal("7.25"))
        self.assertEqual(self.terms.source_of("apr"), "statement")
        self.assertEqual(self.terms.as_of("apr"), "2026-03-01")

    def test_each_field_carries_its_own_freshness(self):
        self.terms.record("apr", Decimal("7.25"), source="statement",
                          as_of=date(2026, 3, 1))
        self.terms.record("minimum_payment", Decimal("450"), source="user",
                          as_of=date(2026, 8, 30))
        self.assertNotEqual(self.terms.as_of("apr"),
                            self.terms.as_of("minimum_payment"))

    def test_an_untracked_field_is_refused(self):
        with self.assertRaises(ValueError):
            self.terms.record("interest_rate_probably", Decimal("7"))

    def test_missing_lists_exactly_what_wlj_still_needs(self):
        self.terms.record("apr", Decimal("7.25"))
        missing = self.terms.missing()
        self.assertNotIn("apr", missing)
        self.assertIn("minimum_payment", missing)
        self.assertNotIn("current_balance", missing,
                         "the balance comes from the account and is known")

    def test_the_balance_is_never_a_second_copy(self):
        self.assertEqual(self.terms.balance, Decimal("24000.00"))
        self.account.current_balance = Decimal("-23000")
        self.account.save()
        self.terms.refresh_from_db()
        self.assertEqual(self.terms.balance, Decimal("23000.00"))

    def test_an_expired_payoff_quote_is_not_current(self):
        self.terms.payoff_amount = Decimal("23500")
        self.terms.payoff_quote_expires = date(2020, 1, 1)
        self.assertFalse(self.terms.payoff_quote_is_current)


class RealAccountTests(PayoffBase):
    def test_debts_come_from_live_liabilities_with_their_gaps_named(self):
        FinancialAccount.objects.create(
            user=self.user, name="Truck loan", account_type="loan",
            current_balance=Decimal("-24000"))
        debts = P.debts_for(self.user)
        truck = [d for d in debts if d.name == "Truck loan"][0]
        self.assertEqual(truck.balance, Decimal("24000"))
        self.assertIn("apr", truck.missing)
        self.assertIn("minimum_payment", truck.missing)

    def test_one_user_never_sees_another_households_debt(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="d2@example.com", password="pw"))
        FinancialAccount.objects.create(
            user=other, name="Theirs", account_type="loan",
            current_balance=Decimal("-99999"))
        self.assertNotIn("Theirs", [d.name for d in P.debts_for(self.user)])


class PartialTimelineTests(PayoffBase):
    """One gap should cost you that debt's timeline, not the whole plan.

    A household with five debts and one missing payment is better served by four
    modelled debts and a clear question than by a blanket refusal.
    """

    def test_a_debt_without_a_payment_is_excluded_and_named(self):
        debts = [self._debt("Card", 1200, apr=0, minimum=100),
                 self._debt("Truck", 24000, apr=7)]
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START)
        self.assertEqual(s.excluded, ["Truck"])
        self.assertEqual(s.months, 12, "the modellable debt still gets its timeline")
        self.assertIn("EXCLUDED from this timeline", " ".join(s.limitations))

    def test_the_exclusion_is_visible_in_the_serialised_scenario(self):
        debts = [self._debt("Card", 1200, apr=0, minimum=100),
                 self._debt("Truck", 24000, apr=7)]
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START)
        self.assertEqual(s.as_dict()["excluded_for_missing_payment"], ["Truck"])

    def test_no_payments_at_all_still_refuses_a_timeline(self):
        debts = [self._debt("Truck", 24000, apr=7)]
        s = P.simulate(self.user, P.STRATEGY_AVALANCHE, debts=debts, start=START)
        self.assertIsNone(s.months)
        self.assertEqual(s.order, ["Truck"])

    def test_comparison_surfaces_the_exclusion(self):
        debts = [self._debt("Card", 1200, apr=0, minimum=100),
                 self._debt("Truck", 24000, apr=7)]
        result = P.compare(self.user, debts=debts)
        self.assertTrue(result["comparable"])
        self.assertEqual(result["excluded_for_missing_payment"], ["Truck"])
