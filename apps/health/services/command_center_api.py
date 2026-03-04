"""
Health Command Center API — returns everything the dashboard needs in one call.

Single entry point for the Health Command Center, reading from
DailyHealthSummary + computed services only (no heavy joins).

Usage:
    from apps.health.services.command_center_api import HealthCommandCenterService
    data = HealthCommandCenterService.get_dashboard_data(user)
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg

logger = logging.getLogger(__name__)


class HealthCommandCenterService:
    """Single-call service for the Health Command Center dashboard."""

    @staticmethod
    def get_dashboard_data(user, as_of_date=None):
        """
        Get complete dashboard data.

        Returns:
            dict with sections:
                score_card: health_score, recovery_score, baseline status
                domain_panels: per-domain current state + mini trends
                trend_lines: 14/28/56 day data for charts
                key_drivers: from health_score_drivers
                recommendation: top action item
        """
        from apps.health.models import DailyHealthSummary
        from apps.health.services.baseline_policy import BaselinePolicy

        target = as_of_date or date.today()

        # Load data for chart rendering (56 days)
        lookback_56 = target - timedelta(days=55)
        summaries = list(
            DailyHealthSummary.objects
            .filter(user=user, summary_date__gte=lookback_56, summary_date__lte=target)
            .order_by("summary_date")
        )

        # Today's summary
        today = next(
            (s for s in reversed(summaries) if s.summary_date == target), None
        )

        # Build sections
        score_card = HealthCommandCenterService._build_score_card(user, today, target)
        domain_panels = HealthCommandCenterService._build_domain_panels(summaries, today, user)
        trend_lines = HealthCommandCenterService._build_trend_lines(summaries, target)

        # Key drivers from health score
        key_drivers = {}
        if today and today.health_score_drivers:
            key_drivers = today.health_score_drivers

        # Top recommendation from trend analyzer
        recommendation = ""
        try:
            from apps.health.services.trend_analyzer import HealthTrendAnalyzer
            analysis = HealthTrendAnalyzer.analyze(user, target)
            recommendation = analysis.get("top_recommendation", "")
        except Exception:
            logger.error("Failed to get recommendation", exc_info=True)

        return {
            "as_of_date": str(target),
            "score_card": score_card,
            "domain_panels": domain_panels,
            "trend_lines": trend_lines,
            "key_drivers": key_drivers,
            "recommendation": recommendation,
        }

    @staticmethod
    def _build_score_card(user, today, target):
        """Build the top-level score card."""
        from apps.health.services.baseline_policy import BaselinePolicy

        card = {
            "health_score": None,
            "recovery_score": None,
            "recovery_status": None,
            "baseline_ready": BaselinePolicy.baseline_ready(user, target),
            "baseline_message": BaselinePolicy.baseline_message(user, target),
            "data_completeness_pct": None,
        }

        if today:
            card["health_score"] = today.health_score
            card["recovery_score"] = today.recovery_score
            card["data_completeness_pct"] = (
                float(today.data_completeness_pct)
                if today.data_completeness_pct else None
            )

            if today.recovery_drivers:
                card["recovery_status"] = today.recovery_drivers.get("status")
                card["recovery_recommendation"] = today.recovery_drivers.get("recommendation")

            if today.health_score_drivers:
                card["health_delta"] = today.health_score_drivers.get("delta_vs_last_week")
                card["immediate_focus"] = today.health_score_drivers.get("immediate_focus")

        return card

    @staticmethod
    def _build_domain_panels(summaries, today, user):
        """Build per-domain mini-panels for the dashboard."""

        def _dec(val):
            return float(val) if val is not None else None

        recent_7 = summaries[-7:] if len(summaries) >= 7 else summaries
        recent_14 = summaries[-14:] if len(summaries) >= 14 else summaries

        panels = {}

        # --- Weight & Body Comp ---
        weight_data = [s for s in recent_14 if s.weight]
        panels["weight"] = {
            "current": _dec(today.weight) if today else None,
            "body_fat_pct": _dec(today.body_fat_pct) if today else None,
            "lean_mass": _dec(today.lean_mass) if today else None,
            "trend_14d": [
                {"date": str(s.summary_date), "value": _dec(s.weight)}
                for s in weight_data
            ],
        }
        if len(weight_data) >= 2:
            change = float(weight_data[-1].weight) - float(weight_data[0].weight)
            panels["weight"]["change_14d"] = round(change, 2)
            # Weekly rate
            days = (weight_data[-1].summary_date - weight_data[0].summary_date).days
            if days > 0:
                panels["weight"]["weekly_rate"] = round(change / days * 7, 2)

        # Goal
        from apps.health.models import HealthProfile
        try:
            profile = HealthProfile.objects.get(user=user)
            if profile.weight_goal:
                panels["weight"]["goal"] = float(profile.weight_goal)
                panels["weight"]["goal_unit"] = profile.weight_goal_unit
        except HealthProfile.DoesNotExist:
            pass

        # --- Sleep ---
        sleep_data = [s for s in recent_14 if s.sleep_hours]
        panels["sleep"] = {
            "last_night": {
                "hours": _dec(today.sleep_hours) if today else None,
                "quality_score": today.sleep_quality_score if today else None,
                "deep_minutes": today.deep_sleep_minutes if today else None,
                "rem_minutes": today.rem_sleep_minutes if today else None,
                "debt_minutes": today.sleep_debt_minutes if today else None,
            },
            "avg_7d": None,
            "trend_14d": [
                {"date": str(s.summary_date), "value": _dec(s.sleep_hours)}
                for s in sleep_data
            ],
        }
        sleep_7 = [float(s.sleep_hours) for s in recent_7 if s.sleep_hours]
        if sleep_7:
            panels["sleep"]["avg_7d"] = round(sum(sleep_7) / len(sleep_7), 2)

        # --- Workouts ---
        panels["workout"] = {
            "today_count": today.workout_count if today else 0,
            "week_count": sum(1 for s in recent_7 if s.workout_count and s.workout_count > 0),
            "total_minutes_7d": sum(s.workout_minutes or 0 for s in recent_7),
            "trend_8w": HealthCommandCenterService._weekly_workout_trend(summaries),
        }

        # --- Activity ---
        panels["activity"] = {
            "today_steps": today.steps if today else None,
            "today_active_minutes": today.active_minutes if today else None,
            "today_calories": today.calories_burned if today else None,
            "avg_steps_7d": None,
            "trend_14d": [
                {"date": str(s.summary_date), "value": s.steps}
                for s in recent_14 if s.steps
            ],
        }
        step_7 = [s.steps for s in recent_7 if s.steps]
        if step_7:
            panels["activity"]["avg_steps_7d"] = int(sum(step_7) / len(step_7))

        # --- Glucose ---
        glucose_data = [s for s in recent_7 if s.glucose_avg]
        panels["glucose"] = {
            "current": _dec(today.glucose_avg) if today else None,
            "time_in_range": _dec(today.time_in_range_pct) if today else None,
            "variability": _dec(today.glucose_variability) if today else None,
            "avg_7d": None,
            "fasting_avg_7d": None,
            "trend_14d": [
                {"date": str(s.summary_date), "value": _dec(s.glucose_avg)}
                for s in summaries[-14:] if s.glucose_avg
            ],
        }
        if glucose_data:
            panels["glucose"]["avg_7d"] = round(
                sum(float(s.glucose_avg) for s in glucose_data) / len(glucose_data), 1
            )

        # --- Nutrition ---
        panels["nutrition"] = {
            "today_calories": today.calories_consumed if today else None,
            "today_protein": _dec(today.protein_g) if today else None,
            "today_carbs": _dec(today.carbs_g) if today else None,
            "today_fat": _dec(today.fat_g) if today else None,
            "nutrition_logged": today.nutrition_logged if today else False,
            "tracking_streak": HealthCommandCenterService._nutrition_streak(summaries),
            "water_oz": _dec(today.water_oz) if today else None,
            "trend_7d": [
                {
                    "date": str(s.summary_date),
                    "calories": s.calories_consumed,
                    "protein": _dec(s.protein_g),
                }
                for s in recent_7 if s.nutrition_logged
            ],
        }

        # --- Recovery ---
        panels["recovery"] = {
            "score": today.recovery_score if today else None,
            "status": (today.recovery_drivers or {}).get("status") if today else None,
            "hrv": _dec(today.hrv) if today else None,
            "resting_hr": today.resting_hr if today else None,
            "recommendation": (today.recovery_drivers or {}).get("recommendation") if today else None,
            "trend_14d": [
                {"date": str(s.summary_date), "value": s.recovery_score}
                for s in recent_14 if s.recovery_score
            ],
        }

        # --- Medication ---
        panels["medication"] = {
            "today_adherence": _dec(today.medication_adherence_pct) if today else None,
            "doses_taken": today.doses_taken if today else 0,
            "doses_expected": today.doses_expected if today else 0,
            "avg_7d": None,
            "trend_30d": [
                {"date": str(s.summary_date), "value": _dec(s.medication_adherence_pct)}
                for s in summaries[-30:] if s.medication_adherence_pct is not None
            ],
        }
        med_7 = [float(s.medication_adherence_pct) for s in recent_7 if s.medication_adherence_pct is not None]
        if med_7:
            panels["medication"]["avg_7d"] = round(sum(med_7) / len(med_7), 1)

        return panels

    @staticmethod
    def _build_trend_lines(summaries, target):
        """Build time-series data for chart rendering."""
        def _dec(val):
            return float(val) if val is not None else None

        return {
            "weight": [
                {"date": str(s.summary_date), "value": _dec(s.weight)}
                for s in summaries if s.weight
            ],
            "sleep_hours": [
                {"date": str(s.summary_date), "value": _dec(s.sleep_hours)}
                for s in summaries if s.sleep_hours
            ],
            "steps": [
                {"date": str(s.summary_date), "value": s.steps}
                for s in summaries if s.steps
            ],
            "glucose_avg": [
                {"date": str(s.summary_date), "value": _dec(s.glucose_avg)}
                for s in summaries if s.glucose_avg
            ],
            "health_score": [
                {"date": str(s.summary_date), "value": s.health_score}
                for s in summaries if s.health_score
            ],
            "recovery_score": [
                {"date": str(s.summary_date), "value": s.recovery_score}
                for s in summaries if s.recovery_score
            ],
            "hrv": [
                {"date": str(s.summary_date), "value": _dec(s.hrv)}
                for s in summaries if s.hrv
            ],
        }

    @staticmethod
    def _weekly_workout_trend(summaries):
        """Group workout counts by week for the 8-week trend bar chart."""
        if not summaries:
            return []

        weeks = {}
        for s in summaries:
            # ISO week start (Monday)
            week_start = s.summary_date - timedelta(days=s.summary_date.weekday())
            if week_start not in weeks:
                weeks[week_start] = 0
            if s.workout_count and s.workout_count > 0:
                weeks[week_start] += 1

        # Last 8 weeks
        sorted_weeks = sorted(weeks.items())[-8:]
        return [
            {"week": str(w), "workouts": c}
            for w, c in sorted_weeks
        ]

    @staticmethod
    def _nutrition_streak(summaries):
        """Count consecutive days with nutrition logged (from most recent)."""
        streak = 0
        for s in reversed(summaries):
            if s.nutrition_logged:
                streak += 1
            else:
                break
        return streak
