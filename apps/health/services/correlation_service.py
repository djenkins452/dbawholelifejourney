"""
Correlation Service — detects cross-domain health correlations.

Computes simple rank correlations (Spearman-like) between health signals
using the last 28 days of DailyHealthSummary data.

Avoids scipy dependency by using a simple rank-based correlation.

Usage:
    from apps.health.services.correlation_service import CorrelationService
    correlations = CorrelationService.compute(user, date.today())
"""

import logging
from datetime import timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)


def _rank_correlation(x_values, y_values):
    """
    Compute Spearman rank correlation without scipy.

    Returns coefficient (-1 to 1) or None if insufficient data.
    """
    if len(x_values) < 5 or len(x_values) != len(y_values):
        return None

    n = len(x_values)

    def rank(values):
        sorted_pairs = sorted(enumerate(values), key=lambda p: p[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and sorted_pairs[j + 1][1] == sorted_pairs[j][1]:
                j += 1
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[sorted_pairs[k][0]] = avg_rank
            i = j + 1
        return ranks

    x_ranks = rank(x_values)
    y_ranks = rank(y_values)

    # Spearman: 1 - 6 * sum(d^2) / (n * (n^2 - 1))
    d_sq = sum((x_ranks[i] - y_ranks[i]) ** 2 for i in range(n))
    denominator = n * (n ** 2 - 1)
    if denominator == 0:
        return None

    rho = 1 - (6 * d_sq / denominator)
    return round(rho, 3)


class CorrelationService:
    """Compute cross-domain health correlations."""

    @staticmethod
    def compute(user, target_date, lookback_days=28):
        """
        Compute top correlations from last N days.

        Returns:
            list of dicts, each with:
                signal_a: str
                signal_b: str
                correlation: float (-1 to 1)
                direction: str ("positive" or "negative")
                confidence: str ("high", "moderate", "low")
                interpretation: str
        """
        from apps.health.models import DailyHealthSummary

        start = target_date - timedelta(days=lookback_days - 1)
        summaries = list(
            DailyHealthSummary.objects
            .filter(user=user, summary_date__gte=start, summary_date__lte=target_date)
            .order_by("summary_date")
        )

        if len(summaries) < 10:
            return []

        results = []

        # 1. Sleep hours ↔ Glucose average
        corr = CorrelationService._correlate_fields(
            summaries, "sleep_hours", "glucose_avg"
        )
        if corr is not None:
            results.append({
                "signal_a": "sleep_hours",
                "signal_b": "glucose_avg",
                "correlation": corr,
                "direction": "negative" if corr < 0 else "positive",
                "confidence": CorrelationService._confidence(corr, summaries, "sleep_hours", "glucose_avg"),
                "interpretation": CorrelationService._interpret_sleep_glucose(corr),
            })

        # 2. Sleep hours ↔ Recovery score (next day)
        corr = CorrelationService._correlate_lagged(
            summaries, "sleep_hours", "recovery_score", lag=1
        )
        if corr is not None:
            results.append({
                "signal_a": "sleep_hours",
                "signal_b": "recovery_score_next_day",
                "correlation": corr,
                "direction": "positive" if corr > 0 else "negative",
                "confidence": CorrelationService._confidence_count(len(summaries) - 1),
                "interpretation": CorrelationService._interpret_sleep_recovery(corr),
            })

        # 3. Training load ↔ Recovery score (next day)
        corr = CorrelationService._correlate_lagged(
            summaries, "training_load", "recovery_score", lag=1
        )
        if corr is not None:
            results.append({
                "signal_a": "training_load",
                "signal_b": "recovery_score_next_day",
                "correlation": corr,
                "direction": "negative" if corr < 0 else "positive",
                "confidence": CorrelationService._confidence_count(len(summaries) - 1),
                "interpretation": CorrelationService._interpret_load_recovery(corr),
            })

        # 4. Caffeine ↔ Sleep quality
        corr = CorrelationService._correlate_fields(
            summaries, "caffeine_mg", "sleep_quality_score"
        )
        if corr is not None:
            results.append({
                "signal_a": "caffeine_mg",
                "signal_b": "sleep_quality",
                "correlation": corr,
                "direction": "negative" if corr < 0 else "positive",
                "confidence": CorrelationService._confidence(corr, summaries, "caffeine_mg", "sleep_quality_score"),
                "interpretation": CorrelationService._interpret_caffeine_sleep(corr),
            })

        # 5. Nutrition logged ↔ Weight trend (weekly)
        corr = CorrelationService._correlate_nutrition_weight(summaries)
        if corr is not None:
            results.append({
                "signal_a": "nutrition_tracking",
                "signal_b": "weight_change",
                "correlation": corr,
                "direction": "negative" if corr < 0 else "positive",
                "confidence": "moderate",
                "interpretation": CorrelationService._interpret_nutrition_weight(corr),
            })

        # 6. Workout days ↔ Glucose average
        corr = CorrelationService._correlate_binary(
            summaries, lambda s: s.workout_count > 0 if s.workout_count else False,
            "glucose_avg",
        )
        if corr is not None:
            results.append({
                "signal_a": "workout_day",
                "signal_b": "glucose_avg",
                "correlation": corr,
                "direction": "negative" if corr < 0 else "positive",
                "confidence": CorrelationService._confidence_count(len(summaries)),
                "interpretation": CorrelationService._interpret_workout_glucose(corr),
            })

        # 7. Protein intake ↔ Recovery score (next day)
        corr = CorrelationService._correlate_lagged(
            summaries, "protein_g", "recovery_score", lag=1
        )
        if corr is not None:
            results.append({
                "signal_a": "protein_g",
                "signal_b": "recovery_score_next_day",
                "correlation": corr,
                "direction": "positive" if corr > 0 else "negative",
                "confidence": CorrelationService._confidence_count(len(summaries) - 1),
                "interpretation": CorrelationService._interpret_protein_recovery(corr),
            })

        # 8. Protein intake ↔ Weekly weight change
        corr = CorrelationService._correlate_protein_weight(summaries)
        if corr is not None:
            results.append({
                "signal_a": "protein_intake",
                "signal_b": "weight_change",
                "correlation": corr,
                "direction": "negative" if corr < 0 else "positive",
                "confidence": "moderate",
                "interpretation": CorrelationService._interpret_protein_weight(corr),
            })

        # 9. Protein ratio ↔ Sleep quality
        corr = CorrelationService._correlate_fields(
            summaries, "protein_per_lb", "sleep_quality_score"
        )
        if corr is not None:
            results.append({
                "signal_a": "protein_per_lb",
                "signal_b": "sleep_quality",
                "correlation": corr,
                "direction": "positive" if corr > 0 else "negative",
                "confidence": CorrelationService._confidence(corr, summaries, "protein_per_lb", "sleep_quality_score"),
                "interpretation": CorrelationService._interpret_protein_sleep(corr),
            })

        # 10. Protein intake ↔ Skeletal muscle mass
        corr = CorrelationService._correlate_fields(
            summaries, "protein_g", "skeletal_muscle_mass"
        )
        if corr is not None:
            results.append({
                "signal_a": "protein_g",
                "signal_b": "skeletal_muscle_mass",
                "correlation": corr,
                "direction": "positive" if corr > 0 else "negative",
                "confidence": CorrelationService._confidence(corr, summaries, "protein_g", "skeletal_muscle_mass"),
                "interpretation": CorrelationService._interpret_protein_muscle(corr),
            })

        # 11. Protein per lb ↔ Body fat change (weekly)
        corr = CorrelationService._correlate_protein_fat_loss(summaries)
        if corr is not None:
            results.append({
                "signal_a": "protein_per_lb",
                "signal_b": "fat_loss_rate",
                "correlation": corr,
                "direction": "negative" if corr < 0 else "positive",
                "confidence": "moderate",
                "interpretation": CorrelationService._interpret_protein_fat_loss(corr),
            })

        # 12. Protein on workout days ↔ Next-day training load
        corr = CorrelationService._correlate_workout_protein_performance(summaries)
        if corr is not None:
            results.append({
                "signal_a": "workout_day_protein",
                "signal_b": "next_training_load",
                "correlation": corr,
                "direction": "positive" if corr > 0 else "negative",
                "confidence": CorrelationService._confidence_count(len(summaries)),
                "interpretation": CorrelationService._interpret_protein_performance(corr),
            })

        # Sort by absolute correlation strength
        results.sort(key=lambda x: abs(x["correlation"]), reverse=True)

        # Return top 3
        return results[:3]

    @staticmethod
    def _correlate_fields(summaries, field_a, field_b):
        """Correlate two fields from summaries (same day)."""
        pairs = []
        for s in summaries:
            a = getattr(s, field_a)
            b = getattr(s, field_b)
            if a is not None and b is not None:
                pairs.append((float(a), float(b)))

        if len(pairs) < 5:
            return None

        x_vals = [p[0] for p in pairs]
        y_vals = [p[1] for p in pairs]
        return _rank_correlation(x_vals, y_vals)

    @staticmethod
    def _correlate_lagged(summaries, field_a, field_b, lag=1):
        """Correlate field_a on day N with field_b on day N+lag."""
        pairs = []
        by_date = {s.summary_date: s for s in summaries}

        for s in summaries:
            lagged_date = s.summary_date + timedelta(days=lag)
            lagged = by_date.get(lagged_date)
            if lagged:
                a = getattr(s, field_a)
                b = getattr(lagged, field_b)
                if a is not None and b is not None:
                    pairs.append((float(a), float(b)))

        if len(pairs) < 5:
            return None

        x_vals = [p[0] for p in pairs]
        y_vals = [p[1] for p in pairs]
        return _rank_correlation(x_vals, y_vals)

    @staticmethod
    def _correlate_binary(summaries, bool_fn, numeric_field):
        """Correlate a boolean condition with a numeric field."""
        pairs = []
        for s in summaries:
            val = getattr(s, numeric_field)
            if val is not None:
                binary = 1 if bool_fn(s) else 0
                pairs.append((binary, float(val)))

        if len(pairs) < 5:
            return None

        x_vals = [p[0] for p in pairs]
        y_vals = [p[1] for p in pairs]

        # Check for variance in binary
        if len(set(x_vals)) < 2:
            return None

        return _rank_correlation(x_vals, y_vals)

    @staticmethod
    def _correlate_nutrition_weight(summaries):
        """Correlate nutrition tracking consistency with weight change direction."""
        # Group by week
        if len(summaries) < 14:
            return None

        weeks = []
        for i in range(0, len(summaries) - 6, 7):
            week = summaries[i:i + 7]
            logged = sum(1 for s in week if s.nutrition_logged)
            weights = [float(s.weight) for s in week if s.weight]
            if weights and len(weights) >= 2:
                weight_change = weights[-1] - weights[0]
                weeks.append((logged, weight_change))

        if len(weeks) < 3:
            return None

        x_vals = [w[0] for w in weeks]
        y_vals = [w[1] for w in weeks]
        return _rank_correlation(x_vals, y_vals)

    @staticmethod
    def _confidence(corr, summaries, field_a, field_b):
        """Determine confidence based on correlation strength and sample size."""
        count = sum(
            1 for s in summaries
            if getattr(s, field_a) is not None and getattr(s, field_b) is not None
        )
        return CorrelationService._confidence_count(count, corr)

    @staticmethod
    def _confidence_count(count, corr=None):
        """Confidence based on data point count."""
        if count >= 21 and (corr is None or abs(corr) >= 0.3):
            return "high"
        elif count >= 14:
            return "moderate"
        return "low"

    # --- Interpretation helpers ---

    @staticmethod
    def _interpret_sleep_glucose(corr):
        if corr < -0.2:
            return "More sleep is associated with lower glucose levels"
        elif corr > 0.2:
            return "Sleep duration and glucose move together (may need investigation)"
        return "No clear relationship between sleep duration and glucose"

    @staticmethod
    def _interpret_sleep_recovery(corr):
        if corr > 0.2:
            return "Better sleep leads to higher recovery scores the next day"
        elif corr < -0.2:
            return "Unexpected: more sleep associated with lower recovery"
        return "Sleep duration has minimal impact on next-day recovery"

    @staticmethod
    def _interpret_load_recovery(corr):
        if corr < -0.2:
            return "Heavy training days reduce next-day recovery (expected pattern)"
        elif corr > 0.2:
            return "Training load positively associated with recovery (may indicate adaptation)"
        return "Training load has minimal impact on next-day recovery"

    @staticmethod
    def _interpret_caffeine_sleep(corr):
        if corr < -0.2:
            return "Higher caffeine intake is associated with lower sleep quality"
        elif corr > 0.2:
            return "Caffeine and sleep quality move together (possibly caffeine after good sleep)"
        return "No clear caffeine-sleep quality relationship detected"

    @staticmethod
    def _interpret_nutrition_weight(corr):
        if corr < -0.2:
            return "Weeks with better nutrition tracking are associated with weight loss"
        elif corr > 0.2:
            return "Nutrition tracking and weight gain are correlated (may need review)"
        return "No clear link between tracking consistency and weight change"

    @staticmethod
    def _interpret_workout_glucose(corr):
        if corr < -0.2:
            return "Workout days are associated with lower glucose levels"
        elif corr > 0.2:
            return "Workout days show higher glucose (possible post-exercise liver glucose release)"
        return "No clear workout-glucose relationship detected"

    @staticmethod
    def _interpret_protein_recovery(corr):
        if corr > 0.2:
            return "Higher protein intake is associated with better next-day recovery"
        elif corr < -0.2:
            return "Unexpected: higher protein associated with lower recovery"
        return "No clear protein-recovery relationship detected"

    @staticmethod
    def _interpret_protein_weight(corr):
        if corr < -0.2:
            return "Higher protein weeks are associated with more weight loss (preserving muscle)"
        elif corr > 0.2:
            return "Higher protein weeks correlate with weight gain (possibly intentional muscle building)"
        return "No clear link between protein intake and weight change"

    @staticmethod
    def _interpret_protein_sleep(corr):
        if corr > 0.2:
            return "Higher protein per lb body weight is associated with better sleep quality"
        elif corr < -0.2:
            return "Higher protein may be affecting sleep quality negatively"
        return "No clear protein-sleep quality relationship detected"

    @staticmethod
    def _interpret_protein_muscle(corr):
        if corr > 0.2:
            return "Higher protein intake is associated with greater skeletal muscle mass"
        elif corr < -0.2:
            return "Unexpected: higher protein associated with lower muscle mass"
        return "No clear protein-muscle mass relationship detected"

    @staticmethod
    def _interpret_protein_fat_loss(corr):
        if corr < -0.2:
            return "Higher protein per lb is associated with body fat reduction"
        elif corr > 0.2:
            return "Higher protein correlates with body fat increase (possibly in surplus)"
        return "No clear protein-fat loss relationship detected"

    @staticmethod
    def _interpret_protein_performance(corr):
        if corr > 0.2:
            return "Higher protein on workout days supports greater next-day training output"
        elif corr < -0.2:
            return "Unexpected: higher workout-day protein associated with lower next-day performance"
        return "No clear protein-performance relationship detected"

    @staticmethod
    def _correlate_protein_fat_loss(summaries):
        """Correlate weekly avg protein per lb with body fat change direction."""
        if len(summaries) < 14:
            return None

        weeks = []
        for i in range(0, len(summaries) - 6, 7):
            week = summaries[i:i + 7]
            protein_per_lb_days = [
                float(s.protein_per_lb) for s in week
                if s.protein_per_lb is not None
            ]
            bf_days = [float(s.body_fat_pct) for s in week if s.body_fat_pct is not None]
            if protein_per_lb_days and bf_days and len(bf_days) >= 2:
                avg_ppl = sum(protein_per_lb_days) / len(protein_per_lb_days)
                bf_change = bf_days[-1] - bf_days[0]
                weeks.append((avg_ppl, bf_change))

        if len(weeks) < 3:
            return None

        x_vals = [w[0] for w in weeks]
        y_vals = [w[1] for w in weeks]
        return _rank_correlation(x_vals, y_vals)

    @staticmethod
    def _correlate_workout_protein_performance(summaries):
        """Correlate protein on workout days with next-day training load."""
        pairs = []
        by_date = {s.summary_date: s for s in summaries}

        for s in summaries:
            if not s.workout_count or s.workout_count == 0:
                continue
            if s.protein_g is None:
                continue
            # Look at next workout day's training load
            next_date = s.summary_date + timedelta(days=1)
            next_s = by_date.get(next_date)
            if next_s and next_s.training_load is not None:
                pairs.append((float(s.protein_g), float(next_s.training_load)))

        if len(pairs) < 5:
            return None

        x_vals = [p[0] for p in pairs]
        y_vals = [p[1] for p in pairs]
        return _rank_correlation(x_vals, y_vals)

    @staticmethod
    def _correlate_protein_weight(summaries):
        """Correlate weekly protein avg with weight change direction."""
        if len(summaries) < 14:
            return None

        weeks = []
        for i in range(0, len(summaries) - 6, 7):
            week = summaries[i:i + 7]
            protein_days = [float(s.protein_g) for s in week if s.protein_g]
            weights = [float(s.weight) for s in week if s.weight]
            if protein_days and weights and len(weights) >= 2:
                avg_protein = sum(protein_days) / len(protein_days)
                weight_change = weights[-1] - weights[0]
                weeks.append((avg_protein, weight_change))

        if len(weeks) < 3:
            return None

        x_vals = [w[0] for w in weeks]
        y_vals = [w[1] for w in weeks]
        return _rank_correlation(x_vals, y_vals)
