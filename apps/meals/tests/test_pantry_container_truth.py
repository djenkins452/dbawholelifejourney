# ==============================================================================
# File: apps/meals/tests/test_pantry_container_truth.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Foundation 2 — Pantry Container Truth. Proves package-unit pantry items
#   deduct correctly against culinary recipe units, deterministically, across every
#   acquisition path, and fail closed only when truth is genuinely absent.
# ==============================================================================
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.health.models import FoodItem
from apps.meals.models import (
    Household, HouseholdMembership, Ingredient, PantryItem, PreparationEvent,
    Recipe, RecipeIngredient,
)
from apps.meals.services.container_truth import resolve_net_content
from apps.meals.services.pantry_ingestion import finalize_pantry_item
from apps.meals.services.preparation import prepare_recipe
from apps.meals.services.unit_conversion import convert_between
from apps.users.models import TermsAcceptance

User = get_user_model()


class ConversionEngineTests(TestCase):
    def test_within_dimension(self):
        self.assertAlmostEqual(float(convert_between(Decimal("2"), "tbsp", "ml")), 29.574, 2)
        self.assertAlmostEqual(float(convert_between(Decimal("1"), "lb", "g")), 453.592, 2)

    def test_mass_volume_needs_density(self):
        self.assertIsNone(convert_between(Decimal("100"), "g", "ml"))          # no density
        self.assertAlmostEqual(
            float(convert_between(Decimal("100"), "g", "ml", Decimal("1.14"))), 87.72, 1)

    def test_count_is_closed(self):
        self.assertEqual(convert_between(Decimal("2"), "piece", "count"), Decimal("2"))
        self.assertIsNone(convert_between(Decimal("2"), "piece", "ml"))         # count↔measure undefined


class ContainerResolutionTests(TestCase):
    def test_priority_fooditem_net_content(self):
        fi = FoodItem.objects.create(name="Ketchup 20oz", serving_size=Decimal("15"),
                                     serving_unit="g", calories=Decimal("20"),
                                     net_content=Decimal("591"), net_content_unit="ml")
        ing = Ingredient.objects.create(canonical_name="ck", category="condiment",
                                        base_measure="volume", density_g_per_ml=Decimal("1.14"),
                                        nutrition_source=fi)
        net, unit = resolve_net_content(ing)
        self.assertEqual(unit, "ml")
        self.assertEqual(net, Decimal("591.000"))

    def test_priority_ingredient_default(self):
        ing = Ingredient.objects.create(canonical_name="olv", category="fat",
                                        base_measure="volume", density_g_per_ml=Decimal("0.915"),
                                        default_quantity=Decimal("500"), default_unit="ml")
        net, unit = resolve_net_content(ing)
        self.assertEqual((net, unit), (Decimal("500.000"), "ml"))

    def test_count_needs_no_container_truth(self):
        # Count substances stay on the legacy unit-matching path (count↔count already
        # deducts). No net_content is synthesized, so an unseeded weight/volume item
        # (base_measure defaults to 'count') is never wrongly forced onto the container path.
        ing = Ingredient.objects.create(canonical_name="egg", category="protein",
                                        base_measure="count")
        self.assertEqual(resolve_net_content(ing), (None, ""))

    def test_unresolvable_returns_none(self):
        # volume + no density + default "100 g" -> 100g can't convert to ml -> unresolvable
        ing = Ingredient.objects.create(canonical_name="mystery", category="other",
                                        base_measure="volume")
        self.assertEqual(resolve_net_content(ing), (None, ""))


class ContainerDeductionBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ct@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.household = Household.objects.create(name="H", primary_user=self.user)
        HouseholdMembership.objects.create(household=self.household, user=self.user, role="admin")

    def _ingredient(self, name, measure, density, net_qty, net_unit):
        return Ingredient.objects.create(
            canonical_name=name, category="other", base_measure=measure,
            density_g_per_ml=(Decimal(density) if density else None),
            default_quantity=Decimal(net_qty), default_unit=net_unit)

    def _recipe(self, ingredient, qty, unit, servings=1):
        r = Recipe.objects.create(user=self.user, title=f"{ingredient.canonical_name} dish",
                                  ingredients="", instructions="cook", servings=servings)
        RecipeIngredient.objects.create(recipe=r, ingredient=ingredient,
                                        quantity=Decimal(str(qty)), unit=unit, order_index=0)
        return r

    def _acquire(self, ingredient, containers=1):
        # Acquisition through the canonical write path -> net_content auto-resolved.
        item, _ = finalize_pantry_item(
            household=self.household, ingredient=ingredient, quantity=Decimal(str(containers)),
            source="manual", notes="acquired", unit="piece")
        return item

    def _prepare(self, recipe, servings=1):
        return prepare_recipe(household=self.household, user=self.user, recipe=recipe,
                              servings=Decimal(str(servings)))


