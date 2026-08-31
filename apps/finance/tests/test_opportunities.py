# ==============================================================================
# File: apps/finance/tests/test_opportunities.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P5 — the savings engine, and what it refuses to claim.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Two questions, and the discipline that makes the answers trustworthy.

    "What is my largest cost that I can control easily?"
    "How can I save $100 a month?"

The tests that matter are the ones proving WLJ stays quiet when it does not know. A
savings plan assembled from the system's own guesses is worse than no plan: the
household acts on it, the money does not appear, and nothing explains why.
"""
from datetime import date, timedelta
from decimal import Decimal

from apps.finance.models import (RecurringSeries, SavingsOpportunity,
                                 SpendingClassification)
from apps.finance.services.finance_calc import opportunities as OPP
from apps.finance.tests.test_p1_economic_roles import RoleBase

START = date(2026, 1, 5)


class OppBase(RoleBase):
    def _series(self, name, amount, *, confirmed=True, months=6, confidence="high",
                variable=False, kind=RecurringSeries.KIND_SUBSCRIPTION):
        series = RecurringSeries.objects.create(
            user=self.user, name=name, payee=name.lower(), kind=kind,
            frequency=RecurringSeries.FREQ_MONTHLY,
            amount_expected=None if variable else Decimal(str(amount)),
            amount_min=Decimal(str(amount)), amount_max=Decimal(str(amount)),
            is_variable=variable, confidence=confidence,
            occurrence_count=months,
            review_state=(RecurringSeries.REVIEW_CONFIRMED if confirmed
                          else RecurringSeries.REVIEW_CANDIDATE))
        for i in range(months):
            txn = self._txn(-Decimal(str(amount)), on=START + timedelta(days=30 * i),
                            description=name, primary="ENTERTAINMENT")
            txn.recurring_series = series
            txn.save()
        return series

    def _lever(self, payee, *levers, source=SpendingClassification.SOURCE_USER):
        return SpendingClassification.objects.create(
            user=self.user, scope=SpendingClassification.SCOPE_PAYEE,
            payee=payee.lower(), levers=list(levers), source=source)


class GenerationTests(OppBase):
    def test_a_confirmed_cancellable_series_becomes_an_opportunity(self):
        self._series("Filmflix", 15)
        self._lever("Filmflix", SpendingClassification.LEVER_CANCELLABLE)
        proposals = OPP.generate(self.user)
        self.assertEqual(len(proposals), 1)
        opportunity = proposals[0]["opportunity"]
        self.assertEqual(opportunity.kind, SavingsOpportunity.KIND_CANCEL)
        self.assertEqual(opportunity.projected_monthly_savings, Decimal("15.00"))

    def test_an_unconfirmed_series_produces_nothing(self):
        """A plan built on WLJ's own guess is worse than no plan."""
        self._series("Filmflix", 15, confirmed=False)
        self._lever("Filmflix", SpendingClassification.LEVER_CANCELLABLE)
        self.assertEqual(OPP.generate(self.user), [])

    def test_a_series_with_no_lever_produces_nothing(self):
        self._series("Filmflix", 15)
        self.assertEqual(OPP.generate(self.user), [])

    def test_negotiable_claims_a_discount_not_a_waiver(self):
        self._series("Insurer", 200)
        self._lever("Insurer", SpendingClassification.LEVER_NEGOTIABLE)
        opportunity = OPP.generate(self.user)[0]["opportunity"]
        self.assertEqual(opportunity.kind, SavingsOpportunity.KIND_NEGOTIATE)
        self.assertEqual(opportunity.projected_monthly_savings, Decimal("30.00"))

    def test_every_opportunity_can_show_its_working(self):
        self._series("Filmflix", 15)
        self._lever("Filmflix", SpendingClassification.LEVER_CANCELLABLE)
        evidence = OPP.generate(self.user)[0]["evidence"]
        self.assertEqual(evidence["calculation"], "15.00 x 1.00 = 15.00")
        self.assertEqual(len(evidence["transaction_ids"]), 6)
        self.assertEqual(evidence["controllability_source"], "user")

    def test_an_inferred_classification_is_only_ever_low_confidence(self):
        self._series("Filmflix", 15)
        self._lever("Filmflix", SpendingClassification.LEVER_CANCELLABLE,
                    source=SpendingClassification.SOURCE_INFERRED)
        self.assertEqual(OPP.generate(self.user)[0]["opportunity"].confidence, "low")

    def test_a_variable_series_is_costed_at_its_floor(self):
        """Claiming the ceiling would overstate what cancelling actually returns."""
        series = self._series("Power", 100, variable=True)
        series.amount_min = Decimal("80")
        series.amount_max = Decimal("210")
        series.save()
        self._lever("Power", SpendingClassification.LEVER_CANCELLABLE)
        self.assertEqual(OPP.generate(self.user)[0]["opportunity"]
                         .projected_monthly_savings, Decimal("80.00"))

    def test_multiple_levers_give_multiple_options(self):
        self._series("Telco", 100)
        self._lever("Telco", SpendingClassification.LEVER_NEGOTIABLE,
                    SpendingClassification.LEVER_REDUCIBLE)
        kinds = {p["opportunity"].kind for p in OPP.generate(self.user)}
        self.assertEqual(kinds, {SavingsOpportunity.KIND_NEGOTIATE,
                                 SavingsOpportunity.KIND_DOWNGRADE})


