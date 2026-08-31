# ==============================================================================
# File: apps/finance/tests/test_cos_evidence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P9 — what the Chief of Staff may know, and what it must never receive.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The packet is the boundary between a private ledger and a third-party service.

So the redaction tests here are not hygiene — they are the control. Everything else
checks the other half of the contract: WLJ computes, the model explains, and "I need
the APR first" is a better answer than a confident payoff date built on a guess.
"""
from datetime import date
from decimal import Decimal

from apps.finance.models import (FinancialAccount, LoanTerms, RecurringSeries,
                                 SpendingClassification, Transaction)
from apps.finance.services.finance_calc import cos_evidence as E
from apps.finance.tests.test_p1_economic_roles import RoleBase


def _walk(node):
    """Every key and string in a packet, however deeply nested."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield ("key", str(key))
            yield from _walk(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, str):
        yield ("value", node)


class RedactionTests(RoleBase):
    """The control that stands between a private ledger and a third-party service."""

    def setUp(self):
        super().setUp()
        self.checking.plaid_account_id = "acct-SECRET-9931"
        self.checking.save()
        self._txn(-50, primary="FOOD_AND_DRINK",
                  description="ACME LIQUOR STORE 4471 MAIN ST")
        self._txn(3000, primary="INCOME", description="EMPLOYER PAYROLL 88-2231")
        account = FinancialAccount.objects.create(
            user=self.user, name="Truck loan", account_type="loan",
            current_balance=Decimal("-24000"))
        LoanTerms.objects.create(user=self.user, account=account,
                                 apr=Decimal("7.25"), minimum_payment=Decimal("450"))

    def _packets(self):
        return {
            "measures": E.measures_packet(self.user),
            "coverage": E.coverage_packet(self.user),
            "debt": E.debt_packet(self.user),
            "payoff": E.payoff_packet(self.user),
            "comparison": E.payoff_comparison_packet(self.user),
            "priority": E.single_debt_priority_packet(self.user, "truck"),
            "obligations": E.obligations_packet(self.user),
            "controllable": E.controllable_packet(self.user),
            "find": E.find_amount_packet(self.user, 100),
            "opportunities": E.opportunities_packet(self.user),
            "snapshot": E.snapshot_packet(self.user),
            "forecast": E.forecast_packet(self.user),
            "affordability": E.affordability_packet(self.user, 300),
            "net_worth": E.net_worth_packet(self.user),
            "net_worth_history": E.net_worth_history_packet(self.user),
            "plan_results": E.plan_results_packet(self.user),
            "data_health_detail": E.data_health_packet(self.user),
            "money_bridge": E.money_bridge_packet(self.user),
        }

    def test_no_packet_carries_a_forbidden_key(self):
        for name, packet in self._packets().items():
            with self.subTest(packet=name):
                keys = {v for kind, v in _walk(packet) if kind == "key"}
                self.assertEqual(keys & E.FORBIDDEN_KEYS, set())

    def test_no_packet_leaks_a_transaction_description(self):
        for name, packet in self._packets().items():
            with self.subTest(packet=name):
                values = " ".join(v for kind, v in _walk(packet) if kind == "value")
                self.assertNotIn("ACME", values)
                self.assertNotIn("MAIN ST", values)
                self.assertNotIn("PAYROLL", values)

    def test_no_packet_leaks_a_provider_identifier(self):
        for name, packet in self._packets().items():
            with self.subTest(packet=name):
                values = " ".join(v for kind, v in _walk(packet) if kind == "value")
                self.assertNotIn("SECRET", values)

    def test_every_packet_says_who_did_the_arithmetic(self):
        for name, packet in self._packets().items():
            with self.subTest(packet=name):
                self.assertIn("envelope", packet)
                self.assertIn("Do not recompute",
                              packet["envelope"]["arithmetic_note"])
                self.assertIn("as_of", packet["envelope"])


