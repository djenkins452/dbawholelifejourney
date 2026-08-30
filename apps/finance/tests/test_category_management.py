# ==============================================================================
# File: apps/finance/tests/test_category_management.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Managing personal categories from the Categories page.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""`/finance/categories/` was a read-only list — it could not create, rename,
archive, restore or delete anything, and had no way to see an archived category.

These cover the management half: that an ordinary Finance user (no staff flag, no
Django admin) can run the whole lifecycle on categories they own, that system
categories stay untouchable, that one user can never see or change another's, and
that archiving never invalidates the transactions already assigned.
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from datetime import date
from decimal import Decimal

from apps.finance.models import (Budget, FinanceAuditLog, FinancialAccount,
                                 Transaction, TransactionCategory)
from apps.finance.services import category_assignment as svc
from apps.users.models import TermsAcceptance, User


def _usable(user):
    TermsAcceptance.objects.get_or_create(
        user=user,
        defaults={"terms_version": settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")})
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.finances_enabled = True
    prefs.save()
    return user


class ManageBase(TestCase):
    def setUp(self):
        self.user = _usable(User.objects.create_user(
            email="manage@example.com", password="pw"))
        self.other = _usable(User.objects.create_user(
            email="other@example.com", password="pw"))
        self.system = TransactionCategory.objects.create(
            name="Groceries", category_type="expense", is_system=True)
        self.mine = TransactionCategory.objects.create(
            user=self.user, name="Coffee", category_type="expense")
        self.account = FinancialAccount.objects.create(
            user=self.user, name="Checking")
        self.client.force_login(self.user)

    def _post(self, _route, *args, **data):
        """`_route` is underscored so a form field called `name` cannot collide."""
        return self.client.post(reverse(_route, args=args), data=data, follow=True)


class CreateTests(ManageBase):
    def test_ordinary_user_creates_an_expense_category(self):
        self.assertFalse(self.user.is_staff)
        self._post("finance:category_create", name="Books", category_type="expense")
        category = TransactionCategory.objects.get(user=self.user, name="Books")
        self.assertEqual(category.category_type, "expense")
        self.assertFalse(category.is_system)
        self.assertTrue(category.is_active)

    def test_ordinary_user_creates_an_income_category(self):
        self._post("finance:category_create", name="Consulting", category_type="income")
        self.assertEqual(
            TransactionCategory.objects.get(user=self.user,
                                            name="Consulting").category_type,
            "income")

    def test_blank_name_is_refused(self):
        before = TransactionCategory.objects.filter(user=self.user).count()
        response = self._post("finance:category_create", name="   ",
                              category_type="expense")
        self.assertEqual(TransactionCategory.objects.filter(user=self.user).count(),
                         before)
        self.assertContains(response, "name")

    def test_case_insensitive_duplicate_does_not_create_a_second(self):
        self._post("finance:category_create", name="  cOFFEE  ",
                   category_type="expense")
        self.assertEqual(
            TransactionCategory.objects.filter(user=self.user,
                                               name__iexact="coffee").count(), 1)

    def test_a_bad_type_is_refused(self):
        self._post("finance:category_create", name="Odd", category_type="nonsense")
        self.assertFalse(
            TransactionCategory.objects.filter(user=self.user, name="Odd").exists())

    def test_creation_uses_the_same_resolver_as_the_inline_picker(self):
        import inspect
        source = inspect.getsource(svc.create_personal_category)
        self.assertIn("resolve_or_create_category", source)


class RenameTests(ManageBase):
    def test_rename_a_personal_category(self):
        self._post("finance:category_rename", self.mine.pk, name="Espresso")
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.name, "Espresso")

    def test_rename_to_a_name_already_used_is_refused(self):
        TransactionCategory.objects.create(
            user=self.user, name="Tea", category_type="expense")
        response = self._post("finance:category_rename", self.mine.pk, name="tea")
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.name, "Coffee")
        self.assertContains(response, "already have a category")

    def test_a_pure_case_change_is_allowed(self):
        self._post("finance:category_rename", self.mine.pk, name="COFFEE")
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.name, "COFFEE")

    def test_blank_rename_is_refused(self):
        self._post("finance:category_rename", self.mine.pk, name="  ")
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.name, "Coffee")