class RankingTests(OppBase):
    def test_the_easier_of_two_equal_savings_ranks_first(self):
        easy = SavingsOpportunity(
            user=self.user, kind=SavingsOpportunity.KIND_CANCEL, title="Easy",
            projected_monthly_savings=Decimal("50"), confidence="high",
            effort="low", disruption="low")
        hard = SavingsOpportunity(
            user=self.user, kind=SavingsOpportunity.KIND_REDUCE_CATEGORY, title="Hard",
            projected_monthly_savings=Decimal("50"), confidence="high",
            effort="high", disruption="high")
        self.assertGreater(OPP.ease_score(easy), OPP.ease_score(hard))

    def test_a_trivial_saving_can_beat_a_larger_painful_one(self):
        trivial = SavingsOpportunity(
            user=self.user, kind=SavingsOpportunity.KIND_CANCEL, title="Trivial",
            projected_monthly_savings=Decimal("50"), confidence="high",
            effort="low", disruption="low")
        painful = SavingsOpportunity(
            user=self.user, kind=SavingsOpportunity.KIND_REDUCE_CATEGORY,
            title="Painful", projected_monthly_savings=Decimal("300"),
            confidence="low", effort="high", disruption="high")
        self.assertGreater(OPP.ease_score(trivial), OPP.ease_score(painful))

    def test_a_bigger_prize_still_wins_when_the_effort_is_comparable(self):
        """Ease is a weighting, not a preference for small things.

        Renegotiating a 400/month bill returns 60 for a phone call. Cancelling a
        40/month subscription returns 40. The engine prefers the phone call, and it is
        right to — a ranking that always favoured the smaller item would be no more
        useful than one that always favoured the larger.
        """
        self._series("Filmflix", 40)
        self._lever("Filmflix", SpendingClassification.LEVER_CANCELLABLE)
        self._series("Mortgage extra", 400, kind=RecurringSeries.KIND_BILL)
        self._lever("Mortgage extra", SpendingClassification.LEVER_NEGOTIABLE)
        OPP.persist(self.user, OPP.generate(self.user), commit=True)
        self.assertEqual(OPP.ranked(self.user)[0].title, "Renegotiate Mortgage extra")

    def test_the_largest_controllable_cost_is_answerable(self):
        self._series("Filmflix", 40)
        self._lever("Filmflix", SpendingClassification.LEVER_CANCELLABLE)
        OPP.persist(self.user, OPP.generate(self.user), commit=True)
        answer = OPP.largest_controllable_cost(self.user)["answer"]
        self.assertEqual(answer["monthly"], "40.00")
        self.assertEqual(answer["annual"], "480.00")
        self.assertTrue(answer["evidence"]["transaction_ids"])

    def test_with_nothing_classified_it_says_what_is_missing(self):
        result = OPP.largest_controllable_cost(self.user)
        self.assertIsNone(result["answer"])
        whats = {m["what"] for m in result["missing"]}
        self.assertIn("controllability_classification", whats)

    def test_it_names_unconfirmed_candidates_specifically(self):
        self._series("Filmflix", 15, confirmed=False)
        result = OPP.largest_controllable_cost(self.user)
        whats = {m["what"] for m in result["missing"]}
        self.assertIn("confirm_recurring_series", whats)


