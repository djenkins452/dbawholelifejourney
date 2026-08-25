# ==============================================================================
# File: apps/finance/tests/test_f0_entity_attribution.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F0 — entities, temporal account ownership, attribution, rules, population.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""F0 truth contracts.

Every assertion is deterministic; no provider call is made anywhere in this module.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction as db_transaction
from django.test import TestCase

from apps.finance.models import (
    AccountEntityAssignment,
    AttributionRule,
    FinancialAccount,
    FinancialEntity,
    RecurringTransaction,
    Transaction,
    TransactionAttribution,
    normalize_entity_name,
)
from apps.finance.services import attribution as attribution_service
from apps.finance.services import attribution_population as population
from apps.finance.services import attribution_rules as rules_service
from apps.finance.services import finance_entities as entity_service

User = get_user_model()
TODAY = date(2026, 6, 15)


class F0Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="f0-owner@example.com", password="x" * 14)
        cls.other = User.objects.create_user(email="f0-other@example.com", password="x" * 14)
        cls.personal, cls.unknown = entity_service.ensure_default_entities(cls.user)
        cls.business = entity_service.create_entity(
            cls.user, entity_type=FinancialEntity.TYPE_BUSINESS, name="Beacon",
        )
        cls.checking = FinancialAccount.objects.create(
            user=cls.user, name="Personal Checking", account_type="checking",
        )
        cls.biz_card = FinancialAccount.objects.create(
            user=cls.user, name="Beacon Card", account_type="credit_card",
        )

    def _txn(self, **kw):
        defaults = dict(user=self.user, account=self.checking, date=TODAY,
                        amount=Decimal("-40.00"), description="Design Tool")
        defaults.update(kw)
        return Transaction.objects.create(**defaults)


class EntityTests(F0Base):

    def test_entity_name_is_data_not_logic(self):
        """No business name may appear in an executable string literal.

        Prose (docstrings, comments) may explain the rule; CODE may never contain the
        name — no comparison, no dict key, no help_text, no choice value. Docstrings are
        excluded deliberately; comments never reach the AST at all.
        """
        import ast
        from pathlib import Path

        finance_dir = Path(__file__).resolve().parents[1]
        offenders = []
        for path in finance_dir.rglob("*.py"):
            parts = path.parts
            if "migrations" in parts or "tests" in parts or "__pycache__" in parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                     ast.AsyncFunctionDef)):
                    body = getattr(node, "body", None)
                    if body and isinstance(body[0], ast.Expr) and \
                            isinstance(body[0].value, ast.Constant) and \
                            isinstance(body[0].value.value, str):
                        docstrings.add(id(body[0].value))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and id(node) not in docstrings \
                        and "beacon" in node.value.casefold():
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [],
                         f"A business name leaked into Finance code: {offenders}")

    def test_case_and_whitespace_duplicates_are_rejected(self):
        for variant in ("beacon", "BEACON", "  Beacon  ", "Bea con".replace(" ", "")):
            with self.subTest(name=variant):
                with self.assertRaises(ValidationError):
                    entity_service.create_entity(
                        self.user, entity_type=FinancialEntity.TYPE_BUSINESS, name=variant,
                    )

    def test_normalization_is_case_and_space_insensitive(self):
        self.assertEqual(normalize_entity_name("  Beacon   LLC "), "beacon llc")

    def test_one_default_personal_per_user(self):
        with self.assertRaises(IntegrityError), db_transaction.atomic():
            FinancialEntity.objects.create(
                user=self.user, entity_type=FinancialEntity.TYPE_PERSONAL,
                name="Second Personal", is_default_personal=True,
            )

    def test_one_unknown_per_user(self):
        with self.assertRaises(IntegrityError), db_transaction.atomic():
            FinancialEntity.objects.create(
                user=self.user, entity_type=FinancialEntity.TYPE_UNKNOWN, name="Unsure",
            )

    def test_ensure_default_entities_is_idempotent(self):
        before = FinancialEntity.objects.filter(user=self.user).count()
        entity_service.ensure_default_entities(self.user)
        entity_service.ensure_default_entities(self.user)
        self.assertEqual(FinancialEntity.objects.filter(user=self.user).count(), before)

    def test_retired_entity_still_resolves_history(self):
        txn = self._txn()
        row = attribution_service.attribute(
            self.user, txn, self.business,
            source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
            actor=TransactionAttribution.ACTOR_SYSTEM,
        )
        entity_service.retire_entity(self.business)
        row.refresh_from_db()
        self.assertEqual(row.attributed_entity_id, self.business.id)

    def test_finance_active_detection(self):
        self.assertTrue(entity_service.is_finance_active(self.user))
        self.assertFalse(entity_service.is_finance_active(self.other))


