"""
Whole Life Journey - Meal Intelligence Models

Project: Whole Life Journey
Path: apps/meals/models.py
Purpose: Models for the Meal Intelligence pillar

Description:
    Structured ingredient normalization, household management, pantry tracking,
    meal planning, receipt parsing, and meal scoring. Meal Intelligence owns the
    canonical Recipe model (moved here in Foundation 1B; table preserved as
    life_recipe) and bridges it with the FoodItem library (apps/health) to enable
    intelligent meal recommendations.

Key Models:
    Phase 1: Ingredient, RecipeIngredient
    Phase 2: Household, HouseholdMembership, DietaryProfile
    Phase 3: PantryItem, InventoryTransaction
    Phase 6: MealPlan, MealPlanEntry
    Phase 7: Receipt, ReceiptItem
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import SoftDeleteModel, TimeStampedModel, UserOwnedModel


# =============================================================================
# Phase 1: Ingredient Normalization
# =============================================================================

class Ingredient(TimeStampedModel):
    """
    Canonical ingredient in the system. Shared across all users.

    Maps a real-world ingredient (e.g., "chicken breast") to a normalized
    form with nutrition linkage, storage info, and substitution data.
    """

    CATEGORY_CHOICES = [
        ("protein", "Protein"),
        ("vegetable", "Vegetable"),
        ("fruit", "Fruit"),
        ("grain", "Grain/Carb"),
        ("dairy", "Dairy"),
        ("fat", "Fat/Oil"),
        ("spice", "Spice/Seasoning"),
        ("condiment", "Condiment/Sauce"),
        ("beverage", "Beverage"),
        ("legume", "Legume/Bean"),
        ("nut", "Nut/Seed"),
        ("sweetener", "Sweetener"),
        ("baking", "Baking"),
        ("other", "Other"),
    ]

    STORAGE_CHOICES = [
        ("pantry", "Pantry/Shelf"),
        ("refrigerator", "Refrigerator"),
        ("freezer", "Freezer"),
        ("counter", "Counter"),
    ]

    # Core identity
    canonical_name = models.CharField(
        max_length=200,
        unique=True,
        db_index=True,
        help_text="Normalized name (e.g., 'chicken breast')",
    )
    aliases = models.JSONField(
        default=list,
        blank=True,
        help_text='Alternative names: ["chicken", "boneless chicken", "pollo"]',
    )

    # Classification
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        db_index=True,
    )

    # Nutrition linkage
    nutrition_source = models.ForeignKey(
        "health.FoodItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ingredient_links",
        help_text="Primary FoodItem for nutrition data",
    )

    # Density values (per 100g standard)
    carb_density = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Carbs per 100g",
    )
    protein_density = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Protein per 100g",
    )

    # Storage & shelf life
    storage_type = models.CharField(
        max_length=20,
        choices=STORAGE_CHOICES,
        default="pantry",
    )
    shelf_life_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Typical shelf life in days",
    )

    # Substitution
    substitution_group = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Group for interchangeable ingredients (e.g., 'poultry')",
    )
    low_carb_alternative = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replaces",
        help_text="Lower-carb substitute for diabetes-aware planning",
    )

    # Default serving
    default_unit = models.CharField(
        max_length=30,
        default="g",
        help_text="Default measurement unit",
    )
    default_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("100"),
        help_text="Default quantity in default_unit",
    )

    class Meta:
        ordering = ["canonical_name"]
        verbose_name = "Ingredient"
        verbose_name_plural = "Ingredients"

    def __str__(self):
        return self.canonical_name

    def matches_text(self, text):
        """Check if text matches this ingredient's name or aliases."""
        text_lower = text.lower().strip()
        if text_lower == self.canonical_name.lower():
            return True
        return any(
            alias.lower() == text_lower
            for alias in (self.aliases or [])
        )


