# ==============================================================================
# File: apps/finance/tests/test_category_picker_surfaces.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The picker is ONE reusable control, on every editable surface.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Rendering, reuse, query cost, CSP and accessibility for the category picker.

The point of a shared component is that it cannot drift: these tests fail if a surface
grows its own copy of the markup, if the control stops being keyboard-reachable, or if
adding rows starts costing a query each.
"""
import re
from datetime import date
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.finance.models import (FinancialAccount, Transaction, TransactionCategory)
from apps.users.models import User

PARTIAL = "finance/components/category_picker.html"
SURFACES = ("finance/transaction_list.html",
            "finance/transaction_detail.html",
            "finance/attribution_review.html")


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


class SurfaceBase(TestCase):
    def setUp(self):
        self.user = _enable_finance(
            User.objects.create_user(email="surf@example.com", password="pw"))
        self.account = FinancialAccount.objects.create(user=self.user, name="Checking")
        self.system = TransactionCategory.objects.create(
            name="Groceries", category_type="expense", is_system=True)
        self.txn = Transaction.objects.create(
            user=self.user, account=self.account, date=date(2026, 8, 20),
            amount=-42, description="Corner shop", category=self.system)
        self.client.force_login(self.user)


class ReuseContractTests(TestCase):
    """One component, included by every surface — never re-implemented."""

    def _template(self, name):
        for directory in [Path(d) for d in settings.TEMPLATES[0]["DIRS"]]:
            candidate = directory / name
            if candidate.exists():
                return candidate.read_text(encoding="utf-8")
        raise AssertionError(f"template not found: {name}")

    def test_every_editable_surface_includes_the_shared_partial(self):
        for surface in SURFACES:
            with self.subTest(surface=surface):
                self.assertIn(PARTIAL, self._template(surface))

    def test_no_surface_reimplements_the_control(self):
        """`data-cat-picker` may be authored in exactly one place."""
        for surface in SURFACES:
            with self.subTest(surface=surface):
                self.assertNotIn("data-cat-picker", self._template(surface),
                                 "include the shared partial instead of re-authoring it")

    def test_the_behaviour_lives_in_one_shared_script(self):
        assets = self._template("finance/components/category_picker_assets.html")
        self.assertIn("js/finance/category_picker.js", assets)
        for surface in SURFACES:
            with self.subTest(surface=surface):
                self.assertIn("category_picker_assets.html", self._template(surface))


class CspComplianceTests(TestCase):
    """Nonce-based CSP silently drops inline handlers — so there must be none."""

    def test_partial_has_no_inline_event_handlers(self):
        for name in (PARTIAL, "finance/components/category_picker_assets.html"):
            path = Path(settings.BASE_DIR) / "templates" / name
            markup = path.read_text(encoding="utf-8")
            for handler in ("onclick=", "onchange=", "onsubmit=", "onkeydown=",
                            "oninput=", "onfocus="):
                with self.subTest(template=name, handler=handler):
                    self.assertNotIn(handler, markup)

    def test_shared_assets_carry_the_nonce(self):
        markup = (Path(settings.BASE_DIR) / "templates" /
                  "finance/components/category_picker_assets.html").read_text()
        self.assertIn('<style nonce="{{ csp_nonce }}">', markup)
        self.assertIn('nonce="{{ csp_nonce }}"', markup)

    def test_script_uses_addeventlistener_not_inline_wiring(self):
        js = (Path(settings.BASE_DIR) / "static" / "js" / "finance" /
              "category_picker.js").read_text()
        self.assertIn("addEventListener", js)


class RenderingTests(SurfaceBase):
    def test_transaction_list_renders_a_picker_per_row(self):
        response = self.client.get(reverse("finance:transaction_list"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("data-cat-picker", body)
        self.assertIn("Create New Category", body)
        self.assertIn(f'data-transaction-id="{self.txn.pk}"', body)

    def test_transaction_detail_renders_the_picker(self):
        response = self.client.get(
            reverse("finance:transaction_detail", args=[self.txn.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("data-cat-picker", response.content.decode())

    def test_the_current_category_is_preselected(self):
        response = self.client.get(
            reverse("finance:transaction_detail", args=[self.txn.pk]))
        body = response.content.decode()
        self.assertRegex(body, rf'<option value="{self.system.pk}"[^>]*selected')

    def test_create_new_option_is_inside_the_dropdown(self):
        response = self.client.get(
            reverse("finance:transaction_detail", args=[self.txn.pk]))
        body = response.content.decode()
        self.assertIn('value="__new__"', body)

    def test_another_users_category_never_reaches_the_page(self):
        other = _enable_finance(
            User.objects.create_user(email="nope@example.com", password="pw"))
        TransactionCategory.objects.create(
            user=other, name="Their Secret Project", category_type="expense")
        response = self.client.get(reverse("finance:transaction_list"))
        self.assertNotIn("Their Secret Project", response.content.decode())


class QueryCostTests(SurfaceBase):
    """A picker per row must not mean a query per row."""

    def test_more_rows_do_not_cost_more_category_queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def render():
            return self.client.get(reverse("finance:transaction_list"))

        with CaptureQueriesContext(connection) as few:
            render()
        baseline = len([q for q in few.captured_queries
                        if "financecategory" in q["sql"].lower()
                        or "transactioncategory" in q["sql"].lower()])

        for i in range(25):
            Transaction.objects.create(
                user=self.user, account=self.account, date=date(2026, 8, 20),
                amount=-5, description=f"Item {i}", category=self.system)

        with CaptureQueriesContext(connection) as many:
            render()
        grown = len([q for q in many.captured_queries
                     if "financecategory" in q["sql"].lower()
                     or "transactioncategory" in q["sql"].lower()])

        self.assertLessEqual(grown, baseline + 1,
                             "category options must be fetched once per page")


class AccessibilityAndResponsiveTests(SurfaceBase):
    def test_each_control_has_a_programmatic_label(self):
        response = self.client.get(
            reverse("finance:transaction_detail", args=[self.txn.pk]))
        body = response.content.decode()
        self.assertIn(f'for="cat-select-{self.txn.pk}"', body)
        self.assertIn(f'id="cat-select-{self.txn.pk}"', body)

    def test_the_new_name_field_is_labelled_too(self):
        response = self.client.get(
            reverse("finance:transaction_detail", args=[self.txn.pk]))
        body = response.content.decode()
        self.assertIn(f'for="cat-new-{self.txn.pk}"', body)
        self.assertIn(f'id="cat-new-{self.txn.pk}"', body)

    def test_status_is_announced_to_screen_readers(self):
        response = self.client.get(
            reverse("finance:transaction_detail", args=[self.txn.pk]))
        body = response.content.decode()
        self.assertIn('role="status"', body)
        self.assertIn('aria-live="polite"', body)

    def test_it_is_a_native_select_so_keyboard_and_mobile_work(self):
        markup = (Path(settings.BASE_DIR) / "templates" / PARTIAL).read_text()
        self.assertIn("<select", markup)
        self.assertNotIn('role="listbox"', markup,
                         "a bespoke listbox would have to re-earn native a11y")

    def test_enter_and_escape_are_handled_without_a_mouse(self):
        js = (Path(settings.BASE_DIR) / "static" / "js" / "finance" /
              "category_picker.js").read_text()
        self.assertIn('"Enter"', js)
        self.assertIn('"Escape"', js)

    def test_touch_targets_and_font_size_meet_the_mobile_rules(self):
        css = (Path(settings.BASE_DIR) / "templates" /
               "finance/components/category_picker_assets.html").read_text()
        self.assertIn("min-height: 44px", css)
        self.assertIn("font-size: 16px", css)

    def test_a_mobile_breakpoint_is_declared(self):
        css = (Path(settings.BASE_DIR) / "templates" /
               "finance/components/category_picker_assets.html").read_text()
        self.assertIn("@media (max-width: 480px)", css)
        self.assertNotIn("width: 100px", css)

    def test_no_fixed_widths_that_would_break_at_375px(self):
        """No pixel LAYOUT widths — CLAUDE.md's rule for narrow screens.

        `.sr-only` is excluded deliberately: its `width: 1px` is the standard
        visually-hidden clip, which keeps the labels reachable by screen readers
        without occupying layout. Removing it would trade accessibility for a rule
        that exists to protect layout.
        """
        css = (Path(settings.BASE_DIR) / "templates" /
               "finance/components/category_picker_assets.html").read_text()
        layout_css = re.sub(r"\.sr-only\s*\{[^}]*\}", "", css, flags=re.S)
        fixed = re.findall(r"[^-]width:\s*\d+px", layout_css)
        self.assertEqual(fixed, [], f"fixed widths break narrow screens: {fixed}")

    def test_the_visually_hidden_helper_is_the_standard_clip(self):
        css = (Path(settings.BASE_DIR) / "templates" /
               "finance/components/category_picker_assets.html").read_text()
        self.assertRegex(css, r"\.sr-only\s*\{[^}]*position:\s*absolute")
        self.assertRegex(css, r"\.sr-only\s*\{[^}]*clip:")


class ScopeContractTests(TestCase):
    """This change must not have reached into ingestion or identity."""

    def test_no_merchant_rules_or_bulk_recategorisation_were_added(self):
        service = (Path(settings.BASE_DIR) / "apps" / "finance" / "services" /
                   "category_assignment.py").read_text()
        for forbidden in ("bulk_update", "filter(payee=", "update(category",
                          "merchant_rule"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, service)

    def test_the_service_never_touches_provider_or_identity_fields(self):
        service = (Path(settings.BASE_DIR) / "apps" / "finance" / "services" /
                   "category_assignment.py").read_text()
        # ASSIGNMENTS only — reading `transfer_state` to infer income/expense/transfer
        # is exactly the kind of reuse this change is supposed to do.
        for pattern in (r"\.plaid_transaction_id\s*=[^=]",
                        r"\.provider_category_\w+\s*=[^=]",
                        r"\.transfer_state\s*=[^=]",
                        r"\.last_sync_cursor\s*=[^=]"):
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, service),
                                  f"category assignment must not write {pattern}")