class AccountEntityTemporalTests(F0Base):

    def test_first_assignment_reaches_back_over_history(self):
        """Imported history must resolve — a first assignment is not 'from today'."""
        self._txn(date=date(2025, 1, 5))
        account = FinancialAccount.objects.create(
            user=self.user, name="Imported Card", account_type="credit_card",
        )
        Transaction.objects.create(user=self.user, account=account, date=date(2025, 3, 2),
                                   amount=Decimal("-10.00"), description="old")
        assignment = entity_service.assign_account_entity(
            self.user, account, self.business,
        )
        self.assertEqual(assignment.effective_from, date(2025, 3, 2))
        self.assertEqual(
            entity_service.resolve_paid_by(self.user, account, date(2025, 4, 1)).id,
            self.business.id,
        )

    def test_later_change_is_forward_dated_and_closes_the_prior_window(self):
        """A real ownership change closes the previous window; it never deletes history."""
        self._txn(date=date(2025, 2, 1))
        entity_service.assign_account_entity(self.user, self.checking, self.personal)
        second = entity_service.assign_account_entity(
            self.user, self.checking, self.business,
        )
        from apps.core.utils import get_user_today
        today = get_user_today(self.user)
        self.assertEqual(second.effective_from, today)
        closed = AccountEntityAssignment.objects.filter(
            account=self.checking, effective_to__isnull=False,
        ).first()
        self.assertIsNotNone(closed, "the prior assignment must be closed, not deleted")
        self.assertEqual(closed.effective_to, today - timedelta(days=1))
        self.assertEqual(
            entity_service.resolve_paid_by(self.user, self.checking,
                                           date(2025, 6, 1)).id,
            self.personal.id,
            "history still resolves to the previous owner",
        )

    def test_same_day_reassignment_leaves_no_zero_length_window(self):
        """Assigning twice in one day means the first owner never actually owned it."""
        account = FinancialAccount.objects.create(
            user=self.user, name="Fresh Account", account_type="checking",
        )
        entity_service.assign_account_entity(self.user, account, self.personal)
        entity_service.assign_account_entity(self.user, account, self.business)
        open_rows = AccountEntityAssignment.objects.filter(
            account=account, effective_to__isnull=True,
        )
        self.assertEqual(open_rows.count(), 1)
        self.assertEqual(open_rows.first().entity_id, self.business.id)
        self.assertEqual(
            AccountEntityAssignment.all_objects.filter(account=account).count(), 2,
            "the superseded window is retained for audit, not hard-deleted",
        )

    def test_retroactive_change_requires_explicit_date(self):
        entity_service.assign_account_entity(
            self.user, self.checking, self.personal, effective_from=date(2025, 1, 1),
        )
        entity_service.assign_account_entity(
            self.user, self.checking, self.business, effective_from=date(2026, 1, 1),
        )
        self.assertEqual(
            entity_service.resolve_paid_by(self.user, self.checking, date(2025, 6, 1)).id,
            self.personal.id,
        )
        self.assertEqual(
            entity_service.resolve_paid_by(self.user, self.checking, date(2026, 3, 1)).id,
            self.business.id,
        )

    def test_paid_by_is_snapshotted_and_survives_reassignment(self):
        entity_service.assign_account_entity(
            self.user, self.checking, self.personal, effective_from=date(2025, 1, 1),
        )
        txn = self._txn()
        row = attribution_service.attribute(
            self.user, txn, self.business,
            source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
            actor=TransactionAttribution.ACTOR_SYSTEM,
        )
        self.assertEqual(row.paid_by_entity_id, self.personal.id)
        entity_service.assign_account_entity(
            self.user, self.checking, self.business, effective_from=date(2025, 1, 1),
        )
        row.refresh_from_db()
        self.assertEqual(row.paid_by_entity_id, self.personal.id,
                         "the snapshot is historical evidence and must not be rewritten")

    def test_one_open_assignment_per_account(self):
        entity_service.assign_account_entity(self.user, self.checking, self.personal)
        with self.assertRaises(IntegrityError), db_transaction.atomic():
            AccountEntityAssignment.objects.create(
                user=self.user, account=self.checking, entity=self.business,
                effective_from=TODAY, effective_to=None,
            )

    def test_retroactive_change_preserves_user_confirmation_as_conflict(self):
        entity_service.assign_account_entity(
            self.user, self.checking, self.personal, effective_from=date(2025, 1, 1),
        )
        confirmed_txn = self._txn()
        inferred_txn = self._txn(description="Other charge")
        confirmed = attribution_service.confirm(self.user, confirmed_txn, self.business)
        inferred = attribution_service.attribute(
            self.user, inferred_txn, self.business,
            source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
            actor=TransactionAttribution.ACTOR_SYSTEM,
        )
        entity_service.assign_account_entity(
            self.user, self.checking, self.business, effective_from=date(2025, 1, 1),
        )
        refreshed, conflicts = attribution_service.record_account_change_conflicts(
            self.user, self.checking, effective_from=date(2025, 1, 1),
        )
        confirmed.refresh_from_db()
        inferred.refresh_from_db()
        self.assertEqual([c.id for c in conflicts], [confirmed.id])
        self.assertEqual(confirmed.attribution_status, TransactionAttribution.STATUS_ACTIVE)
        self.assertEqual(inferred.attribution_status,
                         TransactionAttribution.STATUS_SUPERSEDED)
        self.assertEqual(len(refreshed), 1)