class Recipe(UserOwnedModel):
    """
    A recipe — the canonical operational food asset (Meal Intelligence owns it).

    Meal Intelligence owns what a recipe IS and how it functions (ingredients,
    instructions, servings, nutrition, prep, cost, planning). Legacy projects
    MEANING (family history, stories, traditions) onto it without owning the record.

    Moved here from apps.life in Foundation 1B (Recipe Ownership Migration); the
    physical table is preserved as ``life_recipe`` (no data migration). The recipe
    UI/URLs remain under the ``life`` namespace for now and present this
    Meal-Intelligence-owned model.
    """

    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(
        blank=True,
        help_text="Brief description or story behind this recipe"
    )

    # Recipe details
    ingredients = models.TextField(help_text="One ingredient per line")
    instructions = models.TextField()

    # Metadata
    prep_time_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Preparation time in minutes"
    )
    cook_time_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Cooking time in minutes"
    )
    servings = models.PositiveIntegerField(null=True, blank=True)
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        blank=True
    )

    # Organization
    category = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g., Breakfast, Dinner, Dessert, Holiday"
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tags like 'vegetarian', 'quick', 'family-favorite'"
    )

    # Source
    source = models.CharField(
        max_length=200,
        blank=True,
        help_text="Where did this recipe come from?"
    )
    source_url = models.URLField(blank=True)

    # Image
    image = models.ImageField(
        upload_to='life/recipes/',
        blank=True,
        null=True
    )

    # Personal notes
    notes = models.TextField(
        blank=True,
        help_text="Your variations, tips, or memories"
    )

    # Favorites
    is_favorite = models.BooleanField(default=False)

    class Meta:
        db_table = 'life_recipe'   # preserve the existing table (no data migration)
        ordering = ['-is_favorite', 'title']
        verbose_name = "Recipe"
        verbose_name_plural = "Recipes"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        # Recipe UI/URLs remain under the life namespace (presentation layer).
        return reverse('life:recipe_detail', kwargs={'pk': self.pk})

    @property
    def total_time_minutes(self):
        prep = self.prep_time_minutes or 0
        cook = self.cook_time_minutes or 0
        return prep + cook if (prep or cook) else None


class RecipeIngredient(TimeStampedModel):
    """
    Structured ingredient line for a Recipe.

    Connects a Recipe to an Ingredient with quantity, unit,
    and preparation notes. Replaces the plain-text ingredients field.
    """

    UNIT_CHOICES = [
        # Volume
        ("tsp", "teaspoon"),
        ("tbsp", "tablespoon"),
        ("fl_oz", "fluid ounce"),
        ("cup", "cup"),
        ("ml", "milliliter"),
        ("l", "liter"),
        # Weight
        ("g", "gram"),
        ("oz", "ounce"),
        ("lb", "pound"),
        ("kg", "kilogram"),
        # Count
        ("piece", "piece"),
        ("slice", "slice"),
        ("clove", "clove"),
        ("bunch", "bunch"),
        ("sprig", "sprig"),
        ("pinch", "pinch"),
        ("dash", "dash"),
        ("can", "can"),
        ("jar", "jar"),
        ("package", "package"),
        # Generic
        ("to_taste", "to taste"),
        ("as_needed", "as needed"),
    ]

    recipe = models.ForeignKey(
        "meals.Recipe",
        on_delete=models.CASCADE,
        related_name="structured_ingredients",
    )
    ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.PROTECT,
        related_name="recipe_uses",
    )

    # Quantity and measurement
    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Amount (null for 'to taste')",
    )
    unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default="piece",
    )

    # Preparation context
    preparation_notes = models.CharField(
        max_length=200,
        blank=True,
        help_text="e.g., 'diced', 'minced', 'room temperature'",
    )
    is_optional = models.BooleanField(default=False)

    # Ordering
    order_index = models.PositiveSmallIntegerField(default=0)

    # Original text (for audit trail)
    original_text = models.CharField(
        max_length=300,
        blank=True,
        help_text="Original free-text line before parsing",
    )
    parse_confidence = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("1.0"),
        help_text="Confidence of the parse (0-1)",
    )

    class Meta:
        ordering = ["order_index"]
        verbose_name = "Recipe Ingredient"
        verbose_name_plural = "Recipe Ingredients"
        unique_together = [("recipe", "ingredient", "order_index")]

    def __str__(self):
        qty = f"{self.quantity} " if self.quantity else ""
        unit = f"{self.get_unit_display()} " if self.unit != "piece" else ""
        prep = f", {self.preparation_notes}" if self.preparation_notes else ""
        return f"{qty}{unit}{self.ingredient.canonical_name}{prep}"