class MeasureEvidenceTests(RoleBase):
    def test_the_packet_reports_whether_the_numbers_reconcile(self):
        self._txn(-50, primary="FOOD_AND_DRINK")
        packet = E.measures_packet(self.user)
        self.assertTrue(packet["trustworthy"])
        self.assertTrue(packet["reconciliation"]["all_hold"])

    def test_each_measure_carries_its_own_confidence_and_gaps(self):
        self._txn(-50, primary="FOOD_AND_DRINK")
        measures = E.measures_packet(self.user)["measures"]
        self.assertIn("confidence", measures["net_spending"])
        self.assertIn("inputs_missing", measures["controllable_spending"])

    def test_data_health_reports_classification_coverage(self):
        self._txn(-50, primary="FOOD_AND_DRINK")
        packet = E.coverage_packet(self.user)
        self.assertEqual(packet["transactions"], 1)
        self.assertEqual(packet["unclassified"], 1, "nothing backfilled in this test db")


class DebtQuestionTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.truck = FinancialAccount.objects.create(
            user=self.user, name="Truck loan", account_type="loan",
            current_balance=Decimal("-24000"))
        # The base fixture's credit card is a liability too. Give it terms so these
        # tests exercise the truck's gaps and not the card's.
        LoanTerms.objects.create(user=self.user, account=self.card,
                                 apr=Decimal("19.99"), minimum_payment=Decimal("35"))

    def test_asking_about_a_debt_wlj_does_not_have_is_answered_precisely(self):
        packet = E.single_debt_priority_packet(self.user, "boat")
        self.assertFalse(packet["answerable"])
        self.assertEqual(packet["reason"], "no_such_debt")
        self.assertIn("added by hand", packet["detail"])
        self.assertIn("Truck loan", packet["known_debts"])

    def test_a_debt_without_terms_produces_a_guided_request_not_a_guess(self):
        packet = E.single_debt_priority_packet(self.user, "truck")
        self.assertFalse(packet["answerable"])
        self.assertEqual(packet["reason"], "missing_terms")
        self.assertIn("apr", packet["missing"])
        self.assertIn("will not assume a rate", packet["detail"])

    def test_what_is_still_true_is_offered_alongside_the_refusal(self):
        packet = E.single_debt_priority_packet(self.user, "truck")
        self.assertEqual(packet["what_is_still_true"]["balance"], "24000.00")

    def test_with_terms_the_question_becomes_answerable(self):
        LoanTerms.objects.create(user=self.user, account=self.truck,
                                 apr=Decimal("7.25"),
                                 minimum_payment=Decimal("450"))
        packet = E.single_debt_priority_packet(self.user, "truck")
        self.assertTrue(packet["answerable"])
        # The 19.99% card outranks the 7.25% truck under avalanche — which is the
        # whole point of asking. "Should I pay off the truck first?" gets a real
        # answer, and it is no.
        self.assertEqual(packet["avalanche_position"], 2)
        self.assertEqual(packet["avalanche_order"][0], "Card")

    def test_the_comparison_never_declares_a_winner(self):
        LoanTerms.objects.create(user=self.user, account=self.truck,
                                 apr=Decimal("7.25"),
                                 minimum_payment=Decimal("450"))
        packet = E.payoff_comparison_packet(self.user)
        self.assertTrue(packet["comparable"])
        self.assertIn("does not declare a winner", packet["trade_off"]["note"])

    def test_the_debt_packet_names_every_gap(self):
        packet = E.debt_packet(self.user)
        gaps = {d["name"]: d["missing"] for d in packet["debts_missing_terms"]}
        self.assertIn("apr", gaps["Truck loan"])

    def test_an_extra_payment_scenario_is_computable_by_wlj_not_the_model(self):
        LoanTerms.objects.create(user=self.user, account=self.truck,
                                 apr=Decimal("7.25"),
                                 minimum_payment=Decimal("450"))
        base = E.payoff_packet(self.user)
        faster = E.payoff_packet(self.user, extra_monthly=Decimal("300"))
        self.assertTrue(faster["answerable"])
        self.assertLess(faster["scenario"]["months"], base["scenario"]["months"])


