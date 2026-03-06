"""
Derived body composition metrics service.

Calculates lean body mass and fat mass from weight + body fat percentage.
These derived metrics fill gaps when Apple Health doesn't provide them directly.

Formulas:
    lean_mass = weight × (1 - body_fat_pct / 100)
    fat_mass  = weight × (body_fat_pct / 100)
"""
import logging
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

logger = logging.getLogger(__name__)


def calculate_body_composition(weight, body_fat_percentage):
    """
    Calculate lean body mass and fat mass from weight and body fat percentage.

    Args:
        weight: Weight value (Decimal or numeric). Must be > 0.
        body_fat_percentage: Body fat as a percentage (e.g. 36.5 for 36.5%).

    Returns:
        dict with 'lean_mass' and 'fat_mass' as Decimal values rounded to 1 decimal,
        or None if inputs are invalid.
    """
    if weight is None or body_fat_percentage is None:
        return None

    try:
        weight = Decimal(str(weight))
        body_fat_percentage = Decimal(str(body_fat_percentage))
    except (TypeError, InvalidOperation):
        return None

    if weight <= 0 or body_fat_percentage < 0 or body_fat_percentage > 100:
        return None

    one_dp = Decimal("0.1")
    bf_ratio = body_fat_percentage / Decimal("100")

    fat_mass = (weight * bf_ratio).quantize(one_dp, rounding=ROUND_HALF_UP)
    lean_mass = (weight * (Decimal("1") - bf_ratio)).quantize(one_dp, rounding=ROUND_HALF_UP)

    return {
        "lean_mass": lean_mass,
        "fat_mass": fat_mass,
    }


def sync_derived_body_composition(user, weight_entry):
    """
    Derive lean_mass and fat_mass from a WeightEntry and upsert BodyCompositionEntry rows.

    Skips if the WeightEntry has no real weight (placeholder value=0) or
    no body_fat_percentage.

    Args:
        user: User instance
        weight_entry: WeightEntry instance with value, body_fat_percentage, recorded_at
    """
    if not weight_entry.value or weight_entry.value <= 0:
        return
    if weight_entry.body_fat_percentage is None:
        return

    result = calculate_body_composition(weight_entry.value, weight_entry.body_fat_percentage)
    if result is None:
        return

    from apps.health.models import BodyCompositionEntry

    measurement_date = weight_entry.recorded_at.date()
    source = weight_entry.source or "apple_health"

    for metric_name, value, unit in [
        ("lean_mass", result["lean_mass"], "lb"),
        ("fat_mass", result["fat_mass"], "lb"),
    ]:
        existing = BodyCompositionEntry.objects.filter(
            user=user,
            metric_name=metric_name,
            measurement_date=measurement_date,
        ).first()

        if existing:
            if existing.value != value:
                existing.value = value
                existing.unit = unit
                existing.source = source
                existing.save(update_fields=["value", "unit", "source", "updated_at"])
        else:
            BodyCompositionEntry.objects.create(
                user=user,
                metric_name=metric_name,
                value=value,
                unit=unit,
                measurement_date=measurement_date,
                source=source,
            )