# =============================================================================
# Phase 2: Household Domain
# =============================================================================

class Household(TimeStampedModel):
    """
    A household unit for shared meal planning.

    Supports multi-user households where meal plans, pantry, and
    shopping lists are shared.
    """

    name = models.CharField(
        max_length=100,
        help_text="Household name (e.g., 'Jenkins Family')",
    )
    primary_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_households",
    )
    grocery_cycle_days = models.PositiveIntegerField(
        default=7,
        help_text="Typical days between grocery trips",
    )
    meals_activated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when meal intelligence met minimum activation threshold",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Household"
        verbose_name_plural = "Households"

    def __str__(self):
        return self.name


class HouseholdMembership(TimeStampedModel):
    """
    Links a user to a household with a role.
    """

    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("member", "Member"),
    ]

    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="household_memberships",
    )
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default="member",
    )

    class Meta:
        unique_together = [("household", "user")]
        verbose_name = "Household Membership"
        verbose_name_plural = "Household Memberships"

    def __str__(self):
        return f"{self.user} in {self.household} ({self.role})"


class DietaryProfile(UserOwnedModel):
    """
    Per-user dietary constraints and targets.

    Used by the meal scoring engine to personalize recommendations.
    """

    carb_limit_daily = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Max daily carbs in grams",
    )
    protein_target_daily = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Target daily protein in grams",
    )
    calorie_target = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Target daily calories",
    )
    fat_limit_daily = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Max daily fat in grams",
    )

    # Dietary flags
    dietary_flags = models.JSONField(
        default=list,
        blank=True,
        help_text='Flags: ["vegetarian", "gluten_free", "dairy_free", ...]',
    )

    # Diabetes awareness
    diabetes_sensitive = models.BooleanField(
        default=False,
        help_text="Enable diabetes-aware meal scoring (lower glycemic, carb-conscious)",
    )

    class Meta:
        verbose_name = "Dietary Profile"
        verbose_name_plural = "Dietary Profiles"

    def __str__(self):
        flags = ", ".join(self.dietary_flags) if self.dietary_flags else "none"
        return f"Dietary profile for {self.user}: {flags}"


# =============================================================================
# Phase 3: Pantry & Inventory
# =============================================================================

class PantryItem(TimeStampedModel):
    """
    Tracks an ingredient's presence in a household's pantry.

    Confidence decays over time since last confirmation. Expiration
    dates are estimated based on ingredient shelf life.
    """

    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="pantry_items",
    )
    ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.PROTECT,
        related_name="pantry_entries",
    )

    # Quantity
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal("0"),
    )
    unit = models.CharField(max_length=20, default="piece")

    # Confidence tracking
    confidence_score = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("1.0"),
        help_text="How confident we are this is still in stock (0-1)",
    )
    last_confirmed_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the user last confirmed this item's presence",
    )

    # Storage location
    STORAGE_PANTRY = "pantry"
    STORAGE_FRIDGE = "fridge"
    STORAGE_FREEZER = "freezer"
    STORAGE_OTHER = "other"
    STORAGE_UNKNOWN = "unknown"
    STORAGE_LOCATION_CHOICES = [
        (STORAGE_PANTRY, "Pantry"),
        (STORAGE_FRIDGE, "Fridge"),
        (STORAGE_FREEZER, "Freezer"),
        (STORAGE_OTHER, "Other"),
        (STORAGE_UNKNOWN, "Unknown"),
    ]
    storage_location = models.CharField(
        max_length=10,
        choices=STORAGE_LOCATION_CHOICES,
        default=STORAGE_UNKNOWN,
        db_index=True,
        help_text="Physical storage location (pantry, fridge, freezer)",
    )

    # Expiration
    expiration_date_estimated = models.DateField(
        null=True,
        blank=True,
        help_text="Estimated expiration based on shelf life",
    )

    class Meta:
        unique_together = [("household", "ingredient")]
        ordering = ["ingredient__canonical_name"]
        verbose_name = "Pantry Item"
        verbose_name_plural = "Pantry Items"

    def __str__(self):
        return f"{self.ingredient.canonical_name}: {self.quantity} {self.unit}"

    @property
    def is_expired(self):
        if not self.expiration_date_estimated:
            return False
        return self.expiration_date_estimated < timezone.now().date()

    @property
    def days_until_expiration(self):
        if not self.expiration_date_estimated:
            return None
        delta = self.expiration_date_estimated - timezone.now().date()
        return delta.days

    def decay_confidence(self):
        """Reduce confidence based on time since last confirmation."""
        if not self.last_confirmed_at:
            return
        days_since = (timezone.now() - self.last_confirmed_at).days
        # Lose ~5% confidence per day after 3 days
        if days_since > 3:
            decay = Decimal(str(min(0.05 * (days_since - 3), 0.80)))
            self.confidence_score = max(
                Decimal("0.10"),
                Decimal("1.0") - decay,
            )