class ArchiveRestoreTests(ManageBase):
    def setUp(self):
        super().setUp()
        self.txn = Transaction.objects.create(
            user=self.user, account=self.account, date=date(2026, 8, 20),
            amount=Decimal("-4.50"), description="Flat white",
            category=self.mine,
            category_source=Transaction.CATEGORY_SOURCE_USER)

    def test_archiving_hides_it_from_new_assignments(self):
        self._post("finance:category_archive", self.mine.pk)
        offered = [c["name"] for c in
                   svc.category_choices(self.user)["categories"]]
        self.assertNotIn("Coffee", offered)

    def test_archiving_does_not_invalidate_the_transaction_using_it(self):
        self._post("finance:category_archive", self.mine.pk)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.category_id, self.mine.pk)
        self.assertEqual(self.txn.category_source, Transaction.CATEGORY_SOURCE_USER)

    def test_the_transaction_still_shows_its_archived_category(self):
        self._post("finance:category_archive", self.mine.pk)
        self.txn.refresh_from_db()
        options = svc.category_choices(self.user, self.txn)
        self.assertEqual(options["current_id"], self.mine.pk)
        entry = next(c for c in options["categories"] if c["id"] == self.mine.pk)
        self.assertTrue(entry["archived"])

    def test_archived_categories_are_listed_on_the_page(self):
        self._post("finance:category_archive", self.mine.pk)
        response = self.client.get(reverse("finance:category_list"))
        self.assertContains(response, "archived-category")
        self.assertContains(response, "Coffee")

    def test_restore_brings_it_back(self):
        self._post("finance:category_archive", self.mine.pk)
        self._post("finance:category_restore", self.mine.pk)
        self.mine.refresh_from_db()
        self.assertTrue(self.mine.is_active)
        self.assertIn("Coffee",
                      [c["name"] for c in svc.category_choices(self.user)["categories"]])

    def test_an_archived_name_cannot_be_re_created_as_a_second_row(self):
        """The archived row still holds the name, at the DATABASE level.

        `unique_user_category_name` is `(user, name, category_type)` and does not
        exclude archived rows, so a second "Coffee" cannot exist even while the
        first is archived. That is stricter than the restore-time guard in
        `restore_personal_category`, which is therefore defence in depth rather
        than the thing standing between the user and a duplicate.
        """
        from django.db import IntegrityError, transaction as db_transaction

        self._post("finance:category_archive", self.mine.pk)
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                TransactionCategory.objects.create(
                    user=self.user, name="Coffee", category_type="expense")

    def test_typing_the_archived_name_again_revives_it_instead_of_failing(self):
        """What a person actually experiences: they get their category back."""
        self._post("finance:category_archive", self.mine.pk)
        self._post("finance:category_create", name="coffee",
                   category_type="expense")

        self.mine.refresh_from_db()
        self.assertTrue(self.mine.is_active)
        self.assertEqual(
            TransactionCategory.objects.filter(user=self.user,
                                               name__iexact="coffee").count(), 1)

    def test_archiving_twice_is_harmless(self):
        self._post("finance:category_archive", self.mine.pk)
        self._post("finance:category_archive", self.mine.pk)
        self.mine.refresh_from_db()
        self.assertFalse(self.mine.is_active)


class DeleteTests(ManageBase):
    def test_an_unused_category_can_be_deleted(self):
        self._post("finance:category_delete", self.mine.pk)
        self.assertFalse(
            TransactionCategory.objects.filter(pk=self.mine.pk).exists())

    def test_a_category_used_by_a_transaction_is_not_deleted(self):
        Transaction.objects.create(
            user=self.user, account=self.account, date=date(2026, 8, 20),
            amount=Decimal("-4.50"), description="Flat white", category=self.mine)
        response = self._post("finance:category_delete", self.mine.pk)
        self.assertTrue(TransactionCategory.objects.filter(pk=self.mine.pk).exists())
        self.assertContains(response, "Archive it instead")

    def test_a_category_used_by_a_BUDGET_is_not_deleted(self):
        """Budget.category CASCADES — deleting would silently destroy the budget."""
        Budget.objects.create(
            user=self.user, category=self.mine, month=date(2026, 8, 1),
            budgeted_amount=Decimal("50.00"))
        self._post("finance:category_delete", self.mine.pk)
        self.assertTrue(TransactionCategory.objects.filter(pk=self.mine.pk).exists())
        self.assertEqual(Budget.objects.filter(category=self.mine).count(), 1)

    def test_the_delete_button_is_hidden_while_a_category_is_in_use(self):
        Transaction.objects.create(
            user=self.user, account=self.account, date=date(2026, 8, 20),
            amount=Decimal("-4.50"), description="Flat white", category=self.mine)
        response = self.client.get(reverse("finance:category_list"))
        self.assertContains(response, "In use — archive instead")
        self.assertNotContains(
            response, reverse("finance:category_delete", args=[self.mine.pk]))


