# ==============================================================================
# File: apps/finance/tests/test_finance_trust_lifecycle.py
# Description: INTEGRATED DETERMINISTIC CERTIFICATION of the Finance answer path.
#
#   One seeded household exercised end to end against the real production failures:
#   a loan payment that outranked every purchase, an August question answered with
#   July data, a $5,000 card payment that both was and was not spending, and a $2,300
#   mortgage the user invented to see whether the assistant would repeat it.
#
#   Fixtures only. ZERO provider calls.
# ==============================================================================
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai import finance_claim_guard as guard
from apps.ai.cos_services.domain_entity import get_domain_entity
from apps.ai.cos_services.domain_ranked_entity import get_domain_ranked_entity
from apps.finance.models import FinancialAccount, Transaction as T
from apps.finance.services.finance_calc import measures as M

WINDOW = "past 30 days"


class _Household(TestCase):
    """A realistic canonical population — every economic role the incident touched."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="lifecycle@test.com", password="x")
        cls.other = get_user_model().objects.create_user(
            email="lifecycle-other@test.com", password="x")
        cls.chk = FinancialAccount.objects.create(
            user=cls.user, name="Checking", account_type="checking")
        cls.card = FinancialAccount.objects.create(
            user=cls.user, name="Rewards Card", account_type="credit_card")

        def tx(amount, *, days, payee, acct=None, cat=None, user=None, **kw):
            return T.objects.create(
                user=user or cls.user, account=acct or cls.chk,
                amount=Decimal(str(amount)),
                date=timezone.localdate() - timedelta(days=days),
                description=payee, payee=payee, **kw)

        # ── consumption ──────────────────────────────────────────────────────
        cls.big_purchase = tx(-1450.00, days=5, payee="Roof Repair",
                              provider_category_primary="HOME_IMPROVEMENT")
        tx(-402.10, days=6, payee="Grocery Run",
           provider_category_primary="FOOD_AND_DRINK_GROCERIES")
        tx(-311.75, days=7, payee="Steakhouse",
           provider_category_primary="FOOD_AND_DRINK_RESTAURANT")
        tx(-95.40, days=8, payee="Bistro",
           provider_category_primary="FOOD_AND_DRINK_RESTAURANT")
        tx(-260.00, days=9, payee="Airline",
           provider_category_primary="TRANSPORTATION")
        # a card PURCHASE — still consumption even though it lands on the card
        cls.card_purchase = tx(-180.00, days=10, payee="Card Store", acct=cls.card,
                               provider_category_primary="GENERAL_MERCHANDISE")

        # ── debt / payment activity (must NOT be consumption) ────────────────
        cls.mortgage = tx(-2388.95, days=4, payee="JPMORGAN MORTGAGE",
                          provider_category_primary="LOAN_PAYMENTS")
        cls.auto_loan = tx(-849.84, days=11, payee="ALLY PAYMT",
                           provider_category_primary="LOAN_PAYMENTS")
        cls.card_payment_unpaired = tx(
            -5000.00, days=3, payee="CRDEPAY",
            provider_category_primary="LOAN_PAYMENTS",
            provider_category_detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        cls.card_payment_paired = tx(
            -700.00, days=12, payee="CARD SETTLEMENT",
            provider_category_primary="LOAN_PAYMENTS",
            provider_category_detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT",
            transfer_state=T.TRANSFER_STATE_CONFIRMED,
            transfer_kind=T.TRANSFER_KIND_CARD_PAYMENT)

        # ── neither spending nor payment ─────────────────────────────────────
        cls.transfer = tx(-9500.00, days=2, payee="TRANSFER TO SAVINGS",
                          transfer_state=T.TRANSFER_STATE_CONFIRMED)
        tx(310.00, days=13, payee="Store Refund",
           provider_category_detailed="GENERAL_MERCHANDISE_REFUND")
        tx(6200.00, days=14, payee="Payroll", provider_category_primary="INCOME")

        # ── the >100-row cap trap: the biggest purchase is also the OLDEST ───
        for i in range(115):
            tx(-(1 + (i % 40)), days=1, payee=f"Noise{i}",
               provider_category_primary="GENERAL_MERCHANDISE")

        # ── another household, to prove isolation ────────────────────────────
        other_acct = FinancialAccount.objects.create(
            user=cls.other, name="Theirs", account_type="checking")
        tx(-99999.00, days=5, payee="THEIR HUGE PURCHASE", acct=other_acct,
           user=cls.other, provider_category_primary="GENERAL_MERCHANDISE")

    def rank(self, subject, *, limit=10, period=WINDOW, user=None):
        return get_domain_ranked_entity(user or self.user, subject,
                                        period=period, limit=limit)

    def names(self, env):
        return [r["name"] for r in (env.get("results") or [])]


class SpendingQuestionsTests(_Household):
    """"largest spend" / "top purchases" — consumption only."""

    def test_largest_spend_is_the_largest_PURCHASE(self):
        env = self.rank("transaction_by_spend")
        self.assertEqual(env["status"], "ready", env)
        self.assertEqual(self.names(env)[0], "Roof Repair")
        self.assertAlmostEqual(env["results"][0]["value"], 1450.00, places=2)

    def test_no_debt_or_settlement_wins_a_spending_question(self):
        listed = set(self.names(self.rank("transaction_by_spend", limit=50)))
        for excluded in ("JPMORGAN MORTGAGE", "ALLY PAYMT", "CRDEPAY",
                         "CARD SETTLEMENT", "TRANSFER TO SAVINGS",
                         "Payroll", "Store Refund"):
            self.assertNotIn(excluded, listed, f"{excluded} ranked as spending")

    def test_a_card_PURCHASE_remains_spending(self):
        self.assertIn("Card Store", self.names(self.rank("transaction_by_spend", limit=50)))

    def test_top_five_are_the_canonical_rows_in_canonical_order(self):
        env = self.rank("transaction_by_spend", limit=5)
        values = [r["value"] for r in env["results"]]
        self.assertEqual(len(values), 5)
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertAlmostEqual(values[0], 1450.00, places=2)

    def test_the_row_cap_cannot_hide_the_largest_purchase(self):
        """115 newer noise rows exist; the largest purchase is older than all of them."""
        self.assertGreater(T.objects.filter(user=self.user).count(), 100)
        self.assertEqual(self.names(self.rank("transaction_by_spend"))[0], "Roof Repair")


class PaymentQuestionsTests(_Household):
    def test_largest_payment_is_the_card_settlement(self):
        env = self.rank("transaction_by_payment")
        self.assertEqual(self.names(env)[0], "CRDEPAY")
        self.assertAlmostEqual(env["results"][0]["value"], 5000.00, places=2)

    def test_payments_include_mortgage_and_auto_loan(self):
        listed = set(self.names(self.rank("transaction_by_payment", limit=50)))
        self.assertIn("JPMORGAN MORTGAGE", listed)
        self.assertIn("ALLY PAYMT", listed)

    def test_payments_exclude_purchases_and_transfers(self):
        listed = set(self.names(self.rank("transaction_by_payment", limit=50)))
        self.assertNotIn("Roof Repair", listed)
        self.assertNotIn("TRANSFER TO SAVINGS", listed)


class CashOutflowQuestionsTests(_Household):
    def test_cash_outflow_spans_purchases_and_payments(self):
        listed = set(self.names(self.rank("transaction_by_cash_outflow", limit=60)))
        self.assertIn("CRDEPAY", listed)
        self.assertIn("Roof Repair", listed)

    def test_cash_outflow_still_excludes_internal_transfers(self):
        """Moving your own money between your own accounts is not money leaving."""
        listed = set(self.names(self.rank("transaction_by_cash_outflow", limit=60)))
        self.assertNotIn("TRANSFER TO SAVINGS", listed)

    def test_the_three_questions_give_three_different_answers(self):
        spend = self.names(self.rank("transaction_by_spend"))[0]
        payment = self.names(self.rank("transaction_by_payment"))[0]
        outflow = self.names(self.rank("transaction_by_cash_outflow"))[0]
        self.assertEqual((spend, payment, outflow),
                         ("Roof Repair", "CRDEPAY", "CRDEPAY"))


class CategoryQuestionsTests(_Household):
    def test_finance_aggregates_categories_deterministically(self):
        env = self.rank("category_by_spend")
        self.assertEqual(env["status"], "ready", env)
        values = [r["value"] for r in env["results"]]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_a_single_category_total_is_computed_by_finance(self):
        rows = M.spend_by_category(
            self.user, timezone.localdate() - timedelta(days=29), timezone.localdate())
        by_name = {r["category"]: r for r in rows}
        self.assertTrue(by_name, "no category aggregation produced")
        for row in rows:
            self.assertIsInstance(row["total"], Decimal)
            self.assertGreaterEqual(row["count"], 1)

    def test_category_totals_exclude_debt_and_transfers(self):
        rows = M.spend_by_category(
            self.user, timezone.localdate() - timedelta(days=29), timezone.localdate())
        total = sum(r["total"] for r in rows)
        self.assertLess(total, Decimal("9000"),
                        "a payment or transfer leaked into category spending")

    def test_the_category_entity_carries_its_largest_purchase(self):
        env = get_domain_entity(self.user, "finance", entity_type="category_spend",
                                filters={"period": "last_30_days"})
        self.assertEqual(env["status"], "ready", env)
        first = (env.get("entities") or [])[0]
        self.assertIn("largest_purchase", first["definition"])


class WhereDidMyMoneyGoTests(_Household):
    def test_the_canonical_bridge_is_reachable(self):
        env = get_domain_entity(self.user, "finance", entity_type="money_bridge",
                                filters={"period": "last_30_days"})
        self.assertIn(env.get("status"), ("ready", "empty"), env)

    def test_it_is_discoverable_by_meaning(self):
        from apps.core.truth.semantics import domain_semantics
        desc = domain_semantics("finance")["entities"]["money_bridge"].lower()
        self.assertIn("where did my money go", desc)


class PeriodSemanticsTests(_Household):
    def test_the_four_phrases_are_pinned(self):
        from datetime import date
        from apps.core.truth.periods import resolve_date_expression
        t = date(2026, 8, 31)
        self.assertEqual(
            [(resolve_date_expression(p, t).start, resolve_date_expression(p, t).end)
             for p in ("this month", "last month", "past month", "past 30 days")],
            [(date(2026, 8, 1), date(2026, 8, 31)),
             (date(2026, 7, 1), date(2026, 7, 31)),
             (date(2026, 8, 2), date(2026, 8, 31)),
             (date(2026, 8, 2), date(2026, 8, 31))])


class IsolationTests(_Household):
    def test_another_households_transactions_never_appear(self):
        for subject in ("transaction_by_spend", "transaction_by_payment",
                        "transaction_by_cash_outflow"):
            self.assertNotIn("THEIR HUGE PURCHASE",
                             self.names(self.rank(subject, limit=60)))


class AdversarialClaimTests(_Household):
    """The production trust failures, as guard outcomes over real evidence."""

    def _evidence(self, subject="transaction_by_spend", limit=5):
        return [self.rank(subject, limit=limit)]

    def test_the_canonical_answer_is_certified(self):
        self.assertEqual(
            guard.validate_finance_claims(
                "Your largest spend was $1,450.00 at Roof Repair.", self._evidence()),
            [])

    def test_a_fabricated_user_amount_is_not_certified(self):
        """"Didn't I have a $2,300 house payment?" — the canonical mortgage is
        $2,388.95, and $2,300 exists nowhere."""
        v = guard.validate_finance_claims(
            "Your July house payment was $2,300.00.", self._evidence())
        self.assertTrue(v, "a fabricated amount was certified as fact")

    def test_the_honest_refusal_is_allowed(self):
        self.assertEqual(
            guard.validate_finance_claims(
                "I can't verify a $2,300.00 house payment — I don't see one.",
                self._evidence()),
            [])

    def test_a_real_omitted_value_is_verifiable(self):
        """The user names the real $5,000 card payment: it IS canonical, on the payment
        surface — so verification confirms it rather than the assistant simply agreeing."""
        self.assertEqual(
            guard.validate_finance_claims(
                "The $5,000.00 CRDEPAY is a credit-card payment, not a purchase.",
                self._evidence("transaction_by_payment")),
            [])

    def test_conversation_history_cannot_supply_evidence(self):
        """Prior prose never reaches the guard; only this turn's retrievals do."""
        v = guard.validate_finance_claims(
            "As I said earlier, your largest expense was $2,300.00.", self._evidence())
        self.assertTrue(v)

    def test_cross_wired_fields_are_not_certified(self):
        v = guard.validate_finance_claims(
            "Your largest spend was $1,450.00 at Steakhouse.", self._evidence())
        self.assertTrue(any(x.get("field") == "merchant" for x in v), v)

    def test_a_ranked_list_out_of_order_is_not_certified(self):
        env = self.rank("transaction_by_spend", limit=3)
        vals = [r["value"] for r in env["results"]]
        text = f"Your top expenses were ${vals[1]:,.2f}, then ${vals[0]:,.2f}."
        self.assertTrue(
            any(x.get("field") == "ranking"
                for x in guard.validate_finance_claims(text, [env])), text)


