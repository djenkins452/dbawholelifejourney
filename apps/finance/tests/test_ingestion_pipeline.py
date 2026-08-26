# ==============================================================================
# File: apps/finance/tests/test_ingestion_pipeline.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Provider ingestion — provenance, taxonomy, transfers, totals.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Category, economic entity, and transfer state are THREE independent dimensions.

"Software / Beacon / paid from Personal" is three facts, not one. These tests prove each
dimension keeps its own authority, that provider provenance survives ingestion, and that
no transfer or card payment is ever double-counted or silently counted.

Every fixture here is SYNTHETIC. No Plaid call is made and no Link token is created.
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
    TransactionCategory,
)
from apps.finance.services import attribution as attribution_service
from apps.finance.services import attribution_population as population
from apps.finance.services import finance_entities as entity_service
from apps.finance.services import transfer_detection
from apps.finance.services.category_taxonomy import (
    SYSTEM_CATEGORIES,
    map_provider_category,
    seed_system_categories,
    system_category,
)
from apps.finance.services.finance_domain_truth import FinanceDomainTruth
from apps.finance.services.finance_history import FinanceHistory
from apps.finance.services.sync_service import TransactionSyncService

User = get_user_model()
TODAY = date.today()


# ---------------------------------------------------------------------------
# Synthetic provider fixtures — the shape `plaid_service._transaction_to_dict` emits
# ---------------------------------------------------------------------------

def provider_txn(**overrides):
    payload = {
        "transaction_id": "ptx-1",
        "account_id": "pacct-checking",
        "amount": 54.00,                      # provider: positive = money out
        "date": TODAY,
        "name": "DESIGN TOOL INC",
        "merchant_name": "Design Tool",
        "pending": False,
        "category": ["Service", "Software"],
        "category_id": "18000000",
        "pfc_primary": "GENERAL_SERVICES",
        "pfc_detailed": "GENERAL_SERVICES_OTHER_GENERAL_SERVICES",
        "pfc_confidence": "VERY_HIGH",
        "payment_channel": "online",
        "transaction_code": "",
        "pending_transaction_id": "",
        "authorized_date": TODAY - timedelta(days=1),
        "counterparties": [{"name": "Design Tool", "type": "merchant"}],
        "location": None,
    }
    payload.update(overrides)
    return payload


class IngestionBase(TestCase):
    def setUp(self):
        seed_system_categories()
        self.user = User.objects.create_user(email="ingest@example.com",
                                             password="x" * 14)
        self.personal, _ = entity_service.ensure_default_entities(self.user)
        self.business = entity_service.create_entity(
            self.user, entity_type=FinancialEntity.TYPE_BUSINESS, name="Beacon")
        self.checking = FinancialAccount.objects.create(
            user=self.user, name="Personal Checking", account_type="checking",
            plaid_account_id="pacct-checking")
        self.savings = FinancialAccount.objects.create(
            user=self.user, name="Savings", account_type="savings",
            plaid_account_id="pacct-savings")
        self.card = FinancialAccount.objects.create(
            user=self.user, name="Beacon Card", account_type="credit_card",
            plaid_account_id="pacct-card")
        entity_service.assign_account_entity(
            self.user, self.checking, self.personal,
            effective_from=TODAY - timedelta(days=400))
        entity_service.assign_account_entity(
            self.user, self.card, self.business,
            effective_from=TODAY - timedelta(days=400))
        self.sync = TransactionSyncService.__new__(TransactionSyncService)
        self.sync.user = self.user
        self.sync.bank_connection = None
        self.sync._category_map = None
        self.sync._liability_names = None

    def ingest(self, **overrides):
        self.assertTrue(
            self.sync._create_or_update_transaction(provider_txn(**overrides)))
        return Transaction.objects.get(
            plaid_transaction_id=overrides.get("transaction_id", "ptx-1"))


# ---------------------------------------------------------------------------
# 1 — provider provenance survives ingestion
# ---------------------------------------------------------------------------

class ProviderProvenanceTests(IngestionBase):

    def test_provider_classification_is_retained_verbatim(self):
        txn = self.ingest()
        self.assertEqual(txn.provider_category, ["Service", "Software"])
        self.assertEqual(txn.provider_category_primary, "GENERAL_SERVICES")
        self.assertEqual(txn.provider_category_detailed,
                         "GENERAL_SERVICES_OTHER_GENERAL_SERVICES")
        self.assertEqual(txn.provider_category_confidence, "VERY_HIGH")
        self.assertEqual(txn.provider_payment_channel, "online")
        self.assertEqual(txn.provider_merchant_name, "Design Tool")
        self.assertEqual(txn.provider_counterparties,
                         [{"name": "Design Tool", "type": "merchant"}])
        self.assertEqual(txn.provider_authorized_date, TODAY - timedelta(days=1))

    def test_provider_value_survives_even_when_wlj_chooses_differently(self):
        txn = self.ingest(pfc_primary="FOOD_AND_DRINK",
                          pfc_detailed="FOOD_AND_DRINK_GROCERIES")
        self.assertEqual(txn.category.name, "Groceries")     # WLJ's choice
        self.assertEqual(txn.provider_category_detailed,     # provider's, untouched
                         "FOOD_AND_DRINK_GROCERIES")

    def test_no_credentials_or_identifiers_are_stored(self):
        txn = self.ingest()
        for field in ("provider_category", "provider_counterparties"):
            blob = str(getattr(txn, field)).lower()
            for secret in ("access-", "routing", "account_number", "secret"):
                self.assertNotIn(secret, blob)