class AttributionLifecycleTests(F0Base):

    def setUp(self):
        entity_service.assign_account_entity(
            self.user, self.checking, self.personal, effective_from=date(2025, 1, 1),
        )

    def test_correction_supersedes_and_preserves_the_original(self):
        txn = self._txn()
        first = attribution_service.attribute(
            self.user, txn, self.business,
            source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
            actor=TransactionAttribution.ACTOR_SYSTEM, confidence=0.5,
            evidence={"account_id": self.checking.id},
        )
        snapshot = TransactionAttribution.objects.get(pk=first.pk)
        second = attribution_service.confirm(self.user, txn, self.personal)
        first.refresh_from_db()

        self.assertEqual(first.attribution_status, TransactionAttribution.STATUS_SUPERSEDED)
        self.assertEqual(first.superseded_by_id, second.id)
        for field in ("attributed_entity_id", "paid_by_entity_id", "source", "actor",
                      "confidence", "evidence", "created_at"):
            self.assertEqual(getattr(first, field), getattr(snapshot, field),
                             f"{field} was mutated by a correction")
        self.assertEqual(
            [r.id for r in attribution_service.supersession_chain(first)],
            [first.id, second.id],
        )

    def test_only_one_active_full_attribution_per_transaction(self):
        txn = self._txn()
        attribution_service.confirm(self.user, txn, self.business)
        with self.assertRaises(IntegrityError), db_transaction.atomic():
            TransactionAttribution.objects.create(
                user=self.user, transaction=txn, attributed_entity=self.personal,
                paid_by_entity=self.personal,
                source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
                actor=TransactionAttribution.ACTOR_SYSTEM,
            )

    def test_inferred_cannot_override_user_confirmation(self):
        txn = self._txn()
        attribution_service.confirm(self.user, txn, self.business)
        with self.assertRaises(attribution_service.AttributionConflict):
            attribution_service.attribute(
                self.user, txn, self.personal,
                source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
                actor=TransactionAttribution.ACTOR_SYSTEM,
            )

    def test_user_confirmation_supersedes_user_confirmation(self):
        txn = self._txn()
        first = attribution_service.confirm(self.user, txn, self.business)
        second = attribution_service.confirm(self.user, txn, self.personal)
        first.refresh_from_db()
        self.assertEqual(first.superseded_by_id, second.id)
        self.assertTrue(second.user_confirmed)

    def test_attribute_cannot_forge_user_direct_source(self):
        txn = self._txn()
        with self.assertRaises(ValidationError):
            attribution_service.attribute(
                self.user, txn, self.business,
                source=TransactionAttribution.SOURCE_USER_DIRECT,
                actor=TransactionAttribution.ACTOR_USER,
            )

    def test_rule_path_cannot_set_user_confirmed(self):
        txn = self._txn(payee="Design Tool Inc")
        rule = rules_service.create_rule(
            self.user, scope=AttributionRule.SCOPE_ACCOUNT, entity=self.business,
            account=self.checking, origin=AttributionRule.ORIGIN_USER_AUTHORED,
        )
        row = rules_service.apply_rule(self.user, txn, rule)
        self.assertFalse(row.user_confirmed)
        self.assertEqual(row.source, TransactionAttribution.SOURCE_USER_RULE)
        self.assertIn(row.source, TransactionAttribution.INFERRED_SOURCES)

    def test_evidence_is_minimized(self):
        txn = self._txn()
        row = attribution_service.attribute(
            self.user, txn, self.business,
            source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
            actor=TransactionAttribution.ACTOR_SYSTEM,
            evidence={"account_id": 1, "access_token": "secret",
                      "plaid_transaction_id": "tx_123", "notes": "free text"},
        )
        self.assertEqual(set(row.evidence), {"account_id"})

    def test_uncertain_transactions_are_never_attributed(self):
        pending = self._txn(plaid_pending=True)
        with self.assertRaises(ValidationError):
            attribution_service.attribute(
                self.user, pending, self.business,
                source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
                actor=TransactionAttribution.ACTOR_SYSTEM,
            )


