# ==============================================================================
# File: action_handlers.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Action handlers for executing recognized intents
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# ==============================================================================
"""
Action Handlers for Intent Execution

Each handler creates the appropriate model instance based on extracted parameters.
Handlers validate data and return ActionResult with success status and created object.
"""

import hashlib
import logging
import re
from datetime import timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q

from .intent_service import ActionResult

logger = logging.getLogger(__name__)

# YouVersion Bible API constants
BIBLE_API_BASE = "https://api.youversion.com/v1"

# Book name to USFM abbreviation mapping (used by YouVersion)
BOOK_ABBREVIATIONS = {
    'Genesis': 'GEN', 'Exodus': 'EXO', 'Leviticus': 'LEV', 'Numbers': 'NUM',
    'Deuteronomy': 'DEU', 'Joshua': 'JOS', 'Judges': 'JDG', 'Ruth': 'RUT',
    '1 Samuel': '1SA', '2 Samuel': '2SA', '1 Kings': '1KI', '2 Kings': '2KI',
    '1 Chronicles': '1CH', '2 Chronicles': '2CH', 'Ezra': 'EZR', 'Nehemiah': 'NEH',
    'Esther': 'EST', 'Job': 'JOB', 'Psalms': 'PSA', 'Psalm': 'PSA',
    'Proverbs': 'PRO', 'Ecclesiastes': 'ECC', 'Song of Solomon': 'SNG',
    'Isaiah': 'ISA', 'Jeremiah': 'JER', 'Lamentations': 'LAM', 'Ezekiel': 'EZK',
    'Daniel': 'DAN', 'Hosea': 'HOS', 'Joel': 'JOL', 'Amos': 'AMO',
    'Obadiah': 'OBA', 'Jonah': 'JON', 'Micah': 'MIC', 'Nahum': 'NAM',
    'Habakkuk': 'HAB', 'Zephaniah': 'ZEP', 'Haggai': 'HAG', 'Zechariah': 'ZEC',
    'Malachi': 'MAL', 'Matthew': 'MAT', 'Mark': 'MRK', 'Luke': 'LUK',
    'John': 'JHN', 'Acts': 'ACT', 'Romans': 'ROM', '1 Corinthians': '1CO',
    '2 Corinthians': '2CO', 'Galatians': 'GAL', 'Ephesians': 'EPH',
    'Philippians': 'PHP', 'Colossians': 'COL', '1 Thessalonians': '1TH',
    '2 Thessalonians': '2TH', '1 Timothy': '1TI', '2 Timothy': '2TI',
    'Titus': 'TIT', 'Philemon': 'PHM', 'Hebrews': 'HEB', 'James': 'JAS',
    '1 Peter': '1PE', '2 Peter': '2PE', '1 John': '1JN', '2 John': '2JN',
    '3 John': '3JN', 'Jude': 'JUD', 'Revelation': 'REV',
}

# Default Bible ID for YouVersion (NIV)
# Users can set their preference via default_bible_translation
DEFAULT_YOUVERSION_BIBLE_ID = "111"

# Fallback Bible ID (BSB - Berean Standard Bible)
# Used when primary translation fails (403/404 errors)
FALLBACK_YOUVERSION_BIBLE_ID = "3034"