class SystemCategoryProtectionTests(ManageBase):
    def test_a_system_category_cannot_be_renamed(self):
        response = self.client.post(
            reverse("finance:category_rename", args=[self.system.pk]),
            data={"name": "Hijacked"})
        self.assertEqual(response.status_code, 404)
        self.system.refresh_from_db()
        self.assertEqual(self.system.name, "Groceries")

    def test_a_system_category_cannot_be_archived_or_deleted(self):
        for route in ("finance:category_archive", "finance:category_delete"):
            with self.subTest(route=route):
                response = self.client.post(reverse(route, args=[self.system.pk]))
                self.assertEqual(response.status_code, 404)
        self.system.refresh_from_db()
        self.assertTrue(self.system.is_active)

    def test_the_service_refuses_a_system_category_directly(self):
        with self.assertRaises(ValidationError):
            svc.rename_personal_category(self.user, self.system, "Nope")
        with self.assertRaises(ValidationError):
            svc.archive_personal_category(self.user, self.system)

    def test_system_categories_are_shown_as_read_only(self):
        response = self.client.get(reverse("finance:category_list"))
        self.assertContains(response, "system-category")
        self.assertContains(response, "not editable")


class OwnershipTests(ManageBase):
    def setUp(self):
        super().setUp()
        self.theirs = TransactionCategory.objects.create(
            user=self.other, name="Their Private Thing", category_type="expense")

    def test_another_users_category_is_not_listed(self):
        response = self.client.get(reverse("finance:category_list"))
        self.assertNotContains(response, "Their Private Thing")

    def test_another_users_category_cannot_be_renamed(self):
        response = self.client.post(
            reverse("finance:category_rename", args=[self.theirs.pk]),
            data={"name": "Taken"})
        self.assertEqual(response.status_code, 404)
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.name, "Their Private Thing")

    def test_another_users_category_cannot_be_archived_or_deleted(self):
        for route in ("finance:category_archive", "finance:category_delete",
                      "finance:category_restore"):
            with self.subTest(route=route):
                response = self.client.post(reverse(route, args=[self.theirs.pk]))
                self.assertEqual(response.status_code, 404)
        self.assertTrue(TransactionCategory.objects.filter(pk=self.theirs.pk).exists())

    def test_the_service_refuses_a_foreign_category_directly(self):
        with self.assertRaises(ValidationError):
            svc.rename_personal_category(self.user, self.theirs, "Nope")

    def test_two_users_may_hold_the_same_personal_name(self):
        TransactionCategory.objects.create(
            user=self.other, name="Coffee", category_type="expense")
        self.assertEqual(
            TransactionCategory.objects.filter(name="Coffee").count(), 2)


class AuthorizationTests(ManageBase):
    def test_anonymous_cannot_reach_management(self):
        self.client.logout()
        for route, args in (("finance:category_create", []),
                            ("finance:category_rename", [self.mine.pk])):
            with self.subTest(route=route):
                response = self.client.post(reverse(route, args=args),
                                            data={"name": "X"})
                self.assertIn(response.status_code, (302, 403))

    def test_a_user_without_finance_capability_is_refused(self):
        prefs = self.user.preferences
        prefs.finances_enabled = False
        prefs.save(update_fields=["finances_enabled"])
        response = self.client.post(
            reverse("finance:category_rename", args=[self.mine.pk]),
            data={"name": "Nope"})
        self.assertEqual(response.status_code, 403)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.name, "Coffee")

    def test_the_categories_page_itself_requires_the_capability(self):
        prefs = self.user.preferences
        prefs.finances_enabled = False
        prefs.save(update_fields=["finances_enabled"])
        response = self.client.get(reverse("finance:category_list"))
        self.assertIn(response.status_code, (302, 403))

    def test_management_needs_no_staff_flag(self):
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self._post("finance:category_create", name="Plain User Category",
                   category_type="expense")
        self.assertTrue(TransactionCategory.objects.filter(
            user=self.user, name="Plain User Category").exists())

    def test_every_management_route_rejects_GET(self):
        for route, args in (("finance:category_create", []),
                            ("finance:category_rename", [self.mine.pk]),
                            ("finance:category_archive", [self.mine.pk]),
                            ("finance:category_restore", [self.mine.pk]),
                            ("finance:category_delete", [self.mine.pk])):
            with self.subTest(route=route):
                self.assertEqual(
                    self.client.get(reverse(route, args=args)).status_code, 405)


