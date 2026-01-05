# ==============================================================================
# File: action_handlers.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Action handlers for executing recognized intents
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-04
# ==============================================================================
"""
Action Handlers for Intent Execution

Each handler creates the appropriate model instance based on extracted parameters.
Handlers validate data and return ActionResult with success status and created object.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from django.db.models import Q
from django.utils import timezone

from .intent_service import ActionResult

logger = logging.getLogger(__name__)


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
        Log a food entry.

        Args:
            food_name: Name of the food
            quantity: Number of servings
            meal_type: Type of meal (breakfast, lunch, dinner, snack)
            calories: Estimated calories if known
            notes: Optional notes
        """
        from apps.health.models import FoodEntry

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

            # Create a quick-add food entry (no FoodItem lookup for now)
            entry = FoodEntry.objects.create(
                user=self.user,
                food_name=food_name,
                quantity=Decimal(str(quantity)),
                serving_size=Decimal('1'),
                serving_unit='serving',
                total_calories=Decimal(str(calories)) if calories else Decimal('0'),
                logged_date=today,
                logged_time=now.time(),
                meal_type=meal_type,
                entry_source='voice',
                notes=notes or ""
            )

            cal_str = f" ({calories} cal)" if calories else ""

            return ActionResult(
                success=True,
                message=f"✓ Logged {quantity} {food_name}{cal_str} for {meal_type}",
                created_object={
                    'model': 'FoodEntry',
                    'id': entry.id,
                    'food_name': entry.food_name,
                    'quantity': float(entry.quantity),
                    'meal_type': entry.meal_type,
                    'total_calories': float(entry.total_calories),
                    'logged_date': entry.logged_date.isoformat()
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
