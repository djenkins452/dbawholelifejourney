# ==============================================================================
# File: apps/finance/tests/test_scheduled_intelligence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P11/P12 — scheduled jobs that may do nothing, and must never invent.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""A job runs because a clock fired, not because there is something to say.

That is exactly when a system starts manufacturing findings. Every test here checks one
of: it produced nothing when there was nothing, it did not call a provider, it is safe to
run twice, and one user's bad data did not cost everyone else their sweep.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings

from apps.finance.models import (FinancialAccount, NetWorthSnapshot, RecurringSeries,
                                 SavingsOpportunity, TangibleAsset, Transaction)
from apps.finance.services.finance_calc import data_health as DH
from apps.finance.tests.test_p1_economic_roles import RoleBase

JAN = date(2026, 1, 5)


class RegistrationTests(RoleBase):
    """A job nobody scheduled is a job that never runs."""

    JOBS = (
        "apps.finance.tasks_intelligence.sweep_recurring_detection",
        "apps.finance.tasks_intelligence.sweep_role_reconciliation",
        "apps.finance.tasks_intelligence.sweep_net_worth_snapshots",
        "apps.finance.tasks_intelligence.sweep_opportunities",
        "apps.finance.tasks_intelligence.sweep_plan_outcomes",
        "apps.finance.tasks_intelligence.sweep_data_health",
    )

    def test_every_job_is_on_the_beat_schedule(self):
        scheduled = {entry["task"]
                     for entry in settings.CELERY_BEAT_SCHEDULE.values()}
        for job in self.JOBS:
            with self.subTest(job=job):
                self.assertIn(job, scheduled)

    def test_every_finance_job_uses_a_crontab_not_an_interval(self):
        """Railway resets PersistentScheduler on restart and starves intervals."""
        from celery.schedules import crontab
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            if entry["task"].startswith("apps.finance.tasks_intelligence"):
                with self.subTest(name=name):
                    self.assertIsInstance(entry["schedule"], crontab)

    def test_every_job_is_importable_and_callable(self):
        from apps.finance import tasks_intelligence as TI
        for job in self.JOBS:
            with self.subTest(job=job):
                self.assertTrue(hasattr(TI, job.rsplit(".", 1)[1]))


class SafetyTests(RoleBase):
    def test_no_job_calls_a_provider(self):
        """None of this is allowed to cost money or hit Plaid.

        Checks the CODE, not the prose: the module docstring says the word
        `/transactions/refresh` precisely to promise it is never called, and a guard
        that cannot tell a promise from a call is not a guard.
        """
        import ast

        from apps.finance import tasks_intelligence as TI

        tree = ast.parse(open(TI.__file__).read())
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                called.add(node.attr)
            elif isinstance(node, ast.Name):
                called.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                called.add(getattr(node, "module", "") or "")
                called.update(alias.name for alias in node.names)

        for forbidden in ("transactions_refresh", "plaid_client", "PlaidApi",
                          "liabilities_get", "investments_holdings_get",
                          "plaid", "apps.finance.services.plaid_client"):
            self.assertNotIn(forbidden, called)

    def test_a_lock_is_held_per_user(self):
        from apps.finance.tasks_intelligence import user_lock
        with user_lock("test", self.user.pk) as first:
            self.assertTrue(first)
            with user_lock("test", self.user.pk) as second:
                self.assertFalse(second, "a second pass must step aside, not queue")

    def test_the_lock_is_released_afterwards(self):
        from apps.finance.tasks_intelligence import user_lock
        with user_lock("test", self.user.pk):
            pass
        with user_lock("test", self.user.pk) as again:
            self.assertTrue(again)

    def test_one_failing_user_does_not_stop_the_sweep(self):
        from apps.finance.tasks_intelligence import _sweep
        self._txn(-50, primary="FOOD_AND_DRINK")     # makes this user eligible
        calls = []

        def work(user):
            calls.append(user.pk)
            raise ValueError("bad data")

        result = _sweep("test", work)
        self.assertEqual(result["failed"], len(calls))
        self.assertGreaterEqual(len(calls), 1)

    def test_the_batch_cap_is_reported_not_silent(self):
        from apps.finance.tasks_intelligence import _sweep
        result = _sweep("test", lambda user: None, limit=0)
        self.assertIn("skipped_over_batch", result)
        self.assertEqual(result["processed"], 0)


class DoingNothingTests(RoleBase):
    """Each job is allowed to find nothing, and must say so rather than invent."""

    def test_recurring_detection_reports_nothing_when_there_is_nothing(self):
        from apps.finance.tasks_intelligence import sweep_recurring_detection
        result = sweep_recurring_detection()
        self.assertEqual(result["results"], [])

    def test_opportunities_report_nothing_without_levers(self):
        from apps.finance.tasks_intelligence import sweep_opportunities
        self.assertEqual(sweep_opportunities()["results"], [])

    def test_plan_outcomes_report_nothing_without_accepted_plans(self):
        from apps.finance.tasks_intelligence import sweep_plan_outcomes
        self.assertEqual(sweep_plan_outcomes()["results"], [])

    def test_data_health_reports_nothing_for_a_clean_account(self):
        from apps.finance.tasks_intelligence import sweep_data_health
        Transaction.objects.all().delete()
        FinancialAccount.objects.filter(user=self.user).update(
            current_balance=Decimal("100"))
        result = sweep_data_health()
        self.assertEqual(result["results"], [])


