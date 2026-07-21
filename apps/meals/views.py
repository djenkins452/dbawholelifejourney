"""
Whole Life Journey - Meal Intelligence Views

Project: Whole Life Journey
Path: apps/meals/views.py
Purpose: Views for the Meal Intelligence pillar UI

Views:
    MealsDashboardView — Command center for meal intelligence
    DinnerSuggestionsView — Ranked meal options with filtering
    PantryView — Pantry inventory grouped by section
    MealPlanView — Weekly meal planner with calendar grid
    ReceiptUploadView — Receipt upload and history
    RecipeIntelligenceDetailView — Recipe detail with nutrition + scoring
"""

import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView, View

from apps.core.current_context import PageSummaryMixin
from apps.meals.services.meals_home_summary import build_meals_home_summary
from apps.help.mixins import HelpContextMixin
from apps.meals.models import Recipe

from .models import (
    DietaryProfile,
    Household,
    HouseholdMembership,
    Ingredient,
    InventoryTransaction,
    Leftover,
    MealPlan,
    MealPlanEntry,
    PantryItem,
    PantryPhotoDetection,
    PantryPhotoUpload,
    PantryScanSession,
    PreparationEvent,
    Receipt,
    ReceiptItem,
    RecipeIngredient,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Mixins
# =============================================================================


class MealsHouseholdMixin:
    """Mixin to resolve user's household and dietary profile."""

    def get_household(self):
        """Get or create the user's household."""
        user = self.request.user
        membership = (
            HouseholdMembership.objects.filter(user=user)
            .select_related("household")
            .first()
        )
        if membership:
            return membership.household

        # Auto-create a household for the user
        household = Household.objects.create(
            name=f"{user.first_name or user.email.split('@')[0]}'s Household",
            primary_user=user,
        )
        HouseholdMembership.objects.create(
            household=household,
            user=user,
            role="admin",
        )
        return household

    def get_dietary_profile(self):
        """Get user's dietary profile or None."""
        return DietaryProfile.objects.filter(user=self.request.user).first()


# =============================================================================
# Dashboard — Command Center
# =============================================================================


class MealsDashboardView(
    PageSummaryMixin, HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin,
    TemplateView
):
    """
    Meal Intelligence Command Center.

    Shows tonight's recommendation, expiring items, grocery cycle status,
    and weekly nutrition overview.
    """

    template_name = "meals/dashboard.html"
    help_context_id = "MEALS_DASHBOARD"
    # Current Context — the Meals workspace declares a deterministic overview summary.
    # The meals.dashboard provider reads the SAME build_meals_home_summary source this
    # view exposes below (request-path-safe SAE snapshot), so the page and the assistant
    # never disagree about the figures.
    page_summary_key = "meals.dashboard"
    page_summary_title = "Meals"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # ONE deterministic source feeds both this render and the meals.dashboard page
        # summary provider (Current Context contract — never re-derive independently).
        context["meals_summary"] = build_meals_home_summary(user)

        household = self.get_household()
        dietary_profile = self.get_dietary_profile()
        today = timezone.now().date()

        # Activation check — block scoring if below threshold
        from apps.meals.services.activation import get_activation_status

        activation = get_activation_status(user, household)
        context["activation"] = activation

        if not activation.is_ready:
            # Setup mode — return minimal context
            context["setup_mode"] = True
            context["household"] = household
            context["dietary_profile"] = dietary_profile
            context["pantry_total"] = activation.pantry_count
            context["pantry_low_confidence"] = 0
            return context

        context["setup_mode"] = False

        # Check if just activated (for activation moment message)
        if activation.activated_at and not activation.missing:
            from datetime import timedelta as td

            if timezone.now() - activation.activated_at < td(minutes=30):
                context["just_activated"] = True

        # Tonight's recommendation
        tonight_recommendation = self._get_tonight_recommendation(
            household, dietary_profile
        )
        context["tonight"] = tonight_recommendation

        # Expiring soon (next 3 days)
        from apps.meals.services.inventory_gap import find_pantry_expiring_soon

        context["expiring_items"] = list(
            find_pantry_expiring_soon(household, days=3)
            .select_related("ingredient")[:5]
        )

        # Grocery cycle countdown
        context["grocery_cycle"] = self._get_grocery_cycle(household)

        # Active meal plan
        active_plan = (
            MealPlan.objects.filter(
                household=household,
                start_date__lte=today,
                end_date__gte=today,
            )
            .first()
        )
        context["active_plan"] = active_plan
        if active_plan:
            context["plan_entries_today"] = MealPlanEntry.objects.filter(
                meal_plan=active_plan, date=today
            ).select_related("recipe")

        # Pantry stats
        pantry_total = PantryItem.objects.filter(
            household=household, quantity__gt=0
        ).count()
        low_confidence = PantryItem.objects.filter(
            household=household, quantity__gt=0, confidence_score__lt=Decimal("0.5")
        ).count()
        context["pantry_total"] = pantry_total
        context["pantry_low_confidence"] = low_confidence

        # Weekly protein balance (last 7 days of meal plan entries)
        context["weekly_protein"] = self._get_weekly_protein(household, today)

        # Nudges
        from apps.meals.services.advanced_intelligence import get_todays_nudges

        context["nudges"] = get_todays_nudges(user, household)

        # Dietary profile summary
        context["dietary_profile"] = dietary_profile
        context["household"] = household

        return context

    def _get_tonight_recommendation(self, household, dietary_profile):
        """Get the top-scored recipe for tonight."""
        try:
            from apps.meals.services.meal_scoring import rank_recipes

            user_recipes = Recipe.objects.filter(user=self.request.user)[:50]
            if not user_recipes:
                return None

            ranked = rank_recipes(
                list(user_recipes),
                household,
                dietary_profile,
                available_minutes=60,
                top_n=1,
            )
            if ranked:
                top = ranked[0]
                # Get nutrition summary
                from apps.meals.services.recipe_nutrition import (
                    get_recipe_macro_summary,
                )

                nutrition = get_recipe_macro_summary(
                    Recipe.objects.get(pk=top.recipe_id)
                )
                return {
                    "recipe_id": top.recipe_id,
                    "recipe_title": top.recipe_title,
                    "score": top.total_score,
                    "explanation": top.explanation,
                    "factors": {
                        f.name: float(f.weighted_value)
                        for f in top.factors
                    },
                    "prep_time": top.prep_time_minutes,
                    "nutrition": nutrition,
                }
        except Exception:
            logger.exception("Error getting tonight recommendation")
        return None

    def _get_grocery_cycle(self, household):
        """Get grocery cycle countdown info."""
        from apps.meals.services.advanced_intelligence import (
            _days_since_last_grocery,
        )

        days_since = _days_since_last_grocery(household)
        cycle_days = household.grocery_cycle_days
        if days_since is not None:
            days_until = max(0, cycle_days - days_since)
            return {
                "days_since_trip": days_since,
                "cycle_days": cycle_days,
                "days_until_next": days_until,
                "pct_elapsed": min(
                    100, int((days_since / cycle_days) * 100)
                )
                if cycle_days
                else 0,
            }
        return {
            "days_since_trip": None,
            "cycle_days": cycle_days,
            "days_until_next": None,
            "pct_elapsed": 0,
        }

    def _get_weekly_protein(self, household, today):
        """Get weekly protein from meal plan entries."""
        week_ago = today - timedelta(days=7)
        entries = MealPlanEntry.objects.filter(
            meal_plan__household=household,
            date__gte=week_ago,
            date__lte=today,
        ).select_related("recipe")

        daily_protein = {}
        for entry in entries:
            day_key = entry.date.isoformat()
            if entry.inventory_impact_snapshot and "protein" in entry.inventory_impact_snapshot:
                daily_protein[day_key] = (
                    daily_protein.get(day_key, 0)
                    + entry.inventory_impact_snapshot["protein"]
                )
        return daily_protein


# =============================================================================
# Dinner Suggestions
# =============================================================================


class DinnerSuggestionsView(
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, TemplateView
):
    """
    Ranked dinner suggestions with category filtering.

    Sections: Optimal Tonight, Under 20 Minutes, Scales to 4-6,
    Uses Expiring Items, Requires Store Trip.
    """

    template_name = "meals/suggestions.html"
    help_context_id = "MEALS_SUGGESTIONS"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        household = self.get_household()
        dietary_profile = self.get_dietary_profile()

        # Activation check — block scoring if below threshold
        from apps.meals.services.activation import get_activation_status

        activation = get_activation_status(user, household)
        context["activation"] = activation
        if not activation.is_ready:
            context["setup_mode"] = True
            context["has_recipes"] = False
            return context
        context["setup_mode"] = False

        user_recipes = list(Recipe.objects.filter(user=user)[:100])
        if not user_recipes:
            context["has_recipes"] = False
            return context

        context["has_recipes"] = True

        from apps.meals.services.meal_scoring import rank_recipes
        from apps.meals.services.recipe_nutrition import get_recipe_macro_summary
        from apps.meals.services.inventory_gap import analyze_recipe_gaps

        # Score all recipes
        all_scored = rank_recipes(
            user_recipes, household, dietary_profile, available_minutes=120, top_n=50
        )

        # Build enriched cards
        enriched = []
        for score in all_scored:
            recipe = next(
                (r for r in user_recipes if r.id == score.recipe_id), None
            )
            if not recipe:
                continue

            nutrition = get_recipe_macro_summary(recipe)
            gap = analyze_recipe_gaps(recipe, household)

            enriched.append({
                "recipe": recipe,
                "score": score,
                "nutrition": nutrition,
                "gap": gap,
                "availability_pct": int(gap.availability_score * 100),
                "needs_store": gap.availability_score < 0.5,
            })

        # Optimal Tonight (top 5)
        context["optimal"] = enriched[:5]

        # Under 20 minutes
        context["quick"] = [
            e for e in enriched
            if e["score"].prep_time_minutes and e["score"].prep_time_minutes <= 20
        ][:5]

        # Uses Expiring Items (high expiration urgency score)
        def _get_factor_value(score, name):
            for f in score.factors:
                if f.name == name:
                    return float(f.weighted_value)
            return 0

        context["uses_expiring"] = sorted(
            [e for e in enriched if _get_factor_value(e["score"], "expiration_urgency") > 0.3],
            key=lambda e: _get_factor_value(e["score"], "expiration_urgency"),
            reverse=True,
        )[:5]

        # Requires Store Trip
        context["needs_store"] = [e for e in enriched if e["needs_store"]][:5]

        # Emotional context
        from apps.meals.services.advanced_intelligence import get_emotional_overlay

        context["emotional"] = get_emotional_overlay(user)

        return context


# =============================================================================
# Pantry View
# =============================================================================


class PantryView(
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, TemplateView
):
    """
    Pantry Intelligence view — grouped by storage location.

    Groups items by physical location (Fridge, Pantry, Freezer, Other)
    with confidence scores, expiration badges, and inline actions.
    """

    template_name = "meals/pantry.html"
    help_context_id = "MEALS_PANTRY"

    # Display labels for storage locations
    STORAGE_DISPLAY = {
        "fridge": "Fridge",
        "pantry": "Pantry",
        "freezer": "Freezer",
        "other": "Other",
        "unknown": "Uncategorized",
    }

    STORAGE_ORDER = ["fridge", "pantry", "freezer", "other", "unknown"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        household = self.get_household()

        items = (
            PantryItem.objects.filter(household=household, quantity__gt=0)
            .select_related("ingredient")
            .order_by("storage_location", "ingredient__canonical_name")
        )

        # Group by storage location
        sections = {}
        for item in items:
            loc = item.storage_location or "unknown"
            section_name = self.STORAGE_DISPLAY.get(loc, "Uncategorized")
            if section_name not in sections:
                sections[section_name] = []
            sections[section_name].append(item)

        # Order sections
        ordered_sections = []
        for loc in self.STORAGE_ORDER:
            name = self.STORAGE_DISPLAY.get(loc, "Uncategorized")
            if name in sections:
                ordered_sections.append((name, sections[name]))

        context["sections"] = ordered_sections
        context["pantry_count"] = items.count()
        context["household"] = household

        # Summary stats
        today = timezone.now().date()
        context["expiring_count"] = items.filter(
            expiration_date_estimated__lte=today + timedelta(days=3),
            expiration_date_estimated__gte=today,
        ).count()
        context["low_confidence_count"] = items.filter(
            confidence_score__lt=Decimal("0.5")
        ).count()

        # Phase 12: Recent scan sessions
        from apps.meals.services.pantry_photo_detection import pantry_scan_session_service

        context["recent_sessions"] = pantry_scan_session_service.get_recent_sessions(
            household, limit=5
        )
        drift = pantry_scan_session_service.calculate_confidence_drift(household)
        context["pantry_confidence"] = drift

        return context


class PantryConfirmView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """AJAX endpoint to confirm a pantry item's quantity."""

    def post(self, request, pk):
        household = self.get_household()
        item = get_object_or_404(PantryItem, pk=pk, household=household)
        item.confidence_score = Decimal("1.0")
        item.last_confirmed_at = timezone.now()
        item.save(update_fields=["confidence_score", "last_confirmed_at"])
        return JsonResponse({"status": "ok", "confidence": 1.0})


class PantryMarkUsedView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """AJAX endpoint to mark a pantry item as fully used."""

    def post(self, request, pk):
        household = self.get_household()
        item = get_object_or_404(PantryItem, pk=pk, household=household)
        old_qty = item.quantity
        item.quantity = Decimal("0")
        item.save(update_fields=["quantity"])
        InventoryTransaction.objects.create(
            pantry_item=item,
            delta_quantity=-old_qty,
            source="manual",
            notes="Marked as used from pantry view",
        )
        return JsonResponse({"status": "ok"})


class PantryUpdateView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """AJAX endpoint to update pantry item quantity."""

    def post(self, request, pk):
        household = self.get_household()
        item = get_object_or_404(PantryItem, pk=pk, household=household)
        try:
            data = json.loads(request.body)
            new_qty = Decimal(str(data.get("quantity", 0)))
        except (json.JSONDecodeError, Exception):
            return JsonResponse({"status": "error", "message": "Invalid data"}, status=400)

        delta = new_qty - item.quantity
        item.quantity = new_qty
        item.confidence_score = Decimal("1.0")
        item.last_confirmed_at = timezone.now()
        item.save(update_fields=["quantity", "confidence_score", "last_confirmed_at"])

        InventoryTransaction.objects.create(
            pantry_item=item,
            delta_quantity=delta,
            source="manual",
            notes="Updated from pantry view",
        )
        return JsonResponse({"status": "ok", "quantity": float(new_qty)})


class PantrySetContainerView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """Capture the one missing Container Truth fact in-workflow ("what size is this?").

    Invoked from the preparation result when an item returns `needs_container_info`.
    Sets the container's net contents (deterministically, in a base unit), records the
    substance's base_measure canonically on the Ingredient so future acquisitions resolve
    automatically, normalizes the item's stored remaining to an exact base quantity, and
    returns to where the user was so they can immediately re-cook. No duplicate pantry
    workflow — this is the same PantryItem, one focused field.
    """

    def post(self, request, pk):
        from apps.meals.services.container_truth import capture_container_truth

        household = self.get_household()
        item = get_object_or_404(PantryItem, pk=pk, household=household)

        raw_amount = (request.POST.get("net_content_amount") or "").strip()
        raw_unit = (request.POST.get("net_content_unit") or "").strip().lower()
        container_type = (request.POST.get("container_type") or "").strip()
        next_url = (request.POST.get("next") or "").strip()

        try:
            amount = Decimal(raw_amount)
        except Exception:
            amount = None

        # Shared deterministic capture: writes the Ingredient's canonical base_measure +
        # net-content AND normalizes this item's remaining to an exact base quantity.
        result = capture_container_truth(item, amount, raw_unit, container_type=container_type)
        if result is None:
            messages.error(request, "Enter a valid container size (amount and unit).")
            return redirect(next_url or "meals:pantry")

        base_amount, base_unit = result
        messages.success(
            request,
            f"Saved — one {container_type or 'container'} of {item.ingredient.canonical_name} "
            f"is {base_amount.normalize():f} {base_unit}. This is now automatic.",
        )
        return redirect(next_url or "meals:pantry")


class PantryIngredientSearchView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """Type-ahead ingredient search for manual pantry entry (Pantry Smart Search behavior).

    Powered by the single Ingredient Intelligence search authority — case-insensitive
    substring across canonical name, aliases, and the normalized identity key — so the user
    reuses EXISTING canonical ingredients instead of creating duplicates. Read-only JSON;
    user-scoped only by authentication (ingredients are a shared catalog).
    """

    def get(self, request):
        from apps.meals.services.ingredient_intelligence import search_ingredients

        q = (request.GET.get("q") or "").strip()
        results = []
        if len(q) >= 1:
            for ing in search_ingredients(q, limit=12):
                results.append({
                    "id": ing.id,
                    "name": ing.canonical_name,
                    "category": ing.category,
                    # Whether Container Truth is already known (so the UI can pre-fill/skip).
                    "has_container_truth": bool(
                        ing.base_measure != "count"
                        and ing.default_quantity
                        and ing.default_unit
                    ),
                })
        return JsonResponse({"results": results})


class PantryManualAddView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """First-class MANUAL pantry acquisition — the graceful-degradation path for anything a
    user can buy, grow, cook, or receive (farmers-market produce, homemade salsa, bulk flour,
    restaurant leftovers, barcode-less or AI-unrecognized items).

    It is NOT a separate pantry system: it resolves/creates a canonical Ingredient (reusing
    existing ones, never duplicating) and flows through the SAME canonical write path
    (finalize_pantry_item, source="manual") as barcode, receipt, and scan — landing in an
    identical PantryItem. Optionally captures Container Truth up front (Capture Once, Reuse
    Everywhere) and an explicit expiration (never invented).
    """

    def post(self, request):
        from apps.meals.services.container_truth import capture_container_truth
        from apps.meals.services.ingredient_matching import get_or_create_ingredient
        from apps.meals.services.pantry_ingestion import finalize_pantry_item

        household = self.get_household()

        # 1. Resolve the ingredient — reuse an existing canonical one, or create a new one
        #    ONLY when the user explicitly asked to (no silent duplicates).
        ingredient = None
        ingredient_id = (request.POST.get("ingredient_id") or "").strip()
        new_name = (request.POST.get("new_ingredient_name") or "").strip()
        category = (request.POST.get("category") or "other").strip() or "other"
        if ingredient_id:
            ingredient = Ingredient.objects.filter(pk=ingredient_id).first()
        if ingredient is None and new_name:
            ingredient = get_or_create_ingredient(new_name, category=category)
        if ingredient is None:
            messages.error(request, "Choose an ingredient or enter a new one to add.")
            return redirect("meals:pantry")

        # 2. Quantity / unit / storage location.
        try:
            quantity = Decimal(str(request.POST.get("quantity") or "1"))
        except Exception:
            quantity = Decimal("1")
        if quantity <= 0:
            quantity = Decimal("1")
        unit = (request.POST.get("unit") or "piece").strip() or "piece"
        storage_location = (request.POST.get("storage_location") or "").strip() or None

        # 3. Canonical write — the exact same PantryItem as every other acquisition path.
        pantry_item, created = finalize_pantry_item(
            household=household,
            ingredient=ingredient,
            quantity=quantity,
            unit=unit,
            confidence_score=Decimal("1.0"),  # user-entered → fully confident
            storage_location=storage_location,
            source="manual",
            notes="Manual entry",
        )

        # Honor an explicit location even on an existing item (finalize only upgrades from
        # "unknown"); mirrors the barcode path.
        if storage_location and not created and pantry_item.storage_location != storage_location:
            pantry_item.storage_location = storage_location
            pantry_item.save(update_fields=["storage_location", "updated_at"])

        # 4. Optional Container Truth captured up front (Capture Once, Reuse Everywhere).
        raw_amount = (request.POST.get("net_content_amount") or "").strip()
        raw_unit = (request.POST.get("net_content_unit") or "").strip().lower()
        container_type = (request.POST.get("container_type") or "").strip()
        if raw_amount and raw_unit:
            try:
                amount = Decimal(raw_amount)
            except Exception:
                amount = None
            capture_container_truth(pantry_item, amount, raw_unit, container_type=container_type)

        # 5. Optional explicit expiration — never invented.
        raw_exp = (request.POST.get("expiration_date") or "").strip()
        if raw_exp:
            from django.utils.dateparse import parse_date

            exp = parse_date(raw_exp)
            if exp:
                pantry_item.expiration_date_estimated = exp
                pantry_item.save(update_fields=["expiration_date_estimated", "updated_at"])

        messages.success(request, f"Added {ingredient.canonical_name} to your pantry.")
        return redirect("meals:pantry")


class PantryBarcodeLookupView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """
    Create/update a pantry item from a barcode scan.

    The client scans a barcode via the /scan/barcode/ endpoint first,
    gets product data back, then POSTs here to create the PantryItem.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(
                {"status": "error", "message": "Invalid JSON"}, status=400
            )

        barcode = data.get("barcode", "").strip()
        product_name = data.get("product_name", "").strip()
        if not barcode or not product_name:
            return JsonResponse(
                {"status": "error", "message": "barcode and product_name are required"},
                status=400,
            )

        brand = data.get("brand", "").strip()
        category = data.get("category", "").strip()
        user_storage = data.get("storage_location", "").strip()

        household = self.get_household()

        # Resolve or create ingredient
        from apps.meals.services.ingredient_matching import get_or_create_ingredient

        ingredient = get_or_create_ingredient(
            product_name, category=category or "other"
        )

        # Determine storage location
        from apps.meals.services.storage_classifier import (
            determine_storage_location,
            save_user_override,
        )

        if user_storage:
            storage_location = user_storage
            save_user_override(product_name, storage_location, user=request.user)
        else:
            storage_location = determine_storage_location(product_name, category)

        # Finalize through the canonical pantry ingestion helper so all
        # entry points (receipt, barcode, photo scan) share the same write.
        from apps.meals.services.pantry_ingestion import finalize_pantry_item

        pantry_item, created = finalize_pantry_item(
            household=household,
            ingredient=ingredient,
            quantity=Decimal("1"),
            unit="piece",
            confidence_score=Decimal("0.95"),
            storage_location=storage_location,
            source="barcode",
            notes=f"Barcode scan: {barcode}" + (f" ({brand})" if brand else ""),
        )

        # If the user explicitly picked a storage location in the barcode
        # modal, honor it even on existing items. finalize_pantry_item only
        # upgrades storage from "unknown" by default.
        if (
            user_storage
            and not created
            and pantry_item.storage_location != user_storage
        ):
            pantry_item.storage_location = user_storage
            pantry_item.save(update_fields=["storage_location", "updated_at"])

        logger.info(
            "Barcode pantry item %s for household %d: %s (barcode=%s)",
            "created" if created else "updated",
            household.pk,
            product_name,
            barcode,
        )

        return JsonResponse({
            "status": "ok",
            "pantry_item_id": pantry_item.pk,
            "product_name": product_name,
            "storage_location": pantry_item.storage_location,
            "created": created,
        })


# =============================================================================
# Meal Plan View
# =============================================================================


class MealPlanView(
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, TemplateView
):
    """
    Weekly meal planner with calendar grid.

    7-day default view with meal assignments, protein distribution,
    and grocery impact preview.
    """

    template_name = "meals/meal_plan.html"
    help_context_id = "MEALS_PLAN"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        household = self.get_household()
        dietary_profile = self.get_dietary_profile()
        today = timezone.now().date()

        # Get or generate active plan
        active_plan = (
            MealPlan.objects.filter(
                household=household,
                end_date__gte=today,
            )
            .order_by("-start_date")
            .first()
        )

        if active_plan:
            entries = (
                MealPlanEntry.objects.filter(meal_plan=active_plan)
                .select_related("recipe")
                .order_by("date", "meal_type")
            )

            # Build calendar grid
            days = []
            current = active_plan.start_date
            while current <= active_plan.end_date:
                day_entries = {
                    "date": current,
                    "is_today": current == today,
                    "day_name": current.strftime("%A"),
                    "day_short": current.strftime("%b %d"),
                    "breakfast": None,
                    "lunch": None,
                    "dinner": None,
                    "snack": None,
                }
                for entry in entries:
                    if entry.date == current:
                        day_entries[entry.meal_type] = entry
                days.append(day_entries)
                current += timedelta(days=1)

            context["plan"] = active_plan
            context["days"] = days
            context["has_plan"] = True
        else:
            context["has_plan"] = False

        # Available recipes for assignment
        context["user_recipes"] = Recipe.objects.filter(
            user=self.request.user
        ).order_by("title")[:50]

        context["household"] = household
        context["dietary_profile"] = dietary_profile
        context["today"] = today

        return context


class GeneratePlanView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """Generate a new weekly meal plan."""

    def post(self, request):
        household = self.get_household()
        dietary_profile = self.get_dietary_profile()
        today = timezone.now().date()

        user_recipes = list(Recipe.objects.filter(user=request.user)[:50])
        if not user_recipes:
            messages.warning(request, "Add some recipes first to generate a meal plan.")
            return redirect("meals:plan")

        from apps.meals.services.weekly_optimizer import (
            generate_meal_plan,
            save_meal_plan,
        )

        plan_result = generate_meal_plan(
            household=household,
            start_date=today,
            days=7,
            meal_types=["breakfast", "lunch", "dinner"],
            dietary_profile=dietary_profile,
            recipes=user_recipes,
        )

        save_meal_plan(household, plan_result, request.user)
        messages.success(request, "Meal plan generated for the next 7 days.")
        return redirect("meals:plan")


# =============================================================================
# Receipt Upload
# =============================================================================

# File validation constants (shared with pantry scan)
MAX_RECEIPT_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_RECEIPT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "application/pdf",
}


class ReceiptUploadView(
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, TemplateView
):
    """
    Receipt upload and history.

    Supports three ingestion modes:
    1. Camera capture (mobile)
    2. File upload (image or PDF, with drag-and-drop)
    3. Text paste (existing feature)

    All modes create a pending Receipt and redirect to confirmation.
    """

    template_name = "meals/receipt_upload.html"
    help_context_id = "MEALS_RECEIPTS"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        household = self.get_household()

        # Show confirmed and pending receipts in history
        context["receipts"] = (
            Receipt.objects.filter(household=household)
            .exclude(confirmation_status=Receipt.CONFIRM_CANCELLED)
            .order_by("-receipt_date", "-created_at")[:20]
        )
        context["household"] = household
        return context

    @staticmethod
    def _parse_date(date_str):
        """Parse date from receipt text, trying multiple formats."""
        if not date_str:
            return timezone.now().date()
        from datetime import datetime as dt

        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%m/%d/%y"):
            try:
                return dt.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return timezone.now().date()

    def post(self, request, *args, **kwargs):
        """Handle receipt submission (image or text)."""
        household = self.get_household()

        uploaded_file = request.FILES.get("receipt_image")
        raw_text = request.POST.get("receipt_text", "").strip()

        if uploaded_file:
            return self._process_image_upload(request, household, uploaded_file)
        elif raw_text:
            return self._process_text_upload(request, household, raw_text)
        else:
            messages.error(
                request, "Please upload a receipt image or paste receipt text."
            )
            return redirect("meals:receipts")

    def _process_image_upload(self, request, household, uploaded_file):
        """Handle image/PDF receipt upload via Vision AI."""
        # Validate file size
        if uploaded_file.size > MAX_RECEIPT_UPLOAD_SIZE:
            messages.error(request, "File too large. Maximum size is 10 MB.")
            return redirect("meals:receipts")

        # Validate file type
        content_type = uploaded_file.content_type or ""
        if content_type not in ALLOWED_RECEIPT_TYPES:
            messages.error(
                request,
                "Unsupported file type. Please upload a JPG, PNG, HEIC, or PDF.",
            )
            return redirect("meals:receipts")

        # Read file into memory (in-memory pattern from PantryScanStartView)
        raw_bytes = uploaded_file.read()

        # Check for duplicate receipt before processing
        from apps.meals.services.receipt_vision import compute_receipt_hash

        file_hash = compute_receipt_hash(raw_bytes)
        existing = Receipt.objects.filter(
            household=household,
            receipt_hash=file_hash,
        ).exclude(confirmation_status=Receipt.CONFIRM_CANCELLED).first()

        if existing:
            messages.warning(
                request,
                f"This receipt appears to be a duplicate of "
                f'"{existing.store or "Unknown Store"}" '
                f"({existing.receipt_date}).",
            )
            return redirect("meals:receipt_detail", pk=existing.pk)

        # Create receipt in "processing" state
        receipt = Receipt.objects.create(
            user=request.user,
            household=household,
            confirmation_status=Receipt.CONFIRM_PROCESSING,
            receipt_hash=file_hash,
            created_via=Receipt.CREATED_VIA_AI_CAMERA,
        )

        # Save the image to the receipt (Cloudinary in prod, local in dev)
        uploaded_file.seek(0)
        receipt.image.save(uploaded_file.name, uploaded_file, save=True)

        # Process synchronously — Vision API takes 3-8s, well within HTTP
        # timeout. This avoids Celery worker dependency and stuck-polling bugs.
        try:
            self._sync_process_image(receipt, raw_bytes, content_type, household)
        except Exception as e:
            logger.error(
                "Receipt %d sync processing failed: %s",
                receipt.pk,
                e,
                exc_info=True,
            )
            receipt.confirmation_status = Receipt.CONFIRM_FAILED
            receipt.processing_error = f"Processing failed: {e}"
            receipt.save(
                update_fields=[
                    "confirmation_status",
                    "processing_error",
                    "updated_at",
                ]
            )
            # Surface the failure to the user — without this they get
            # redirected to a FAILED receipt page with no explanation.
            # Truncate to avoid leaking stack-trace-like strings to UI.
            detail = str(e).splitlines()[0][:160] if str(e) else "Unknown error"
            messages.error(
                request,
                f"We couldn't read this receipt ({detail}). "
                "Try a clearer photo, or enter it manually.",
            )

        return redirect("meals:receipt_confirm", pk=receipt.pk)

    def _sync_process_image(self, receipt, raw_bytes, content_type, household):
        """Process receipt image synchronously via Vision AI."""
        from apps.meals.services.receipt_vision import ReceiptVisionService

        service = ReceiptVisionService()

        # Get Cloudinary URL if available — preferred path because
        # Cloudinary normalizes image format (handles HEIC→JPEG, etc.)
        image_url = None
        try:
            if receipt.image:
                url = receipt.image.url
                if url and url.startswith("http"):
                    image_url = url
        except Exception:
            pass

        if content_type == "application/pdf":
            vision_result = service.process_pdf(raw_bytes)
        else:
            vision_result = service.process_image(
                raw_bytes, content_type, image_url=image_url
            )

        if vision_result.error:
            receipt.confirmation_status = Receipt.CONFIRM_FAILED
            receipt.processing_error = vision_result.error
            receipt.save(
                update_fields=[
                    "confirmation_status",
                    "processing_error",
                    "updated_at",
                ]
            )
            return

        # Update receipt with vision results
        receipt.raw_text = vision_result.raw_text
        receipt.store = vision_result.store or ""
        receipt.total = vision_result.total or Decimal("0")
        receipt.subtotal = vision_result.subtotal
        receipt.tax_amount = vision_result.tax
        receipt.payment_method = vision_result.payment_method or ""
        receipt.receipt_type = vision_result.receipt_type
        receipt.receipt_date = self._parse_date(vision_result.date)
        receipt.parsed_json = {
            "store": vision_result.store,
            "date": vision_result.date,
            "items": vision_result.items,
            "source": vision_result.source,
        }
        receipt.confirmation_status = Receipt.CONFIRM_PENDING
        receipt.save()

        # Create ReceiptItem entries
        from apps.meals.services.ingredient_matching import match_ingredient_name

        for item_data in vision_result.items:
            name = item_data.get("name", "")
            if not name:
                continue

            match = match_ingredient_name(name)
            price = item_data.get("price")

            ReceiptItem.objects.create(
                receipt=receipt,
                ingredient=Ingredient.objects.filter(
                    pk=match.ingredient_id
                ).first()
                if match.ingredient_id
                else None,
                raw_name=name,
                raw_price=Decimal(str(price)) if price else None,
                quantity=Decimal(str(item_data.get("quantity", 1))),
                unit="each",
                match_confidence=match.confidence,
                category=item_data.get("category", ""),
            )

    def _process_text_upload(
        self, request, household, raw_text, uploaded_file=None, receipt_hash=""
    ):
        """Handle text paste (creates pending receipt for confirmation)."""
        import hashlib

        from apps.meals.services.receipt_parser import (
            match_receipt_items,
            parse_receipt_text,
        )

        # Compute hash for text-based deduplication
        if not receipt_hash:
            receipt_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

            # Check for duplicate
            existing = Receipt.objects.filter(
                household=household,
                receipt_hash=receipt_hash,
            ).exclude(confirmation_status=Receipt.CONFIRM_CANCELLED).first()

            if existing:
                messages.warning(
                    request,
                    f"This receipt text appears to be a duplicate of "
                    f'"{existing.store or "Unknown Store"}" '
                    f"({existing.receipt_date}).",
                )
                return redirect("meals:receipt_detail", pk=existing.pk)

        parsed = parse_receipt_text(raw_text)

        receipt = Receipt.objects.create(
            user=request.user,
            household=household,
            raw_text=raw_text,
            parsed_json={
                "store": parsed.store,
                "date": parsed.date,
                "items": [
                    {
                        "name": i.raw_name,
                        "price": float(i.price) if i.price else None,
                        "qty": float(i.quantity) if i.quantity else None,
                    }
                    for i in parsed.items
                ],
            },
            store=parsed.store or "",
            total=parsed.total or Decimal("0"),
            receipt_date=self._parse_date(parsed.date),
            receipt_type=Receipt.RECEIPT_TYPE_GROCERY,  # Default for text paste
            confirmation_status=Receipt.CONFIRM_PENDING,
            receipt_hash=receipt_hash,
        )

        # Save PDF if text was extracted from a PDF upload
        if uploaded_file:
            uploaded_file.seek(0)
            receipt.image.save(uploaded_file.name, uploaded_file, save=True)

        # Match items to ingredients
        matched = match_receipt_items(parsed)
        for item, match in matched:
            ReceiptItem.objects.create(
                receipt=receipt,
                ingredient=Ingredient.objects.filter(
                    pk=match.ingredient_id
                ).first()
                if match.ingredient_id
                else None,
                raw_name=item.raw_name,
                raw_price=item.price,
                quantity=item.quantity or Decimal("1"),
                unit=item.unit or "each",
                match_confidence=match.confidence if match else Decimal("0"),
            )

        messages.info(
            request,
            f"Receipt parsed with {len(parsed.items)} items. "
            f"Please review and confirm below.",
        )
        return redirect("meals:receipt_confirm", pk=receipt.pk)


class ReceiptDetailView(
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, DetailView
):
    """Show parsed receipt details with match confidence and routing summary."""

    template_name = "meals/receipt_detail.html"
    help_context_id = "MEALS_RECEIPTS"
    context_object_name = "receipt"

    def get_queryset(self):
        household = self.get_household()
        return Receipt.objects.filter(household=household)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        receipt = self.object
        context["items"] = receipt.items.all().select_related("ingredient")
        context["is_confirmed"] = (
            receipt.confirmation_status == Receipt.CONFIRM_CONFIRMED
        )
        context["is_pending"] = (
            receipt.confirmation_status == Receipt.CONFIRM_PENDING
        )

        # Show routing summary for confirmed receipts
        if context["is_confirmed"]:
            context["routed_to_pantry"] = receipt.receipt_type == "grocery"
            context["routed_to_health"] = receipt.receipt_type == "restaurant"
            context["routed_to_finance"] = receipt.receipt_type in (
                "grocery",
                "restaurant",
                "retail",
            )

        # Financial details
        context["has_financial_breakdown"] = bool(
            receipt.subtotal or receipt.tax_amount or receipt.payment_method
        )
        return context


# =============================================================================
# Receipt Confirmation
# =============================================================================


class ReceiptConfirmView(
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, TemplateView
):
    """
    Display parsed receipt items for user review and confirmation.

    GET: Show parsed items with editable fields, receipt type selector.
    POST: Confirm selected items, trigger domain routing.
    """

    template_name = "meals/receipt_confirm.html"
    help_context_id = "MEALS_RECEIPTS"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        household = self.get_household()
        receipt = get_object_or_404(
            Receipt,
            pk=self.kwargs["pk"],
            household=household,
            confirmation_status__in=[
                Receipt.CONFIRM_PENDING,
                Receipt.CONFIRM_PROCESSING,
                Receipt.CONFIRM_FAILED,
            ],
        )
        context["receipt"] = receipt
        context["items"] = receipt.items.all().select_related("ingredient")
        context["receipt_types"] = Receipt.RECEIPT_TYPE_CHOICES

        # Processing state for polling UI
        context["is_processing"] = (
            receipt.confirmation_status == Receipt.CONFIRM_PROCESSING
        )
        context["is_failed"] = (
            receipt.confirmation_status == Receipt.CONFIRM_FAILED
        )
        if context["is_processing"]:
            from django.urls import reverse

            context["status_url"] = reverse(
                "meals:receipt_processing_status", kwargs={"pk": receipt.pk}
            )

        return context

    def post(self, request, *args, **kwargs):
        household = self.get_household()
        receipt = get_object_or_404(
            Receipt,
            pk=self.kwargs["pk"],
            household=household,
            confirmation_status=Receipt.CONFIRM_PENDING,
        )

        action = request.POST.get("action")

        if action == "cancel":
            receipt.confirmation_status = Receipt.CONFIRM_CANCELLED
            receipt.save(update_fields=["confirmation_status", "updated_at"])
            messages.info(request, "Receipt cancelled.")
            return redirect("meals:receipts")

        # Get user-confirmed receipt type
        receipt_type = request.POST.get("receipt_type", receipt.receipt_type)

        # Get confirmed item IDs (checkboxes)
        confirmed_ids = [
            int(x) for x in request.POST.getlist("confirmed_items") if x.isdigit()
        ]

        # Get quantity/price overrides from editable fields
        quantity_overrides = {}
        price_overrides = {}
        for item_id in confirmed_ids:
            qty_val = request.POST.get(f"qty_{item_id}")
            price_val = request.POST.get(f"price_{item_id}")
            if qty_val:
                try:
                    quantity_overrides[item_id] = Decimal(qty_val)
                except Exception:
                    pass
            if price_val:
                try:
                    price_overrides[item_id] = Decimal(price_val)
                except Exception:
                    pass

        # Execute domain routing
        from apps.meals.services.receipt_routing import ReceiptRoutingService

        routing_service = ReceiptRoutingService()
        result = routing_service.route_receipt(
            receipt=receipt,
            household=household,
            receipt_type=receipt_type,
            confirmed_item_ids=confirmed_ids,
            quantity_overrides=quantity_overrides,
            price_overrides=price_overrides,
            user=request.user,
        )

        # Mark receipt confirmed
        receipt.receipt_type = receipt_type
        receipt.confirmation_status = Receipt.CONFIRM_CONFIRMED
        receipt.save(
            update_fields=["receipt_type", "confirmation_status", "updated_at"]
        )

        messages.success(request, result.summary_message)
        return redirect("meals:receipt_detail", pk=receipt.pk)


# =============================================================================
# Receipt Processing Status (async polling endpoint)
# =============================================================================


class ReceiptProcessingStatusView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """
    JSON endpoint for polling receipt processing status.

    Returns current status, progress percentage, and processing stage.
    Also provides a sync fallback: if processing is stuck > 8s with no
    progress, attempts sync processing directly (no locking needed since
    uploads now process synchronously — this is just a safety net).
    """

    def get(self, request, pk):
        household = self.get_household()

        try:
            receipt = Receipt.objects.get(pk=pk, household=household)
        except Receipt.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Not found"}, status=404)

        status = receipt.confirmation_status

        if status == Receipt.CONFIRM_PROCESSING:
            # Recovery: if the receipt is stuck (>8s, <25% progress), the worker
            # likely didn't pick up the task. RE-ENQUEUE it (fire-and-forget) —
            # NEVER run OpenAI Vision on this poll thread. Keep reporting
            # "processing" until the worker lands; the task is idempotent.
            age_seconds = (timezone.now() - receipt.created_at).total_seconds()

            if age_seconds > 8 and receipt.image and receipt.processing_progress < 25:
                from apps.core.celery_utils import safe_enqueue
                from apps.meals.tasks import process_receipt_image_task
                safe_enqueue(process_receipt_image_task, receipt.pk)

        response = {
            "status": status,
            "progress": receipt.processing_progress,
            "stage": receipt.processing_stage,
            "store": receipt.store,
            "receipt_type": receipt.receipt_type,
            "items_count": receipt.items.count(),
        }

        if status == Receipt.CONFIRM_FAILED:
            response["error"] = receipt.processing_error

        if status == Receipt.CONFIRM_PENDING:
            from django.urls import reverse

            response["redirect_url"] = reverse(
                "meals:receipt_confirm", kwargs={"pk": pk}
            )

        return JsonResponse(response)

    def _sync_process_receipt(self, receipt):
        """Sync fallback for stuck processing — reads image and runs Vision."""
        try:
            import mimetypes

            receipt.image.open("rb")
            raw_bytes = receipt.image.read()
            receipt.image.close()

            mime_type, _ = mimetypes.guess_type(receipt.image.name)
            content_type = mime_type or "image/jpeg"

            from apps.meals.services.receipt_vision import ReceiptVisionService

            service = ReceiptVisionService()

            # Get Cloudinary URL if available
            image_url = None
            try:
                url = receipt.image.url
                if url and url.startswith("http"):
                    image_url = url
            except Exception:
                pass

            if content_type == "application/pdf":
                vision_result = service.process_pdf(raw_bytes)
            else:
                vision_result = service.process_image(
                    raw_bytes, content_type, image_url=image_url
                )

            if vision_result.error:
                receipt.confirmation_status = Receipt.CONFIRM_FAILED
                receipt.processing_error = vision_result.error
                receipt.processing_progress = 0
                receipt.processing_stage = ""
                receipt.save(
                    update_fields=[
                        "confirmation_status", "processing_error",
                        "processing_progress", "processing_stage", "updated_at",
                    ]
                )
                return

            # Update receipt with vision results
            receipt.raw_text = vision_result.raw_text
            receipt.store = vision_result.store or ""
            receipt.total = vision_result.total or Decimal("0")
            receipt.subtotal = vision_result.subtotal
            receipt.tax_amount = vision_result.tax
            receipt.payment_method = vision_result.payment_method or ""
            receipt.receipt_type = vision_result.receipt_type
            receipt.confirmation_status = Receipt.CONFIRM_PENDING
            receipt.processing_error = ""
            receipt.processing_progress = 100
            receipt.processing_stage = Receipt.STAGE_COMPLETE
            receipt.save()

            # Create items
            from apps.meals.services.ingredient_matching import match_ingredient_name

            for item_data in vision_result.items:
                name = item_data.get("name", "")
                if not name:
                    continue
                match = match_ingredient_name(name)
                price = item_data.get("price")
                ReceiptItem.objects.create(
                    receipt=receipt,
                    ingredient=Ingredient.objects.filter(
                        pk=match.ingredient_id
                    ).first()
                    if match.ingredient_id
                    else None,
                    raw_name=name,
                    raw_price=Decimal(str(price)) if price else None,
                    quantity=Decimal(str(item_data.get("quantity", 1))),
                    unit="each",
                    match_confidence=match.confidence,
                    category=item_data.get("category", ""),
                )

            logger.info("Receipt %d sync fallback completed successfully", receipt.pk)

        except Exception as e:
            logger.error(
                "Receipt %d sync fallback failed: %s", receipt.pk, e, exc_info=True
            )
            receipt.confirmation_status = Receipt.CONFIRM_FAILED
            receipt.processing_error = f"Processing failed: {e}"
            receipt.processing_progress = 0
            receipt.processing_stage = ""
            receipt.save(
                update_fields=[
                    "confirmation_status", "processing_error",
                    "processing_progress", "processing_stage", "updated_at",
                ]
            )


# =============================================================================
# Receipt Delete
# =============================================================================


class ReceiptDeleteView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """
    Delete a receipt with cascade cleanup of routed data.

    For confirmed receipts, reverses downstream data:
    - Finance Transaction (matched by reference field)
    - FoodEntry for restaurant receipts (matched by notes + date)
    - InventoryTransactions for grocery receipts (matched by receipt items)
    """

    def post(self, request, pk):
        household = self.get_household()
        receipt = get_object_or_404(Receipt, pk=pk, household=household)

        cascade_parts = []

        # For confirmed receipts, reverse routed data before deleting
        if receipt.confirmation_status == Receipt.CONFIRM_CONFIRMED:
            cascade_parts = self._cascade_cleanup(receipt, request.user)

        # Delete receipt items (hard delete — they're child records)
        item_count = ReceiptItem.objects.filter(receipt=receipt).count()
        ReceiptItem.objects.filter(receipt=receipt).delete()

        # Soft-delete the receipt itself
        receipt.soft_delete()

        summary = f"Receipt deleted ({item_count} item{'s' if item_count != 1 else ''} removed)"
        if cascade_parts:
            summary += ". " + "; ".join(cascade_parts)
        messages.success(request, summary)

        return redirect("meals:receipts")

    def _cascade_cleanup(self, receipt, user):
        """Reverse downstream data created by receipt routing."""
        summary = []

        # 1. Finance Transaction — reliable match via reference field
        summary.extend(self._cleanup_finance(receipt))

        # 2. FoodEntry — restaurant receipts
        if receipt.receipt_type == "restaurant":
            summary.extend(self._cleanup_food_entries(receipt, user))

        # 3. InventoryTransactions — grocery receipts
        if receipt.receipt_type == "grocery":
            summary.extend(self._cleanup_inventory(receipt))

        return summary

    def _cleanup_finance(self, receipt):
        """Remove finance transactions created from this receipt."""
        try:
            from apps.finance.models import Transaction

            txns = Transaction.objects.filter(reference=f"receipt:{receipt.pk}")
            count = txns.count()
            if count:
                for txn in txns:
                    txn.soft_delete()
                return [f"{count} finance transaction(s) removed"]
        except ImportError:
            pass
        except Exception as e:
            logger.warning("Finance cleanup for receipt %d failed: %s", receipt.pk, e)
        return []

    def _cleanup_food_entries(self, receipt, user):
        """Remove food entries created from restaurant receipt routing."""
        try:
            from apps.health.models import FoodEntry

            entries = FoodEntry.objects.filter(
                user=user,
                notes__contains="From receipt:",
                logged_date=receipt.receipt_date,
            )
            if receipt.store:
                entries = entries.filter(notes__contains=receipt.store)

            count = entries.count()
            if count:
                for entry in entries:
                    entry.soft_delete()
                return [f"{count} food log(s) removed"]
        except ImportError:
            pass
        except Exception as e:
            logger.warning("FoodEntry cleanup for receipt %d failed: %s", receipt.pk, e)
        return []

    def _cleanup_inventory(self, receipt):
        """Reverse inventory transactions from grocery receipt routing."""
        try:
            receipt_items = ReceiptItem.objects.filter(
                receipt=receipt
            ).select_related("ingredient")
            ingredient_ids = [
                item.ingredient_id for item in receipt_items if item.ingredient_id
            ]

            if not ingredient_ids:
                return []

            pantry_items = PantryItem.objects.filter(
                household=receipt.household,
                ingredient_id__in=ingredient_ids,
            )

            txns = InventoryTransaction.objects.filter(
                pantry_item__in=pantry_items,
                source="receipt",
                notes__contains="From receipt:",
            )
            if receipt.store:
                txns = txns.filter(notes__contains=receipt.store)

            count = txns.count()
            if count:
                # Reverse pantry quantities
                for txn in txns:
                    pi = txn.pantry_item
                    pi.quantity = max(Decimal("0"), pi.quantity - txn.delta_quantity)
                    pi.save(update_fields=["quantity", "updated_at"])
                txns.delete()
                return [f"{count} inventory transaction(s) reversed"]
        except Exception as e:
            logger.warning(
                "Inventory cleanup for receipt %d failed: %s", receipt.pk, e
            )
        return []


# =============================================================================
# Recipe Intelligence Detail
# =============================================================================


class RecipeIntelligenceDetailView(
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, DetailView
):
    """
    Enhanced recipe detail with nutrition, scoring, inventory gaps,
    and substitution suggestions.
    """

    template_name = "meals/recipe_detail.html"
    help_context_id = "MEALS_RECIPE_DETAIL"
    context_object_name = "recipe"

    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recipe = self.object
        household = self.get_household()
        dietary_profile = self.get_dietary_profile()

        # Structured ingredients
        context["structured_ingredients"] = (
            RecipeIngredient.objects.filter(recipe=recipe)
            .select_related("ingredient")
            .order_by("order_index")
        )

        # Nutrition
        from apps.meals.services.recipe_nutrition import (
            calculate_recipe_nutrition,
            get_recipe_macro_summary,
        )

        context["nutrition"] = get_recipe_macro_summary(recipe)
        context["nutrition_detail"] = calculate_recipe_nutrition(recipe)

        # Scoring
        from apps.meals.services.meal_scoring import score_recipe

        meal_score = score_recipe(
            recipe, household, dietary_profile, available_minutes=60
        )
        context["meal_score"] = meal_score
        # Convert factors list to dict for template rendering
        context["meal_score"].factor_scores = {
            f.name: float(f.weighted_value) for f in meal_score.factors
        }

        # Inventory gaps
        from apps.meals.services.inventory_gap import analyze_recipe_gaps

        context["gap_analysis"] = analyze_recipe_gaps(recipe, household)

        # Substitutions for missing ingredients
        from apps.meals.services.substitution_engine import find_substitutions

        substitutions = {}
        for gap in context["gap_analysis"].gaps:
            if gap.gap_type == "missing":
                ingredient = Ingredient.objects.filter(
                    canonical_name=gap.ingredient_name
                ).first()
                if ingredient:
                    subs = find_substitutions(
                        ingredient, household, dietary_profile
                    )
                    if subs:
                        substitutions[gap.ingredient_name] = subs
        context["substitutions"] = substitutions

        # Idempotency key for the "record preparation" form — a re-submit of the SAME
        # rendered form (double-click / back-and-resubmit) replays instead of double-deducting.
        import uuid
        context["preparation_idempotency_key"] = uuid.uuid4().hex

        return context


class PrepareRecipeView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """Record that the household prepared a recipe (Foundation 2 execution spine).

    Deducts the recipe's structured ingredients from the pantry through the canonical
    InventoryTransaction authority and records leftovers. Fail-closed + idempotent
    (handled in the service). Synchronous, deterministic, bounded — request-path-safe.
    """

    def post(self, request, pk):
        from apps.meals.services.preparation import prepare_recipe

        household = self.get_household()
        recipe = get_object_or_404(Recipe, pk=pk, user=request.user)

        def _dec(field_name):
            raw = (request.POST.get(field_name) or "").strip()
            if not raw:
                return None
            try:
                return Decimal(raw)
            except Exception:
                return None

        result = prepare_recipe(
            household=household,
            user=request.user,
            recipe=recipe,
            servings=_dec("servings"),
            leftover_servings=_dec("leftover_servings"),
            idempotency_key=(request.POST.get("idempotency_key") or "").strip() or None,
            notes=(request.POST.get("notes") or "").strip(),
        )
        import uuid
        return render(request, "meals/preparation_result.html", {
            "recipe": recipe,
            "result": result,
            "consumption_idempotency_key": uuid.uuid4().hex,
        })


class ConsumeMealView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """Record that a person ate servings of a prepared meal (Foundation 2 consumption
    bridge): creates a canonical health.FoodEntry (nutrition) and reduces leftovers.
    Idempotent + fail-closed (in the service). Synchronous, deterministic — safe."""

    def post(self, request, prep_pk):
        from apps.meals.services.consumption import consume_meal

        household = self.get_household()
        prep = get_object_or_404(PreparationEvent, pk=prep_pk, household=household)

        raw = (request.POST.get("servings") or "").strip()
        try:
            servings = Decimal(raw) if raw else Decimal("1")
        except Exception:
            servings = Decimal("1")

        result = consume_meal(
            user=request.user,
            household=household,
            preparation=prep,
            servings=servings,
            meal_type=(request.POST.get("meal_type") or "").strip() or None,
            idempotency_key=(request.POST.get("idempotency_key") or "").strip() or None,
        )
        return render(request, "meals/consumption_result.html", {
            "preparation": prep,
            "result": result,
        })


# =============================================================================
# Foundation 2 — Leftovers inventory (list / detail / consume / discard)
# =============================================================================


class LeftoverListView(HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin,
                       PageSummaryMixin, ListView):
    """Available leftovers — a durable, returnable truth surface. Overview page →
    facts-only Current Context summary (summary:meals.leftovers)."""

    template_name = "meals/leftovers_list.html"
    context_object_name = "leftovers"
    page_summary_key = "meals.leftovers"
    page_summary_title = "Leftovers"
    help_context_id = "MEALS_LEFTOVERS"

    def get_queryset(self):
        from apps.meals.services.leftover_queries import available_leftovers
        return available_leftovers(self.get_household())

    def get_context_data(self, **kwargs):
        import uuid
        context = super().get_context_data(**kwargs)
        context["action_idempotency_key"] = uuid.uuid4().hex
        return context


class LeftoverDetailView(HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin,
                         DetailView):
    """One leftover (canonical object). base.html auto-declares Current Context from
    the UserOwnedModel's context_ref."""

    template_name = "meals/leftover_detail.html"
    context_object_name = "leftover"
    help_context_id = "MEALS_LEFTOVER_DETAIL"

    def get_queryset(self):
        return Leftover.objects.filter(
            household=self.get_household(), status="active",
        ).select_related("recipe", "preparation")

    def get_context_data(self, **kwargs):
        import uuid
        context = super().get_context_data(**kwargs)
        context["action_idempotency_key"] = uuid.uuid4().hex
        context["waste_events"] = self.object.waste_events.all()
        context["consumptions"] = self.object.consumptions.all()
        return context


class ConsumeLeftoverView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """Eat servings of an existing leftover on a later date (reuses consume_meal)."""

    def post(self, request, pk):
        from apps.meals.services.consumption import consume_meal

        household = self.get_household()
        leftover = get_object_or_404(
            Leftover, pk=pk, household=household, status="active")

        raw = (request.POST.get("servings") or "").strip()
        try:
            servings = Decimal(raw) if raw else Decimal("1")
        except Exception:
            servings = Decimal("1")

        result = consume_meal(
            user=request.user, household=household, leftover=leftover,
            servings=servings,
            meal_type=(request.POST.get("meal_type") or "").strip() or None,
            idempotency_key=(request.POST.get("idempotency_key") or "").strip() or None,
        )
        return render(request, "meals/consumption_result.html", {
            "preparation": leftover.preparation, "result": result,
        })


class DiscardLeftoverView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """Discard servings of a leftover (waste truth — no FoodEntry, no pantry change)."""

    def post(self, request, pk):
        from apps.meals.services.waste import discard_leftover

        household = self.get_household()
        leftover = get_object_or_404(
            Leftover, pk=pk, household=household, status="active")

        raw = (request.POST.get("servings") or "").strip()
        servings = None
        if raw:
            try:
                servings = Decimal(raw)
            except Exception:
                servings = None

        result = discard_leftover(
            user=request.user, household=household, leftover=leftover,
            servings=servings,  # None = discard all remaining
            reason=(request.POST.get("reason") or "").strip(),
            idempotency_key=(request.POST.get("idempotency_key") or "").strip() or None,
        )
        return render(request, "meals/waste_result.html", {
            "leftover": leftover, "result": result,
        })


# =============================================================================
# Guided Setup Wizard
# =============================================================================


class MealsSetupView(
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, TemplateView
):
    """
    Guided setup wizard for meal intelligence activation.

    Three steps:
    1. Pantry — add items via receipt, photo, or manual entry
    2. Recipes — add recipes via URL, image, or manual entry
    3. Dietary Profile — confirm carb/protein targets
    """

    template_name = "meals/setup.html"
    help_context_id = "MEALS_SETUP"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        household = self.get_household()

        from apps.meals.services.activation import get_activation_status

        activation = get_activation_status(user, household)
        context["activation"] = activation
        context["household"] = household

        # Determine current step based on progress
        if activation.pantry_count < activation.pantry_required:
            context["current_step"] = 1
        elif activation.recipe_count < activation.recipe_required:
            context["current_step"] = 2
        else:
            context["current_step"] = 3

        # Dietary profile for step 3
        context["dietary_profile"] = self.get_dietary_profile()

        return context


# =============================================================================
# Phase 12: Pantry Photo Scan Views
# =============================================================================

MAX_PHOTOS_PER_SESSION = 5
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


class PantryScanStartView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """
    Start a new pantry scan session and process uploaded photos.

    POST: Create session with location_type, upload 1-5 images,
    process through Vision AI, redirect to confirmation page.
    """

    def post(self, request):
        household = self.get_household()
        location_type = request.POST.get("location_type", "").strip()

        # Validate location type
        valid_locations = [c[0] for c in PantryScanSession.LOCATION_CHOICES]
        if location_type not in valid_locations:
            return JsonResponse(
                {"status": "error", "message": "Invalid location type"},
                status=400,
            )

        # Validate files
        files = request.FILES.getlist("photos")
        if not files:
            return JsonResponse(
                {"status": "error", "message": "No photos uploaded"},
                status=400,
            )
        if len(files) > MAX_PHOTOS_PER_SESSION:
            return JsonResponse(
                {"status": "error", "message": f"Maximum {MAX_PHOTOS_PER_SESSION} photos per session"},
                status=400,
            )

        # Validate each file
        for f in files:
            if f.size > MAX_UPLOAD_SIZE_BYTES:
                return JsonResponse(
                    {"status": "error", "message": f"File '{f.name}' exceeds 10MB limit"},
                    status=400,
                )
            if f.content_type not in ALLOWED_IMAGE_TYPES:
                return JsonResponse(
                    {"status": "error", "message": f"File '{f.name}' is not a supported image type"},
                    status=400,
                )

        # Create session
        session = PantryScanSession.objects.create(
            household=household,
            location_type=location_type,
        )

        # Read files into memory and process directly — avoids Cloudinary round-trip
        # which has been unreliable for Vision API reads.
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        inline_failures = 0
        for f in files:
            raw_bytes = f.read()
            content_type = f.content_type or "image/jpeg"

            try:
                # Create upload record (save image to Cloudinary as backup only)
                f.seek(0)
                upload = PantryPhotoUpload.objects.create(session=session, image=f)
            except Exception as e:
                # Cloudinary save failed — create record without image
                logger.warning(
                    "Cloudinary save failed for session %d, creating without image: %s",
                    session.pk, e,
                )
                upload = PantryPhotoUpload.objects.create(session=session)

            # Process from in-memory bytes — this is the primary path
            try:
                pantry_photo_detection_service.process_from_memory(
                    upload, raw_bytes, content_type
                )
            except Exception as e:
                inline_failures += 1
                logger.error(
                    "Failed to process photo for session %d: %s",
                    session.pk, e, exc_info=True,
                )

        # If any uploads still unprocessed, dispatch Celery as backup
        unprocessed_count = session.uploads.filter(processed=False).count()
        dispatch_failed = False
        if unprocessed_count > 0:
            from apps.meals.tasks import process_pantry_scan_task
            try:
                process_pantry_scan_task.delay(session.pk)
            except Exception as e:
                # Fail-loud: inline path already had errors, and the Celery
                # fallback cannot be dispatched. Log with exc_info so ops can
                # see the broker failure in production.
                dispatch_failed = True
                logger.error(
                    "Pantry scan Celery dispatch failed for session %d: %s",
                    session.pk, e, exc_info=True,
                )

        # Surface failure state to the user via flash messages so the
        # confirm page shows actionable text instead of an empty detection list.
        if inline_failures and dispatch_failed:
            messages.error(
                request,
                "We couldn't analyze your pantry photos. "
                "Please try again in a moment — if the problem persists, "
                "contact support.",
            )
        elif inline_failures and unprocessed_count == 0:
            # Inline failed but something got processed (partial success).
            messages.warning(
                request,
                "Some photos could not be processed. "
                "Check the detections below and rescan if needed.",
            )
        elif unprocessed_count > 0 and not dispatch_failed:
            # Inline timed out / failed, but backup is queued
            messages.info(
                request,
                "Analysis is still running in the background. "
                "Refresh this page in a few seconds to see detections.",
            )

        # Redirect to confirmation page
        from django.urls import reverse
        return redirect(reverse("meals:pantry_scan_confirm", kwargs={"session_id": session.pk}))


class PantryScanConfirmView(
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, TemplateView
):
    """
    Display detections for user confirmation.

    GET: Show detections with editable fields.
    POST: Confirm selected detections, create PantryItems.
    """

    template_name = "meals/pantry_scan_confirm.html"
    help_context_id = "MEALS_PANTRY"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        household = self.get_household()
        session_id = self.kwargs["session_id"]

        session = get_object_or_404(
            PantryScanSession, pk=session_id, household=household
        )

        # If already completed, show read-only summary
        if session.completed_at:
            context["session"] = session
            context["completed"] = True
            context["processing"] = False
            context["detections"] = session.detections.select_related(
                "matched_ingredient", "upload"
            ).all()
            return context

        # Check if still processing (unprocessed uploads remain)
        total_uploads = session.uploads.count()
        processed_uploads = session.uploads.filter(processed=True).count()
        still_processing = total_uploads > 0 and processed_uploads < total_uploads

        if still_processing:
            # Recovery: if the session is stuck (>30s), the worker likely didn't
            # pick up the task. RE-ENQUEUE it (fire-and-forget) — NEVER run
            # OpenAI Vision on this page-render thread. The page shows the
            # "processing" state and its poll drives completion.
            age_seconds = (timezone.now() - session.created_at).total_seconds()
            if age_seconds > 30:
                from apps.core.celery_utils import safe_enqueue
                from apps.meals.tasks import process_pantry_scan_task
                safe_enqueue(process_pantry_scan_task, session.pk)

            if still_processing:
                context["session"] = session
                context["processing"] = True
                context["completed"] = False
                context["total_uploads"] = total_uploads
                context["processed_uploads"] = processed_uploads
                return context

        detections = list(session.detections.select_related(
            "matched_ingredient", "upload"
        ).all())

        # Build ingredient choices for dropdown
        ingredients = Ingredient.objects.all().order_by("canonical_name").values_list(
            "id", "canonical_name"
        )

        # Check which detected ingredients already exist in pantry
        existing_ingredient_ids = set(
            PantryItem.objects.filter(
                household=household, quantity__gt=0,
            ).values_list("ingredient_id", flat=True)
        )
        for det in detections:
            det.already_in_pantry = (
                det.matched_ingredient_id is not None
                and det.matched_ingredient_id in existing_ingredient_ids
            )

        context["session"] = session
        context["completed"] = False
        context["processing"] = False
        context["detections"] = detections
        context["ingredients"] = list(ingredients)

        return context

    def post(self, request, session_id):
        household = self.get_household()
        session = get_object_or_404(
            PantryScanSession, pk=session_id, household=household
        )

        if session.completed_at:
            messages.warning(request, "This scan session has already been completed.")
            return redirect("meals:pantry")

        action = request.POST.get("action", "confirm")

        if action == "cancel":
            from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service
            pantry_photo_detection_service.cancel_session(session)
            messages.info(request, "Scan session cancelled.")
            return redirect("meals:pantry")

        # Collect confirmed detection IDs
        confirmed_ids = []
        quantities = {}
        ingredient_overrides = {}

        for key, value in request.POST.items():
            if key.startswith("confirm_") and value == "on":
                try:
                    det_id = int(key.replace("confirm_", ""))
                    confirmed_ids.append(det_id)
                except ValueError:
                    continue

            if key.startswith("quantity_"):
                try:
                    det_id = int(key.replace("quantity_", ""))
                    quantities[det_id] = Decimal(str(value))
                except (ValueError, TypeError):
                    continue

            if key.startswith("ingredient_"):
                try:
                    det_id = int(key.replace("ingredient_", ""))
                    ing_id = int(value)
                    ingredient_overrides[det_id] = ing_id
                except (ValueError, TypeError):
                    continue

        if not confirmed_ids:
            messages.warning(request, "No items selected for confirmation.")
            return redirect("meals:pantry_scan_confirm", session_id=session.pk)

        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        created, updated = pantry_photo_detection_service.confirm_session(
            session, confirmed_ids, quantities, ingredient_overrides,
        )

        messages.success(
            request,
            f"Pantry updated: {created} new items, {updated} items updated. "
            f"Session confidence: {session.overall_confidence:.0%}",
        )
        return redirect("meals:pantry")


class PantryScanStatusView(LoginRequiredMixin, MealsHouseholdMixin, View):
    """
    JSON endpoint for polling scan session processing status.

    Returns: {processing: bool, total: int, processed: int, detections_count: int}
    """

    def get(self, request, session_id):
        household = self.get_household()
        try:
            session = PantryScanSession.objects.get(pk=session_id, household=household)
        except PantryScanSession.DoesNotExist:
            return JsonResponse({"error": "not_found"}, status=404)

        total = session.uploads.count()
        processed = session.uploads.filter(processed=True).count()
        still_unprocessed = total > 0 and processed < total

        # Sync fallback: if session older than 30s and still unprocessed,
        # Celery worker likely didn't pick up the task. Process one upload
        # Recovery: if the session is stuck (>30s, still unprocessed), the
        # worker likely didn't pick up the task. RE-ENQUEUE it (fire-and-forget)
        # — NEVER run OpenAI Vision on this poll thread. The task is idempotent
        # (already-processed uploads are skipped), so a duplicate enqueue is safe.
        if still_unprocessed:
            age_seconds = (timezone.now() - session.created_at).total_seconds()
            if age_seconds > 30:
                from apps.core.celery_utils import safe_enqueue
                from apps.meals.tasks import process_pantry_scan_task
                safe_enqueue(process_pantry_scan_task, session.pk)

        return JsonResponse({
            "processing": total > 0 and processed < total,
            "total": total,
            "processed": processed,
            "detections_count": session.detections.count(),
        })


class PantryScanSessionsView(
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, TemplateView
):
    """
    List all pantry scan sessions with pagination.
    """

    template_name = "meals/pantry_scan_sessions.html"
    help_context_id = "MEALS_PANTRY"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        household = self.get_household()

        sessions = PantryScanSession.objects.filter(
            household=household,
        ).order_by("-created_at")

        # Simple pagination (10 per page)
        page = self.request.GET.get("page", 1)
        try:
            page = max(1, int(page))
        except (ValueError, TypeError):
            page = 1

        per_page = 10
        total = sessions.count()
        start = (page - 1) * per_page
        end = start + per_page

        context["sessions"] = sessions[start:end]
        context["current_page"] = page
        context["total_pages"] = max(1, (total + per_page - 1) // per_page)
        context["has_next"] = end < total
        context["has_prev"] = page > 1

        # Confidence drift
        from apps.meals.services.pantry_photo_detection import pantry_scan_session_service
        context["pantry_confidence"] = pantry_scan_session_service.calculate_confidence_drift(household)

        return context