# ---------------------------------------------------------------------------
# 2 — the three dimensions are independent
# ---------------------------------------------------------------------------

class DimensionIndependenceTests(IngestionBase):

    def test_category_entity_and_transfer_state_are_separate(self):
        txn = self.ingest()
        attribution_service.confirm(self.user, txn, self.business)
        txn.refresh_from_db()

        self.assertEqual(txn.category.name, "Professional Services")   # what it is
        row = attribution_service.current_attribution(txn)
        self.assertEqual(row.attributed_entity.name, "Beacon")         # who bears it
        self.assertEqual(row.paid_by_entity.name, "Personal")          # who paid
        self.assertEqual(txn.transfer_state,                           # is it spending
                         Transaction.TRANSFER_STATE_NOT_TRANSFER)

    def test_changing_the_entity_does_not_touch_the_category(self):
        txn = self.ingest()
        attribution_service.confirm(self.user, txn, self.business)
        attribution_service.confirm(self.user, txn, self.personal)
        txn.refresh_from_db()
        self.assertEqual(txn.category.name, "Professional Services")
        self.assertEqual(txn.category_source, Transaction.CATEGORY_SOURCE_PROVIDER)

    def test_truth_surface_exposes_both_dimensions(self):
        txn = self.ingest()
        attribution_service.confirm(self.user, txn, self.business)
        row = [e.to_dict() for e in FinanceDomainTruth(self.user)
               .describe("transaction")][0]
        self.assertEqual(row["definition"]["category"], "Professional Services")
        self.assertEqual(row["definition"]["attributed_to"], "Beacon")
        self.assertEqual(row["definition"]["paid_by"], "Personal")


# ---------------------------------------------------------------------------
# 3 & 4 — the taxonomy is global and idempotent
# ---------------------------------------------------------------------------

class TaxonomyTests(TestCase):

    def test_seeded_categories_are_owned_by_nobody(self):
        seed_system_categories()
        rows = TransactionCategory.objects.filter(is_system=True)
        self.assertEqual(rows.count(), len(SYSTEM_CATEGORIES))
        self.assertEqual(rows.filter(user__isnull=False).count(), 0,
                         "a system category owned by a user leaks between accounts")

    def test_system_categories_cannot_leak_a_user_specific_classification(self):
        seed_system_categories()
        alice = User.objects.create_user(email="alice@example.com", password="x" * 14)
        bob = User.objects.create_user(email="bob@example.com", password="x" * 14)
        TransactionCategory.objects.create(
            user=alice, name="Alice Secret Project", category_type="expense",
            is_system=False)
        visible_to_bob = {c.name for c in TransactionCategory.get_for_user(bob)}
        self.assertNotIn("Alice Secret Project", visible_to_bob)
        self.assertIn("Software", visible_to_bob)

    def test_seeding_is_idempotent(self):
        created_first, _ = seed_system_categories()
        created_second, existing_second = seed_system_categories()
        self.assertEqual(created_first, len(SYSTEM_CATEGORIES))
        self.assertEqual(created_second, 0)
        self.assertEqual(existing_second, len(SYSTEM_CATEGORIES))
        self.assertEqual(
            TransactionCategory.objects.filter(is_system=True).count(),
            len(SYSTEM_CATEGORIES))

    def test_command_is_idempotent(self):
        from io import StringIO

        from django.core.management import call_command
        call_command("seed_finance_categories", stdout=StringIO())
        out = StringIO()
        call_command("seed_finance_categories", stdout=out)
        self.assertIn("created=0", out.getvalue())

    def test_mapping_is_deterministic_and_confidence_gated(self):
        self.assertEqual(
            map_provider_category("FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES",
                                  "VERY_HIGH"), "Groceries")
        self.assertIsNone(
            map_provider_category("FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES", "LOW"),
            "a low-confidence provider guess must not become a WLJ fact")
        self.assertIsNone(map_provider_category("SOMETHING_NEW", "", "VERY_HIGH"))


# ---------------------------------------------------------------------------
# 5 — user corrections outrank provider and inferred classifications
# ---------------------------------------------------------------------------

