# ==============================================================================
# File: apps/finance/tests/test_category_assignment.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Choosing and creating a transaction's category, in place.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Ordinary users categorising their own money.

The invariants that matter here are ownership (one person's categories are invisible to
another), authority (a user's choice outranks the provider's and survives the next
sync), lineage (the provider's own classification is never overwritten), and the
lifecycle rules that keep an archived category from quietly changing what a transaction
says it is.
"""
import json
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction as db_transaction
from django.test import TestCase
from django.urls import reverse

from apps.finance.models import (FinanceAuditLog, FinancialAccount, Transaction,
                                 TransactionCategory)
from apps.finance.services import category_assignment as svc
from apps.users.models import User


def _enable_finance(user):
    """A user who can actually reach Finance.

    Terms acceptance and completed onboarding are prerequisites for ANY authenticated
    page in WLJ — without them the middleware redirects and every assertion about the
    rendered control is really an assertion about the onboarding screen.
    """
    from django.conf import settings
    from apps.users.models import TermsAcceptance

    TermsAcceptance.objects.get_or_create(
        user=user,
        defaults={"terms_version": settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")},
    )
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.finances_enabled = True
    prefs.save()
    return user


class CategoryTestBase(TestCase):
    def setUp(self):
        self.user = _enable_finance(
            User.objects.create_user(email="cat@example.com", password="pw"))
        self.other = _enable_finance(
            User.objects.create_user(email="other@example.com", password="pw"))
        self.account = FinancialAccount.objects.create(
            user=self.user, name="Checking")
        self.system = TransactionCategory.objects.create(
            name="Groceries", category_type="expense", is_system=True)
        self.txn = Transaction.objects.create(
            user=self.user, account=self.account, date=date(2026, 8, 20),
            amount=-42, description="Corner shop",
            provider_category_primary="FOOD_AND_DRINK",
            category=self.system,
            category_source=Transaction.CATEGORY_SOURCE_PROVIDER)

    def _login(self, user=None):
        self.client.force_login(user or self.user)

    def _set(self, body, txn=None, expect=200):
        response = self.client.post(
            reverse("finance:transaction_category_set", args=[(txn or self.txn).pk]),
            data=json.dumps(body), content_type="application/json")
        self.assertEqual(response.status_code, expect, response.content[:300])
        return response


class AuthorizationTests(CategoryTestBase):
    """Normal Finance permissions — never staff, never Django admin."""

    def test_anonymous_is_redirected(self):
        response = self.client.post(
            reverse("finance:transaction_category_set", args=[self.txn.pk]),
            data="{}", content_type="application/json")
        self.assertIn(response.status_code, (302, 403))

    def test_user_without_finance_capability_is_refused(self):
        prefs = self.user.preferences
        prefs.finances_enabled = False
        prefs.save(update_fields=["finances_enabled"])
        self._login()
        self._set({"category_id": self.system.pk}, expect=403)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.category_source,
                         Transaction.CATEGORY_SOURCE_PROVIDER)

    def test_ordinary_non_staff_user_succeeds(self):
        self.assertFalse(self.user.is_staff)
        self._login()
        self._set({"category_id": self.system.pk})
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.category_source, Transaction.CATEGORY_SOURCE_USER)

    def test_cannot_categorise_someone_elses_transaction(self):
        self._login(self.other)
        response = self.client.post(
            reverse("finance:transaction_category_set", args=[self.txn.pk]),
            data=json.dumps({"category_id": self.system.pk}),
            content_type="application/json")
        self.assertEqual(response.status_code, 404)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.category, self.system)
        self.assertEqual(self.txn.category_source,
                         Transaction.CATEGORY_SOURCE_PROVIDER)


class IsolationTests(CategoryTestBase):
    """One person's private categories must be invisible and unusable to another."""

    def setUp(self):
        super().setUp()
        self.theirs = TransactionCategory.objects.create(
            user=self.other, name="Their Secret Project", category_type="expense")

    def test_another_users_category_is_not_offered(self):
        names = [c["name"] for c in
                 svc.category_choices(self.user, self.txn)["categories"]]
        self.assertIn("Groceries", names)
        self.assertNotIn("Their Secret Project", names)

    def test_another_users_category_cannot_be_assigned(self):
        self._login()
        response = self.client.post(
            reverse("finance:transaction_category_set", args=[self.txn.pk]),
            data=json.dumps({"category_id": self.theirs.pk}),
            content_type="application/json")
        self.assertEqual(response.status_code, 404)
        self.txn.refresh_from_db()
        self.assertNotEqual(self.txn.category_id, self.theirs.pk)

    def test_service_refuses_a_foreign_category_directly(self):
        with self.assertRaises(ValidationError):
            svc.assign_category(self.user, self.txn, self.theirs)

    def test_options_endpoint_leaks_nothing(self):
        self._login()
        response = self.client.get(
            reverse("finance:transaction_category_options", args=[self.txn.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Their Secret Project", response.content.decode())


class CreationTests(CategoryTestBase):
    """Name only — everything else is derived or defaulted."""

    def test_creating_asks_for_nothing_but_a_name(self):
        self._login()
        response = self._set({"new_name": "Coffee"})
        body = response.json()
        self.assertTrue(body["created"])
        self.assertEqual(body["category"]["name"], "Coffee")

        category = TransactionCategory.objects.get(user=self.user, name="Coffee")
        self.assertFalse(category.is_system)
        self.assertTrue(category.is_active)
        # Derived from the transaction's own sign rather than asked for.
        self.assertEqual(category.category_type, "expense")

    def test_type_is_inferred_from_an_income_transaction(self):
        income = Transaction.objects.create(
            user=self.user, account=self.account, date=date(2026, 8, 21),
            amount=500, description="Invoice")
        self._login()
        self._set({"new_name": "Consulting"}, txn=income)
        self.assertEqual(
            TransactionCategory.objects.get(user=self.user,
                                            name="Consulting").category_type,
            "income")

    def test_blank_name_is_refused(self):
        self._login()
        for blank in ("", "   ", "\t"):
            with self.subTest(blank=repr(blank)):
                response = self.client.post(
                    reverse("finance:transaction_category_set", args=[self.txn.pk]),
                    data=json.dumps({"new_name": blank, "category_id": None}),
                    content_type="application/json")
                # A blank name is not a creation request; nothing is created.
                self.assertEqual(
                    TransactionCategory.objects.filter(user=self.user).count(), 0)

    def test_service_rejects_a_blank_name(self):
        with self.assertRaises(ValidationError):
            svc.normalise_name("   ")

    def test_case_insensitive_duplicate_reuses_rather_than_duplicating(self):
        self._login()
        self._set({"new_name": "Coffee"})
        self._set({"new_name": "  cOFFEE  "})
        self.assertEqual(
            TransactionCategory.objects.filter(user=self.user,
                                               category_type="expense").count(), 1)

    def test_typing_a_system_category_name_reuses_the_system_one(self):
        self._login()
        body = self._set({"new_name": "groceries"}).json()
        self.assertFalse(body["created"])
        self.assertTrue(body["reused"])
        self.assertEqual(TransactionCategory.objects.filter(user=self.user).count(), 0)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.category_id, self.system.pk)

    def test_database_refuses_a_case_insensitive_personal_duplicate(self):
        TransactionCategory.objects.create(
            user=self.user, name="Software", category_type="expense")
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                TransactionCategory.objects.create(
                    user=self.user, name="software", category_type="expense")

    def test_database_refuses_a_blank_category_name(self):
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                TransactionCategory.objects.create(
                    user=self.user, name="", category_type="expense")

    def test_two_users_may_each_have_the_same_private_name(self):
        TransactionCategory.objects.create(
            user=self.user, name="Software", category_type="expense")
        TransactionCategory.objects.create(
            user=self.other, name="Software", category_type="expense")   # must not raise
        self.assertEqual(
            TransactionCategory.objects.filter(name="Software").count(), 2)

    def test_same_name_is_allowed_across_different_types(self):
        TransactionCategory.objects.create(
            user=self.user, name="Rent", category_type="expense")
        TransactionCategory.objects.create(
            user=self.user, name="Rent", category_type="income")         # must not raise


class AssignmentTests(CategoryTestBase):
    """The user's answer becomes authoritative without erasing the bank's."""

    def test_creation_assigns_immediately(self):
        self._login()
        body = self._set({"new_name": "Coffee"}).json()
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.category.name, "Coffee")
        self.assertEqual(self.txn.category_source, Transaction.CATEGORY_SOURCE_USER)
        self.assertEqual(body["category"]["id"], self.txn.category_id)

    def test_assignment_records_a_user_decision(self):
        self._login()
        self._set({"category_id": self.system.pk})
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.category_source, Transaction.CATEGORY_SOURCE_USER)
        self.assertIsNotNone(self.txn.category_confirmed_at)

    def test_provider_lineage_is_preserved(self):
        self._login()
        self._set({"new_name": "Coffee"})
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.provider_category_primary, "FOOD_AND_DRINK")

    def test_a_later_sync_cannot_overwrite_the_user_choice(self):
        """The existing ingestion rule, exercised end to end."""
        from apps.finance.services.sync_service import TransactionSyncService
        from apps.finance.models import BankConnection

        self._login()
        self._set({"new_name": "Coffee"})
        self.txn.refresh_from_db()

        connection = BankConnection.objects.create(
            user=self.user, institution_name="B", item_id="item-cat",
            connection_status=BankConnection.STATUS_ACTIVE)
        TransactionSyncService(connection)._apply_provider_category(self.txn)

        self.assertEqual(self.txn.category.name, "Coffee")
        self.assertEqual(self.txn.category_source, Transaction.CATEGORY_SOURCE_USER)

    def test_clearing_the_category_is_honest_about_it(self):
        self._login()
        self._set({"category_id": None})
        self.txn.refresh_from_db()
        self.assertIsNone(self.txn.category)
        self.assertEqual(self.txn.category_source, Transaction.CATEGORY_SOURCE_NONE)
        self.assertIsNone(self.txn.category_confirmed_at)


