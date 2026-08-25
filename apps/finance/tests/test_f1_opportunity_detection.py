# ==============================================================================
# File: apps/finance/tests/test_f1_opportunity_detection.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F1 — deterministic mismatch detection over canonical Insight records.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Detection is deterministic, idempotent, evidence-bearing, and never a model call."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.ai_insights.models import Insight
from apps.finance.models import (
    FinancialAccount,
    FinancialEntity,
    RecurringTransaction,
    Transaction,
    TransactionAttribution,
    TransactionCategory,
)
from apps.finance.services import attribution as attribution_service
from apps.finance.services import finance_entities as entity_service
from apps.finance.services import opportunity_detection as detection

User = get_user_model()
TODAY = date(2026, 6, 15)


class F1Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="f1@example.com", password="x" * 14)
        cls.personal, cls.unknown = entity_service.ensure_default_entities(cls.user)
        cls.business = entity_service.create_entity(
            cls.user, entity_type=FinancialEntity.TYPE_BUSINESS, name="Lighthouse Co",
        )
        cls.checking = FinancialAccount.objects.create(
            user=cls.user, name="Personal Checking", account_type="checking",
        )
        cls.biz_card = FinancialAccount.objects.create(
            user=cls.user, name="Company Card", account_type="credit_card",
        )
        entity_service.assign_account_entity(
            cls.user, cls.checking, cls.personal, effective_from=date(2025, 1, 1),
        )
        entity_service.assign_account_entity(
            cls.user, cls.biz_card, cls.business, effective_from=date(2025, 1, 1),
        )

    def _txn(self, **kw):
        defaults = dict(user=self.user, account=self.checking, date=TODAY,
                        amount=Decimal("-54.00"), description="Design Tool",
                        payee="Design Tool Inc")
        defaults.update(kw)
        return Transaction.objects.create(**defaults)

    def _mismatch(self, *, confirmed=False, **kw):
        txn = self._txn(**kw)
        if confirmed:
            return attribution_service.confirm(self.user, txn, self.business)
        return attribution_service.attribute(
            self.user, txn, self.business,
            source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
            actor=TransactionAttribution.ACTOR_SYSTEM,
        )


class DetectionCorrectnessTests(F1Base):

    def test_business_expense_paid_personally_is_detected(self):
        self._mismatch(confirmed=True)
        findings = detection.build_findings(self.user)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["bearer"].id, self.business.id)
        self.assertEqual(findings[0]["payer"].id, self.personal.id)
        self.assertTrue(findings[0]["confirmed"])

    def test_matched_attribution_is_not_a_finding(self):
        """A business expense paid from the business card is correct — say nothing."""
        txn = self._txn(account=self.biz_card)
        attribution_service.confirm(self.user, txn, self.business)
        self.assertEqual(detection.build_findings(self.user), [])

    def test_personal_expense_on_personal_card_is_not_a_finding(self):
        txn = self._txn(description="Groceries", payee="Market")
        attribution_service.confirm(self.user, txn, self.personal)
        self.assertEqual(detection.build_findings(self.user), [])

    def test_confirmed_and_inferred_findings_are_distinguished(self):
        self._mismatch(confirmed=True, payee="Confirmed Vendor")
        self._mismatch(confirmed=False, payee="Inferred Vendor")
        by_label = {f["label"]: f for f in detection.build_findings(self.user)}
        self.assertTrue(by_label["Confirmed Vendor"]["confirmed"])
        self.assertEqual(by_label["Confirmed Vendor"]["confidence"],
                         detection.CONFIDENCE_CONFIRMED)
        self.assertFalse(by_label["Inferred Vendor"]["confirmed"])
        self.assertEqual(by_label["Inferred Vendor"]["confidence"],
                         detection.CONFIDENCE_INFERRED)

    def test_superseded_attribution_is_ignored(self):
        row = self._mismatch()
        attribution_service.confirm(self.user, row.transaction, self.personal)
        self.assertEqual(detection.build_findings(self.user), [])

    def test_findings_group_by_pattern_not_per_transaction(self):
        for i in range(4):
            self._mismatch(date=TODAY - timedelta(days=30 * i))
        findings = detection.build_findings(self.user)
        self.assertEqual(len(findings), 1, "four charges from one vendor = ONE finding")
        self.assertEqual(findings[0]["occurrences"], 4)
        self.assertGreater(findings[0]["annual_estimate"], 0)

    def test_recurring_series_is_its_own_pattern(self):
        recurring = RecurringTransaction.objects.create(
            user=self.user, name="Design Tool", transaction_type="expense",
            amount=Decimal("-54.00"), account=self.checking, frequency="monthly",
            start_date=date(2025, 1, 1), next_due_date=TODAY,
        )
        self._mismatch(recurring_source=recurring)
        self._mismatch(payee="Ad-hoc Vendor")
        findings = detection.build_findings(self.user)
        self.assertEqual(len(findings), 2)
        self.assertTrue(any(f["is_recurring"] for f in findings))

    def test_never_branches_on_an_entity_name(self):
        """Rename the business — detection is structural and must be unchanged."""
        self._mismatch(confirmed=True)
        before = len(detection.build_findings(self.user))
        self.business.name = "Something Else Entirely"
        self.business.save()
        self.assertEqual(len(detection.build_findings(self.user)), before)