class UserAuthorityTests(IngestionBase):

    def test_user_category_is_not_overwritten_by_a_later_sync(self):
        txn = self.ingest()
        self.assertEqual(txn.category_source, Transaction.CATEGORY_SOURCE_PROVIDER)

        txn.category = system_category("Software")
        txn.category_source = Transaction.CATEGORY_SOURCE_USER
        txn.save(update_fields=["category", "category_source"])

        self.ingest(pfc_primary="ENTERTAINMENT", pfc_detailed="", pfc_confidence="VERY_HIGH")
        txn.refresh_from_db()
        self.assertEqual(txn.category.name, "Software")
        self.assertEqual(txn.category_source, Transaction.CATEGORY_SOURCE_USER)
        # The provider's newest opinion is still recorded.
        self.assertEqual(txn.provider_category_primary, "ENTERTAINMENT")

    def test_user_transfer_decision_outranks_the_provider(self):
        txn = self.ingest(pfc_primary="TRANSFER_OUT", pfc_confidence="VERY_HIGH")
        self.assertEqual(txn.transfer_state, Transaction.TRANSFER_STATE_CONFIRMED)

        transfer_detection.confirm_transfer(self.user, txn, is_transfer=False)
        self.ingest(pfc_primary="TRANSFER_OUT", pfc_confidence="VERY_HIGH")
        txn.refresh_from_db()
        self.assertEqual(txn.transfer_state, Transaction.TRANSFER_STATE_NOT_TRANSFER)
        self.assertEqual(txn.transfer_classified_by, Transaction.TRANSFER_BY_USER)

    def test_user_entity_confirmation_still_outranks_inference(self):
        txn = self.ingest()
        attribution_service.confirm(self.user, txn, self.business)
        with self.assertRaises(attribution_service.AttributionConflict):
            attribution_service.attribute(
                self.user, txn, self.personal,
                source=Transaction.CATEGORY_SOURCE_PROVIDER
                if False else "account_default",
                actor="system")


# ---------------------------------------------------------------------------
# 6 & 7 — transfers, card payments, refunds, pending→posted, totals
# ---------------------------------------------------------------------------