class AuditTests(ManageBase):
    def test_each_management_decision_is_audited(self):
        self._post("finance:category_create", name="Books", category_type="expense")
        books = TransactionCategory.objects.get(user=self.user, name="Books")
        self._post("finance:category_rename", books.pk, name="Reading")
        self._post("finance:category_archive", books.pk)
        self._post("finance:category_restore", books.pk)

        entries = FinanceAuditLog.objects.filter(
            user=self.user, entity_type="transaction_category").order_by("id")
        operations = [e.details.get("operation") for e in entries]
        self.assertIn("rename", operations)
        self.assertIn("archive", operations)
        self.assertIn("restore", operations)
        self.assertTrue(any(e.action == "create" for e in entries))

    def test_a_rename_records_both_sides(self):
        self._post("finance:category_rename", self.mine.pk, name="Espresso")
        entry = FinanceAuditLog.objects.filter(
            user=self.user, entity_type="transaction_category").order_by("-id").first()
        self.assertEqual(entry.details["from"], "Coffee")
        self.assertEqual(entry.details["to"], "Espresso")

    def test_deleting_is_audited_before_the_row_disappears(self):
        self._post("finance:category_delete", self.mine.pk)
        entry = FinanceAuditLog.objects.filter(
            user=self.user, entity_type="transaction_category",
            action="delete").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.details["name"], "Coffee")

    def test_audit_failure_never_blocks_the_user(self):
        from unittest.mock import patch
        with patch("apps.finance.security.FinanceAuditLogger.log",
                   side_effect=RuntimeError("audit down")):
            svc.archive_personal_category(self.user, self.mine)
        self.mine.refresh_from_db()
        self.assertFalse(self.mine.is_active)


class SharedAuthorityTests(ManageBase):
    """The page and the inline picker must be two doors into one model."""

    def test_both_surfaces_use_the_same_service_module(self):
        import inspect
        from apps.finance import views_categories
        source = inspect.getsource(views_categories)
        self.assertIn("category_assignment", source)
        for function in ("create_personal_category", "rename_personal_category",
                         "archive_personal_category"):
            self.assertIn(f"categories.{function}", source)

    def test_the_page_and_the_picker_offer_the_same_categories(self):
        self._post("finance:category_create", name="Books", category_type="expense")
        page = self.client.get(reverse("finance:category_list"))
        picker = [c["name"] for c in svc.category_choices(self.user)["categories"]]
        self.assertContains(page, "Books")
        self.assertIn("Books", picker)

    def test_archiving_from_the_page_changes_what_the_picker_offers(self):
        self._post("finance:category_archive", self.mine.pk)
        self.assertNotIn("Coffee",
                         [c["name"] for c in svc.category_choices(self.user)["categories"]])

    def test_there_is_no_second_category_model(self):
        from apps.finance import models
        names = [n for n in dir(models) if "Category" in n]
        self.assertEqual(sorted(names), ["TransactionCategory"])


class ResponsiveAndAccessibilityTests(ManageBase):
    def _css(self):
        return (Path(settings.BASE_DIR) / "templates" / "finance" /
                "category_list.html").read_text(encoding="utf-8")

    def test_touch_targets_and_font_size_meet_the_mobile_rules(self):
        css = self._css()
        self.assertIn("min-height: 44px", css)
        self.assertIn("font-size: 16px", css)

    def test_a_mobile_breakpoint_is_declared(self):
        self.assertIn("@media (max-width: 480px)", self._css())

    def test_no_fixed_layout_widths(self):
        """No pixel LAYOUT widths at 375px.

        `.sr-only` (the visually-hidden clip) and `.category-color` (a 12px colour
        swatch that is decoration, not layout, and already `flex-shrink: 0`) are
        excluded deliberately — neither can cause horizontal overflow.
        """
        css = self._css()
        layout = re.sub(r"\.(sr-only|category-color)\s*\{[^}]*\}", "", css,
                        flags=re.S)
        self.assertEqual(re.findall(r"[^-]width:\s*\d+px", layout), [])

    def test_every_rename_field_is_labelled(self):
        response = self.client.get(reverse("finance:category_list"))
        body = response.content.decode()
        self.assertIn(f'for="cat-name-{self.mine.pk}"', body)
        self.assertIn(f'id="cat-name-{self.mine.pk}"', body)

    def test_the_create_form_is_labelled(self):
        body = self.client.get(reverse("finance:category_list")).content.decode()
        self.assertIn('for="cat-new-name"', body)
        self.assertIn('id="cat-new-name"', body)

    def test_no_inline_event_handlers(self):
        markup = self._css()
        for handler in ("onclick=", "onchange=", "onsubmit=", "oninput="):
            with self.subTest(handler=handler):
                self.assertNotIn(handler, markup)

    def test_every_mutating_form_carries_csrf(self):
        markup = self._css()
        self.assertEqual(markup.count("<form"), markup.count("csrf_token"))
