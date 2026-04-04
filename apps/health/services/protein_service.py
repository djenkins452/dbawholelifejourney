"""
Protein Intelligence Service — LBM-based targets, adaptive workout-day goals,
scoring, coaching, and weekly summaries.

Target priority:
    1. HealthProfile.protein_target_g_override (fixed)
    2. Lean Body Mass × multiplier (1.0 rest / 1.1 workout)
    3. Body weight × 0.7 (fallback when no body fat data)

LBM formula:
    LBM = weight × (1 − body_fat_pct / 100)

Usage:
    from apps.health.services.protein_service import ProteinService

    info = ProteinService.calculate_target(user, date.today(), is_workout_day=True)
    # Returns: {target_g, method, lbm, workout_day, ...}

    ratio = ProteinService.calculate_ratio(consumed_g=193, target_g=212)
    score = ProteinService.calculate_score(user, date.today())
    coaching = ProteinService.get_coaching(user, date.today())
"""

import logging
from datetime import timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)

# Default fallback: 0.7g per pound of total body weight
DEFAULT_PROTEIN_PER_LB = Decimal("0.700")

# LBM-based multipliers
LBM_REST_MULTIPLIER = Decimal("1.000")    # 1.0 g/lb LBM on rest days
LBM_WORKOUT_MULTIPLIER = Decimal("1.100")  # 1.1 g/lb LBM on workout days


