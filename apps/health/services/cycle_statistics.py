"""
Cycle Statistics Service

Provides comprehensive cycle statistics, pattern analysis, and correlations
for cycle tracking data.

Key Features:
- Average cycle and period length calculations
- Symptom frequency analysis
- Mood by cycle phase correlations
- Cycle regularity scoring
- Trend detection (longer/shorter cycles over time)

Usage:
    from apps.health.services.cycle_statistics import CycleStatisticsService

    service = CycleStatisticsService(user)
    stats = service.get_summary()
"""

from collections import Counter
from datetime import date, timedelta
from statistics import mean, stdev
from typing import Optional

from django.db.models import Count
from django.utils import timezone

from ..models import (
    CYCLE_MOOD_CHOICES,
    CYCLE_SYMPTOM_CHOICES,
    Cycle,
    CycleDailyLog,
    CycleSettings,
)
from .cycle_phase import get_phase_by_day


class CycleStatisticsService:
    """
    Service for calculating cycle statistics and correlations.

    Provides comprehensive analytics on menstrual cycle data including
    averages, frequencies, trends, and phase correlations.
    """

    # Default number of cycles to analyze
    DEFAULT_CYCLE_COUNT = 6

    # Minimum cycles needed for trend analysis
    MIN_CYCLES_FOR_TRENDS = 4

    # Regularity score thresholds (std dev in days)
    EXCELLENT_REGULARITY_STD = 2.0
    GOOD_REGULARITY_STD = 4.0
    FAIR_REGULARITY_STD = 6.0

    def __init__(self, user):
        """
        Initialize the statistics service for a specific user.

        Args:
            user: The User instance to calculate statistics for
        """
        self.user = user
        self._settings = None

    @property
    def settings(self) -> Optional[CycleSettings]:
        """Get user's cycle settings (cached)."""
        if self._settings is None:
            try:
                self._settings = CycleSettings.objects.get(user=self.user)
            except CycleSettings.DoesNotExist:
                pass
        return self._settings

    def get_average_cycle_length(
        self, num_cycles: Optional[int] = None, months: Optional[int] = None
    ) -> Optional[dict]:
        """
        Calculate average cycle length over a configurable period.

        Args:
            num_cycles: Number of recent cycles to analyze (default: 6)
            months: Alternatively, analyze cycles from last N months

        Returns:
            Dictionary with average, min, max, and count, or None if no data
        """
        query = Cycle.objects.filter(
            user=self.user,
            end_date__isnull=False,  # Only completed cycles
        ).order_by("-start_date")

        if months:
            cutoff_date = timezone.now().date() - timedelta(days=months * 30)
            query = query.filter(start_date__gte=cutoff_date)
        elif num_cycles:
            query = query[:num_cycles]
        else:
            query = query[: self.DEFAULT_CYCLE_COUNT]

        cycles = list(query)
        lengths = [c.cycle_length for c in cycles if c.cycle_length is not None]

        if not lengths:
            return None

        return {
            "average": round(mean(lengths), 1),
            "min": min(lengths),
            "max": max(lengths),
            "count": len(lengths),
            "std_dev": round(stdev(lengths), 1) if len(lengths) > 1 else 0,
        }

    def get_average_period_length(
        self, num_cycles: Optional[int] = None, months: Optional[int] = None
    ) -> Optional[dict]:
        """
        Calculate average period length over a configurable period.

        Args:
            num_cycles: Number of recent cycles to analyze (default: 6)
            months: Alternatively, analyze cycles from last N months

        Returns:
            Dictionary with average, min, max, and count, or None if no data
        """
        query = Cycle.objects.filter(
            user=self.user,
            period_end_date__isnull=False,
        ).order_by("-start_date")

        if months:
            cutoff_date = timezone.now().date() - timedelta(days=months * 30)
            query = query.filter(start_date__gte=cutoff_date)
        elif num_cycles:
            query = query[:num_cycles]
        else:
            query = query[: self.DEFAULT_CYCLE_COUNT]

        cycles = list(query)
        lengths = [c.period_length for c in cycles if c.period_length is not None]

        if not lengths:
            return None

        return {
            "average": round(mean(lengths), 1),
            "min": min(lengths),
            "max": max(lengths),
            "count": len(lengths),
        }

    def get_symptom_frequency(
        self, months: int = 3
    ) -> list[dict]:
        """
        Get symptom frequency counts over a time period.

        Args:
            months: Number of months to analyze (default: 3)

        Returns:
            List of dicts with symptom name, count, and percentage, sorted by frequency
        """
        cutoff_date = timezone.now().date() - timedelta(days=months * 30)

        logs = CycleDailyLog.objects.filter(
            user=self.user,
            log_date__gte=cutoff_date,
        )

        # Count all symptoms
        symptom_counts = Counter()
        total_logs = 0

        for log in logs:
            total_logs += 1
            for symptom in log.symptoms:
                symptom_counts[symptom] += 1

        if total_logs == 0:
            return []

        # Build result with display names
        symptom_map = dict(CYCLE_SYMPTOM_CHOICES)
        result = []

        for symptom, count in symptom_counts.most_common():
            result.append({
                "symptom": symptom,
                "display_name": symptom_map.get(symptom, symptom),
                "count": count,
                "percentage": round((count / total_logs) * 100, 1),
            })

        return result

    def get_mood_by_cycle_phase(
        self, months: int = 3
    ) -> dict:
        """
        Correlate moods with cycle phases.

        Analyzes which moods are most common during each cycle phase.

        Args:
            months: Number of months to analyze (default: 3)

        Returns:
            Dictionary mapping phase names to mood distributions
        """
        cutoff_date = timezone.now().date() - timedelta(days=months * 30)

        logs = CycleDailyLog.objects.filter(
            user=self.user,
            log_date__gte=cutoff_date,
            mood__isnull=False,
        ).exclude(mood="")

        # Get cycle length for phase calculation
        cycle_length = 28
        if self.settings:
            cycle_length = self.settings.average_cycle_length

        # Get all cycles in the period for phase mapping
        cycles = list(
            Cycle.objects.filter(
                user=self.user,
                start_date__lte=timezone.now().date(),
            ).order_by("-start_date")
        )

        # Build phase -> mood mapping
        phase_moods = {
            "menstrual": Counter(),
            "follicular": Counter(),
            "ovulation": Counter(),
            "luteal": Counter(),
        }

        mood_map = dict(CYCLE_MOOD_CHOICES)

        for log in logs:
            # Find which cycle this log belongs to
            log_cycle = None
            for cycle in cycles:
                if cycle.start_date <= log.log_date:
                    if cycle.end_date is None or log.log_date <= cycle.end_date:
                        log_cycle = cycle
                        break

            if not log_cycle:
                continue

            # Calculate cycle day and phase
            cycle_day = (log.log_date - log_cycle.start_date).days + 1
            phase_info = get_phase_by_day(cycle_day, cycle_length)

            if phase_info and phase_info["name"] in phase_moods:
                phase_moods[phase_info["name"]][log.mood] += 1

        # Convert to result format
        result = {}
        for phase, mood_counts in phase_moods.items():
            if not mood_counts:
                result[phase] = {"moods": [], "dominant_mood": None}
                continue

            total = sum(mood_counts.values())
            moods = [
                {
                    "mood": mood,
                    "display_name": mood_map.get(mood, mood),
                    "count": count,
                    "percentage": round((count / total) * 100, 1),
                }
                for mood, count in mood_counts.most_common()
            ]

            result[phase] = {
                "moods": moods,
                "dominant_mood": moods[0]["display_name"] if moods else None,
                "total_entries": total,
            }

        return result

    def get_cycle_regularity_score(
        self, num_cycles: Optional[int] = None
    ) -> Optional[dict]:
        """
        Calculate cycle regularity score (0-100) based on standard deviation.

        Lower standard deviation = higher regularity score.

        Args:
            num_cycles: Number of cycles to analyze (default: 6)

        Returns:
            Dictionary with score, rating, and statistics, or None if insufficient data
        """
        cycles_to_check = num_cycles or self.DEFAULT_CYCLE_COUNT

        cycles = Cycle.objects.filter(
            user=self.user,
            end_date__isnull=False,
        ).order_by("-start_date")[:cycles_to_check]

        lengths = [c.cycle_length for c in cycles if c.cycle_length is not None]

        if len(lengths) < 2:
            return None

        std_dev = stdev(lengths)

        # Calculate score (0-100)
        # std_dev of 0 = 100, std_dev of 10 = 0
        score = max(0, min(100, round(100 - (std_dev * 10))))

        # Determine rating
        if std_dev <= self.EXCELLENT_REGULARITY_STD:
            rating = "excellent"
            description = "Your cycles are very regular"
        elif std_dev <= self.GOOD_REGULARITY_STD:
            rating = "good"
            description = "Your cycles are fairly regular"
        elif std_dev <= self.FAIR_REGULARITY_STD:
            rating = "fair"
            description = "Your cycles show some variation"
        else:
            rating = "irregular"
            description = "Your cycles are irregular"

        return {
            "score": score,
            "rating": rating,
            "description": description,
            "std_dev": round(std_dev, 1),
            "cycles_analyzed": len(lengths),
        }

    def get_trends(self, num_cycles: Optional[int] = None) -> Optional[dict]:
        """
        Detect if cycles are getting longer or shorter over time.

        Uses linear regression to detect trends.

        Args:
            num_cycles: Number of cycles to analyze (default: 6)

        Returns:
            Dictionary with trend direction and magnitude, or None if insufficient data
        """
        cycles_to_check = num_cycles or self.DEFAULT_CYCLE_COUNT

        if cycles_to_check < self.MIN_CYCLES_FOR_TRENDS:
            cycles_to_check = self.MIN_CYCLES_FOR_TRENDS

        cycles = list(
            Cycle.objects.filter(
                user=self.user,
                end_date__isnull=False,
            ).order_by("start_date")[:cycles_to_check]
        )

        lengths = [c.cycle_length for c in cycles if c.cycle_length is not None]

        if len(lengths) < self.MIN_CYCLES_FOR_TRENDS:
            return None

        # Simple linear regression
        n = len(lengths)
        x_mean = (n - 1) / 2
        y_mean = mean(lengths)

        numerator = sum(
            (i - x_mean) * (lengths[i] - y_mean) for i in range(n)
        )
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            slope = 0
        else:
            slope = numerator / denominator

        # Determine trend
        if abs(slope) < 0.5:
            trend = "stable"
            description = "Your cycle length is stable"
        elif slope > 0:
            trend = "lengthening"
            description = f"Your cycles are getting longer (about {abs(slope):.1f} days per cycle)"
        else:
            trend = "shortening"
            description = f"Your cycles are getting shorter (about {abs(slope):.1f} days per cycle)"

        # Calculate period trend separately
        period_lengths = [c.period_length for c in cycles if c.period_length is not None]
        period_trend = None

        if len(period_lengths) >= self.MIN_CYCLES_FOR_TRENDS:
            p_n = len(period_lengths)
            p_x_mean = (p_n - 1) / 2
            p_y_mean = mean(period_lengths)

            p_numerator = sum(
                (i - p_x_mean) * (period_lengths[i] - p_y_mean) for i in range(p_n)
            )
            p_denominator = sum((i - p_x_mean) ** 2 for i in range(p_n))

            if p_denominator != 0:
                p_slope = p_numerator / p_denominator
                if abs(p_slope) < 0.3:
                    period_trend = "stable"
                elif p_slope > 0:
                    period_trend = "lengthening"
                else:
                    period_trend = "shortening"

        return {
            "cycle_trend": trend,
            "cycle_description": description,
            "cycle_slope": round(slope, 2),
            "period_trend": period_trend,
            "cycles_analyzed": n,
            "oldest_cycle_date": cycles[0].start_date.isoformat() if cycles else None,
            "newest_cycle_date": cycles[-1].start_date.isoformat() if cycles else None,
        }

    def get_summary(self) -> dict:
        """
        Get a comprehensive summary of all statistics.

        Returns:
            Dictionary with all available statistics
        """
        return {
            "average_cycle_length": self.get_average_cycle_length(),
            "average_period_length": self.get_average_period_length(),
            "regularity_score": self.get_cycle_regularity_score(),
            "trends": self.get_trends(),
            "symptom_frequency": self.get_symptom_frequency(months=3),
            "mood_by_phase": self.get_mood_by_cycle_phase(months=3),
            "generated_at": timezone.now().isoformat(),
        }
