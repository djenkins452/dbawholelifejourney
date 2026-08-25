# ==============================================================================
# File: apps/finance/tests/test_f3_opportunity_lifecycle.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F3 — opportunity lifecycle, follow-through reuse, outcome verification.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""WLJ observes an outcome; it never causes one."""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.finance.models import (
    FinanceOpportunity,
    FinancialAccount,
    FinancialEntity,
    RecurringTransaction,
    Transaction,
    TransactionAttribution,
)
from apps.finance.services import attribution as attribution_service
from apps.finance.services import finance_entities as entity_service
from apps.finance.services import opportunity_detection as detection
from apps.finance.services import opportunity_lifecycle as lifecycle
from apps.users.models import TermsAcceptance, User

# Verification compares against the acceptance date, which is real "now" — so this
# suite anchors on the actual current date rather than a frozen literal.
TODAY = date.today()


class F3Base(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="f3@example.com",
                                             password="testpass123")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        prefs = self.user.preferences
        prefs.has_completed_onboarding = True
        prefs.finances_enabled = True
        prefs.save()

        self.personal, _ = entity_service.ensure_default_entities(self.user)
        self.business = entity_service.create_entity(
            self.user, entity_type=FinancialEntity.TYPE_BUSINESS, name="Northwind Studio",
        )
        self.checking = FinancialAccount.objects.create(
            user=self.user, name="Personal Checking", account_type="checking",
        )
        self.biz_card = FinancialAccount.objects.create(
            user=self.user, name="Studio Card", account_type="credit_card",
        )
        entity_service.assign_account_entity(
            self.user, self.checking, self.personal, effective_from=TODAY - timedelta(days=400))
        entity_service.assign_account_entity(
            self.user, self.biz_card, self.business, effective_from=TODAY - timedelta(days=400))
        self.recurring = RecurringTransaction.objects.create(
            user=self.user, name="Design Tool", transaction_type="expense",
            amount=Decimal("-54.00"), account=self.checking, frequency="monthly",
            start_date=TODAY - timedelta(days=365), next_due_date=TODAY,
        )

    def _charge(self, *, account=None, when=TODAY, fingerprint=""):
        txn = Transaction.objects.create(
            user=self.user, account=account or self.checking, date=when,
            amount=Decimal("-54.00"), description="Design Tool",
            payee="Design Tool Inc", recurring_source=self.recurring,
            fingerprint=fingerprint,
        )
        attribution_service.confirm(self.user, txn, self.business)
        return txn

    def _opportunity(self):
        findings = detection.build_findings(self.user)
        lifecycle.sync_from_findings(self.user, findings)
        return FinanceOpportunity.objects.get(user=self.user)


class LifecycleTests(F3Base):

    def test_detection_creates_an_opportunity(self):
        self._charge(fingerprint="fp-1")
        opportunity = self._opportunity()
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_DETECTED)
        self.assertEqual(opportunity.attributed_entity_id, self.business.id)
        self.assertEqual(opportunity.paid_by_entity_id, self.personal.id)
        self.assertGreater(opportunity.annual_estimate, 0)

    def test_sync_is_idempotent(self):
        self._charge(fingerprint="fp-1")
        self._opportunity()
        self._opportunity()
        self.assertEqual(FinanceOpportunity.objects.filter(user=self.user).count(), 1)

    def test_every_state_is_reachable(self):
        self._charge(fingerprint="fp-1")
        opportunity = self._opportunity()
        lifecycle.mark_presented(opportunity)
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_PRESENTED)
        lifecycle.defer(self.user, opportunity, until=TODAY + timedelta(days=30))
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_DEFERRED)
        lifecycle.accept(self.user, opportunity)
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_ACCEPTED)
        lifecycle.mark_in_progress(self.user, opportunity)
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_IN_PROGRESS)
        lifecycle.verify_manually(self.user, opportunity, note="switched the card")
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_VERIFIED_MANUAL)
        self.assertEqual(opportunity.verification_evidence["method"], "user_stated")

    def test_rejected_opportunity_is_not_reopened_by_detection(self):
        self._charge(fingerprint="fp-1")
        opportunity = self._opportunity()
        lifecycle.reject(self.user, opportunity, reason="intentional")
        self._charge(when=TODAY + timedelta(days=30), fingerprint="fp-2")
        self._opportunity()
        opportunity.refresh_from_db()
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_REJECTED)

    def test_resolved_pattern_becomes_not_relevant(self):
        txn = self._charge(fingerprint="fp-1")
        opportunity = self._opportunity()
        attribution_service.confirm(self.user, txn, self.personal)
        findings = detection.build_findings(self.user)
        live = lifecycle.sync_from_findings(self.user, findings)
        lifecycle.retire_resolved(self.user, live)
        opportunity.refresh_from_db()
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_NOT_RELEVANT)

    def test_accepted_opportunity_is_not_retired_by_the_sweep(self):
        txn = self._charge(fingerprint="fp-1")
        opportunity = self._opportunity()
        lifecycle.accept(self.user, opportunity)
        attribution_service.confirm(self.user, txn, self.personal)
        lifecycle.retire_resolved(self.user, set())
        opportunity.refresh_from_db()
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_ACCEPTED,
                         "a decision the user made belongs to them")


