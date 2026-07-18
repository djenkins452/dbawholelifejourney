# ==============================================================================
# File: apps/health/services/nutrition_queries.py
# Description: Canonical nutrition/food query service.
# Created: 2026-04-05
# ==============================================================================
"""
Canonical nutrition queries, meal-level aggregation, and meal signals.

This is the single source of truth for:
- Food entry queries (date, range)
- Meal-level subtotals (get_meal_totals)
- Deterministic meal-level nutrition signals (build_meal_signals)
"""

from decimal import Decimal

from django.db.models import Sum

from apps.health.models import FoodEntry


# ---------------------------------------------------------------------------
# Macro calorie conversion constants (standard Atwater factors)
# ---------------------------------------------------------------------------
CAL_PER_G_PROTEIN = Decimal("4")
CAL_PER_G_CARBS = Decimal("4")
CAL_PER_G_FAT = Decimal("9")

# ---------------------------------------------------------------------------
# Deterministic signal thresholds
# ---------------------------------------------------------------------------
SIGNAL_LOW_PROTEIN_G = Decimal("30")
SIGNAL_HIGH_PROTEIN_G = Decimal("50")
SIGNAL_HIGH_FAT_PCT = Decimal("0.40")       # >= 40% of calories from fat
SIGNAL_HIGH_CARB_PCT = Decimal("0.50")       # >= 50% of calories from carbs
SIGNAL_CALORIE_DENSE = Decimal("700")
SIGNAL_BALANCED_PROTEIN_G = Decimal("30")
SIGNAL_BALANCED_FAT_PCT = Decimal("0.35")    # < 35%
SIGNAL_BALANCED_CARB_PCT = Decimal("0.45")   # < 45%

# Signal label constants (stable keys for CoS consumption)
SIG_LOW_PROTEIN = "low_protein"
SIG_HIGH_PROTEIN = "high_protein"
SIG_HIGH_FAT = "high_fat"
SIG_HIGH_CARB = "high_carb"
SIG_CALORIE_DENSE = "calorie_dense"
SIG_BALANCED = "balanced"

# Human-readable display for each signal
SIGNAL_DISPLAY = {
    SIG_LOW_PROTEIN: {"icon": "\u26a0\ufe0f", "label": "Low protein", "tone": "warn"},
    SIG_HIGH_PROTEIN: {"icon": "\u2705", "label": "High protein", "tone": "good"},
    SIG_HIGH_FAT: {"icon": "\u26a0\ufe0f", "label": "High fat", "tone": "warn"},
    SIG_HIGH_CARB: {"icon": "\u26a0\ufe0f", "label": "High carb", "tone": "warn"},
    SIG_CALORIE_DENSE: {"icon": "\u26a0\ufe0f", "label": "Calorie dense", "tone": "warn"},
    SIG_BALANCED: {"icon": "\u2705", "label": "Balanced", "tone": "good"},
}

# Canonical meal type keys (matches FoodEntry.MEAL_* values)
MEAL_TYPES = (
    FoodEntry.MEAL_BREAKFAST,
    FoodEntry.MEAL_LUNCH,
    FoodEntry.MEAL_DINNER,
    FoodEntry.MEAL_SNACK,
)

# Zero totals template (reused when meal has no entries)
_ZERO_TOTALS = {
    "calories": Decimal("0"),
    "protein_g": Decimal("0"),
    "carbs_g": Decimal("0"),
    "fat_g": Decimal("0"),
}


