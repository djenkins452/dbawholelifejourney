# ==============================================================================
# File: apps/finance/tests/test_asset_registry.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tangible assets, valuations, loan links, and the net-worth contract.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The dashboard counted the mortgage but not the house.

The contract these prove:

    net worth = financial assets + tangible values - ALL liabilities

A loan linked to an asset is explanatory. Its balance is already in liabilities, so
the aggregate must never subtract it twice — the single most likely way this feature
could produce a confidently wrong number.
"""
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction as db_transaction
from django.test import TestCase
from django.urls import reverse

from apps.finance.models import (AssetLoanLink, AssetValuation, FinanceAuditLog,
                                 FinancialAccount, TangibleAsset)
from apps.finance.services import asset_registry as registry
from apps.finance.services import valuation_providers as providers
from apps.users.models import TermsAcceptance, User

TODAY = date(2026, 8, 30)


def _usable(user):
    TermsAcceptance.objects.get_or_create(
        user=user,
        defaults={"terms_version": settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")})
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.finances_enabled = True
    prefs.save()
    return user


class AssetBase(TestCase):
    def setUp(self):
        self.user = _usable(User.objects.create_user(
            email="assets@example.com", password="pw"))
        self.other = _usable(User.objects.create_user(
            email="stranger@example.com", password="pw"))
        self.client.force_login(self.user)

    def _asset(self, name="Home", asset_type=TangibleAsset.TYPE_REAL_ESTATE,
               user=None, **kw):
        return TangibleAsset.objects.create(
            user=user or self.user, name=name, asset_type=asset_type, **kw)

    def _value(self, asset, amount, on=TODAY, **kw):
        return registry.record_valuation(
            asset.user, asset, amount=Decimal(str(amount)), effective_date=on,
            source=kw.pop("source", "manual"), **kw)

    def _account(self, name, account_type, balance, user=None):
        return FinancialAccount.objects.create(
            user=user or self.user, name=name, account_type=account_type,
            current_balance=Decimal(str(balance)))


class AssetTypeTests(AssetBase):
    def test_every_supported_type_can_be_created(self):
        for value, _label in TangibleAsset.ASSET_TYPE_CHOICES:
            with self.subTest(asset_type=value):
                asset = self._asset(name=f"Thing {value}", asset_type=value)
                self.assertEqual(asset.asset_type, value)

    def test_each_type_declares_only_the_fields_it_uses(self):
        house = self._asset(asset_type=TangibleAsset.TYPE_REAL_ESTATE)
        truck = self._asset("Truck", TangibleAsset.TYPE_VEHICLE)
        boat = self._asset("Boat", TangibleAsset.TYPE_BOAT)

        self.assertIn("street_address", house.relevant_fields)
        self.assertNotIn("vin", house.relevant_fields)
        self.assertIn("vin", truck.relevant_fields)
        self.assertNotIn("street_address", truck.relevant_fields)
        self.assertIn("hull_identification_number", boat.relevant_fields)
        self.assertNotIn("mileage", boat.relevant_fields)

    def test_the_form_omits_irrelevant_fields_entirely(self):
        from apps.finance.views_assets import TangibleAssetForm

        house = TangibleAssetForm(self.user,
                                  initial={"asset_type": TangibleAsset.TYPE_REAL_ESTATE})
        self.assertIn("street_address", house.fields)
        self.assertNotIn("vin", house.fields,
                         "a house must not be asked for a VIN — nor accept one")

        vehicle = TangibleAssetForm(self.user,
                                    initial={"asset_type": TangibleAsset.TYPE_VEHICLE})
        self.assertIn("vin", vehicle.fields)
        self.assertNotIn("street_address", vehicle.fields)

    def test_a_blank_name_is_refused_by_the_database(self):
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                TangibleAsset.objects.create(user=self.user, name="")


class SensitiveDataTests(AssetBase):
    def test_a_vin_is_masked_for_display(self):
        truck = self._asset("Truck", TangibleAsset.TYPE_VEHICLE,
                            vin="1FTFW1ET5DFC12345")
        self.assertEqual(truck.masked_vin, "••••2345")
        self.assertNotIn("1FTFW1ET5DFC", truck.masked_vin)

    def test_an_address_is_reduced_to_city_and_region(self):
        house = self._asset(street_address="12 Private Lane", city="Memphis",
                            state_region="TN", postal_code="38103")
        self.assertEqual(house.masked_address, "Memphis, TN")
        self.assertNotIn("12 Private Lane", house.masked_address)

    def test_the_detail_page_never_renders_the_full_vin_or_street(self):
        truck = self._asset("Truck", TangibleAsset.TYPE_VEHICLE,
                            vin="1FTFW1ET5DFC12345")
        house = self._asset(street_address="12 Private Lane", city="Memphis",
                            state_region="TN")
        for asset in (truck, house):
            body = self.client.get(
                reverse("finance:asset_detail", args=[asset.pk])).content.decode()
            with self.subTest(asset=asset.name):
                self.assertNotIn("1FTFW1ET5DFC12345", body)
                self.assertNotIn("12 Private Lane", body)

    def test_audit_payloads_carry_no_identifiers(self):
        truck = self._asset("Truck", TangibleAsset.TYPE_VEHICLE,
                            vin="1FTFW1ET5DFC12345")
        self._value(truck, "30000.00")
        for entry in FinanceAuditLog.objects.filter(entity_type="tangible_asset"):
            blob = str(entry.details)
            with self.subTest(entry=entry.pk):
                self.assertNotIn("1FTFW1ET5DFC12345", blob)
                self.assertNotIn("Private Lane", blob)


class ValuationTests(AssetBase):
    def test_a_manual_valuation_becomes_the_current_value(self):
        house = self._asset()
        self._value(house, "450000.00")
        self.assertEqual(registry.current_value(house), Decimal("450000.00"))

    def test_history_is_preserved_rather_than_overwritten(self):
        house = self._asset()
        self._value(house, "400000.00", on=date(2025, 1, 1))
        self._value(house, "450000.00", on=date(2026, 6, 1))

        self.assertEqual(house.valuations.filter(status="active").count(), 2)
        self.assertEqual(registry.current_value(house), Decimal("450000.00"))

    def test_the_latest_is_by_effective_date_not_entry_order(self):
        house = self._asset()
        self._value(house, "450000.00", on=date(2026, 6, 1))
        self._value(house, "400000.00", on=date(2025, 1, 1))    # entered later
        self.assertEqual(registry.current_value(house), Decimal("450000.00"))

    def test_an_unvalued_asset_is_unknown_not_zero(self):
        house = self._asset()
        self.assertIsNone(registry.current_value(house))
        self.assertIsNone(registry.net_equity(house))

    def test_a_negative_valuation_is_refused(self):
        house = self._asset()
        with self.assertRaises(ValidationError):
            self._value(house, "-1.00")

    def test_the_database_refuses_a_negative_valuation(self):
        house = self._asset()
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                AssetValuation.objects.create(
                    user=self.user, asset=house, amount=Decimal("-5"),
                    effective_date=TODAY)

    def test_valuation_age_is_reported(self):
        house = self._asset()
        self._value(house, "450000.00", on=TODAY - timedelta(days=400))
        self.assertEqual(registry.valuation_age_days(house, TODAY), 400)

    def test_age_is_none_when_unvalued(self):
        self.assertIsNone(registry.valuation_age_days(self._asset(), TODAY))

    def test_a_stale_valuation_is_flagged_on_the_page(self):
        house = self._asset()
        self._value(house, "450000.00", on=TODAY - timedelta(days=400))
        body = self.client.get(
            reverse("finance:asset_detail", args=[house.pk])).content.decode()
        self.assertIn("stale-valuation", body)

    def test_cannot_value_someone_elses_asset(self):
        theirs = self._asset("Their House", user=self.other)
        with self.assertRaises(ValidationError):
            registry.record_valuation(
                self.user, theirs, amount=Decimal("1"), effective_date=TODAY,
                source="manual")


class ProviderBoundaryTests(AssetBase):
    """No provider is connected, and the code says so honestly."""

    def test_no_provider_is_configured(self):
        self.assertEqual(providers.PROVIDERS, {})
        self.assertFalse(providers.provider_status()["any_configured"])

    def test_an_unavailable_lookup_reports_why_and_is_not_retryable(self):
        outcome = providers.fetch_estimate(self._asset())
        self.assertIsInstance(outcome, providers.ValuationUnavailable)
        self.assertFalse(outcome.retryable)
        self.assertIn("paid subscription", outcome.reason)

    def test_a_failed_refresh_leaves_the_last_valuation_intact(self):
        house = self._asset()
        self._value(house, "450000.00", on=date(2025, 1, 1))
        self.client.post(reverse("finance:asset_valuation_refresh", args=[house.pk]))

        self.assertEqual(registry.current_value(house), Decimal("450000.00"))
        self.assertEqual(house.valuations.filter(status="active").count(), 1)

    def test_a_failed_refresh_never_writes_a_zero(self):
        house = self._asset()
        self.client.post(reverse("finance:asset_valuation_refresh", args=[house.pk]))
        self.assertIsNone(registry.current_value(house))
        self.assertEqual(house.valuations.count(), 0)

    def test_a_provider_fault_is_reported_not_raised(self):
        class Exploding(providers.ValuationProvider):
            key, name = "boom", "Exploding Co"
            supported_types = (TangibleAsset.TYPE_REAL_ESTATE,)

            def estimate(self, asset):
                raise RuntimeError("upstream on fire")

        providers.PROVIDERS["boom"] = Exploding()
        try:
            outcome = providers.fetch_estimate(self._asset())
        finally:
            providers.PROVIDERS.pop("boom")
        self.assertIsInstance(outcome, providers.ValuationUnavailable)
        self.assertTrue(outcome.retryable)

    def test_a_provider_estimate_is_stored_and_labelled_as_an_estimate(self):
        house = self._asset()
        valuation = registry.record_valuation(
            self.user, house, amount=Decimal("460000"), effective_date=TODAY,
            source="provider", source_detail="Example AVM", is_estimate=True,
            range_low=Decimal("440000"), range_high=Decimal("480000"),
            confidence="medium", limitations="Not an appraisal.",
            provider_key="example")
        self.assertTrue(valuation.is_estimate)
        body = self.client.get(
            reverse("finance:asset_detail", args=[house.pk])).content.decode()
        self.assertIn("Estimate", body)

    def test_the_module_refuses_to_fabricate_a_value(self):
        """No depreciation curve, no VIN-decode-as-value."""
        source = (Path(settings.BASE_DIR) / "apps" / "finance" / "services" /
                  "valuation_providers.py").read_text()
        for forbidden in ("depreciat", "0.85 **", "* 0.85"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source.replace("depreciation curve", ""))

    def test_no_scheduled_refresh_exists(self):
        """Nothing may create recurring provider spend on its own."""
        from django.conf import settings as s
        schedule = getattr(s, "CELERY_BEAT_SCHEDULE", {}) or {}
        for name, entry in schedule.items():
            with self.subTest(task=name):
                self.assertNotIn("valuation", str(entry.get("task", "")).lower())


class LoanLinkTests(AssetBase):
    def setUp(self):
        super().setUp()
        self.house = self._asset()
        self.mortgage = self._account("Mortgage", "mortgage", "405507.93")

    def test_a_loan_can_be_linked(self):
        registry.link_loan(self.user, self.house, self.mortgage)
        self.assertEqual(registry.linked_debt(self.house), Decimal("405507.93"))

    def test_the_balance_comes_from_the_account_not_a_copy(self):
        registry.link_loan(self.user, self.house, self.mortgage)
        self.mortgage.current_balance = Decimal("400000.00")
        self.mortgage.save(update_fields=["current_balance"])
        self.assertEqual(registry.linked_debt(self.house), Decimal("400000.00"))

    def test_nothing_copies_a_balance_onto_the_link(self):
        field_names = {f.name for f in AssetLoanLink._meta.get_fields()}
        self.assertNotIn("balance", field_names)
        self.assertNotIn("amount", field_names)

    def test_the_same_loan_cannot_be_linked_twice(self):
        registry.link_loan(self.user, self.house, self.mortgage)
        with self.assertRaises(ValidationError):
            registry.link_loan(self.user, self.house, self.mortgage)

    def test_the_database_also_refuses_a_duplicate_link(self):
        registry.link_loan(self.user, self.house, self.mortgage)
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                AssetLoanLink.objects.create(
                    user=self.user, asset=self.house, account=self.mortgage)

    def test_an_asset_may_carry_several_loans(self):
        second = self._account("Home equity line", "loan", "50000.00")
        registry.link_loan(self.user, self.house, self.mortgage)
        registry.link_loan(self.user, self.house, second)
        self.assertEqual(registry.linked_debt(self.house),
                         Decimal("455507.93"))

    def test_a_cross_user_link_is_refused(self):
        theirs = self._account("Their loan", "mortgage", "1000", user=self.other)
        with self.assertRaises(ValidationError):
            registry.link_loan(self.user, self.house, theirs)

        their_asset = self._asset("Their house", user=self.other)
        with self.assertRaises(ValidationError):
            registry.link_loan(self.user, their_asset, self.mortgage)

    def test_an_asset_account_cannot_secure_an_asset(self):
        checking = self._account("Checking", "checking", "100")
        with self.assertRaises(ValidationError):
            registry.link_loan(self.user, self.house, checking)

    def test_unlinking_archives_rather_than_erasing(self):
        link = registry.link_loan(self.user, self.house, self.mortgage)
        registry.unlink_loan(self.user, link)
        link.refresh_from_db()
        self.assertEqual(link.status, "archived")
        self.assertEqual(registry.linked_debt(self.house), Decimal("0.00"))

    def test_an_archived_account_keeps_its_historical_context(self):
        registry.link_loan(self.user, self.house, self.mortgage)
        self.mortgage.archive()
        rows = registry.linked_loans(self.house)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["account_active"])

    def test_net_equity_explains_one_asset(self):
        self._value(self.house, "500000.00")
        registry.link_loan(self.user, self.house, self.mortgage)
        self.assertEqual(registry.net_equity(self.house),
                         Decimal("500000.00") - Decimal("405507.93"))


class NetWorthContractTests(AssetBase):
    """The accounting proof."""

    def setUp(self):
        super().setUp()
        self._account("Checking", "checking", "25805.45")
        self._account("Savings", "savings", "21162.60")
        self.mortgage = self._account("Mortgage", "mortgage", "405507.93")
        self._account("Card", "credit_card", "37638.70")

    def test_without_tangible_assets_the_picture_matches_todays_dashboard(self):
        b = registry.net_worth_breakdown(self.user)
        self.assertEqual(b["financial_assets"], Decimal("46968.05"))
        self.assertEqual(b["liabilities"], Decimal("443146.63"))
        self.assertEqual(b["net_worth"], Decimal("-396178.58"))

    def test_adding_the_house_completes_the_picture(self):
        house = self._asset()
        self._value(house, "500000.00")
        b = registry.net_worth_breakdown(self.user)
        self.assertEqual(b["tangible_assets"], Decimal("500000.00"))
        self.assertEqual(b["gross_assets"], Decimal("546968.05"))
        self.assertEqual(b["net_worth"], Decimal("103821.42"))

    def test_a_linked_loan_is_subtracted_exactly_once(self):
        """The whole point. Gross value in once, liability out once."""
        house = self._asset()
        self._value(house, "500000.00")
        before = registry.net_worth_breakdown(self.user)["net_worth"]

        registry.link_loan(self.user, house, self.mortgage)
        after = registry.net_worth_breakdown(self.user)["net_worth"]

        self.assertEqual(before, after,
                         "linking a loan explains an asset; it must not change "
                         "net worth, because that debt was already counted")

    def test_several_loans_on_one_asset_do_not_double_count(self):
        house = self._asset()
        self._value(house, "500000.00")
        second = self._account("HELOC", "loan", "50000.00")
        before = registry.net_worth_breakdown(self.user)["net_worth"]

        registry.link_loan(self.user, house, self.mortgage)
        registry.link_loan(self.user, house, second)
        after = registry.net_worth_breakdown(self.user)["net_worth"]
        self.assertEqual(before, after)

    def test_net_equity_is_never_summed_into_the_total(self):
        house = self._asset()
        self._value(house, "500000.00")
        registry.link_loan(self.user, house, self.mortgage)

        b = registry.net_worth_breakdown(self.user)
        equity = registry.net_equity(house)
        self.assertNotEqual(b["tangible_assets"], equity)
        self.assertEqual(b["tangible_assets"], Decimal("500000.00"),
                         "the GROSS value is what enters total assets")

    def test_an_unvalued_asset_contributes_nothing_and_is_counted_separately(self):
        self._asset("Unvalued boat", TangibleAsset.TYPE_BOAT)
        b = registry.net_worth_breakdown(self.user)
        self.assertEqual(b["tangible_assets"], Decimal("0.00"))
        self.assertEqual(b["unvalued_count"], 1)
        self.assertEqual(b["net_worth"], Decimal("-396178.58"))

    def test_an_archived_asset_leaves_the_totals_but_keeps_its_history(self):
        house = self._asset()
        self._value(house, "500000.00")
        self.assertEqual(
            registry.net_worth_breakdown(self.user)["tangible_assets"],
            Decimal("500000.00"))

        house.archive()
        b = registry.net_worth_breakdown(self.user)
        self.assertEqual(b["tangible_assets"], Decimal("0.00"))
        self.assertEqual(house.valuations.filter(status="active").count(), 1)

    def test_an_asset_excluded_from_net_worth_is_omitted(self):
        house = self._asset(include_in_net_worth=False)
        self._value(house, "500000.00")
        self.assertEqual(
            registry.net_worth_breakdown(self.user)["tangible_assets"],
            Decimal("0.00"))

    def test_the_breakdown_reconciles_to_its_own_parts(self):
        house = self._asset()
        self._value(house, "500000.00")
        boat = self._asset("Boat", TangibleAsset.TYPE_BOAT)
        self._value(boat, "35000.00")
        registry.link_loan(self.user, house, self.mortgage)

        b = registry.net_worth_breakdown(self.user)
        self.assertTrue(b["reconciles"])
        self.assertEqual(b["gross_assets"],
                         b["financial_assets"] + b["tangible_assets"])
        self.assertEqual(b["net_worth"], b["gross_assets"] - b["liabilities"])
        self.assertEqual(sum(x["total"] for x in b["tangible_by_type"]),
                         b["tangible_assets"])

    def test_the_dashboard_and_the_reconciliation_agree(self):
        house = self._asset()
        self._value(house, "500000.00")

        dash = self.client.get(reverse("finance:dashboard")).context
        rec = self.client.get(reverse("finance:net_worth_detail")).context["breakdown"]
        self.assertEqual(dash["net_worth"], rec["net_worth"])
        self.assertEqual(dash["total_assets"], rec["gross_assets"])
        self.assertEqual(dash["total_liabilities"], rec["liabilities"])


class CrudAndAccessTests(AssetBase):
    def test_an_ordinary_user_creates_an_asset(self):
        self.assertFalse(self.user.is_staff)
        self.client.post(reverse("finance:asset_create"), {
            "name": "Lake House", "asset_type": TangibleAsset.TYPE_REAL_ESTATE,
            "city": "Memphis", "state_region": "TN", "include_in_net_worth": "on"})
        self.assertTrue(TangibleAsset.objects.filter(
            user=self.user, name="Lake House").exists())

    def test_archive_and_restore(self):
        house = self._asset()
        self.client.post(reverse("finance:asset_archive", args=[house.pk]))
        house.refresh_from_db()
        self.assertEqual(house.status, "archived")

        # The Assets page links to archived assets, so the detail page must open
        # one — the default manager filters them out, which would 404.
        self.assertEqual(self.client.get(
            reverse("finance:asset_detail", args=[house.pk])).status_code, 200)

        self.client.post(reverse("finance:asset_restore", args=[house.pk]))
        house.refresh_from_db()
        self.assertEqual(house.status, "active")

    def test_delete_is_refused_when_history_exists(self):
        house = self._asset()
        self._value(house, "450000.00")
        self.client.post(reverse("finance:asset_delete", args=[house.pk]))
        self.assertTrue(TangibleAsset.objects.filter(pk=house.pk).exists())

    def test_an_asset_with_no_history_can_be_deleted(self):
        house = self._asset()
        self.client.post(reverse("finance:asset_delete", args=[house.pk]))
        self.assertFalse(TangibleAsset.objects.filter(pk=house.pk).exists())

    def test_another_user_cannot_see_or_change_an_asset(self):
        house = self._asset()
        self.client.force_login(self.other)
        for route, method in (("finance:asset_detail", "get"),
                              ("finance:asset_update", "get"),
                              ("finance:asset_archive", "post"),
                              ("finance:asset_delete", "post"),
                              ("finance:asset_valuation_add", "post")):
            with self.subTest(route=route):
                response = getattr(self.client, method)(
                    reverse(route, args=[house.pk]))
                self.assertEqual(response.status_code, 404)

    def test_another_users_assets_are_not_listed(self):
        self._asset("Their Villa", user=self.other)
        body = self.client.get(reverse("finance:asset_list")).content.decode()
        self.assertNotIn("Their Villa", body)

    def test_finance_access_is_required(self):
        prefs = self.user.preferences
        prefs.finances_enabled = False
        prefs.save(update_fields=["finances_enabled"])
        for route in ("finance:asset_list", "finance:net_worth_detail"):
            with self.subTest(route=route):
                self.assertIn(
                    self.client.get(reverse(route)).status_code, (302, 403))

    def test_mutating_routes_reject_GET(self):
        house = self._asset()
        for route in ("finance:asset_archive", "finance:asset_restore",
                      "finance:asset_delete", "finance:asset_valuation_add",
                      "finance:asset_loan_link"):
            with self.subTest(route=route):
                self.assertEqual(
                    self.client.get(reverse(route, args=[house.pk])).status_code, 405)

    def test_changes_are_audited(self):
        house = self._asset()
        self._value(house, "450000.00")
        operations = set(FinanceAuditLog.objects.filter(
            entity_type="tangible_asset").values_list("details__operation", flat=True))
        self.assertIn("valuation_added", operations)


class RenderingTests(AssetBase):
    def test_the_list_groups_by_type_and_uses_the_shared_formatter(self):
        house = self._asset()
        self._value(house, "500000.00")
        boat = self._asset("Boat", TangibleAsset.TYPE_BOAT)
        self._value(boat, "35000.00")

        body = self.client.get(reverse("finance:asset_list")).content.decode()
        self.assertEqual(body.count('data-testid="asset-group"'), 2)
        self.assertIn("$500,000.00", body)
        self.assertIn("$35,000.00", body)
        self.assertNotIn("$500000.00", body)

    def test_an_unvalued_asset_says_so_instead_of_showing_zero(self):
        self._asset("Mystery boat", TangibleAsset.TYPE_BOAT)
        body = self.client.get(reverse("finance:asset_list")).content.decode()
        self.assertIn("Value not recorded", body)

    def test_the_reconciliation_page_shows_every_line(self):
        self._account("Checking", "checking", "25805.45")
        self._account("Mortgage", "mortgage", "405507.93")
        house = self._asset()
        self._value(house, "500000.00")

        body = self.client.get(
            reverse("finance:net_worth_detail")).content.decode()
        for marker in ("rec-financial", "rec-tangible", "rec-gross",
                       "rec-liabilities", "rec-net-worth"):
            with self.subTest(marker=marker):
                self.assertIn(marker, body)
        self.assertNotIn("rec-mismatch", body)

    def test_the_dashboard_links_to_the_reconciliation(self):
        body = self.client.get(reverse("finance:dashboard")).content.decode()
        self.assertIn(reverse("finance:net_worth_detail"), body)
        self.assertIn(reverse("finance:asset_list"), body)

    def test_negative_net_worth_renders_correctly(self):
        self._account("Mortgage", "mortgage", "405507.93")
        body = self.client.get(reverse("finance:dashboard")).content.decode()
        self.assertIn("-$405,507.93", body)
        self.assertNotIn("$-405,507.93", body)

    def test_queries_do_not_grow_with_the_number_of_assets(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for i in range(3):
            asset = self._asset(f"Asset {i}", TangibleAsset.TYPE_VEHICLE)
            self._value(asset, "10000.00")
        with CaptureQueriesContext(connection) as few:
            self.client.get(reverse("finance:asset_list"))
        baseline = len(few.captured_queries)

        for i in range(20):
            asset = self._asset(f"Extra {i}", TangibleAsset.TYPE_VEHICLE)
            self._value(asset, "10000.00")
        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse("finance:asset_list"))

        self.assertLessEqual(len(many.captured_queries), baseline + 3,
                             "prefetch should keep valuations and links flat")

    def test_the_pages_are_responsive(self):
        for name in ("asset_list.html", "asset_detail.html", "asset_form.html",
                     "net_worth_detail.html"):
            markup = (Path(settings.BASE_DIR) / "templates" / "finance" /
                      name).read_text()
            with self.subTest(template=name):
                self.assertIn("@media (max-width: 480px)", markup)
                self.assertEqual(
                    re.findall(r"[^-]width:\s*\d+px",
                               re.sub(r"\.sr-only\s*\{[^}]*\}", "", markup,
                                      flags=re.S)), [])

    def test_no_inline_handlers(self):
        for name in ("asset_list.html", "asset_detail.html", "asset_form.html",
                     "net_worth_detail.html"):
            markup = (Path(settings.BASE_DIR) / "templates" / "finance" /
                      name).read_text()
            for handler in ("onclick=", "onchange=", "onsubmit="):
                with self.subTest(template=name, handler=handler):
                    self.assertNotIn(handler, markup)
