# ==============================================================================
# File: apps/core/tests/test_truth_exposure_completion.py
# Description: Truth Exposure Completion (2026-08-12) — Owner-1 deterministic certs.
# ==============================================================================
"""Exposes EXISTING canonical truth through the existing Retrieval Platform for three
proven gaps: Relationships interaction history, Project task records, Finance transaction
/ account entities. These tests certify Owner-1 invariants — canonical authority, correct
user scoping, dates/counts, no duplicate authority, no sensitive-field leakage — with
REAL seeded domain data.
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services import get_domain_entity, get_domain_history

User = get_user_model()


class RelationshipsHistoryExposureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.relationships.models import Person, RelationshipInteraction
        cls.user = User.objects.create_user(email="rel_owner@example.com", password="x")
        cls.other = User.objects.create_user(email="rel_other@example.com", password="x")
        cls.person = Person.objects.create(owner=cls.user, first_name="Heather",
                                            relationship_type="family")
        op = Person.objects.create(owner=cls.other, first_name="Zed",
                                   relationship_type="friend")
        today = date.today()
        # 3 interactions on day-10, 1 on day-3, for THIS user.
        for d, n in ((today - timedelta(days=10), 3), (today - timedelta(days=3), 1)):
            for _ in range(n):
                RelationshipInteraction.objects.create(
                    user=cls.user, person=cls.person, context_type_label="manual",
                    interaction_date=d)
        # foreign user's interaction — MUST be excluded from cls.user's history.
        RelationshipInteraction.objects.create(
            user=cls.other, person=op, context_type_label="manual",
            interaction_date=today - timedelta(days=3))

    def test_history_exposes_per_day_interaction_counts_user_scoped(self):
        # "this_year" robustly spans the seeded dates (10 and 3 days ago); "last_month" is
        # the PREVIOUS calendar month and would legitimately be empty.
        out = get_domain_history(self.user, "relationships", "interactions",
                                 period="this_year")
        self.assertIn(out.get("status"), ("ok", "ready"), out)
        # count/total live on the composed series (top-level or under 'value').
        val = out.get("value") if isinstance(out.get("value"), dict) else out
        # 2 days with interactions, 4 total — the foreign user's row is excluded.
        self.assertEqual(val.get("count"), 2, out)
        self.assertEqual(val.get("total"), 4, out)
        # deterministic trend is present (>= 2 points) — arithmetic, not a verdict.
        self.assertIsNotNone(val.get("change"))

    def test_history_advertised_and_comparable(self):
        from apps.ai.cos_services.domain_comparison import comparison_capable_domains
        from apps.ai.cos_services.domain_history import history_capable_domains
        self.assertIn("relationships", history_capable_domains())
        self.assertIn("relationships", comparison_capable_domains())


class ProjectTaskExposureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.life.models import Project, Task
        cls.user = User.objects.create_user(email="proj_owner@example.com", password="x")
        cls.other = User.objects.create_user(email="proj_other@example.com", password="x")
        cls.project = Project.objects.create(user=cls.user, title="Kitchen Remodel",
                                             status="active")
        Task.objects.create(user=cls.user, project=cls.project, title="Pick tiles",
                            completion_status="pending")
        Task.objects.create(user=cls.user, project=cls.project, title="Hire contractor",
                            completion_status="completed")
        foreign = Project.objects.create(user=cls.other, title="Foreign", status="active")
        Task.objects.create(user=cls.other, project=foreign, title="secret",
                            completion_status="pending")

    def test_project_entity_exposes_canonical_task_records(self):
        out = get_domain_entity(self.user, "projects", name="Kitchen")
        self.assertEqual(out.get("status"), "ready", out)
        ent = out.get("entity") or {}
        tasks = (ent.get("extensions") or {}).get("tasks") or []
        titles = {t["title"] for t in tasks}
        self.assertIn("Pick tiles", titles)
        self.assertIn("Hire contractor", titles)
        self.assertNotIn("secret", titles)          # user-scoped (canonical Task rows)
        # per-task status is the canonical Task field, not a duplicated verdict
        by_title = {t["title"]: t["status"] for t in tasks}
        self.assertEqual(by_title["Hire contractor"], "completed")


class FinanceEntityExposureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.finance.models import FinancialAccount, Transaction
        cls.user = User.objects.create_user(email="fin_owner@example.com", password="x")
        cls.other = User.objects.create_user(email="fin_other@example.com", password="x")
        cls.acct = FinancialAccount.objects.create(
            user=cls.user, name="Chase Checking", account_type="checking",
            current_balance="1000.00", account_number_last4="6411")
        FinancialAccount.objects.create(
            user=cls.user, name="Hidden Vault", account_type="savings",
            current_balance="5.00", is_hidden=True)
        today = date.today()
        Transaction.objects.create(user=cls.user, account=cls.acct, date=today,
                                   amount="-84.20", description="COSTCO WHOLESALE")
        Transaction.objects.create(user=cls.user, account=cls.acct, date=today,
                                   amount="-12.00", description="Coffee shop")
        Transaction.objects.create(user=cls.other, account=FinancialAccount.objects.create(
            user=cls.other, name="Other", account_type="checking", current_balance="0"),
            date=today, amount="-999.00", description="COSTCO other user")

    def test_transaction_search_by_merchant_user_scoped(self):
        out = get_domain_entity(self.user, "finance", entity_type="transaction",
                                filters={"contains": "Costco"})
        self.assertEqual(out.get("status"), "ready", out)
        ents = out.get("entities") or []
        self.assertEqual(len(ents), 1)              # foreign user's Costco excluded
        self.assertEqual(ents[0]["identity"], "COSTCO WHOLESALE")
        self.assertEqual(ents[0]["definition"]["direction"], "expense")

    def test_accounts_exclude_hidden_and_no_sensitive_fields(self):
        out = get_domain_entity(self.user, "finance", entity_type="account")
        self.assertEqual(out.get("status"), "ready", out)
        ents = out.get("entities") or []
        names = {e["identity"] for e in ents}
        self.assertIn("Chase Checking", names)
        self.assertNotIn("Hidden Vault", names)     # hidden accounts are not exposed
        chase = next(e for e in ents if e["identity"] == "Chase Checking")
        self.assertEqual(chase["definition"]["last4"], "6411")   # safe partial only
        # no credential/token/full-number field leaks into the model-facing entity
        blob = str(out).lower()
        for forbidden in ("plaid", "access_token", "account_number\":", "fingerprint"):
            self.assertNotIn(forbidden, blob)

    def test_finance_entity_advertised(self):
        from apps.ai.cos_services.domain_entity import entity_capable_domains
        self.assertIn("finance", entity_capable_domains())