class TransferHandlingTests(IngestionBase):

    def _ids(self):
        return set(population.financial_activity(self.user)
                   .values_list("id", flat=True))

    def test_checking_to_savings_pair_is_confirmed_and_not_counted(self):
        out = self.ingest(transaction_id="t-out", amount=500.00,
                          merchant_name="Transfer to Savings",
                          pfc_primary="TRANSFER_OUT",
                          pfc_detailed="TRANSFER_OUT_ACCOUNT_TRANSFER")
        self.sync._create_or_update_transaction(provider_txn(
            transaction_id="t-in", account_id="pacct-savings", amount=-500.00,
            merchant_name="Transfer from Checking", pfc_primary="TRANSFER_IN",
            pfc_detailed="TRANSFER_IN_ACCOUNT_TRANSFER"))
        inn = Transaction.objects.get(plaid_transaction_id="t-in")

        transfer_detection.pair_transfers(self.user)
        out.refresh_from_db(); inn.refresh_from_db()
        self.assertEqual(out.transfer_pair_id, inn.id)
        self.assertEqual(out.transfer_state, Transaction.TRANSFER_STATE_CONFIRMED)
        ids = self._ids()
        self.assertNotIn(out.id, ids)
        self.assertNotIn(inn.id, ids, "both legs must leave the totals")

    def test_credit_card_payment_is_confirmed_not_spending(self):
        payment = self.ingest(
            transaction_id="t-card", amount=900.00, merchant_name="Beacon Card Payment",
            pfc_primary="LOAN_PAYMENTS",
            pfc_detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        self.assertEqual(payment.transfer_state, Transaction.TRANSFER_STATE_CONFIRMED)
        self.assertEqual(payment.transfer_kind, Transaction.TRANSFER_KIND_CARD_PAYMENT)
        self.assertNotIn(payment.id, self._ids())
        self.assertEqual(population.exclusion_reason(payment),
                         population.EXCLUDED_CARD_PAYMENT)

    def test_personal_to_business_transfer_is_a_transfer_not_an_expense(self):
        out = self.ingest(transaction_id="t-biz-out", amount=1000.00,
                          merchant_name="Transfer to Beacon Card",
                          pfc_primary="TRANSFER_OUT",
                          pfc_detailed="TRANSFER_OUT_ACCOUNT_TRANSFER")
        self.assertEqual(out.transfer_state, Transaction.TRANSFER_STATE_CONFIRMED)
        self.assertNotIn(out.id, self._ids())

    def test_ambiguous_unpaired_transfer_goes_to_review_not_totals(self):
        txn = self.ingest(transaction_id="t-amb", amount=250.00,
                          merchant_name="ONLINE PAYMENT",
                          pfc_primary="TRANSFER_OUT", pfc_confidence="LOW")
        self.assertEqual(txn.transfer_state, Transaction.TRANSFER_STATE_CANDIDATE)
        self.assertNotIn(txn.id, self._ids())
        self.assertIn(txn.id, set(population.review_candidates(self.user)
                                  .values_list("id", flat=True)))
        self.assertEqual(population.exclusion_reason(txn),
                         population.REVIEW_AMBIGUOUS_TRANSFER)

    def test_refund_stays_in_the_totals_and_offsets_spending(self):
        self.ingest(transaction_id="t-buy", amount=100.00)
        refund = self.ingest(transaction_id="t-ref", amount=-40.00,
                             merchant_name="Design Tool Refund",
                             pfc_detailed="GENERAL_SERVICES_REFUND")
        self.assertEqual(refund.transfer_kind, Transaction.TRANSFER_KIND_REFUND)
        self.assertEqual(refund.transfer_state,
                         Transaction.TRANSFER_STATE_NOT_TRANSFER)
        self.assertIn(refund.id, self._ids())

    def test_pending_becomes_posted_without_double_counting(self):
        pending = self.ingest(transaction_id="t-pending", amount=54.00, pending=True)
        self.assertTrue(pending.plaid_pending)
        attribution_service.confirm(self.user, pending, self.business)

        self.sync._create_or_update_transaction(provider_txn(
            transaction_id="t-posted", pending=False, amount=54.00,
            pending_transaction_id="t-pending"))

        rows = Transaction.objects.filter(user=self.user, description="Design Tool")
        self.assertEqual(rows.count(), 1, "the pending row was not replaced in place")
        posted = rows.first()
        self.assertEqual(posted.plaid_transaction_id, "t-posted")
        self.assertFalse(posted.plaid_pending)
        self.assertEqual(posted.id, pending.id)
        row = attribution_service.current_attribution(posted)
        self.assertIsNotNone(row, "the user's attribution was stranded on the ghost row")
        self.assertEqual(row.attributed_entity.name, "Beacon")

    def test_reversal_removes_the_row_from_totals(self):
        txn = self.ingest(transaction_id="t-rev", amount=75.00)
        self.assertIn(txn.id, self._ids())
        self.sync._remove_transaction("t-rev")
        self.assertNotIn(txn.id, self._ids())

    def test_totals_are_accurate_across_the_whole_mix(self):
        """One real expense, one refund — everything else is movement, not spending."""
        self.ingest(transaction_id="e1", amount=100.00)                       # -100
        self.ingest(transaction_id="r1", amount=-25.00,
                    pfc_detailed="GENERAL_SERVICES_REFUND")                   # +25
        self.ingest(transaction_id="c1", amount=900.00,
                    merchant_name="Beacon Card Payment",
                    pfc_detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")         # excluded
        self.ingest(transaction_id="a1", amount=250.00, merchant_name="ONLINE PAYMENT",
                    pfc_primary="TRANSFER_OUT", pfc_confidence="LOW")         # held out

        from django.db.models import Sum
        total = population.financial_activity(self.user).aggregate(
            t=Sum("amount"))["t"]
        self.assertEqual(total, Decimal("-75.00"))
        series = FinanceHistory.spending(self.user, period="this_year")
        self.assertEqual(abs(Decimal(str(series.total()))), Decimal("100.00"))

    def test_population_authority_is_still_the_only_path(self):
        """No second spending calculation may appear."""
        import ast
        from pathlib import Path

        finance_dir = Path(__file__).resolve().parents[1]
        repo_root = finance_dir.parents[1]
        allowed = {
            "apps/finance/services/attribution_population.py",
            "apps/finance/services/opportunity_detection.py",
            "apps/finance/management/commands/finance_population_audit.py",
            "apps/finance/services/finance_audit.py",
            "apps/finance/services/transfer_detection.py",
        }
        offenders = []
        for path in finance_dir.rglob("*.py"):
            parts = path.parts
            if any(skip in parts for skip in ("migrations", "tests", "__pycache__")):
                continue
            rel = path.relative_to(repo_root).as_posix()
            if rel in allowed:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in ("filter", "exclude"):
                    for kw in node.keywords:
                        name = (kw.arg or "").split("transaction__")[-1]
                        if name.startswith("transfer_state"):
                            offenders.append(f"{rel}:{node.lineno}")
                        # EXCLUDING opening balances defines spending; looking one UP
                        # for account-balance arithmetic is the opposite question.
                        elif name == "is_opening_balance" and isinstance(
                                kw.value, ast.Constant) and kw.value.value is False:
                            offenders.append(f"{rel}:{node.lineno}")
        self.assertEqual(offenders, [],
                         f"a second spending definition appeared: {offenders}")
