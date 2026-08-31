# ==============================================================================
# File: apps/finance/tests/test_spend_ranking_truth.py
# Description: Contract — FINANCE SPEND RANKING (analytical transaction truth).
#
#   Production friction: "What is my largest spend this past month?" →
#   "It seems I can't directly retrieve your largest spend ... you can check your
#   transaction history in your financial overview."
#
#   The model was honest, not broken: Finance transactions were RETRIEVABLE but not
#   RANKABLE. `describe('transaction')` orders by DATE and caps at 100, so "largest"
#   had no deterministic path — and on a busy month the largest spend can fall outside
#   the returned window entirely.
#
#   Fix reuses the existing platform ranked-entity capability (whose own docstring
#   names "which expenses were largest") plus the existing Finance population and sign
#   conventions. No new accounting rule, no new tool, no provider call.
# ==============================================================================
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services.domain_ranked_entity import (
    RANKING_SUBJECTS, get_domain_ranked_entity,
)
from apps.finance.models import FinancialAccount, Transaction

SUBJECT = "transaction_by_spend"


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="spendrank@test.com", password="x")
        cls.other = get_user_model().objects.create_user(
            email="spendrank-other@test.com", password="x")
        cls.acct = FinancialAccount.objects.create(
            user=cls.user, name="Everyday Checking", account_type="checking")
        cls.acct2 = FinancialAccount.objects.create(
            user=cls.user, name="Rewards Card", account_type="credit_card")

    def _tx(self, amount, *, days_ago=3, payee="Merchant", account=None, user=None,
            description=None, **kw):
        return Transaction.objects.create(
            user=user or self.user, account=account or self.acct,
            amount=Decimal(str(amount)),
            date=timezone.localdate() - timedelta(days=days_ago),
            description=description or payee, payee=payee, **kw)

    def _rank(self, period="this_month", limit=10, user=None):
        return get_domain_ranked_entity(user or self.user, SUBJECT,
                                        period=period, limit=limit)

    def _names(self, env):
        return [r["name"] for r in (env.get("results") or [])]


class RegistrationTests(TestCase):
    def test_the_subject_is_registered_and_declared_not_arbitrary(self):
        spec = RANKING_SUBJECTS[SUBJECT]
        self.assertEqual(spec["domain"], "finance")
        self.assertEqual(spec["entity_type"], "transaction")
        self.assertEqual(spec["measure_key"], "spend_amount")
        self.assertEqual(spec["aggregation"], "occurrence")

    def test_it_is_advertised_to_the_model(self):
        from apps.ai.cos_services.current_context import _capabilities
        self.assertIn(SUBJECT,
                      _capabilities()["truth_ranked_entity"].get("finance", []))

    def test_the_producer_orders_by_the_measure_not_by_date(self):
        """Without this the capped population is date-ordered and the ranking can
        silently omit the largest spend."""
        self.assertEqual(RANKING_SUBJECTS[SUBJECT]["producer_filters"],
                         {"order_by": "spend_desc"})


class LargestSpendTests(_Base):
    def test_largest_actual_spend_in_a_period(self):
        self._tx(-42.10, payee="Coffee")
        self._tx(-318.44, payee="Big Purchase")
        self._tx(-95.00, payee="Groceries")
        env = self._rank()
        self.assertEqual(env["status"], "ready", env)
        self.assertEqual(self._names(env)[0], "Big Purchase")
        self.assertAlmostEqual(env["results"][0]["value"], 318.44, places=2)

    def test_top_five_spending_transactions(self):
        for i in range(9):
            self._tx(-(10 + i * 10), payee=f"M{i}")
        env = self._rank(limit=5)
        self.assertEqual(len(env["results"]), 5)
        values = [r["value"] for r in env["results"]]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertAlmostEqual(values[0], 90.0, places=2)

    def test_income_never_becomes_spend(self):
        self._tx(-120.00, payee="Purchase")
        self._tx(5400.00, payee="Payroll Deposit")
        env = self._rank()
        self.assertNotIn("Payroll Deposit", self._names(env))
        self.assertEqual(self._names(env)[0], "Purchase")

    def test_a_refund_is_an_inflow_and_is_not_ranked_as_spend(self):
        """Refund treatment follows the EXISTING sign convention — no new rule."""
        self._tx(-60.00, payee="Store Purchase")
        self._tx(250.00, payee="Store Refund")
        env = self._rank()
        self.assertNotIn("Store Refund", self._names(env))

    def test_multiple_accounts_are_ranked_together(self):
        self._tx(-80.00, payee="Checking Buy", account=self.acct)
        self._tx(-410.00, payee="Card Buy", account=self.acct2)
        env = self._rank()
        self.assertEqual(self._names(env)[0], "Card Buy")
        accounts = {r["meta"].get("account") for r in env["results"]}
        self.assertEqual(accounts, {"Everyday Checking", "Rewards Card"})

    def test_no_matching_spend_is_reported_honestly(self):
        self._tx(1000.00, payee="Only Income")
        env = self._rank()
        # An honest "nothing to rank" state — not a fabricated zero and not an error.
        self.assertIn(env["status"], ("empty", "ready"))
        self.assertEqual(env.get("results") or [], [])

    def test_bounded_result_size(self):
        from apps.core.truth.ranked_entity import MAX_LIMIT
        for i in range(60):
            self._tx(-(5 + i), payee=f"T{i}")
        env = self._rank(limit=500)
        self.assertLessEqual(len(env["results"]), MAX_LIMIT)

    def test_cross_user_isolation(self):
        self._tx(-25.00, payee="Mine")
        self._tx(-9999.00, payee="Theirs", user=self.other,
                 account=FinancialAccount.objects.create(
                     user=self.other, name="Other", account_type="checking"))
        env = self._rank()
        self.assertNotIn("Theirs", self._names(env))

    def test_the_ranked_result_carries_when_and_where(self):
        """So the answer can be 'X at Y on DATE' from truth, not from inference."""
        self._tx(-201.00, payee="Named Merchant", days_ago=4)
        top = self._rank()["results"][0]
        self.assertTrue(top.get("occurred_on"), "ranked result has no date")
        self.assertEqual(top["meta"].get("payee"), "Named Merchant")
        self.assertEqual(top["meta"].get("direction"), "expense")


