"""
Global Insight Engine (Part 4)

Generates DESCRIPTIVE insights only. Reads across all WLJ domains
through the Health Data Service Layer.

Allowed:
- Observational, pattern-based, neutral, encouraging insights
- Trend, consistency, gap, correlation types

NOT Allowed:
- Advice, recommendations, medical interpretation
- Risk assessment, diagnosis, prescriptions
- Judgment language (unsafe, dangerous, harmful, "you should")
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.health.models import InsightResult
from apps.health.services.health_data import HealthDataService

logger = logging.getLogger(__name__)

MIN_TREND_POINTS = 3
HIGH_CONFIDENCE_POINTS = 10


class InsightEngine:
    """
    Centralized insight generation service.

    Reads across Health (Labs, Vitals, Body Composition, Weight),
    Goals, Habits, Journal, and frequency patterns via the
    HealthDataService abstraction layer.

    All insights are descriptive and non-directive.
    """

    def __init__(self, user):
        self.user = user
        self.service = HealthDataService(user)
        self._insights = []

    def generate_insights(self):
        """Generate all insights and persist them. Returns count."""
        self._insights = []

        self._analyze_weight_trend()
        self._analyze_body_composition_trends()
        self._analyze_logging_gaps()
        self._analyze_weight_body_comp_correlation()
        self._analyze_goal_alignment()
        self._analyze_habit_consistency()
        self._analyze_journal_frequency()

        count = 0
        for insight_data in self._insights:
            InsightResult.objects.create(user=self.user, **insight_data)
            count += 1
        return count

    # Alias for backward compat with stub
    def refresh_insights(self):
        return self.generate_insights()

    # ------------------------------------------------------------------
    # Weight Trend
    # ------------------------------------------------------------------

    def _analyze_weight_trend(self):
        trend = self.service.get_metric_trend("weight", days=42)
        if len(trend) < MIN_TREND_POINTS:
            return

        values = [d["value"] for d in trend if d["value"] is not None]
        if len(values) < MIN_TREND_POINTS:
            return

        first_third = values[:len(values) // 3] or values[:1]
        last_third = values[-(len(values) // 3):] or values[-1:]
        avg_first = sum(first_third) / len(first_third)
        avg_last = sum(last_third) / len(last_third)
        change = avg_last - avg_first
        confidence = self._confidence_from_count(len(values))

        if abs(change) < 0.5:
            self._add_insight(
                "trend",
                f"Weight has remained relatively stable over the past 6 weeks, "
                f"averaging around {avg_last:.1f} lb.",
                ["weight"], confidence,
            )
        elif change < 0:
            self._add_insight(
                "trend",
                f"Weight trend has declined over 6 weeks, "
                f"from approximately {avg_first:.1f} lb to {avg_last:.1f} lb.",
                ["weight"], confidence,
            )
        else:
            self._add_insight(
                "trend",
                f"Weight trend has increased over 6 weeks, "
                f"from approximately {avg_first:.1f} lb to {avg_last:.1f} lb.",
                ["weight"], confidence,
            )

        # Extreme value contextual modeling (Part 5)
        if len(values) >= 2:
            days_span = (trend[-1]["date"] - trend[0]["date"]).days
            if days_span > 0:
                weekly_change = (change / days_span) * 7
                daily_cal_equiv = abs(weekly_change) * 3500 / 7
                if abs(weekly_change) > 2.0:
                    direction = "loss" if weekly_change < 0 else "gain"
                    self._add_insight(
                        "trend",
                        f"Recent weekly weight {direction} of approximately "
                        f"{abs(weekly_change):.1f} lb corresponds to roughly "
                        f"{daily_cal_equiv:.0f} calories per day, which is outside "
                        f"commonly referenced physiological modeling ranges.",
                        ["weight"], confidence,
                        metadata={"weekly_change_lb": round(weekly_change, 2),
                                  "daily_cal_equivalent": round(daily_cal_equiv, 0)},
                    )

    # ------------------------------------------------------------------
    # Body Composition Trends
    # ------------------------------------------------------------------

    def _analyze_body_composition_trends(self):
        metrics = self.service.get_body_comp_metrics_logged()
        for metric_name in metrics:
            trend = self.service.get_metric_trend(metric_name, days=42)
            if len(trend) < MIN_TREND_POINTS:
                continue

            values = [d["value"] for d in trend if d["value"] is not None]
            if len(values) < MIN_TREND_POINTS:
                continue

            first_val = values[0]
            last_val = values[-1]
            change = last_val - first_val
            confidence = self._confidence_from_count(len(values))

            from apps.health.models import BODY_COMPOSITION_METRIC_CHOICES
            display = dict(BODY_COMPOSITION_METRIC_CHOICES).get(metric_name, metric_name)
            unit = trend[-1].get("unit", "")
            unit_str = f" {unit}" if unit else ""

            threshold = 0.1 * abs(first_val) if first_val else 0
            if abs(change) < threshold:
                self._add_insight(
                    "trend",
                    f"{display} stable at approximately {last_val:.1f}{unit_str}.",
                    ["body_composition"], confidence,
                )
            elif change < 0:
                self._add_insight(
                    "trend",
                    f"{display} trending downward, "
                    f"from {first_val:.1f}{unit_str} to {last_val:.1f}{unit_str}.",
                    ["body_composition"], confidence,
                )
            else:
                self._add_insight(
                    "trend",
                    f"{display} trending upward, "
                    f"from {first_val:.1f}{unit_str} to {last_val:.1f}{unit_str}.",
                    ["body_composition"], confidence,
                )

    # ------------------------------------------------------------------
    # Logging Gaps
    # ------------------------------------------------------------------

    def _analyze_logging_gaps(self):
        weight_count = self.service.get_weight_entries_count(days=30)
        if weight_count == 0:
            latest = self.service.get_latest_metric("weight")
            if latest:
                self._add_insight(
                    "gap",
                    "No weight entries logged in the past 30 days.",
                    ["weight"], Decimal("0.95"),
                )

        bc_count = self.service.get_body_comp_entries_count(days=30)
        if bc_count == 0:
            metrics = self.service.get_body_comp_metrics_logged()
            if metrics:
                self._add_insight(
                    "gap",
                    "No body composition entries logged in the past 30 days.",
                    ["body_composition"], Decimal("0.95"),
                )

    # ------------------------------------------------------------------
    # Cross-Domain Correlation
    # ------------------------------------------------------------------

    def _analyze_weight_body_comp_correlation(self):
        weight_trend = self.service.get_metric_trend("weight", days=42)
        lean_trend = self.service.get_metric_trend("lean_mass", days=42)

        if len(weight_trend) < MIN_TREND_POINTS or len(lean_trend) < MIN_TREND_POINTS:
            return

        w_values = [d["value"] for d in weight_trend if d["value"]]
        l_values = [d["value"] for d in lean_trend if d["value"]]
        if not w_values or not l_values:
            return

        w_change = w_values[-1] - w_values[0]
        l_change = l_values[-1] - l_values[0]
        confidence = self._confidence_from_count(min(len(w_values), len(l_values)))

        if w_change < -1 and abs(l_change) < 1:
            self._add_insight(
                "correlation",
                "Lean mass stable during weight reduction.",
                ["weight", "body_composition"], confidence,
            )
        elif w_change < -1 and l_change < -1:
            self._add_insight(
                "correlation",
                "Both weight and lean mass have declined over this period.",
                ["weight", "body_composition"], confidence,
            )
        elif w_change > 1 and l_change > 1:
            self._add_insight(
                "correlation",
                "Both weight and lean mass have increased over this period.",
                ["weight", "body_composition"], confidence,
            )

    # ------------------------------------------------------------------
    # Goals
    # ------------------------------------------------------------------

    def _analyze_goal_alignment(self):
        try:
            from apps.purpose.models import HabitGoal
            active_goals = HabitGoal.objects.filter(
                user=self.user, status="active",
                life_domain__name__iexact="health",
            )
            for goal in active_goals[:3]:
                rate = goal.completion_rate
                if rate is not None:
                    if rate >= 80:
                        self._add_insight(
                            "consistency",
                            f"Goal \"{goal.title}\" has a {rate:.0f}% completion rate.",
                            ["goals"], Decimal("0.85"),
                        )
                    elif rate < 30 and goal.elapsed_days > 7:
                        self._add_insight(
                            "gap",
                            f"Goal \"{goal.title}\" has a {rate:.0f}% completion rate "
                            f"over {goal.elapsed_days} days.",
                            ["goals"], Decimal("0.80"),
                        )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Habits
    # ------------------------------------------------------------------

    def _analyze_habit_consistency(self):
        try:
            from apps.purpose.models import HabitGoal
            active_habits = HabitGoal.objects.filter(
                user=self.user, status="active",
            ).order_by("-created_at")[:5]

            streaks = []
            for habit in active_habits:
                streak = habit.current_streak
                if streak and streak >= 7:
                    streaks.append((habit.title, streak))

            if streaks:
                best = max(streaks, key=lambda s: s[1])
                self._add_insight(
                    "consistency",
                    f"Current streak of {best[1]} days on \"{best[0]}\".",
                    ["habits"], Decimal("0.90"),
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Journal
    # ------------------------------------------------------------------

    def _analyze_journal_frequency(self):
        try:
            from apps.journal.models import JournalEntry
            cutoff = timezone.now() - timedelta(days=30)
            count = JournalEntry.objects.filter(
                user=self.user, created_at__gte=cutoff
            ).count()

            if count == 0:
                total = JournalEntry.objects.filter(user=self.user).count()
                if total > 0:
                    self._add_insight(
                        "gap",
                        "No journal entries in the past 30 days.",
                        ["journal"], Decimal("0.90"),
                    )
            elif count >= 20:
                self._add_insight(
                    "consistency",
                    f"{count} journal entries in the past 30 days.",
                    ["journal"], Decimal("0.85"),
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_insight(self, insight_type, text, related_domains, confidence, metadata=None):
        self._insights.append({
            "insight_type": insight_type,
            "text": text,
            "related_domains": related_domains,
            "confidence_score": Decimal(str(confidence)),
            "generated_at": timezone.now(),
            "metadata": metadata or {},
        })

    def _confidence_from_count(self, count):
        if count >= HIGH_CONFIDENCE_POINTS:
            return Decimal("0.90")
        elif count >= MIN_TREND_POINTS:
            ratio = count / HIGH_CONFIDENCE_POINTS
            return Decimal(str(round(0.50 + (ratio * 0.40), 2)))
        return Decimal("0.30")