class MissingDataTests(RoleBase):
    def test_the_savings_question_says_exactly_what_it_needs(self):
        packet = E.find_amount_packet(self.user, 100)
        self.assertFalse(packet["reached"])
        self.assertTrue(packet["missing"])

    def test_the_controllable_question_says_exactly_what_it_needs(self):
        packet = E.controllable_packet(self.user)
        self.assertIsNone(packet["answer"])
        self.assertTrue(packet["missing"])

    def test_obligations_distinguish_confirmed_from_awaiting_review(self):
        RecurringSeries.objects.create(
            user=self.user, name="Filmflix", payee="filmflix",
            amount_expected=Decimal("15"),
            review_state=RecurringSeries.REVIEW_CANDIDATE)
        packet = E.obligations_packet(self.user)
        self.assertEqual(packet["monthly_committed"], "0.00")
        self.assertEqual(packet["awaiting_review"], 1)
        self.assertEqual(packet["confirmed"], [])


class OwnershipTests(RoleBase):
    def test_no_packet_reaches_another_households_data(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="e2@example.com", password="pw"))
        FinancialAccount.objects.create(
            user=other, name="Their yacht loan", account_type="loan",
            current_balance=Decimal("-999999"))
        packet = E.debt_packet(self.user)
        self.assertNotIn("Their yacht loan", str(packet))
        # Only this user's own card from the base fixture.
        self.assertEqual(packet["total_balance"], "500.00")


class DomainTruthExposureTests(RoleBase):
    """The packets have to be REACHABLE, or they are a library nobody calls.

    A previous WLJ lesson, twice over: truth that exists but is not exposed produces a
    generic answer, and it looks exactly like a missing capability.
    """

    def setUp(self):
        super().setUp()
        from apps.finance.services.finance_domain_truth import FinanceDomainTruth
        self.truth = FinanceDomainTruth(self.user)

    PACKETS = ("measures", "debt", "payoff", "payoff_comparison", "obligations",
               "controllable_costs", "savings_opportunities", "financial_snapshot",
               "data_health", "forecast", "affordability", "net_worth",
               "net_worth_history", "plan_results", "data_health_detail",
               "money_bridge")

    def test_every_packet_is_declared_as_an_entity_type(self):
        for entity_type in self.PACKETS:
            with self.subTest(entity_type=entity_type):
                self.assertIn(entity_type, self.truth.entity_types)

    def test_every_declared_packet_actually_resolves(self):
        for entity_type in self.PACKETS:
            with self.subTest(entity_type=entity_type):
                result = self.truth.describe(entity_type)
                self.assertEqual(len(result), 1)
                self.assertIn("envelope", result[0])

    def test_a_named_debt_question_routes_to_the_priority_packet(self):
        FinancialAccount.objects.create(
            user=self.user, name="Truck loan", account_type="loan",
            current_balance=Decimal("-24000"))
        result = self.truth.describe("debt", {"name": "truck"})[0]
        self.assertEqual(result["packet"], "debt_priority")

    def test_a_savings_target_routes_to_the_plan_packet(self):
        result = self.truth.describe("savings_opportunities", {"target": "100"})[0]
        self.assertEqual(result["packet"], "savings_plan")
        self.assertEqual(result["target"], "100")

    def test_an_extra_payment_reaches_the_payoff_engine(self):
        account = FinancialAccount.objects.create(
            user=self.user, name="Truck loan", account_type="loan",
            current_balance=Decimal("-24000"))
        LoanTerms.objects.create(user=self.user, account=account,
                                 apr=Decimal("7.25"), minimum_payment=Decimal("450"))
        LoanTerms.objects.create(user=self.user, account=self.card,
                                 apr=Decimal("19.99"), minimum_payment=Decimal("35"))
        base = self.truth.describe("payoff")[0]
        faster = self.truth.describe("payoff", {"extra_monthly": "300"})[0]
        self.assertLess(faster["scenario"]["months"], base["scenario"]["months"])

    def test_a_nonsense_amount_does_not_crash_the_packet(self):
        result = self.truth.describe("payoff", {"extra_monthly": "three hundred"})[0]
        self.assertIn("scenario", result)

    def test_an_unknown_entity_type_is_still_refused(self):
        with self.assertRaises(KeyError):
            self.truth.describe("crystal_ball")


