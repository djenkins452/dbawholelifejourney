# ==============================================================================
# File: apps/finance/tests/test_finance_exposure.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Stage 2 — dashboard exposure, entity setup, and CoS surfacing.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Intelligence nobody can see is not intelligence.

These prove the F1–F3 truth actually reaches the dashboard and the Chief of Staff, that
empty states are honest, that stale data says so, and that nothing repeats itself.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.ai_insights.models import Insight
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
from apps.finance.services.finance_intelligence_summary import (
    SETUP_NO_ACCOUNTS,
    SETUP_NO_ATTRIBUTION,
    SETUP_NO_ENTITY,
    SETUP_READY,
    build_finance_intelligence,
    summary_lines,
)
from apps.users.models import TermsAcceptance, User

TODAY = date.today()


class ExposureBase(TestCase):
    def setUp(self):
        self.user = self._user("exposure@example.com")
        self.personal, _ = entity_service.ensure_default_entities(self.user)

    def _user(self, email):
        user = User.objects.create_user(email=email, password="testpass123")
        TermsAcceptance.objects.create(
            user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        prefs = user.preferences
        prefs.has_completed_onboarding = True
        prefs.finances_enabled = True
        prefs.save()
        return user

    def _full_setup(self):
        self.business = entity_service.create_entity(
            self.user, entity_type=FinancialEntity.TYPE_BUSINESS, name="Harbor Works")
        self.checking = FinancialAccount.objects.create(
            user=self.user, name="Personal Checking", account_type="checking")
        self.biz_card = FinancialAccount.objects.create(
            user=self.user, name="Works Card", account_type="credit_card")
        entity_service.assign_account_entity(
            self.user, self.checking, self.personal,
            effective_from=TODAY - timedelta(days=400))
        entity_service.assign_account_entity(
            self.user, self.biz_card, self.business,
            effective_from=TODAY - timedelta(days=400))
        self.recurring = RecurringTransaction.objects.create(
            user=self.user, name="Design Tool", transaction_type="expense",
            amount=Decimal("-54.00"), account=self.checking, frequency="monthly",
            start_date=TODAY - timedelta(days=365), next_due_date=TODAY)

    def _mismatch_charges(self, count=4):
        for i in range(count):
            txn = Transaction.objects.create(
                user=self.user, account=self.checking,
                date=TODAY - timedelta(days=30 * i), amount=Decimal("-54.00"),
                description="Design Tool", payee="Design Tool Inc",
                recurring_source=self.recurring, fingerprint=f"fp-{i}")
            attribution_service.confirm(self.user, txn, self.business)
        findings = detection.build_findings(self.user)
        detection.record_findings(self.user, findings)
        lifecycle.sync_from_findings(self.user, findings)
        return findings


class HonestEmptyStateTests(ExposureBase):

    def test_no_accounts_state(self):
        self.assertEqual(build_finance_intelligence(self.user)["setup_state"],
                         SETUP_NO_ACCOUNTS)

    def test_no_entity_state_names_the_real_blocker(self):
        FinancialAccount.objects.create(user=self.user, name="Checking",
                                        account_type="checking")
        data = build_finance_intelligence(self.user)
        self.assertEqual(data["setup_state"], SETUP_NO_ENTITY)
        self.assertFalse(data["has_business_entity"])
        joined = " ".join(summary_lines(self.user, data)).lower()
        self.assertIn("personal only", joined)

    def test_no_attribution_state(self):
        self._full_setup()
        self.assertEqual(build_finance_intelligence(self.user)["setup_state"],
                         SETUP_NO_ATTRIBUTION)

    def test_ready_state(self):
        self._full_setup()
        self._mismatch_charges()
        self.assertEqual(build_finance_intelligence(self.user)["setup_state"],
                         SETUP_READY)


class DashboardExposureTests(ExposureBase):

    def setUp(self):
        super().setUp()
        self._full_setup()
        self.client.login(email="exposure@example.com", password="testpass123")

    def test_attention_items_carry_facts_and_evidence(self):
        self._mismatch_charges()
        data = build_finance_intelligence(self.user)
        self.assertEqual(len(data["attention"]), 1)
        item = data["attention"][0]
        self.assertEqual(item["bearer"], "Harbor Works")
        self.assertEqual(item["payer"], "Personal")
        self.assertEqual(item["occurrences"], 4)
        self.assertGreater(item["annual_estimate"], 0)
        self.assertIn("transaction_ids", item["evidence"])
        self.assertTrue(item["why"])

    def test_dashboard_renders_the_section(self):
        self._mismatch_charges()
        response = self.client.get(reverse("finance:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attribution &amp; opportunities")
        self.assertContains(response, "Harbor Works")
        self.assertContains(response, "finance-attention-item")

    def test_dashboard_states_no_verdict(self):
        self._mismatch_charges()
        body = self.client.get(reverse("finance:dashboard")).content.decode().lower()
        for verdict in ("you should", "we recommend", "you're overspending",
                        "mistake", "wrong card"):
            self.assertNotIn(verdict, body)

    def test_resolved_and_rejected_items_are_suppressed(self):
        self._mismatch_charges()
        opportunity = FinanceOpportunity.objects.get(user=self.user)
        lifecycle.reject(self.user, opportunity, reason="deliberate")
        self.assertEqual(build_finance_intelligence(self.user)["attention"], [])

    def test_deferred_items_follow_the_resurfacing_date(self):
        self._mismatch_charges()
        opportunity = FinanceOpportunity.objects.get(user=self.user)
        lifecycle.defer(self.user, opportunity, until=TODAY + timedelta(days=30))
        self.assertEqual(build_finance_intelligence(self.user)["attention"], [])
        lifecycle.defer(self.user, opportunity, until=TODAY - timedelta(days=1))
        self.assertEqual(len(build_finance_intelligence(self.user)["attention"]), 1)

    def test_accepted_items_show_as_unresolved(self):
        self._mismatch_charges()
        opportunity = FinanceOpportunity.objects.get(user=self.user)
        lifecycle.accept(self.user, opportunity)
        data = build_finance_intelligence(self.user)
        self.assertEqual(len(data["unresolved"]), 1)
        self.assertEqual(data["attention"], [])

    def test_stale_data_is_labelled(self):
        Transaction.objects.create(
            user=self.user, account=self.checking, date=TODAY - timedelta(days=120),
            amount=Decimal("-20.00"), description="old")
        data = build_finance_intelligence(self.user)
        self.assertTrue(data["freshness"]["is_stale"])
        self.assertTrue(data["freshness"]["manual_only"])
        self.assertIn("out of date", " ".join(summary_lines(self.user, data)))

    def test_fresh_data_is_not_labelled_stale(self):
        Transaction.objects.create(
            user=self.user, account=self.checking, date=TODAY,
            amount=Decimal("-20.00"), description="today")
        self.assertFalse(build_finance_intelligence(self.user)["freshness"]["is_stale"])

    def test_users_see_only_their_own_intelligence(self):
        self._mismatch_charges()
        other = self._user("exposure-other@example.com")
        entity_service.ensure_default_entities(other)
        self.assertEqual(build_finance_intelligence(other)["attention"], [])
        self.client.logout()
        self.client.login(email="exposure-other@example.com", password="testpass123")
        body = self.client.get(reverse("finance:dashboard")).content.decode()
        self.assertNotIn("Harbor Works", body)

    def test_dashboard_query_count_does_not_grow_with_data(self):
        """Bounded means CONSTANT — the same cost at 4 charges and at 20."""
        self._mismatch_charges(count=4)
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as small:
            build_finance_intelligence(self.user)
        for i in range(16):
            txn = Transaction.objects.create(
                user=self.user, account=self.checking,
                date=TODAY - timedelta(days=400 + i), amount=Decimal("-12.00"),
                description=f"Vendor {i}", payee=f"Vendor {i}",
                fingerprint=f"fp-extra-{i}")
            attribution_service.confirm(self.user, txn, self.business)
        detection.record_findings(self.user)
        with CaptureQueriesContext(connection) as large:
            build_finance_intelligence(self.user)
        self.assertEqual(len(large), len(small),
                         "the intelligence summary grew with the data (N+1)")
        self.assertLessEqual(len(large), 20)

    def test_dashboard_makes_no_provider_call(self):
        import inspect

        from apps.finance.services import finance_intelligence_summary
        source = inspect.getsource(finance_intelligence_summary)
        for token in ("_call_api", "OpenAI", "AIService", "PlaidService", "requests."):
            self.assertNotIn(token, source)


class MaterialitySurfacingTests(ExposureBase):
    """PROVEN, not assumed: the executive briefing only collects warning/critical."""

    def setUp(self):
        super().setUp()
        self._full_setup()

    def test_material_confirmed_finding_routes_to_the_briefing(self):
        self._mismatch_charges()
        insight = Insight.objects.get(user=self.user,
                                      insight_type=detection.INSIGHT_TYPE)
        self.assertEqual(insight.severity, "warning")
        self.assertGreaterEqual(insight.evidence["annual_estimate"],
                                detection.MATERIAL_ANNUAL_ESTIMATE)

    def test_immaterial_finding_stays_quiet(self):
        txn = Transaction.objects.create(
            user=self.user, account=self.checking, date=TODAY,
            amount=Decimal("-3.00"), description="Tiny", payee="Tiny Vendor",
            fingerprint="fp-tiny")
        attribution_service.confirm(self.user, txn, self.business)
        detection.record_findings(self.user)
        insight = Insight.objects.get(user=self.user, evidence__occurrences=1)
        self.assertEqual(insight.severity, "info")

    def test_unconfirmed_finding_never_interrupts(self):
        txn = Transaction.objects.create(
            user=self.user, account=self.checking, date=TODAY,
            amount=Decimal("-900.00"), description="Big", payee="Big Vendor",
            fingerprint="fp-big")
        attribution_service.attribute(
            self.user, txn, self.business,
            source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
            actor=TransactionAttribution.ACTOR_SYSTEM)
        detection.record_findings(self.user)
        insight = Insight.objects.get(user=self.user, evidence__occurrences=1)
        self.assertEqual(insight.severity, "info",
                         "WLJ does not interrupt over an unconfirmed attribution")

    def test_the_briefing_collector_actually_picks_it_up(self):
        """The real runtime path, not a proxy for it."""
        from apps.core.cos_briefing.executive_summary import _collect_needs_attention
        self._mismatch_charges()
        titles = [row["title"] for row in _collect_needs_attention(self.user)]
        self.assertTrue(any("Harbor Works" in t for t in titles),
                        f"a material Finance finding never reached the briefing: {titles}")

    def test_cos_context_carries_the_finding(self):
        self._mismatch_charges()
        insight = Insight.objects.get(user=self.user,
                                      insight_type=detection.INSIGHT_TYPE)
        self.assertEqual(insight.module, "finance")
        self.assertIn(insight.status, ("new", "read"))
        self.assertGreater(insight.created_at,
                           timezone.now() - timedelta(hours=72),
                           "cos_context only reads insights from the last 72 hours")

    def test_unchanged_findings_do_not_repeat(self):
        self._mismatch_charges()
        insight = Insight.objects.get(user=self.user,
                                      insight_type=detection.INSIGHT_TYPE)
        original_created, original_status = insight.created_at, insight.status
        insight.status = "read"
        insight.save(update_fields=["status"])

        detection.record_findings(self.user)
        insight.refresh_from_db()
        self.assertEqual(insight.created_at, original_created,
                         "an unchanged finding must not resurface")
        self.assertEqual(insight.status, "read")
        self.assertEqual(original_status, "new")

    def test_a_materially_changed_finding_does_resurface(self):
        self._mismatch_charges()
        insight = Insight.objects.get(user=self.user,
                                      insight_type=detection.INSIGHT_TYPE)
        insight.status = "read"
        insight.save(update_fields=["status"])
        before = insight.created_at

        txn = Transaction.objects.create(
            user=self.user, account=self.checking, date=TODAY + timedelta(days=1),
            amount=Decimal("-54.00"), description="Design Tool",
            payee="Design Tool Inc", recurring_source=self.recurring,
            fingerprint="fp-new")
        attribution_service.confirm(self.user, txn, self.business)
        detection.record_findings(self.user)

        insight.refresh_from_db()
        self.assertEqual(insight.status, "new")
        self.assertGreater(insight.created_at, before)
        self.assertEqual(insight.evidence["occurrences"], 5)


class EntityWorkspaceTests(ExposureBase):

    def setUp(self):
        super().setUp()
        self.account = FinancialAccount.objects.create(
            user=self.user, name="Checking", account_type="checking")
        self.client.login(email="exposure@example.com", password="testpass123")

    def test_page_renders(self):
        response = self.client.get(reverse("finance:entity_workspace"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Who can your money belong to?")

    def test_create_entity(self):
        response = self.client.post(
            reverse("finance:entity_create"),
            data=json.dumps({"name": "  Harbor Works ", "entity_type": "business"}),
            content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Harbor Works")

    def test_duplicate_name_is_rejected_case_insensitively(self):
        entity_service.create_entity(self.user, entity_type="business", name="Harbor")
        response = self.client.post(
            reverse("finance:entity_create"),
            data=json.dumps({"name": "harbor", "entity_type": "business"}),
            content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_assign_account_entity(self):
        entity = entity_service.create_entity(self.user, entity_type="business",
                                              name="Harbor")
        response = self.client.post(
            reverse("finance:account_assign_entity", args=[self.account.pk]),
            data=json.dumps({"entity_id": entity.pk}),
            content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entity"], "Harbor")

    def test_cannot_assign_another_users_account(self):
        other = self._user("exposure-third@example.com")
        their_account = FinancialAccount.objects.create(
            user=other, name="Theirs", account_type="checking")
        entity = entity_service.create_entity(self.user, entity_type="business",
                                              name="Harbor")
        response = self.client.post(
            reverse("finance:account_assign_entity", args=[their_account.pk]),
            data=json.dumps({"entity_id": entity.pk}),
            content_type="application/json")
        self.assertEqual(response.status_code, 404)