class InventoryTransaction(TimeStampedModel):
    """
    Tracks changes to pantry item quantities.

    Every add/remove is logged for audit trail and pattern analysis.
    """

    SOURCE_CHOICES = [
        ("manual", "Manual Entry"),
        ("receipt", "Receipt Scan"),
        ("meal_plan", "Meal Plan Deduction"),
        ("preparation", "Meal Preparation"),
        ("expiration", "Expired Removal"),
        ("correction", "User Correction"),
        ("photo_scan", "Photo Scan"),
        ("barcode", "Barcode Scan"),
    ]

    pantry_item = models.ForeignKey(
        PantryItem,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    delta_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        help_text="Positive = added, negative = consumed/removed",
    )
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="manual",
    )
    # Provenance for preparation deductions (Foundation 2) — ties a deduction to the
    # PreparationEvent that produced it. Null for all other sources.
    preparation = models.ForeignKey(
        "meals.PreparationEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_transactions",
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Inventory Transaction"
        verbose_name_plural = "Inventory Transactions"

    def __str__(self):
        direction = "+" if self.delta_quantity > 0 else ""
        return f"{direction}{self.delta_quantity} {self.pantry_item.ingredient.canonical_name}"


class StorageOverride(TimeStampedModel):
    """
    User-defined storage location overrides for product names.

    When a user manually selects a storage location for an item that was
    classified as 'unknown', this saves the mapping for future auto-classification.
    Global (not per-household) since storage rules are product-inherent.
    """

    product_name_lower = models.CharField(
        max_length=200,
        unique=True,
        db_index=True,
        help_text="Lowercase product name for matching",
    )
    product_name_display = models.CharField(
        max_length=200,
        blank=True,
        help_text="Original casing for display",
    )
    storage_location = models.CharField(
        max_length=10,
        choices=PantryItem.STORAGE_LOCATION_CHOICES,
        help_text="User-selected storage location",
    )
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who set this override",
    )

    class Meta:
        verbose_name = "Storage Override"
        verbose_name_plural = "Storage Overrides"

    def __str__(self):
        return f"{self.product_name_display} → {self.storage_location}"


# =============================================================================
# Phase 6: Meal Planning
# =============================================================================

class MealPlan(UserOwnedModel):
    """
    A household meal plan for a date range.
    """

    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="meal_plans",
    )
    start_date = models.DateField()
    end_date = models.DateField()

    # Computed metadata
    projected_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )
    confidence_score = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("0.5"),
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "Meal Plan"
        verbose_name_plural = "Meal Plans"

    def __str__(self):
        return f"Meal Plan {self.start_date} to {self.end_date}"

    @property
    def day_count(self):
        return (self.end_date - self.start_date).days + 1


