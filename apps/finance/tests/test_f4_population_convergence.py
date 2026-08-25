# ==============================================================================
# File: apps/finance/tests/test_f4_population_convergence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F4 — every Finance surface reads ONE population definition.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The four competing definitions are gone; agreement is now enforced, not hoped for.

Before F4, Finance answered "what counts as a transaction" four different ways, with two
incompatible definitions of "transfer". These tests assert the surfaces now agree AND that
no new definition can quietly appear.
"""
from __future__ import annotations

import inspect
import re
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import (
    Budget,
    FinancialAccount,
    FinancialMetricSnapshot,
    Transaction,
    TransactionCategory,
)
from apps.finance.services.attribution_population import financial_activity
from apps.finance.services.finance_domain_truth import FinanceDomainTruth
from apps.finance.services.finance_history import FinanceHistory

User = get_user_model()


class PopulationAgreementTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="f4@example.com", password="x" * 14)
        self.today = date.today()
        self.month_start = self.today.replace(day=1)
        self.account = FinancialAccount.objects.create(
            user=self.user, name="Checking", account_type="checking",
        )
        self.groceries = TransactionCategory.objects.create(
            name="Groceries", category_type="expense",
        )
        self.transfer_cat = TransactionCategory.objects.create(
            name="Transfer", category_type="transfer", is_system=True,
        )
        # One real expense — the only row every surface should count.
        self.real = self._txn(Decimal("-100.00"), category=self.groceries)
        # The three kinds that used to be counted by SOME surfaces and not others.
        self.opening = self._txn(Decimal("500.00"), is_opening_balance=True)
        self.categorised_transfer = self._txn(Decimal("-250.00"),
                                              category=self.transfer_cat)
        out_leg = self._txn(Decimal("-75.00"))
        in_leg = self._txn(Decimal("75.00"))
        out_leg.transfer_pair = in_leg
        out_leg.save(update_fields=["transfer_pair"])
        in_leg.transfer_pair = out_leg
        in_leg.save(update_fields=["transfer_pair"])
        self.paired_out = out_leg

    def _txn(self, amount, **kw):
        return Transaction.objects.create(
            user=self.user, account=self.account,
            date=self.month_start + timedelta(days=1), amount=amount,
            description="row", **kw,
        )

    def test_the_authority_counts_only_real_activity(self):
        ids = set(financial_activity(self.user).values_list("id", flat=True))
        self.assertEqual(ids, {self.real.id})

    def test_history_agrees_with_the_authority(self):
        series = FinanceHistory.spending(self.user, period="this_year")
        self.assertEqual(abs(Decimal(str(series.total()))), Decimal("100.00"))

    def test_metric_snapshot_agrees_with_the_authority(self):
        snapshot = FinancialMetricSnapshot.create_snapshot(self.user)
        self.assertEqual(snapshot.monthly_expenses, Decimal("100.00"))
        self.assertEqual(snapshot.monthly_income, Decimal("0.00"),
                         "an opening balance and a transfer leg are not income")

    def test_budget_agrees_with_the_authority(self):
        budget = Budget.objects.create(
            user=self.user, month=self.month_start, category=self.groceries,
            budgeted_amount=Decimal("400.00"),
        )
        self.assertEqual(budget.spent_amount, Decimal("100.00"))

        transfer_budget = Budget.objects.create(
            user=self.user, month=self.month_start, category=self.transfer_cat,
            budgeted_amount=Decimal("100.00"),
        )
        self.assertEqual(transfer_budget.spent_amount, Decimal("0.00"),
                         "a transfer must never be reported as spend")

    def test_domain_truth_agrees_with_the_authority(self):
        rows = FinanceDomainTruth(self.user).describe("transaction")
        self.assertEqual(len(rows), 1)

    def test_all_surfaces_return_the_same_row_set(self):
        expected = {self.real.id}
        self.assertEqual(
            set(financial_activity(self.user).values_list("id", flat=True)), expected)
        self.assertEqual(len(FinanceDomainTruth(self.user).describe("transaction")),
                         len(expected))


class NoSecondDefinitionTests(TestCase):
    """A fifth definition cannot appear quietly."""

    AUTHORITY = "apps/finance/services/attribution_population.py"
    #: Deliberate, documented exceptions.
    ALLOWED = {
        # Detection re-asserts the contract at READ time: a transaction can be
        # soft-deleted or re-categorised AFTER it was attributed (the F1 defect fix).
        "apps/finance/services/opportunity_detection.py",
        # The audit command's whole purpose is to compare the OLD and NEW definitions.
        "apps/finance/management/commands/finance_population_audit.py",
    }

    def test_no_surface_redefines_what_counts_as_activity(self):
        """Flags EXCLUSION of activity outside the authority.

        Looking an opening-balance row UP (account-balance arithmetic, `models.py:257`) is
        the opposite question and stays legal — a balance includes transfers and opening
        rows; *activity* does not. What must never be re-derived is the exclusion.
        """
        import ast
        from pathlib import Path

        finance_dir = Path(__file__).resolve().parents[1]
        repo_root = finance_dir.parents[1]
        offenders = []

        def flags(keyword):
            name = keyword.arg or ""
            base = name.split("transaction__")[-1]
            if base in ("is_opening_balance",):
                value = keyword.value
                return isinstance(value, ast.Constant) and value.value is False
            if base.startswith("transfer_pair"):
                return True
            if base.startswith("category__category_type"):
                value = keyword.value
                return isinstance(value, ast.Constant) and value.value == "transfer"
            return False

        for path in finance_dir.rglob("*.py"):
            parts = path.parts
            if any(skip in parts for skip in ("migrations", "tests", "__pycache__")):
                continue
            rel = path.relative_to(repo_root).as_posix()
            if rel == self.AUTHORITY or rel in self.ALLOWED:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Attribute) or \
                        func.attr not in ("filter", "exclude"):
                    continue
                for keyword in node.keywords:
                    if flags(keyword):
                        offenders.append(f"{rel}:{node.lineno} {keyword.arg}")
        self.assertEqual(
            offenders, [],
            "A second definition of 'what counts as activity' appeared. Route it through "
            f"financial_activity(): {offenders}",
        )

    def test_consumers_import_the_authority(self):
        for module in (
            "apps.finance.services.finance_history",
            "apps.finance.services.finance_domain_truth",
        ):
            imported = __import__(module, fromlist=["*"])
            self.assertIn("financial_activity", inspect.getsource(imported),
                          f"{module} must consume the shared authority")

    def test_audit_command_exists_for_production_measurement(self):
        from django.core.management import get_commands
        self.assertEqual(get_commands().get("finance_population_audit"), "apps.finance")