class PopulationContractTests(F0Base):

    def setUp(self):
        from apps.finance.models import TransactionCategory
        self.transfer_cat = TransactionCategory.objects.create(
            name="Transfer", category_type="transfer", is_system=True,
        )

    def _ids(self):
        return set(population.attributable_transactions(self.user)
                   .values_list("id", flat=True))

    def test_ordinary_expense_is_attributable(self):
        txn = self._txn()
        self.assertIn(txn.id, self._ids())
        self.assertIsNone(population.exclusion_reason(txn))

    def test_soft_deleted_excluded(self):
        txn = self._txn()
        txn.soft_delete()
        self.assertNotIn(txn.id, self._ids())

    def test_opening_balance_excluded(self):
        txn = self._txn(is_opening_balance=True)
        self.assertNotIn(txn.id, self._ids())
        self.assertEqual(population.exclusion_reason(txn),
                         population.EXCLUDED_OPENING_BALANCE)

    def test_paired_transfer_both_legs_excluded(self):
        out_leg = self._txn(description="Transfer to Beacon Card")
        in_leg = self._txn(account=self.biz_card, amount=Decimal("40.00"),
                           description="Transfer from Personal Checking")
        out_leg.transfer_pair = in_leg
        out_leg.save(update_fields=["transfer_pair"])
        in_leg.transfer_pair = out_leg
        in_leg.save(update_fields=["transfer_pair"])
        ids = self._ids()
        self.assertNotIn(out_leg.id, ids)
        self.assertNotIn(in_leg.id, ids)

    def test_transfer_category_excluded(self):
        txn = self._txn(category=self.transfer_cat)
        self.assertNotIn(txn.id, self._ids())
        self.assertEqual(population.exclusion_reason(txn),
                         population.EXCLUDED_TRANSFER_CATEGORY)

    def test_pending_is_review_not_attributable(self):
        txn = self._txn(plaid_pending=True)
        self.assertNotIn(txn.id, self._ids())
        self.assertEqual(population.exclusion_reason(txn), population.REVIEW_PENDING)
        self.assertIn(population.REVIEW_PENDING, population.NEEDS_REVIEW_REASONS)
        self.assertIn(txn.id, set(population.review_candidates(self.user)
                                  .values_list("id", flat=True)))

    def test_unpaired_card_payment_is_review_not_an_expense(self):
        """THE F1 false-positive class: an imported payment toward the user's own card."""
        txn = self._txn(description="Payment to Beacon Card", amount=Decimal("-500.00"))
        self.assertNotIn(txn.id, self._ids())
        self.assertEqual(population.exclusion_reason(txn),
                         population.REVIEW_SUSPECTED_INTERNAL_TRANSFER)
        self.assertIn(txn.id, set(population.review_candidates(self.user)
                                  .values_list("id", flat=True)))

    def test_income_and_refunds_are_attributable(self):
        income = self._txn(amount=Decimal("1200.00"), description="Client deposit")
        refund = self._txn(amount=Decimal("25.00"), description="Refund - Design Tool")
        ids = self._ids()
        self.assertIn(income.id, ids)
        self.assertIn(refund.id, ids)

    def test_other_users_transactions_never_appear(self):
        other_account = FinancialAccount.objects.create(
            user=self.other, name="Their Checking", account_type="checking",
        )
        theirs = Transaction.objects.create(
            user=self.other, account=other_account, date=TODAY,
            amount=Decimal("-10.00"), description="theirs",
        )
        self.assertNotIn(theirs.id, self._ids())