class ContainerDeductionTests(ContainerDeductionBase):
    # The 8 validation ingredients — package pantry unit, culinary recipe unit.
    CASES = [
        # name, measure, density, net_qty, net_unit, recipe_qty, recipe_unit, expect_base
        ("tct_ketchup",  "volume", "1.14",  "591",  "ml", 2, "tbsp", 29.574),
        ("tct_mustard",  "volume", "1.05",  "255",  "ml", 1, "tsp",  4.929),
        ("tct_mayo",     "volume", "0.91",  "445",  "ml", 3, "tbsp", 44.361),
        ("tct_oliveoil", "volume", "0.915", "500",  "ml", 2, "tbsp", 29.574),
        ("tct_milk",     "volume", "1.03",  "3785", "ml", 1, "cup",  236.588),
        ("tct_flour",    "mass",   "0.53",  "2270", "g",  1, "cup",  125.39),   # cup->ml->g via density
        ("tct_sugar",    "mass",   "0.85",  "1810", "g",  2, "tbsp", 25.14),    # 29.574ml*0.85
        ("tct_protein",  "mass",   "0.45",  "907",  "g",  1, "cup",  106.46),   # 236.588*0.45
    ]

    def test_all_eight_deduct_deterministically(self):
        for name, measure, density, nq, nu, rq, ru, expect in self.CASES:
            with self.subTest(ingredient=name):
                ing = self._ingredient(name, measure, density, nq, nu)
                item = self._acquire(ing, containers=1)
                self.assertIsNotNone(item.net_content, f"{name}: net_content not resolved")
                r = self._recipe(ing, rq, ru)
                res = self._prepare(r)
                d = res.deductions[0]
                self.assertEqual(d["status"], "applied", f"{name}: {d}")
                self.assertAlmostEqual(d["deducted"], expect, delta=0.5,
                                       msg=f"{name}: deducted {d['deducted']} != {expect}")

    def test_partial_remaining_container(self):
        # Half a bottle of ketchup (quantity 0.5 containers) still deducts deterministically.
        ing = self._ingredient("ketchup2", "volume", "1.14", "591", "ml")
        item = self._acquire(ing, containers=1)
        item.quantity = Decimal("0.5")   # "about half a bottle left" (Remaining Truth)
        item.save()
        r = self._recipe(ing, 2, "tbsp")   # 29.574 ml
        res = self._prepare(r)
        self.assertEqual(res.deductions[0]["status"], "applied")
        item.refresh_from_db()
        # 0.5*591=295.5 ml available; deduct 29.574 -> 265.926 ml -> 0.45 containers
        self.assertAlmostEqual(float(item.quantity), 0.45, delta=0.01)

    def test_insufficient_container_partial(self):
        ing = self._ingredient("ketchup3", "volume", "1.14", "591", "ml")
        item = self._acquire(ing, containers=1)
        item.quantity = Decimal("0.01")  # almost empty (5.91 ml)
        item.save()
        r = self._recipe(ing, 2, "tbsp")  # wants 29.574 ml
        res = self._prepare(r)
        self.assertEqual(res.deductions[0]["status"], "partial")
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("0"))  # floored, never negative


class MissingTruthTests(ContainerDeductionBase):
    def test_needs_container_info_when_no_truth(self):
        # Volume ingredient, no density/net-content resolvable, pantry is 'piece'.
        ing = Ingredient.objects.create(canonical_name="mystery-sauce", category="other",
                                        base_measure="volume")
        PantryItem.objects.create(household=self.household, ingredient=ing,
                                  quantity=Decimal("1"), unit="piece")
        r = self._recipe(ing, 2, "tbsp")
        res = self._prepare(r)
        d = res.deductions[0]
        self.assertEqual(d["status"], "needs_container_info")   # NOT "unsupported_conversion"
        self.assertIn("net contents", d["note"])

    def test_legacy_same_unit_still_deducts(self):
        # Backward-compat: count item, recipe in the same unit, no net_content -> legacy path.
        ing = Ingredient.objects.create(canonical_name="lime", category="fruit",
                                        base_measure="count")
        PantryItem.objects.create(household=self.household, ingredient=ing,
                                  quantity=Decimal("6"), unit="piece")  # no net_content set
        r = self._recipe(ing, 2, "piece")
        res = self._prepare(r)
        self.assertEqual(res.deductions[0]["status"], "applied")
        self.assertEqual(res.deductions[0]["deducted"], 2.0)


class AcquisitionNormalizationTests(ContainerDeductionBase):
    def test_finalize_resolves_container_truth_from_fooditem(self):
        fi = FoodItem.objects.create(name="Ketchup", serving_size=Decimal("15"),
                                     serving_unit="g", calories=Decimal("20"),
                                     net_content=Decimal("591"), net_content_unit="ml")
        ing = Ingredient.objects.create(canonical_name="ck-acq", category="condiment",
                                        base_measure="volume", density_g_per_ml=Decimal("1.14"),
                                        nutrition_source=fi)
        item, _ = finalize_pantry_item(household=self.household, ingredient=ing,
                                       quantity=Decimal("1"), source="receipt", notes="", unit="piece")
        self.assertEqual(item.net_content, Decimal("591.000"))
        self.assertEqual(item.net_content_unit, "ml")
