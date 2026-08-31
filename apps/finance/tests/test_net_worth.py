# ==============================================================================
# File: apps/finance/tests/test_net_worth.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P8 — net worth, the double-subtraction trap, and honest history.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Two failures would each quietly misstate a household by a large amount.

Subtracting a linked mortgage twice understates net worth by the size of the largest
debt. Treating an unvalued house as worth zero erases it. Both are silent, and both get
their own tests.
"""
from datetime import date, timedelta
from decimal import Decimal

from apps.finance.models import (AssetLoanLink, AssetValuation, FinancialAccount,
                                 NetWorthSnapshot, TangibleAsset)
from apps.finance.services.finance_calc import net_worth as NW
from apps.finance.tests.test_p1_economic_roles import RoleBase


class NetWorthBase(RoleBase):
    def _asset(self, name, *, value=None, asset_type="vehicle", include=True,
               as_of=None):
        asset = TangibleAsset.objects.create(
            user=self.user, name=name, asset_type=asset_type,
            include_in_net_worth=include)
        if value is not None:
            AssetValuation.objects.create(
                user=self.user, asset=asset, amount=Decimal(str(value)),
                effective_date=as_of or date(2026, 8, 1), source="user")
        return asset

    def _liability(self, name, balance, account_type="loan"):
        return FinancialAccount.objects.create(
            user=self.user, name=name, account_type=account_type,
            current_balance=Decimal(str(balance)))


class CompositionTests(NetWorthBase):
    def test_cash_and_liabilities_make_the_simple_case(self):
        # Base fixture: checking 1000, savings 2000, card -500 → wait, card is +500.
        position = NW.compose(self.user)
        self.assertEqual(position["cash_and_financial"], Decimal("3000"))

    def test_a_valued_asset_is_added(self):
        self._asset("Truck", value=30000)
        self.assertEqual(NW.compose(self.user)["tangible_assets"], Decimal("30000"))

    def test_an_unvalued_asset_is_a_named_gap_not_a_zero(self):
        self._asset("House")
        position = NW.compose(self.user)
        self.assertEqual(position["tangible_assets"], Decimal("0.00"))
        self.assertEqual(position["unvalued_assets"], ["House"])
        self.assertEqual(position["confidence"], "low")
        self.assertIn("not nothing", " ".join(position["assumptions"]))

    def test_an_excluded_asset_says_who_excluded_it(self):
        self._asset("Guitar", value=800, include=False)
        position = NW.compose(self.user)
        self.assertEqual(position["tangible_assets"], Decimal("0.00"))
        self.assertEqual(position["excluded_assets"], ["Guitar"])
        self.assertIn("at your request", " ".join(position["assumptions"]))

    def test_a_stale_valuation_is_flagged_but_still_counted(self):
        self._asset("Boat", value=12000, as_of=date(2023, 1, 1))
        position = NW.compose(self.user)
        self.assertEqual(position["tangible_assets"], Decimal("12000"))
        self.assertEqual(position["stale_valuations"], ["Boat"])
        self.assertEqual(position["confidence"], "medium")

    def test_a_property_ACCOUNT_is_not_added_on_top_of_the_asset(self):
        """Counting the account and the registry entry is how a house doubles."""
        FinancialAccount.objects.create(
            user=self.user, name="House (account)", account_type="property",
            current_balance=Decimal("400000"))
        self._asset("House", value=400000, asset_type="real_estate")
        self.assertEqual(NW.compose(self.user)["tangible_assets"], Decimal("400000"))


class DoubleSubtractionTests(NetWorthBase):
    """The trap: a mortgage is a liability AND it is linked to the house."""

    def setUp(self):
        super().setUp()
        self.house = self._asset("House", value=400000, asset_type="real_estate")
        self.mortgage = self._liability("Mortgage", -250000, "mortgage")
        AssetLoanLink.objects.create(user=self.user, asset=self.house,
                                     account=self.mortgage)

    def test_the_linked_debt_is_subtracted_exactly_once(self):
        position = NW.compose(self.user)
        # cash 3000 + card 500 asset-side? card is a liability. Let's assert the parts.
        self.assertEqual(position["tangible_assets"], Decimal("400000"))
        self.assertEqual(position["liabilities"], Decimal("250500"))  # mortgage + card
        self.assertEqual(position["net_worth"],
                         Decimal("3000") + Decimal("400000") - Decimal("250500"))

    def test_equity_is_shown_but_never_added_to_the_total(self):
        position = NW.compose(self.user)
        house = [a for a in position["asset_rows"] if a["name"] == "House"][0]
        self.assertEqual(house["equity"], "150000.00")
        self.assertEqual(house["linked_debt"], "250000.00")
        # The total uses the full value, not the equity.
        self.assertEqual(position["tangible_assets"], Decimal("400000"))

    def test_the_rule_is_stated_where_someone_will_read_it(self):
        self.assertIn("subtracted ONCE",
                      " ".join(NW.compose(self.user)["assumptions"]))


class SnapshotTests(NetWorthBase):
    def test_a_dry_run_writes_nothing(self):
        result = NW.take_snapshot(self.user)
        self.assertFalse(result["committed"])
        self.assertEqual(NetWorthSnapshot.objects.count(), 0)

    def test_a_committed_snapshot_records_the_position(self):
        self._asset("Truck", value=30000)
        result = NW.take_snapshot(self.user, commit=True)
        self.assertTrue(result["created"])
        snapshot = NetWorthSnapshot.objects.get()
        self.assertEqual(snapshot.tangible_assets, Decimal("30000"))

    def test_running_it_twice_in_a_day_updates_rather_than_duplicates(self):
        NW.take_snapshot(self.user, commit=True)
        second = NW.take_snapshot(self.user, commit=True)
        self.assertFalse(second["created"])
        self.assertEqual(NetWorthSnapshot.objects.count(), 1)

    def test_a_re_run_picks_up_a_changed_value(self):
        asset = self._asset("Truck", value=30000)
        NW.take_snapshot(self.user, commit=True)
        AssetValuation.objects.create(
            user=self.user, asset=asset, amount=Decimal("28000"),
            effective_date=date(2026, 8, 30), source="user")
        NW.take_snapshot(self.user, commit=True)
        self.assertEqual(NetWorthSnapshot.objects.get().tangible_assets,
                         Decimal("28000"))

    def test_the_snapshot_keeps_its_composition_for_drill_down(self):
        self._asset("Truck", value=30000)
        NW.take_snapshot(self.user, commit=True)
        composition = NetWorthSnapshot.objects.get().composition
        self.assertTrue(composition["accounts"])
        self.assertEqual(composition["assets"][0]["name"], "Truck")

    def test_gaps_are_carried_into_the_snapshot(self):
        self._asset("House")
        NW.take_snapshot(self.user, commit=True)
        snapshot = NetWorthSnapshot.objects.get()
        self.assertEqual(snapshot.unvalued_asset_count, 1)
        self.assertFalse(snapshot.is_complete)


class HistoryTests(NetWorthBase):
    def test_no_snapshots_explains_why_rather_than_drawing_a_line(self):
        result = NW.history(self.user)
        self.assertFalse(result["has_history"])
        self.assertIn("look like history and be fiction", result["explanation"])

    def test_one_snapshot_is_a_position_not_a_trend(self):
        NW.take_snapshot(self.user, commit=True)
        result = NW.history(self.user)
        self.assertTrue(result["has_history"])
        self.assertTrue(result["single_point"])
        self.assertIn("not yet a trend", result["explanation"])

    def test_two_snapshots_give_a_direction(self):
        from apps.core.utils import get_user_today
        today = get_user_today(self.user)
        NW.take_snapshot(self.user, today=today - timedelta(days=30), commit=True)
        self._asset("Truck", value=30000)
        NW.take_snapshot(self.user, today=today, commit=True)
        result = NW.history(self.user)
        self.assertEqual(len(result["points"]), 2)
        self.assertEqual(result["change"], "30000.00")

    def test_history_never_predates_the_first_snapshot(self):
        from apps.core.utils import get_user_today
        NW.take_snapshot(self.user, commit=True)
        result = NW.history(self.user)
        self.assertEqual(result["first"], str(get_user_today(self.user)))

    def test_every_point_says_whether_it_was_observed(self):
        NW.take_snapshot(self.user, commit=True)
        self.assertEqual(NW.history(self.user)["points"][0]["basis"], "observed")


class OwnershipTests(NetWorthBase):
    def test_one_household_never_sees_another(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="nw2@example.com", password="pw"))
        FinancialAccount.objects.create(
            user=other, name="Theirs", account_type="checking",
            current_balance=Decimal("999999"))
        self.assertEqual(NW.compose(self.user)["cash_and_financial"], Decimal("3000"))

    def test_snapshots_do_not_leak_between_users(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="nw3@example.com", password="pw"))
        NW.take_snapshot(self.user, commit=True)
        self.assertFalse(NW.history(other)["has_history"])
