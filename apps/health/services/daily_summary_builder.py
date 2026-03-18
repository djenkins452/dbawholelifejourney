"""
Daily Health Summary Builder — aggregates data from 15+ source tables
into one DailyHealthSummary row per user per day.

Idempotent: safe to rerun. Creates or updates via update_or_create.

Usage:
    from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
    builder = DailyHealthSummaryBuilder()
    summary = builder.build_for_date(user, date.today())
    builder.build_range(user, start, end)  # backfill
"""

import logging
import statistics
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

# Domains used for completeness calculation
ALL_DOMAINS = [
    "sleep", "steps", "workout", "nutrition", "weight",
    "glucose", "medication", "vitals", "hydration", "fasting",
]


class DailyHealthSummaryBuilder:
    """
    Builds DailyHealthSummary rows by querying all source health tables.

    Each _collect_* method returns a dict of field values.
    build_for_date merges them all and does an upsert.
    """

    def build_for_date(self, user, target_date):
        """Build/update one DailyHealthSummary for the given user+date."""
        from apps.health.models import DailyHealthSummary

        data = {}
        signals = []

        # Collect from each domain
        sleep = self._collect_sleep(user, target_date)
        if sleep:
            data.update(sleep)
            signals.append("sleep")

        vitals = self._collect_vitals(user, target_date)
        if vitals:
            data.update(vitals)
            signals.append("vitals")

        activity = self._collect_activity(user, target_date)
        if activity:
            data.update(activity)
            signals.append("steps")

        workouts = self._collect_workouts(user, target_date)
        if workouts:
            data.update(workouts)
            if workouts.get("workout_count", 0) > 0:
                signals.append("workout")

        weight_comp = self._collect_weight_and_composition(user, target_date)
        if weight_comp:
            data.update(weight_comp)
            signals.append("weight")

        glucose = self._collect_glucose(user, target_date)
        if glucose:
            data.update(glucose)
            signals.append("glucose")

        nutrition = self._collect_nutrition(user, target_date)
        if nutrition:
            data.update(nutrition)
            if nutrition.get("nutrition_logged"):
                signals.append("nutrition")

        hydration = self._collect_hydration(user, target_date)
        if hydration:
            data.update(hydration)
            signals.append("hydration")

        medication = self._collect_medication(user, target_date)
        if medication:
            data.update(medication)
            signals.append("medication")

        fasting = self._collect_fasting(user, target_date)
        if fasting:
            data.update(fasting)
            signals.append("fasting")

        extras = self._collect_extras(user, target_date)
        if extras:
            data.update(extras)

        # Protein intelligence (must run after nutrition + weight)
        protein_data = self._compute_protein_intelligence(user, target_date, data)
        if protein_data:
            data.update(protein_data)

        # Body composition intelligence (must run after weight + protein)
        body_comp = self._compute_body_composition_intelligence(user, target_date, data)
        if body_comp:
            data.update(body_comp)

        # Completeness
        completeness = (len(signals) / len(ALL_DOMAINS)) * 100 if ALL_DOMAINS else 0
        data["data_completeness_pct"] = Decimal(str(round(completeness, 2)))
        data["signals_present"] = signals

        # Baseline check
        from apps.health.services.baseline_policy import BaselinePolicy
        data["baseline_ready"] = BaselinePolicy.baseline_ready(user, target_date)

        # Upsert
        summary, created = DailyHealthSummary.objects.update_or_create(
            user=user,
            summary_date=target_date,
            defaults=data,
        )

        action = "created" if created else "updated"
        logger.info(
            "DailyHealthSummary %s for %s on %s (signals: %s, completeness: %.0f%%)",
            action, user.email, target_date, signals, completeness,
        )
        return summary

    def build_range(self, user, start_date, end_date):
        """Build summaries for a date range (inclusive). Returns count."""
        current = start_date
        count = 0
        while current <= end_date:
            try:
                self.build_for_date(user, current)
                count += 1
            except Exception:
                logger.error(
                    "Failed to build summary for %s on %s",
                    user.email, current, exc_info=True,
                )
            current += timedelta(days=1)
        return count

    # ---- Collectors ----

    def _collect_sleep(self, user, target_date):
        """Collect sleep data for the target date."""
        from apps.health.models import SleepEntry

        entry = (
            SleepEntry.objects
            .filter(user=user, sleep_date=target_date)
            .order_by("-created_at")
            .first()
        )
        if not entry:
            return None

        result = {}
        if entry.bedtime and entry.wake_time:
            delta = entry.wake_time - entry.bedtime
            hours = delta.total_seconds() / 3600
            result["sleep_hours"] = Decimal(str(round(hours, 2)))

            # Sleep debt: target 7.5h
            target_minutes = 450  # 7.5 hours
            actual_minutes = delta.total_seconds() / 60
            result["sleep_debt_minutes"] = int(target_minutes - actual_minutes)
        elif entry.total_duration_minutes:
            hours = entry.total_duration_minutes / 60
            result["sleep_hours"] = Decimal(str(round(hours, 2)))
            result["sleep_debt_minutes"] = int(450 - entry.total_duration_minutes)

        result["deep_sleep_minutes"] = entry.stage_deep_minutes
        result["rem_sleep_minutes"] = entry.stage_rem_minutes

        # Sleep quality score: composite 0-100
        quality_score = self._compute_sleep_quality_score(entry, result)
        result["sleep_quality_score"] = quality_score

        # Efficiency
        if entry.sleep_efficiency:
            result["sleep_efficiency_pct"] = entry.sleep_efficiency

        # HRV / extras from SleepEntry
        if entry.hrv_value:
            result["hrv"] = entry.hrv_value
        if entry.caffeine_mg:
            result["caffeine_mg"] = entry.caffeine_mg
        if entry.mindful_minutes:
            result["mindful_minutes"] = entry.mindful_minutes

        return result

    def _compute_sleep_quality_score(self, entry, sleep_data):
        """Compute a 0-100 sleep quality score from available data."""
        points = 0
        max_points = 0

        # Duration (0-40 pts): 7-8h is optimal
        hours = float(sleep_data.get("sleep_hours", 0) or 0)
        if hours > 0:
            max_points += 40
            if 7 <= hours <= 9:
                points += 40
            elif 6 <= hours < 7 or 9 < hours <= 10:
                points += 30
            elif 5 <= hours < 6:
                points += 15
            else:
                points += 5

        # Deep sleep (0-25 pts): target 60-120 min
        deep = entry.stage_deep_minutes
        if deep is not None:
            max_points += 25
            if 60 <= deep <= 120:
                points += 25
            elif 45 <= deep < 60 or 120 < deep <= 150:
                points += 18
            elif 30 <= deep < 45:
                points += 10
            else:
                points += 3

        # REM sleep (0-20 pts): target 60-120 min
        rem = entry.stage_rem_minutes
        if rem is not None:
            max_points += 20
            if 60 <= rem <= 120:
                points += 20
            elif 45 <= rem < 60 or 120 < rem <= 150:
                points += 14
            elif 30 <= rem < 45:
                points += 7
            else:
                points += 2

        # Quality rating (0-15 pts)
        rating = entry.quality_rating
        if rating:
            max_points += 15
            rating_map = {"excellent": 15, "good": 12, "fair": 8, "poor": 4, "terrible": 1}
            points += rating_map.get(rating, 0)

        if max_points == 0:
            return None
        return min(100, int(round(points / max_points * 100)))

    def _collect_vitals(self, user, target_date):
        """Collect heart rate, blood pressure, SpO2 for the day."""
        from apps.health.models import (
            BloodOxygenEntry, BloodPressureEntry, HeartRateEntry,
        )

        result = {}

        # Resting heart rate (prefer resting context)
        resting_hr = (
            HeartRateEntry.objects
            .filter(
                user=user,
                recorded_at__date=target_date,
                context="resting",
            )
            .aggregate(avg=Avg("bpm"))
        )
        if resting_hr["avg"]:
            result["resting_hr"] = int(round(resting_hr["avg"]))
        else:
            # Fallback: morning reading
            morning_hr = (
                HeartRateEntry.objects
                .filter(
                    user=user,
                    recorded_at__date=target_date,
                    context="morning",
                )
                .aggregate(avg=Avg("bpm"))
            )
            if morning_hr["avg"]:
                result["resting_hr"] = int(round(morning_hr["avg"]))

        # Blood pressure (latest of day)
        bp = (
            BloodPressureEntry.objects
            .filter(user=user, recorded_at__date=target_date)
            .order_by("-recorded_at")
            .first()
        )
        if bp:
            result["blood_pressure_systolic"] = bp.systolic
            result["blood_pressure_diastolic"] = bp.diastolic

        # SpO2 (average of day)
        spo2 = (
            BloodOxygenEntry.objects
            .filter(user=user, recorded_at__date=target_date)
            .aggregate(avg=Avg("spo2"))
        )
        if spo2["avg"]:
            result["spo2_pct"] = Decimal(str(round(spo2["avg"], 2)))

        return result if result else None

    def _collect_activity(self, user, target_date):
        """Collect steps and activity data."""
        from apps.health.models import StepsEntry

        entry = (
            StepsEntry.objects
            .filter(user=user, logged_date=target_date)
            .order_by("-count")
            .first()
        )
        if not entry:
            return None

        return {
            "steps": entry.count,
            "active_minutes": entry.exercise_minutes,
            "calories_burned": entry.calories_burned,
            "stand_hours": entry.stand_hours,
            "flights_climbed": entry.flights_climbed,
        }

    def _collect_workouts(self, user, target_date):
        """Collect workout session data and compute training load."""
        from apps.health.models import ExerciseSet, WorkoutSession

        sessions = WorkoutSession.objects.filter(
            user=user, date=target_date, completed_at__isnull=False,
        )
        count = sessions.count()
        if count == 0:
            return {"workout_count": 0}

        total_minutes = 0
        total_load = Decimal("0")

        for session in sessions:
            if session.duration_minutes:
                total_minutes += session.duration_minutes

            # Training load = sum(weight * reps) for resistance
            sets = ExerciseSet.objects.filter(
                workout_exercise__session=session,
            ).exclude(is_warmup=True)

            for s in sets:
                if s.weight and s.reps:
                    total_load += Decimal(str(float(s.weight) * s.reps))

            # Add cardio load estimate (minutes * intensity factor)
            if session.calories_burned:
                total_load += Decimal(str(session.calories_burned))
            elif session.duration_minutes:
                # Estimate: 1 min cardio ~ 8 cal (moderate)
                total_load += Decimal(str(session.duration_minutes * 8))

        return {
            "workout_count": count,
            "workout_minutes": total_minutes or None,
            "training_load": total_load if total_load > 0 else None,
        }

    def _collect_weight_and_composition(self, user, target_date):
        """Collect weight and body composition data.

        Merges data from multiple WeightEntry records on the same day.
        HealthKit may sync weight and body_fat_percentage as separate
        records — body_fat creates a placeholder entry with value=0.
        We skip placeholders for weight but still collect body_fat from them.
        """
        from apps.health.models import BodyCompositionEntry, WeightEntry

        result = {}

        # All weight entries for the day
        day_entries = (
            WeightEntry.objects
            .filter(user=user, recorded_at__date=target_date)
            .order_by("-recorded_at")
        )

        # Weight: pick latest entry with a real weight (skip value=0 placeholders)
        weight = day_entries.filter(value__gt=0).first()
        if weight:
            if weight.unit == "kg":
                result["weight"] = Decimal(str(round(float(weight.value) * 2.20462, 2)))
            else:
                result["weight"] = weight.value
            if weight.body_fat_percentage:
                result["body_fat_pct"] = weight.body_fat_percentage
            if weight.lean_body_mass:
                result["lean_mass"] = weight.lean_body_mass

        # Merge body_fat_percentage from ANY entry on the same day if not yet set
        # (handles HealthKit body_fat arriving on a separate placeholder entry)
        if not result.get("body_fat_pct"):
            bf_entry = day_entries.filter(body_fat_percentage__isnull=False).first()
            if bf_entry:
                result["body_fat_pct"] = bf_entry.body_fat_percentage

        # Merge lean_body_mass similarly
        if not result.get("lean_mass"):
            lbm_entry = day_entries.filter(lean_body_mass__isnull=False).first()
            if lbm_entry:
                result["lean_mass"] = lbm_entry.lean_body_mass

        # Body composition — BodyCompositionEntry is a flexible key-value model
        # with metric_name, value, unit, measurement_date
        comp_entries = (
            BodyCompositionEntry.objects
            .filter(user=user, measurement_date=target_date)
        )
        for entry in comp_entries:
            name = entry.metric_name.lower()
            if name in ("body_fat_pct", "body_fat_percentage") and not result.get("body_fat_pct"):
                result["body_fat_pct"] = entry.value
            elif name in ("lean_mass", "lean_body_mass") and not result.get("lean_mass"):
                result["lean_mass"] = entry.value
            elif name in ("skeletal_muscle_mass", "muscle_mass"):
                result["skeletal_muscle_mass"] = entry.value

        return result if result else None

    def _collect_glucose(self, user, target_date):
        """Collect glucose metrics for the day."""
        from apps.health.models import GlucoseEntry

        readings = GlucoseEntry.objects.filter(
            user=user, recorded_at__date=target_date,
        )
        count = readings.count()
        if count == 0:
            return None

        # Convert all to mg/dL for consistency
        values = []
        for r in readings:
            val = float(r.value)
            if r.unit == "mmol/L":
                val = val * 18.0  # Convert to mg/dL
            values.append(val)

        avg_val = statistics.mean(values)
        result = {
            "glucose_avg": Decimal(str(round(avg_val, 2))),
            "glucose_min": Decimal(str(round(min(values), 2))),
            "glucose_max": Decimal(str(round(max(values), 2))),
        }

        # Coefficient of variation
        if len(values) >= 3:
            std = statistics.stdev(values)
            cv = (std / avg_val) * 100 if avg_val > 0 else 0
            result["glucose_variability"] = Decimal(str(round(cv, 2)))

        # Time in range (70-180 mg/dL)
        in_range = sum(1 for v in values if 70 <= v <= 180)
        result["time_in_range_pct"] = Decimal(str(round((in_range / count) * 100, 2)))

        return result

    def _collect_nutrition(self, user, target_date):
        """Collect nutrition data from DailyNutritionSummary or FoodEntry."""
        from apps.health.models import DailyNutritionSummary, FoodEntry

        result = {}

        # Prefer DailyNutritionSummary if it exists
        summary = (
            DailyNutritionSummary.objects
            .filter(user=user, summary_date=target_date)
            .first()
        )
        if summary:
            result["calories_consumed"] = int(summary.total_calories) if summary.total_calories else None
            result["protein_g"] = summary.total_protein_g
            result["carbs_g"] = summary.total_carbohydrates_g
            result["fat_g"] = summary.total_fat_g
            result["fiber_g"] = summary.total_fiber_g
            result["meals_logged"] = (
                (summary.breakfast_count or 0) + (summary.lunch_count or 0) +
                (summary.dinner_count or 0) + (summary.snack_count or 0)
            )
            result["nutrition_logged"] = result["meals_logged"] > 0
            return result

        # Fallback: aggregate from FoodEntry directly
        entries = FoodEntry.objects.filter(user=user, logged_date=target_date)
        entry_count = entries.count()
        if entry_count == 0:
            return {"nutrition_logged": False, "meals_logged": 0}

        agg = entries.aggregate(
            total_cal=Sum("total_calories"),
            total_protein=Sum("total_protein_g"),
            total_carbs=Sum("total_carbohydrates_g"),
            total_fat=Sum("total_fat_g"),
            total_fiber=Sum("total_fiber_g"),
        )
        result["calories_consumed"] = int(agg["total_cal"]) if agg["total_cal"] else None
        result["protein_g"] = agg["total_protein"]
        result["carbs_g"] = agg["total_carbs"]
        result["fat_g"] = agg["total_fat"]
        result["fiber_g"] = agg["total_fiber"]
        result["meals_logged"] = entry_count
        result["nutrition_logged"] = True
        return result

    def _collect_hydration(self, user, target_date):
        """Collect water intake for the day."""
        from apps.health.models import WaterEntry

        total = WaterEntry.get_daily_total(user, target_date)
        if total and total > 0:
            return {"water_oz": Decimal(str(round(total, 2)))}
        return None

    def _collect_medication(self, user, target_date):
        """Collect medication adherence for the day."""
        from apps.health.medicine_utils import calculate_medicine_adherence

        try:
            result = calculate_medicine_adherence(user, target_date, target_date)
            if result and result.get("expected_doses", 0) > 0:
                return {
                    "medication_adherence_pct": Decimal(
                        str(round(result["adherence_rate"], 2))
                    ) if result.get("adherence_rate") is not None else None,
                    "doses_taken": result.get("taken_doses", 0),
                    "doses_expected": result.get("expected_doses", 0),
                }
        except Exception:
            logger.warning(
                "Failed to collect medication adherence for %s on %s",
                user.email, target_date, exc_info=True,
            )
        return None

    def _collect_fasting(self, user, target_date):
        """Collect fasting hours for the day."""
        from apps.health.models import FastingWindow

        # Fasting windows that overlap with this day
        windows = FastingWindow.objects.filter(
            user=user,
            started_at__date__lte=target_date,
        ).filter(
            Q(ended_at__isnull=True) | Q(ended_at__date__gte=target_date)
        )

        total_hours = Decimal("0")
        for w in windows:
            # Calculate overlap with target_date
            day_start = timezone.make_aware(
                timezone.datetime.combine(target_date, timezone.datetime.min.time())
            )
            day_end = day_start + timedelta(days=1)

            start = max(w.started_at, day_start)
            end = min(w.ended_at or timezone.now(), day_end)

            if end > start:
                hours = Decimal(str(round((end - start).total_seconds() / 3600, 2)))
                total_hours += hours

        if total_hours > 0:
            return {"fasting_hours": total_hours}
        return None

    def _collect_extras(self, user, target_date):
        """Collect extra metrics (caffeine, mindful minutes) not from sleep."""
        # These might come from SleepEntry (already collected there)
        # or from standalone sources. Only set if not already present.
        return {}

    def _compute_protein_intelligence(self, user, target_date, collected_data):
        """
        Compute protein target, ratio, score, and per-lb from collected data.

        Runs AFTER _collect_nutrition and _collect_weight_and_composition so that
        protein_g and weight are already populated in collected_data.

        Uses LBM-aware targets when body fat data is available.
        """
        from apps.health.services.protein_service import ProteinService

        protein_g = collected_data.get("protein_g")
        if protein_g is None:
            return None

        result = {}

        # Copy consumed for clarity
        result["protein_consumed_g"] = protein_g

        # Calculate target (returns dict with target_g, method, lbm, etc.)
        # Pass weight and body_fat from collected_data since the summary
        # hasn't been saved to DB yet at this point.
        weight = collected_data.get("weight")
        body_fat = collected_data.get("body_fat_pct")
        target_info = ProteinService.calculate_target(
            user, target_date,
            weight_lbs=weight,
            body_fat_pct=body_fat,
        )
        target_g = None
        if target_info:
            target_g = target_info["target_g"]
            result["protein_target_g"] = target_g
            result["protein_ratio"] = ProteinService.calculate_ratio(protein_g, target_g)
            result["protein_method"] = target_info["method"]

        # Protein per lb body weight
        weight = collected_data.get("weight")
        if weight:
            result["protein_per_lb"] = ProteinService.calculate_protein_per_lb(
                protein_g, weight
            )

        # Protein score (lightweight inline version to avoid circular dep)
        # Uses workout-day awareness for scoring penalty
        if target_g and target_g > 0:
            ratio = float(protein_g) / float(target_g)
            is_workout = target_info.get("workout_day", False) if target_info else False

            if ratio >= 1.0:
                score = 95
            elif ratio >= 0.85:
                score = 90
            elif ratio >= 0.70:
                score = 75
            elif ratio >= 0.50:
                score = 58
            else:
                score = 35

            # Workout-day penalty: ratio < 0.85 on workout day → -10 pts
            if is_workout and ratio < 0.85:
                score = max(0, score - 10)

            result["protein_score"] = score

        return result

    def _compute_body_composition_intelligence(self, user, target_date, collected_data):
        """
        Compute body composition intelligence from collected data.

        Runs AFTER _compute_protein_intelligence so that weight and body_fat_pct
        are available in collected_data.

        Returns dict with DailyHealthSummary body comp fields, or None.
        """
        try:
            from apps.health.services.body_composition_intelligence import (
                BodyCompositionIntelligence,
            )
            result = BodyCompositionIntelligence.compute_daily_intelligence(
                user, target_date
            )
            return result if result else None
        except Exception:
            logger.error(
                "Failed to compute body composition intelligence for %s on %s",
                user.email, target_date, exc_info=True,
            )
            return None