class MealPlanEntry(TimeStampedModel):
    """
    A single meal assignment within a meal plan.
    """

    MEAL_TYPE_CHOICES = [
        ("breakfast", "Breakfast"),
        ("lunch", "Lunch"),
        ("dinner", "Dinner"),
        ("snack", "Snack"),
    ]

    meal_plan = models.ForeignKey(
        MealPlan,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    date = models.DateField()
    meal_type = models.CharField(
        max_length=10,
        choices=MEAL_TYPE_CHOICES,
        default="dinner",
    )
    recipe = models.ForeignKey(
        "meals.Recipe",
        on_delete=models.CASCADE,
        related_name="meal_plan_entries",
    )
    serving_count = models.PositiveSmallIntegerField(default=1)

    # Snapshot at plan creation for historical accuracy
    inventory_impact_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Snapshot of ingredients needed vs available at plan time",
    )
    score = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Meal score when this entry was planned",
    )

    class Meta:
        ordering = ["date", "meal_type"]
        verbose_name = "Meal Plan Entry"
        verbose_name_plural = "Meal Plan Entries"

    def __str__(self):
        return f"{self.date} {self.get_meal_type_display()}: {self.recipe.title}"


# =============================================================================
# Phase 7: Receipt Parsing
# =============================================================================

class Receipt(UserOwnedModel):
    """
    A receipt parsed from OCR or text input.

    Supports image-based ingestion (camera/upload via Vision AI)
    and text-based ingestion (manual paste). Receipt type determines
    domain routing on confirmation.
    """

    # Receipt type classification
    RECEIPT_TYPE_GROCERY = "grocery"
    RECEIPT_TYPE_RESTAURANT = "restaurant"
    RECEIPT_TYPE_RETAIL = "retail"
    RECEIPT_TYPE_UNKNOWN = "unknown"
    RECEIPT_TYPE_CHOICES = [
        (RECEIPT_TYPE_GROCERY, "Grocery"),
        (RECEIPT_TYPE_RESTAURANT, "Restaurant"),
        (RECEIPT_TYPE_RETAIL, "Retail"),
        (RECEIPT_TYPE_UNKNOWN, "Unknown"),
    ]

    # Confirmation status (separate from SoftDeleteModel.status)
    CONFIRM_PROCESSING = "processing"
    CONFIRM_PENDING = "pending"
    CONFIRM_CONFIRMED = "confirmed"
    CONFIRM_CANCELLED = "cancelled"
    CONFIRM_FAILED = "failed"
    CONFIRM_CHOICES = [
        (CONFIRM_PROCESSING, "Processing"),
        (CONFIRM_PENDING, "Pending Confirmation"),
        (CONFIRM_CONFIRMED, "Confirmed"),
        (CONFIRM_CANCELLED, "Cancelled"),
        (CONFIRM_FAILED, "Processing Failed"),
    ]

    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="receipts",
    )
    raw_text = models.TextField(
        blank=True,
        help_text="Raw OCR text or pasted text from receipt",
    )
    parsed_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured parse result",
    )
    store = models.CharField(
        max_length=200,
        blank=True,
    )
    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    receipt_date = models.DateField(
        null=True,
        blank=True,
    )

    # Image upload (Phase: Receipt Ingestion)
    image = models.ImageField(
        upload_to="receipts/%Y/%m/",
        blank=True,
        null=True,
        help_text="Uploaded receipt image",
    )

    # Receipt type and status (Phase: Receipt Ingestion)
    receipt_type = models.CharField(
        max_length=20,
        choices=RECEIPT_TYPE_CHOICES,
        default=RECEIPT_TYPE_UNKNOWN,
        db_index=True,
        help_text="Classification determines domain routing",
    )
    confirmation_status = models.CharField(
        max_length=20,
        choices=CONFIRM_CHOICES,
        default=CONFIRM_PENDING,
        db_index=True,
    )

    # Financial breakdown (Phase: Receipt Hardening)
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Pre-tax subtotal from receipt",
    )
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Tax amount from receipt",
    )

    PAYMENT_METHOD_CHOICES = [
        ("", "Unknown"),
        ("cash", "Cash"),
        ("credit", "Credit Card"),
        ("debit", "Debit Card"),
        ("ebt", "EBT/SNAP"),
        ("mobile", "Mobile Pay"),
        ("other", "Other"),
    ]
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        blank=True,
        default="",
        help_text="Payment method detected from receipt",
    )

    # Processing progress tracking (for async receipt ingestion)
    STAGE_UPLOAD = "upload"
    STAGE_IMAGE_PROCESSING = "image_processing"
    STAGE_VISION_EXTRACTION = "vision_extraction"
    STAGE_ITEM_PARSING = "item_parsing"
    STAGE_CLASSIFICATION = "classification"
    STAGE_COMPLETE = "complete"
    STAGE_CHOICES = [
        (STAGE_UPLOAD, "Upload Complete"),
        (STAGE_IMAGE_PROCESSING, "Image Processing"),
        (STAGE_VISION_EXTRACTION, "Vision Extraction"),
        (STAGE_ITEM_PARSING, "Item Parsing"),
        (STAGE_CLASSIFICATION, "Classification"),
        (STAGE_COMPLETE, "Complete"),
    ]

    processing_progress = models.PositiveSmallIntegerField(
        default=0,
        help_text="Processing progress 0-100",
    )
    processing_stage = models.CharField(
        max_length=20,
        choices=STAGE_CHOICES,
        blank=True,
        default="",
        help_text="Current processing stage",
    )

    # Processing error message (for async failures)
    processing_error = models.TextField(
        blank=True,
        default="",
        help_text="Error message if async processing failed",
    )

    # Deduplication (Phase: Receipt Hardening)
    receipt_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="SHA-256 hash for deduplication",
    )
    duplicate_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicates",
        help_text="Original receipt if this is a detected duplicate",
    )

    # Link to scan if came from Vision AI
    scan_log = models.ForeignKey(
        "scan.ScanLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipts",
    )

    class Meta:
        ordering = ["-receipt_date", "-created_at"]
        verbose_name = "Receipt"
        verbose_name_plural = "Receipts"

    def __str__(self):
        store = self.store or "Unknown Store"
        date = self.receipt_date or "Unknown Date"
        return f"{store} - {date}"