class RulePrecedenceTests(F0Base):

    def setUp(self):
        from apps.finance.models import Payee
        entity_service.assign_account_entity(
            self.user, self.checking, self.personal, effective_from=date(2025, 1, 1),
        )
        self.payee = Payee.objects.create(user=self.user, name="Design Tool Inc")
        self.recurring = RecurringTransaction.objects.create(
            user=self.user, name="Design Tool", transaction_type="expense",
            amount=Decimal("-40.00"), account=self.checking, frequency="monthly",
            start_date=date(2025, 1, 1), next_due_date=TODAY,
        )

    def test_recurring_outranks_payee_outranks_account(self):
        household = entity_service.create_entity(
            self.user, entity_type=FinancialEntity.TYPE_HOUSEHOLD, name="Household",
        )
        rules_service.create_rule(self.user, scope=AttributionRule.SCOPE_ACCOUNT,
                                  entity=self.personal, account=self.checking,
                                  origin=AttributionRule.ORIGIN_USER_AUTHORED)
        rules_service.create_rule(self.user, scope=AttributionRule.SCOPE_PAYEE,
                                  entity=household, payee=self.payee)
        rules_service.create_rule(self.user, scope=AttributionRule.SCOPE_RECURRING,
                                  entity=self.business, recurring=self.recurring)
        index = rules_service.build_rule_index(self.user)
        txn = self._txn(recurring_source=self.recurring)
        winner = rules_service.match_rule(txn, index, payee_id=self.payee.id)
        self.assertEqual(winner.entity_id, self.business.id)

        plain = self._txn()
        self.assertEqual(
            rules_service.match_rule(plain, index, payee_id=self.payee.id).entity_id,
            household.id,
        )
        self.assertEqual(
            rules_service.match_rule(plain, index).entity_id, self.personal.id,
        )

    def test_category_is_not_a_scope(self):
        with self.assertRaises(ValidationError):
            rules_service.create_rule(self.user, scope="category", entity=self.business)
        field_names = {f.name for f in AttributionRule._meta.get_fields()}
        self.assertNotIn("category", field_names)
        attribution_fields = {f.name for f in TransactionAttribution._meta.get_fields()}
        self.assertNotIn("category", attribution_fields)

    def test_new_rule_supersedes_the_previous_one_on_the_same_anchor(self):
        first = rules_service.create_rule(self.user, scope=AttributionRule.SCOPE_PAYEE,
                                          entity=self.business, payee=self.payee)
        second = rules_service.create_rule(self.user, scope=AttributionRule.SCOPE_PAYEE,
                                           entity=self.personal, payee=self.payee)
        first.refresh_from_db()
        self.assertEqual(first.rule_status, AttributionRule.STATUS_SUPERSEDED)
        self.assertEqual(first.superseded_by_id, second.id)

    def test_no_rules_are_created_automatically(self):
        self._txn()
        attribution_service.attribute(
            self.user, self._txn(description="another"), self.business,
            source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
            actor=TransactionAttribution.ACTOR_SYSTEM,
        )
        self.assertEqual(AttributionRule.objects.filter(user=self.user).count(), 0)