class NutritionQueries:
    """Canonical, deterministic nutrition queries. No instance state."""

    @classmethod
    def entries_on_date(cls, user, target_date):
        """Active food entries logged on a specific date."""
        return FoodEntry.objects.filter(
            user=user, logged_date=target_date, status='active',
        )

    @classmethod
    def has_logged_on(cls, user, target_date):
        """Boolean: did user log food on this date?"""
        return cls.entries_on_date(user, target_date).exists()

    @classmethod
    def entries_in_range(cls, user, start_date, end_date):
        """Active food entries in a date range (inclusive)."""
        return FoodEntry.objects.filter(
            user=user,
            logged_date__gte=start_date,
            logged_date__lte=end_date,
            status='active',
        )

    @classmethod
    def last_entry(cls, user):
        """Most recent active food entry date, or None."""
        return FoodEntry.objects.filter(
            user=user, status='active',
        ).order_by('-logged_date', '-logged_time').first()

    # ------------------------------------------------------------------
    # Canonical meal-level aggregation
    # ------------------------------------------------------------------

    @classmethod
    def get_meal_totals(cls, user, target_date):
        """
        Canonical meal-level macro totals for a single date.

        Returns dict keyed by meal type string with Decimal values:
        {
            "breakfast": {"calories": D, "protein_g": D, "carbs_g": D, "fat_g": D},
            "lunch":     {...},
            "dinner":    {...},
            "snack":     {...},
        }

        This is the SINGLE SOURCE OF TRUTH for per-meal aggregation.
        All consumers (views, signals, future CoS) must call this.
        """
        entries = cls.entries_on_date(user, target_date)

        result = {}
        for meal_type in MEAL_TYPES:
            agg = entries.filter(meal_type=meal_type).aggregate(
                calories=Sum('total_calories'),
                protein_g=Sum('total_protein_g'),
                carbs_g=Sum('total_carbohydrates_g'),
                fat_g=Sum('total_fat_g'),
            )
            result[meal_type] = {
                "calories": agg["calories"] or Decimal("0"),
                "protein_g": agg["protein_g"] or Decimal("0"),
                "carbs_g": agg["carbs_g"] or Decimal("0"),
                "fat_g": agg["fat_g"] or Decimal("0"),
            }
        return result

    @classmethod
    def get_daily_totals(cls, user, target_date):
        """
        Canonical daily macro totals across all meals.

        Returns dict with Decimal values:
        {"calories": D, "protein_g": D, "carbs_g": D, "fat_g": D, "fiber_g": D, "sugar_g": D}
        """
        entries = cls.entries_on_date(user, target_date)
        agg = entries.aggregate(
            calories=Sum('total_calories'),
            protein_g=Sum('total_protein_g'),
            carbs_g=Sum('total_carbohydrates_g'),
            fat_g=Sum('total_fat_g'),
            fiber_g=Sum('total_fiber_g'),
            sugar_g=Sum('total_sugar_g'),
        )
        return {
            "calories": agg["calories"] or Decimal("0"),
            "protein_g": agg["protein_g"] or Decimal("0"),
            "carbs_g": agg["carbs_g"] or Decimal("0"),
            "fat_g": agg["fat_g"] or Decimal("0"),
            "fiber_g": agg["fiber_g"] or Decimal("0"),
            "sugar_g": agg["sugar_g"] or Decimal("0"),
        }

    # ── Point-in-Time History (per-day macro totals) ──────────────────────────────
    # Daily intake TOTAL per macro over a period, handed to the platform History
    # capability (apps.core.truth.history). This is the surface behind
    # NutritionDomainTruth.history(): it lets the CoS answer date-scoped totals ("how
    # many calories yesterday") and windowed averages ("average protein this week")
    # deterministically via get_history — closing the nutrition HISTORICAL/TIMELINE
    # gap measured in production (2026-07-18). ONE grouped query, request-path safe;
    # reuses the canonical FoodEntry macro fields. No new store, no per-day looping.
    _MACRO_FIELD = {
        "calories": "total_calories",
        "protein": "total_protein_g",
        "carbs": "total_carbohydrates_g",
        "fat": "total_fat_g",
        "fiber": "total_fiber_g",
        "sugar": "total_sugar_g",
    }
    _MACRO_UNIT = {"calories": "kcal", "protein": "g", "carbs": "g",
                   "fat": "g", "fiber": "g", "sugar": "g"}
    HISTORY_METRICS = tuple(_MACRO_FIELD)

    @classmethod
    def macro_series(cls, user, metric, period="last_7_days", *,
                     today=None, start=None, end=None):
        """Per-day intake total for `metric` (calories|protein|carbs|fat|fiber|sugar)
        over a resolved period, as a platform `HistorySeries`. The series aggregates
        (average/total/count) give the windowed average the CoS narrates — the mean of
        the per-DAY totals, so "average calories this week" is calories-per-day."""
        from apps.core.truth.history import series_from_rows
        from apps.core.truth.periods import resolve_period
        field = cls._MACRO_FIELD.get(metric)
        if field is None:
            raise KeyError(f"nutrition history unsupported: {metric!r} "
                           f"(have {cls.HISTORY_METRICS})")
        if today is None:
            from apps.core.utils import get_user_today
            today = get_user_today(user)
        p = resolve_period(period, today, start=start, end=end)
        rows = (FoodEntry.objects
                .filter(user=user, status="active",
                        logged_date__range=(p.start, p.end))
                .values("logged_date").annotate(v=Sum(field))
                .order_by("logged_date"))
        return series_from_rows(
            "nutrition", metric, p,
            [{"date": r["logged_date"], "value": round(float(r["v"] or 0), 1)}
             for r in rows],
            unit=cls._MACRO_UNIT[metric])

    # ── Entity Completeness Law (record-level "what I ate" for the Model Interface) ──
    # `describe` / `describe_one` return `CompleteEntity` objects — the actual FOODS the
    # user logged (name, brand, meal, macros). Before this, the Model Interface reached
    # nutrition AGGREGATES (targets, totals) but not the food items, so "what have I
    # eaten?" returned "no meal details" and personalized menus ignored the foods the
    # user actually eats (e.g. their 45g protein shake). This is the surface behind
    # NutritionDomainTruth.describe(); it lets the CoS reason FROM the user's real foods
    # instead of generic knowledge (personalization defect, 2026-07-17). Reuses the
    # canonical queries above; no new store.
    _DESCRIBE_LIMIT = 40   # recent foods across the last few days, newest-first

    @classmethod
    def describe(cls, user, *, limit=None, meal=None, period=None,
                start=None, end=None, contains=None, today=None):
        """Logged foods as CompleteEntity objects (newest-first). Deterministic
        SCOPING (so the answer is truth, not model inference):
          * meal      — 'breakfast'|'lunch'|'dinner'|'snack' → only that meal.
          * period    — a named period, OR start/end dates → only that window
                        ('every lunch this week', 'every dinner this month').
          * contains  — substring of food_name → only matching foods
                        ('how often have I eaten pizza' = len of the result).
        Unscoped, returns the recent bounded list as before."""
        qs = FoodEntry.objects.filter(user=user, status='active')
        if meal:
            qs = qs.filter(meal_type=meal)
        if contains:
            qs = qs.filter(food_name__icontains=contains)
        scoped = bool(period or start or end)
        if scoped:
            from apps.core.truth.periods import resolve_period
            if today is None:
                from apps.core.utils import get_user_today
                today = get_user_today(user)
            p = resolve_period(period or "custom", today, start=start, end=end)
            qs = qs.filter(logged_date__range=(p.start, p.end))
        qs = qs.order_by('-logged_date', '-logged_time', '-created_at')
        # A scoped query returns the FULL matching set (that IS the deterministic
        # answer); an unscoped browse stays bounded.
        if not scoped:
            qs = qs[: (limit or cls._DESCRIBE_LIMIT)]
        return [cls._to_entity(f) for f in qs]

    @classmethod
    def describe_one(cls, user, name):
        """The most recent logged food matching `name` (e.g. "protein shake"), as a
        `CompleteEntity`, or None — so the CoS cites the user's ACTUAL item + macros
        ("your protein shake is 45g protein"), never a generic assumption."""
        name = (name or "").strip()
        if not name:
            return None
        f = (FoodEntry.objects.filter(user=user, status='active',
                                      food_name__icontains=name)
             .order_by('-logged_date', '-logged_time').first())
        return cls._to_entity(f) if f else None

    @classmethod
    def _to_entity(cls, f):
        """One FoodEntry → a CompleteEntity across the contract dimensions."""
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity

        def _num(v):
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        name = (f.food_name or "").strip() or "Food"
        brand = (f.food_brand or "").strip()
        label = name + (f" ({brand})" if brand else "")
        return CompleteEntity(
            kind="food",
            identity=f"{label} — {f.logged_date}",
            definition={
                "date": f.logged_date,
                "meal_type": (f.meal_type or None),
                "food_name": name,
                "brand": brand or None,
                "quantity": _num(f.quantity),
                "serving_size": _num(f.serving_size),
                "serving_unit": (f.serving_unit or None),
            },
            status="eaten",
            performance={
                "calories": _num(f.total_calories),
                "protein_g": _num(f.total_protein_g),
                "carbohydrates_g": _num(f.total_carbohydrates_g),
                "fat_g": _num(f.total_fat_g),
                "fiber_g": _num(f.total_fiber_g),
                "sugar_g": _num(f.total_sugar_g),
            },
            freshness=F.CURRENT,
        )