class ActionHandler:
    """
    Handles execution of recognized intents by creating/updating model instances.

    Usage:
        handler = ActionHandler(user)
        result = handler.handle_log_heart_rate(bpm=60, context="resting")
    """

    def __init__(self, user):
        self.user = user

    def _get_user_now(self):
        """Get current datetime in user's timezone."""
        from apps.core.utils import get_user_now
        return get_user_now(self.user)

    def _get_recorded_at(self, kwargs):
        """
        Get recorded_at timestamp, using HTIE-resolved time if available.

        The orchestrator passes a 'recorded_at' key in kwargs when HTIE
        resolves a time expression (e.g., "3 days ago"). Falls back to
        the user's current time.
        """
        recorded_at = kwargs.get('recorded_at')
        if recorded_at:
            return recorded_at
        return self._get_user_now()

    def _get_user_today(self):
        """Get current date in user's timezone."""
        from apps.core.utils import get_user_today
        return get_user_today(self.user)

    # =========================================================================
    # TREND HELPERS (for execution confirmation detail)
    # =========================================================================

    def _get_trend_text(self, model_class, value_field='value', days=7, label='',
                         unit='', direction='lower_is_better'):
        """
        Generic trend helper — compare latest entry to 7-day average.

        Returns: str or None (e.g., "Down 2 lbs this week" or None if insufficient data)
        """
        from django.utils import timezone as tz
        import datetime as dt

        cutoff = tz.now() - dt.timedelta(days=days)
        entries = list(
            model_class.objects.filter(
                user=self.user,
                created_at__gte=cutoff,
            ).order_by('-created_at').values_list(value_field, flat=True)[:30]
        )
        if len(entries) < 2:
            return None

        latest = float(entries[0])
        avg = sum(float(e) for e in entries[1:]) / len(entries[1:])
        diff = latest - avg

        if abs(diff) < 0.01:
            return None

        direction_word = 'down' if diff < 0 else 'up'
        if unit:
            return f"{direction_word.capitalize()} {abs(diff):.1f} {unit} vs. {days}-day avg"
        else:
            return f"{direction_word.capitalize()} {abs(diff):.1f} vs. {days}-day avg"

    def _get_daily_count(self, model_class, date_field='created_at'):
        """Count entries logged today."""
        from django.utils import timezone as tz
        today = self._get_user_today()
        return model_class.objects.filter(
            user=self.user,
            **{f'{date_field}__date': today}
        ).count()

    def _get_weekly_count(self, model_class, date_field='created_at'):
        """Count entries logged this week."""
        from django.utils import timezone as tz
        import datetime as dt
        today = self._get_user_today()
        week_start = today - dt.timedelta(days=today.weekday())
        return model_class.objects.filter(
            user=self.user,
            **{f'{date_field}__date__gte': week_start}
        ).count()

    def _cross_complete_task(self, keyword):
        """Try to find and complete a matching active task. Returns message or None."""
        try:
            tasks, _ = self._resolve_tasks_by_query(keyword)
            if len(tasks) == 1:
                tasks[0].mark_complete()
                return f"✓ Also marked task complete: {tasks[0].title}"
        except Exception:
            pass
        return None

    def _cross_log_habit(self, keyword):
        """Try to find and log a matching active habit. Returns message or None."""
        try:
            from apps.purpose.models import HabitGoal, HabitEntry
            habits = HabitGoal.objects.filter(
                user=self.user, status='active'
            ).filter(
                Q(name__icontains=keyword) | Q(description__icontains=keyword)
            )
            if habits.count() == 1:
                habit = habits.first()
                today = self._get_user_today()
                entry, created = HabitEntry.objects.get_or_create(
                    goal=habit, date=today, session_number=1,
                    defaults={'completed': True, 'notes': ''}
                )
                if not created and not entry.completed:
                    entry.completed = True
                    entry.save()
                return f"✓ Also logged habit: {habit.name}"
        except Exception:
            pass
        return None

    def _find_task_suggestion(self, keyword):
        """Check if a matching task exists (for suggesting when habit not found)."""
        try:
            tasks, _ = self._resolve_tasks_by_query(keyword)
            if len(tasks) == 1:
                return tasks[0]
        except Exception:
            pass
        return None

    def _find_habit_suggestion(self, keyword):
        """Check if a matching habit exists (for suggesting when task not found)."""
        try:
            from apps.purpose.models import HabitGoal
            habits = HabitGoal.objects.filter(
                user=self.user, status='active'
            ).filter(
                Q(name__icontains=keyword) | Q(description__icontains=keyword)
            )
            if habits.count() == 1:
                return habits.first()
        except Exception:
            pass
        return None

    def _resolve_tasks_by_query(self, query, include_completed=False):
        """
        Resolve tasks by query with literal-first matching.

        Matching tiers (evaluated in order — first match wins):
        1. Exact case-insensitive title match
        2. Prefix match (title starts with query)
        3. Substring match (title or notes contains query)

        Returns:
            (tasks_list, match_tier) — tier is 'exact', 'prefix', or 'substring'
        """
        from apps.life.models import Task

        base_qs = Task.objects.filter(user=self.user, status='active')
        if not include_completed:
            base_qs = base_qs.filter(completion_status='pending')

        query_stripped = query.strip()

        # Tier 1: Exact match
        exact = list(base_qs.filter(title__iexact=query_stripped))
        if exact:
            return exact, 'exact'

        # Tier 2: Prefix match
        prefix = list(base_qs.filter(title__istartswith=query_stripped))
        if prefix:
            return prefix, 'prefix'

        # Tier 3: Substring match (existing behavior)
        substring = list(
            base_qs.filter(
                Q(title__icontains=query_stripped)
                | Q(notes__icontains=query_stripped)
            )
        )
        return substring, 'substring'

    def _build_confirmation(self, what, where, trend=None, risk=None):
        """
        Build a confirmation_detail dict for ActionResult.

        Args:
            what: What was recorded (e.g., "185 lb")
            where: Where it lives (e.g., "Health > Weight")
            trend: 7-day trend text or None
            risk: Risk/context note or None

        Returns: dict
        """
        detail = {'what': what, 'where': where}
        if trend:
            detail['trend'] = trend
        if risk:
            detail['risk'] = risk
        return detail

    def _fetch_verse_text(self, book_name: str, chapter: int, verse_start: int,
                          verse_end: int = None, translation: str = None) -> str:
        """
        Fetch verse text from the YouVersion Bible API.

        Args:
            book_name: Full book name (e.g., 'John', 'Genesis')
            chapter: Chapter number
            verse_start: Starting verse number
            verse_end: Ending verse number (optional, for ranges)
            translation: Bible translation ID (YouVersion Bible ID)

        Returns:
            Verse text or empty string if lookup fails
        """
        api_key = getattr(settings, 'YOUVERSION_API_KEY', '')
        if not api_key:
            logger.warning("YouVersion API key not configured, cannot fetch verse text")
            return ""

        # Get the book abbreviation
        book_abbrev = BOOK_ABBREVIATIONS.get(book_name)
        if not book_abbrev:
            logger.warning(f"Unknown book name: {book_name}")
            return ""

        # Use user's preferred translation or default to NIV (111)
        bible_id = translation if translation else DEFAULT_YOUVERSION_BIBLE_ID

        # Build the passage ID in USFM format (e.g., "JHN.3.16" or "JHN.3.16-18")
        if verse_end and verse_end != verse_start:
            passage_id = f"{book_abbrev}.{chapter}.{verse_start}-{verse_end}"
        else:
            passage_id = f"{book_abbrev}.{chapter}.{verse_start}"

        def try_fetch(bid):
            """Try to fetch verse with given Bible ID."""
            url = f"{BIBLE_API_BASE}/bibles/{bid}/passages/{passage_id}"
            headers = {"X-YVP-App-Key": api_key}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get('content'):
                text = data['content'].strip()
                return ' '.join(text.split())
            return ""

        try:
            return try_fetch(bible_id)
        except requests.exceptions.HTTPError as e:
            # If we get a 403/404 and aren't already using fallback, try fallback
            if e.response.status_code in (403, 404) and bible_id != FALLBACK_YOUVERSION_BIBLE_ID:
                logger.warning(
                    f"YouVersion API {e.response.status_code} for bible {bible_id}, "
                    f"trying fallback {FALLBACK_YOUVERSION_BIBLE_ID}"
                )
                try:
                    return try_fetch(FALLBACK_YOUVERSION_BIBLE_ID)
                except requests.exceptions.RequestException as fallback_e:
                    logger.error(f"Fallback also failed: {fallback_e}")
                    return ""
            logger.error(f"Error fetching verse from YouVersion API: {e}")
            return ""
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching verse from YouVersion API: {e}")
            return ""

    # =========================================================================
    # HEALTH HANDLERS
    # =========================================================================

    def handle_log_heart_rate(self, bpm: int, context: str = "resting",
                               notes: str = "", **kwargs) -> ActionResult:
        """
        Log a heart rate entry.

        Args:
            bpm: Heart rate in beats per minute
            context: Measurement context (resting, active, etc.)
            notes: Optional notes
        """
        from apps.health.models import HeartRateEntry

        try:
            entry = HeartRateEntry.objects.create(
                user=self.user,
                bpm=bpm,
                context=context,
                notes=notes or "",
                recorded_at=self._get_recorded_at(kwargs)
            )

            time_str = entry.recorded_at.strftime("%I:%M %p")

            # Trend lookup (safe — never blocks action)
            trend = None
            try:
                trend = self._get_trend_text(HeartRateEntry, 'bpm', 7, '', 'BPM')
            except Exception:
                pass

            return ActionResult(
                success=True,
                message=f"✓ Logged heart rate: {bpm} BPM ({context}) at {time_str}",
                created_object={
                    'model': 'HeartRateEntry',
                    'id': entry.id,
                    'bpm': entry.bpm,
                    'context': entry.context,
                    'recorded_at': entry.recorded_at.isoformat()
                },
                action_type='log_heart_rate',
                confirmation_detail=self._build_confirmation(
                    what=f"{bpm} BPM ({context})",
                    where="Health > Heart Rate",
                    trend=trend,
                )
            )

        except Exception as e:
            logger.error(f"Error logging heart rate: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log your heart rate.",
                error=str(e)
            )

    def handle_log_blood_pressure(self, systolic: int, diastolic: int,
                                   pulse: int = None, context: str = "resting",
                                   arm: str = "left", position: str = "sitting",
                                   notes: str = "", **kwargs) -> ActionResult:
        """
        Log a blood pressure entry.

        Args:
            systolic: Systolic pressure (top number)
            diastolic: Diastolic pressure (bottom number)
            pulse: Optional pulse rate
            context: Measurement context
            arm: Which arm (left/right)
            position: Body position (sitting/standing/lying)
            notes: Optional notes
        """
        from apps.health.models import BloodPressureEntry

        try:
            entry = BloodPressureEntry.objects.create(
                user=self.user,
                systolic=systolic,
                diastolic=diastolic,
                pulse=pulse,
                context=context,
                arm=arm,
                position=position,
                notes=notes or "",
                recorded_at=self._get_recorded_at(kwargs)
            )

            time_str = entry.recorded_at.strftime("%I:%M %p")
            bp_str = f"{systolic}/{diastolic}"
            pulse_str = f", pulse {pulse}" if pulse else ""

            # Trend lookup (safe — never blocks action)
            trend = None
            try:
                trend = self._get_trend_text(BloodPressureEntry, 'systolic', 7, '', 'mmHg')
            except Exception:
                pass

            return ActionResult(
                success=True,
                message=f"✓ Logged blood pressure: {bp_str} mmHg{pulse_str} at {time_str}",
                created_object={
                    'model': 'BloodPressureEntry',
                    'id': entry.id,
                    'systolic': entry.systolic,
                    'diastolic': entry.diastolic,
                    'pulse': entry.pulse,
                    'category': entry.category,
                    'recorded_at': entry.recorded_at.isoformat()
                },
                action_type='log_blood_pressure',
                confirmation_detail=self._build_confirmation(
                    what=f"{systolic}/{diastolic} mmHg",
                    where="Health > Blood Pressure",
                    trend=trend,
                )
            )

        except Exception as e:
            logger.error(f"Error logging blood pressure: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log your blood pressure.",
                error=str(e)
            )

    def handle_log_weight(self, value: float, unit: str = "lb",
                          notes: str = "", **kwargs) -> ActionResult:
        """
        Log a weight entry.

        Args:
            value: Weight value
            unit: Unit (lb or kg)
            notes: Optional notes
        """
        from apps.health.models import WeightEntry

        try:
            entry = WeightEntry.objects.create(
                user=self.user,
                value=Decimal(str(value)),
                unit=unit,
                notes=notes or "",
                recorded_at=self._get_recorded_at(kwargs)
            )

            # Trend lookup (safe — never blocks action)
            trend = None
            try:
                trend = self._get_trend_text(WeightEntry, 'value', 7, '', unit)
            except Exception:
                pass

            return ActionResult(
                success=True,
                message=f"✓ Logged weight: {value} {unit}",
                created_object={
                    'model': 'WeightEntry',
                    'id': entry.id,
                    'value': float(entry.value),
                    'unit': entry.unit,
                    'recorded_at': entry.recorded_at.isoformat()
                },
                action_type='log_weight',
                confirmation_detail=self._build_confirmation(
                    what=f"{value} {unit}",
                    where="Health > Weight",
                    trend=trend,
                )
            )

        except Exception as e:
            logger.error(f"Error logging weight: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log your weight.",
                error=str(e)
            )

    def handle_log_glucose(self, value: float, unit: str = "mg/dL",
                           context: str = "random", notes: str = "",
                           **kwargs) -> ActionResult:
        """
        Log a blood glucose entry.

        Args:
            value: Glucose reading value
            unit: Unit (mg/dL or mmol/L)
            context: Reading context (fasting, after_meal, etc.)
            notes: Optional notes
        """
        from apps.health.models import GlucoseEntry

        try:
            entry = GlucoseEntry.objects.create(
                user=self.user,
                value=Decimal(str(value)),
                unit=unit,
                context=context,
                source='manual',
                notes=notes or "",
                recorded_at=self._get_recorded_at(kwargs)
            )

            # Trend lookup (safe — never blocks action)
            trend = None
            try:
                trend = self._get_trend_text(GlucoseEntry, 'value', 7, '', unit)
            except Exception:
                pass

            return ActionResult(
                success=True,
                message=f"✓ Logged blood glucose: {value} {unit} ({context})",
                created_object={
                    'model': 'GlucoseEntry',
                    'id': entry.id,
                    'value': float(entry.value),
                    'unit': entry.unit,
                    'context': entry.context,
                    'glucose_status': entry.glucose_status,
                    'recorded_at': entry.recorded_at.isoformat()
                },
                action_type='log_glucose',
                confirmation_detail=self._build_confirmation(
                    what=f"{value} {unit} ({context})",
                    where="Health > Blood Glucose",
                    trend=trend,
                )
            )

        except Exception as e:
            logger.error(f"Error logging glucose: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log your blood glucose.",
                error=str(e)
            )

    def handle_log_blood_oxygen(self, spo2: int, pulse: int = None,
                                 context: str = "resting",
                                 measurement_method: str = "finger",
                                 notes: str = "", **kwargs) -> ActionResult:
        """
        Log a blood oxygen (SpO2) entry.

        Args:
            spo2: Blood oxygen saturation percentage
            pulse: Optional pulse rate
            context: Measurement context
            measurement_method: How measurement was taken
            notes: Optional notes
        """
        from apps.health.models import BloodOxygenEntry

        try:
            entry = BloodOxygenEntry.objects.create(
                user=self.user,
                spo2=spo2,
                pulse=pulse,
                context=context,
                measurement_method=measurement_method,
                notes=notes or "",
                recorded_at=self._get_recorded_at(kwargs)
            )

            time_str = entry.recorded_at.strftime("%I:%M %p")
            pulse_str = f", pulse {pulse}" if pulse else ""

            return ActionResult(
                success=True,
                message=f"✓ Logged blood oxygen: {spo2}% SpO2{pulse_str} at {time_str}",
                created_object={
                    'model': 'BloodOxygenEntry',
                    'id': entry.id,
                    'spo2': entry.spo2,
                    'pulse': entry.pulse,
                    'category': entry.category,
                    'recorded_at': entry.recorded_at.isoformat()
                },
                action_type='log_blood_oxygen',
                confirmation_detail=self._build_confirmation(
                    what=f"{spo2}% SpO2",
                    where="Health > Blood Oxygen",
                )
            )

        except Exception as e:
            logger.error(f"Error logging blood oxygen: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log your blood oxygen.",
                error=str(e)
            )

    def handle_log_food(self, food_name: str, quantity: float = 1,
                        meal_type: str = None, calories: int = None,
                        notes: str = "", **kwargs) -> ActionResult:
        """
        Log a food entry with smart nutrition lookup.

        Uses 3-tier food search:
        1. Local database (CustomFood + FoodItem)
        2. FatSecret API (1.9M+ foods including restaurants)
        3. AI estimation (handles misspellings, generic foods)

        Args:
            food_name: Name of the food (can be misspelled, AI will correct)
            quantity: Number of servings
            meal_type: Type of meal (breakfast, lunch, dinner, snack)
            calories: Estimated calories if known (overrides search)
            notes: Optional notes
        """
        from apps.health.models import FoodEntry, FoodItem

        try:
            # Use HTIE-resolved time if available, else current time
            recorded_at = self._get_recorded_at(kwargs)
            now = recorded_at
            today = recorded_at.date() if hasattr(recorded_at, 'date') else self._get_user_today()

            # Determine meal type from time if not specified
            if not meal_type:
                hour = now.hour
                if hour < 10:
                    meal_type = 'breakfast'
                elif hour < 14:
                    meal_type = 'lunch'
                elif hour < 18:
                    meal_type = 'snack'
                else:
                    meal_type = 'dinner'

            # Smart food lookup with 3-tier search
            food_match = None
            matched_name = food_name
            nutrition_data = {
                'total_calories': Decimal(str(calories)) if calories else Decimal('0'),
                'total_protein_g': Decimal('0'),
                'total_carbohydrates_g': Decimal('0'),
                'total_fat_g': Decimal('0'),
                'total_fiber_g': Decimal('0'),
                'total_sugar_g': Decimal('0'),
                'serving_size': Decimal('1'),
                'serving_unit': 'serving',
            }
            source_note = ""

            try:
                from apps.health.services.food_search import food_search_service

                # Search for the food (includes misspelling correction via AI)
                results = food_search_service.search(
                    query=food_name,
                    user=self.user,
                    limit=1,
                    use_fatsecret=True,
                    use_ai=True  # AI can correct misspellings
                )

                if results:
                    best_match = results[0]
                    matched_name = best_match.name
                    food_match = best_match

                    # Use nutrition data from the match (unless calories explicitly provided)
                    if not calories and best_match.calories:
                        nutrition_data['total_calories'] = Decimal(str(best_match.calories))
                    if best_match.protein_g:
                        nutrition_data['total_protein_g'] = Decimal(str(best_match.protein_g))
                    if best_match.carbohydrates_g:
                        nutrition_data['total_carbohydrates_g'] = Decimal(str(best_match.carbohydrates_g))
                    if best_match.fat_g:
                        nutrition_data['total_fat_g'] = Decimal(str(best_match.fat_g))
                    if best_match.fiber_g:
                        nutrition_data['total_fiber_g'] = Decimal(str(best_match.fiber_g))
                    if best_match.sugar_g:
                        nutrition_data['total_sugar_g'] = Decimal(str(best_match.sugar_g))
                    if best_match.serving_size:
                        nutrition_data['serving_size'] = Decimal(str(best_match.serving_size))
                    if best_match.serving_unit:
                        nutrition_data['serving_unit'] = best_match.serving_unit

                    # Track source for user feedback
                    if best_match.source == 'ai':
                        source_note = " (AI estimate)"
                    elif best_match.source == 'fatsecret':
                        source_note = " (FatSecret)"

            except Exception as e:
                logger.warning(f"Food search failed, using basic entry: {e}")

            # Get food_item for linking if available
            food_item = None
            if food_match and food_match.food_item_id:
                try:
                    food_item = FoodItem.objects.get(id=food_match.food_item_id)
                except FoodItem.DoesNotExist:
                    pass

            # Create the food entry with full nutrition data
            entry = FoodEntry.objects.create(
                user=self.user,
                food_name=matched_name,
                food_item=food_item,
                quantity=Decimal(str(quantity)),
                serving_size=nutrition_data['serving_size'],
                serving_unit=nutrition_data['serving_unit'],
                total_calories=nutrition_data['total_calories'],
                total_protein_g=nutrition_data['total_protein_g'],
                total_carbohydrates_g=nutrition_data['total_carbohydrates_g'],
                total_fat_g=nutrition_data['total_fat_g'],
                total_fiber_g=nutrition_data['total_fiber_g'],
                total_sugar_g=nutrition_data['total_sugar_g'],
                logged_date=today,
                logged_time=now.time(),
                meal_type=meal_type,
                entry_source='voice',
                notes=notes or ""
            )

            # Build response message
            cal_val = float(nutrition_data['total_calories'])
            cal_str = f" ({int(cal_val)} cal)" if cal_val > 0 else ""

            # Note if name was corrected (e.g., misspelling fixed)
            name_note = ""
            if matched_name.lower() != food_name.lower():
                name_note = f" (matched: {matched_name})"

            # Trend lookup — daily calorie total (safe — never blocks action)
            trend = None
            try:
                from django.db.models import Sum
                daily_cals = FoodEntry.objects.filter(
                    user=self.user,
                    logged_date=today,
                ).aggregate(total=Sum('total_calories'))['total']
                if daily_cals:
                    trend = f"Today's total: {int(daily_cals)} cal"
            except Exception:
                pass

            return ActionResult(
                success=True,
                message=f"✓ Logged {quantity} {matched_name}{cal_str} for {meal_type}{source_note}{name_note}",
                created_object={
                    'model': 'FoodEntry',
                    'id': entry.id,
                    'food_name': entry.food_name,
                    'quantity': float(entry.quantity),
                    'meal_type': entry.meal_type,
                    'total_calories': float(entry.total_calories),
                    'total_protein_g': float(entry.total_protein_g),
                    'total_carbohydrates_g': float(entry.total_carbohydrates_g),
                    'total_fat_g': float(entry.total_fat_g),
                    'logged_date': entry.logged_date.isoformat(),
                    'source': food_match.source if food_match else 'manual',
                },
                action_type='log_food',
                confirmation_detail=self._build_confirmation(
                    what=f"{quantity} {matched_name}{cal_str}",
                    where="Health > Nutrition",
                    trend=trend,
                )
            )

        except Exception as e:
            logger.error(f"Error logging food: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log that food.",
                error=str(e)
            )

    # =========================================================================
    # SLEEP / WATER / STEPS / BODY MEASUREMENT HANDLERS
    # =========================================================================

    def handle_log_sleep(self, hours: float, quality: str = "",
                         bedtime: str = "", wake_time: str = "",
                         interruptions: int = 0, notes: str = "",
                         **kwargs) -> ActionResult:
        """
        Log a sleep entry.

        Args:
            hours: Total hours of sleep
            quality: Quality rating (excellent/good/fair/poor/terrible)
            bedtime: When they went to bed (optional)
            wake_time: When they woke up (optional)
            interruptions: Number of wake-ups (optional)
            notes: Optional notes
        """
        from apps.health.models import SleepEntry
        import datetime as dt

        try:
            recorded_at = self._get_recorded_at(kwargs)
            today = self._get_user_today()
            # Sleep date is typically the previous night
            sleep_date = today - dt.timedelta(days=1)

            total_minutes = int(hours * 60)

            # Parse bedtime and wake_time if provided
            bedtime_dt = None
            wake_time_dt = None
            if bedtime:
                try:
                    for fmt in ('%I:%M %p', '%I:%M%p', '%H:%M', '%I %p', '%I%p'):
                        try:
                            t = dt.datetime.strptime(bedtime.strip(), fmt).time()
                            bedtime_dt = dt.datetime.combine(sleep_date, t)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
            if wake_time:
                try:
                    for fmt in ('%I:%M %p', '%I:%M%p', '%H:%M', '%I %p', '%I%p'):
                        try:
                            t = dt.datetime.strptime(wake_time.strip(), fmt).time()
                            wake_time_dt = dt.datetime.combine(today, t)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

            # If no bedtime/wake_time, calculate reasonable defaults
            if not bedtime_dt:
                wake_hour = 7  # default wake time
                bed_hour = wake_hour - hours
                bedtime_dt = dt.datetime.combine(
                    sleep_date, dt.time(int(bed_hour) % 24, int((bed_hour % 1) * 60))
                )
            if not wake_time_dt:
                wake_time_dt = bedtime_dt + dt.timedelta(hours=hours)

            entry = SleepEntry.objects.create(
                user=self.user,
                sleep_date=sleep_date,
                bedtime=bedtime_dt,
                wake_time=wake_time_dt,
                total_duration_minutes=total_minutes,
                quality_rating=quality or "",
                interruption_count=interruptions,
                notes=notes or "",
                source="manual",
                recorded_at=recorded_at,
            )

            # Trend: 7-day average sleep
            trend = None
            try:
                cutoff = today - dt.timedelta(days=7)
                recent = list(SleepEntry.objects.filter(
                    user=self.user, sleep_date__gte=cutoff,
                ).values_list('total_duration_minutes', flat=True))
                if len(recent) >= 2:
                    avg_hrs = sum(recent) / len(recent) / 60
                    trend = f"7-day avg: {avg_hrs:.1f}h"
            except Exception:
                pass

            quality_str = f" ({quality})" if quality else ""
            return ActionResult(
                success=True,
                message=f"✓ Logged {hours}h sleep{quality_str}",
                created_object={
                    'model': 'SleepEntry',
                    'id': entry.id,
                    'hours': hours,
                    'quality': quality,
                    'sleep_date': sleep_date.isoformat(),
                },
                action_type='log_sleep',
                confirmation_detail=self._build_confirmation(
                    what=f"{hours}h{quality_str}",
                    where="Health > Sleep",
                    trend=trend,
                )
            )

        except Exception as e:
            logger.error(f"Error logging sleep: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log your sleep.",
                error=str(e)
            )

    def handle_log_water(self, amount: float, unit: str = "oz",
                         notes: str = "", **kwargs) -> ActionResult:
        """
        Log a water intake entry.

        Args:
            amount: Amount of water
            unit: Unit (oz, ml, cups, liters)
            notes: Optional notes
        """
        from apps.health.models import WaterEntry

        try:
            recorded_at = self._get_recorded_at(kwargs)
            today = self._get_user_today()

            entry = WaterEntry.objects.create(
                user=self.user,
                amount=Decimal(str(amount)),
                unit=unit,
                logged_date=today,
                notes=notes or "",
                source="manual",
                recorded_at=recorded_at,
            )

            # Trend: daily total
            trend = None
            try:
                daily_total = WaterEntry.get_daily_total(self.user, today)
                if daily_total:
                    progress = WaterEntry.get_daily_goal_progress(self.user, today)
                    pct = progress.get('percentage', 0) if progress else 0
                    trend = f"Today's total: {daily_total:.0f} oz ({pct:.0f}% of goal)"
            except Exception:
                pass

            return ActionResult(
                success=True,
                message=f"✓ Logged {amount} {unit} of water",
                created_object={
                    'model': 'WaterEntry',
                    'id': entry.id,
                    'amount': float(entry.amount),
                    'unit': entry.unit,
                    'logged_date': today.isoformat(),
                },
                action_type='log_water',
                confirmation_detail=self._build_confirmation(
                    what=f"{amount} {unit}",
                    where="Health > Water",
                    trend=trend,
                )
            )

        except Exception as e:
            logger.error(f"Error logging water: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log your water intake.",
                error=str(e)
            )

    def handle_log_steps(self, count: int, distance: float = None,
                         calories: int = None, notes: str = "",
                         **kwargs) -> ActionResult:
        """
        Log a steps entry.

        Args:
            count: Number of steps
            distance: Distance in miles (optional)
            calories: Active calories burned (optional)
            notes: Optional notes
        """
        from apps.health.models import StepsEntry

        try:
            recorded_at = self._get_recorded_at(kwargs)
            today = self._get_user_today()

            create_kwargs = {
                'user': self.user,
                'count': count,
                'logged_date': today,
                'notes': notes or "",
                'source': "manual",
                'recorded_at': recorded_at,
            }
            if distance is not None:
                create_kwargs['distance_miles'] = Decimal(str(distance))
            if calories is not None:
                create_kwargs['calories_burned'] = calories

            entry = StepsEntry.objects.create(**create_kwargs)

            # Trend: 7-day average
            trend = None
            try:
                import datetime as dt
                cutoff = today - dt.timedelta(days=7)
                recent = list(StepsEntry.objects.filter(
                    user=self.user, logged_date__gte=cutoff,
                ).values_list('count', flat=True))
                if len(recent) >= 2:
                    avg = sum(recent) / len(recent)
                    trend = f"7-day avg: {avg:,.0f} steps"
            except Exception:
                pass

            return ActionResult(
                success=True,
                message=f"✓ Logged {count:,} steps",
                created_object={
                    'model': 'StepsEntry',
                    'id': entry.id,
                    'count': entry.count,
                    'logged_date': today.isoformat(),
                },
                action_type='log_steps',
                confirmation_detail=self._build_confirmation(
                    what=f"{count:,} steps",
                    where="Health > Steps",
                    trend=trend,
                )
            )

        except Exception as e:
            logger.error(f"Error logging steps: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log your steps.",
                error=str(e)
            )

    def handle_log_body_measurement(self, metric: str, value: float,
                                     unit: str = "", notes: str = "",
                                     **kwargs) -> ActionResult:
        """
        Log a body composition/measurement entry.

        Args:
            metric: Type of measurement (body_fat_pct, waist, etc.)
            value: Measurement value
            unit: Unit (inferred from metric if not specified)
            notes: Optional notes
        """
        from apps.health.models import BodyCompositionEntry

        try:
            today = self._get_user_today()

            # Infer unit from metric if not provided
            if not unit:
                unit_map = {
                    'body_fat_pct': 'pct', 'body_water_pct': 'pct',
                    'lean_mass': 'lb', 'fat_mass': 'lb',
                    'skeletal_muscle_mass': 'lb', 'bone_mass': 'lb',
                    'waist': 'in', 'chest': 'in', 'hips': 'in',
                    'neck': 'in', 'shoulders': 'in',
                    'arm_left': 'in', 'arm_right': 'in',
                    'thigh_left': 'in', 'thigh_right': 'in',
                    'calf_left': 'in', 'calf_right': 'in',
                    'bmr': 'kcal', 'metabolic_age': 'years',
                    'visceral_fat': 'index',
                }
                unit = unit_map.get(metric, '')

            entry = BodyCompositionEntry.objects.create(
                user=self.user,
                metric_name=metric,
                value=Decimal(str(value)),
                unit=unit,
                measurement_date=today,
                notes=notes or "",
                source="manual",
            )

            # Trend: compare to last measurement
            trend = None
            try:
                prev = BodyCompositionEntry.objects.filter(
                    user=self.user, metric_name=metric,
                ).exclude(id=entry.id).order_by('-measurement_date').first()
                if prev:
                    diff = float(entry.value) - float(prev.value)
                    direction = "up" if diff > 0 else "down"
                    trend = f"{direction.capitalize()} {abs(diff):.1f} {unit} from last"
            except Exception:
                pass

            # Human-readable metric name
            metric_labels = {
                'body_fat_pct': 'Body Fat %', 'lean_mass': 'Lean Mass',
                'waist': 'Waist', 'chest': 'Chest', 'hips': 'Hips',
                'skeletal_muscle_mass': 'Skeletal Muscle',
                'visceral_fat': 'Visceral Fat', 'bmr': 'BMR',
            }
            label = metric_labels.get(metric, metric.replace('_', ' ').title())

            return ActionResult(
                success=True,
                message=f"✓ Logged {label}: {value} {unit}",
                created_object={
                    'model': 'BodyCompositionEntry',
                    'id': entry.id,
                    'metric': metric,
                    'value': float(entry.value),
                    'unit': unit,
                },
                action_type='log_body_measurement',
                confirmation_detail=self._build_confirmation(
                    what=f"{value} {unit}",
                    where=f"Health > {label}",
                    trend=trend,
                )
            )

        except Exception as e:
            logger.error(f"Error logging body measurement: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log that measurement.",
                error=str(e)
            )

    # =========================================================================
    # FINANCE HANDLERS
    # =========================================================================

    def handle_log_transaction(self, amount: float, description: str,
                                category: str = "", account: str = "",
                                notes: str = "", **kwargs) -> ActionResult:
        """
        Log a financial transaction.

        Args:
            amount: Amount (positive=income, negative=expense)
            description: Transaction description
            category: Category name (matched against user's categories)
            account: Account name (matched against user's accounts)
            notes: Optional notes
        """
        from apps.finance.models import Transaction, FinancialAccount, TransactionCategory

        try:
            today = self._get_user_today()

            # Find or default account
            acct = None
            if account:
                acct = FinancialAccount.objects.filter(
                    user=self.user, name__icontains=account, is_hidden=False,
                ).first()
            if not acct:
                acct = FinancialAccount.objects.filter(
                    user=self.user, is_hidden=False,
                ).order_by('sort_order').first()

            if not acct:
                return ActionResult(
                    success=False,
                    message="You don't have any financial accounts set up yet. "
                            "Add one in Finance > Accounts first.",
                    error="no_account"
                )

            # Find or create category
            cat = None
            if category:
                cat = TransactionCategory.objects.filter(
                    user=self.user, name__icontains=category,
                ).first()
                if not cat:
                    # Create the category
                    cat = TransactionCategory.objects.create(
                        user=self.user,
                        name=category.title(),
                    )

            entry = Transaction.objects.create(
                user=self.user,
                account=acct,
                date=today,
                amount=Decimal(str(amount)),
                description=description,
                category=cat,
                notes=notes or "",
            )

            # Update account balance
            try:
                acct.recalculate_balance()
            except Exception:
                pass

            # Type label
            txn_type = "income" if amount > 0 else "expense"
            amt_display = f"${abs(amount):,.2f}"
            cat_str = f" ({cat.name})" if cat else ""

            return ActionResult(
                success=True,
                message=f"✓ Logged {txn_type}: {amt_display} — {description}{cat_str}",
                created_object={
                    'model': 'Transaction',
                    'id': entry.id,
                    'amount': float(entry.amount),
                    'description': entry.description,
                    'account': acct.name,
                },
                action_type='log_transaction',
                confirmation_detail=self._build_confirmation(
                    what=f"{amt_display} {description}",
                    where=f"Finance > {acct.name}",
                )
            )

        except Exception as e:
            logger.error(f"Error logging transaction: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log that transaction.",
                error=str(e)
            )

    def handle_check_budget(self, category: str = "",
                             month: str = "", **kwargs) -> ActionResult:
        """
        Check budget status for a category or overall.

        Args:
            category: Specific category to check (optional)
            month: Month to check (optional, defaults to current)
        """
        from apps.finance.models import Budget
        import datetime as dt

        try:
            today = self._get_user_today()
            month_date = today.replace(day=1)

            if category:
                budgets = Budget.objects.filter(
                    user=self.user, month=month_date,
                    category__name__icontains=category,
                )
            else:
                budgets = Budget.objects.filter(
                    user=self.user, month=month_date,
                ).select_related('category')

            if not budgets.exists():
                if category:
                    msg = f"No budget found for '{category}' this month."
                else:
                    msg = "No budgets set up for this month."
                return ActionResult(
                    success=True,
                    message=msg,
                    action_type='check_budget',
                )

            lines = []
            total_budgeted = Decimal('0')
            total_spent = Decimal('0')
            for b in budgets:
                spent = b.spent_amount
                remaining = b.remaining_amount
                status = b.health_status
                icon = "✓" if status == "on_track" else "⚠" if status == "warning" else "✗"
                lines.append(
                    f"{icon} {b.category.name}: ${spent:,.2f} / ${b.total_budget:,.2f} "
                    f"(${remaining:,.2f} left)"
                )
                total_budgeted += b.total_budget
                total_spent += spent

            summary = "\n".join(lines)
            if len(budgets) > 1:
                summary += f"\n\nTotal: ${total_spent:,.2f} / ${total_budgeted:,.2f}"

            return ActionResult(
                success=True,
                message=summary,
                action_type='check_budget',
                confirmation_detail=self._build_confirmation(
                    what=f"${total_spent:,.2f} spent",
                    where="Finance > Budgets",
                )
            )

        except Exception as e:
            logger.error(f"Error checking budget: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't check your budget.",
                error=str(e)
            )

    # =========================================================================
    # UNDO / EDIT HANDLERS
    # =========================================================================

    def handle_undo_last_action(self, confirmation: str = "",
                                 **kwargs) -> ActionResult:
        """
        Undo the most recent action by soft-deleting the created record.

        Uses the last_action tracking from the conversation metadata.
        """
        try:
            # Get the last action from conversation actions_taken
            conversation = kwargs.get('conversation')
            if not conversation:
                return ActionResult(
                    success=False,
                    message="Nothing to undo — I don't see a recent action.",
                    error="no_conversation"
                )

            meta = conversation.metadata or {}
            last_actions = meta.get('actions_taken', [])
            if not last_actions:
                return ActionResult(
                    success=False,
                    message="Nothing to undo — no recent actions in this conversation.",
                    error="no_actions"
                )

            last = last_actions[-1]
            model_name = last.get('created', {}).get('model', '')
            obj_id = last.get('created', {}).get('id')
            action_type = last.get('type', '')

            if not model_name or not obj_id:
                return ActionResult(
                    success=False,
                    message="Can't undo — the last action didn't create a record.",
                    error="no_record"
                )

            # Resolve model and soft-delete
            model_map = self._get_undo_model_map()
            model_class = model_map.get(model_name)
            if not model_class:
                return ActionResult(
                    success=False,
                    message=f"Can't undo {action_type} — this type isn't undoable yet.",
                    error="unsupported_model"
                )

            obj = model_class.objects.filter(
                user=self.user, id=obj_id,
            ).first()
            if not obj:
                return ActionResult(
                    success=False,
                    message="That record has already been removed.",
                    error="not_found"
                )

            # Soft-delete if available, else hard delete
            if hasattr(obj, 'soft_delete'):
                obj.soft_delete()
            else:
                obj.delete()

            # Remove from actions_taken
            last_actions.pop()
            meta['actions_taken'] = last_actions
            conversation.metadata = meta
            conversation.save(update_fields=['metadata', 'updated_at'])

            return ActionResult(
                success=True,
                message=f"✓ Undone — removed the {action_type.replace('_', ' ')} entry.",
                action_type='undo_last_action',
            )

        except Exception as e:
            logger.error(f"Error undoing action: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't undo that action.",
                error=str(e)
            )

    def handle_edit_last_entry(self, entry_type: str, new_value: float = None,
                                field: str = "", new_text: str = "",
                                **kwargs) -> ActionResult:
        """
        Edit the most recent entry for a given data type.

        Args:
            entry_type: Type of entry to edit (weight, heart_rate, etc.)
            new_value: New numeric value
            field: Specific field to update
            new_text: New text value for text fields
        """
        try:
            model_map = {
                'weight': ('apps.health.models', 'WeightEntry', 'value', 'recorded_at'),
                'heart_rate': ('apps.health.models', 'HeartRateEntry', 'bpm', 'recorded_at'),
                'blood_pressure': ('apps.health.models', 'BloodPressureEntry', 'systolic', 'recorded_at'),
                'glucose': ('apps.health.models', 'GlucoseEntry', 'value', 'recorded_at'),
                'blood_oxygen': ('apps.health.models', 'BloodOxygenEntry', 'spo2', 'recorded_at'),
                'sleep': ('apps.health.models', 'SleepEntry', 'total_duration_minutes', 'recorded_at'),
                'water': ('apps.health.models', 'WaterEntry', 'amount', 'recorded_at'),
                'steps': ('apps.health.models', 'StepsEntry', 'count', 'recorded_at'),
            }

            info = model_map.get(entry_type)
            if not info:
                return ActionResult(
                    success=False,
                    message=f"Can't edit '{entry_type}' entries yet.",
                    error="unsupported_type"
                )

            module_path, class_name, default_field, order_field = info
            import importlib
            mod = importlib.import_module(module_path)
            model_class = getattr(mod, class_name)

            # Get the most recent entry
            entry = model_class.objects.filter(
                user=self.user,
            ).order_by(f'-{order_field}').first()

            if not entry:
                return ActionResult(
                    success=False,
                    message=f"No {entry_type} entries found to edit.",
                    error="not_found"
                )

            target_field = field or default_field
            old_value = getattr(entry, target_field, None)

            if new_value is not None:
                setattr(entry, target_field, Decimal(str(new_value))
                        if isinstance(old_value, Decimal) else new_value)
            elif new_text:
                setattr(entry, target_field, new_text)
            else:
                return ActionResult(
                    success=False,
                    message="Please specify the new value.",
                    error="no_value"
                )

            entry.save()

            display_value = new_value if new_value is not None else new_text
            return ActionResult(
                success=True,
                message=f"✓ Updated {entry_type}: {target_field} changed from {old_value} to {display_value}",
                action_type='edit_last_entry',
                confirmation_detail=self._build_confirmation(
                    what=f"{display_value}",
                    where=f"Health > {entry_type.replace('_', ' ').title()}",
                )
            )

        except Exception as e:
            logger.error(f"Error editing entry: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't edit that entry.",
                error=str(e)
            )

    @staticmethod
    def _get_undo_model_map():
        """Map model names to model classes for undo operations."""
        from apps.health.models import (
            WeightEntry, HeartRateEntry, BloodPressureEntry,
            GlucoseEntry, BloodOxygenEntry, SleepEntry, WaterEntry,
            StepsEntry, FoodEntry, BodyCompositionEntry,
        )
        from apps.journal.models import JournalEntry
        return {
            'WeightEntry': WeightEntry,
            'HeartRateEntry': HeartRateEntry,
            'BloodPressureEntry': BloodPressureEntry,
            'GlucoseEntry': GlucoseEntry,
            'BloodOxygenEntry': BloodOxygenEntry,
            'SleepEntry': SleepEntry,
            'WaterEntry': WaterEntry,
            'StepsEntry': StepsEntry,
            'FoodEntry': FoodEntry,
            'BodyCompositionEntry': BodyCompositionEntry,
            'JournalEntry': JournalEntry,
        }

    # =========================================================================
    # MEDICINE HANDLERS
    # =========================================================================

    def handle_take_medicine(self, medicine_name: str, dose_label: str = None,
                             notes: str = "", **kwargs) -> ActionResult:
        """
        Log that user took a medicine.

        Logic:
        1. Search user's active medicines by name (case-insensitive partial match)
        2. If one match: Log the next scheduled dose (or most recent if PRN)
        3. If multiple matches: Return options for user to choose
        4. If no match: Inform user medicine not found

        Args:
            medicine_name: Name of the medicine
            dose_label: Optional dose label (morning, evening, etc.)
            notes: Optional notes
        """
        from apps.health.models import Medicine

        try:
            # Search for matching active medicines
            medicines = Medicine.objects.filter(
                user=self.user,
                medicine_status=Medicine.STATUS_ACTIVE,
                status='active'  # UserOwnedModel soft delete
            ).filter(
                Q(name__icontains=medicine_name)
            )

            count = medicines.count()

            if count == 0:
                return ActionResult(
                    success=False,
                    message=f"I couldn't find '{medicine_name}' in your medicines. Would you like to add it?",
                    error='medicine_not_found'
                )

            elif count == 1:
                medicine = medicines.first()
                return self._log_medicine_taken(medicine, dose_label, notes)

            else:
                # Multiple matches - list them
                names = [f"• {m.name} ({m.dose})" for m in medicines[:5]]
                return ActionResult(
                    success=False,
                    message=f"I found {count} medicines matching '{medicine_name}':\n" + "\n".join(names) + "\nWhich one did you take?",
                    error='multiple_matches',
                    created_object={
                        'matches': [{'id': m.id, 'name': m.name, 'dose': m.dose} for m in medicines[:5]]
                    }
                )

        except Exception as e:
            logger.error(f"Error logging medicine: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log that medicine.",
                error=str(e)
            )

    def _log_medicine_taken(self, medicine, dose_label: str = None,
                            notes: str = "") -> ActionResult:
        """Internal method to log a specific medicine as taken."""
        from apps.health.models import MedicineLog

        now = self._get_user_now()
        today = self._get_user_today()

        # Find the appropriate schedule/dose to log
        if medicine.is_prn:
            # PRN medicine - create a PRN dose log
            log = MedicineLog.objects.create(
                user=self.user,
                medicine=medicine,
                scheduled_date=today,
                taken_at=now,
                log_status=MedicineLog.STATUS_TAKEN,
                is_prn_dose=True,
                prn_reason=notes or "",
                notes=notes or ""
            )
        else:
            # Scheduled medicine - find the appropriate schedule
            schedules = medicine.schedules.filter(is_active=True)

            if dose_label:
                # Try to match by label
                schedule = schedules.filter(label__icontains=dose_label).first()
            else:
                # Find the most recent scheduled dose that hasn't been logged
                schedule = None
                for sched in schedules:
                    existing = MedicineLog.objects.filter(
                        user=self.user,
                        medicine=medicine,
                        schedule=sched,
                        scheduled_date=today
                    ).first()
                    if not existing or existing.log_status not in [MedicineLog.STATUS_TAKEN, MedicineLog.STATUS_LATE]:
                        schedule = sched
                        break

            if schedule:
                # Update or create log for this schedule
                log, created = MedicineLog.objects.get_or_create(
                    user=self.user,
                    medicine=medicine,
                    schedule=schedule,
                    scheduled_date=today,
                    defaults={
                        'scheduled_time': schedule.scheduled_time,
                        'notes': notes or ""
                    }
                )
                log.mark_taken(taken_at=now)
            else:
                # No matching schedule found, create a general log
                log = MedicineLog.objects.create(
                    user=self.user,
                    medicine=medicine,
                    scheduled_date=today,
                    taken_at=now,
                    log_status=MedicineLog.STATUS_TAKEN,
                    notes=notes or ""
                )

        time_str = now.strftime("%I:%M %p")

        return ActionResult(
            success=True,
            message=f"✓ Logged {medicine.name} ({medicine.dose}) taken at {time_str}",
            created_object={
                'model': 'MedicineLog',
                'id': log.id,
                'medicine_id': medicine.id,
                'medicine_name': medicine.name,
                'dose': medicine.dose,
                'taken_at': log.taken_at.isoformat() if log.taken_at else None
            },
            action_type='take_medicine',
            confirmation_detail=self._build_confirmation(
                what=f"{medicine.name} ({medicine.dose})",
                where="Health > Medicine",
            )
        )

    def handle_take_medicines_by_time(self, time_of_day: str,
                                      use_scheduled_time: bool = False,
                                      notes: str = "", **kwargs) -> ActionResult:
        """
        Mark all medicines for a time-of-day period as taken.

        Mirrors MedicineBulkTakeView logic.

        Args:
            time_of_day: Period like 'morning', 'evening', 'nightly'
            use_scheduled_time: If True, log with scheduled time instead of now
            notes: Optional notes
        """
        from apps.health.models import Medicine, MedicineSchedule, MedicineLog
        from datetime import datetime as dt
        import pytz

        try:
            today = self._get_user_today()
            now = self._get_user_now()

            # Get all active scheduled (non-PRN) medicines
            active_medicines = Medicine.objects.filter(
                user=self.user,
                medicine_status=Medicine.STATUS_ACTIVE,
                status='active',
                is_prn=False,
            )

            taken_count = 0
            taken_names = []

            for medicine in active_medicines:
                for schedule in medicine.schedules.filter(
                    is_active=True,
                    time_of_day=time_of_day,
                ):
                    if not schedule.applies_to_day(today.weekday()):
                        continue

                    # Check if already logged
                    existing_log = MedicineLog.objects.filter(
                        medicine=medicine,
                        schedule=schedule,
                        scheduled_date=today,
                    ).first()

                    if existing_log and existing_log.log_status in [
                        MedicineLog.STATUS_TAKEN,
                        MedicineLog.STATUS_LATE,
                        MedicineLog.STATUS_SKIPPED,
                    ]:
                        continue  # Already handled

                    # Create or update log
                    log, created = MedicineLog.objects.get_or_create(
                        user=self.user,
                        medicine=medicine,
                        schedule=schedule,
                        scheduled_date=today,
                        defaults={
                            "scheduled_time": schedule.scheduled_time,
                            "is_prn_dose": False,
                            "notes": notes,
                        }
                    )

                    # Determine taken_at time
                    taken_at = None
                    if use_scheduled_time and schedule.scheduled_time:
                        user_tz = pytz.timezone(self.user.preferences.timezone_iana)
                        scheduled_dt = dt.combine(today, schedule.scheduled_time)
                        taken_at = user_tz.localize(scheduled_dt)

                    log.mark_taken(taken_at=taken_at)
                    taken_count += 1
                    taken_names.append(f"{medicine.name} ({medicine.dose})")

                    # Decrease supply if tracked
                    if medicine.current_supply is not None and medicine.current_supply > 0:
                        medicine.current_supply -= 1
                        medicine.save(update_fields=["current_supply", "updated_at"])

            if taken_count == 0:
                time_display = dict(MedicineSchedule.TIME_OF_DAY_CHOICES).get(
                    time_of_day, time_of_day
                )
                return ActionResult(
                    success=False,
                    message=f"No pending {time_display.lower()} medicines to log today. They may already be logged.",
                    error='no_pending_medicines'
                )

            time_display = dict(MedicineSchedule.TIME_OF_DAY_CHOICES).get(
                time_of_day, time_of_day
            )
            time_note = " at their scheduled times" if use_scheduled_time else ""
            names_list = "\n".join(f"  • {n}" for n in taken_names)

            return ActionResult(
                success=True,
                message=f"✓ Logged {taken_count} {time_display.lower()} medicine{'s' if taken_count != 1 else ''}{time_note}:\n{names_list}",
                created_object={
                    'model': 'MedicineLog',
                    'count': taken_count,
                    'time_of_day': time_of_day,
                    'medicines': taken_names,
                },
                action_type='take_medicines_by_time',
                confirmation_detail=self._build_confirmation(
                    what=f"{taken_count} {time_display.lower()} medicines",
                    where="Health > Medicine",
                )
            )

        except Exception as e:
            logger.error(f"Error bulk logging medicines: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log those medicines.",
                error=str(e)
            )

    def handle_email_medicine_list(self, recipient_email: str = "",
                                    include_adherence: bool = True,
                                    include_inactive: bool = False,
                                    **kwargs) -> ActionResult:
        """
        Email the user's medicine list with details and adherence stats.

        Args:
            recipient_email: Email address to send to (falls back to user's email)
            include_adherence: Include 30-day adherence stats
            include_inactive: Include paused/completed medicines
        """
        from django.core.mail import EmailMessage
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        from apps.health.models import Medicine
        from apps.health.medicine_utils import (
            calculate_medicine_adherence,
            calculate_single_medicine_adherence,
        )
        from datetime import timedelta

        try:
            # Resolve email — fall back to user's own email
            email_addr = (recipient_email or "").strip()
            # Catch placeholder text from LLM (e.g., "<user's email>")
            if not email_addr or email_addr.startswith("<") or email_addr.startswith("{"):
                email_addr = self.user.email

            try:
                validate_email(email_addr)
            except ValidationError:
                return ActionResult(
                    success=False,
                    message=f"'{email_addr}' doesn't look like a valid email address. Could you double-check it?",
                    error='invalid_email'
                )

            # Query medicines
            status_filter = ['active']
            if include_inactive:
                status_filter.extend(['paused', 'completed'])

            medicines = Medicine.objects.filter(
                user=self.user,
                medicine_status__in=status_filter,
                status='active',  # soft delete filter
            ).prefetch_related('schedules').order_by('name')

            if not medicines.exists():
                return ActionResult(
                    success=False,
                    message="You don't have any medicines on file to email. You can add medicines in Health > Medicine.",
                    error='no_medicines'
                )

            # Build medicine details
            today = self._get_user_today()
            medicine_data = []

            for med in medicines:
                # Schedule info
                schedules = med.schedules.filter(is_active=True)
                schedule_times = []
                for sched in schedules:
                    time_str = sched.scheduled_time.strftime("%I:%M %p") if sched.scheduled_time else ""
                    label = sched.label or sched.get_time_of_day_display()
                    schedule_times.append(f"{label}: {time_str}" if time_str else label)

                # Per-medicine adherence (30 days) — schedule-based
                med_adherence = None
                if include_adherence and not med.is_prn:
                    start = today - timedelta(days=30)
                    adh_result = calculate_single_medicine_adherence(
                        self.user, med, start, today
                    )
                    med_adherence = adh_result.get('adherence_rate')

                medicine_data.append({
                    'name': med.name,
                    'dose': med.dose,
                    'purpose': med.purpose or '',
                    'frequency': med.get_frequency_display(),
                    'is_prn': med.is_prn,
                    'status': med.medicine_status,
                    'prescribing_doctor': med.prescribing_doctor or '',
                    'pharmacy': med.pharmacy or '',
                    'instructions': med.instructions or '',
                    'schedule_times': schedule_times,
                    'adherence_rate': med_adherence,
                    'start_date': med.start_date,
                })

            # Overall adherence (30 days)
            overall_adherence = None
            if include_adherence:
                start = today - timedelta(days=30)
                adh = calculate_medicine_adherence(self.user, start, today)
                overall_adherence = adh.get('adherence_rate')

            user_name = self.user.get_full_name() or self.user.email.split('@')[0]

            context = {
                'user_name': user_name,
                'medicines': medicine_data,
                'overall_adherence': overall_adherence,
                'include_adherence': include_adherence,
                'include_inactive': include_inactive,
                'report_date': today,
                'current_year': today.year,
            }

            html_content = render_to_string(
                'health/email/medicine_list.html', context
            )
            text_content = strip_tags(html_content)

            email = EmailMessage(
                subject=f"Your Medicine List — Whole Life Journey",
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email_addr],
                reply_to=[self.user.email],
            )
            email.content_subtype = 'html'
            email.body = html_content
            email.send(fail_silently=False)

            med_count = len(medicine_data)
            adherence_note = ""
            if overall_adherence is not None:
                adherence_note = f" Your 30-day adherence is {overall_adherence}%."

            return ActionResult(
                success=True,
                message=(
                    f"✓ Emailed your medicine list ({med_count} medicine{'s' if med_count != 1 else ''}) "
                    f"to {email_addr}.{adherence_note}"
                ),
                action_type='email_medicine_list',
                confirmation_detail=self._build_confirmation(
                    what=f"{med_count} medicines emailed",
                    where="Health > Medicine",
                )
            )

        except Exception as e:
            logger.error(f"Error emailing medicine list: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't send the email. Please try again.",
                error=str(e)
            )

    # =========================================================================
    # FASTING HANDLERS
    # =========================================================================

    def handle_start_fast(self, fasting_type: str = None,
                          notes: str = "", **kwargs) -> ActionResult:
        """
        Start a new fasting window.

        Args:
            fasting_type: Type of fast (16:8, 18:6, etc.)
            notes: Optional notes
        """
        from apps.health.models import FastingWindow

        try:
            # Check for active fast
            active_fast = FastingWindow.objects.filter(
                user=self.user,
                ended_at__isnull=True,
                status='active'
            ).first()

            if active_fast:
                duration = active_fast.duration_hours
                return ActionResult(
                    success=False,
                    message=f"You already have an active fast ({active_fast.fasting_type}) running for {duration:.1f} hours. End it first to start a new one.",
                    error='active_fast_exists'
                )

            # Get default fasting type from preferences if not specified
            if not fasting_type:
                prefs = self.user.preferences
                fasting_type = getattr(prefs, 'default_fasting_type', '16:8')

            # Calculate target hours from fasting type
            target_hours_map = {
                '16:8': 16,
                '18:6': 18,
                '20:4': 20,
                'OMAD': 23,
                '24h': 24,
                '36h': 36,
                'custom': None
            }
            target_hours = target_hours_map.get(fasting_type, 16)

            now = self._get_recorded_at(kwargs)

            fast = FastingWindow.objects.create(
                user=self.user,
                fasting_type=fasting_type,
                started_at=now,
                target_hours=target_hours,
                notes=notes or ""
            )

            time_str = now.strftime("%I:%M %p")
            target_str = f" (target: {target_hours} hours)" if target_hours else ""

            return ActionResult(
                success=True,
                message=f"✓ Started {fasting_type} fast at {time_str}{target_str}",
                created_object={
                    'model': 'FastingWindow',
                    'id': fast.id,
                    'fasting_type': fast.fasting_type,
                    'started_at': fast.started_at.isoformat(),
                    'target_hours': fast.target_hours,
                    'target_end_time': fast.target_end_time.isoformat() if fast.target_end_time else None
                },
                action_type='start_fast',
                confirmation_detail=self._build_confirmation(
                    what=f"Started {fasting_type} fast",
                    where="Health > Fasting",
                )
            )

        except Exception as e:
            logger.error(f"Error starting fast: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't start your fast.",
                error=str(e)
            )

    def handle_end_fast(self, notes: str = "", **kwargs) -> ActionResult:
        """
        End the current fasting window.

        Args:
            notes: Optional notes
        """
        from apps.health.models import FastingWindow

        try:
            # Find active fast
            active_fast = FastingWindow.objects.filter(
                user=self.user,
                ended_at__isnull=True,
                status='active'
            ).first()

            if not active_fast:
                return ActionResult(
                    success=False,
                    message="You don't have an active fast to end. Would you like to start one?",
                    error='no_active_fast'
                )

            # End the fast
            active_fast.end_fast()

            if notes:
                active_fast.notes = (active_fast.notes + "\n" + notes).strip() if active_fast.notes else notes
                active_fast.save(update_fields=['notes', 'updated_at'])

            duration = active_fast.duration_hours
            goal_reached = active_fast.is_goal_reached

            if goal_reached:
                message = f"✓ Fast ended! You fasted for {duration:.1f} hours and reached your goal! 🎉"
            else:
                target = active_fast.target_hours
                if target:
                    message = f"✓ Fast ended after {duration:.1f} hours (goal was {target} hours)"
                else:
                    message = f"✓ Fast ended after {duration:.1f} hours"

            # Format duration for confirmation
            hours = int(duration)
            minutes = int((duration - hours) * 60)
            duration_text = f"{hours}h {minutes}m" if minutes else f"{hours}h"

            return ActionResult(
                success=True,
                message=message,
                created_object={
                    'model': 'FastingWindow',
                    'id': active_fast.id,
                    'fasting_type': active_fast.fasting_type,
                    'started_at': active_fast.started_at.isoformat(),
                    'ended_at': active_fast.ended_at.isoformat(),
                    'duration_hours': round(duration, 1),
                    'goal_reached': goal_reached
                },
                action_type='end_fast',
                confirmation_detail=self._build_confirmation(
                    what=f"Ended fast ({duration_text})",
                    where="Health > Fasting",
                )
            )

        except Exception as e:
            logger.error(f"Error ending fast: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't end your fast.",
                error=str(e)
            )

    # =========================================================================
    # JOURNAL HANDLERS
    # =========================================================================

    def handle_create_journal_entry(self, body: str, title: str = None,
                                     mood: str = None, categories: list = None,
                                     **kwargs) -> ActionResult:
        """
        Create a new journal entry.

        Args:
            body: The main content of the journal entry
            title: Optional title (will auto-generate if not provided)
            mood: User's mood (great, good, okay, down, struggling)
            categories: List of category names
        """
        from apps.journal.models import JournalEntry, Category

        try:
            today = self._get_user_today()

            # Auto-generate title if not provided
            if not title:
                # Use first 50 chars of body or a default
                title = body[:50] + "..." if len(body) > 50 else body
                if not title:
                    title = f"Journal Entry - {today.strftime('%B %d')}"

            entry = JournalEntry.objects.create(
                user=self.user,
                title=title,
                body=body,
                entry_date=today,
                mood=mood or 'okay'
            )

            # Add categories if provided (Category is system-wide, not per-user)
            if categories:
                for cat_name in categories:
                    category = Category.objects.filter(
                        name__iexact=cat_name.strip()
                    ).first()
                    if category:
                        entry.categories.add(category)

            # Trend lookup — weekly journal count (safe — never blocks action)
            trend = None
            try:
                weekly = self._get_weekly_count(JournalEntry, 'entry_date')
                if weekly:
                    trend = f"{weekly} entr{'ies' if weekly != 1 else 'y'} this week"
            except Exception:
                pass

            display_title = f"{title[:30]}..." if len(title) > 30 else title

            return ActionResult(
                success=True,
                message=f"✓ Created journal entry: \"{display_title}\"",
                created_object={
                    'model': 'JournalEntry',
                    'id': entry.id,
                    'title': entry.title,
                    'mood': entry.mood,
                    'entry_date': entry.entry_date.isoformat()
                },
                action_type='create_journal_entry',
                confirmation_detail=self._build_confirmation(
                    what=display_title,
                    where="Journal",
                    trend=trend,
                )
            )

        except Exception as e:
            logger.error(f"Error creating journal entry: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't create that journal entry.",
                error=str(e)
            )

    def handle_add_gratitude(self, gratitude: str, reason: str = "",
                              **kwargs) -> ActionResult:
        """
        Log something the user is grateful for (creates a gratitude journal entry).

        Args:
            gratitude: What the user is grateful for
            reason: Why they're grateful (optional)
        """
        from apps.journal.models import JournalEntry, Category

        try:
            recorded_at = self._get_recorded_at(kwargs)
            today = recorded_at.date() if hasattr(recorded_at, 'date') else self._get_user_today()

            # Build the body
            body = f"I'm grateful for {gratitude}."
            if reason:
                body += f" {reason}"

            entry = JournalEntry.objects.create(
                user=self.user,
                title=f"Gratitude: {gratitude[:40]}",
                body=body,
                entry_date=today,
                mood='good'
            )

            # Add gratitude category
            category, _ = Category.objects.get_or_create(
                user=self.user,
                name='gratitude',
                defaults={'color': '#10B981'}  # Green
            )
            entry.categories.add(category)

            # Truncate for confirmation detail
            gratitude_short = gratitude[:50] + "..." if len(gratitude) > 50 else gratitude

            return ActionResult(
                success=True,
                message=f"✓ Logged gratitude: {gratitude}",
                created_object={
                    'model': 'JournalEntry',
                    'id': entry.id,
                    'title': entry.title,
                    'entry_date': entry.entry_date.isoformat()
                },
                action_type='add_gratitude',
                confirmation_detail=self._build_confirmation(
                    what=gratitude_short,
                    where="Journal > Gratitude",
                )
            )

        except Exception as e:
            logger.error(f"Error logging gratitude: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log that gratitude.",
                error=str(e)
            )

    # =========================================================================
    # FAITH HANDLERS
    # =========================================================================

    def handle_log_prayer(self, title: str, description: str = "",
                          person_or_situation: str = "", priority: str = "normal",
                          is_personal: bool = False, **kwargs) -> ActionResult:
        """
        Create a new prayer request.

        Args:
            title: Brief title for the prayer
            description: Details about the prayer
            person_or_situation: Who/what the prayer is for
            priority: urgent, high, normal, ongoing
            is_personal: Whether this is a personal prayer
        """
        from apps.faith.models import PrayerRequest

        try:
            prayer = PrayerRequest.objects.create(
                user=self.user,
                title=title,
                description=description or "",
                person_or_situation=person_or_situation or "",
                priority=priority,
                is_personal=is_personal,
                prayer_status='active'
            )

            return ActionResult(
                success=True,
                message=f"✓ Added prayer: {title}",
                created_object={
                    'model': 'PrayerRequest',
                    'id': prayer.id,
                    'title': prayer.title,
                    'priority': prayer.priority,
                    'created_at': prayer.created_at.isoformat()
                },
                action_type='log_prayer',
                confirmation_detail=self._build_confirmation(
                    what=title,
                    where="Faith > Prayer",
                )
            )

        except Exception as e:
            logger.error(f"Error creating prayer: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't add that prayer.",
                error=str(e)
            )

    def handle_mark_prayer_answered(self, prayer_keyword: str,
                                     answer_notes: str = "", **kwargs) -> ActionResult:
        """
        Mark a prayer request as answered.

        Args:
            prayer_keyword: Keywords to find the prayer
            answer_notes: Testimony of how prayer was answered
        """
        from apps.faith.models import PrayerRequest

        try:
            # Search for matching active prayers
            prayers = PrayerRequest.objects.filter(
                user=self.user,
                prayer_status='active',
                status='active'
            ).filter(
                Q(title__icontains=prayer_keyword) |
                Q(description__icontains=prayer_keyword) |
                Q(person_or_situation__icontains=prayer_keyword)
            )

            count = prayers.count()

            if count == 0:
                return ActionResult(
                    success=False,
                    message=f"I couldn't find an active prayer matching '{prayer_keyword}'.",
                    error='prayer_not_found'
                )
            elif count == 1:
                prayer = prayers.first()
                prayer.mark_answered(answer_notes=answer_notes)

                return ActionResult(
                    success=True,
                    message=f"✓ Marked prayer as answered: {prayer.title} 🙏",
                    created_object={
                        'model': 'PrayerRequest',
                        'id': prayer.id,
                        'title': prayer.title,
                        'prayer_status': 'answered',
                        'answered_at': prayer.answered_at.isoformat() if prayer.answered_at else None
                    },
                    action_type='mark_prayer_answered',
                    confirmation_detail=self._build_confirmation(
                        what=prayer.title,
                        where="Faith > Prayer",
                    )
                )
            else:
                # Multiple matches
                titles = [f"• {p.title}" for p in prayers[:5]]
                return ActionResult(
                    success=False,
                    message=f"I found {count} prayers matching '{prayer_keyword}':\n" + "\n".join(titles) + "\nWhich one was answered?",
                    error='multiple_matches'
                )

        except Exception as e:
            logger.error(f"Error marking prayer answered: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't mark that prayer as answered.",
                error=str(e)
            )

    def handle_save_verse(self, reference: str, text: str = "",
                          notes: str = "", is_memory_verse: bool = False,
                          themes: list = None, **kwargs) -> ActionResult:
        """
        Save a scripture verse. Automatically fetches verse text from Bible API
        if not provided.

        Args:
            reference: Scripture reference (e.g., 'John 3:16')
            text: The verse text (fetched from API if not provided)
            notes: Personal notes
            is_memory_verse: Whether to memorize this verse
            themes: List of themes/topics
        """
        from apps.faith.models import SavedVerse
        from apps.faith.views import ScriptureSaveView

        try:
            # Parse reference to extract book, chapter, verse info
            book_name = "Unknown"
            book_order = 1
            chapter = 1
            verse_start = 1
            verse_end = None

            # Match patterns like "1 John 3:16-17" or "John 3:17" or "Genesis 1:1"
            match = re.match(r"^(\d?\s?[A-Za-z]+)\s+(\d+):(\d+)(?:-(\d+))?", reference)
            if match:
                book_name = match.group(1).strip()
                book_order = ScriptureSaveView.BOOK_ORDER.get(book_name, 1)
                chapter = int(match.group(2))
                verse_start = int(match.group(3))
                if match.group(4):
                    verse_end = int(match.group(4))

            # If no text provided, fetch from Bible API
            verse_text = text
            if not verse_text and book_name != "Unknown":
                # Get user's preferred translation, default to KJV
                translation = getattr(self.user.preferences, 'default_bible_translation', 'KJV')
                verse_text = self._fetch_verse_text(
                    book_name=book_name,
                    chapter=chapter,
                    verse_start=verse_start,
                    verse_end=verse_end,
                    translation=translation
                )

            verse = SavedVerse.objects.create(
                user=self.user,
                reference=reference,
                text=verse_text or "",
                book_name=book_name,
                book_order=book_order,
                chapter=chapter,
                verse_start=verse_start,
                verse_end=verse_end,
                notes=notes or "",
                is_memory_verse=is_memory_verse,
                themes=themes if themes else []
            )

            memory_str = " (marked for memorization)" if is_memory_verse else ""
            text_preview = f": \"{verse_text[:50]}...\"" if verse_text and len(verse_text) > 50 else (f": \"{verse_text}\"" if verse_text else "")

            return ActionResult(
                success=True,
                message=f"✓ Saved {reference}{memory_str}{text_preview}",
                created_object={
                    'model': 'SavedVerse',
                    'id': verse.id,
                    'reference': verse.reference,
                    'is_memory_verse': verse.is_memory_verse,
                    'created_at': verse.created_at.isoformat()
                },
                action_type='save_verse',
                confirmation_detail=self._build_confirmation(
                    what=reference,
                    where="Faith > Verses",
                )
            )

        except Exception as e:
            logger.error(f"Error saving verse: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't save that verse.",
                error=str(e)
            )

    def handle_add_faith_milestone(self, title: str, milestone_type: str,
                                    description: str = "", scripture_reference: str = "",
                                    date: str = None, **kwargs) -> ActionResult:
        """
        Record a spiritual milestone.

        Args:
            title: Title of the milestone
            milestone_type: Type (salvation, baptism, etc.)
            description: Description of the milestone
            scripture_reference: Related scripture
            date: Date of milestone (YYYY-MM-DD)
        """
        from apps.faith.models import FaithMilestone
        from datetime import datetime as dt

        try:
            # Parse date if provided
            if date:
                try:
                    milestone_date = dt.strptime(date, '%Y-%m-%d').date()
                except ValueError:
                    milestone_date = self._get_user_today()
            else:
                milestone_date = self._get_user_today()

            milestone = FaithMilestone.objects.create(
                user=self.user,
                title=title,
                milestone_type=milestone_type,
                description=description or "",
                scripture_reference=scripture_reference or "",
                date=milestone_date
            )

            return ActionResult(
                success=True,
                message=f"✓ Recorded milestone: {title}",
                created_object={
                    'model': 'FaithMilestone',
                    'id': milestone.id,
                    'title': milestone.title,
                    'milestone_type': milestone.milestone_type,
                    'date': milestone.date.isoformat()
                },
                action_type='add_faith_milestone',
                confirmation_detail=self._build_confirmation(
                    what=title,
                    where="Faith > Milestones",
                )
            )

        except Exception as e:
            logger.error(f"Error adding faith milestone: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't add that milestone.",
                error=str(e)
            )

    # =========================================================================
    # PURPOSE HANDLERS
    # =========================================================================

    def handle_create_goal(self, title: str, description: str = "",
                           why_it_matters: str = "", domain: str = "personal_growth",
                           timeframe: str = "within_1_year", target_date: str = None,
                           **kwargs) -> ActionResult:
        """
        Create a new life goal.

        Args:
            title: Goal title
            description: Goal description
            why_it_matters: Why this goal is important
            domain: Life domain (faith, health, family, etc.)
            timeframe: Target timeframe
            target_date: Specific target date
        """
        from apps.purpose.models import LifeGoal
        from datetime import datetime as dt

        try:
            # Parse target date if provided
            parsed_date = None
            if target_date:
                try:
                    parsed_date = dt.strptime(target_date, '%Y-%m-%d').date()
                except ValueError:
                    pass

            goal = LifeGoal.objects.create(
                user=self.user,
                title=title,
                description=description or "",
                why_it_matters=why_it_matters or "",
                domain=domain,
                timeframe=timeframe,
                target_date=parsed_date,
                goal_status='active'
            )

            return ActionResult(
                success=True,
                message=f"✓ Created goal: {title}",
                created_object={
                    'model': 'LifeGoal',
                    'id': goal.id,
                    'title': goal.title,
                    'domain': goal.domain,
                    'timeframe': goal.timeframe,
                    'created_at': goal.created_at.isoformat()
                },
                action_type='create_goal',
                confirmation_detail=self._build_confirmation(
                    what=title,
                    where="Goals",
                )
            )

        except Exception as e:
            logger.error(f"Error creating goal: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't create that goal.",
                error=str(e)
            )

    def handle_update_goal_progress(self, goal_keyword: str, progress_notes: str,
                                     mark_complete: bool = False, **kwargs) -> ActionResult:
        """
        Log progress on an existing goal.

        Args:
            goal_keyword: Keywords to find the goal
            progress_notes: Notes about progress
            mark_complete: Whether to mark as complete
        """
        from apps.purpose.models import LifeGoal

        try:
            goals = LifeGoal.objects.filter(
                user=self.user,
                goal_status='active',
                status='active'
            ).filter(
                Q(title__icontains=goal_keyword) |
                Q(description__icontains=goal_keyword)
            )

            count = goals.count()

            if count == 0:
                return ActionResult(
                    success=False,
                    message=f"I couldn't find an active goal matching '{goal_keyword}'.",
                    error='goal_not_found'
                )
            elif count == 1:
                goal = goals.first()

                # Add progress to reflection field
                existing = goal.reflection or ""
                timestamp = self._get_user_now().strftime("%Y-%m-%d")
                new_entry = f"\n[{timestamp}] {progress_notes}"
                goal.reflection = (existing + new_entry).strip()

                if mark_complete:
                    goal.goal_status = 'completed'
                    goal.completed_date = self._get_user_today()

                goal.save()

                status_msg = " and marked complete! 🎉" if mark_complete else ""

                return ActionResult(
                    success=True,
                    message=f"✓ Updated progress on: {goal.title}{status_msg}",
                    created_object={
                        'model': 'LifeGoal',
                        'id': goal.id,
                        'title': goal.title,
                        'goal_status': goal.goal_status
                    },
                    action_type='update_goal_progress',
                    confirmation_detail=self._build_confirmation(
                        what=f"{goal.title}: {progress_notes[:40]}",
                        where="Goals",
                    )
                )
            else:
                titles = [f"• {g.title}" for g in goals[:5]]
                return ActionResult(
                    success=False,
                    message=f"I found {count} goals matching '{goal_keyword}':\n" + "\n".join(titles) + "\nWhich one?",
                    error='multiple_matches'
                )

        except Exception as e:
            logger.error(f"Error updating goal: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't update that goal.",
                error=str(e)
            )

    def handle_set_intention(self, intention: str, description: str = "",
                              motivation: str = "", **kwargs) -> ActionResult:
        """
        Create a change intention (identity-based).

        Args:
            intention: The intention statement (e.g., "Be more present")
            description: What this means
            motivation: Why it matters
        """
        from apps.purpose.models import ChangeIntention

        try:
            intent = ChangeIntention.objects.create(
                user=self.user,
                intention=intention,
                description=description or "",
                motivation=motivation or "",
                intention_status='active'
            )

            return ActionResult(
                success=True,
                message=f"✓ Set intention: {intention}",
                created_object={
                    'model': 'ChangeIntention',
                    'id': intent.id,
                    'intention': intent.intention,
                    'created_at': intent.created_at.isoformat()
                },
                action_type='set_intention',
                confirmation_detail=self._build_confirmation(
                    what=intention,
                    where="Goals > Intentions",
                )
            )

        except Exception as e:
            logger.error(f"Error setting intention: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't set that intention.",
                error=str(e)
            )

    def handle_log_habit(self, habit_keyword: str, completed: bool = True,
                          notes: str = "", **kwargs) -> ActionResult:
        """
        Log daily habit completion.

        Args:
            habit_keyword: Keywords to find the habit
            completed: Whether habit was completed
            notes: Optional notes
        """
        from apps.purpose.models import HabitGoal, HabitEntry

        try:
            habits = HabitGoal.objects.filter(
                user=self.user,
                status='active'
            ).filter(
                Q(name__icontains=habit_keyword) |
                Q(description__icontains=habit_keyword)
            )

            count = habits.count()

            if count == 0:
                # No habit found — check if there's a matching task to suggest
                task = self._find_task_suggestion(habit_keyword)
                if task:
                    return ActionResult(
                        success=False,
                        message=(
                            f"I couldn't find an active habit matching '{habit_keyword}', "
                            f"but I see a task called '{task.title}'. "
                            f"Would you like me to mark it complete?"
                        ),
                        error='habit_not_found'
                    )
                return ActionResult(
                    success=False,
                    message=f"I couldn't find an active habit matching '{habit_keyword}'.",
                    error='habit_not_found'
                )
            elif count == 1:
                habit = habits.first()
                recorded_at = self._get_recorded_at(kwargs)
                today = recorded_at.date() if hasattr(recorded_at, 'date') else self._get_user_today()

                # Create or update today's entry
                entry, created = HabitEntry.objects.get_or_create(
                    goal=habit,
                    date=today,
                    session_number=1,
                    defaults={'completed': completed, 'notes': notes or ""}
                )

                if not created:
                    entry.completed = completed
                    entry.notes = notes or entry.notes
                    entry.save()

                status = "completed" if completed else "skipped"

                # Trend lookup — weekly habit count (safe — never blocks action)
                trend = None
                try:
                    import datetime as dt
                    today_for_trend = self._get_user_today()
                    week_start = today_for_trend - dt.timedelta(days=today_for_trend.weekday())
                    weekly = HabitEntry.objects.filter(
                        goal__user=self.user,
                        date__gte=week_start
                    ).count()
                    if weekly:
                        trend = f"{weekly} habit log{'s' if weekly != 1 else ''} this week"
                except Exception:
                    pass

                # Cross-complete: also mark matching task complete
                task_msg = self._cross_complete_task(habit_keyword)
                msg = f"✓ Logged habit: {habit.name} - {status}"
                if task_msg:
                    msg += f"\n{task_msg}"

                return ActionResult(
                    success=True,
                    message=msg,
                    created_object={
                        'model': 'HabitEntry',
                        'id': entry.id,
                        'habit_name': habit.name,
                        'completed': entry.completed,
                        'date': entry.date.isoformat()
                    },
                    action_type='log_habit',
                    confirmation_detail=self._build_confirmation(
                        what=habit.name,
                        where="Goals > Habits",
                        trend=trend,
                    )
                )
            else:
                names = [f"• {h.name}" for h in habits[:5]]
                return ActionResult(
                    success=False,
                    message=f"I found {count} habits matching '{habit_keyword}':\n" + "\n".join(names) + "\nWhich one?",
                    error='multiple_matches'
                )

        except Exception as e:
            logger.error(f"Error logging habit: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log that habit.",
                error=str(e)
            )

    # =========================================================================
    # LIFE HANDLERS
    # =========================================================================

    def handle_create_task(self, title: str, notes: str = "", due_date: str = None,
                           priority: str = None, effort: str = "small",
                           project_name: str = None, scheduled_time: str = None,
                           duration_minutes: int = None, end_time: str = None,
                           **kwargs) -> ActionResult:
        """
        Create a new task.

        Args:
            title: Task title
            notes: Additional notes
            due_date: When task is due
            priority: now, soon, someday
            effort: quick, small, medium, large
            project_name: Name of project to associate
            scheduled_time: Specific time in HH:MM format (e.g., '10:00')
            duration_minutes: Duration in minutes when scheduled_time is set
            end_time: End time in HH:MM format (e.g., '18:00') for time ranges
        """
        from apps.life.models import Task, Project
        from datetime import datetime as dt, timedelta

        try:
            # Parse due date
            parsed_due = None
            if due_date:
                due_lower = due_date.lower()
                today = self._get_user_today()

                if due_lower == 'today':
                    parsed_due = today
                elif due_lower == 'tomorrow':
                    parsed_due = today + timedelta(days=1)
                elif due_lower == 'next week':
                    parsed_due = today + timedelta(days=7)
                else:
                    try:
                        parsed_due = dt.strptime(due_date, '%Y-%m-%d').date()
                    except ValueError:
                        pass

            # Parse scheduled_time (HH:MM format)
            parsed_time = None
            if scheduled_time:
                try:
                    parsed_time = dt.strptime(scheduled_time, '%H:%M').time()
                    # If user specified a time but no date, default to today
                    if not parsed_due:
                        parsed_due = self._get_user_today()
                except ValueError:
                    pass

            # Find project if specified
            project = None
            if project_name:
                project = Project.objects.filter(
                    user=self.user,
                    title__icontains=project_name,
                    status='active'
                ).first()

            # Parse end_time (HH:MM format)
            parsed_end_time = None
            if end_time:
                try:
                    parsed_end_time = dt.strptime(end_time, '%H:%M').time()
                except ValueError:
                    pass

            # Auto-compute duration from time range if both start and end provided
            if parsed_time and parsed_end_time and not duration_minutes:
                from datetime import timedelta
                start_tmp = dt.combine(self._get_user_today(), parsed_time)
                end_tmp = dt.combine(self._get_user_today(), parsed_end_time)
                if end_tmp > start_tmp:
                    duration_minutes = int((end_tmp - start_tmp).total_seconds() / 60)

            task_kwargs = dict(
                user=self.user,
                title=title,
                notes=notes or "",
                due_date=parsed_due,
                effort=effort,
                project=project,
            )
            if parsed_time:
                task_kwargs['scheduled_time'] = parsed_time
                if parsed_end_time:
                    task_kwargs['scheduled_end_time'] = parsed_end_time
                if duration_minutes:
                    task_kwargs['estimated_duration_minutes'] = duration_minutes

            task = Task.objects.create(**task_kwargs)

            # Task priority is auto-calculated from due date

            if parsed_time and parsed_end_time:
                start_str = parsed_time.strftime('%I:%M %p').lstrip('0')
                end_str = parsed_end_time.strftime('%I:%M %p').lstrip('0')
                time_str = f" at {start_str} – {end_str}"
            elif parsed_time:
                time_str = f" at {parsed_time.strftime('%I:%M %p').lstrip('0')}"
            else:
                time_str = ""
            due_str = f" (due {parsed_due.strftime('%b %d')}{time_str})" if parsed_due else ""
            project_str = f" in {project.title}" if project else ""

            # Include a helpful link to where they can find the task
            task_url = "/life/tasks/"
            location_hint = f" You can find it in [Organize → Tasks]({task_url})."

            # Risk lookup — tasks due this week (safe — never blocks action)
            risk = None
            try:
                import datetime as dt
                today = self._get_user_today()
                week_end = today + dt.timedelta(days=(6 - today.weekday()))
                due_this_week = Task.objects.filter(
                    user=self.user,
                    completion_status='pending',
                    status='active',
                    due_date__lte=week_end,
                ).count()
                if due_this_week > 1:
                    risk = f"{due_this_week} tasks due this week"
            except Exception:
                pass

            return ActionResult(
                success=True,
                message=f"✓ Created task: {title}{due_str}{project_str}.{location_hint}",
                created_object={
                    'model': 'Task',
                    'id': task.id,
                    'title': task.title,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'priority': task.priority,
                    'project_id': project.id if project else None,
                    'url': task_url
                },
                action_type='create_task',
                confirmation_detail=self._build_confirmation(
                    what=title,
                    where="Organize > Tasks",
                    risk=risk,
                )
            )

        except Exception as e:
            logger.error(f"Error creating task: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't create that task.",
                error=str(e)
            )

    def handle_create_routine_task(
        self,
        title: str,
        scheduled_time: str,
        end_time: str = "",
        duration_minutes: int = 30,
        recurrence_pattern: str = "daily",
        notes: str = "",
        **kwargs,
    ) -> ActionResult:
        """
        Create a daily routine task with scheduled time and CoS prompting.

        Args:
            title: Routine name (e.g., 'Quiet Time', 'Morning Workout')
            scheduled_time: Begin time in HH:MM 24-hour format
            end_time: End time in HH:MM 24-hour format (optional, computed from duration if omitted)
            duration_minutes: Estimated duration (default 30, used if end_time not provided)
            recurrence_pattern: How often (daily, weekdays, weekly:mon,wed,fri)
            notes: Additional notes
        """
        from apps.life.models import Task
        from datetime import time as dt_time

        logger.info(
            "handle_create_routine_task called: title=%s time=%s end=%s "
            "duration=%s recurrence=%s user=%s",
            title, scheduled_time, end_time, duration_minutes,
            recurrence_pattern, self.user.id,
        )

        try:
            # Parse scheduled_time
            parts = scheduled_time.replace('.', ':').split(':')
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            sched_time = dt_time(hour, minute)

            # Normalize common recurrence aliases
            pattern_lower = recurrence_pattern.lower().strip()
            if pattern_lower in ('weekdays', 'every weekday', 'every_weekday'):
                recurrence_pattern = 'every_weekday'
            elif pattern_lower in ('daily', 'every day', 'everyday'):
                recurrence_pattern = 'daily'

            today = self._get_user_today()

            # Parse end_time if provided
            sched_end_time = None
            if end_time:
                end_parts = end_time.replace('.', ':').split(':')
                end_hour = int(end_parts[0])
                end_minute = int(end_parts[1]) if len(end_parts) > 1 else 0
                sched_end_time = dt_time(end_hour, end_minute)
                # Compute duration from times if end_time is explicit
                from datetime import datetime as dt_datetime, timedelta
                start_tmp = dt_datetime.combine(today, sched_time)
                end_tmp = dt_datetime.combine(today, sched_end_time)
                if end_tmp > start_tmp:
                    duration_minutes = int((end_tmp - start_tmp).total_seconds() / 60)

            task = Task.objects.create(
                user=self.user,
                title=title,
                notes=notes or "",
                due_date=today,
                is_routine=True,
                is_recurring=True,
                recurrence_pattern=recurrence_pattern,
                start_date=today,
                scheduled_time=sched_time,
                scheduled_end_time=sched_end_time,
                estimated_duration_minutes=duration_minutes,
                effort='small',
            )

            # Verify the task actually persisted
            verify = Task.all_objects.filter(pk=task.pk).exists()
            logger.info(
                "Routine task created: id=%s title='%s' due=%s persisted=%s",
                task.pk, task.title, task.due_date, verify,
            )

            time_str = sched_time.strftime('%I:%M %p').lstrip('0')
            if sched_end_time:
                end_time_str = sched_end_time.strftime('%I:%M %p').lstrip('0')
                time_display = f"{time_str} – {end_time_str}"
            else:
                time_display = f"{time_str} ({duration_minutes} min)"
            task_url = "/life/tasks/"

            return ActionResult(
                success=True,
                message=(
                    f"✓ Created routine: **{title}** {time_display} "
                    f"({recurrence_pattern}). "
                    f"I'll prompt you before and check in after. "
                    f"[View in Tasks]({task_url})"
                ),
                created_object={
                    'model': 'Task',
                    'id': task.id,
                    'title': task.title,
                    'scheduled_time': str(sched_time),
                    'duration_minutes': duration_minutes,
                    'recurrence_pattern': recurrence_pattern,
                    'is_routine': True,
                },
                action_type='create_routine_task',
                confirmation_detail=self._build_confirmation(
                    what=f"{title} at {time_str} ({recurrence_pattern})",
                    where="Organize > Tasks + Calendar",
                )
            )

        except Exception as e:
            logger.error(f"Error creating routine task: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't create that routine.",
                error=str(e),
            )

    def handle_complete_task(self, task_keyword: str, notes: str = "",
                              **kwargs) -> ActionResult:
        """
        Mark a task as complete.

        Args:
            task_keyword: Keywords to find the task
            notes: Completion notes
        """
        from apps.life.models import Task

        try:
            # Check for pre-resolved task ID (from clarification flow)
            resolved_id = kwargs.get('_resolved_id')
            if resolved_id:
                try:
                    tasks = [Task.objects.get(
                        pk=resolved_id, user=self.user, status='active',
                    )]
                except Task.DoesNotExist:
                    return ActionResult(
                        success=False,
                        message="That task no longer exists or was already completed.",
                        error='task_not_found',
                        action_type='complete_task',
                    )
            else:
                tasks, _ = self._resolve_tasks_by_query(task_keyword)

            count = len(tasks)

            if count == 0:
                # No task found — check if there's a matching habit to suggest
                habit = self._find_habit_suggestion(task_keyword)
                if habit:
                    return ActionResult(
                        success=False,
                        message=(
                            f"I couldn't find an incomplete task matching '{task_keyword}', "
                            f"but I see a habit called '{habit.name}'. "
                            f"Would you like me to log it as completed for today?"
                        ),
                        error='task_not_found'
                    )
                return ActionResult(
                    success=False,
                    message=f"I couldn't find an incomplete task matching '{task_keyword}'.",
                    error='task_not_found'
                )
            elif count == 1:
                task = tasks[0]
                if notes:
                    task.notes = (task.notes + "\n" + notes).strip() if task.notes else notes
                    task.save(update_fields=['notes', 'updated_at'])
                task.mark_complete()  # handles recurrence + calendar sync + CoS

                # Cross-complete: also log matching habit
                habit_msg = self._cross_log_habit(task_keyword)
                msg = f"✓ Completed: {task.title}"
                if habit_msg:
                    msg += f"\n{habit_msg}"

                return ActionResult(
                    success=True,
                    message=msg,
                    created_object={
                        'model': 'Task',
                        'id': task.id,
                        'title': task.title,
                        'completed_at': task.completed_at.isoformat()
                    },
                    action_type='complete_task',
                    confirmation_detail=self._build_confirmation(
                        what=task.title,
                        where="Organize > Tasks",
                    )
                )
            else:
                candidates = [{'id': t.id, 'title': t.title} for t in tasks[:5]]
                titles = [f"• {c['title']}" for c in candidates]
                return ActionResult(
                    success=False,
                    message=f"I found {count} tasks matching '{task_keyword}':\n" + "\n".join(titles) + "\nWhich one?",
                    error='multiple_matches',
                    action_type='complete_task',
                    created_object={'candidates': candidates},
                )

        except Exception as e:
            logger.error(f"Error completing task: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't complete that task.",
                error=str(e)
            )

    def handle_skip_task(self, task_keyword: str, reason: str = "", **kwargs) -> ActionResult:
        """Mark a task as skipped (intentionally not completed)."""
        from apps.life.models import Task

        try:
            resolved_id = kwargs.get('_resolved_id')
            if resolved_id:
                try:
                    tasks = [Task.objects.get(
                        pk=resolved_id, user=self.user, status='active',
                    )]
                except Task.DoesNotExist:
                    return ActionResult(
                        success=False,
                        message="That task no longer exists.",
                        error='task_not_found',
                        action_type='skip_task',
                    )
            else:
                tasks, _ = self._resolve_tasks_by_query(task_keyword)

            count = len(tasks)

            if count == 0:
                return ActionResult(
                    success=False,
                    message=f"I couldn't find a pending task matching '{task_keyword}'.",
                    error='task_not_found',
                    action_type='skip_task',
                )
            elif count == 1:
                task = tasks[0]
                if reason:
                    task.notes = (task.notes + "\nSkipped: " + reason).strip() if task.notes else "Skipped: " + reason
                    task.save(update_fields=['notes', 'updated_at'])
                task.mark_skipped()

                return ActionResult(
                    success=True,
                    message=f"Skipped: {task.title}",
                    created_object={
                        'model': 'Task',
                        'id': task.id,
                        'title': task.title,
                        'completion_status': 'skipped',
                    },
                    action_type='skip_task',
                    confirmation_detail=self._build_confirmation(
                        what=task.title,
                        where="Organize > Tasks",
                    )
                )
            else:
                candidates = [{'id': t.id, 'title': t.title} for t in tasks[:5]]
                titles = [f"• {c['title']}" for c in candidates]
                return ActionResult(
                    success=False,
                    message=f"I found {count} tasks matching '{task_keyword}':\n" + "\n".join(titles) + "\nWhich one?",
                    error='multiple_matches',
                    action_type='skip_task',
                    created_object={'candidates': candidates},
                )

        except Exception as e:
            logger.error(f"Error skipping task: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't skip that task.",
                error=str(e),
            )

    def handle_mutate_task(
        self,
        action: str,
        task_query: str,
        new_due_date: str = None,
        new_scheduled_time: str = None,
        new_end_time: str = None,
        new_title: str = None,
        new_notes: str = None,
        new_effort: str = None,
        apply_to_all: bool = False,
        **kwargs,
    ) -> ActionResult:
        """
        Reschedule, rename, update, or delete a task.

        Args:
            action: 'update' or 'delete'
            task_query: Keywords to find the task(s)
            new_due_date: New due date (natural language or YYYY-MM-DD)
            new_scheduled_time: New scheduled time in HH:MM format
            new_end_time: New end time in HH:MM format
            new_title: New title if renaming
            new_notes: New notes
            new_effort: New effort level
            apply_to_all: Apply to all matching tasks (for batch operations)
        """
        from apps.life.models import Task
        from apps.calendar_engine.utils.date_resolution import resolve_weekday_to_date
        from datetime import datetime as dt

        try:
            # Check for pre-resolved task ID (from clarification flow)
            resolved_id = kwargs.get('_resolved_id')
            if resolved_id:
                try:
                    tasks = [Task.objects.get(
                        pk=resolved_id, user=self.user, status='active',
                    )]
                except Task.DoesNotExist:
                    return ActionResult(
                        success=False,
                        message="That task no longer exists.",
                        error='task_not_found',
                        action_type='mutate_task',
                    )
            else:
                # Find matching tasks with literal-first matching
                tasks, _ = self._resolve_tasks_by_query(task_query)

            count = len(tasks)

            if count == 0:
                return ActionResult(
                    success=False,
                    message=f"I couldn't find an active task matching '{task_query}'.",
                    error='task_not_found',
                    action_type='mutate_task',
                )

            if count > 1 and not apply_to_all:
                candidates = [{'id': t.id, 'title': t.title} for t in tasks[:5]]
                titles = [f"• {c['title']}" for c in candidates]
                return ActionResult(
                    success=False,
                    message=(
                        f"I found {count} tasks matching '{task_query}':\n"
                        + "\n".join(titles)
                        + "\nWhich one? Or say 'all of them' to update all."
                    ),
                    error='multiple_matches',
                    action_type='mutate_task',
                    created_object={'candidates': candidates},
                )

            tasks = tasks[:10]  # Safety limit

            if action == 'delete':
                delete_confirmed = kwargs.get('delete_confirmed', False)

                # Safety: ALWAYS require confirmation before deleting
                if not delete_confirmed:
                    titles = [f"• {t.title}" for t in tasks[:5]]
                    task_word = "task" if len(tasks) == 1 else f"{len(tasks)} tasks"
                    return ActionResult(
                        success=False,
                        message=(
                            f"Just to confirm — you want me to delete this {task_word}?\n"
                            + "\n".join(titles)
                            + "\n\nSay 'yes, delete' to confirm."
                        ),
                        error='delete_confirmation_required',
                        action_type='mutate_task',
                        created_object={
                            'candidates': [
                                {'id': t.id, 'title': t.title} for t in tasks[:5]
                            ],
                        },
                    )

                # Batch delete (>2 tasks) still requires explicit apply_to_all
                if len(tasks) > 2 and not apply_to_all:
                    candidates = [{'id': t.id, 'title': t.title} for t in tasks[:5]]
                    titles = [f"• {c['title']}" for c in candidates]
                    return ActionResult(
                        success=False,
                        message=(
                            f"I found {len(tasks)} tasks matching '{task_query}':\n"
                            + "\n".join(titles)
                            + "\nThat's a lot of tasks to delete. Which one did you mean? "
                            "Or say 'delete all of them' to confirm."
                        ),
                        error='multiple_matches',
                        action_type='mutate_task',
                        created_object={'candidates': candidates},
                    )

                deleted_titles = []
                for task in tasks:
                    task.soft_delete()
                    deleted_titles.append(task.title)

                if len(deleted_titles) == 1:
                    msg = f"✓ Deleted task: {deleted_titles[0]}"
                else:
                    msg = f"✓ Deleted {len(deleted_titles)} tasks: {', '.join(deleted_titles)}"

                return ActionResult(
                    success=True,
                    message=msg,
                    created_object={
                        'model': 'Task',
                        'ids': [t.id for t in tasks],
                        'action': 'delete',
                    },
                    action_type='mutate_task',
                    confirmation_detail=self._build_confirmation(
                        what=', '.join(deleted_titles),
                        where="Organize > Tasks",
                    ),
                )

            elif action == 'update':
                # Parse new due date using the same date resolution as calendar
                parsed_due = None
                if new_due_date:
                    try:
                        parsed_due = resolve_weekday_to_date(self.user, new_due_date)
                    except ValueError:
                        # Fallback to simple parsing
                        due_lower = new_due_date.lower()
                        today = self._get_user_today()
                        if due_lower == 'today':
                            parsed_due = today
                        elif due_lower == 'tomorrow':
                            from datetime import timedelta
                            parsed_due = today + timedelta(days=1)
                        else:
                            try:
                                parsed_due = dt.strptime(new_due_date, '%Y-%m-%d').date()
                            except ValueError:
                                return ActionResult(
                                    success=False,
                                    message=f"I couldn't understand the date '{new_due_date}'. Try 'tomorrow', 'next monday', or a specific date.",
                                    error='invalid_date',
                                    action_type='mutate_task',
                                )

                # Parse new scheduled time
                parsed_time = None
                if new_scheduled_time:
                    try:
                        parsed_time = dt.strptime(new_scheduled_time, '%H:%M').time()
                    except ValueError:
                        return ActionResult(
                            success=False,
                            message=f"I couldn't understand the time '{new_scheduled_time}'. Use HH:MM format (e.g., '14:00').",
                            error='invalid_time',
                            action_type='mutate_task',
                        )

                # Parse new end time
                parsed_end_time = None
                if new_end_time:
                    try:
                        parsed_end_time = dt.strptime(new_end_time, '%H:%M').time()
                    except ValueError:
                        return ActionResult(
                            success=False,
                            message=f"I couldn't understand the end time '{new_end_time}'. Use HH:MM format (e.g., '18:00').",
                            error='invalid_time',
                            action_type='mutate_task',
                        )

                # Apply updates — skip fields that are already at the target value
                updated_titles = []
                changes_desc = []
                any_actual_change = False
                for task in tasks:
                    update_fields = ['updated_at']

                    if parsed_due is not None and task.due_date != parsed_due:
                        task.due_date = parsed_due
                        update_fields.append('due_date')
                        any_actual_change = True

                    if parsed_time is not None and task.scheduled_time != parsed_time:
                        task.scheduled_time = parsed_time
                        update_fields.append('scheduled_time')
                        any_actual_change = True

                    if parsed_end_time is not None and task.scheduled_end_time != parsed_end_time:
                        task.scheduled_end_time = parsed_end_time
                        update_fields.append('scheduled_end_time')
                        any_actual_change = True

                    if new_title and task.title != new_title:
                        task.title = new_title
                        update_fields.append('title')
                        any_actual_change = True

                    if new_notes and task.notes != new_notes:
                        task.notes = new_notes
                        update_fields.append('notes')
                        any_actual_change = True

                    if new_effort and task.effort != new_effort:
                        task.effort = new_effort
                        update_fields.append('effort')
                        any_actual_change = True

                    if len(update_fields) > 1:
                        # Only save if we actually changed something
                        task.save(update_fields=update_fields)

                    updated_titles.append(task.title)

                # If nothing actually changed, report that it's already set
                if not any_actual_change:
                    already_parts = []
                    if parsed_due is not None:
                        already_parts.append(f"due {parsed_due.strftime('%b %d')}")
                    if parsed_time is not None:
                        already_parts.append(f"at {parsed_time.strftime('%I:%M %p').lstrip('0')}")
                    title_list = ', '.join(f"'{t}'" for t in updated_titles)
                    already_desc = ' → '.join(already_parts) if already_parts else 'at the requested values'
                    return ActionResult(
                        success=True,
                        message=f"{title_list} is already {already_desc}. No changes needed.",
                        action_type='mutate_task',
                    )

                # Build change description
                if parsed_due is not None and 'due_date' in update_fields:
                    changes_desc.append(f"due {parsed_due.strftime('%b %d')}")
                if parsed_time is not None and parsed_end_time is not None:
                    if 'scheduled_time' in update_fields or 'scheduled_end_time' in update_fields:
                        changes_desc.append(
                            f"at {parsed_time.strftime('%I:%M %p').lstrip('0')} – "
                            f"{parsed_end_time.strftime('%I:%M %p').lstrip('0')}"
                        )
                elif parsed_time is not None and 'scheduled_time' in update_fields:
                    changes_desc.append(f"at {parsed_time.strftime('%I:%M %p').lstrip('0')}")
                elif parsed_end_time is not None and 'scheduled_end_time' in update_fields:
                    changes_desc.append(f"end time {parsed_end_time.strftime('%I:%M %p').lstrip('0')}")
                if new_title and 'title' in update_fields:
                    changes_desc.append(f"renamed to '{new_title}'")
                if new_effort:
                    changes_desc.append(f"effort: {new_effort}")

                changes_str = ", ".join(changes_desc) if changes_desc else "updated"

                if len(updated_titles) == 1:
                    msg = f"✓ Updated '{updated_titles[0]}' → {changes_str}"
                else:
                    msg = f"✓ Updated {len(updated_titles)} tasks → {changes_str}:\n" + "\n".join(f"• {t}" for t in updated_titles)

                return ActionResult(
                    success=True,
                    message=msg,
                    created_object={
                        'model': 'Task',
                        'ids': [t.id for t in tasks],
                        'action': 'update',
                        'changes': changes_desc,
                    },
                    action_type='mutate_task',
                    confirmation_detail=self._build_confirmation(
                        what=', '.join(updated_titles),
                        where="Organize > Tasks",
                    ),
                )

            else:
                return ActionResult(
                    success=False,
                    message=f"Unknown action: {action}. Use 'update' or 'delete'.",
                    error='invalid_action',
                    action_type='mutate_task',
                )

        except Exception as e:
            logger.error(f"Error mutating task: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't update that task.",
                error=str(e),
            )

    def handle_read_task(self, task_keyword: str = None, date_filter: str = None,
                         include_completed: bool = False, **kwargs) -> ActionResult:
        """
        Look up task details — time, due date, status, scheduled time.
        Queries both the Task model and its CalendarEvent projection for
        accurate time reporting.

        Args:
            task_keyword: Keywords to search in task titles
            date_filter: 'today', 'tomorrow', 'this_week', 'overdue', or YYYY-MM-DD
            include_completed: Include completed tasks
        """
        from apps.life.models import Task
        from apps.calendar_engine.models import CalendarEvent
        import datetime as dt

        try:
            today = self._get_user_today()
            qs = Task.objects.filter(user=self.user, status='active')

            if not include_completed:
                qs = qs.filter(completion_status='pending')

            # Keyword filter
            if task_keyword:
                qs = qs.filter(
                    Q(title__icontains=task_keyword) |
                    Q(notes__icontains=task_keyword)
                )

            # Date filter
            if date_filter:
                df = date_filter.lower()
                if df == 'today':
                    qs = qs.filter(due_date=today)
                elif df == 'tomorrow':
                    qs = qs.filter(due_date=today + dt.timedelta(days=1))
                elif df == 'this_week':
                    week_end = today + dt.timedelta(days=(6 - today.weekday()))
                    qs = qs.filter(due_date__gte=today, due_date__lte=week_end)
                elif df == 'overdue':
                    qs = qs.filter(due_date__lt=today, completion_status='pending')
                else:
                    try:
                        filter_date = dt.datetime.strptime(df, '%Y-%m-%d').date()
                        qs = qs.filter(due_date=filter_date)
                    except ValueError:
                        pass

            tasks = list(qs.order_by('due_date', 'scheduled_time')[:20])

            if not tasks:
                search_desc = f" matching '{task_keyword}'" if task_keyword else ""
                return ActionResult(
                    success=True,
                    message=f"No tasks found{search_desc}.",
                    created_object={'tasks': [], 'count': 0},
                    action_type='read_task',
                )

            # Get user timezone for calendar event time display
            try:
                from zoneinfo import ZoneInfo
                user_tz = ZoneInfo(self.user.preferences.timezone_iana)
            except Exception:
                from zoneinfo import ZoneInfo
                user_tz = ZoneInfo('America/Chicago')

            # Build detailed task list with calendar event times
            task_list = []
            for task in tasks:
                task_info = {
                    'id': task.id,
                    'title': task.title,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'is_completed': task.is_completed,
                    'priority': task.priority,
                    'effort': task.effort,
                    'scheduled_time': task.scheduled_time.strftime('%I:%M %p').lstrip('0') if task.scheduled_time else None,
                }

                # Look up the CalendarEvent for authoritative display time
                cal_event = CalendarEvent.objects.filter(
                    user=self.user,
                    source_type=CalendarEvent.SOURCE_TASK,
                    source_id=str(task.pk),
                ).exclude(status=CalendarEvent.STATUS_CANCELED).first()

                if cal_event:
                    local_start = cal_event.start_dt.astimezone(user_tz)
                    local_end = cal_event.end_dt.astimezone(user_tz)
                    task_info['calendar_start'] = local_start.strftime('%I:%M %p').lstrip('0')
                    task_info['calendar_end'] = local_end.strftime('%I:%M %p').lstrip('0')
                    task_info['calendar_kind'] = cal_event.event_kind

                task_list.append(task_info)

            # Build human-readable message with FULL details
            count = len(task_list)
            if count == 1:
                t = task_list[0]
                parts = [f"**{t['title']}**"]
                if t.get('due_date'):
                    parts.append(f"Due: {t['due_date']}")
                if t.get('calendar_start'):
                    # Use calendar event time (authoritative) for ALL event kinds
                    parts.append(f"Scheduled: {t['calendar_start']} – {t['calendar_end']}")
                elif t.get('scheduled_time'):
                    parts.append(f"Scheduled: {t['scheduled_time']}")
                if t.get('priority'):
                    parts.append(f"Priority: {t['priority']}")
                if t.get('is_completed'):
                    parts.append("Status: ✓ Completed")
                msg = " | ".join(parts)
            else:
                lines = [f"Found {count} tasks:"]
                for t in task_list:
                    time_str = ""
                    if t.get('calendar_start'):
                        # Use calendar event time (authoritative) for ALL event kinds
                        time_str = f" at {t['calendar_start']}"
                    elif t.get('scheduled_time'):
                        time_str = f" at {t['scheduled_time']}"
                    due_str = f" (due {t['due_date']})" if t.get('due_date') else ""
                    status = " ✓" if t.get('is_completed') else ""
                    lines.append(f"- {t['title']}{time_str}{due_str}{status}")
                msg = "\n".join(lines)

            return ActionResult(
                success=True,
                message=msg,
                created_object={'tasks': task_list, 'count': count},
                action_type='read_task',
            )

        except Exception as e:
            logger.error("handle_read_task failed for user=%s: %s",
                         self.user.id, e, exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't look up that task.",
                error=str(e),
                action_type='read_task',
            )

    # =========================================================================
    # SCHEDULING CONTEXT — for "same" / clone parameter inheritance
    # =========================================================================

    @staticmethod
    def _get_scheduling_context(user):
        """Retrieve the last scheduling context from cache."""
        from django.core.cache import cache
        return cache.get(f'scheduling_context_{user.id}')

    @staticmethod
    def _store_scheduling_context(user, context):
        """Store scheduling context in cache (30-min TTL — session scope)."""
        from django.core.cache import cache
        cache.set(f'scheduling_context_{user.id}', context, timeout=1800)

    def handle_create_event(self, title: str, start_date: str,
                             description: str = "", start_time: str = None,
                             end_time: str = None, is_all_day: bool = False,
                             location: str = "", event_type: str = "personal",
                             reminder_minutes: int = None, **kwargs) -> ActionResult:
        """
        Create a CalendarEvent (Time Command Center) with CoS integration.

        Creates in calendar_engine.CalendarEvent so events appear in the
        Time Command Center at /calendar/.

        After creating the event, runs the CoS post-scheduling chain:
        1. Conflict detection (priority_engine)
        2. Drift/pressure recomputation
        3. Google Calendar sync (if connected)

        Scheduling reliability contract:
        - Dates anchored to get_current_local_datetime(user), never server UTC
        - clone_from_last=True inherits all params from prior scheduling action
        - No default time fallback allowed during cloning
        - Debug logging at every decision point

        Args:
            title: Event title
            start_date: Event date ('today', 'tomorrow', weekday name, or YYYY-MM-DD)
            description: Event description
            start_time: Start time (HH:MM)
            end_time: End time (HH:MM)
            is_all_day: Whether all-day event
            location: Event location
            event_type: Type of event (personal, work, health, etc.)
            reminder_minutes: Minutes before for reminder
            **kwargs: clone_from_last (bool), recorded_at (datetime)
        """
        from apps.calendar_engine.models import CalendarEvent
        from datetime import datetime as dt
        from django.utils import timezone as tz

        try:
            # --- Authoritative local date/time (Part 1) ---
            from apps.core.utils import get_current_local_datetime
            user_now = get_current_local_datetime(self.user)
            today = user_now.date()
            user_tz = user_now.tzinfo

            logger.debug(
                "[SCHED] Base local datetime: %s (tz=%s, user=%s)",
                user_now.isoformat(), user_tz, self.user.id,
            )

            # --- Clone inheritance (Part 2) ---
            clone_from_last = kwargs.get('clone_from_last', False)
            prior_ctx = None
            if clone_from_last:
                prior_ctx = self._get_scheduling_context(self.user)
                if prior_ctx:
                    logger.debug(
                        "[SCHED] Clone mode: inheriting from prior context %r",
                        prior_ctx,
                    )
                    # Inherit missing parameters from prior context
                    if not start_time and prior_ctx.get('start_time'):
                        start_time = prior_ctx['start_time']
                        logger.debug(
                            "[SCHED] Inherited start_time=%s from prior event",
                            start_time,
                        )
                    if not end_time and prior_ctx.get('end_time'):
                        end_time = prior_ctx['end_time']
                    if not description and prior_ctx.get('description'):
                        description = prior_ctx['description']
                    if not location and prior_ctx.get('location'):
                        location = prior_ctx['location']
                    if event_type == 'personal' and prior_ctx.get('event_type'):
                        event_type = prior_ctx['event_type']
                    if is_all_day is False and prior_ctx.get('is_all_day'):
                        is_all_day = prior_ctx['is_all_day']
                else:
                    logger.warning(
                        "[SCHED] clone_from_last=True but no prior scheduling "
                        "context found for user %s", self.user.id,
                    )

            # Parse times BEFORE date resolution (Phase 9.1)
            # so start_time can inform same-day weekday logic.
            parsed_start_time = None
            parsed_end_time = None

            if start_time and not is_all_day:
                try:
                    parsed_start_time = dt.strptime(start_time, '%H:%M').time()
                except ValueError:
                    pass

            if end_time and not is_all_day:
                try:
                    parsed_end_time = dt.strptime(end_time, '%H:%M').time()
                except ValueError:
                    pass

            # --- Deterministic date resolution (Phase 9) ---
            # All weekday/relative-date resolution is server-side;
            # never trust LLM-provided date computations.
            from apps.calendar_engine.utils.date_resolution import (
                resolve_weekday_to_date,
            )
            try:
                event_date = resolve_weekday_to_date(
                    self.user, start_date, reference_dt=user_now,
                    start_time=parsed_start_time,
                )
                logger.debug(
                    "[SCHED] Resolved '%s' → %s (deterministic)",
                    start_date, event_date,
                )
            except ValueError as date_err:
                logger.warning(
                    "[SCHED] Date resolution failed for '%s': %s — "
                    "falling back to today %s",
                    start_date, date_err, today,
                )
                event_date = today

            # --- Safety invariant (Part 3): no default-time during clone ---
            actual_all_day = is_all_day or (parsed_start_time is None)

            if actual_all_day and not is_all_day:
                # Time was defaulted automatically (no start_time provided)
                logger.warning(
                    "[SCHED] Time defaulted to all-day — no start_time "
                    "provided for '%s' on %s (clone=%s)",
                    title, event_date, clone_from_last,
                )
                if clone_from_last and prior_ctx and prior_ctx.get('start_time'):
                    # This should never happen: clone was requested, prior
                    # context had a time, but inheritance didn't work.
                    logger.error(
                        "[SCHED] INVARIANT VIOLATION: clone requested with "
                        "prior time=%s but parsed_start_time is None",
                        prior_ctx['start_time'],
                    )

            if actual_all_day:
                # All-day: midnight to midnight
                import datetime as datetime_mod
                naive_start = dt.combine(event_date, datetime_mod.time.min)
                naive_end = dt.combine(event_date, datetime_mod.time(23, 59, 59))
            else:
                naive_start = dt.combine(event_date, parsed_start_time)
                if parsed_end_time:
                    naive_end = dt.combine(event_date, parsed_end_time)
                else:
                    # Default: 1 hour after start
                    naive_end = naive_start + timedelta(hours=1)

            # Make timezone-aware using user's timezone
            start_dt = tz.make_aware(naive_start, user_tz)
            end_dt = tz.make_aware(naive_end, user_tz)

            logger.debug(
                "[SCHED] Final event: title=%s, start_dt=%s, end_dt=%s, "
                "all_day=%s, tz=%s",
                title, start_dt.isoformat(), end_dt.isoformat(),
                actual_all_day, user_tz,
            )

            # --- Clone assertion (Part 3) ---
            if clone_from_last and prior_ctx and prior_ctx.get('start_time'):
                if not actual_all_day:
                    prior_time_str = prior_ctx['start_time']
                    try:
                        prior_time = dt.strptime(prior_time_str, '%H:%M').time()
                        assert parsed_start_time == prior_time, (
                            f"Clone time mismatch: cloned={parsed_start_time}, "
                            f"original={prior_time}"
                        )
                        logger.debug(
                            "[SCHED] Clone assertion passed: time=%s",
                            parsed_start_time,
                        )
                    except (ValueError, AssertionError) as e:
                        logger.warning("[SCHED] Clone assertion: %s", e)

            # Resolve domain from event_type if possible
            domain = None
            try:
                from apps.purpose.models import LifeDomain
                domain_map = {
                    'health': 'health', 'fitness': 'health',
                    'work': 'work', 'professional': 'work',
                    'faith': 'faith', 'spiritual': 'faith',
                    'family': 'family',
                    'personal': None,  # No specific domain
                }
                slug = domain_map.get(event_type)
                if slug:
                    domain = LifeDomain.objects.filter(
                        slug=slug, is_active=True
                    ).first()
            except Exception:
                pass

            # --- Source identity (Phase 9 final) ---
            # Extract source_type/source_id from kwargs if provided
            # (e.g. when called from projection or provider-backed paths).
            # Defaults: manual event with no source.
            source_type = kwargs.get('source_type', CalendarEvent.SOURCE_NONE)
            source_id = str(kwargs.get('source_id', '') or '')

            # Map event_kind based on source
            if source_id:
                event_kind = CalendarEvent.KIND_EXECUTION_BLOCK
            else:
                event_kind = CalendarEvent.KIND_MANUAL

            # --- Idempotency key (Phase 9) ---
            from apps.calendar_engine.utils.idempotency import compute_idempotency_key
            idem_key = compute_idempotency_key(
                self.user.id, title, start_dt, end_dt=end_dt,
                source_type=source_type, source_id=source_id,
            )

            logger.debug(
                "[SCHED] Idempotency key: %s (user=%s, title=%r, start=%s, "
                "source_type=%s, source_id=%s)",
                idem_key[:12], self.user.id, title, start_dt.isoformat(),
                source_type, source_id,
            )

            # --- Phase 10: Route through CalendarMutationService ---
            # All creates go through CMS for centralized conflict detection,
            # idempotency, semantic dedup, and post-scheduling hooks.
            from apps.calendar_engine.services.calendar_mutation_service import (
                CalendarMutationService,
            )

            force_override = kwargs.get('force_override', False)
            cms = CalendarMutationService(self.user)
            result = cms.create(
                title=title,
                start_dt=start_dt,
                end_dt=end_dt,
                idempotency_key=idem_key,
                description=description or "",
                is_all_day=actual_all_day,
                domain=domain,
                event_kind=event_kind,
                source_type=source_type,
                source_id=source_id,
                force=force_override,
            )

            # --- Phase 10: Conflict requires user decision ---
            if result.requires_decision:
                logger.info(
                    "[SCHED] Conflict detected for '%s' — pausing for user decision",
                    title,
                )
                return ActionResult(
                    success=False,
                    message=result.error,
                    action_type='create_event',
                    confirmation_detail={
                        'type': 'calendar_conflict',
                        'case': result.conflict_details.get('case'),
                        'conflicts': result.conflict_details.get('conflicts', []),
                        'proposed_event': result.conflict_details.get('proposed_event', {}),
                        'suggested_alternatives': result.suggested_alternatives,
                        'requires_decision': True,
                    },
                )

            if not result.success:
                return ActionResult(
                    success=False,
                    message=f"Could not create event: {result.error}",
                    error=result.error,
                    action_type='create_event',
                )

            event = result.event
            reused = result.reused

            from apps.calendar_engine.utils.formatting import (
                friendly_date, friendly_time,
            )
            date_str = friendly_date(event_date)
            time_str = (
                f" at {friendly_time(parsed_start_time)}"
                if parsed_start_time else ""
            )

            # --- Store scheduling context for future "same" references ---
            self._store_scheduling_context(self.user, {
                'title': title,
                'start_time': start_time,
                'end_time': end_time,
                'description': description,
                'location': location,
                'event_type': event_type,
                'is_all_day': is_all_day,
                'reminder_minutes': reminder_minutes,
            })

            # Build response with CoS awareness
            if reused:
                response_parts = [
                    f"You already have {title} scheduled for {date_str}{time_str} — no duplicate created."
                ]
            else:
                response_parts = [f"✓ Scheduled: {title} on {date_str}{time_str}"]

            if result.conflict_warning:
                response_parts.append(result.conflict_warning)
            if result.pressure_note:
                response_parts.append(result.pressure_note)
            if result.gcal_synced:
                response_parts.append("Synced to Google Calendar.")

            return ActionResult(
                success=True,
                message=" — ".join(response_parts),
                created_object={
                    'model': 'CalendarEvent',
                    'id': event.id,
                    'title': event.title,
                    'start_dt': event.start_dt.isoformat(),
                    'event_kind': event.event_kind,
                    'reused': reused,
                },
                action_type='create_event',
                confirmation_detail=self._build_confirmation(
                    what=f"{title} on {date_str}{time_str}",
                    where="Time Command Center",
                )
            )

        except Exception as e:
            logger.error(f"Error creating event: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't create that event.",
                error=str(e)
            )

    def _run_cos_post_scheduling(self, calendar_event):
        """
        CoS post-scheduling chain — runs after CalendarEvent creation.

        Accepts a CalendarEvent (calendar_engine) with start_dt/end_dt fields.

        1. Conflict detection: checks if the new event overlaps Tier 1/2 blocks
        2. Drift/pressure recompute: updates daily drift and weekly pressure
        3. Google Calendar sync: pushes to Google if user has it connected

        Returns dict with:
            conflict_warning: str or None
            pressure_note: str or None
            gcal_synced: bool
        """
        result = {
            'conflict_warning': None,
            'pressure_note': None,
            'gcal_synced': False,
        }

        user = self.user

        # Extract date and time — supports both CalendarEvent (start_dt)
        # and legacy LifeEvent (start_date/start_time) objects
        from django.utils import timezone as tz
        if hasattr(calendar_event, 'start_dt') and calendar_event.start_dt:
            event_date = tz.localtime(calendar_event.start_dt).date()
            event_start_time = tz.localtime(calendar_event.start_dt).time()
            event_end_time = (
                tz.localtime(calendar_event.end_dt).time()
                if calendar_event.end_dt else None
            )
        elif hasattr(calendar_event, 'start_date'):
            event_date = calendar_event.start_date
            event_start_time = getattr(calendar_event, 'start_time', None)
            event_end_time = getattr(calendar_event, 'end_time', None)
        else:
            return result  # Unknown event type, bail safely

        # --- 1. Conflict Detection ---
        try:
            if not calendar_event.is_all_day:
                from apps.core.blueprint.architecture_engine import get_todays_plan
                from apps.core.blueprint.models import ArchitecturePlan

                plan = None
                today = tz.localdate()

                if event_date == today:
                    plan = get_todays_plan(user)
                else:
                    plan = ArchitecturePlan.get_active_for_date(
                        user, event_date,
                    )

                if plan:
                    blocks = list(plan.blocks.all().order_by('start_time'))
                    overlapping = []
                    for block in blocks:
                        if not block.start_time or not block.end_time:
                            continue
                        # Check time overlap
                        if (event_start_time < block.end_time
                                and event_end_time > block.start_time):
                            overlapping.append(block)

                    if overlapping:
                        tier1_conflicts = [
                            b for b in overlapping if b.tier == 1
                        ]
                        if tier1_conflicts:
                            titles = ', '.join(
                                b.title for b in tier1_conflicts
                            )
                            result['conflict_warning'] = (
                                f"⚠️ Overlaps protected commitment: {titles}"
                            )
                        else:
                            titles = ', '.join(
                                b.title for b in overlapping[:2]
                            )
                            result['conflict_warning'] = (
                                f"Overlaps with: {titles}"
                            )
        except Exception as e:
            logger.debug(f"CoS conflict check skipped: {e}")

        # --- 2. Drift & Pressure Recompute ---
        try:
            from apps.core.blueprint.drift_engine import compute_daily_drift_score
            compute_daily_drift_score(user, date=event_date)
        except Exception as e:
            logger.debug(f"CoS drift recompute skipped: {e}")

        # Phase 10: Evaluate schedule instability after event creation
        try:
            from apps.core.drift.engine import DriftEngine
            DriftEngine.evaluate_schedule_instability(user)
        except Exception as e:
            logger.debug(f"Schedule instability evaluation skipped: {e}")

        try:
            from apps.core.blueprint.weekly_pressure import compute_weekly_pressure
            from apps.core.blueprint.human_language import translate_capacity

            pressure = compute_weekly_pressure(user, start_date=event_date, days=1)
            day_loads = pressure.get('day_loads', [])
            if day_loads:
                _, capacity_pct = day_loads[0]
                if capacity_pct >= 85:
                    label, _ = translate_capacity(capacity_pct)
                    result['pressure_note'] = (
                        f"Day is now at {label} capacity"
                    )
        except Exception as e:
            logger.debug(f"CoS pressure recompute skipped: {e}")

        # --- 3. Google Calendar Sync ---
        try:
            from apps.life.models import GoogleCalendarCredential

            credential = user.google_calendar_credential
            if (credential.is_connected
                    and credential.sync_direction in ('export', 'both')
                    and not credential.has_decryption_error()):

                from apps.life.services.google_calendar import CalendarSyncService
                sync_service = CalendarSyncService(user)
                sync_result = sync_service.sync_to_google(
                    calendar_event,
                    credential.get_credentials_dict(),
                    calendar_id=credential.selected_calendar_id or 'primary',
                )
                if sync_result:
                    result['gcal_synced'] = True
        except Exception as e:
            logger.debug(f"CoS Google Calendar sync skipped: {e}")

        return result

    def handle_add_reminder(self, title: str, event_type: str, event_date: str,
                             person_name: str = "", description: str = "",
                             reminder_days: int = 7, **kwargs) -> ActionResult:
        """
        Add a significant event reminder (birthday, anniversary, etc.).

        Args:
            title: Event title
            event_type: birthday, anniversary, memorial, etc.
            event_date: Date (MM-DD for annual or YYYY-MM-DD)
            person_name: Name of person
            description: Additional notes
            reminder_days: Days before to remind
        """
        from apps.life.models import SignificantEvent
        from datetime import datetime as dt

        try:
            # Parse date - support both MM-DD and YYYY-MM-DD
            if len(event_date) == 5:  # MM-DD format
                month, day = event_date.split('-')
                # Use current or next year
                today = self._get_user_today()
                year = today.year
                parsed_date = dt(year, int(month), int(day)).date()
                if parsed_date < today:
                    parsed_date = dt(year + 1, int(month), int(day)).date()
                original_year = None
            else:
                parsed_date = dt.strptime(event_date, '%Y-%m-%d').date()
                original_year = parsed_date.year

            event = SignificantEvent.objects.create(
                user=self.user,
                title=title,
                event_type=event_type,
                event_date=parsed_date,
                original_year=original_year,
                person_name=person_name or "",
                description=description or "",
                sms_reminder_enabled=True,
                reminder_days=reminder_days
            )

            date_str = parsed_date.strftime("%B %d")

            return ActionResult(
                success=True,
                message=f"✓ Added reminder: {title} on {date_str} (will remind {reminder_days} days before)",
                created_object={
                    'model': 'SignificantEvent',
                    'id': event.id,
                    'title': event.title,
                    'event_type': event.event_type,
                    'event_date': event.event_date.isoformat()
                },
                action_type='add_reminder',
                confirmation_detail=self._build_confirmation(
                    what=title,
                    where="Organize > Reminders",
                )
            )

        except Exception as e:
            logger.error(f"Error adding reminder: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't add that reminder.",
                error=str(e)
            )

    # =========================================================================
    # FITNESS HANDLERS
    # =========================================================================

    def handle_log_workout(self, name: str, duration_minutes: int = None,
                           notes: str = "", exercises: list = None,
                           **kwargs) -> ActionResult:
        """
        Log a workout session.

        Args:
            name: Workout name
            duration_minutes: Duration in minutes
            notes: Notes about the workout
            exercises: List of exercises with sets/reps/weight
        """
        from apps.health.models import WorkoutSession

        try:
            recorded_at = self._get_recorded_at(kwargs)
            now = recorded_at
            today = recorded_at.date() if hasattr(recorded_at, 'date') else self._get_user_today()

            session = WorkoutSession.objects.create(
                user=self.user,
                date=today,
                name=name,
                notes=notes or "",
                duration_minutes=duration_minutes,
                started_at=now,
                completed_at=now
            )

            duration_str = f" ({duration_minutes} min)" if duration_minutes else ""

            # Trend lookup — weekly workout count (safe — never blocks action)
            trend = None
            try:
                weekly = self._get_weekly_count(WorkoutSession, 'date')
                if weekly:
                    trend = f"{weekly} workout{'s' if weekly != 1 else ''} this week"
            except Exception:
                pass

            # Cross-complete: also mark matching task complete
            task_msg = self._cross_complete_task(name)
            # Also try generic "workout" keyword if name was specific
            if not task_msg and name.lower() != 'workout':
                task_msg = self._cross_complete_task('workout')
            msg = f"✓ Logged workout: {name}{duration_str}"
            if task_msg:
                msg += f"\n{task_msg}"

            return ActionResult(
                success=True,
                message=msg,
                created_object={
                    'model': 'WorkoutSession',
                    'id': session.id,
                    'name': session.name,
                    'duration_minutes': session.duration_minutes,
                    'date': session.date.isoformat()
                },
                action_type='log_workout',
                confirmation_detail=self._build_confirmation(
                    what=f"{name}{duration_str}",
                    where="Health > Fitness",
                    trend=trend,
                )
            )

        except Exception as e:
            logger.error(f"Error logging workout: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log that workout.",
                error=str(e)
            )

    def handle_log_exercise_set(self, exercise_name: str, weight: float, reps: int,
                                 set_number: int = None, is_warmup: bool = False,
                                 is_pr: bool = False, notes: str = "",
                                 **kwargs) -> ActionResult:
        """
        Log a specific exercise set.

        PRs are auto-detected by comparing against historical sets for
        the same exercise (weight PR, rep PR, estimated 1RM PR).
        The is_pr parameter is kept for backwards compatibility but
        auto-detection overrides it.

        Args:
            exercise_name: Name of the exercise
            weight: Weight used
            reps: Number of reps
            set_number: Which set (1, 2, 3, etc.)
            is_warmup: Whether this is a warmup set
            is_pr: Ignored — PRs are auto-detected via post_save signal
            notes: Notes about the set
        """
        from apps.health.models import WorkoutSession, Exercise, WorkoutExercise, ExerciseSet

        try:
            recorded_at = self._get_recorded_at(kwargs)
            today = recorded_at.date() if hasattr(recorded_at, 'date') else self._get_user_today()
            now = recorded_at

            # Get or create today's workout session
            session, created = WorkoutSession.objects.get_or_create(
                user=self.user,
                date=today,
                completed_at__isnull=True,
                defaults={
                    'name': 'Workout',
                    'started_at': now
                }
            )

            # Find or create the exercise in the library
            exercise, _ = Exercise.objects.get_or_create(
                name__iexact=exercise_name,
                defaults={
                    'name': exercise_name.title(),
                    'exercise_type': 'strength',
                    'primary_muscle': 'other'
                }
            )

            # Get or create workout exercise entry
            workout_exercise, _ = WorkoutExercise.objects.get_or_create(
                session=session,
                exercise=exercise,
                defaults={'order': 1}
            )

            # Determine set number if not provided
            if not set_number:
                existing_sets = workout_exercise.sets.count()
                set_number = existing_sets + 1

            # Create the set (post_save signal auto-detects PRs)
            exercise_set = ExerciseSet.objects.create(
                workout_exercise=workout_exercise,
                set_number=set_number,
                weight=Decimal(str(weight)),
                reps=reps,
                is_warmup=is_warmup,
                notes=notes or ""
            )

            # Refresh to pick up is_pr set by auto-detection signal
            exercise_set.refresh_from_db()
            detected_pr = exercise_set.is_pr

            pr_str = ""
            if detected_pr:
                pr_str = " (PR! 🎉)"
            warmup_str = " (warmup)" if is_warmup else ""

            return ActionResult(
                success=True,
                message=f"✓ Logged: {exercise_name} - Set {set_number}: {weight} x {reps}{warmup_str}{pr_str}",
                created_object={
                    'model': 'ExerciseSet',
                    'id': exercise_set.id,
                    'exercise': exercise_name,
                    'set_number': set_number,
                    'weight': float(weight),
                    'reps': reps,
                    'is_pr': detected_pr
                },
                action_type='log_exercise_set',
                confirmation_detail=self._build_confirmation(
                    what=f"{exercise_name} {weight} x {reps}",
                    where="Health > Fitness",
                )
            )

        except Exception as e:
            logger.error(f"Error logging exercise set: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log that set.",
                error=str(e)
            )

    def handle_log_cardio(self, activity: str, duration_minutes: int,
                          distance: float = None, distance_unit: str = "miles",
                          intensity: str = "medium", calories_burned: int = None,
                          avg_heart_rate: int = None, notes: str = "",
                          **kwargs) -> ActionResult:
        """
        Log a cardio session.

        Args:
            activity: Type of cardio (running, walking, etc.)
            duration_minutes: Duration in minutes
            distance: Distance covered
            distance_unit: miles or km
            intensity: easy, medium, hard
            calories_burned: Estimated calories
            avg_heart_rate: Average heart rate
            notes: Notes about the session
        """
        from apps.health.models import WorkoutSession, Exercise, WorkoutExercise, CardioDetails

        try:
            recorded_at = self._get_recorded_at(kwargs)
            today = recorded_at.date() if hasattr(recorded_at, 'date') else self._get_user_today()
            now = recorded_at

            # Create workout session for cardio
            session = WorkoutSession.objects.create(
                user=self.user,
                date=today,
                name=activity.title(),
                notes=notes or "",
                duration_minutes=duration_minutes,
                started_at=now,
                completed_at=now
            )

            # Find or create cardio exercise
            exercise, _ = Exercise.objects.get_or_create(
                name__iexact=activity,
                defaults={
                    'name': activity.title(),
                    'exercise_type': 'cardio',
                    'primary_muscle': 'cardio'
                }
            )

            # Create workout exercise
            workout_exercise = WorkoutExercise.objects.create(
                session=session,
                exercise=exercise,
                order=1
            )

            # Create cardio details
            cardio = CardioDetails.objects.create(
                workout_exercise=workout_exercise,
                duration_minutes=duration_minutes,
                distance=Decimal(str(distance)) if distance else None,
                intensity=intensity,
                calories_burned=calories_burned,
                avg_heart_rate=avg_heart_rate
            )

            distance_str = f" - {distance} {distance_unit}" if distance else ""
            cal_str = f" ({calories_burned} cal)" if calories_burned else ""

            # Trend lookup — weekly cardio count (safe — never blocks action)
            trend = None
            try:
                weekly = self._get_weekly_count(WorkoutSession, 'date')
                if weekly:
                    trend = f"{weekly} session{'s' if weekly != 1 else ''} this week"
            except Exception:
                pass

            # Cross-complete: also mark matching task complete
            task_msg = self._cross_complete_task(activity)
            if not task_msg:
                task_msg = self._cross_complete_task('workout')
            msg = f"✓ Logged: {activity.title()} - {duration_minutes} min{distance_str}{cal_str}"
            if task_msg:
                msg += f"\n{task_msg}"

            return ActionResult(
                success=True,
                message=msg,
                created_object={
                    'model': 'CardioDetails',
                    'id': cardio.id,
                    'activity': activity,
                    'duration_minutes': duration_minutes,
                    'distance': float(distance) if distance else None,
                    'calories_burned': calories_burned
                },
                action_type='log_cardio',
                confirmation_detail=self._build_confirmation(
                    what=f"{activity.title()} {duration_minutes} min",
                    where="Health > Fitness",
                    trend=trend,
                )
            )

        except Exception as e:
            logger.error(f"Error logging cardio: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log that cardio session.",
                error=str(e)
            )

    # ── Transformation Protocol Handlers ─────────────────────────

    def handle_log_transformation_protocol(self, **kwargs):
        """Create a new transformation protocol."""
        from apps.health.models import TransformationProtocol

        try:
            name = kwargs.get('name', 'My Transformation')
            protocol_type = kwargs.get('protocol_type', 'custom')
            start_date = kwargs.get('start_date', self._get_user_today())
            target_end_date = kwargs.get('target_end_date')
            goal_weight = kwargs.get('goal_weight')
            goal_body_fat = kwargs.get('goal_body_fat')
            notes = kwargs.get('notes', '')

            protocol = TransformationProtocol.objects.create(
                user=self.user,
                name=name,
                protocol_type=protocol_type,
                start_date=start_date,
                target_end_date=target_end_date,
                goal_weight=goal_weight,
                goal_body_fat=goal_body_fat,
                notes=notes,
                is_active=True,
            )

            return ActionResult(
                success=True,
                message=f"Started transformation protocol: {name}",
                created_object={'id': protocol.id, 'name': name},
                action_type='log_transformation_protocol',
                confirmation_detail=self._build_confirmation(
                    what=name,
                    where="Transformation",
                )
            )

        except Exception as e:
            logger.error(f"Error creating protocol: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't create that protocol.",
                error=str(e)
            )

    def handle_log_shopping_item(self, **kwargs):
        """Add an item to a shopping list (creates list if needed)."""
        from apps.life.models import ShoppingItem, ShoppingList

        try:
            item_name = kwargs.get('name', kwargs.get('item', ''))
            if not item_name:
                return ActionResult(
                    success=False,
                    message="Please specify what to add to the shopping list.",
                    error="No item name provided"
                )

            list_name = kwargs.get('list_name', 'Shopping List')
            quantity = kwargs.get('quantity', '')
            category = kwargs.get('category', 'other')

            # Get or create shopping list
            shopping_list, _ = ShoppingList.objects.get_or_create(
                user=self.user,
                name=list_name,
                is_completed=False,
                defaults={'status': 'active'},
            )

            item = ShoppingItem.objects.create(
                user=self.user,
                shopping_list=shopping_list,
                name=item_name,
                quantity=quantity,
                category=category,
            )

            return ActionResult(
                success=True,
                message=f"Added '{item_name}' to {list_name}",
                created_object={'id': item.id, 'name': item_name, 'list_id': shopping_list.id},
                action_type='log_shopping_item',
                confirmation_detail=self._build_confirmation(
                    what=item_name,
                    where="Shopping List",
                )
            )

        except Exception as e:
            logger.error(f"Error adding shopping item: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't add that to your shopping list.",
                error=str(e)
            )

    def handle_complete_shopping_item(self, **kwargs):
        """Mark a shopping item as purchased."""
        from apps.life.models import ShoppingItem

        try:
            item_name = kwargs.get('name', kwargs.get('item', ''))
            if not item_name:
                return ActionResult(
                    success=False,
                    message="Please specify which item to mark as purchased.",
                    error="No item name provided"
                )

            # Find the most recent unpurchased item matching the name
            item = (
                ShoppingItem.objects.filter(
                    user=self.user,
                    name__icontains=item_name,
                    is_purchased=False,
                    status="active",
                )
                .order_by("-created_at")
                .first()
            )

            if not item:
                return ActionResult(
                    success=False,
                    message=f"Couldn't find '{item_name}' on your shopping list.",
                    error="Item not found"
                )

            from apps.core.time.system_clock import get_current_time
            item.is_purchased = True
            item.purchased_at = get_current_time()
            item.save(update_fields=["is_purchased", "purchased_at"])

            return ActionResult(
                success=True,
                message=f"Marked '{item.name}' as purchased",
                created_object={'id': item.id, 'name': item.name},
                action_type='complete_shopping_item',
                confirmation_detail=self._build_confirmation(
                    what=item.name,
                    where="Shopping List",
                )
            )

        except Exception as e:
            logger.error(f"Error completing shopping item: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't mark that item as purchased.",
                error=str(e)
            )

    # =========================================================================
    # SETTINGS HANDLERS
    # =========================================================================

    def handle_set_cos_name(self, name: str = '', **kwargs) -> ActionResult:
        """
        Change the Chief of Staff display name.

        Args:
            name: The new display name (empty string resets to default)
        """
        try:
            clean_name = name.strip()[:50]
            prefs = self.user.preferences
            old_name = prefs.get_cos_name()
            prefs.cos_display_name = clean_name
            prefs.save(update_fields=['cos_display_name'])
            new_name = prefs.get_cos_name()

            if clean_name:
                msg = f"Done — I'm {new_name} now."
            else:
                msg = "Done — I'm back to Chief of Staff."

            return ActionResult(
                success=True,
                message=msg,
                created_object={
                    'old_name': old_name,
                    'new_name': new_name,
                },
                action_type='set_cos_name'
            )

        except Exception as e:
            logger.error(f"Error setting CoS name: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't update the name right now.",
                error=str(e)
            )

    # =========================================================================
    # CALIBRATION HANDLERS
    # =========================================================================

    def handle_pause_calibration(self, **kwargs) -> ActionResult:
        """
        Pause the getting-to-know-you / calibration flow.
        User can resume next session.
        """
        try:
            from apps.core.blueprint.cos_governance import pause_calibration
            pause_calibration(self.user)
            return ActionResult(
                success=True,
                message=(
                    "No problem. We'll pick this up where we left off "
                    "whenever you're ready."
                ),
                action_type='pause_calibration',
            )
        except Exception as e:
            logger.error(f"Error pausing calibration: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Something went wrong, but I'll stop asking for now.",
                error=str(e),
            )

    def handle_complete_calibration(self, **kwargs) -> ActionResult:
        """
        Complete the getting-to-know-you introduction.
        Only called when the user explicitly says they're ready.
        """
        try:
            from apps.core.blueprint.cos_governance import (
                complete_calibration_by_user,
            )
            result = complete_calibration_by_user(self.user)
            if result:
                return ActionResult(
                    success=True,
                    message=(
                        "Got it — I have a solid picture of what matters to you. "
                        "From here on, I'll be watching your data and speaking up "
                        "when something needs your attention. If I ever get it wrong, "
                        "tell me."
                    ),
                    action_type='complete_calibration',
                )
            else:
                return ActionResult(
                    success=True,
                    message="Introduction is already complete — we're good to go.",
                    action_type='complete_calibration',
                )
        except Exception as e:
            logger.error(f"Error completing calibration: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Something went wrong, but I'll consider the intro done.",
                error=str(e),
            )

    # =========================================================================
    # LEARNING MODE HANDLERS (control-plane — bypasses UAIO suppression)
    # =========================================================================

    def handle_exit_learning_mode(self, **kwargs) -> ActionResult:
        """
        Exit Learning Mode — present summary in chat for confirmation.

        Sets exit_pending state and returns a structured summary of declared
        priorities. The user confirms or declines directly in chat.
        Execution remains blocked until confirmation.
        """
        try:
            from apps.core.blueprint.learning_mode import (
                is_learning_mode_active,
                request_exit_learning_mode,
            )
            if not is_learning_mode_active(self.user):
                return ActionResult(
                    success=True,
                    message="You're not in Learning Mode — execution is already active.",
                    action_type='exit_learning_mode',
                )

            # Build structured summary of what was learned
            summary_parts = []
            try:
                from apps.core.blueprint.models import UserPriorityProfile
                priorities = UserPriorityProfile.get_user_priorities(self.user)
                if priorities:
                    for p in priorities:
                        sub = f" > {p.sub_module_key}" if p.sub_module_key else ""
                        level = p.get_declared_priority_level_display()
                        line = f"- **{p.module_key}{sub}**: {level}"
                        if p.declared_reason:
                            line += f" — {p.declared_reason}"
                        summary_parts.append(line)
            except Exception:
                pass

            # Build learned preferences summary
            try:
                from apps.core.ai_memory.models import LearnedMapping
                recent_prefs = LearnedMapping.objects.filter(
                    user=self.user, is_active=True,
                ).order_by('-updated_at')[:5]
                if recent_prefs:
                    summary_parts.append("")
                    summary_parts.append("**Learned preferences:**")
                    for lp in recent_prefs:
                        summary_parts.append(
                            f"- {lp.phrase} → {lp.meaning_type}"
                        )
            except Exception:
                pass

            summary_text = "\n".join(summary_parts) if summary_parts else ""
            request_exit_learning_mode(self.user, summary_text)

            # Build the chat confirmation message
            if summary_parts:
                msg = (
                    "Here's what I've learned so far:\n\n"
                    + summary_text
                    + "\n\nDoes this accurately reflect your priorities? "
                    "Say **yes** to confirm and resume execution, "
                    "or **no** to stay in Learning Mode."
                )
            else:
                msg = (
                    "I haven't captured any specific priorities yet, but I've "
                    "been listening to our conversation.\n\n"
                    "Ready to exit Learning Mode and start taking actions? "
                    "Say **yes** to confirm, or **no** to keep teaching me."
                )

            return ActionResult(
                success=True,
                message=msg,
                action_type='exit_learning_mode',
            )
        except Exception as e:
            logger.error(f"Error exiting learning mode: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Something went wrong, but I'll keep listening for now.",
                error=str(e),
                action_type='exit_learning_mode',
            )

    def handle_enter_learning_mode(self, **kwargs) -> ActionResult:
        """
        Enter Learning Mode — pause execution and just listen.
        """
        try:
            from apps.core.blueprint.learning_mode import (
                is_learning_mode_active,
                enter_learning_mode,
            )
            if is_learning_mode_active(self.user):
                return ActionResult(
                    success=True,
                    message=(
                        "I'm already in Learning Mode — listening and learning, "
                        "not executing. Keep telling me what matters to you."
                    ),
                    action_type='enter_learning_mode',
                )

            success = enter_learning_mode(self.user)
            if success:
                # Start priority onboarding
                try:
                    from apps.core.blueprint.priority_questions import (
                        start_priority_onboarding,
                    )
                    start_priority_onboarding(self.user)
                except Exception:
                    pass

                return ActionResult(
                    success=True,
                    message=(
                        "Learning Mode is now active. I'm listening and learning "
                        "— I won't execute any actions until you're ready. "
                        "Tell me about your priorities, values, and what matters most."
                    ),
                    action_type='enter_learning_mode',
                )
            return ActionResult(
                success=False,
                message="Something went wrong entering Learning Mode.",
                error='enter_failed',
                action_type='enter_learning_mode',
            )
        except Exception as e:
            logger.error(f"Error entering learning mode: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Something went wrong. I'll keep operating normally for now.",
                error=str(e),
                action_type='enter_learning_mode',
            )

    # ================================================================== #
    # Calendar CRUD handlers
    # ================================================================== #

    def handle_read_calendar_events(
        self,
        timezone: str = 'America/Chicago',
        query_text: str = None,
        date_range_start: str = None,
        date_range_end: str = None,
        include_deleted: bool = False,
        limit: int = 20,
        **kwargs,
    ) -> ActionResult:
        """
        Read calendar events from local DB. Pure query — no mutation.

        Supports:
        - Title keyword search (case-insensitive contains)
        - Date range filtering with weekday/relative date resolution
        - Optional inclusion of canceled (soft-deleted) events
        """
        import datetime as dt
        import pytz

        from apps.calendar_engine.models import CalendarEvent

        try:
            user_tz = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            user_tz = pytz.timezone('America/Chicago')

        try:
            qs = CalendarEvent.objects.filter(user=self.user)

            # Exclude canceled unless requested
            if not include_deleted:
                qs = qs.exclude(status=CalendarEvent.STATUS_CANCELED)

            # Title search
            if query_text:
                qs = qs.filter(title__icontains=query_text)

            # Date range filtering
            if date_range_start:
                start_date = self._resolve_date_string(date_range_start, user_tz)
                if start_date:
                    start_dt = user_tz.localize(
                        dt.datetime.combine(start_date, dt.time.min)
                    )
                    qs = qs.filter(start_dt__gte=start_dt)

            if date_range_end:
                end_date = self._resolve_date_string(date_range_end, user_tz)
                if end_date:
                    end_dt = user_tz.localize(
                        dt.datetime.combine(end_date, dt.time.max)
                    )
                    qs = qs.filter(start_dt__lte=end_dt)
            elif date_range_start:
                # If only start provided, default end to same day
                if start_date:
                    end_dt = user_tz.localize(
                        dt.datetime.combine(start_date, dt.time.max)
                    )
                    qs = qs.filter(start_dt__lte=end_dt)

            # Limit results
            limit = min(max(limit, 1), 50)
            events = list(qs.order_by('start_dt')[:limit])

            # Serialize
            event_list = []
            for ev in events:
                local_start = ev.start_dt.astimezone(user_tz)
                local_end = ev.end_dt.astimezone(user_tz)
                event_list.append({
                    'id': ev.pk,
                    'title': ev.title,
                    'description': ev.description,
                    'start_dt': local_start.isoformat(),
                    'end_dt': local_end.isoformat(),
                    'is_all_day': ev.is_all_day,
                    'status': ev.status,
                    'event_kind': ev.event_kind,
                    'is_protected': ev.is_protected,
                })

            count = len(event_list)
            if count == 0:
                msg = "No events found matching your criteria."
            elif count == 1:
                ev = event_list[0]
                # Include full time details so the LLM can answer time questions
                local_start = ev['start_dt']
                local_end = ev['end_dt']
                if ev.get('is_all_day'):
                    msg = f"Found 1 event: {ev['title']} on {local_start[:10]} (all day)"
                else:
                    # Parse ISO to friendly time: "10:00 AM"
                    try:
                        from datetime import datetime as _dt
                        _s = _dt.fromisoformat(local_start)
                        _e = _dt.fromisoformat(local_end)
                        time_str = f"{_s.strftime('%I:%M %p').lstrip('0')} – {_e.strftime('%I:%M %p').lstrip('0')}"
                    except Exception:
                        time_str = local_start
                    msg = (
                        f"Found 1 event: {ev['title']} on {local_start[:10]} "
                        f"from {time_str}, status: {ev.get('status', 'scheduled')}, "
                        f"kind: {ev.get('event_kind', 'event')}"
                    )
            else:
                # Include details for all events so LLM has full picture
                lines = [f"Found {count} events:"]
                for ev in event_list:
                    if ev.get('is_all_day'):
                        lines.append(f"- {ev['title']} on {ev['start_dt'][:10]} (all day)")
                    else:
                        try:
                            from datetime import datetime as _dt
                            _s = _dt.fromisoformat(ev['start_dt'])
                            _e = _dt.fromisoformat(ev['end_dt'])
                            time_str = f"{_s.strftime('%I:%M %p').lstrip('0')}-{_e.strftime('%I:%M %p').lstrip('0')}"
                        except Exception:
                            time_str = ev['start_dt']
                        lines.append(f"- {ev['title']}: {ev['start_dt'][:10]} {time_str} [{ev.get('event_kind', 'event')}]")
                msg = "\n".join(lines)

            return ActionResult(
                success=True,
                message=msg,
                created_object={'events': event_list, 'count': count},
                action_type='read_calendar_events',
            )

        except Exception as e:
            logger.error(
                "handle_read_calendar_events failed for user=%s: %s",
                self.user.id, e, exc_info=True,
            )
            return ActionResult(
                success=False,
                message="Sorry, I couldn't read your calendar right now.",
                error=str(e),
                action_type='read_calendar_events',
            )

    def handle_mutate_calendar_event(
        self,
        action: str,
        idempotency_key: str,
        timezone: str = 'America/Chicago',
        event_id: int = None,
        event_query: str = None,
        event_date: str = None,
        title: str = None,
        start_date: str = None,
        start_time: str = None,
        end_time: str = None,
        description: str = None,
        event_type: str = None,
        force_override: bool = False,
        **kwargs,
    ) -> ActionResult:
        """
        Unified calendar mutation: create, update, or delete.

        All mutations go through CalendarMutationService — the same
        service used by the view-layer endpoints.

        For update/delete, the event can be identified by either:
        - event_id: Direct ID (from a prior read_calendar_events call)
        - event_query + event_date: Title search + date hint — resolved
          internally to an event_id. This enables single-turn mutation
          without a separate read call.
        """
        from apps.calendar_engine.services.calendar_mutation_service import (
            CalendarMutationService,
        )

        service = CalendarMutationService(self.user)

        # --- Resolve event_query → event_id if needed ---
        if not event_id and event_query and action in ('update', 'delete'):
            resolved = self._resolve_event_query(
                event_query, event_date, timezone,
            )
            if resolved is None:
                return ActionResult(
                    success=False,
                    message=(
                        f"Could not find an event matching '{event_query}'"
                        + (f" on {event_date}" if event_date else "")
                        + ". Please check the event name and date."
                    ),
                    error='event_not_found',
                    action_type='mutate_calendar_event',
                )
            event_id = resolved

        if action == 'create':
            return self._mutate_create(
                service, idempotency_key, timezone,
                title=title, start_date=start_date,
                start_time=start_time, end_time=end_time,
                description=description, event_type=event_type,
                force_override=force_override,
                **kwargs,
            )
        elif action == 'update':
            if not event_id:
                return ActionResult(
                    success=False,
                    message=(
                        "event_id is required for update. Provide event_id directly "
                        "or use event_query + event_date to find the event."
                    ),
                    error='missing_event_id',
                    action_type='mutate_calendar_event',
                )
            return self._mutate_update(
                service, event_id, idempotency_key, timezone,
                title=title, start_date=start_date,
                start_time=start_time, end_time=end_time,
                description=description, event_type=event_type,
                force_override=force_override,
                **kwargs,
            )
        elif action == 'delete':
            if not event_id:
                return ActionResult(
                    success=False,
                    message=(
                        "event_id is required for delete. Provide event_id directly "
                        "or use event_query + event_date to find the event."
                    ),
                    error='missing_event_id',
                    action_type='mutate_calendar_event',
                )
            return self._mutate_delete(service, event_id)
        else:
            return ActionResult(
                success=False,
                message=f"Unknown action: {action}. Use 'create', 'update', or 'delete'.",
                error='invalid_action',
                action_type='mutate_calendar_event',
            )

    def _resolve_event_query(
        self, query_text: str, event_date: str = None,
        timezone_str: str = 'America/Chicago',
    ):
        """
        Resolve an event title query + optional date to a single event_id.

        Returns the event's pk, or None if no match found.
        If multiple matches, returns the one closest to event_date (or the
        next upcoming match if no date hint).
        """
        import datetime as _dt
        import pytz

        from apps.calendar_engine.models import CalendarEvent

        try:
            user_tz = pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            user_tz = pytz.timezone('America/Chicago')

        qs = CalendarEvent.objects.filter(
            user=self.user,
            title__icontains=query_text.strip(),
            deleted_at__isnull=True,
        ).exclude(status=CalendarEvent.STATUS_CANCELED)

        # Apply date filter if provided
        if event_date:
            resolved_date = self._resolve_date_string(event_date, user_tz)
            if resolved_date:
                day_start = user_tz.localize(
                    _dt.datetime.combine(resolved_date, _dt.time.min)
                )
                day_end = user_tz.localize(
                    _dt.datetime.combine(resolved_date, _dt.time.max)
                )
                qs = qs.filter(start_dt__gte=day_start, start_dt__lte=day_end)

        # Get the best match: nearest upcoming, or most recent if none upcoming
        from django.utils import timezone as dj_tz
        now = dj_tz.now()

        # Prefer upcoming events
        upcoming = qs.filter(start_dt__gte=now).order_by('start_dt').first()
        if upcoming:
            return upcoming.pk

        # Fall back to most recent past event
        past = qs.order_by('-start_dt').first()
        if past:
            return past.pk

        return None

    def _mutate_create(
        self, service, idempotency_key, timezone, **kwargs,
    ) -> ActionResult:
        """Delegate create to existing handle_create_event."""
        # Strip None values so handle_create_event uses its defaults
        create_kwargs = {k: v for k, v in kwargs.items() if v is not None}
        # Ensure force_override passes through
        if 'force_override' in kwargs:
            create_kwargs['force_override'] = kwargs['force_override']
        return self.handle_create_event(**create_kwargs)

    def _mutate_update(
        self, service, event_id, idempotency_key, timezone,
        title=None, start_date=None, start_time=None, end_time=None,
        description=None, event_type=None, force_override=False, **kwargs,
    ) -> ActionResult:
        """Update an existing calendar event via CalendarMutationService."""
        import datetime as dt
        import pytz

        try:
            user_tz = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            user_tz = pytz.timezone('America/Chicago')

        update_fields = {}

        if title is not None:
            update_fields['title'] = title
        if description is not None:
            update_fields['description'] = description

        # Resolve event_type → domain for color coding
        if event_type is not None:
            from apps.purpose.models import LifeDomain
            domain_map = {
                'health': 'health', 'fitness': 'health',
                'work': 'work', 'professional': 'work',
                'faith': 'faith', 'spiritual': 'faith',
                'family': 'family',
                'personal': None,
            }
            slug = domain_map.get(event_type)
            if slug:
                domain = LifeDomain.objects.filter(
                    slug=slug, is_active=True,
                ).first()
                if domain:
                    update_fields['domain'] = domain
            else:
                # "personal" or unmapped → clear domain
                update_fields['domain'] = None

        # Resolve date/time if provided
        if start_date or start_time:
            from apps.calendar_engine.models import CalendarEvent
            try:
                existing = CalendarEvent.objects.get(pk=event_id, user=self.user)
            except CalendarEvent.DoesNotExist:
                return ActionResult(
                    success=False,
                    message="Event not found.",
                    error='event_not_found',
                    action_type='mutate_calendar_event',
                )

            current_start = existing.start_dt.astimezone(user_tz)
            current_end = existing.end_dt.astimezone(user_tz)
            duration = current_end - current_start

            if start_date:
                new_date = self._resolve_date_string(
                    start_date, user_tz, start_time_str=start_time,
                )
                if not new_date:
                    return ActionResult(
                        success=False,
                        message=f"Could not resolve date: {start_date}",
                        error='invalid_date',
                        action_type='mutate_calendar_event',
                    )
            else:
                new_date = current_start.date()

            if start_time:
                try:
                    parsed_time = dt.datetime.strptime(start_time, "%H:%M").time()
                except ValueError:
                    return ActionResult(
                        success=False,
                        message=f"Invalid time format: {start_time}. Use HH:MM.",
                        error='invalid_time',
                        action_type='mutate_calendar_event',
                    )
            else:
                parsed_time = current_start.time()

            new_start_dt = user_tz.localize(
                dt.datetime.combine(new_date, parsed_time)
            )
            update_fields['start_dt'] = new_start_dt

            if end_time:
                try:
                    parsed_end = dt.datetime.strptime(end_time, "%H:%M").time()
                    new_end_dt = user_tz.localize(
                        dt.datetime.combine(new_date, parsed_end)
                    )
                except ValueError:
                    new_end_dt = new_start_dt + duration
            else:
                new_end_dt = new_start_dt + duration

            update_fields['end_dt'] = new_end_dt

        if not update_fields:
            return ActionResult(
                success=False,
                message="No fields to update.",
                error='no_fields',
                action_type='mutate_calendar_event',
            )

        result = service.update(event_id, force=force_override, **update_fields)

        # --- Phase 10: Conflict requires user decision ---
        if result.requires_decision:
            return ActionResult(
                success=False,
                message=result.error,
                action_type='mutate_calendar_event',
                confirmation_detail={
                    'type': 'calendar_conflict',
                    'case': result.conflict_details.get('case'),
                    'conflicts': result.conflict_details.get('conflicts', []),
                    'proposed_event': result.conflict_details.get('proposed_event', {}),
                    'suggested_alternatives': result.suggested_alternatives,
                    'requires_decision': True,
                },
            )

        if not result.success:
            return ActionResult(
                success=False,
                message=f"Update failed: {result.error}",
                error=result.error,
                action_type='mutate_calendar_event',
            )

        event = result.event
        msg_parts = [f"✓ Updated: {event.title}"]
        if result.fields_changed:
            for field_name, diff in result.fields_changed.items():
                if field_name == 'start_dt':
                    from apps.calendar_engine.utils.formatting import friendly_datetime
                    msg_parts.append(f"moved to {friendly_datetime(event.start_dt)}")
                elif field_name == 'title':
                    msg_parts.append(f"renamed to \"{diff['new']}\"")
                elif field_name == 'domain':
                    domain_label = diff['new'] if diff['new'] != 'None' else 'Personal'
                    msg_parts.append(f"labeled as {domain_label}")

        if result.conflict_warning:
            msg_parts.append(result.conflict_warning)
        if result.pressure_note:
            msg_parts.append(result.pressure_note)
        if result.gcal_synced:
            msg_parts.append("— Synced to Google Calendar.")

        return ActionResult(
            success=True,
            message=" ".join(msg_parts),
            created_object={
                'model': 'CalendarEvent',
                'id': event.pk,
                'title': event.title,
                'start_dt': event.start_dt.isoformat(),
                'fields_changed': result.fields_changed,
            },
            action_type='mutate_calendar_event',
        )

    def _mutate_delete(self, service, event_id) -> ActionResult:
        """Soft-delete a calendar event via CalendarMutationService."""
        result = service.delete(event_id)

        if not result.success:
            return ActionResult(
                success=False,
                message=f"Delete failed: {result.error}",
                error=result.error,
                action_type='mutate_calendar_event',
            )

        event = result.event
        msg = f"✓ Removed from calendar: {event.title}"
        if result.gcal_synced:
            msg += " — Also removed from Google Calendar."

        return ActionResult(
            success=True,
            message=msg,
            created_object={
                'model': 'CalendarEvent',
                'id': event.pk,
                'title': event.title,
                'status': 'canceled',
            },
            action_type='mutate_calendar_event',
        )

    def _resolve_date_string(self, date_str, user_tz, start_time_str=None):
        """
        Resolve a date string to a date object.
        Delegates to the canonical resolve_weekday_to_date() for weekday and
        relative-date resolution. Also handles Month Day formats as fallback.

        Args:
            date_str: The date string (e.g. 'today', 'wednesday', 'next friday',
                      '2026-03-15', 'March 15').
            user_tz: The user's pytz timezone.
            start_time_str: Optional HH:MM string for same-day disambiguation.
        """
        import datetime as dt

        from apps.calendar_engine.utils.date_resolution import resolve_weekday_to_date
        from apps.core.time.system_clock import get_current_time

        now_utc = get_current_time()
        now_local = now_utc.astimezone(user_tz)
        today = now_local.date()

        # Parse start_time for same-day weekday disambiguation
        parsed_time = None
        if start_time_str:
            try:
                parsed_time = dt.datetime.strptime(start_time_str, "%H:%M").time()
            except (ValueError, TypeError):
                pass

        # Delegate to canonical resolver (handles today, tomorrow, weekday,
        # next <weekday>, ISO dates)
        try:
            return resolve_weekday_to_date(
                self.user, date_str, reference_dt=now_local,
                start_time=parsed_time,
            )
        except ValueError:
            pass

        # Fallback: Month Day format (e.g., "March 15")
        date_str_stripped = date_str.strip()
        for fmt in ('%B %d', '%b %d', '%B %d, %Y', '%b %d, %Y'):
            try:
                parsed = dt.datetime.strptime(date_str_stripped, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=today.year)
                return parsed.date()
            except ValueError:
                continue

        return None