class IdempotenceTests(RoleBase):
    def test_snapshots_do_not_duplicate_across_runs(self):
        from apps.finance.tasks_intelligence import sweep_net_worth_snapshots
        self._txn(-50, primary="FOOD_AND_DRINK")
        sweep_net_worth_snapshots()
        sweep_net_worth_snapshots()
        self.assertEqual(NetWorthSnapshot.objects.filter(user=self.user).count(), 1)

    def test_role_reconciliation_writes_nothing_on_a_second_pass(self):
        from apps.finance.tasks_intelligence import sweep_role_reconciliation
        self._txn(-50, primary="FOOD_AND_DRINK")
        sweep_role_reconciliation()
        second = sweep_role_reconciliation()
        self.assertEqual(second["results"], [])

    def test_recurring_detection_does_not_duplicate_a_series(self):
        from apps.finance.tasks_intelligence import sweep_recurring_detection
        for i in range(6):
            self._txn(-15, on=JAN + timedelta(days=30 * i), description="Filmflix",
                      primary="ENTERTAINMENT")
        sweep_recurring_detection()
        sweep_recurring_detection()
        self.assertEqual(RecurringSeries.objects.filter(user=self.user).count(), 1)


class DriftTests(RoleBase):
    def test_drift_is_reported_and_never_silently_rewritten(self):
        """A cron job does not get to mass-reclassify a person's history."""
        from apps.finance.services.finance_calc import backfill
        from apps.finance.tasks_intelligence import sweep_role_reconciliation

        self._txn(-50, primary="FOOD_AND_DRINK")
        backfill.run(self.user, commit=True)
        Transaction.objects.filter(user=self.user).update(
            role_classifier_version="0.0.1")

        result = sweep_role_reconciliation()
        mine = [r for r in result["results"] if r["user"] == self.user.pk]
        self.assertTrue(mine)
        self.assertGreater(mine[0]["classifier_drift"], 0)
        self.assertEqual(mine[0]["written"], 0, "reported, not rewritten")
        self.assertEqual(
            Transaction.objects.filter(user=self.user,
                                       role_classifier_version="0.0.1").count(), 1)


class DataHealthTests(RoleBase):
    def test_an_unclassified_transaction_is_a_high_severity_gap(self):
        self._txn(-50, primary="FOOD_AND_DRINK")
        issues = {i["code"]: i for i in DH.evaluate(self.user)["issues"]}
        self.assertIn("unclassified_transactions", issues)
        self.assertEqual(issues["unclassified_transactions"]["severity"], "high")

    def test_a_debt_without_terms_is_named_with_a_route(self):
        FinancialAccount.objects.create(
            user=self.user, name="Truck", account_type="loan",
            current_balance=Decimal("-24000"))
        issues = {i["code"]: i for i in DH.evaluate(self.user)["issues"]}
        self.assertIn("loan_terms_missing", issues)
        self.assertEqual(issues["loan_terms_missing"]["route"], "finance:money_debt")

    def test_an_unvalued_asset_is_flagged_as_understating_net_worth(self):
        TangibleAsset.objects.create(user=self.user, name="House",
                                     asset_type="real_estate")
        issues = {i["code"]: i for i in DH.evaluate(self.user)["issues"]}
        self.assertIn("assets_unvalued", issues)
        self.assertIn("understated", issues["assets_unvalued"]["detail"])

    def test_issues_are_ordered_worst_first(self):
        FinancialAccount.objects.create(
            user=self.user, name="Truck", account_type="loan",
            current_balance=Decimal("-24000"))
        self._txn(-50, primary="FOOD_AND_DRINK")
        severities = [i["severity"] for i in DH.evaluate(self.user)["issues"]]
        self.assertEqual(severities, sorted(
            severities, key=lambda s: {"high": 0, "medium": 1, "low": 2}[s]))

    def test_every_issue_offers_somewhere_to_go(self):
        self._txn(-50, primary="FOOD_AND_DRINK")
        for issue in DH.evaluate(self.user)["issues"]:
            with self.subTest(code=issue["code"]):
                self.assertTrue(issue["route"])

    def test_it_never_renders_a_verdict(self):
        """WLJ says a valuation is old. It never says your net worth is wrong."""
        TangibleAsset.objects.create(user=self.user, name="House",
                                     asset_type="real_estate")
        text = " ".join(i["detail"] for i in DH.evaluate(self.user)["issues"]).lower()
        for verdict in ("you are wrong", "your net worth is wrong", "you should"):
            self.assertNotIn(verdict, text)