class NewPacketTests(RoleBase):
    """The packets added to finish Finance 2.0, and what they refuse to claim."""

    def test_the_forecast_packet_carries_its_setup_state(self):
        packet = E.forecast_packet(self.user)
        self.assertFalse(packet["projectable"])
        self.assertTrue(packet["setup"]["steps"])
        self.assertIn("route", packet["setup"]["steps"][0])

    def test_affordability_refuses_without_a_forecast(self):
        packet = E.affordability_packet(self.user, 300)
        self.assertFalse(packet["answerable"])
        self.assertEqual(packet["reason"], "no_forecast")
        self.assertIn("will not guess", packet["detail"])

    def test_affordability_refuses_without_a_reserve_target(self):
        """'Without dropping below my emergency fund' needs an emergency fund."""
        from apps.finance.models import RecurringSeries
        RecurringSeries.objects.create(
            user=self.user, name="Salary", payee="salary",
            kind=RecurringSeries.KIND_INCOME, amount_expected=Decimal("4000"),
            review_state=RecurringSeries.REVIEW_CONFIRMED)
        packet = E.affordability_packet(self.user, 300)
        self.assertFalse(packet["answerable"])
        self.assertEqual(packet["reason"], "no_reserve_target")

    def test_affordability_answers_once_a_floor_exists(self):
        from apps.finance.models import CashReserve, RecurringSeries
        RecurringSeries.objects.create(
            user=self.user, name="Salary", payee="salary",
            kind=RecurringSeries.KIND_INCOME, amount_expected=Decimal("4000"),
            review_state=RecurringSeries.REVIEW_CONFIRMED)
        CashReserve.objects.create(
            user=self.user, name="Emergency", kind=CashReserve.KIND_RESERVE,
            target_amount=Decimal("1000"))
        packet = E.affordability_packet(self.user, 300)
        self.assertTrue(packet["answerable"])
        self.assertIn("fits", packet)

    def test_the_net_worth_packet_carries_no_identifying_detail(self):
        from apps.finance.models import TangibleAsset
        TangibleAsset.objects.create(
            user=self.user, name="Truck", asset_type="vehicle",
            vin="1FTFW1ET5DFA12345", street_address="12 Elm Street")
        packet = E.net_worth_packet(self.user)
        blob = str(packet)
        self.assertNotIn("1FTFW1ET5DFA12345", blob)
        self.assertNotIn("Elm Street", blob)
        self.assertIn("Truck", blob)

    def test_net_worth_history_explains_an_empty_series(self):
        packet = E.net_worth_history_packet(self.user)
        self.assertFalse(packet["has_history"])
        self.assertIn("fiction", packet["explanation"])

    def test_plan_results_keep_projected_and_realized_apart(self):
        packet = E.plan_results_packet(self.user)
        self.assertIn("never merged", packet["note"])

    def test_data_health_detail_routes_every_issue_somewhere(self):
        self._txn(-50, primary="FOOD_AND_DRINK")
        for issue in E.data_health_packet(self.user)["issues"]:
            with self.subTest(code=issue["code"]):
                self.assertTrue(issue["route"])

    def test_the_snapshot_explains_the_gross_to_net_gap(self):
        packet = E.snapshot_packet(self.user)
        self.assertIn("spending_bridge", packet)
        self.assertIn("are not purchases", packet["spending_bridge"]["explains"])