class FindAmountTests(OppBase):
    def _stock(self):
        for name, amount in (("Filmflix", 40), ("Gymme", 45), ("Cloudy", 30)):
            self._series(name, amount)
            self._lever(name, SpendingClassification.LEVER_CANCELLABLE)
        OPP.persist(self.user, OPP.generate(self.user), commit=True)

    def test_it_assembles_a_plan_that_reaches_the_target(self):
        self._stock()
        result = OPP.find_amount(self.user, 100)
        self.assertTrue(result["reached"])
        self.assertGreaterEqual(Decimal(result["found"]), Decimal("100"))

    def test_it_stops_once_the_target_is_met(self):
        self._stock()
        self.assertLessEqual(len(OPP.find_amount(self.user, 100)["plan"]), 3)

    def test_it_never_counts_the_same_subscription_twice(self):
        self._series("Telco", 200)
        self._lever("Telco", SpendingClassification.LEVER_NEGOTIABLE,
                    SpendingClassification.LEVER_REDUCIBLE)
        OPP.persist(self.user, OPP.generate(self.user), commit=True)
        plan = OPP.find_amount(self.user, 200)["plan"]
        self.assertEqual(len(plan), 1, "cancel AND renegotiate is the same money twice")

    def test_falling_short_says_how_short_and_why(self):
        self._series("Filmflix", 20)
        self._lever("Filmflix", SpendingClassification.LEVER_CANCELLABLE)
        OPP.persist(self.user, OPP.generate(self.user), commit=True)
        result = OPP.find_amount(self.user, 100)
        self.assertFalse(result["reached"])
        self.assertEqual(result["shortfall"], "80.00")
        self.assertIn("cannot yet point to one", result["note"])

    def test_with_no_data_it_asks_rather_than_inventing(self):
        result = OPP.find_amount(self.user, 100)
        self.assertFalse(result["reached"])
        self.assertEqual(result["plan"], [])
        self.assertTrue(result["missing"])

    def test_moving_who_pays_is_not_a_household_saving(self):
        self._series("Software", 90)
        self._lever("Software", SpendingClassification.LEVER_CANCELLABLE)
        OPP.persist(self.user, OPP.generate(self.user), commit=True)
        SavingsOpportunity.objects.create(
            user=self.user, kind=SavingsOpportunity.KIND_MOVE_TO_ENTITY,
            title="Charge to the business",
            projected_monthly_savings=Decimal("500"))
        result = OPP.find_amount(self.user, 100)
        titles = [p["title"] for p in result["plan"]]
        self.assertNotIn("Charge to the business", titles)


class DecisionTests(OppBase):
    def setUp(self):
        super().setUp()
        self._series("Filmflix", 40)
        self._lever("Filmflix", SpendingClassification.LEVER_CANCELLABLE)
        OPP.persist(self.user, OPP.generate(self.user), commit=True)
        self.opportunity = SavingsOpportunity.objects.get(user=self.user)

    def test_rejecting_removes_it_from_the_ranking(self):
        self.opportunity.decide(SavingsOpportunity.STATUS_REJECTED,
                                reason="I use it daily").save()
        self.assertEqual(OPP.ranked(self.user), [])

    def test_a_live_snooze_hides_it(self):
        self.opportunity.decide(SavingsOpportunity.STATUS_SNOOZED,
                                snooze_until=date(2030, 1, 1)).save()
        self.assertEqual(OPP.ranked(self.user), [])

    def test_an_expired_snooze_brings_it_back(self):
        self.opportunity.decide(SavingsOpportunity.STATUS_SNOOZED,
                                snooze_until=date(2020, 1, 1)).save()
        self.assertEqual(len(OPP.ranked(self.user)), 1)

    def test_regenerating_never_reopens_a_decision(self):
        self.opportunity.decide(SavingsOpportunity.STATUS_REJECTED).save()
        OPP.persist(self.user, OPP.generate(self.user), commit=True)
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.decision,
                         SavingsOpportunity.STATUS_REJECTED)

    def test_projected_and_realized_are_never_the_same_field(self):
        self.assertIsNone(self.opportunity.realized_monthly_savings)
        self.assertIsNone(self.opportunity.variance)
        self.opportunity.realized_monthly_savings = Decimal("30")
        self.assertEqual(self.opportunity.variance, Decimal("-10.00"))

    def test_one_user_never_sees_another_households_opportunities(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="o2@example.com", password="pw"))
        self.assertEqual(OPP.ranked(other), [])