class ReceiptItem(TimeStampedModel):
    """
    A single line item from a parsed receipt.
    """

    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.CASCADE,
        related_name="items",
    )
    ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipt_items",
        help_text="Matched ingredient (null if unmatched)",
    )

    # Raw data from receipt
    raw_name = models.CharField(max_length=300)
    raw_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # Parsed data
    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=Decimal("1"),
    )
    unit = models.CharField(max_length=20, default="piece")

    # Match confidence
    match_confidence = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Confidence of ingredient match (0-1)",
    )

    # Category from Vision AI classification
    category = models.CharField(
        max_length=50,
        blank=True,
        help_text="Item category (e.g., produce, dairy, meat)",
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "Receipt Item"
        verbose_name_plural = "Receipt Items"

    def __str__(self):
        return f"{self.raw_name} → {self.ingredient or 'unmatched'}"


# =============================================================================
# Phase 12: Pantry Photo Intelligence (Session-Based)
# =============================================================================


class PantryScanSession(TimeStampedModel):
    """
    A structured pantry scanning session.

    Each session represents a single scan event for a specific kitchen location
    (fridge, pantry shelf, or freezer). Contains 1-5 photo uploads, AI
    detections, and tracks confirmation status.
    """

    LOCATION_CHOICES = [
        ("fridge", "Fridge"),
        ("pantry", "Pantry Shelf"),
        ("freezer", "Freezer"),
    ]

    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="pantry_scan_sessions",
    )
    location_type = models.CharField(
        max_length=10,
        choices=LOCATION_CHOICES,
    )
    overall_confidence = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Average confidence of confirmed detections",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the session was confirmed/completed",
    )
    items_detected = models.PositiveIntegerField(
        default=0,
        help_text="Total items detected by AI",
    )
    items_confirmed = models.PositiveIntegerField(
        default=0,
        help_text="Items confirmed by user",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Pantry Scan Session"
        verbose_name_plural = "Pantry Scan Sessions"

    def __str__(self):
        loc = self.get_location_type_display()
        dt = self.created_at.strftime("%b %d, %I:%M %p") if self.created_at else "pending"
        return f"{loc} Scan — {dt}"


class PantryPhotoUpload(TimeStampedModel):
    """
    A single photo uploaded as part of a pantry scan session.

    Stores the image and raw detection output from Vision AI.
    """

    session = models.ForeignKey(
        PantryScanSession,
        on_delete=models.CASCADE,
        related_name="uploads",
    )
    image = models.ImageField(
        upload_to="pantry_scans/%Y/%m/",
        null=True,
        blank=True,
        help_text="Photo of pantry/fridge/freezer contents (optional — processed in-memory)",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(
        default=False,
        help_text="Whether Vision AI has processed this image",
    )
    raw_detection_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw detection output from Vision AI",
    )

    class Meta:
        ordering = ["uploaded_at"]
        verbose_name = "Pantry Photo Upload"
        verbose_name_plural = "Pantry Photo Uploads"

    def __str__(self):
        return f"Photo {self.pk} for {self.session}"


class PantryPhotoDetection(TimeStampedModel):
    """
    A single detected food item from a pantry photo.

    Represents an AI-detected item that requires user confirmation
    before being added to the pantry inventory.
    """

    session = models.ForeignKey(
        PantryScanSession,
        on_delete=models.CASCADE,
        related_name="detections",
    )
    upload = models.ForeignKey(
        PantryPhotoUpload,
        on_delete=models.CASCADE,
        related_name="detections",
    )
    detected_label = models.CharField(
        max_length=200,
        help_text="Label as detected by Vision AI",
    )
    matched_ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="photo_detections",
        help_text="Matched canonical ingredient (editable by user)",
    )
    confidence_score = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("0"),
        help_text="AI confidence in detection (0-1)",
    )
    suggested_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="AI-suggested quantity",
    )
    unit = models.CharField(
        max_length=20,
        blank=True,
        default="piece",
        help_text="Suggested unit for the quantity",
    )
    confirmed = models.BooleanField(
        default=False,
        help_text="User confirmed this detection",
    )
    rejected = models.BooleanField(
        default=False,
        help_text="User rejected this detection",
    )

    class Meta:
        ordering = ["-confidence_score"]
        verbose_name = "Pantry Photo Detection"
        verbose_name_plural = "Pantry Photo Detections"

    def __str__(self):
        status = "confirmed" if self.confirmed else ("rejected" if self.rejected else "pending")
        return f"{self.detected_label} ({status})"


