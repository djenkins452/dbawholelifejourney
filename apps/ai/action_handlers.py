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

import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import requests
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

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

    def _get_user_today(self):
        """Get current date in user's timezone."""
        from apps.core.utils import get_user_today
        return get_user_today(self.user)

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

        try:
            url = f"{BIBLE_API_BASE}/bibles/{bible_id}/passages/{passage_id}"
            headers = {"X-YVP-App-Key": api_key}

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Extract the verse text from the response
            # YouVersion returns: {"id": "...", "content": "...", "reference": "..."}
            if data.get('content'):
                text = data['content'].strip()
                # Clean up any extra whitespace
                text = ' '.join(text.split())
                return text

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
                recorded_at=self._get_user_now()
            )

            time_str = entry.recorded_at.strftime("%I:%M %p")

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
                action_type='log_heart_rate'
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
                recorded_at=self._get_user_now()
            )

            time_str = entry.recorded_at.strftime("%I:%M %p")
            bp_str = f"{systolic}/{diastolic}"
            pulse_str = f", pulse {pulse}" if pulse else ""

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
                action_type='log_blood_pressure'
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
                recorded_at=self._get_user_now()
            )

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
                action_type='log_weight'
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
                recorded_at=self._get_user_now()
            )

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
                action_type='log_glucose'
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
                recorded_at=self._get_user_now()
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
                action_type='log_blood_oxygen'
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
            # Determine meal type from time if not specified
            if not meal_type:
                hour = self._get_user_now().hour
                if hour < 10:
                    meal_type = 'breakfast'
                elif hour < 14:
                    meal_type = 'lunch'
                elif hour < 18:
                    meal_type = 'snack'
                else:
                    meal_type = 'dinner'

            today = self._get_user_today()
            now = self._get_user_now()

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
                action_type='log_food'
            )

        except Exception as e:
            logger.error(f"Error logging food: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log that food.",
                error=str(e)
            )

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
        from apps.health.models import Medicine, MedicineLog, MedicineSchedule

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
            action_type='take_medicine'
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

            now = self._get_user_now()

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
                action_type='start_fast'
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
                action_type='end_fast'
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

            # Add categories if provided
            if categories:
                for cat_name in categories:
                    category, _ = Category.objects.get_or_create(
                        user=self.user,
                        name=cat_name.strip().lower(),
                        defaults={'color': '#6B7280'}
                    )
                    entry.categories.add(category)

            return ActionResult(
                success=True,
                message=f"✓ Created journal entry: \"{title[:30]}...\"" if len(title) > 30 else f"✓ Created journal entry: \"{title}\"",
                created_object={
                    'model': 'JournalEntry',
                    'id': entry.id,
                    'title': entry.title,
                    'mood': entry.mood,
                    'entry_date': entry.entry_date.isoformat()
                },
                action_type='create_journal_entry'
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
            today = self._get_user_today()

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

            return ActionResult(
                success=True,
                message=f"✓ Logged gratitude: {gratitude}",
                created_object={
                    'model': 'JournalEntry',
                    'id': entry.id,
                    'title': entry.title,
                    'entry_date': entry.entry_date.isoformat()
                },
                action_type='add_gratitude'
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
                action_type='log_prayer'
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
                    action_type='mark_prayer_answered'
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
                action_type='save_verse'
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
                action_type='add_faith_milestone'
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
                action_type='create_goal'
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
                    action_type='update_goal_progress'
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
                action_type='set_intention'
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
                habit_status='active',
                status='active'
            ).filter(
                Q(name__icontains=habit_keyword) |
                Q(description__icontains=habit_keyword)
            )

            count = habits.count()

            if count == 0:
                return ActionResult(
                    success=False,
                    message=f"I couldn't find an active habit matching '{habit_keyword}'.",
                    error='habit_not_found'
                )
            elif count == 1:
                habit = habits.first()
                today = self._get_user_today()

                # Create or update today's entry
                entry, created = HabitEntry.objects.get_or_create(
                    user=self.user,
                    habit=habit,
                    date=today,
                    defaults={'completed': completed, 'notes': notes or ""}
                )

                if not created:
                    entry.completed = completed
                    entry.notes = notes or entry.notes
                    entry.save()

                status = "completed" if completed else "skipped"

                return ActionResult(
                    success=True,
                    message=f"✓ Logged habit: {habit.name} - {status}",
                    created_object={
                        'model': 'HabitEntry',
                        'id': entry.id,
                        'habit_name': habit.name,
                        'completed': entry.completed,
                        'date': entry.date.isoformat()
                    },
                    action_type='log_habit'
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
                           project_name: str = None, **kwargs) -> ActionResult:
        """
        Create a new task.

        Args:
            title: Task title
            notes: Additional notes
            due_date: When task is due
            priority: now, soon, someday
            effort: quick, small, medium, large
            project_name: Name of project to associate
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

            # Find project if specified
            project = None
            if project_name:
                project = Project.objects.filter(
                    user=self.user,
                    title__icontains=project_name,
                    status='active'
                ).first()

            task = Task.objects.create(
                user=self.user,
                title=title,
                notes=notes or "",
                due_date=parsed_due,
                effort=effort,
                project=project
            )

            # Task priority is auto-calculated from due date

            due_str = f" (due {parsed_due.strftime('%b %d')})" if parsed_due else ""
            project_str = f" in {project.title}" if project else ""

            return ActionResult(
                success=True,
                message=f"✓ Created task: {title}{due_str}{project_str}",
                created_object={
                    'model': 'Task',
                    'id': task.id,
                    'title': task.title,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'priority': task.priority,
                    'project_id': project.id if project else None
                },
                action_type='create_task'
            )

        except Exception as e:
            logger.error(f"Error creating task: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't create that task.",
                error=str(e)
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
            tasks = Task.objects.filter(
                user=self.user,
                is_completed=False,
                status='active'
            ).filter(
                Q(title__icontains=task_keyword) |
                Q(notes__icontains=task_keyword)
            )

            count = tasks.count()

            if count == 0:
                return ActionResult(
                    success=False,
                    message=f"I couldn't find an incomplete task matching '{task_keyword}'.",
                    error='task_not_found'
                )
            elif count == 1:
                task = tasks.first()
                task.is_completed = True
                task.completed_at = self._get_user_now()
                if notes:
                    task.notes = (task.notes + "\n" + notes).strip() if task.notes else notes
                task.save()

                return ActionResult(
                    success=True,
                    message=f"✓ Completed: {task.title}",
                    created_object={
                        'model': 'Task',
                        'id': task.id,
                        'title': task.title,
                        'completed_at': task.completed_at.isoformat()
                    },
                    action_type='complete_task'
                )
            else:
                titles = [f"• {t.title}" for t in tasks[:5]]
                return ActionResult(
                    success=False,
                    message=f"I found {count} tasks matching '{task_keyword}':\n" + "\n".join(titles) + "\nWhich one?",
                    error='multiple_matches'
                )

        except Exception as e:
            logger.error(f"Error completing task: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't complete that task.",
                error=str(e)
            )

    def handle_create_event(self, title: str, start_date: str,
                             description: str = "", start_time: str = None,
                             end_time: str = None, is_all_day: bool = False,
                             location: str = "", event_type: str = "personal",
                             reminder_minutes: int = None, **kwargs) -> ActionResult:
        """
        Create a calendar event.

        Args:
            title: Event title
            start_date: Event date (YYYY-MM-DD)
            description: Event description
            start_time: Start time (HH:MM)
            end_time: End time (HH:MM)
            is_all_day: Whether all-day event
            location: Event location
            event_type: Type of event
            reminder_minutes: Minutes before for reminder
        """
        from apps.life.models import LifeEvent
        from datetime import datetime as dt, time

        try:
            # Parse date
            try:
                event_date = dt.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                # Try relative dates
                today = self._get_user_today()
                if start_date.lower() == 'today':
                    event_date = today
                elif start_date.lower() == 'tomorrow':
                    event_date = today + timedelta(days=1)
                else:
                    event_date = today

            # Parse times
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

            event = LifeEvent.objects.create(
                user=self.user,
                title=title,
                description=description or "",
                event_type=event_type,
                start_date=event_date,
                start_time=parsed_start_time,
                end_time=parsed_end_time,
                is_all_day=is_all_day or (parsed_start_time is None),
                location=location or "",
                reminder_minutes=reminder_minutes
            )

            date_str = event_date.strftime("%b %d")
            time_str = f" at {parsed_start_time.strftime('%I:%M %p')}" if parsed_start_time else ""

            return ActionResult(
                success=True,
                message=f"✓ Scheduled: {title} on {date_str}{time_str}",
                created_object={
                    'model': 'LifeEvent',
                    'id': event.id,
                    'title': event.title,
                    'start_date': event.start_date.isoformat(),
                    'event_type': event.event_type
                },
                action_type='create_event'
            )

        except Exception as e:
            logger.error(f"Error creating event: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't create that event.",
                error=str(e)
            )

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
                action_type='add_reminder'
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
            now = self._get_user_now()
            today = self._get_user_today()

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

            return ActionResult(
                success=True,
                message=f"✓ Logged workout: {name}{duration_str}",
                created_object={
                    'model': 'WorkoutSession',
                    'id': session.id,
                    'name': session.name,
                    'duration_minutes': session.duration_minutes,
                    'date': session.date.isoformat()
                },
                action_type='log_workout'
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

        Args:
            exercise_name: Name of the exercise
            weight: Weight used
            reps: Number of reps
            set_number: Which set (1, 2, 3, etc.)
            is_warmup: Whether this is a warmup set
            is_pr: Whether this is a personal record
            notes: Notes about the set
        """
        from apps.health.models import WorkoutSession, Exercise, WorkoutExercise, ExerciseSet

        try:
            today = self._get_user_today()
            now = self._get_user_now()

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

            # Create the set
            exercise_set = ExerciseSet.objects.create(
                workout_exercise=workout_exercise,
                set_number=set_number,
                weight=Decimal(str(weight)),
                reps=reps,
                is_warmup=is_warmup,
                is_pr=is_pr,
                notes=notes or ""
            )

            pr_str = " (PR! 🎉)" if is_pr else ""
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
                    'is_pr': is_pr
                },
                action_type='log_exercise_set'
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
            today = self._get_user_today()
            now = self._get_user_now()

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

            return ActionResult(
                success=True,
                message=f"✓ Logged: {activity.title()} - {duration_minutes} min{distance_str}{cal_str}",
                created_object={
                    'model': 'CardioDetails',
                    'id': cardio.id,
                    'activity': activity,
                    'duration_minutes': duration_minutes,
                    'distance': float(distance) if distance else None,
                    'calories_burned': calories_burned
                },
                action_type='log_cardio'
            )

        except Exception as e:
            logger.error(f"Error logging cardio: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message="Sorry, I couldn't log that cardio session.",
                error=str(e)
            )