class FollowThroughReuseTests(F3Base):

    def test_acceptance_schedules_the_existing_follow_up_record(self):
        from apps.ai.models import ConversationFollowUp
        self._charge(fingerprint="fp-1")
        opportunity = self._opportunity()
        lifecycle.accept(self.user, opportunity)
        follow_up = opportunity.follow_up
        self.assertIsNotNone(follow_up)
        self.assertEqual(follow_up.status, ConversationFollowUp.STATUS_PENDING)
        self.assertEqual(follow_up.subject_ref,
                         f"finance.financeopportunity:{opportunity.pk}")
        self.assertGreater(follow_up.due_at, opportunity.accepted_at)

    def test_no_second_scheduler_exists(self):
        """F3 reuses ConversationFollowUp; it must not add a Finance scheduler."""
        import inspect
        source = inspect.getsource(lifecycle)
        self.assertIn("ConversationFollowUp", source)
        for token in ("crontab(", "PeriodicTask", "apply_async", "shared_task"):
            self.assertNotIn(token, source)


class VerificationTests(F3Base):

    def _accepted(self):
        self._charge(fingerprint="fp-old")
        opportunity = self._opportunity()
        return lifecycle.accept(self.user, opportunity)

    def test_new_charge_on_the_business_account_verifies(self):
        opportunity = self._accepted()
        Transaction.objects.create(
            user=self.user, account=self.biz_card, date=TODAY + timedelta(days=30),
            amount=Decimal("-54.00"), description="Design Tool",
            payee="Design Tool Inc", recurring_source=self.recurring,
            fingerprint="fp-new",
        )
        result = lifecycle.verify_from_truth(self.user, opportunity)
        self.assertIsNotNone(result)
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_VERIFIED_AUTO)
        self.assertEqual(opportunity.verification_evidence["method"],
                         "transaction_truth")
        self.assertEqual(opportunity.verification_evidence["account_id"],
                         self.biz_card.id)

    def test_a_baseline_transaction_can_never_be_evidence(self):
        """Reusing `fingerprint`: a row that existed at acceptance proves nothing."""
        opportunity = self._accepted()
        Transaction.objects.create(
            user=self.user, account=self.biz_card, date=TODAY + timedelta(days=1),
            amount=Decimal("-54.00"), description="Design Tool",
            payee="Design Tool Inc", recurring_source=self.recurring,
            fingerprint="fp-old",
        )
        self.assertIsNone(lifecycle.verify_from_truth(self.user, opportunity))
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_ACCEPTED)

    def test_still_on_the_personal_card_does_not_verify(self):
        opportunity = self._accepted()
        Transaction.objects.create(
            user=self.user, account=self.checking, date=TODAY + timedelta(days=30),
            amount=Decimal("-54.00"), description="Design Tool",
            payee="Design Tool Inc", recurring_source=self.recurring,
            fingerprint="fp-new",
        )
        self.assertIsNone(lifecycle.verify_from_truth(self.user, opportunity))
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_ACCEPTED)

    def test_unaccepted_opportunity_is_not_verified(self):
        self._charge(fingerprint="fp-old")
        opportunity = self._opportunity()
        self.assertIsNone(lifecycle.verify_from_truth(self.user, opportunity))

    def test_verification_is_one_pass_and_idempotent(self):
        opportunity = self._accepted()
        Transaction.objects.create(
            user=self.user, account=self.biz_card, date=TODAY + timedelta(days=30),
            amount=Decimal("-54.00"), description="Design Tool",
            payee="Design Tool Inc", recurring_source=self.recurring,
            fingerprint="fp-new",
        )
        lifecycle.verify_from_truth(self.user, opportunity)
        self.assertIsNone(lifecycle.verify_from_truth(self.user, opportunity))