class CrossUserAuthorizationTests(F0Base):

    def setUp(self):
        self.their_entity = entity_service.create_entity(
            self.other, entity_type=FinancialEntity.TYPE_BUSINESS, name="Their Co",
        )
        self.their_account = FinancialAccount.objects.create(
            user=self.other, name="Their Checking", account_type="checking",
        )
        self.their_txn = Transaction.objects.create(
            user=self.other, account=self.their_account, date=TODAY,
            amount=Decimal("-10.00"), description="theirs",
        )

    def test_cannot_attribute_own_transaction_to_another_users_entity(self):
        txn = self._txn()
        with self.assertRaises(ValidationError):
            attribution_service.attribute(
                self.user, txn, self.their_entity,
                source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
                actor=TransactionAttribution.ACTOR_SYSTEM,
            )

    def test_cannot_confirm_another_users_transaction(self):
        with self.assertRaises(ValidationError):
            attribution_service.confirm(self.user, self.their_txn, self.business)

    def test_cannot_assign_another_users_account(self):
        with self.assertRaises(ValidationError):
            entity_service.assign_account_entity(
                self.user, self.their_account, self.business,
            )

    def test_cannot_assign_own_account_to_another_users_entity(self):
        with self.assertRaises(ValidationError):
            entity_service.assign_account_entity(
                self.user, self.checking, self.their_entity,
            )

    def test_cannot_build_a_rule_across_users(self):
        with self.assertRaises(ValidationError):
            rules_service.create_rule(
                self.user, scope=AttributionRule.SCOPE_ACCOUNT,
                entity=self.business, account=self.their_account,
                origin=AttributionRule.ORIGIN_USER_AUTHORED,
            )


