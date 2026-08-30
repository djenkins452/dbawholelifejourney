# ==============================================================================
# File: apps/finance/tests/test_finance_presentation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: How Finance renders money, and where each account belongs.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Two presentation fixes, both from the live dashboard.

Money was rendering as `$46968.05` and — worse — `$-396178.58`, a minus stranded
between the currency symbol and the digits. And Chase and First Horizon accounts sat
in one undifferentiated list.

Nothing here changes a stored value, a sign, a calculation, or anything Plaid sends;
these assert only what a person sees.
"""
import glob
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from apps.finance.models import BankConnection, FinancialAccount
from apps.finance.services.account_grouping import (
    MANUAL_GROUP, group_accounts_by_institution, institution_name_for)
from apps.finance.templatetags.finance_format import money, money_abs, money_signed
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


class MoneyFilterTests(TestCase):
    """The exact strings from the report."""

    def test_the_reported_values_now_render_correctly(self):
        self.assertEqual(money(Decimal("46968.05")), "$46,968.05")
        self.assertEqual(money(Decimal("443146.63")), "$443,146.63")
        self.assertEqual(money(Decimal("-396178.58")), "-$396,178.58")
        self.assertEqual(money(Decimal("0")), "$0.00")

    def test_the_minus_never_sits_after_the_dollar_sign(self):
        for value in ("-1", "-0.01", "-396178.58", "-1000000"):
            with self.subTest(value=value):
                self.assertNotIn("$-", money(Decimal(value)))
                self.assertTrue(money(Decimal(value)).startswith("-$"))

    def test_thousands_separators_and_exactly_two_decimals(self):
        self.assertEqual(money(Decimal("1234567.891")), "$1,234,567.89")
        self.assertEqual(money(Decimal("1000")), "$1,000.00")
        self.assertEqual(money(Decimal("999")), "$999.00")
        self.assertEqual(money(Decimal("0.005")), "$0.01")
        self.assertEqual(money(Decimal("5")), "$5.00")

    def test_it_accepts_what_templates_actually_hand_it(self):
        self.assertEqual(money(46968.05), "$46,968.05")
        self.assertEqual(money("443146.63"), "$443,146.63")
        self.assertEqual(money(0), "$0.00")

    def test_a_missing_value_is_not_dressed_up_as_zero(self):
        """No balance and a zero balance are different facts."""
        self.assertEqual(money(None), "—")
        self.assertEqual(money(""), "—")
        self.assertEqual(money("not a number"), "—")

    def test_money_signed_shows_direction(self):
        self.assertEqual(money_signed(Decimal("3585.85")), "+$3,585.85")
        self.assertEqual(money_signed(Decimal("-2127.31")), "-$2,127.31")
        self.assertEqual(money_signed(Decimal("0")), "$0.00")

    def test_money_abs_is_magnitude_only(self):
        self.assertEqual(money_abs(Decimal("-396178.58")), "$396,178.58")
        self.assertEqual(money_abs(Decimal("396178.58")), "$396,178.58")

    def test_no_raw_decimal_ever_leaks(self):
        for value in (Decimal("1.5"), Decimal("-1.5"), Decimal("1E+2")):
            with self.subTest(value=value):
                self.assertNotIn("Decimal", money(value))
                self.assertNotIn("E+", money(value))

    def test_it_works_as_a_template_filter(self):
        rendered = Template(
            "{% load finance_format %}{{ a|money }}|{{ b|money }}|{{ c|money_signed }}"
        ).render(Context({"a": Decimal("46968.05"), "b": Decimal("-396178.58"),
                          "c": Decimal("3585.85")}))
        self.assertEqual(rendered, "$46,968.05|-$396,178.58|+$3,585.85")


class TemplateAuditTests(TestCase):
    """No Finance template may format money by hand any more."""

    def _templates(self):
        base = Path(settings.BASE_DIR) / "templates" / "finance"
        return sorted(glob.glob(str(base / "*.html")) +
                      glob.glob(str(base / "components" / "*.html")))

    def test_no_template_renders_a_bare_dollar_variable(self):
        offenders = []
        for path in self._templates():
            body = Path(path).read_text(encoding="utf-8")
            for match in re.findall(r"\$\{\{[^}]*\}\}", body):
                offenders.append(f"{Path(path).name}: {match}")
        self.assertEqual(offenders, [],
                         "use |money / |money_signed / |money_abs instead")

    def test_the_sign_stripping_hack_is_gone(self):
        for path in self._templates():
            body = Path(path).read_text(encoding="utf-8")
            with self.subTest(template=Path(path).name):
                self.assertNotIn('slice:"1:"', body,
                                 "chopping the minus off a rendered string is a "
                                 "formatting decision hidden in a string operation")

    def test_every_template_using_the_filters_loads_them(self):
        for path in self._templates():
            body = Path(path).read_text(encoding="utf-8")
            if re.search(r"\|money(_abs|_signed)?[\s|}]", body):
                with self.subTest(template=Path(path).name):
                    self.assertIn("{% load finance_format %}", body)

    def test_no_literal_sign_sits_in_front_of_a_signed_amount(self):
        """`-{{ x|money }}` would render `--$5` the moment x goes negative."""
        offenders = []
        for path in self._templates():
            body = Path(path).read_text(encoding="utf-8")
            for match in re.findall(r"[+-]\{\{[^}]*\|money\s*\}\}", body):
                offenders.append(f"{Path(path).name}: {match}")
        self.assertEqual(offenders, [], "pair a literal sign with |money_abs")


class GroupingTests(TestCase):
    def setUp(self):
        self.user = _usable(User.objects.create_user(
            email="group@example.com", password="pw"))
        self.chase = BankConnection.objects.create(
            user=self.user, institution_name="Chase", item_id="item-chase",
            connection_status=BankConnection.STATUS_ACTIVE)
        self.horizon = BankConnection.objects.create(
            user=self.user, institution_name="First Horizon", item_id="item-fh",
            connection_status=BankConnection.STATUS_ACTIVE)

    def _account(self, name, connection=None, order=0, balance="100.00"):
        return FinancialAccount.objects.create(
            user=self.user, name=name, bank_connection=connection,
            sort_order=order, current_balance=Decimal(balance))

    def test_accounts_group_under_their_institution(self):
        self._account("Chase Checking", self.chase)
        self._account("Chase Savings", self.chase)
        self._account("FH Checking", self.horizon)

        groups = group_accounts_by_institution(
            FinancialAccount.objects.filter(user=self.user).order_by("sort_order", "name"))
        names = [g["institution"] for g in groups]
        self.assertEqual(names, ["Chase", "First Horizon"])
        self.assertEqual(len(groups[0]["accounts"]), 2)
        self.assertEqual(len(groups[1]["accounts"]), 1)

    def test_institutions_sort_by_display_name(self):
        zeta = BankConnection.objects.create(
            user=self.user, institution_name="Zeta Bank", item_id="item-z",
            connection_status=BankConnection.STATUS_ACTIVE)
        alpha = BankConnection.objects.create(
            user=self.user, institution_name="alpha credit union", item_id="item-a",
            connection_status=BankConnection.STATUS_ACTIVE)
        self._account("Z", zeta)
        self._account("A", alpha)
        self._account("C", self.chase)

        names = [g["institution"] for g in group_accounts_by_institution(
            FinancialAccount.objects.filter(user=self.user))]
        self.assertEqual(names, ["alpha credit union", "Chase", "Zeta Bank"])

    def test_unlinked_accounts_land_in_a_labelled_manual_group(self):
        self._account("Cash Jar", None)
        groups = group_accounts_by_institution(
            FinancialAccount.objects.filter(user=self.user))
        self.assertEqual(groups[0]["institution"], MANUAL_GROUP)
        self.assertTrue(groups[0]["is_manual"])

    def test_the_manual_group_sorts_last(self):
        self._account("Cash Jar", None)
        self._account("Chase Checking", self.chase)
        self._account("FH Checking", self.horizon)
        names = [g["institution"] for g in group_accounts_by_institution(
            FinancialAccount.objects.filter(user=self.user))]
        self.assertEqual(names, ["Chase", "First Horizon", MANUAL_GROUP])

    def test_a_connection_with_a_blank_institution_is_treated_as_manual(self):
        blank = BankConnection.objects.create(
            user=self.user, institution_name="   ", item_id="item-blank",
            connection_status=BankConnection.STATUS_ACTIVE)
        self._account("Mystery", blank)
        groups = group_accounts_by_institution(
            FinancialAccount.objects.filter(user=self.user))
        self.assertEqual(groups[0]["institution"], MANUAL_GROUP)

    def test_every_account_appears_exactly_once(self):
        made = [self._account(f"Chase {i}", self.chase, order=i) for i in range(3)]
        made += [self._account(f"FH {i}", self.horizon, order=i) for i in range(2)]
        made += [self._account("Manual", None)]

        groups = group_accounts_by_institution(
            FinancialAccount.objects.filter(user=self.user))
        seen = [a.pk for g in groups for a in g["accounts"]]
        self.assertEqual(sorted(seen), sorted(a.pk for a in made))
        self.assertEqual(len(seen), len(set(seen)))

    def test_order_within_a_group_is_preserved_not_re_decided(self):
        self._account("Zebra", self.chase, order=1)
        self._account("Apple", self.chase, order=2)
        ordered = FinancialAccount.objects.filter(
            user=self.user).order_by("sort_order", "name")
        groups = group_accounts_by_institution(ordered)
        self.assertEqual([a.name for a in groups[0]["accounts"]], ["Zebra", "Apple"])

    def test_institution_is_never_inferred_from_the_account_name(self):
        """A name saying "Chase" does not make it a Chase account."""
        account = self._account("Chase-looking manual account", None)
        self.assertIsNone(institution_name_for(account))
        groups = group_accounts_by_institution([account])
        self.assertEqual(groups[0]["institution"], MANUAL_GROUP)

    def test_institutions_are_never_merged(self):
        self._account("A", self.chase)
        self._account("B", self.horizon)
        groups = group_accounts_by_institution(
            FinancialAccount.objects.filter(user=self.user))
        self.assertEqual(len(groups), 2)


class RenderedSurfaceTests(TestCase):
    def setUp(self):
        self.user = _usable(User.objects.create_user(
            email="render@example.com", password="pw"))
        chase = BankConnection.objects.create(
            user=self.user, institution_name="Chase", item_id="item-chase",
            connection_status=BankConnection.STATUS_ACTIVE)
        horizon = BankConnection.objects.create(
            user=self.user, institution_name="First Horizon", item_id="item-fh",
            connection_status=BankConnection.STATUS_ACTIVE)
        FinancialAccount.objects.create(
            user=self.user, name="Chase Checking", bank_connection=chase,
            account_type="checking", current_balance=Decimal("46968.05"))
        FinancialAccount.objects.create(
            user=self.user, name="FH Mortgage", bank_connection=horizon,
            account_type="mortgage", current_balance=Decimal("-396178.58"))
        FinancialAccount.objects.create(
            user=self.user, name="Cash Jar", account_type="cash",
            current_balance=Decimal("0.00"))
        self.client.force_login(self.user)

    def test_the_accounts_page_shows_institution_headings(self):
        body = self.client.get(reverse("finance:account_list")).content.decode()
        self.assertIn("Chase", body)
        self.assertIn("First Horizon", body)
        self.assertIn(MANUAL_GROUP, body)
        self.assertEqual(body.count('data-testid="institution-group"'), 3)

    def test_the_dashboard_shows_institution_headings(self):
        body = self.client.get(reverse("finance:dashboard")).content.decode()
        self.assertIn('data-testid="institution-group"', body)
        self.assertIn("Chase", body)
        self.assertIn("First Horizon", body)

    def test_currency_renders_formatted_on_both_surfaces(self):
        for route in ("finance:account_list", "finance:dashboard"):
            with self.subTest(route=route):
                body = self.client.get(reverse(route)).content.decode()
                self.assertIn("$46,968.05", body)
                self.assertIn("-$396,178.58", body)
                self.assertNotIn("$-396,178.58", body)
                self.assertNotIn("$46968.05", body)

    def test_zero_renders_as_zero_not_as_a_dash(self):
        body = self.client.get(reverse("finance:account_list")).content.decode()
        self.assertIn("$0.00", body)

    def test_every_account_appears_exactly_once_on_the_page(self):
        body = self.client.get(reverse("finance:account_list")).content.decode()
        self.assertEqual(body.count('data-testid="account-card"'), 3)
        for name in ("Chase Checking", "FH Mortgage", "Cash Jar"):
            with self.subTest(name=name):
                self.assertEqual(body.count(f">{name}<"), 1)

    def test_account_links_types_and_actions_survive_the_regrouping(self):
        body = self.client.get(reverse("finance:account_list")).content.decode()
        account = FinancialAccount.objects.get(user=self.user, name="Chase Checking")
        self.assertIn(reverse("finance:account_detail", args=[account.pk]), body)
        self.assertIn(reverse("finance:account_update", args=[account.pk]), body)
        self.assertIn("Checking", body)

    def test_totals_span_every_account_not_one_institution(self):
        response = self.client.get(reverse("finance:account_list"))
        self.assertEqual(response.context["total_assets"], Decimal("46968.05"))
        self.assertEqual(response.context["total_liabilities"], Decimal("396178.58"))
        self.assertEqual(response.context["net_worth"],
                         Decimal("46968.05") - Decimal("396178.58"))

    def test_no_provider_identifier_is_exposed(self):
        for route in ("finance:account_list", "finance:dashboard"):
            with self.subTest(route=route):
                body = self.client.get(reverse(route)).content.decode()
                self.assertNotIn("item-chase", body)
                self.assertNotIn("item-fh", body)

    def test_grouping_does_not_cost_a_query_per_account(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as few:
            self.client.get(reverse("finance:account_list"))
        baseline = len(few.captured_queries)

        chase = BankConnection.objects.get(item_id="item-chase")
        for i in range(20):
            FinancialAccount.objects.create(
                user=self.user, name=f"Extra {i}", bank_connection=chase,
                account_type="checking", current_balance=Decimal("1.00"))

        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse("finance:account_list"))
        self.assertLessEqual(len(many.captured_queries), baseline + 2,
                             "select_related should keep this flat")


class ResponsiveTests(TestCase):
    def _css(self, name):
        return (Path(settings.BASE_DIR) / "templates" / "finance" /
                name).read_text(encoding="utf-8")

    def test_both_surfaces_declare_a_mobile_breakpoint(self):
        for name in ("account_list.html", "dashboard.html"):
            with self.subTest(template=name):
                self.assertIn("@media (max-width: 480px)", self._css(name))

    def test_grouped_headings_stack_at_phone_width(self):
        self.assertIn("flex-direction: column", self._css("account_list.html"))

    def test_account_actions_stay_tappable_on_mobile(self):
        self.assertIn("min-height: 44px", self._css("account_list.html"))
