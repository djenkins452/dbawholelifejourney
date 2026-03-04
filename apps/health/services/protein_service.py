"""
Protein Intelligence Service — target calculation, scoring, and coaching.

Default target: 0.7 g/lb body weight (adjustable per user via HealthProfile).
Score: 0-100 based on ratio to target, consistency, and workout-day adequacy.

Usage:
    from apps.health.services.protein_service import ProteinService

    target = ProteinService.calculate_target(user)
    ratio = ProteinService.calculate_ratio(consumed_g=150, target_g=168)
    score = ProteinService.calculate_score(user, date.today())
    coaching = ProteinService.get_coaching(user, date.today())
"""

import logging
from datetime import timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)

# Default protein target: 0.7g per pound of body weight
DEFAULT_PROTEIN_PER_LB = Decimal("0.700")


class ProteinService:
    """Protein intelligence — target, ratio, scoring, and coaching."""

    @staticmethod
    def calculate_target(user, target_date=None):
        """
        Calculate daily protein target in grams.

        Priority:
            1. HealthProfile.protein_target_g_override (fixed gram target)
            2. HealthProfile.protein_per_lb_target * body weight
            3. DEFAULT_PROTEIN_PER_LB (0.7) * body weight
            4. None if no weight data available

        Returns:
            Decimal (grams) or None
        """
        from apps.health.models import HealthProfile

        multiplier = DEFAULT_PROTEIN_PER_LB
        override_g = None

        try:
            profile = HealthProfile.objects.get(user=user)
            if profile.protein_target_g_override:
                return profile.protein_target_g_override
            if profile.protein_per_lb_target:
                multiplier = profile.protein_per_lb_target
        except HealthProfile.DoesNotExist:
            pass

        # Get current body weight
        weight_lbs = ProteinService._get_weight_lbs(user, target_date)
        if weight_lbs is None:
            return None

        target = Decimal(str(float(weight_lbs) * float(multiplier)))
        return target.quantize(Decimal("0.01"))

    @staticmethod
    def calculate_ratio(consumed_g, target_g):
        """
        Calculate protein ratio (consumed / target).

        Returns:
            Decimal (e.g. 0.89 = 89% of target), or None
        """
        if target_g is None or target_g <= 0 or consumed_g is None:
            return None
        ratio = Decimal(str(float(consumed_g) / float(target_g)))
        return ratio.quantize(Decimal("0.01"))

    @staticmethod
    def calculate_protein_per_lb(consumed_g, weight_lbs):
        """
        Calculate grams of protein per pound of body weight.

        Returns:
            Decimal (e.g. 0.650), or None
        """
        if weight_lbs is None or weight_lbs <= 0 or consumed_g is None:
            return None
        per_lb = Decimal(str(float(consumed_g) / float(weight_lbs)))
        return per_lb.quantize(Decimal("0.001"))

    @staticmethod
    def calculate_score(user, target_date):
        """
        Compute protein adequacy score (0-100).

        Components:
            - Ratio to target today (50%): How close to daily target
            - 7-day consistency (30%): How many of last 7 days hit >=80% target
            - Workout-day bonus (20%): Extra points for meeting target on workout days

        Returns:
            (score: int or None, details: dict)
        """
        from apps.health.models import DailyHealthSummary

        # Get today's summary
        today = (
            DailyHealthSummary.objects
            .filter(user=user, summary_date=target_date)
            .first()
        )
        if not today or today.protein_g is None:
            return None, {"status": "no_data", "message": "No protein data for today"}

        target_g = ProteinService.calculate_target(user, target_date)
        if target_g is None:
            return None, {"status": "no_target", "message": "No weight data to calculate protein target"}

        consumed = float(today.protein_g)
        target = float(target_g)
        ratio = consumed / target if target > 0 else 0

        # --- Component 1: Today's ratio (50%) ---
        if ratio >= 1.0:
            ratio_score = 100
        elif ratio >= 0.9:
            ratio_score = 90
        elif ratio >= 0.8:
            ratio_score = 75
        elif ratio >= 0.7:
            ratio_score = 60
        elif ratio >= 0.5:
            ratio_score = 40
        else:
            ratio_score = 20

        # --- Component 2: 7-day consistency (30%) ---
        week_start = target_date - timedelta(days=6)
        week_summaries = list(
            DailyHealthSummary.objects
            .filter(
                user=user,
                summary_date__gte=week_start,
                summary_date__lte=target_date,
                protein_g__isnull=False,
            )
            .values_list("protein_g", flat=True)
        )

        if week_summaries:
            days_hitting_80 = sum(
                1 for p in week_summaries
                if float(p) >= target * 0.8
            )
            consistency_score = min(100, int(days_hitting_80 / len(week_summaries) * 100))
        else:
            consistency_score = 0

        # --- Component 3: Workout-day bonus (20%) ---
        workout_protein_days = list(
            DailyHealthSummary.objects
            .filter(
                user=user,
                summary_date__gte=week_start,
                summary_date__lte=target_date,
                workout_count__gt=0,
                protein_g__isnull=False,
            )
            .values_list("protein_g", flat=True)
        )

        if workout_protein_days:
            workout_hits = sum(
                1 for p in workout_protein_days
                if float(p) >= target * 0.8
            )
            workout_score = min(100, int(workout_hits / len(workout_protein_days) * 100))
        else:
            # No workout days this week — neutral score
            workout_score = 70

        # Weighted final
        final = int(ratio_score * 0.5 + consistency_score * 0.3 + workout_score * 0.2)
        final = max(0, min(100, final))

        details = {
            "score": final,
            "status": ProteinService._status_label(final),
            "today_consumed_g": round(consumed, 1),
            "today_target_g": round(target, 1),
            "today_ratio": round(ratio, 2),
            "today_pct": int(ratio * 100),
            "week_days_at_80pct": days_hitting_80 if week_summaries else 0,
            "week_days_tracked": len(week_summaries),
            "workout_days_hit": (
                workout_hits if workout_protein_days else None
            ),
            "components": {
                "ratio_score": ratio_score,
                "consistency_score": consistency_score,
                "workout_score": workout_score,
            },
        }

        return final, details

    @staticmethod
    def get_coaching(user, target_date):
        """
        Generate protein coaching message based on current state.

        Returns:
            dict with keys: message, severity, context
        """
        from apps.health.models import DailyHealthSummary

        target_g = ProteinService.calculate_target(user, target_date)
        if target_g is None:
            return {
                "message": "Log your weight to unlock protein coaching",
                "severity": "info",
                "context": "missing_weight",
            }

        today = (
            DailyHealthSummary.objects
            .filter(user=user, summary_date=target_date)
            .first()
        )

        target = float(target_g)
        is_workout_day = today and today.workout_count and today.workout_count > 0

        if not today or today.protein_g is None:
            if is_workout_day:
                return {
                    "message": f"Workout day — aim for {target:.0f}g+ protein today to support recovery",
                    "severity": "nudge",
                    "context": "workout_day_no_data",
                    "target_g": round(target, 1),
                }
            return {
                "message": f"Log your meals to track protein (target: {target:.0f}g/day)",
                "severity": "info",
                "context": "no_data",
                "target_g": round(target, 1),
            }

        consumed = float(today.protein_g)
        ratio = consumed / target if target > 0 else 0
        remaining = max(0, target - consumed)

        if ratio >= 1.0:
            msg = f"Protein target hit! {consumed:.0f}g of {target:.0f}g ({ratio:.0%})"
            if is_workout_day:
                msg += " — great fueling for your workout"
            return {
                "message": msg,
                "severity": "success",
                "context": "target_met",
                "consumed_g": round(consumed, 1),
                "target_g": round(target, 1),
                "remaining_g": 0,
            }
        elif ratio >= 0.8:
            return {
                "message": f"Almost there — {remaining:.0f}g more protein to hit your {target:.0f}g target",
                "severity": "nudge",
                "context": "close_to_target",
                "consumed_g": round(consumed, 1),
                "target_g": round(target, 1),
                "remaining_g": round(remaining, 1),
            }
        else:
            if is_workout_day:
                return {
                    "message": (
                        f"Low protein on workout day — {consumed:.0f}g of {target:.0f}g target. "
                        f"Add {remaining:.0f}g more for recovery support"
                    ),
                    "severity": "warning",
                    "context": "low_protein_workout_day",
                    "consumed_g": round(consumed, 1),
                    "target_g": round(target, 1),
                    "remaining_g": round(remaining, 1),
                }
            return {
                "message": (
                    f"Protein intake low — {consumed:.0f}g of {target:.0f}g target ({ratio:.0%}). "
                    f"Consider a protein-rich snack ({remaining:.0f}g remaining)"
                ),
                "severity": "info",
                "context": "below_target",
                "consumed_g": round(consumed, 1),
                "target_g": round(target, 1),
                "remaining_g": round(remaining, 1),
            }

    @staticmethod
    def get_weekly_summary(user, target_date):
        """
        Get a 7-day protein summary for dashboards.

        Returns:
            dict with avg_consumed, avg_target, avg_ratio, days_at_target,
            best_day, worst_day, workout_day_avg
        """
        from apps.health.models import DailyHealthSummary

        week_start = target_date - timedelta(days=6)
        summaries = list(
            DailyHealthSummary.objects
            .filter(
                user=user,
                summary_date__gte=week_start,
                summary_date__lte=target_date,
            )
            .order_by("summary_date")
        )

        target_g = ProteinService.calculate_target(user, target_date)
        target = float(target_g) if target_g else None

        protein_days = [s for s in summaries if s.protein_g is not None]
        if not protein_days:
            return {"status": "no_data", "days_tracked": 0}

        consumed_values = [float(s.protein_g) for s in protein_days]
        avg_consumed = sum(consumed_values) / len(consumed_values)

        result = {
            "status": "ok",
            "days_tracked": len(protein_days),
            "total_days": len(summaries),
            "avg_consumed_g": round(avg_consumed, 1),
            "max_consumed_g": round(max(consumed_values), 1),
            "min_consumed_g": round(min(consumed_values), 1),
            "target_g": round(target, 1) if target else None,
            "daily_detail": [],
        }

        if target:
            days_at_target = sum(1 for v in consumed_values if v >= target)
            days_at_80 = sum(1 for v in consumed_values if v >= target * 0.8)
            result["days_at_target"] = days_at_target
            result["days_at_80pct"] = days_at_80
            result["avg_ratio"] = round(avg_consumed / target, 2)

        # Workout-day protein
        workout_days = [s for s in protein_days if s.workout_count and s.workout_count > 0]
        rest_days = [s for s in protein_days if not s.workout_count or s.workout_count == 0]

        if workout_days:
            workout_avg = sum(float(s.protein_g) for s in workout_days) / len(workout_days)
            result["workout_day_avg_g"] = round(workout_avg, 1)
        if rest_days:
            rest_avg = sum(float(s.protein_g) for s in rest_days) / len(rest_days)
            result["rest_day_avg_g"] = round(rest_avg, 1)

        # Daily detail for chart rendering
        for s in summaries:
            entry = {
                "date": str(s.summary_date),
                "consumed_g": float(s.protein_g) if s.protein_g else None,
                "target_g": target,
                "is_workout_day": bool(s.workout_count and s.workout_count > 0),
            }
            if target and s.protein_g:
                entry["ratio"] = round(float(s.protein_g) / target, 2)
            result["daily_detail"].append(entry)

        return result

    # --- Internal helpers ---

    @staticmethod
    def _get_weight_lbs(user, target_date=None):
        """
        Get user's most recent weight in lbs.

        Looks at DailyHealthSummary first (fast), falls back to WeightEntry.
        """
        from apps.health.models import DailyHealthSummary, WeightEntry
        from datetime import date as dt_date

        target = target_date or dt_date.today()

        # Try DailyHealthSummary (already in lbs)
        summary = (
            DailyHealthSummary.objects
            .filter(user=user, summary_date__lte=target, weight__isnull=False)
            .order_by("-summary_date")
            .values_list("weight", flat=True)
            .first()
        )
        if summary:
            return summary

        # Fallback to WeightEntry
        entry = (
            WeightEntry.objects
            .filter(user=user, recorded_at__date__lte=target)
            .order_by("-recorded_at")
            .first()
        )
        if entry:
            if entry.unit == "kg":
                return Decimal(str(round(float(entry.value) * 2.20462, 2)))
            return entry.value

        return None

    @staticmethod
    def _status_label(score):
        """Convert protein score to status label."""
        if score >= 90:
            return "excellent"
        elif score >= 75:
            return "good"
        elif score >= 60:
            return "fair"
        elif score >= 40:
            return "needs_improvement"
        return "low"
