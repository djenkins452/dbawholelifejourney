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

        # Create or update PantryItem
        pantry_item, created = PantryItem.objects.get_or_create(
            household=household,
            ingredient=ingredient,
            defaults={
                "quantity": Decimal("1"),
                "unit": "piece",
                "confidence_score": Decimal("0.95"),
                "last_confirmed_at": timezone.now(),
                "storage_location": storage_location,
            },
        )

        if not created:
            pantry_item.quantity += Decimal("1")
            pantry_item.confidence_score = Decimal("0.95")
            pantry_item.last_confirmed_at = timezone.now()
            if storage_location and storage_location != "unknown":
                pantry_item.storage_location = storage_location
            pantry_item.save(
                update_fields=[
                    "quantity",
                    "confidence_score",
                    "last_confirmed_at",
                    "storage_location",
                    "updated_at",
                ]
            )
        else:
            # Set estimated expiration for new items
            if ingredient.shelf_life_days:
                pantry_item.expiration_date_estimated = timezone.now().date() + timedelta(
                    days=ingredient.shelf_life_days
                )
                pantry_item.save(update_fields=["expiration_date_estimated"])

        # Log inventory transaction
        InventoryTransaction.objects.create(
            pantry_item=pantry_item,
            delta_quantity=Decimal("1"),
            source="barcode",
            notes=f"Barcode scan: {barcode}" + (f" ({brand})" if brand else ""),
        )

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

        # Dispatch async processing task
        try:
            from apps.meals.tasks import process_receipt_image_task

            process_receipt_image_task.delay(receipt.pk)
            logger.info(
                "Receipt %d dispatched for async processing", receipt.pk
            )
        except Exception as e:
            # Celery unavailable — fall back to sync processing
            logger.warning(
                "Celery dispatch failed for receipt %d, processing sync: %s",
                receipt.pk,
                e,
            )
            self._sync_process_image(receipt, raw_bytes, content_type, household)
            return redirect("meals:receipt_confirm", pk=receipt.pk)

        # Redirect to processing page (polls for completion)
        return redirect("meals:receipt_confirm", pk=receipt.pk)

    def _sync_process_image(self, receipt, raw_bytes, content_type, household):
        """Sync fallback when Celery is unavailable."""
        from apps.meals.services.receipt_vision import ReceiptVisionService

        service = ReceiptVisionService()

        if content_type == "application/pdf":
            vision_result = service.process_pdf(raw_bytes)
        else:
            vision_result = service.process_image(raw_bytes, content_type)

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
    Also provides a sync fallback: if processing is stuck > 30s with no
    progress, attempts sync processing with select_for_update locking.
    """

    def get(self, request, pk):
        from django.db import transaction

        household = self.get_household()

        try:
            receipt = Receipt.objects.get(pk=pk, household=household)
        except Receipt.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Not found"}, status=404)

        status = receipt.confirmation_status

        if status == Receipt.CONFIRM_PROCESSING:
            # Check if processing is stuck (> 10s old with no progress)
            age_seconds = (timezone.now() - receipt.created_at).total_seconds()

            if age_seconds > 10 and receipt.image and receipt.processing_progress < 25:
                # Try to claim ownership via select_for_update, then process
                # OUTSIDE the atomic block to avoid rolling back on failure.
                should_process = False
                try:
                    with transaction.atomic():
                        locked = (
                            Receipt.objects.select_for_update(skip_locked=True)
                            .filter(
                                pk=pk,
                                confirmation_status=Receipt.CONFIRM_PROCESSING,
                            )
                            .first()
                        )
                        if locked:
                            # Claim ownership by setting progress > 0
                            locked.processing_progress = 5
                            locked.processing_stage = "fallback"
                            locked.save(
                                update_fields=[
                                    "processing_progress",
                                    "processing_stage",
                                    "updated_at",
                                ]
                            )
                            should_process = True
                            logger.info(
                                "Receipt %d stuck for %.0fs, claiming for sync fallback",
                                pk,
                                age_seconds,
                            )
                        else:
                            logger.info(
                                "Receipt %d locked by another process, skipping fallback",
                                pk,
                            )
                except Exception as e:
                    logger.error(
                        "Receipt %d sync fallback lock failed: %s", pk, e
                    )

                # Process OUTSIDE the atomic block so saves aren't rolled back
                if should_process:
                    receipt.refresh_from_db()
                    self._sync_process_receipt(receipt)

                receipt.refresh_from_db()
                status = receipt.confirmation_status

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
        """Sync fallback for stuck async processing. Receipt must be locked."""
        try:
            import mimetypes

            receipt.image.open("rb")
            raw_bytes = receipt.image.read()
            receipt.image.close()

            mime_type, _ = mimetypes.guess_type(receipt.image.name)
            content_type = mime_type or "image/jpeg"

            from apps.meals.services.receipt_vision import ReceiptVisionService

            service = ReceiptVisionService()

            if content_type == "application/pdf":
                vision_result = service.process_pdf(raw_bytes)
            else:
                vision_result = service.process_image(raw_bytes, content_type)

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
            receipt.processing_error = f"Sync processing failed: {e}"
            receipt.processing_progress = 0
            receipt.processing_stage = ""
            receipt.save(
                update_fields=[
                    "confirmation_status", "processing_error",
                    "processing_progress", "processing_stage", "updated_at",
                ]
            )


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

        # Read files into memory and process directly — avoids Cloudinary round-trip
        # which has been unreliable for Vision API reads.
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

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
                logger.error(
                    "Failed to process photo for session %d: %s",
                    session.pk, e, exc_info=True,
                )

        # If any uploads still unprocessed, dispatch Celery as backup
        unprocessed_count = session.uploads.filter(processed=False).count()
        if unprocessed_count > 0:
            from apps.meals.tasks import process_pantry_scan_task
            try:
                process_pantry_scan_task.delay(session.pk)
            except Exception:
                pass  # Confirm page fallback will handle it

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
            # Safety fallback: if session is older than 30s and still unprocessed,
            # the Celery worker likely didn't pick up the task. Process sync.
            age_seconds = (timezone.now() - session.created_at).total_seconds()
            if age_seconds > 30:
                logger.warning(
                    "Pantry scan session %d stuck after %.0fs — processing sync fallback",
                    session.pk, age_seconds,
                )
                from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service
                for upload in session.uploads.filter(processed=False):
                    try:
                        pantry_photo_detection_service.process_upload(upload)
                    except Exception as e:
                        logger.error(
                            "Sync fallback failed for upload %d: %s",
                            upload.pk, e, exc_info=True,
                        )
                        upload.processed = True
                        upload.raw_detection_json = {"error": str(e)}
                        upload.save(update_fields=["processed", "raw_detection_json"])
                # Re-check after sync processing
                processed_uploads = session.uploads.filter(processed=True).count()
                still_processing = processed_uploads < total_uploads

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
        # per poll request to make incremental progress without blocking too long.
        if still_unprocessed:
            age_seconds = (timezone.now() - session.created_at).total_seconds()
            if age_seconds > 30:
                next_upload = session.uploads.filter(processed=False).first()
                if next_upload:
                    from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service
                    try:
                        pantry_photo_detection_service.process_upload(next_upload)
                    except Exception as e:
                        logger.error(
                            "Status poll sync fallback failed for upload %d: %s",
                            next_upload.pk, e, exc_info=True,
                        )
                        next_upload.processed = True
                        next_upload.raw_detection_json = {"error": str(e)}
                        next_upload.save(update_fields=["processed", "raw_detection_json"])
                    # Re-count
                    processed = session.uploads.filter(processed=True).count()

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
