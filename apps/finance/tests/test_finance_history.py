# ==============================================================================
# File: apps/finance/tests/test_finance_history.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: FinanceHistory — deterministic monthly cash-flow trend truth, and Finance's
#   whole-domain executive-assessment coverage (state + trends). Model-free.
# ==============================================================================
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.domain_analysis import get_domain_analysis
from apps.finance.models import FinancialAccount, Transaction
from apps.finance.services.finance_history import FinanceHistory

User = get_user_model()


class FinanceHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="fin@test.com", password="x")
        self.acct = FinancialAccount.objects.create(
            user=self.user, name="Checking", account_type="checking",
            current_balance=Decimal("1000.00"))

    def _txn(self, y, m, d, amount):
        return Transaction.objects.create(
            user=self.user, account=self.acct, date=date(y, m, d),
            amount=Decimal(str(amount)), description="t")

    def test_monthly_spending_and_income_trend(self):
        # Two months of activity → a real trend (>=2 points).
        self._txn(2026, 6, 5, -100)   # June spend 100
        self._txn(2026, 6, 20, 3000)  # June income 3000
        self._txn(2026, 7, 5, -250)   # July spend 250
        self._txn(2026, 7, 20, 3000)  # July income 3000

        spend = FinanceHistory.spending(self.user, start=date(2026, 6, 1),
                                        end=date(2026, 7, 31)).to_dict()
        self.assertTrue(spend["present"])
        self.assertEqual(spend["count"], 2)                 # two monthly buckets
        self.assertEqual([p["value"] for p in spend["points"]],
                         [Decimal("100.00"), Decimal("250.00")])
        self.assertEqual(spend["change"]["direction"], "rising")   # spending went up

        income = FinanceHistory.income(self.user, start=date(2026, 6, 1),
                                       end=date(2026, 7, 31)).to_dict()
        self.assertEqual([p["value"] for p in income["points"]],
                         [Decimal("3000.00"), Decimal("3000.00")])

    def test_transfers_and_opening_balance_excluded(self):
        from apps.finance.models import TransactionCategory
        transfer = TransactionCategory.objects.create(
            user=self.user, name="Transfer", category_type="transfer")
        Transaction.objects.create(user=self.user, account=self.acct,
                                   date=date(2026, 6, 10), amount=Decimal("-500"),
                                   description="xfer", category=transfer)
        Transaction.objects.create(user=self.user, account=self.acct,
                                   date=date(2026, 6, 1), amount=Decimal("1000"),
                                   description="opening", is_opening_balance=True)
        self._txn(2026, 6, 15, -80)   # the only real expense
        spend = FinanceHistory.spending(self.user, start=date(2026, 6, 1),
                                        end=date(2026, 6, 30)).to_dict()
        self.assertEqual(spend["total"], Decimal("80.00"))   # transfer + opening excluded

    def test_empty_is_not_zero(self):
        # A month with no transactions produces NO point — never a fabricated 0.
        spend = FinanceHistory.spending(self.user, start=date(2026, 1, 1),
                                        end=date(2026, 3, 31)).to_dict()
        self.assertFalse(spend["present"])
        self.assertEqual(spend["points"], [])


class FinanceExecutiveAssessmentTests(TestCase):
    """Finance is the reference: 'how are my finances' composes STATE + TRENDS and never
    returns 'unsupported'."""

    def setUp(self):
        self.user = User.objects.create_user(email="fin2@test.com", password="x")
        self.acct = FinancialAccount.objects.create(
            user=self.user, name="Checking", account_type="checking",
            current_balance=Decimal("1000.00"))
        for m in (6, 7):
            Transaction.objects.create(user=self.user, account=self.acct,
                                       date=date(2026, m, 10), amount=Decimal("-200"),
                                       description="spend")
            Transaction.objects.create(user=self.user, account=self.acct,
                                       date=date(2026, m, 15), amount=Decimal("3000"),
                                       description="pay")

    def test_finance_overall_composes_trends_not_unsupported(self):
        a = get_domain_analysis(self.user, "finance", "overall", period="this_year")
        self.assertEqual(a["status"], "ready")          # NOT unsupported
        self.assertTrue(a["holds_data"])
        # Trend facets present (spending/income composed over the window).
        self.assertIn("spending", a["subjects"])
        self.assertTrue(a["subjects"]["spending"]["present"])