# =============================================================================
# Foundation 2 — Preparation execution spine (household-scoped)
# =============================================================================

class PreparationEvent(UserOwnedModel):
    """A household preparation event: "we cooked recipe X".

    The first real execution event in the food lifecycle. Deducts pantry stock
    (through the canonical InventoryTransaction authority) and may produce
    Leftovers. Household-scoped supply truth; consumption/nutrition is a SEPARATE
    later increment and is NOT recorded here.

    ``preparation_status`` and ``deduction_status`` are distinct on purpose — a meal
    can be genuinely cooked (completed) even if the pantry could not be fully
    deducted (partial / skipped). We never record false completion.
    """

    PREP_INTENDED = "intended"
    PREP_COMPLETED = "completed"
    PREP_FAILED = "failed"
    PREPARATION_STATUS_CHOICES = [
        (PREP_INTENDED, "Intended"),
        (PREP_COMPLETED, "Completed"),
        (PREP_FAILED, "Failed"),
    ]

    DED_PENDING = "pending"
    DED_APPLIED = "applied"
    DED_PARTIAL = "partial"
    DED_SKIPPED = "skipped"
    DED_FAILED = "failed"
    DEDUCTION_STATUS_CHOICES = [
        (DED_PENDING, "Pending"),
        (DED_APPLIED, "Applied"),
        (DED_PARTIAL, "Partially applied"),
        (DED_SKIPPED, "Skipped (no structured ingredients)"),
        (DED_FAILED, "Failed"),
    ]

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="preparation_events",
    )
    recipe = models.ForeignKey(
        "meals.Recipe", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="preparation_events",
    )
    recipe_title = models.CharField(
        max_length=200, blank=True,
        help_text="Snapshot of the recipe title (provenance; survives recipe deletion)",
    )
    servings_prepared = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("1"),
        help_text="How many servings were prepared (scales the deduction)",
    )
    preparation_status = models.CharField(
        max_length=12, choices=PREPARATION_STATUS_CHOICES, default=PREP_COMPLETED,
    )
    deduction_status = models.CharField(
        max_length=12, choices=DEDUCTION_STATUS_CHOICES, default=DED_PENDING,
    )
    prepared_at = models.DateTimeField(default=timezone.now)
    idempotency_key = models.CharField(
        max_length=100, null=True, blank=True, unique=True, db_index=True,
        help_text="Client-supplied key; a repeat with the same key is a no-op replay",
    )
    deduction_summary = models.JSONField(
        default=dict, blank=True,
        help_text="Per-ingredient audit: required / available / deducted / shortage / "
                  "unsupported-conversion (deterministic provenance)",
    )
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-prepared_at"]
        verbose_name = "Preparation Event"
        verbose_name_plural = "Preparation Events"

    def __str__(self):
        return f"Prepared {self.recipe_title or 'recipe'} ({self.preparation_status})"