def build_meal_signals(meal_totals):
    """
    Deterministic meal-level nutrition signals.

    Input: meal_totals dict from NutritionQueries.get_meal_totals()
    Output: dict keyed by meal type -> list of signal strings

    Example:
        {
            "breakfast": ["low_protein", "high_fat"],
            "lunch": [],
            "dinner": ["balanced"],
            "snack": ["calorie_dense"],
        }

    Rules are strict threshold-based. No heuristics, no LLM.
    Uses the SAME meal_totals input -- never re-queries.
    """
    signals = {}
    for meal_type, totals in meal_totals.items():
        meal_signals = []

        cal = totals["calories"]
        pro = totals["protein_g"]
        carb = totals["carbs_g"]
        fat = totals["fat_g"]

        # Skip empty meals (no entries)
        if cal <= 0:
            signals[meal_type] = meal_signals
            continue

        # Calorie-derived macro percentages
        fat_cal = fat * CAL_PER_G_FAT
        carb_cal = carb * CAL_PER_G_CARBS
        fat_pct = fat_cal / cal if cal > 0 else Decimal("0")
        carb_pct = carb_cal / cal if cal > 0 else Decimal("0")

        # --- Apply threshold rules ---

        # Calorie density
        if cal >= SIGNAL_CALORIE_DENSE:
            meal_signals.append(SIG_CALORIE_DENSE)

        # Protein signals
        if pro < SIGNAL_LOW_PROTEIN_G:
            meal_signals.append(SIG_LOW_PROTEIN)
        elif pro >= SIGNAL_HIGH_PROTEIN_G:
            meal_signals.append(SIG_HIGH_PROTEIN)

        # Fat signal
        if fat_pct >= SIGNAL_HIGH_FAT_PCT:
            meal_signals.append(SIG_HIGH_FAT)

        # Carb signal
        if carb_pct >= SIGNAL_HIGH_CARB_PCT:
            meal_signals.append(SIG_HIGH_CARB)

        # Balanced check (only if not already flagged as calorie_dense)
        if (
            SIG_CALORIE_DENSE not in meal_signals
            and pro >= SIGNAL_BALANCED_PROTEIN_G
            and fat_pct < SIGNAL_BALANCED_FAT_PCT
            and carb_pct < SIGNAL_BALANCED_CARB_PCT
        ):
            meal_signals.append(SIG_BALANCED)

        signals[meal_type] = meal_signals

    return signals