class TransferAndPaymentSemanticsTests(_Base):
    """Transfers/card payments follow the EXISTING population authority — this suite
    proves the ranking inherits it rather than re-deciding what counts."""

    def test_a_transfer_larger_than_any_purchase_is_not_the_largest_spend(self):
        self._tx(-150.00, payee="Real Purchase")
        self._tx(-4000.00, payee="Transfer to Savings",
                 transfer_state=Transaction.TRANSFER_STATE_CONFIRMED)
        env = self._rank()
        self.assertNotIn("Transfer to Savings", self._names(env),
                         "a transfer was ranked as spending")
        self.assertEqual(self._names(env)[0], "Real Purchase")

    def test_the_ranking_uses_the_shared_population_authority(self):
        import inspect

        from apps.finance.services import finance_domain_truth
        src = inspect.getsource(finance_domain_truth.FinanceDomainTruth.describe)
        self.assertIn("financial_activity(self.user)", src,
                      "the ranking must inherit the ONE population definition")

    def test_opening_balances_are_excluded_by_the_population(self):
        self._tx(-75.00, payee="Purchase")
        self._tx(-8000.00, payee="Opening Balance", is_opening_balance=True)
        self.assertNotIn("Opening Balance", self._names(self._rank()))


class DateSemanticsTests(_Base):
    def test_period_is_resolved_deterministically(self):
        self._tx(-100.00, days_ago=2, payee="In Window")
        env = self._rank(period="last_30_days")
        self.assertEqual(env["status"], "ready")
        self.assertIn("In Window", self._names(env))

    def test_a_transaction_outside_the_range_is_excluded(self):
        self._tx(-100.00, days_ago=2, payee="Recent")
        self._tx(-9000.00, days_ago=400, payee="Ancient")
        env = self._rank(period="last_30_days")
        self.assertNotIn("Ancient", self._names(env))
        self.assertEqual(self._names(env)[0], "Recent")

    def test_an_unresolvable_period_fails_honestly(self):
        env = self._rank(period="whenever-ish")
        self.assertEqual(env["status"], "unsupported")


class CapCannotHideTheLargestTests(_Base):
    """The specific correctness trap: the producer caps its result, so a date-ordered
    population would drop the largest spend on a busy month."""

    def test_the_largest_spend_survives_a_population_larger_than_the_cap(self):
        from apps.finance.services.finance_domain_truth import FinanceDomainTruth
        cap = FinanceDomainTruth._MAX_TX
        # the big one is the OLDEST, so a date-ordered cap would drop it
        self._tx(-7777.00, days_ago=20, payee="Oldest Biggest")
        for i in range(cap + 25):
            self._tx(-(1 + (i % 50)), days_ago=1, payee=f"Noise{i}")
        env = self._rank()
        self.assertEqual(self._names(env)[0], "Oldest Biggest",
                         "the cap hid the largest spend")


class NoProviderCallTests(_Base):
    def test_ranking_requires_no_model_or_network_call(self):
        import apps.ai.cos_services.domain_ranked_entity as dre
        self._tx(-10.00, payee="X")
        with self.assertRaises(AssertionError):
            # sanity: this context manager only fires if something calls out
            with self.assertLogs("openai", level="DEBUG"):
                self._rank()
        self.assertNotIn("openai", inspect_module_source(dre).lower())


def inspect_module_source(mod):
    import inspect
    return inspect.getsource(mod)