class Leftover(UserOwnedModel):
    """Deterministic leftover truth produced by an actual PreparationEvent.

    Recorded ONLY from a real preparation. Expiration and storage location are
    never invented — they stay null unless the user provides them.
    """

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="leftovers",
    )
    preparation = models.ForeignKey(
        PreparationEvent, on_delete=models.CASCADE, related_name="leftovers",
    )
    recipe = models.ForeignKey(
        "meals.Recipe", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="leftovers",
    )
    recipe_title = models.CharField(max_length=200, blank=True)
    servings = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("1"),
        help_text="Servings of leftovers remaining (as stated at preparation)",
    )
    # Optional, user-provided ONLY — never auto-invented.
    storage_location = models.CharField(
        max_length=10, choices=PantryItem.STORAGE_LOCATION_CHOICES,
        null=True, blank=True,
    )
    expiration_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Leftover"
        verbose_name_plural = "Leftovers"

    def __str__(self):
        return f"{self.servings} serving(s) of {self.recipe_title or 'a meal'}"


class MealConsumption(UserOwnedModel):
    """Person-scoped provenance link for eating a prepared meal (Foundation 2).

    Ties a consumption to (a) the PreparationEvent / Leftover it came from and (b) the
    canonical nutrition record it produced — ``health.FoodEntry`` (the SOLE nutrition
    authority; this model stores NO macros). Reducing leftovers, idempotency, and
    "which FoodEntry came from which preparation" live here; the nutrition itself
    lives in FoodEntry. Supports multiple consumptions from one preparation.
    """

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="meal_consumptions",
    )
    preparation = models.ForeignKey(
        PreparationEvent, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="consumptions",
    )
    leftover = models.ForeignKey(
        Leftover, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="consumptions",
    )
    recipe = models.ForeignKey(
        "meals.Recipe", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="consumptions",
    )
    recipe_title = models.CharField(max_length=200, blank=True)
    # The canonical nutrition record this consumption created (owned by Health).
    food_entry = models.ForeignKey(
        "health.FoodEntry", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="meal_consumptions",
    )
    servings_consumed = models.DecimalField(max_digits=6, decimal_places=2)
    meal_type = models.CharField(max_length=20, blank=True)
    consumed_at = models.DateTimeField(default=timezone.now)
    idempotency_key = models.CharField(
        max_length=100, null=True, blank=True, unique=True, db_index=True,
    )

    class Meta:
        ordering = ["-consumed_at"]
        verbose_name = "Meal Consumption"
        verbose_name_plural = "Meal Consumptions"

    def __str__(self):
        return f"Ate {self.servings_consumed} serving(s) of {self.recipe_title or 'a meal'}"
