# ==============================================================================
# File: apps/finance/tests/test_finance_reset.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Finance reset removes everything Finance and nothing else.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""A destructive tool earns trust by proving its blast radius."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.core.ai_insights.models import Insight
from apps.core.models import Notification
from apps.finance.models import (
    AttributionRule,
    BankConnection,
    Budget,
    FinanceAuditLog,
    FinanceOpportunity,
    FinancialAccount,
    FinancialEntity,
    FinancialGoal,
    Payee,
    RecurringTransaction,
    Transaction,
    TransactionAttribution,
    TransactionCategory,
)
from apps.finance.services import finance_reset
from apps.finance.services import finance_entities as entity_service
from apps.finance.services.encryption import generate_encryption_key
from apps.users.models import TermsAcceptance, User

TODAY = date.today()


class ResetBase(TestCase):
    def setUp(self):
        self.key = generate_encryption_key()
        self.user = self._user("reset@example.com", finance=True, staff=True)
        self.other = self._user("reset-other@example.com", finance=False)

        self.system_category = TransactionCategory.objects.create(
            name="Groceries", category_type="expense", is_system=True, user=None)
        self.user_category = TransactionCategory.objects.create(
            name="My Custom", category_type="expense", is_system=False, user=self.user)

        self.personal, _ = entity_service.ensure_default_entities(self.user)
        self.business = entity_service.create_entity(
            self.user, entity_type=FinancialEntity.TYPE_BUSINESS, name="Harbor")
        self.account = FinancialAccount.objects.create(
            user=self.user, name="Checking", account_type="checking")
        entity_service.assign_account_entity(
            self.user, self.account, self.personal,
            effective_from=TODAY - timedelta(days=100))
        self.recurring = RecurringTransaction.objects.create(
            user=self.user, name="Sub", transaction_type="expense",
            amount=Decimal("-10.00"), account=self.account, frequency="monthly",
            start_date=TODAY - timedelta(days=90), next_due_date=TODAY)
        self.txn = Transaction.objects.create(
            user=self.user, account=self.account, date=TODAY,
            amount=Decimal("-10.00"), description="x", payee="Vendor",
            category=self.user_category, recurring_source=self.recurring)
        Budget.objects.create(user=self.user, month=TODAY.replace(day=1),
                              category=self.user_category,
                              budgeted_amount=Decimal("50.00"))
        FinancialGoal.objects.create(user=self.user, name="Fund",
                                     target_amount=Decimal("100.00"))
        Payee.objects.create(user=self.user, name="Vendor")

        from apps.finance.services import attribution as attribution_service
        self.attribution = attribution_service.confirm(
            self.user, self.txn, self.business)
        AttributionRule.objects.create(
            user=self.user, scope=AttributionRule.SCOPE_PAYEE,
            payee=Payee.objects.get(user=self.user), entity=self.business)
        FinanceOpportunity.objects.create(
            user=self.user, dedupe_key="k1", attributed_entity=self.business,
            paid_by_entity=self.personal)
        Insight.objects.create(user=self.user, module="finance",
                               insight_type="entity_expense_mismatch",
                               title="t", message="m", explain_why="w",
                               dedupe_key="k1")
        Notification.objects.create(user=self.user, category="finance",
                                    title="t", message="m")

        # A soft-deleted row must NOT survive a reset.
        self.soft_deleted = Transaction.objects.create(
            user=self.user, account=self.account, date=TODAY,
            amount=Decimal("-1.00"), description="gone")
        self.soft_deleted.soft_delete()

        # Non-Finance data that must be untouched.
        self.other_insight = Insight.objects.create(
            user=self.user, module="health", insight_type="weight_trend",
            title="t", message="m", explain_why="w", dedupe_key="h1")
        self.other_notification = Notification.objects.create(
            user=self.user, category="task", title="t", message="m")

    def _user(self, email, *, finance=False, staff=False):
        user = User.objects.create_user(email=email, password="testpass123",
                                        is_staff=staff)
        TermsAcceptance.objects.create(
            user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        prefs = user.preferences
        prefs.has_completed_onboarding = True
        prefs.finances_enabled = finance
        prefs.save()
        return user


class InventoryTests(ResetBase):

    def test_inventory_counts_everything_including_soft_deleted(self):
        report = finance_reset.inventory()
        self.assertEqual(report["finance_models"]["transactions"]["total"], 2)
        self.assertEqual(report["finance_models"]["transactions"]["soft_deleted"], 1)
        self.assertEqual(report["derived"]["finance_insights"], 1)
        self.assertEqual(report["derived"]["finance_notifications"], 1)
        self.assertEqual(report["preserved"]["system_categories"], 1)

    def test_inventory_reports_no_values(self):
        import json
        blob = json.dumps(finance_reset.inventory(), default=str)
        for value in ("Vendor", "Checking", "Harbor", "My Custom", "10.00"):
            self.assertNotIn(value, blob)

    def test_inventory_changes_nothing(self):
        before = Transaction.all_objects.count()
        finance_reset.inventory()
        self.assertEqual(Transaction.all_objects.count(), before)


class ProviderSafetyTests(ResetBase):

    def test_reset_refuses_while_a_provider_token_exists(self):
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=self.key):
            connection = BankConnection.objects.create(
                user=self.user, item_id="i1", institution_name="Bank",
                connection_status=BankConnection.STATUS_ACTIVE)
            connection.set_access_token("access-sandbox-token")
            connection.save()
            with self.assertRaises(finance_reset.ProviderCredentialPresent):
                finance_reset.reset()
        self.assertEqual(Transaction.all_objects.count(), 2,
                         "nothing may be deleted while a credential exists")

    def test_command_refuses_with_a_clear_error(self):
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=self.key):
            connection = BankConnection.objects.create(
                user=self.user, item_id="i1", institution_name="Bank")
            connection.set_access_token("access-sandbox-token")
            connection.save()
            with self.assertRaises(CommandError) as ctx:
                call_command("finance_reset", confirm="RESET-FINANCE",
                             stdout=StringIO())
        self.assertIn("Revoke", str(ctx.exception))