class ExcludedPopulationTests(F1Base):
    """Transfers, card payments, opening balances, pending, and inactive rows never
    become findings — because they can never be attributed in the first place."""

    def test_excluded_kinds_cannot_produce_findings(self):
        transfer_cat = TransactionCategory.objects.create(
            name="Transfer", category_type="transfer", is_system=True,
        )
        cases = {
            "opening_balance": dict(is_opening_balance=True),
            "pending": dict(plaid_pending=True),
            "transfer_category": dict(category=transfer_cat),
            "card_payment": dict(description="Payment to Company Card",
                                 amount=Decimal("-500.00")),
        }
        from django.core.exceptions import ValidationError
        for label, kwargs in cases.items():
            with self.subTest(case=label):
                txn = self._txn(**kwargs)
                with self.assertRaises(ValidationError):
                    attribution_service.attribute(
                        self.user, txn, self.business,
                        source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
                        actor=TransactionAttribution.ACTOR_SYSTEM,
                    )
        self.assertEqual(detection.build_findings(self.user), [])

    def test_soft_deleted_transaction_drops_out_of_findings(self):
        row = self._mismatch(confirmed=True)
        self.assertEqual(len(detection.build_findings(self.user)), 1)
        row.transaction.soft_delete()
        self.assertEqual(detection.build_findings(self.user), [])


class InsightLifecycleTests(F1Base):

    def test_findings_write_canonical_insights(self):
        self._mismatch(confirmed=True)
        result = detection.record_findings(self.user)
        self.assertEqual(result["created"], 1)
        insight = Insight.objects.get(user=self.user,
                                      insight_type=detection.INSIGHT_TYPE)
        self.assertEqual(insight.module, "finance")
        self.assertEqual(insight.severity, "info")
        self.assertTrue(insight.explain_why)
        self.assertIn("transaction_ids", insight.evidence)
        self.assertIn("annual_estimate", insight.evidence)
        self.assertTrue(insight.dedupe_key)

    def test_rerun_is_idempotent(self):
        self._mismatch(confirmed=True)
        detection.record_findings(self.user)
        second = detection.record_findings(self.user)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["updated"], 1)
        self.assertEqual(
            Insight.objects.filter(user=self.user,
                                   insight_type=detection.INSIGHT_TYPE).count(), 1)

    def test_resolved_pattern_is_retired(self):
        row = self._mismatch()
        detection.record_findings(self.user)
        attribution_service.confirm(self.user, row.transaction, self.personal)
        result = detection.record_findings(self.user)
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(
            Insight.objects.get(user=self.user,
                                insight_type=detection.INSIGHT_TYPE).status, "dismissed")

    def test_insight_states_facts_without_a_recommendation(self):
        self._mismatch(confirmed=True)
        detection.record_findings(self.user)
        insight = Insight.objects.get(user=self.user,
                                      insight_type=detection.INSIGHT_TYPE)
        blob = f"{insight.title} {insight.message} {insight.explain_why}".lower()
        for verdict in ("you should", "we recommend", "move this", "switch to",
                        "mistake", "wrong"):
            self.assertNotIn(verdict, blob, f"WLJ rendered a verdict: {verdict!r}")

    def test_no_cross_user_leakage(self):
        other = User.objects.create_user(email="f1-other@example.com", password="x" * 14)
        entity_service.ensure_default_entities(other)
        self._mismatch(confirmed=True)
        detection.record_findings(self.user)
        self.assertEqual(detection.build_findings(other), [])
        self.assertEqual(Insight.objects.filter(user=other).count(), 0)


class DetectionQueryShapeTests(F1Base):

    def test_scan_does_not_grow_queries_with_transaction_count(self):
        for i in range(15):
            self._mismatch(date=TODAY - timedelta(days=i), payee=f"Vendor {i}")
        with self.assertNumQueries(1):
            list(detection.find_mismatches(self.user))

    def test_no_provider_call_in_detection(self):
        """Detection is deterministic comparison; a model call here would be a defect."""
        import apps.finance.services.opportunity_detection as module
        source = open(module.__file__.replace(".pyc", ".py")).read()
        for token in ("_call_api", "OpenAI", "AIService", "build_guarded_client"):
            self.assertNotIn(token, source)


class DetectionTaskTests(F1Base):

    def test_task_runs_and_is_idempotent(self):
        from apps.finance.tasks import detect_finance_opportunities
        self._mismatch(confirmed=True)
        first = detect_finance_opportunities(user_id=self.user.id)
        second = detect_finance_opportunities(user_id=self.user.id)
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["updated"], 1)

    def test_task_is_registered_on_the_beat_schedule(self):
        from django.conf import settings
        entries = [e for e in settings.CELERY_BEAT_SCHEDULE.values()
                   if e["task"] == "apps.finance.tasks.detect_finance_opportunities"]
        self.assertEqual(len(entries), 1)
        # Crontab, never an interval — Railway resets PersistentScheduler on restart.
        self.assertEqual(type(entries[0]["schedule"]).__name__, "crontab")