class ReadOnlyBoundaryTests(F3Base):

    def test_lifecycle_cannot_touch_external_money(self):
        """No payment-method change, no cancellation, no external call — anywhere."""
        import inspect
        source = inspect.getsource(lifecycle).lower()
        for forbidden in ("requests.", "plaid", "http", "payment_method",
                          "cancel_subscription", "transfer_funds"):
            self.assertNotIn(forbidden, source)

    def test_no_finance_intent_became_write_enabled(self):
        from apps.ai.model_interface.constitution import ALLOWED_WRITE_INTENTS
        markers = ("transaction", "payment", "transfer", "bill", "expense", "reimburse")
        self.assertEqual(
            [n for n in ALLOWED_WRITE_INTENTS
             if any(m in n.lower() for m in markers)], [])


class OpportunityEndpointTests(F3Base):

    def setUp(self):
        super().setUp()
        self.client.login(email="f3@example.com", password="testpass123")
        self._charge(fingerprint="fp-1")
        self.opportunity = self._opportunity()

    def _decide(self, payload, pk=None):
        return self.client.post(
            reverse("finance:opportunity_decide", args=[pk or self.opportunity.pk]),
            data=json.dumps(payload), content_type="application/json",
        )

    def test_accept_endpoint_schedules_follow_up(self):
        response = self._decide({"decision": "accept"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["state"], FinanceOpportunity.STATE_ACCEPTED)
        self.assertTrue(body["follow_up_scheduled"])

    def test_reject_and_done_endpoints(self):
        self.assertEqual(self._decide({"decision": "reject", "reason": "on purpose"})
                         .json()["state"], FinanceOpportunity.STATE_REJECTED)
        self.assertEqual(self._decide({"decision": "done", "note": "moved it"})
                         .json()["state"], FinanceOpportunity.STATE_VERIFIED_MANUAL)

    def test_unknown_decision_is_rejected(self):
        self.assertEqual(self._decide({"decision": "pay_it"}).status_code, 400)

    def test_cannot_decide_on_another_users_opportunity(self):
        other = User.objects.create_user(email="f3-other@example.com", password="x" * 14)
        personal, _ = entity_service.ensure_default_entities(other)
        theirs = FinanceOpportunity.objects.create(
            user=other, dedupe_key="other-key", attributed_entity=personal,
            paid_by_entity=personal,
        )
        self.assertEqual(self._decide({"decision": "accept"}, pk=theirs.pk).status_code,
                         404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.state, FinanceOpportunity.STATE_DETECTED)


class TaskIntegrationTests(F3Base):

    def test_task_detects_syncs_and_verifies_in_one_pass(self):
        from apps.finance.tasks import detect_finance_opportunities
        self._charge(fingerprint="fp-1")
        first = detect_finance_opportunities(user_id=self.user.id)
        self.assertEqual(first["created"], 1)
        opportunity = FinanceOpportunity.objects.get(user=self.user)
        lifecycle.accept(self.user, opportunity)

        Transaction.objects.create(
            user=self.user, account=self.biz_card, date=TODAY + timedelta(days=30),
            amount=Decimal("-54.00"), description="Design Tool",
            payee="Design Tool Inc", recurring_source=self.recurring,
            fingerprint="fp-new",
        )
        second = detect_finance_opportunities(user_id=self.user.id)
        self.assertEqual(second["verified"], 1)
        opportunity.refresh_from_db()
        self.assertEqual(opportunity.state, FinanceOpportunity.STATE_VERIFIED_AUTO)
