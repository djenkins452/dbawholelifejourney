# ==============================================================================
# File: apps/meals/tests/test_leftover_management.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Foundation 2, Increment 4 — leftover inventory, later consumption,
#   discard/waste truth, deterministic expiration, and legal state transitions.
# ==============================================================================
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.health.models import FoodEntry, FoodItem
from apps.health.services.nutrition_queries import NutritionQueries
from apps.meals.models import (
    FoodWasteEvent, Household, HouseholdMembership, Ingredient, Leftover,
    PantryItem, PreparationEvent, Recipe, RecipeIngredient,
)
from apps.meals.services.consumption import consume_meal
from apps.meals.services.leftover_queries import available_leftovers
from apps.meals.services.preparation import prepare_recipe
from apps.meals.services.waste import discard_leftover, expire_due_leftovers
from apps.users.models import TermsAcceptance

User = get_user_model()


def _household_for(email):
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    hh = Household.objects.create(name="H", primary_user=u)
    HouseholdMembership.objects.create(household=hh, user=u, role="admin")
    return u, hh


class LeftoverBase(TestCase):
    def setUp(self):
        self.user, self.household = _household_for("left@test.com")
        self.food = FoodItem.objects.create(
            name="Stew", serving_size=Decimal("100"), serving_unit="g",
            calories=Decimal("300"), protein_g=Decimal("25"),
            carbohydrates_g=Decimal("20"), fat_g=Decimal("10"))
        self.ingredient = Ingredient.objects.create(
            canonical_name="leftstew", category="protein", nutrition_source=self.food)
        self.recipe = Recipe.objects.create(
            user=self.user, title="Beef Stew", ingredients="", instructions="cook",
            servings=1)
        RecipeIngredient.objects.create(
            recipe=self.recipe, ingredient=self.ingredient,
            quantity=Decimal("1"), unit="serving", order_index=0)
        PantryItem.objects.create(
            household=self.household, ingredient=self.ingredient,
            quantity=Decimal("100"), unit="serving")

    def _leftover(self, servings=6):
        prep = prepare_recipe(
            household=self.household, user=self.user, recipe=self.recipe,
            servings=Decimal("8"), leftover_servings=Decimal(str(servings)))
        return Leftover.objects.get(pk=prep.leftover_id)


class LeftoverQueryingTests(LeftoverBase):

    def test_only_available_returned(self):
        avail = self._leftover(6)
        consumed = self._leftover(2)
        consumed.disposition = Leftover.DISP_CONSUMED
        consumed.servings = Decimal("0")
        consumed.save()
        discarded = self._leftover(3)
        discarded.disposition = Leftover.DISP_DISCARDED
        discarded.save()
        deleted = self._leftover(1)
        deleted.soft_delete()
        rows = list(available_leftovers(self.household))
        self.assertEqual([lo.pk for lo in rows], [avail.pk])

    def test_household_isolation(self):
        mine = self._leftover(6)
        other_u, other_hh = _household_for("other@test.com")
        Leftover.objects.create(
            user=other_u, household=other_hh, preparation=mine.preparation,
            servings=Decimal("4"))
        rows = list(available_leftovers(self.household))
        self.assertEqual([lo.pk for lo in rows], [mine.pk])


class LaterConsumptionTests(LeftoverBase):

    def test_consume_from_leftover_uses_actual_date_not_prep_time(self):
        lo = self._leftover(6)
        later = timezone.now() + timedelta(days=3)
        r = consume_meal(user=self.user, household=self.household, leftover=lo,
                         servings=Decimal("1"), consumed_at=later)
        self.assertEqual(r.status, "ok")
        entry = FoodEntry.objects.get(pk=r.food_entry_id)
        self.assertEqual(entry.logged_date, later.date())  # NOT the preparation date

    def test_fractional_and_deplete_sets_consumed(self):
        lo = self._leftover(2)
        consume_meal(user=self.user, household=self.household, leftover=lo, servings=Decimal("1.5"))
        r2 = consume_meal(user=self.user, household=self.household, leftover=lo, servings=Decimal("0.5"))
        self.assertEqual(r2.leftover_remaining, 0.0)
        lo.refresh_from_db()
        self.assertEqual(lo.disposition, Leftover.DISP_CONSUMED)
        self.assertIsNotNone(lo.depleted_at)

    def test_cannot_consume_depleted_leftover(self):
        lo = self._leftover(2)
        consume_meal(user=self.user, household=self.household, leftover=lo, servings=Decimal("2"))
        r = consume_meal(user=self.user, household=self.household, leftover=lo, servings=Decimal("1"))
        self.assertEqual(r.status, "failed")
        self.assertEqual(r.message, "leftover_unavailable")


