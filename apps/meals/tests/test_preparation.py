# ==============================================================================
# File: apps/meals/tests/test_preparation.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Foundation 2, Increment 2 — preparation execution spine.
#   Behavioral proof: PreparationEvent, pantry deduction via InventoryTransaction,
#   leftovers, idempotency (no double deduction), unsupported units, shortages,
#   fail-closed rollback.
# ==============================================================================
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.meals.models import (
    Household, HouseholdMembership, Ingredient, InventoryTransaction, Leftover,
    PantryItem, PreparationEvent, Recipe, RecipeIngredient,
)
from apps.meals.services.preparation import prepare_recipe

User = get_user_model()


class PreparationBase(TestCase):
    def setUp(self):
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(email="prep@test.com", password="x")
        # Onboard the user so the meals views are reachable (not redirected to onboarding).
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        self.household = Household.objects.create(name="H", primary_user=self.user)
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin")
        # Empty free-text → no auto-enrichment; we control RecipeIngredient directly.
        self.recipe = Recipe.objects.create(
            user=self.user, title="Flatbread", ingredients="", instructions="bake",
            servings=2)
        self.flour = Ingredient.objects.create(
            canonical_name="prepflour", category="grain")
        RecipeIngredient.objects.create(
            recipe=self.recipe, ingredient=self.flour,
            quantity=Decimal("2"), unit="cup", order_index=0)
        self.pantry = PantryItem.objects.create(
            household=self.household, ingredient=self.flour,
            quantity=Decimal("10"), unit="cup")

    def _prepare(self, **kw):
        return prepare_recipe(
            household=self.household, user=self.user, recipe=self.recipe, **kw)


class PreparationCoreTests(PreparationBase):

    def test_creates_preparation_event(self):
        r = self._prepare()
        self.assertEqual(r.status, "ok")
        prep = PreparationEvent.objects.get(pk=r.preparation_id)
        self.assertEqual(prep.preparation_status, PreparationEvent.PREP_COMPLETED)
        self.assertEqual(prep.household_id, self.household.id)
        self.assertEqual(prep.recipe_id, self.recipe.id)
        self.assertEqual(prep.recipe_title, "Flatbread")

    def test_deducts_pantry_through_inventory_transaction(self):
        self._prepare()  # servings default = recipe.servings=2 → scale 1 → deduct 2 cup
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("8"))
        txn = InventoryTransaction.objects.get(pantry_item=self.pantry, source="preparation")
        self.assertEqual(txn.delta_quantity, Decimal("-2"))
        self.assertIsNotNone(txn.preparation_id)

    def test_deduction_status_applied(self):
        r = self._prepare()
        self.assertEqual(r.deduction_status, PreparationEvent.DED_APPLIED)

    def test_scales_by_servings(self):
        self._prepare(servings=Decimal("4"))  # scale 2 → deduct 4 cup
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("6"))

    def test_leftovers_created(self):
        r = self._prepare(leftover_servings=Decimal("3"))
        self.assertIsNotNone(r.leftover_id)
        lo = Leftover.objects.get(pk=r.leftover_id)
        self.assertEqual(lo.servings, Decimal("3"))
        self.assertEqual(lo.preparation_id, r.preparation_id)
        self.assertEqual(lo.household_id, self.household.id)
        # deterministic: no invented expiration / storage
        self.assertIsNone(lo.expiration_date)
        self.assertIsNone(lo.storage_location)

    def test_no_leftover_when_zero(self):
        r = self._prepare(leftover_servings=Decimal("0"))
        self.assertIsNone(r.leftover_id)
        self.assertEqual(Leftover.objects.count(), 0)

    def test_audit_trail_in_deduction_summary(self):
        r = self._prepare()
        prep = PreparationEvent.objects.get(pk=r.preparation_id)
        ds = prep.deduction_summary
        self.assertIn("deductions", ds)
        self.assertEqual(ds["deductions"][0]["ingredient"], "prepflour")
        self.assertEqual(ds["deductions"][0]["status"], "applied")


class PreparationIdempotencyTests(PreparationBase):

    def test_same_key_never_double_deducts(self):
        r1 = self._prepare(idempotency_key="abc-123")
        r2 = self._prepare(idempotency_key="abc-123")  # refresh / retry / replay
        self.assertEqual(r1.status, "ok")
        self.assertEqual(r2.status, "replayed")
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("8"))  # deducted ONCE
        self.assertEqual(PreparationEvent.objects.count(), 1)
        self.assertEqual(
            InventoryTransaction.objects.filter(source="preparation").count(), 1)

    def test_different_keys_deduct_each_time(self):
        self._prepare(idempotency_key="k1")
        self._prepare(idempotency_key="k2")
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("6"))  # 10 - 2 - 2
        self.assertEqual(PreparationEvent.objects.count(), 2)


class PreparationEdgeCaseTests(PreparationBase):

    def test_insufficient_inventory_deducts_available_and_flags_partial(self):
        self.pantry.quantity = Decimal("1")   # need 2, only 1
        self.pantry.save()
        r = self._prepare()
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("0"))  # never negative
        self.assertEqual(r.deduction_status, PreparationEvent.DED_PARTIAL)
        self.assertEqual(r.deductions[0]["status"], "partial")

    def test_unsupported_conversion_rejected(self):
        # recipe wants cups (volume); pantry is grams (weight) → no density → unsupported
        self.pantry.unit = "g"
        self.pantry.quantity = Decimal("500")
        self.pantry.save()
        r = self._prepare()
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("500"))  # untouched
        self.assertEqual(r.deductions[0]["status"], "unsupported_conversion")

    def test_no_pantry_item(self):
        self.pantry.delete()
        r = self._prepare()
        self.assertEqual(r.deductions[0]["status"], "no_pantry_item")
        self.assertEqual(r.deduction_status, PreparationEvent.DED_SKIPPED)

    def test_no_structured_ingredients_skips(self):
        RecipeIngredient.objects.filter(recipe=self.recipe).delete()
        r = self._prepare()
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.deduction_status, PreparationEvent.DED_SKIPPED)
        self.assertEqual(r.deductions, [])
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("10"))  # untouched

    def test_unquantified_ingredient_skipped(self):
        RecipeIngredient.objects.filter(recipe=self.recipe).update(quantity=None)
        r = self._prepare()
        self.assertEqual(r.deductions[0]["status"], "no_quantity")
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("10"))

    def test_fail_closed_rollback_leaves_no_partial_truth(self):
        # A mid-execution failure must leave NO PreparationEvent and NO deduction.
        with patch("apps.meals.services.preparation.deduct_pantry_item",
                   side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self._prepare()
        self.assertEqual(PreparationEvent.objects.count(), 0)
        self.assertEqual(InventoryTransaction.objects.filter(source="preparation").count(), 0)
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("10"))  # untouched


class PreparationViewTests(PreparationBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_prepare_via_view_records_and_renders(self):
        resp = self.client.post(
            reverse("meals:prepare_recipe", args=[self.recipe.pk]),
            {"servings": "2", "leftover_servings": "1", "idempotency_key": "view-key-1"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Preparation recorded")
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("8"))
        self.assertEqual(Leftover.objects.count(), 1)

    def test_view_refresh_is_idempotent(self):
        url = reverse("meals:prepare_recipe", args=[self.recipe.pk])
        data = {"servings": "2", "idempotency_key": "view-key-2"}
        self.client.post(url, data)
        self.client.post(url, data)  # browser refresh / resubmit
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("8"))  # once
        self.assertEqual(PreparationEvent.objects.count(), 1)