class ResetTests(ResetBase):

    def test_reset_empties_every_finance_model(self):
        finance_reset.reset(actor=self.user)
        for model in (FinancialAccount, Transaction, Budget, FinancialGoal,
                      RecurringTransaction, Payee, FinancialEntity,
                      TransactionAttribution, AttributionRule, FinanceOpportunity,
                      BankConnection):
            self.assertEqual(getattr(model, "all_objects", model.objects).count(), 0,
                             f"{model.__name__} still has rows")

    def test_soft_deleted_rows_do_not_survive(self):
        finance_reset.reset(actor=self.user)
        self.assertEqual(Transaction.all_objects.count(), 0)

    def test_derived_finance_records_are_removed(self):
        finance_reset.reset(actor=self.user)
        self.assertEqual(Insight.objects.filter(module="finance").count(), 0)
        self.assertEqual(Notification.objects.filter(category="finance").count(), 0)

    def test_non_finance_data_is_untouched(self):
        finance_reset.reset(actor=self.user)
        self.assertTrue(Insight.objects.filter(pk=self.other_insight.pk).exists())
        self.assertTrue(
            Notification.objects.filter(pk=self.other_notification.pk).exists())

    def test_system_taxonomy_is_preserved_and_user_categories_are_not(self):
        finance_reset.reset(actor=self.user)
        self.assertTrue(
            TransactionCategory.objects.filter(pk=self.system_category.pk).exists())
        self.assertFalse(
            TransactionCategory.objects.filter(pk=self.user_category.pk).exists())

    def test_users_and_finance_grant_survive(self):
        finance_reset.reset(actor=self.user)
        self.user.refresh_from_db()
        self.user.preferences.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.other.pk).exists())
        self.assertTrue(self.user.preferences.finances_enabled)
        self.assertFalse(self.other.preferences.finances_enabled)

    def test_reset_leaves_redacted_audit_evidence(self):
        finance_reset.reset(actor=self.user)
        record = FinanceAuditLog.objects.get(action=FinanceAuditLog.ACTION_RESET)
        self.assertEqual(record.entity_type, "module")
        self.assertTrue(record.details["removed"])
        import json
        blob = json.dumps(record.details)
        for value in ("Vendor", "Checking", "Harbor", "access-"):
            self.assertNotIn(value, blob)

    def test_reset_is_idempotent(self):
        finance_reset.reset(actor=self.user)
        second = finance_reset.reset(actor=self.user)
        self.assertEqual(
            sum(v for k, v in second["removed"].items()
                if k not in ("finance_audit_logs",)), 0)

    def test_sae_finance_state_is_stripped_without_losing_other_domains(self):
        from apps.core.ai_state.models import UserState
        UserState.objects.update_or_create(
            user=self.user,
            defaults={"state_data": {"finance": {"net_worth": 1}, "health": {"w": 2}}})
        finance_reset.reset(actor=self.user)
        state = UserState.objects.get(user=self.user)
        self.assertNotIn("finance", state.state_data)
        self.assertIn("health", state.state_data,
                      "another domain's state was destroyed")

    def test_dry_run_command_deletes_nothing(self):
        out = StringIO()
        call_command("finance_reset", stdout=out)
        self.assertIn("DRY RUN", out.getvalue())
        self.assertEqual(Transaction.all_objects.count(), 2)

    def test_command_requires_the_exact_confirmation_token(self):
        out = StringIO()
        call_command("finance_reset", confirm="yes", stdout=out)
        self.assertIn("DRY RUN", out.getvalue())
        self.assertEqual(Transaction.all_objects.count(), 2)

    def test_command_requires_a_staff_operator(self):
        with self.assertRaises(CommandError):
            call_command("finance_reset", confirm="RESET-FINANCE",
                         by="reset-other@example.com", stdout=StringIO())

    def test_command_completes_and_reports_empty(self):
        out = StringIO()
        call_command("finance_reset", confirm="RESET-FINANCE",
                     by="reset@example.com", stdout=out)
        output = out.getvalue()
        self.assertIn("RESET COMPLETE", output)
        self.assertIn("Finance is empty", output)
        self.assertEqual(Transaction.all_objects.count(), 0)

    def test_command_output_contains_no_values(self):
        out = StringIO()
        call_command("finance_reset", confirm="RESET-FINANCE",
                     by="reset@example.com", stdout=out)
        output = out.getvalue()
        for value in ("Vendor", "Checking", "Harbor", "My Custom", "reset@example.com"):
            self.assertNotIn(value, output)