class ProteinService:
    """Protein intelligence — LBM-aware targets, scoring, coaching."""

    # ------------------------------------------------------------------
    # Core calculation methods
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_lean_body_mass(weight_lbs, body_fat_pct):
        """
        Calculate lean body mass (LBM) from weight and body fat %.

        LBM = weight × (1 − body_fat_pct / 100)

        Args:
            weight_lbs: Decimal or float — total body weight in lbs
            body_fat_pct: Decimal or float — body fat percentage (e.g. 36.7)

        Returns:
            Decimal (lbs) or None if inputs invalid
        """
        if weight_lbs is None or body_fat_pct is None:
            return None
        w = float(weight_lbs)
        bf = float(body_fat_pct)
        if w <= 0 or bf < 0 or bf >= 100:
            return None
        lbm = w * (1 - bf / 100)
        return Decimal(str(round(lbm, 2)))

    @staticmethod
    def calculate_target(user, target_date=None, is_workout_day=None, weight_lbs=None, body_fat_pct=None):
        """
        Calculate daily protein target with full context.

        Priority:
            1. HealthProfile.protein_target_g_override → fixed gram target
            2. LBM × multiplier (1.0 rest / 1.1 workout) → when body fat available
            3. Body weight × HealthProfile.protein_per_lb_target → custom multiplier
            4. Body weight × 0.7 → default fallback

        Args:
            user: User instance
            target_date: date (defaults to today)
            is_workout_day: bool or None (auto-detect from DailyHealthSummary)
            weight_lbs: Decimal override (skip DB lookup)
            body_fat_pct: Decimal override (skip DB lookup)

        Returns:
            dict with keys:
                target_g: Decimal — grams
                method: str — 'lean_body_mass', 'body_weight', or 'override'
                lbm: float or None
                workout_day: bool
                multiplier: float
                weight_lbs: float or None
                body_fat_pct: float or None
            OR None if no weight data
        """
        from apps.health.models import HealthProfile
        from datetime import date as dt_date

        target = target_date or dt_date.today()

        # Check for override first
        try:
            profile = HealthProfile.objects.get(user=user)
            if profile.protein_target_g_override:
                workout = ProteinService._detect_workout_day(
                    user, target
                ) if is_workout_day is None else is_workout_day
                return {
                    "target_g": profile.protein_target_g_override,
                    "method": "override",
                    "lbm": None,
                    "workout_day": workout,
                    "multiplier": None,
                    "weight_lbs": None,
                    "body_fat_pct": None,
                }
        except HealthProfile.DoesNotExist:
            profile = None

        # Get weight
        if weight_lbs is None:
            weight_lbs = ProteinService._get_weight_lbs(user, target)
        if weight_lbs is None:
            return None

        # Auto-detect workout day
        if is_workout_day is None:
            is_workout_day = ProteinService._detect_workout_day(user, target)

        # Get body fat %
        if body_fat_pct is None:
            body_fat_pct = ProteinService._get_body_fat_pct(user, target)

        # Try LBM method
        lbm = ProteinService.calculate_lean_body_mass(weight_lbs, body_fat_pct)
        if lbm is not None:
            multiplier = LBM_WORKOUT_MULTIPLIER if is_workout_day else LBM_REST_MULTIPLIER
            target_g = Decimal(str(float(lbm) * float(multiplier)))
            return {
                "target_g": target_g.quantize(Decimal("0.01")),
                "method": "lean_body_mass",
                "lbm": round(float(lbm), 2),
                "workout_day": is_workout_day,
                "multiplier": float(multiplier),
                "weight_lbs": float(weight_lbs),
                "body_fat_pct": float(body_fat_pct),
            }

        # Fallback: body weight method
        bw_multiplier = DEFAULT_PROTEIN_PER_LB
        if profile and profile.protein_per_lb_target:
            bw_multiplier = profile.protein_per_lb_target

        target_g = Decimal(str(float(weight_lbs) * float(bw_multiplier)))
        return {
            "target_g": target_g.quantize(Decimal("0.01")),
            "method": "body_weight",
            "lbm": None,
            "workout_day": is_workout_day,
            "multiplier": float(bw_multiplier),
            "weight_lbs": float(weight_lbs),
            "body_fat_pct": None,
        }

    @staticmethod
    def calculate_target_g(user, target_date=None, is_workout_day=None,
                           weight_lbs=None, body_fat_pct=None):
        """
        Convenience: return just the target grams (Decimal or None).
        Backward-compatible with the old calculate_target() return signature.
        """
        info = ProteinService.calculate_target(
            user, target_date, is_workout_day, weight_lbs, body_fat_pct
        )
        if info is None:
            return None
        return info["target_g"]

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

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_score(user, target_date):
        """
        Compute protein adequacy score (0-100).

        Components:
            - Ratio to target today (50%)
            - 7-day consistency (30%)
            - Workout-day adequacy (20%)

        Workout-day penalty: if workout day and ratio < 0.85, −10 pts.

        Returns:
            (score: int or None, details: dict)
        """
        from apps.health.models import DailyHealthSummary

        today_summary = (
            DailyHealthSummary.objects
            .filter(user=user, summary_date=target_date)
            .first()
        )
        if not today_summary or today_summary.protein_g is None:
            return None, {"status": "no_data", "message": "No protein data for today"}

        target_info = ProteinService.calculate_target(user, target_date)
        if target_info is None:
            return None, {"status": "no_target", "message": "No weight data to calculate protein target"}

        target_g_val = float(target_info["target_g"])
        consumed = float(today_summary.protein_g)
        ratio = consumed / target_g_val if target_g_val > 0 else 0
        is_workout = target_info["workout_day"]

        # --- Component 1: Today's ratio (50%) ---
        if ratio >= 1.0:
            ratio_score = 100
        elif ratio >= 0.85:
            ratio_score = 90
        elif ratio >= 0.70:
            ratio_score = 75
        elif ratio >= 0.50:
            ratio_score = 60
        else:
            ratio_score = 40

        # Workout-day penalty
        if is_workout and ratio < 0.85:
            ratio_score = max(0, ratio_score - 10)

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

        days_hitting_80 = 0
        if week_summaries:
            days_hitting_80 = sum(
                1 for p in week_summaries
                if float(p) >= target_g_val * 0.8
            )
            consistency_score = min(100, int(days_hitting_80 / len(week_summaries) * 100))
        else:
            consistency_score = 0

        # --- Component 3: Workout-day adequacy (20%) ---
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

        workout_hits = 0
        if workout_protein_days:
            workout_hits = sum(
                1 for p in workout_protein_days
                if float(p) >= target_g_val * 0.85
            )
            workout_score = min(100, int(workout_hits / len(workout_protein_days) * 100))
        else:
            workout_score = 70

        # Weighted final
        final = int(ratio_score * 0.5 + consistency_score * 0.3 + workout_score * 0.2)
        final = max(0, min(100, final))

        details = {
            "score": final,
            "status": ProteinService._status_label(final),
            "method": target_info["method"],
            "lbm": target_info["lbm"],
            "workout_day": is_workout,
            "today_consumed_g": round(consumed, 1),
            "today_target_g": round(target_g_val, 1),
            "today_ratio": round(ratio, 2),
            "today_pct": int(ratio * 100),
            "week_days_at_80pct": days_hitting_80,
            "week_days_tracked": len(week_summaries),
            "workout_days_hit": workout_hits if workout_protein_days else None,
            "components": {
                "ratio_score": ratio_score,
                "consistency_score": consistency_score,
                "workout_score": workout_score,
            },
        }

        return final, details

    # ------------------------------------------------------------------
    # Coaching
    # ------------------------------------------------------------------

    @staticmethod
    def get_coaching(user, target_date):
        """
        Generate protein coaching message based on current state.

        Returns:
            dict with keys: message, severity, context, method, lbm, ...
        """
        from apps.health.models import DailyHealthSummary

        target_info = ProteinService.calculate_target(user, target_date)
        if target_info is None:
            return {
                "message": "Log your weight to unlock protein coaching",
                "severity": "info",
                "context": "missing_weight",
            }

        target_g_val = float(target_info["target_g"])
        method = target_info["method"]
        lbm = target_info["lbm"]
        is_workout = target_info["workout_day"]

        today = (
            DailyHealthSummary.objects
            .filter(user=user, summary_date=target_date)
            .first()
        )

        method_note = ""
        if method == "lean_body_mass":
            day_type = "workout" if is_workout else "rest"
            method_note = f" (LBM-based, {day_type} day)"

        if not today or today.protein_g is None:
            if is_workout:
                return {
                    "message": f"Workout day — aim for {target_g_val:.0f}g+ protein to support recovery{method_note}",
                    "severity": "nudge",
                    "context": "workout_day_no_data",
                    "target_g": round(target_g_val, 1),
                    "method": method,
                    "lbm": lbm,
                }
            return {
                "message": f"Log your meals to track protein (target: {target_g_val:.0f}g/day{method_note})",
                "severity": "info",
                "context": "no_data",
                "target_g": round(target_g_val, 1),
                "method": method,
                "lbm": lbm,
            }

        consumed = float(today.protein_g)
        ratio = consumed / target_g_val if target_g_val > 0 else 0
        remaining = max(0, target_g_val - consumed)

        base = {
            "consumed_g": round(consumed, 1),
            "target_g": round(target_g_val, 1),
            "remaining_g": round(remaining, 1),
            "method": method,
            "lbm": lbm,
        }

        if ratio >= 1.0:
            msg = f"Protein target hit! {consumed:.0f}g of {target_g_val:.0f}g ({ratio:.0%}){method_note}"
            if is_workout:
                msg += " — great fueling for your workout"
            return {**base, "message": msg, "severity": "success", "context": "target_met", "remaining_g": 0}
        elif ratio >= 0.85:
            return {
                **base,
                "message": f"Almost there — {remaining:.0f}g more protein to hit your {target_g_val:.0f}g target{method_note}",
                "severity": "nudge",
                "context": "close_to_target",
            }
        else:
            if is_workout:
                return {
                    **base,
                    "message": (
                        f"Low protein on workout day — {consumed:.0f}g of {target_g_val:.0f}g target. "
                        f"Add {remaining:.0f}g more for recovery support{method_note}"
                    ),
                    "severity": "warning",
                    "context": "low_protein_workout_day",
                }
            return {
                **base,
                "message": (
                    f"Protein intake low — {consumed:.0f}g of {target_g_val:.0f}g target ({ratio:.0%}). "
                    f"Consider a protein-rich snack ({remaining:.0f}g remaining){method_note}"
                ),
                "severity": "info",
                "context": "below_target",
            }

    # ------------------------------------------------------------------
    # Weekly summary
    # ------------------------------------------------------------------

    @staticmethod
    def get_weekly_summary(user, target_date):
        """
        Get a 7-day protein summary for dashboards.

        Returns dict with avg_consumed, target, method, consistency, etc.
        """
        from apps.health.models import DailyHealthSummary

        week_start = target_date - timedelta(days=6)
        summaries = list(
            DailyHealthSummary.objects
            .filter(user=user, summary_date__gte=week_start, summary_date__lte=target_date)
            .order_by("summary_date")
        )

        target_info = ProteinService.calculate_target(user, target_date)
        target_g_val = float(target_info["target_g"]) if target_info else None

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
            "target_g": round(target_g_val, 1) if target_g_val else None,
            "method": target_info["method"] if target_info else None,
            "lbm": target_info["lbm"] if target_info else None,
            "daily_detail": [],
        }

        if target_g_val:
            days_at_target = sum(1 for v in consumed_values if v >= target_g_val)
            days_at_80 = sum(1 for v in consumed_values if v >= target_g_val * 0.8)
            result["days_at_target"] = days_at_target
            result["days_at_80pct"] = days_at_80
            result["avg_ratio"] = round(avg_consumed / target_g_val, 2)
            result["consistency_pct"] = round(days_at_80 / len(protein_days) * 100, 1)

        # Workout vs rest day
        workout_days = [s for s in protein_days if s.workout_count and s.workout_count > 0]
        rest_days = [s for s in protein_days if not s.workout_count or s.workout_count == 0]

        if workout_days:
            result["workout_day_avg_g"] = round(
                sum(float(s.protein_g) for s in workout_days) / len(workout_days), 1
            )
        if rest_days:
            result["rest_day_avg_g"] = round(
                sum(float(s.protein_g) for s in rest_days) / len(rest_days), 1
            )

        # Daily detail
        for s in summaries:
            is_wd = bool(s.workout_count and s.workout_count > 0)
            entry = {
                "date": str(s.summary_date),
                "consumed_g": float(s.protein_g) if s.protein_g else None,
                "target_g": float(s.protein_target_g) if s.protein_target_g else target_g_val,
                "is_workout_day": is_wd,
                "method": s.protein_method or (target_info["method"] if target_info else None),
            }
            if entry["target_g"] and s.protein_g:
                entry["ratio"] = round(float(s.protein_g) / entry["target_g"], 2)
            result["daily_detail"].append(entry)

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_weight_lbs(user, target_date=None):
        """Get user's most recent weight in lbs."""
        from apps.health.models import DailyHealthSummary, WeightEntry
        from datetime import date as dt_date

        target = target_date or dt_date.today()

        summary = (
            DailyHealthSummary.objects
            .filter(user=user, summary_date__lte=target, weight__isnull=False)
            .order_by("-summary_date")
            .values_list("weight", flat=True)
            .first()
        )
        if summary:
            return summary

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
    def _get_body_fat_pct(user, target_date=None):
        """
        Get user's most recent body fat percentage.

        Checks DailyHealthSummary first, then BodyCompositionEntry.
        """
        from apps.health.models import BodyCompositionEntry, DailyHealthSummary
        from datetime import date as dt_date

        target = target_date or dt_date.today()

        # DailyHealthSummary (fast)
        bf = (
            DailyHealthSummary.objects
            .filter(user=user, summary_date__lte=target, body_fat_pct__isnull=False)
            .order_by("-summary_date")
            .values_list("body_fat_pct", flat=True)
            .first()
        )
        if bf is not None:
            return bf

        # BodyCompositionEntry (flexible key-value)
        entry = (
            BodyCompositionEntry.objects
            .filter(
                user=user,
                metric_name__in=["body_fat_pct", "body_fat_percentage"],
                measurement_date__lte=target,
            )
            .order_by("-measurement_date")
            .first()
        )
        if entry and entry.value is not None:
            return entry.value

        return None

    @staticmethod
    def _detect_workout_day(user, target_date):
        """Check if target_date has a workout."""
        from apps.health.models import DailyHealthSummary, WorkoutSession

        # Check DailyHealthSummary first
        summary = (
            DailyHealthSummary.objects
            .filter(user=user, summary_date=target_date)
            .values_list("workout_count", flat=True)
            .first()
        )
        if summary is not None:
            return summary > 0

        # Fallback to WorkoutSession — any session (incl in-progress) counts
        # for protein-day detection since training has started
        from apps.health.services.workout_queries import WorkoutQueries
        return WorkoutQueries.on_date(user, target_date).exists()

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