class DiscardTests(LeftoverBase):

    def test_partial_discard(self):
        lo = self._leftover(6)
        r = discard_leftover(user=self.user, household=self.household, leftover=lo,
                             servings=Decimal("2"), reason="spilled")
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.leftover_remaining, 4.0)
        lo.refresh_from_db()
        self.assertEqual(lo.disposition, Leftover.DISP_AVAILABLE)  # still some left
        we = FoodWasteEvent.objects.get(pk=r.waste_event_id)
        self.assertEqual(we.event_type, FoodWasteEvent.EVENT_DISCARDED)
        self.assertEqual(we.servings, Decimal("2.00"))
        self.assertEqual(we.reason, "spilled")

    def test_full_discard_default_all(self):
        lo = self._leftover(4)
        r = discard_leftover(user=self.user, household=self.household, leftover=lo)  # all
        self.assertEqual(r.leftover_remaining, 0.0)
        lo.refresh_from_db()
        self.assertEqual(lo.disposition, Leftover.DISP_DISCARDED)

    def test_discard_creates_no_foodentry_no_nutrition_no_pantry_change(self):
        lo = self._leftover(4)
        pantry_before = PantryItem.objects.get(
            household=self.household, ingredient=self.ingredient).quantity
        discard_leftover(user=self.user, household=self.household, leftover=lo)
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 0)
        totals = NutritionQueries.get_daily_totals(self.user, date.today())
        self.assertEqual(totals["calories"], Decimal("0"))
        pantry_after = PantryItem.objects.get(
            household=self.household, ingredient=self.ingredient).quantity
        self.assertEqual(pantry_before, pantry_after)  # no second pantry deduction

    def test_discard_idempotent(self):
        lo = self._leftover(6)
        discard_leftover(user=self.user, household=self.household, leftover=lo,
                         servings=Decimal("2"), idempotency_key="d1")
        r2 = discard_leftover(user=self.user, household=self.household, leftover=lo,
                              servings=Decimal("2"), idempotency_key="d1")
        self.assertEqual(r2.status, "replayed")
        lo.refresh_from_db()
        self.assertEqual(lo.servings, Decimal("4.00"))  # subtracted once
        self.assertEqual(FoodWasteEvent.objects.count(), 1)

    def test_over_discard_rejected(self):
        lo = self._leftover(3)
        r = discard_leftover(user=self.user, household=self.household, leftover=lo,
                             servings=Decimal("10"))
        self.assertEqual(r.status, "failed")
        self.assertEqual(r.message, "insufficient_leftover")
        lo.refresh_from_db()
        self.assertEqual(lo.servings, Decimal("3.00"))

    def test_cannot_discard_already_discarded(self):
        lo = self._leftover(3)
        discard_leftover(user=self.user, household=self.household, leftover=lo)
        r = discard_leftover(user=self.user, household=self.household, leftover=lo,
                             servings=Decimal("1"))
        self.assertEqual(r.status, "failed")
        self.assertEqual(r.message, "leftover_unavailable")

    def test_discard_fail_closed(self):
        lo = self._leftover(6)
        with patch("apps.meals.services.waste.FoodWasteEvent.objects.create",
                   side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                discard_leftover(user=self.user, household=self.household, leftover=lo,
                                 servings=Decimal("2"))
        lo.refresh_from_db()
        self.assertEqual(lo.servings, Decimal("6.00"))  # untouched
        self.assertEqual(FoodWasteEvent.objects.count(), 0)


class ExpirationTests(LeftoverBase):

    def test_expire_due_marks_expired(self):
        lo = self._leftover(4)
        lo.expiration_date = date.today() - timedelta(days=1)
        lo.save()
        count = expire_due_leftovers()
        self.assertEqual(count, 1)
        lo.refresh_from_db()
        self.assertEqual(lo.disposition, Leftover.DISP_EXPIRED)
        we = FoodWasteEvent.objects.get(leftover=lo)
        self.assertEqual(we.event_type, FoodWasteEvent.EVENT_EXPIRED)
        self.assertEqual(we.source, FoodWasteEvent.SOURCE_SCHEDULED)

    def test_expire_is_idempotent(self):
        lo = self._leftover(4)
        lo.expiration_date = date.today() - timedelta(days=1)
        lo.save()
        self.assertEqual(expire_due_leftovers(), 1)
        self.assertEqual(expire_due_leftovers(), 0)  # already terminal
        self.assertEqual(FoodWasteEvent.objects.filter(leftover=lo).count(), 1)

    def test_no_expiration_date_never_expires(self):
        lo = self._leftover(4)  # no expiration_date (never invented)
        self.assertEqual(expire_due_leftovers(), 0)
        lo.refresh_from_db()
        self.assertEqual(lo.disposition, Leftover.DISP_AVAILABLE)

    def test_future_expiration_not_expired(self):
        lo = self._leftover(4)
        lo.expiration_date = date.today() + timedelta(days=2)
        lo.save()
        self.assertEqual(expire_due_leftovers(), 0)

    def test_expired_leftover_cannot_be_consumed(self):
        lo = self._leftover(4)
        lo.expiration_date = date.today() - timedelta(days=1)
        lo.save()
        expire_due_leftovers()
        r = consume_meal(user=self.user, household=self.household, leftover=lo,
                         servings=Decimal("1"))
        self.assertEqual(r.status, "failed")
        self.assertEqual(r.message, "leftover_unavailable")
