"""
Recovery Score Service — baseline-aware recovery scoring (0-100).

Uses rolling baselines for HRV, resting HR, sleep, and training load.
Deviation from personal baseline determines score, not absolute values.

Usage:
    from apps.health.services.recovery_score import RecoveryScoreService
    score, drivers = RecoveryScoreService.compute(user, date.today())
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg

logger = logging.getLogger(__name__)

# Weights for recovery score components
WEIGHTS = {
    "sleep": 0.40,
    "hrv": 0.25,
    "resting_hr": 0.15,
    "training_load": 0.10,
    "glucose": 0.10,
}


class RecoveryScoreService:
    """Compute a 0-100 recovery score with explainable drivers."""

    @staticmethod
    def compute(user, target_date):
        """
        Compute recovery score for a specific date.

        Returns:
            tuple: (score: int or None, drivers: dict)

        Drivers dict structure:
            {
                "components": {
                    "sleep": {"score": 75, "weight": 0.40, "detail": "..."},
                    ...
                },
                "top_positive": "Sleep quality above baseline",
                "top_negative": "Training load elevated",
                "status": "good",  # excellent/good/fair/poor/critical
                "recommendation": "Normal training appropriate",
            }
        """
        from apps.health.models import DailyHealthSummary
        from apps.health.services.baseline_policy import BaselinePolicy

        if not BaselinePolicy.baseline_ready(user, target_date):
            return None, {"status": "baseline_collecting", "message": "Collecting baseline data"}

        # Get today's summary
        today = (
            DailyHealthSummary.objects
            .filter(user=user, summary_date=target_date)
            .first()
        )
        if not today:
            return None, {"status": "no_data", "message": "No data for this date"}

        # Get baseline (14-day rolling average, excluding today)
        baseline_start = target_date - timedelta(days=14)
        baselines = (
            DailyHealthSummary.objects
            .filter(
                user=user,
                summary_date__gte=baseline_start,
                summary_date__lt=target_date,
            )
            .aggregate(
                avg_sleep_hours=Avg("sleep_hours"),
                avg_sleep_quality=Avg("sleep_quality_score"),
                avg_hrv=Avg("hrv"),
                avg_resting_hr=Avg("resting_hr"),
                avg_training_load=Avg("training_load"),
                avg_glucose_variability=Avg("glucose_variability"),
            )
        )

        components = {}
        active_weights = {}

        # --- Sleep component (40%) ---
        sleep_score = RecoveryScoreService._score_sleep(today, baselines)
        if sleep_score is not None:
            components["sleep"] = sleep_score
            active_weights["sleep"] = WEIGHTS["sleep"]

        # --- HRV component (25%) ---
        hrv_score = RecoveryScoreService._score_hrv(today, baselines)
        if hrv_score is not None:
            components["hrv"] = hrv_score
            active_weights["hrv"] = WEIGHTS["hrv"]

        # --- Resting HR component (15%) ---
        hr_score = RecoveryScoreService._score_resting_hr(today, baselines)
        if hr_score is not None:
            components["resting_hr"] = hr_score
            active_weights["resting_hr"] = WEIGHTS["resting_hr"]

        # --- Training load component (10%) ---
        load_score = RecoveryScoreService._score_training_load(today, baselines)
        if load_score is not None:
            components["training_load"] = load_score
            active_weights["training_load"] = WEIGHTS["training_load"]

        # --- Glucose stability component (10%) ---
        glucose_score = RecoveryScoreService._score_glucose(today, baselines)
        if glucose_score is not None:
            components["glucose"] = glucose_score
            active_weights["glucose"] = WEIGHTS["glucose"]

        # No components available
        if not active_weights:
            return None, {"status": "insufficient_data", "message": "Not enough signals for recovery score"}

        # Normalize weights and compute final score
        total_weight = sum(active_weights.values())
        final_score = sum(
            components[k]["score"] * (active_weights[k] / total_weight)
            for k in active_weights
        )
        final_score = max(0, min(100, int(round(final_score))))

        # Build drivers
        status = RecoveryScoreService._status_label(final_score)
        recommendation = RecoveryScoreService._recommendation(final_score)

        # Find top positive and negative
        sorted_components = sorted(
            components.items(),
            key=lambda x: x[1]["score"],
            reverse=True,
        )
        top_positive = sorted_components[0][1]["detail"] if sorted_components else ""
        top_negative = sorted_components[-1][1]["detail"] if len(sorted_components) > 1 else ""

        drivers = {
            "components": {
                k: {
                    "score": v["score"],
                    "weight": active_weights.get(k, 0),
                    "detail": v["detail"],
                }
                for k, v in components.items()
            },
            "top_positive": top_positive,
            "top_negative": top_negative,
            "status": status,
            "recommendation": recommendation,
        }

        return final_score, drivers

    @staticmethod
    def _score_sleep(today, baselines):
        """Score sleep quality and duration vs baseline."""
        hours = float(today.sleep_hours or 0)
        quality = today.sleep_quality_score

        if hours == 0 and quality is None:
            return None

        score = 50  # Default: neutral
        detail_parts = []

        if hours > 0:
            # Duration scoring: 7-9h optimal
            if hours >= 7:
                duration_score = min(100, int(hours / 8 * 100))
            elif hours >= 6:
                duration_score = 60
            elif hours >= 5:
                duration_score = 35
            else:
                duration_score = 15
            score = duration_score
            detail_parts.append(f"{hours:.1f}h sleep")

        if quality is not None:
            # Blend with quality score
            score = int((score + quality) / 2)
            detail_parts.append(f"quality {quality}/100")

        # Compare to baseline
        baseline_hours = float(baselines.get("avg_sleep_hours") or 0)
        if baseline_hours > 0 and hours > 0:
            pct_of_baseline = hours / baseline_hours
            if pct_of_baseline >= 1.05:
                detail_parts.append("above baseline")
                score = min(100, score + 10)
            elif pct_of_baseline < 0.85:
                detail_parts.append("below baseline")
                score = max(0, score - 10)

        return {"score": max(0, min(100, score)), "detail": ", ".join(detail_parts) or "Sleep data available"}

    @staticmethod
    def _score_hrv(today, baselines):
        """Score HRV relative to personal baseline."""
        hrv = float(today.hrv or 0)
        baseline_hrv = float(baselines.get("avg_hrv") or 0)

        if hrv == 0:
            return None

        if baseline_hrv == 0:
            # No baseline yet — use absolute scale
            if hrv >= 50:
                score = 85
            elif hrv >= 35:
                score = 70
            elif hrv >= 20:
                score = 50
            else:
                score = 30
            return {"score": score, "detail": f"HRV {hrv:.0f}ms (no baseline yet)"}

        # Relative to baseline
        ratio = hrv / baseline_hrv
        if ratio >= 1.15:
            score = 95
            detail = f"HRV {hrv:.0f}ms, +{(ratio-1)*100:.0f}% above baseline"
        elif ratio >= 1.05:
            score = 82
            detail = f"HRV {hrv:.0f}ms, above baseline"
        elif ratio >= 0.95:
            score = 70
            detail = f"HRV {hrv:.0f}ms, at baseline"
        elif ratio >= 0.85:
            score = 50
            detail = f"HRV {hrv:.0f}ms, below baseline"
        elif ratio >= 0.75:
            score = 35
            detail = f"HRV {hrv:.0f}ms, significantly below baseline"
        else:
            score = 20
            detail = f"HRV {hrv:.0f}ms, critically below baseline"

        return {"score": score, "detail": detail}

    @staticmethod
    def _score_resting_hr(today, baselines):
        """Score resting HR (lower is better, relative to baseline)."""
        hr = today.resting_hr
        baseline_hr = baselines.get("avg_resting_hr")

        if hr is None:
            return None

        if baseline_hr is None:
            # Absolute scale
            if hr < 60:
                score = 90
            elif hr < 70:
                score = 75
            elif hr < 80:
                score = 55
            else:
                score = 35
            return {"score": score, "detail": f"Resting HR {hr} bpm (no baseline)"}

        baseline_hr = float(baseline_hr)
        diff = float(hr) - baseline_hr

        if diff <= -5:
            score = 90
            detail = f"Resting HR {hr} bpm, {abs(diff):.0f} below baseline"
        elif diff <= -2:
            score = 80
            detail = f"Resting HR {hr} bpm, slightly below baseline"
        elif diff <= 2:
            score = 70
            detail = f"Resting HR {hr} bpm, at baseline"
        elif diff <= 5:
            score = 50
            detail = f"Resting HR {hr} bpm, elevated above baseline"
        elif diff <= 10:
            score = 30
            detail = f"Resting HR {hr} bpm, significantly elevated"
        else:
            score = 15
            detail = f"Resting HR {hr} bpm, critically elevated"

        return {"score": score, "detail": detail}

    @staticmethod
    def _score_training_load(today, baselines):
        """Score recovery based on recent training load (inverse: high load = lower recovery)."""
        load = float(today.training_load or 0)
        baseline_load = float(baselines.get("avg_training_load") or 0)

        # No workout today = well recovered from training perspective
        if load == 0 and today.workout_count == 0:
            return {"score": 85, "detail": "Rest day (no training load)"}

        if baseline_load == 0:
            # No baseline — just note the load
            return {"score": 65, "detail": f"Training load {load:.0f} (no baseline yet)"}

        ratio = load / baseline_load
        if ratio <= 0.5:
            score = 85
            detail = f"Light training load ({ratio:.0%} of baseline)"
        elif ratio <= 0.8:
            score = 75
            detail = f"Moderate training load"
        elif ratio <= 1.2:
            score = 60
            detail = f"Normal training load"
        elif ratio <= 1.5:
            score = 45
            detail = f"Heavy training load ({ratio:.0%} of baseline)"
        else:
            score = 25
            detail = f"Very heavy load ({ratio:.0%} of baseline)"

        return {"score": score, "detail": detail}

    @staticmethod
    def _score_glucose(today, baselines):
        """Score glucose stability."""
        cv = float(today.glucose_variability or 0)
        tir = float(today.time_in_range_pct or 0)

        if cv == 0 and tir == 0:
            return None

        score = 70  # Default neutral
        detail_parts = []

        if tir > 0:
            if tir >= 85:
                score = 90
            elif tir >= 70:
                score = 75
            elif tir >= 55:
                score = 55
            else:
                score = 35
            detail_parts.append(f"{tir:.0f}% time in range")

        if cv > 0:
            if cv < 25:
                cv_score = 90
            elif cv < 36:
                cv_score = 70
            elif cv < 50:
                cv_score = 45
            else:
                cv_score = 25
            score = int((score + cv_score) / 2)
            detail_parts.append(f"CV {cv:.1f}%")

        return {"score": max(0, min(100, score)), "detail": ", ".join(detail_parts)}

    @staticmethod
    def _status_label(score):
        """Map score to status label."""
        if score >= 85:
            return "excellent"
        elif score >= 70:
            return "good"
        elif score >= 50:
            return "fair"
        elif score >= 30:
            return "poor"
        return "critical"

    @staticmethod
    def _recommendation(score):
        """Map score to training recommendation."""
        if score >= 85:
            return "Fully recovered — ready for hard training"
        elif score >= 70:
            return "Good recovery — normal training appropriate"
        elif score >= 50:
            return "Moderate recovery — lighter training recommended"
        elif score >= 30:
            return "Low recovery — active recovery or rest day suggested"
        return "Critical — complete rest recommended, monitor symptoms"
