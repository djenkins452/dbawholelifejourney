# ==============================================================================
# File: apps/finance/tests/test_f2_attribution_review.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F2 — review queue, scoped decisions, learning, and authorization.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Review, confirm, correct, and learn — without ever overruling the user."""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.finance.models import (
    AttributionRule,
    FinancialAccount,
    FinancialEntity,
    Payee,
    RecurringTransaction,
    Transaction,
    TransactionAttribution,
)
from apps.finance.services import attribution as attribution_service
from apps.finance.services import attribution_review as review
from apps.finance.services import finance_entities as entity_service
from apps.users.models import TermsAcceptance, User

TODAY = date(2026, 6, 15)


class F2Base(TestCase):
    def setUp(self):
        self.user = self._make_user("f2@example.com")
        self.personal, _ = entity_service.ensure_default_entities(self.user)
        self.business = entity_service.create_entity(
            self.user, entity_type=FinancialEntity.TYPE_BUSINESS, name="Harbor Works",
        )
        self.checking = FinancialAccount.objects.create(
            user=self.user, name="Personal Checking", account_type="checking",
        )
        entity_service.assign_account_entity(
            self.user, self.checking, self.personal, effective_from=date(2025, 1, 1),
        )

    def _make_user(self, email):
        user = User.objects.create_user(email=email, password="testpass123")
        TermsAcceptance.objects.create(
            user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        prefs = user.preferences
        prefs.has_completed_onboarding = True
        prefs.finances_enabled = True
        prefs.save()
        return user

    def _txn(self, **kw):
        defaults = dict(user=self.user, account=self.checking, date=TODAY,
                        amount=Decimal("-54.00"), description="Design Tool",
                        payee="Design Tool Inc")
        defaults.update(kw)
        return Transaction.objects.create(**defaults)


class ReviewQueueTests(F2Base):

    def test_unattributed_transactions_surface(self):
        txn = self._txn()
        self.assertIn(txn.id, [t.id for t in review.unattributed(self.user)])

    def test_confirmed_transactions_leave_the_queue(self):
        txn = self._txn()
        attribution_service.confirm(self.user, txn, self.business)
        self.assertNotIn(txn.id, [t.id for t in review.unattributed(self.user)])

    def test_uncertain_rows_surface_with_a_reason(self):
        FinancialAccount.objects.create(
            user=self.user, name="Company Card", account_type="credit_card",
        )
        self._txn(description="Payment to Company Card", payee="")
        rows = review.uncertain(self.user)
        self.assertTrue(rows)
        self.assertTrue(all(reason for _, reason in rows))

    def test_counts_match_the_queue_contents(self):
        self._txn()
        self._txn(payee="Another Vendor", description="Another")
        counts = review.review_counts(self.user)
        self.assertEqual(counts["unattributed"], 2)
        self.assertEqual(counts["confirmed"], 0)

    def test_explain_is_always_available(self):
        txn = self._txn()
        self.assertIn("decided", review.explain(txn, None).lower())
        row = attribution_service.attribute(
            self.user, txn, self.business,
            source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
            actor=TransactionAttribution.ACTOR_SYSTEM,
        )
        self.assertIn(self.personal.name, review.explain(txn, row))
        confirmed = attribution_service.confirm(self.user, txn, self.business)
        self.assertEqual(review.explain(txn, confirmed), "You confirmed this.")


class ScopedDecisionTests(F2Base):

    def test_transaction_scope_touches_only_that_row(self):
        first, second = self._txn(), self._txn(description="second")
        result = review.apply_decision(self.user, first, self.business,
                                       scope="transaction")
        self.assertIsNone(result["rule"])
        self.assertEqual(result["also_settled"], 0)
        self.assertIsNone(attribution_service.current_attribution(second))

    def test_payee_scope_creates_a_rule_and_settles_siblings(self):
        Payee.objects.create(user=self.user, name="Design Tool Inc")
        target = self._txn()
        sibling = self._txn(date=TODAY - timedelta(days=30))
        unrelated = self._txn(payee="Someone Else", description="Other")

        result = review.apply_decision(self.user, target, self.business, scope="payee")
        self.assertIsNotNone(result["rule"])
        self.assertEqual(result["rule"].scope, AttributionRule.SCOPE_PAYEE)
        self.assertEqual(result["also_settled"], 1)

        sibling_row = attribution_service.current_attribution(sibling)
        self.assertEqual(sibling_row.attributed_entity_id, self.business.id)
        self.assertFalse(sibling_row.user_confirmed,
                         "a rule infers; only the user confirms")
        self.assertIsNone(attribution_service.current_attribution(unrelated))

    def test_recurring_scope_settles_the_series(self):
        recurring = RecurringTransaction.objects.create(
            user=self.user, name="Design Tool", transaction_type="expense",
            amount=Decimal("-54.00"), account=self.checking, frequency="monthly",
            start_date=date(2025, 1, 1), next_due_date=TODAY,
        )
        target = self._txn(recurring_source=recurring)
        sibling = self._txn(recurring_source=recurring, date=TODAY - timedelta(days=30))
        result = review.apply_decision(self.user, target, self.business,
                                       scope="recurring")
        self.assertEqual(result["rule"].scope, AttributionRule.SCOPE_RECURRING)
        self.assertEqual(result["also_settled"], 1)
        self.assertEqual(
            attribution_service.current_attribution(sibling).attributed_entity_id,
            self.business.id,
        )

    def test_an_exception_inside_a_batch_survives_the_batch(self):
        """Confirm the exception first, then apply the batch — the exception stands."""
        Payee.objects.create(user=self.user, name="Design Tool Inc")
        exception_txn = self._txn(date=TODAY - timedelta(days=10))
        target = self._txn()
        attribution_service.confirm(self.user, exception_txn, self.personal)

        review.apply_decision(self.user, target, self.business, scope="payee")

        row = attribution_service.current_attribution(exception_txn)
        self.assertEqual(row.attributed_entity_id, self.personal.id)
        self.assertTrue(row.user_confirmed)

    def test_scope_never_settles_uncertain_rows(self):
        FinancialAccount.objects.create(
            user=self.user, name="Company Card", account_type="credit_card",
        )
        Payee.objects.create(user=self.user, name="Design Tool Inc")
        uncertain = self._txn(description="Payment to Company Card")
        target = self._txn()
        review.apply_decision(self.user, target, self.business, scope="payee")
        self.assertIsNone(attribution_service.current_attribution(uncertain))

    def test_confirmed_decisions_reduce_future_review(self):
        Payee.objects.create(user=self.user, name="Design Tool Inc")
        target = self._txn()
        review.apply_decision(self.user, target, self.business, scope="payee")
        before = review.review_counts(self.user)["unattributed"]
        later = self._txn(date=TODAY + timedelta(days=30))

        from apps.finance.services import attribution_rules as rules_service
        index = rules_service.build_rule_index(self.user)
        payee = review.resolve_payee(self.user, later)
        rule = rules_service.match_rule(later, index, payee_id=payee.id)
        self.assertIsNotNone(rule, "the learned rule matches the next charge")
        rules_service.apply_rule(self.user, later, rule)
        self.assertEqual(review.review_counts(self.user)["unattributed"], before)


class ReviewEndpointTests(F2Base):

    def setUp(self):
        super().setUp()
        self.client.login(email="f2@example.com", password="testpass123")

    def test_page_renders(self):
        response = self.client.get(reverse("finance:attribution_review"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Who does this belong to?")

    def test_decide_endpoint_confirms(self):
        txn = self._txn()
        response = self.client.post(
            reverse("finance:attribution_decide"),
            data=json.dumps({"transaction_id": txn.id, "entity_id": self.business.id,
                             "scope": "transaction"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["entity"], "Harbor Works")
        row = attribution_service.current_attribution(txn)
        self.assertTrue(row.user_confirmed)

    def test_explain_endpoint(self):
        txn = self._txn()
        attribution_service.confirm(self.user, txn, self.business)
        response = self.client.get(
            reverse("finance:attribution_explain", args=[txn.id]))
        self.assertEqual(response.json()["attributed_to"], "Harbor Works")
        self.assertTrue(response.json()["confirmed"])

    def test_cannot_decide_on_another_users_transaction(self):
        other = self._make_user("f2-other@example.com")
        other_account = FinancialAccount.objects.create(
            user=other, name="Theirs", account_type="checking",
        )
        theirs = Transaction.objects.create(
            user=other, account=other_account, date=TODAY,
            amount=Decimal("-10.00"), description="theirs",
        )
        response = self.client.post(
            reverse("finance:attribution_decide"),
            data=json.dumps({"transaction_id": theirs.id,
                             "entity_id": self.business.id, "scope": "transaction"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertIsNone(attribution_service.current_attribution(theirs))

    def test_cannot_use_another_users_entity(self):
        other = self._make_user("f2-other2@example.com")
        their_entity = entity_service.create_entity(
            other, entity_type=FinancialEntity.TYPE_BUSINESS, name="Their Co",
        )
        txn = self._txn()
        response = self.client.post(
            reverse("finance:attribution_decide"),
            data=json.dumps({"transaction_id": txn.id, "entity_id": their_entity.id,
                             "scope": "transaction"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_anonymous_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("finance:attribution_review"))
        self.assertIn(response.status_code, (302, 301))


class CurrentContextTests(F2Base):

    def test_page_summary_is_registered_and_facts_only(self):
        from apps.core.current_context import (
            _PAGE_SUMMARY_PROVIDERS,
            registered_page_summaries,
        )
        self.assertIn("finance.attribution", registered_page_summaries())
        provider = _PAGE_SUMMARY_PROVIDERS["finance.attribution"]
        self._txn()
        summary = provider(self.user, {})
        self.assertIn("Awaiting a decision: 1", summary["content"])
        for verdict in ("you should", "on track", "behind", "problem"):
            self.assertNotIn(verdict, summary["content"].lower())

    def test_summary_and_page_share_one_source(self):
        """The provider must not re-derive counts independently of the page."""
        import inspect

        from apps.finance import page_summaries_attribution
        source = inspect.getsource(page_summaries_attribution)
        self.assertIn("review_counts", source)
        self.assertNotIn("Transaction.objects", source)
