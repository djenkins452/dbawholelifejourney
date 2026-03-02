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
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, TemplateView, View

from apps.help.mixins import HelpContextMixin
from apps.life.models import Recipe

from .models import (
    DietaryProfile,
    Household,
    HouseholdMembership,
    Ingredient,
    InventoryTransaction,
    MealPlan,
    MealPlanEntry,
    PantryItem,
    PantryPhotoDetection,
    PantryPhotoUpload,
    PantryScanSession,
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
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, TemplateView
):
    """
    Meal Intelligence Command Center.

    Shows tonight's recommendation, expiring items, grocery cycle status,
    and weekly nutrition overview.
    """

    template_name = "meals/dashboard.html"
    help_context_id = "MEALS_DASHBOARD"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
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
    Pantry Intelligence view — grouped by store section.

    Displays confidence scores, expiration badges, and inline actions.
    """

    template_name = "meals/pantry.html"
    help_context_id = "MEALS_PANTRY"

    # Map storage types to display sections
    SECTION_ORDER = [
        ("refrigerator", "Produce & Fresh"),
        ("freezer", "Frozen"),
        ("pantry", "Pantry Staples"),
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        household = self.get_household()

        items = (
            PantryItem.objects.filter(household=household, quantity__gt=0)
            .select_related("ingredient")
            .order_by("ingredient__category", "ingredient__canonical_name")
        )

        # Group by ingredient category for display
        CATEGORY_SECTIONS = {
            "protein": "Meat & Protein",
            "vegetable": "Produce",
            "fruit": "Produce",
            "dairy": "Dairy",
            "grain": "Pantry Staples",
            "fat": "Pantry Staples",
            "spice": "Spices & Seasonings",
            "condiment": "Condiments",
            "beverage": "Beverages",
            "frozen": "Frozen",
            "other": "Other",
        }

        sections = {}
        for item in items:
            category = item.ingredient.category if item.ingredient else "other"
            section_name = CATEGORY_SECTIONS.get(category, "Other")
            if section_name not in sections:
                sections[section_name] = []
            sections[section_name].append(item)

        # Sort sections in a sensible order
        SECTION_PRIORITY = [
            "Produce",
            "Meat & Protein",
            "Dairy",
            "Pantry Staples",
            "Spices & Seasonings",
            "Condiments",
            "Beverages",
            "Frozen",
            "Other",
        ]
        ordered_sections = []
        for name in SECTION_PRIORITY:
            if name in sections:
                ordered_sections.append((name, sections[name]))
        # Add any remaining
        for name, items_list in sections.items():
            if name not in SECTION_PRIORITY:
                ordered_sections.append((name, items_list))

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


class ReceiptUploadView(
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, TemplateView
):
    """
    Receipt upload and history.

    Supports manual text entry and shows match confidence for parsed items.
    """

    template_name = "meals/receipt_upload.html"
    help_context_id = "MEALS_RECEIPTS"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        household = self.get_household()

        # Recent receipts
        context["receipts"] = (
            Receipt.objects.filter(household=household)
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
        """Handle receipt text submission."""
        household = self.get_household()
        raw_text = request.POST.get("receipt_text", "").strip()

        if not raw_text:
            messages.error(request, "Please enter receipt text.")
            return redirect("meals:receipts")

        from apps.meals.services.receipt_parser import (
            match_receipt_items,
            parse_receipt_text,
            process_receipt_to_pantry,
        )

        # Parse the receipt
        parsed = parse_receipt_text(raw_text)

        # Create receipt record
        receipt = Receipt.objects.create(
            user=request.user,
            household=household,
            raw_text=raw_text,
            parsed_json={
                "store": parsed.store,
                "date": parsed.date,
                "items": [
                    {"name": i.name, "price": float(i.price) if i.price else None, "qty": float(i.quantity) if i.quantity else None}
                    for i in parsed.items
                ],
            },
            store=parsed.store or "",
            total=parsed.total or Decimal("0"),
            receipt_date=self._parse_date(parsed.date),
        )

        # Match items to ingredients
        matched = match_receipt_items(parsed)
        for item, match in matched:
            ReceiptItem.objects.create(
                receipt=receipt,
                ingredient=match.ingredient if match and match.ingredient else None,
                raw_name=item.name,
                raw_price=item.price,
                quantity=item.quantity or Decimal("1"),
                unit=item.unit or "each",
                match_confidence=match.confidence if match else Decimal("0"),
            )

        # Auto-update pantry
        created, updated = process_receipt_to_pantry(receipt, household)

        messages.success(
            request,
            f"Receipt processed: {created} new items added, {updated} items updated in pantry.",
        )
        return redirect("meals:receipt_detail", pk=receipt.pk)


class ReceiptDetailView(
    HelpContextMixin, LoginRequiredMixin, MealsHouseholdMixin, DetailView
):
    """Show parsed receipt details with match confidence."""

    template_name = "meals/receipt_detail.html"
    help_context_id = "MEALS_RECEIPTS"
    context_object_name = "receipt"

    def get_queryset(self):
        household = self.get_household()
        return Receipt.objects.filter(household=household)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["items"] = self.object.items.all().select_related("ingredient")
        return context


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

        return context


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

        # Read files into memory BEFORE any DB saves — avoids Cloudinary round-trip
        file_data = []
        for f in files:
            raw_bytes = f.read()
            file_data.append((raw_bytes, f.content_type or "image/jpeg"))

        # Process each photo from memory through detection service
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        for raw_bytes, content_type in file_data:
            try:
                # Create upload record without image (processed in-memory)
                upload = PantryPhotoUpload.objects.create(session=session)
                pantry_photo_detection_service.process_from_memory(
                    upload, raw_bytes, content_type
                )
            except Exception as e:
                logger.error(
                    "Failed to process photo for session %d: %s",
                    session.pk, e, exc_info=True,
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
            context["detections"] = session.detections.select_related(
                "matched_ingredient", "upload"
            ).all()
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