class QueryShapeTests(F0Base):
    """F1's access patterns must not be N+1 — proven without a denormalized cache."""

    def setUp(self):
        entity_service.assign_account_entity(
            self.user, self.checking, self.personal, effective_from=date(2025, 1, 1),
        )
        for i in range(12):
            txn = self._txn(description=f"charge {i}", date=TODAY - timedelta(days=i))
            attribution_service.attribute(
                self.user, txn, self.business,
                source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
                actor=TransactionAttribution.ACTOR_SYSTEM,
            )

    def test_entity_totals_is_one_grouped_query(self):
        from django.db.models import Sum
        with self.assertNumQueries(1):
            list(TransactionAttribution.objects
                 .filter(user=self.user,
                         attribution_status=TransactionAttribution.STATUS_ACTIVE)
                 .values("attributed_entity")
                 .annotate(total=Sum("transaction__amount")))

    def test_mismatch_scan_is_one_query_without_joins(self):
        from django.db.models import F
        with self.assertNumQueries(1):
            rows = list(TransactionAttribution.objects
                        .filter(user=self.user,
                                attribution_status=TransactionAttribution.STATUS_ACTIVE)
                        .exclude(attributed_entity=F("paid_by_entity"))
                        .values_list("id", flat=True))
        self.assertEqual(len(rows), 12)

    def test_unattributed_listing_is_one_query_when_batched(self):
        """The batch shape: hoist the liability lookup once, then scan in ONE query.

        No denormalized `Transaction.current_attribution` is needed — `Exists()` over the
        indexed attribution table is the authoritative path (F0 decision).
        """
        from django.db.models import Exists, OuterRef
        active = TransactionAttribution.objects.filter(
            transaction=OuterRef("pk"),
            attribution_status=TransactionAttribution.STATUS_ACTIVE,
        )
        names = population.liability_account_names(self.user)
        with self.assertNumQueries(1):
            list(population.attributable_transactions(self.user, liability_names=names)
                 .annotate(has_attr=Exists(active))
                 .filter(has_attr=False)
                 .values_list("id", flat=True))

    def test_population_query_count_is_flat_in_transaction_count(self):
        """Convenience path = 1 bounded lookup + 1 scan, regardless of how many rows."""
        with self.assertNumQueries(2):
            list(population.attributable_transactions(self.user)
                 .values_list("id", flat=True))
        for i in range(30):
            self._txn(description=f"extra {i}")
        with self.assertNumQueries(2):
            list(population.attributable_transactions(self.user)
                 .values_list("id", flat=True))

    def test_rule_index_is_one_query_for_any_batch_size(self):
        with self.assertNumQueries(1):
            rules_service.build_rule_index(self.user)

    def test_open_assignment_map_is_one_query(self):
        with self.assertNumQueries(1):
            entity_service.open_assignment_map(self.user)


class TruthExposureTests(F0Base):
    """F1 reads Finance truth through the canonical surface — facts only."""

    def setUp(self):
        from apps.finance.services.finance_domain_truth import FinanceDomainTruth
        entity_service.assign_account_entity(
            self.user, self.checking, self.personal, effective_from=date(2025, 1, 1),
        )
        self.truth = FinanceDomainTruth(self.user)

    def test_entities_are_exposed(self):
        rows = [e.to_dict() for e in self.truth.describe("entity")]
        names = {r["identity"] for r in rows}
        self.assertIn("Beacon", names)
        self.assertIn("Personal", names)
        for row in rows:
            self.assertIn("entity_type", row["definition"])

    def test_transaction_entities_carry_attribution_facts(self):
        txn = self._txn()
        attribution_service.confirm(self.user, txn, self.business)
        row = [e.to_dict() for e in self.truth.describe("transaction")][0]
        self.assertEqual(row["definition"]["attributed_to"], "Beacon")
        self.assertEqual(row["definition"]["paid_by"], "Personal")
        self.assertTrue(row["definition"]["attribution_confirmed"])

    def test_attribution_exposure_has_no_n_plus_one(self):
        for i in range(10):
            txn = self._txn(description=f"c{i}")
            attribution_service.attribute(
                self.user, txn, self.business,
                source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
                actor=TransactionAttribution.ACTOR_SYSTEM,
            )
        with self.assertNumQueries(2):   # transactions + one prefetch
            list(self.truth.describe("transaction"))

    def test_no_verdicts_in_attribution_facts(self):
        txn = self._txn()
        attribution_service.confirm(self.user, txn, self.business)
        row = [e.to_dict() for e in self.truth.describe("transaction")][0]
        blob = str(row).lower()
        for verdict in ("should move", "wrong card", "mistake", "on track", "overspend"):
            self.assertNotIn(verdict, blob)
