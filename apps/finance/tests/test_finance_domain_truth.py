# ==============================================================================
# File: apps/finance/tests/test_finance_domain_truth.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: FinanceDomainTruth record-level entity exposure (F-1).
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Finance exposes recurring commitments, budgets, and goals as canonical truth.

These replace the fact-retrieval half of the retired `FinanceAIService` endpoints
(subscription review / budget alert / goal encouragement) — but as DETERMINISTIC RECORDS
the model reasons over, not as prose a domain-local prompt generated.

Every assertion here is deterministic. No provider call is made anywhere in this module.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import (
    Budget,
    FinancialAccount,
    FinancialGoal,
    RecurringTransaction,
    TransactionCategory,
)
from apps.finance.services.finance_domain_truth import FinanceDomainTruth

User = get_user_model()


class FinanceEntityTruthTests(TestCase):
    """Record-level Finance truth: shape, facts-only, and ownership isolation."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="finance-truth@example.com", password="x" * 14,
        )
        cls.other = User.objects.create_user(
            email="finance-other@example.com", password="x" * 14,
        )
        cls.today = date.today()
        cls.account = FinancialAccount.objects.create(
            user=cls.user, name="Everyday Checking", account_type="checking",
            current_balance=Decimal("1200.00"),
        )
        cls.category = TransactionCategory.objects.create(
            name="Software", category_type="expense",
        )
        cls.recurring = RecurringTransaction.objects.create(
            user=cls.user, name="Design Tool", transaction_type="expense",
            amount=Decimal("-54.00"), account=cls.account, category=cls.category,
            payee="Design Tool Inc", frequency="monthly",
            start_date=cls.today - timedelta(days=90),
            next_due_date=cls.today + timedelta(days=5),
            is_active=True, total_generated=3,
        )
        cls.budget = Budget.objects.create(
            user=cls.user, month=cls.today.replace(day=1), category=cls.category,
            budgeted_amount=Decimal("100.00"),
        )
        cls.goal = FinancialGoal.objects.create(
            user=cls.user, name="Vacation Fund", goal_type="savings",
            target_amount=Decimal("3000.00"), current_amount=Decimal("750.00"),
            target_date=cls.today + timedelta(days=200),
        )

    def _entities(self, kind, filters=None):
        return [e.to_dict() for e in
                FinanceDomainTruth(self.user).describe(kind, filters=filters)]

    # -- registration --------------------------------------------------------
    def test_entity_types_declared(self):
        self.assertEqual(
            FinanceDomainTruth.entity_types,
            ("transaction", "account", "recurring", "budget", "goal", "entity",
             "connection"),
        )

    def test_unknown_entity_type_is_rejected(self):
        with self.assertRaises(KeyError):
            FinanceDomainTruth(self.user).describe("payee")

    # -- recurring -----------------------------------------------------------
    def test_recurring_entities(self):
        rows = self._entities("recurring")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["kind"], "recurring")
        self.assertEqual(row["identity"], "Design Tool")
        self.assertEqual(row["definition"]["amount"], -54.0)
        self.assertEqual(row["definition"]["direction"], "expense")
        self.assertEqual(row["definition"]["frequency"], "monthly")
        self.assertEqual(row["definition"]["account"], "Everyday Checking")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["plan"]["next_due_date"],
                         (self.today + timedelta(days=5)).isoformat())
        self.assertEqual(row["performance"]["occurrences_generated"], 3)

    def test_paused_recurring_reports_paused_not_missing(self):
        self.recurring.is_active = False
        self.recurring.save(update_fields=["is_active"])
        self.assertEqual(self._entities("recurring")[0]["status"], "paused")

    # -- budget --------------------------------------------------------------
    def test_budget_entities_reuse_the_existing_authority(self):
        rows = self._entities("budget")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["kind"], "budget")
        self.assertEqual(row["identity"], "Software")
        # The Budget model remains the ONE authority for these numbers.
        self.assertEqual(row["definition"]["budgeted_amount"],
                         float(self.budget.total_budget))
        self.assertEqual(row["standing"]["spent_amount"], float(self.budget.spent_amount))
        self.assertEqual(row["standing"]["remaining_amount"],
                         float(self.budget.remaining_amount))
        self.assertEqual(row["plan"]["month"], self.budget.month.isoformat())

    def test_budget_defaults_to_current_month(self):
        Budget.objects.create(
            user=self.user, month=(self.today.replace(day=1) - timedelta(days=90)),
            category=self.category, budgeted_amount=Decimal("80.00"),
        )
        self.assertEqual(len(self._entities("budget")), 1)

    # -- goal ----------------------------------------------------------------
    def test_goal_entities(self):
        rows = self._entities("goal")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["kind"], "goal")
        self.assertEqual(row["identity"], "Vacation Fund")
        self.assertEqual(row["definition"]["goal_type"], "savings")
        self.assertEqual(row["definition"]["target_amount"], 3000.0)
        self.assertIsNone(row["definition"]["linked_life_goal"])
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["standing"]["current_amount"], 750.0)
        self.assertEqual(row["standing"]["remaining_amount"],
                         float(self.goal.remaining_amount))

    # -- facts-only ----------------------------------------------------------
    def test_no_verdicts_or_sensitive_fields_are_exposed(self):
        """Facts only, and only the fields reasoning needs.

        `Budget.health_status` is a verdict — the model interprets, WLJ never rules
        (Constitution I.4). Free-text notes and credentials are never surfaced.
        """
        forbidden = {
            "health_status", "health_status_color", "spent_percentage",
            "progress_percentage", "notes", "description", "access_token",
            "account_number", "plaid_transaction_id", "custom_pattern",
        }
        for kind in ("recurring", "budget", "goal"):
            for row in self._entities(kind):
                for bucket in ("definition", "plan", "standing", "performance"):
                    overlap = forbidden & set(row.get(bucket) or {})
                    self.assertEqual(
                        overlap, set(),
                        f"{kind}.{bucket} exposed forbidden field(s): {overlap}",
                    )

    def test_freshness_and_confidence_envelope_present(self):
        for kind in ("recurring", "budget", "goal"):
            for row in self._entities(kind):
                self.assertTrue(row["freshness"])
                self.assertTrue(row["confidence"])

    # -- authorization -------------------------------------------------------
    def test_ownership_isolation(self):
        """A second user's Finance records never appear — the query IS the boundary."""
        truth = FinanceDomainTruth(self.other)
        for kind in ("recurring", "budget", "goal", "transaction", "account"):
            self.assertEqual(
                list(truth.describe(kind)), [],
                f"{kind}: another user's records leaked across the ownership boundary",
            )