class AuditTests(CategoryTestBase):
    def test_assignment_is_audited_with_both_sides_of_the_change(self):
        self._login()
        self._set({"new_name": "Coffee"})
        entry = (FinanceAuditLog.objects
                 .filter(user=self.user, entity_type="transaction", action="update")
                 .order_by("-id").first())
        self.assertIsNotNone(entry)
        self.assertEqual(entry.details["field"], "category")
        self.assertEqual(entry.details["from_category"], "Groceries")
        self.assertEqual(entry.details["to_category"], "Coffee")
        self.assertEqual(entry.details["category_source"], "user")

    def test_category_creation_is_audited(self):
        self._login()
        self._set({"new_name": "Coffee"})
        entry = FinanceAuditLog.objects.filter(
            user=self.user, entity_type="transaction_category",
            action="create").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.details["name"], "Coffee")
        self.assertFalse(entry.details["is_system"])

    def test_audit_failure_never_blocks_the_user(self):
        from unittest.mock import patch
        with patch("apps.finance.security.FinanceAuditLogger.log",
                   side_effect=RuntimeError("audit down")):
            svc.assign_category(self.user, self.txn, self.system)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.category_source, Transaction.CATEGORY_SOURCE_USER)


class ArchivedCategoryTests(CategoryTestBase):
    """Archiving hides a category from NEW choices; it never invalidates old ones."""

    def test_an_archived_category_still_shows_on_the_transaction_using_it(self):
        archived = TransactionCategory.objects.create(
            user=self.user, name="Old Hobby", category_type="expense", is_active=False)
        self.txn.category = archived
        self.txn.save(update_fields=["category"])

        options = svc.category_choices(self.user, self.txn)
        self.assertEqual(options["current_id"], archived.pk)
        entry = next(c for c in options["categories"] if c["id"] == archived.pk)
        self.assertTrue(entry["archived"])

    def test_an_archived_category_is_not_offered_to_other_transactions(self):
        TransactionCategory.objects.create(
            user=self.user, name="Old Hobby", category_type="expense", is_active=False)
        names = [c["name"] for c in
                 svc.category_choices(self.user, self.txn)["categories"]]
        self.assertNotIn("Old Hobby", names)

    def test_recreating_an_archived_personal_category_revives_it(self):
        archived = TransactionCategory.objects.create(
            user=self.user, name="Old Hobby", category_type="expense", is_active=False)
        self._login()
        self._set({"new_name": "old hobby"})
        archived.refresh_from_db()
        self.assertTrue(archived.is_active)
        self.assertEqual(TransactionCategory.objects.filter(
            user=self.user, name__iexact="old hobby").count(), 1)

    def test_archiving_does_not_change_what_a_transaction_says_it_is(self):
        category = TransactionCategory.objects.create(
            user=self.user, name="Old Hobby", category_type="expense")
        self._login()
        self._set({"category_id": category.pk})
        category.is_active = False
        category.save(update_fields=["is_active"])

        self.txn.refresh_from_db()
        self.assertEqual(self.txn.category_id, category.pk)
        self.assertEqual(self.txn.category_source, Transaction.CATEGORY_SOURCE_USER)


class SystemCategoryProtectionTests(CategoryTestBase):
    def test_creating_never_mutates_a_system_category(self):
        self._login()
        self._set({"new_name": "GROCERIES"})
        self.system.refresh_from_db()
        self.assertEqual(self.system.name, "Groceries")
        self.assertTrue(self.system.is_system)
        self.assertIsNone(self.system.user_id)

    def test_a_system_category_is_never_revived_or_altered_by_reuse(self):
        self.system.is_active = False
        self.system.save(update_fields=["is_active"])
        category, created = svc.resolve_or_create_category(
            self.user, "Groceries", "expense")
        self.assertFalse(created)
        self.system.refresh_from_db()
        self.assertFalse(self.system.is_active,
                         "a system category must not be silently re-activated")

    def test_this_feature_exposes_no_rename_or_delete(self):
        from apps.finance import urls as finance_urls
        names = {p.name for p in finance_urls.urlpatterns if getattr(p, "name", None)}
        self.assertIn("transaction_category_set", names)
        for forbidden in ("category_delete", "category_update", "category_rename"):
            self.assertNotIn(forbidden, names)
