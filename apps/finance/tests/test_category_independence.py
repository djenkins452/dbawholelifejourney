# ==============================================================================
# File: apps/finance/tests/test_category_independence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance works correctly with ZERO transaction categories.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Categories are optional metadata; entity attribution is the canonical classification.

Production holds zero `TransactionCategory` rows. This locks in the conclusion that this
is correct rather than a gap: the Plaid sync path never assigns a category, and every
downstream surface — population, attribution, detection, truth, review, reporting —
handles an uncategorised transaction as ordinary truth.

The one honest consequence is asserted too: the population contract's category-based
transfer exclusion cannot fire on synced data, which is exactly why the suspected-internal
-transfer review class exists.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import (
    FinancialAccount,
    FinancialEntity,
    Transaction,
    TransactionAttribution,
    TransactionCategory,
)
from apps.finance.services import attribution as attribution_service
from apps.finance.services import attribution_population as population
from apps.finance.services import finance_entities as entity_service
from apps.finance.services import opportunity_detection as detection
from apps.finance.services.attribution_review import review_counts
from apps.finance.services.finance_domain_truth import FinanceDomainTruth
from apps.finance.services.finance_intelligence_summary import build_finance_intelligence

User = get_user_model()
TODAY = date.today()


class ZeroCategoryTests(TestCase):
    """Everything below runs with NOT ONE category row in the database."""

    def setUp(self):
        TransactionCategory.objects.all().delete()
        self.user = User.objects.create_user(email="nocat@example.com",
                                             password="x" * 14)
        self.personal, _ = entity_service.ensure_default_entities(self.user)
        self.business = entity_service.create_entity(
            self.user, entity_type=FinancialEntity.TYPE_BUSINESS, name="Harbor")
        self.checking = FinancialAccount.objects.create(
            user=self.user, name="Checking", account_type="checking")
        self.card = FinancialAccount.objects.create(
            user=self.user, name="Company Card", account_type="credit_card")
        entity_service.assign_account_entity(
            self.user, self.checking, self.personal,
            effective_from=TODAY - timedelta(days=400))
        entity_service.assign_account_entity(
            self.user, self.card, self.business,
            effective_from=TODAY - timedelta(days=400))

    def _synced_txn(self, **kw):
        """Shaped exactly like `sync_service._sync_transaction` builds one: NO category."""
        defaults = dict(
            user=self.user, account=self.checking, date=TODAY,
            amount=Decimal("-54.00"), description="Design Tool",
            payee="Design Tool Inc", plaid_transaction_id="ptx-1",
            plaid_pending=False, is_cleared=True)
        defaults.update(kw)
        txn = Transaction.objects.create(**defaults)
        self.assertIsNone(txn.category_id, "the sync path assigns no category")
        return txn

    def test_no_categories_exist(self):
        self.assertEqual(TransactionCategory.objects.count(), 0)
        self.assertEqual(TransactionCategory.get_for_user(self.user).count(), 0)

    def test_uncategorised_transaction_is_attributable(self):
        txn = self._synced_txn()
        self.assertIsNone(population.exclusion_reason(txn))
        self.assertIn(txn.id, set(
            population.attributable_transactions(self.user).values_list("id", flat=True)))

    def test_attribution_works_without_a_category(self):
        txn = self._synced_txn()
        row = attribution_service.confirm(self.user, txn, self.business)
        self.assertTrue(row.user_confirmed)
        self.assertEqual(row.attributed_entity_id, self.business.id)

    def test_detection_works_without_a_category(self):
        txn = self._synced_txn()
        attribution_service.confirm(self.user, txn, self.business)
        findings = detection.build_findings(self.user)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["bearer"].name, "Harbor")

    def test_truth_surface_renders_a_null_category_safely(self):
        txn = self._synced_txn()
        attribution_service.confirm(self.user, txn, self.business)
        row = [e.to_dict() for e in FinanceDomainTruth(self.user)
               .describe("transaction")][0]
        self.assertIsNone(row["definition"]["category"])
        self.assertEqual(row["definition"]["attributed_to"], "Harbor")

    def test_review_and_dashboard_survive_zero_categories(self):
        self._synced_txn()
        counts = review_counts(self.user)
        self.assertEqual(counts["unattributed"], 1)
        intel = build_finance_intelligence(self.user)
        self.assertIn(intel["setup_state"], ("ready", "no_attribution"))

    def test_reporting_totals_ignore_the_missing_category(self):
        from apps.finance.services.finance_history import FinanceHistory
        self._synced_txn()
        series = FinanceHistory.spending(self.user, period="this_year")
        self.assertEqual(abs(Decimal(str(series.total()))), Decimal("54.00"))

    def test_category_transfer_exclusion_cannot_fire_on_synced_data(self):
        """The honest limitation — and why the review class exists.

        Synced rows carry no category, so `category__category_type='transfer'` can never
        match them; `sync_service` never sets `transfer_pair` either. A card payment is
        therefore caught by NAME, as a review candidate, never silently as an expense.
        """
        payment = self._synced_txn(description="Payment to Company Card",
                                   amount=Decimal("-500.00"), payee="")
        self.assertEqual(population.exclusion_reason(payment),
                         population.REVIEW_SUSPECTED_INTERNAL_TRANSFER)
        self.assertNotIn(payment.id, set(
            population.attributable_transactions(self.user).values_list("id", flat=True)))

    def test_sync_path_assigns_no_category(self):
        """Code-backed: the importer neither reads nor writes a category."""
        import inspect

        from apps.finance.services import sync_service
        source = inspect.getsource(sync_service)
        self.assertNotIn("category", source,
                         "if the sync path starts assigning categories, revisit whether "
                         "reference categories become required data")


class CategoryLoaderSafetyTests(TestCase):
    """`load_default_categories` is NOT safe to run as global reference data."""

    def test_loader_scopes_system_categories_to_a_user(self):
        """It marks rows `is_system=True` while also setting `user=<someone>`.

        `get_for_user` matches on `Q(user=user) | Q(is_system=True)`, so a row created
        "for" one user becomes visible to EVERY user — a cross-user classification leak,
        duplicated once per account. This is why production was not seeded from it.
        """
        import inspect

        from apps.finance.management.commands import load_default_categories
        source = inspect.getsource(load_default_categories)
        self.assertIn("user=user", source)
        self.assertIn("'is_system': True", source)

    def test_globally_safe_categories_are_user_null(self):
        """What a genuinely global category looks like — the transfer form builds one."""
        globally_safe = TransactionCategory.objects.create(
            name="Transfer", category_type="transfer", is_system=True, user=None)
        someone = User.objects.create_user(email="anyone@example.com", password="x" * 14)
        self.assertIn(globally_safe,
                      list(TransactionCategory.get_for_user(someone)))
        self.assertIsNone(globally_safe.user_id)