class SemanticDiscoveryTests(TestCase):
    """The model must find the right canonical subject BY MEANING, not by knowing the
    tool exists. Existence without discoverability is what left "largest spend" with no
    route in the first place."""

    def setUp(self):
        from apps.ai.cos_services.current_context import _capabilities
        from apps.core.truth.semantics import domain_semantics
        self.caps = _capabilities()
        self.sem = domain_semantics("finance")
        self.blob = " ".join([
            self.sem.get("purpose", ""), self.sem.get("boundary", ""),
            " ".join(self.sem.get("cues", []) or []),
            " ".join((self.sem.get("entities") or {}).values()),
        ]).lower()

    def test_all_four_finance_subjects_are_advertised(self):
        advertised = set(self.caps["truth_ranked_entity"].get("finance", []))
        self.assertEqual(advertised, {"transaction_by_spend", "transaction_by_payment",
                                      "transaction_by_cash_outflow",
                                      "category_by_spend"})

    def test_the_natural_phrasings_are_discoverable(self):
        for phrase in ("largest spend", "biggest purchase", "top 5 purchases",
                       "top purchases", "largest payment", "top payments",
                       "largest cash outflow", "top cash outflows",
                       "top spending categories", "how much did i spend dining",
                       "how much did i spend on transportation",
                       "where did my money go"):
            self.assertIn(phrase, self.blob, f"undiscoverable phrasing: {phrase!r}")

    def test_the_three_money_questions_are_distinguished_for_the_model(self):
        """The purpose text must say plainly that spending, payments and cash outflow
        are different questions — the confusion that produced the incident."""
        purpose = self.sem["purpose"].lower()
        self.assertIn("three different money questions", purpose)
        self.assertIn("is not spending", purpose)
        self.assertIn("double-counts", purpose)

    def test_every_subject_the_family_needs_has_a_description(self):
        entities = self.sem.get("entities") or {}
        for required in ("transaction", "category_spend", "money_bridge",
                         "monthly_views", "measures"):
            self.assertTrue((entities.get(required) or "").strip(),
                            f"{required} is advertised without a description")


class DashboardAndCoSShareVocabularyTests(TestCase):
    """The dashboard's spending figure and the CoS's must be the SAME definition.

    Two surfaces holding two definitions of "spend" is how a person is told one number
    on a page and a different one in conversation.
    """

    def test_the_dashboard_reads_the_measure_authority(self):
        import inspect
        from apps.finance import views
        src = inspect.getsource(views)
        self.assertIn("monthly_views", src)
        self.assertIn("net_spending", src)

    def test_the_cos_reads_the_same_authority(self):
        import inspect
        from apps.finance.services import finance_domain_truth as fdt
        src = inspect.getsource(fdt.FinanceDomainTruth._transaction_entity)
        self.assertIn("spend_magnitude", src)

    def test_both_verdicts_come_from_one_module(self):
        """`net_spending` (the dashboard total) and `spend_magnitude` (the CoS per-row
        verdict) are published by the same authority and rest on the same roles."""
        self.assertTrue(hasattr(M, "net_spending"))
        self.assertTrue(hasattr(M, "spend_magnitude"))
        self.assertEqual(M.spend_magnitude.__module__, M.net_spending.__module__)
        self.assertIn("purchase", {r for r in M.consumption_roles()})
