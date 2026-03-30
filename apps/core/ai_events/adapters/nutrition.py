# ==============================================================================
# File: apps/core/ai_events/adapters/nutrition.py
# Project: Whole Life Journey
# Description: Nutrition/food event adapter
# Created: 2026-03-28
# ==============================================================================
"""Nutrition Event Adapter. Reads FoodEntry directly."""

import logging
from datetime import date
from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    from apps.health.models import FoodEntry
    entries = FoodEntry.objects.filter(
        user=user, logged_date__gte=start_date, logged_date__lte=end_date,
    ).order_by('logged_date', 'logged_time')
    return [_to_event(e) for e in entries]


def get_latest(user, count=1):
    from apps.health.models import FoodEntry
    return [_to_event(e) for e in FoodEntry.objects.filter(user=user).order_by('-logged_date', '-logged_time')[:count]]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def _to_event(entry):
    from django.utils import timezone as tz
    meal = entry.meal_type or ''
    name = entry.food_name or 'Food'
    cal = round(float(entry.total_calories)) if entry.total_calories else None
    label = f"{meal.title()}: {name}" if meal else name
    if cal:
        label += f" ({cal} cal)"

    if entry.logged_time:
        naive = tz.datetime.combine(entry.logged_date, entry.logged_time)
        timestamp = tz.make_aware(naive, tz.get_default_timezone())
    else:
        timestamp = tz.make_aware(
            tz.datetime.combine(entry.logged_date, tz.datetime.min.time()),
            tz.get_default_timezone(),
        )

    return EventRecord(
        domain='nutrition', event_type='food_logged', timestamp=timestamp,
        label=label, status='logged',
        detail={
            'food_name': entry.food_name or '', 'meal_type': meal,
            'calories': cal,
            'protein_g': float(entry.total_protein_g) if entry.total_protein_g else None,
            'carbs_g': float(entry.total_carbohydrates_g) if entry.total_carbohydrates_g else None,
            'fat_g': float(entry.total_fat_g) if entry.total_fat_g else None,
            'date': str(entry.logged_date),
        },
        source_model='FoodEntry', source_id=entry.pk,
    )


def _enforce_bounds(s, e):
    if e < s: raise ValueError("end_date must be >= start_date")
    if (e - s).days > MAX_LOOKBACK_DAYS: raise ValueError(f"Exceeds {MAX_LOOKBACK_DAYS} days")
