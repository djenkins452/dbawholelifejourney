"""
IOCD — Observability Dashboard View.

Admin-only view displaying intelligence system metrics.
Staff users can view guidance effectiveness, prediction coverage,
delivery performance, engagement, quality, persona effectiveness,
and UAL v2 arbitration metrics.

Project: Whole Life Journey
Path: apps/core/ai_observability/views.py

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
from collections import Counter
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Avg, Count
from django.utils import timezone
from django.views.generic import TemplateView

from apps.core.ai_observability.observability_engine import (
    get_latest_snapshot,
    get_snapshot_history,
)

logger = logging.getLogger(__name__)


class ObservabilityDashboardView(
    LoginRequiredMixin, UserPassesTestMixin, TemplateView
):
    """
    Intelligence Observability Dashboard — staff-only.

    Displays system-wide intelligence metrics:
    1. Guidance Effectiveness
    2. Prediction Confidence & Coverage
    3. Delivery Performance
    4. User Engagement
    5. System Quality
    6. Persona Effectiveness
    7. UAL Confidence Distribution (v2)
    8. UAL Scenario Frequency (v2)
    9. UAL Capacity Trend (v2)
    10. UAL Weight Adjustments (v2)

    Plus 7-day trend indicators.
    """

    template_name = "intelligence/observability_dashboard.html"

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Latest snapshot
        context["snapshot"] = get_latest_snapshot()

        # 7-day history for trend
        history = list(get_snapshot_history(days=7))
        context["history"] = history

        # Compute trend indicators
        if context["snapshot"] and len(history) >= 2:
            context["trends"] = self._compute_trends(history)
        else:
            context["trends"] = {}

        # UAL v2 observability panels
        context["ual_metrics"] = self._get_ual_metrics()

        # Page metadata
        context["app_name"] = "intelligence"
        context["help_context_id"] = "INTELLIGENCE_OBSERVABILITY"
        context["page_title"] = "Intelligence Observability"

        return context

    def _get_ual_metrics(self) -> dict:
        """Gather UAL v2 + v2.1 metrics for dashboard panels."""
        try:
            from apps.core.ai_arbitration.models import (
                ArbitrationDecisionLog,
                DailyCapacityLog,
                InterventionResponseLog,
                RecentNudgeMemory,
                ScenarioHistory,
                WeightAdjustment,
            )

            now = timezone.now()
            seven_days_ago = now - timedelta(days=7)

            # 1. Confidence distribution (last 7 days)
            recent_decisions = ArbitrationDecisionLog.objects.filter(
                timestamp__gte=seven_days_ago,
            )
            confidence_counts = dict(
                recent_decisions.values_list("confidence_level")
                .annotate(count=Count("id"))
                .values_list("confidence_level", "count")
            )
            confidence_total = sum(confidence_counts.values()) or 1

            # 2. Scenario frequency (14 days)
            scenario_freq = dict(
                ScenarioHistory.objects.filter(
                    date__gte=(now - timedelta(days=14)).date(),
                ).values_list("dominant_scenario")
                .annotate(count=Count("id"))
                .values_list("dominant_scenario", "count")
            )

            # 3. Capacity trend (14 days, most recent per day)
            capacity_logs = list(
                DailyCapacityLog.objects.filter(
                    date__gte=(now - timedelta(days=14)).date(),
                ).order_by("date").values(
                    "date", "capacity_score", "capacity_state"
                )[:14]
            )
            # Convert dates to strings for template
            for log in capacity_logs:
                log["date_str"] = log["date"].strftime("%m/%d")

            # 4. Weight adjustment deltas (current offsets)
            weight_deltas = list(
                WeightAdjustment.objects.exclude(
                    adjustment_delta=0.0,
                ).values(
                    "scenario", "signal", "baseline_weight",
                    "adjustment_delta",
                ).order_by("-adjustment_delta")[:20]
            )

            # v2.1 Panel 1: Fatigue Score Distribution (7d)
            fatigue_distribution = self._get_fatigue_distribution(
                InterventionResponseLog, seven_days_ago
            )

            # v2.1 Panel 2: Nudge Collision Rate (12h window)
            nudge_collision_rate = self._get_nudge_collision_rate(
                RecentNudgeMemory, now
            )

            # v2.1 Panel 3: Capacity Volatility Indicator (14d)
            capacity_volatility = self._get_capacity_volatility(
                DailyCapacityLog, now
            )

            # v2.1 Panel 4: Pattern Tier 2 Trigger Count
            tier2_trigger_count = self._get_tier2_trigger_count(
                ScenarioHistory, now
            )

            return {
                "has_data": True,
                "confidence_distribution": {
                    "HIGH": confidence_counts.get("HIGH", 0),
                    "MODERATE": confidence_counts.get("MODERATE", 0),
                    "LOW": confidence_counts.get("LOW", 0),
                    "total": confidence_total,
                },
                "scenario_frequency": scenario_freq,
                "capacity_trend": capacity_logs,
                "weight_deltas": weight_deltas,
                "decisions_count_7d": sum(confidence_counts.values()),
                # v2.1 panels
                "fatigue_distribution": fatigue_distribution,
                "nudge_collision_rate": nudge_collision_rate,
                "capacity_volatility": capacity_volatility,
                "tier2_trigger_count": tier2_trigger_count,
            }

        except Exception as e:
            logger.debug("UAL metrics unavailable: %s", e)
            return {"has_data": False}

    def _get_fatigue_distribution(self, model, since) -> dict:
        """v2.1: Fatigue score distribution from intervention response logs."""
        try:
            from django.db.models import F, Sum

            logs = model.objects.filter(date__gte=since.date())
            agg = logs.aggregate(
                total_surfaced=Sum("surfaced_count"),
                total_complied=Sum("complied_count"),
                total_ignored=Sum("ignored_count"),
                total_overrode=Sum("overrode_count"),
            )
            total_surfaced = agg["total_surfaced"] or 0
            total_ignored = agg["total_ignored"] or 0
            total_complied = agg["total_complied"] or 0
            total_overrode = agg["total_overrode"] or 0

            # Per-scenario fatigue summary
            scenario_fatigue = []
            for row in logs.values("scenario").annotate(
                surfaced=Sum("surfaced_count"),
                ignored=Sum("ignored_count"),
            ).order_by("-ignored"):
                s = row["surfaced"] or 0
                i = row["ignored"] or 0
                ratio = round(i / s, 2) if s > 0 else 0
                scenario_fatigue.append({
                    "scenario": row["scenario"],
                    "surfaced": s,
                    "ignored": i,
                    "fatigue_ratio": ratio,
                })

            return {
                "total_surfaced": total_surfaced,
                "total_complied": total_complied,
                "total_ignored": total_ignored,
                "total_overrode": total_overrode,
                "ignore_rate": round(
                    total_ignored / total_surfaced, 2
                ) if total_surfaced > 0 else 0,
                "scenario_breakdown": scenario_fatigue[:10],
            }
        except Exception as e:
            logger.debug("Fatigue distribution unavailable: %s", e)
            return {}

    def _get_nudge_collision_rate(self, model, now) -> dict:
        """v2.1: Nudge collision rate from recent nudge memory."""
        try:
            cutoff_12h = now - timedelta(hours=12)
            recent = model.objects.filter(surfaced_at__gte=cutoff_12h)
            total = recent.count()

            # Count duplicated semantic tags
            tag_counts = Counter(
                recent.values_list("semantic_tag", flat=True)
            )
            collisions = sum(1 for c in tag_counts.values() if c > 1)
            unique_tags = len(tag_counts)

            return {
                "total_nudges_12h": total,
                "unique_tags": unique_tags,
                "collision_count": collisions,
                "collision_rate": round(
                    collisions / unique_tags, 2
                ) if unique_tags > 0 else 0,
            }
        except Exception as e:
            logger.debug("Nudge collision rate unavailable: %s", e)
            return {}

    def _get_capacity_volatility(self, model, now) -> dict:
        """v2.1: Capacity volatility indicator from daily capacity logs."""
        try:
            import math
            window = now - timedelta(days=14)
            scores = list(
                model.objects.filter(
                    date__gte=window.date(),
                ).values_list("capacity_score", flat=True)
            )
            if len(scores) < 2:
                return {"std_dev": 0, "volatile": False, "sample_count": 0}

            mean = sum(scores) / len(scores)
            variance = sum((x - mean) ** 2 for x in scores) / len(scores)
            std_dev = math.sqrt(variance)

            return {
                "std_dev": round(std_dev, 4),
                "volatile": std_dev > 0.25,
                "sample_count": len(scores),
                "mean_score": round(mean, 3),
            }
        except Exception as e:
            logger.debug("Capacity volatility unavailable: %s", e)
            return {}

    def _get_tier2_trigger_count(self, model, now) -> dict:
        """v2.1: Count Tier 2 pattern triggers from scenario history."""
        try:
            from apps.core.ai_arbitration.pattern_analyzer import TIER2_RULES

            triggers = []
            for scenario, threshold, window, label in TIER2_RULES:
                window_start = (now - timedelta(days=window)).date()
                count = model.objects.filter(
                    date__gte=window_start,
                    dominant_scenario=scenario,
                ).count()
                triggered = count >= threshold
                triggers.append({
                    "pattern": label,
                    "scenario": scenario,
                    "count": count,
                    "threshold": threshold,
                    "window_days": window,
                    "triggered": triggered,
                })

            active_count = sum(1 for t in triggers if t["triggered"])

            return {
                "triggers": triggers,
                "active_count": active_count,
            }
        except Exception as e:
            logger.debug("Tier 2 trigger count unavailable: %s", e)
            return {}

    def _compute_trends(self, history):
        """
        Compute trend arrows for key metrics by comparing
        latest snapshot to 7-day average.

        Returns:
            dict mapping metric_name → "up"/"down"/"stable"
        """
        if len(history) < 2:
            return {}

        latest = history[0]
        older = history[1:]

        trends = {}

        # Guidance action rate trend
        if older:
            avg_action_rate = sum(
                s.guidance_action_rate for s in older
            ) / len(older)
            trends["guidance_action_rate"] = self._trend_direction(
                latest.guidance_action_rate, avg_action_rate
            )

        # Delivery success rate trend
        if older:
            avg_delivery_rate = sum(
                s.deliveries_success_rate for s in older
            ) / len(older)
            trends["deliveries_success_rate"] = self._trend_direction(
                latest.deliveries_success_rate, avg_delivery_rate
            )

        # Usefulness score trend
        if older:
            avg_usefulness = sum(
                s.avg_usefulness_score for s in older
            ) / len(older)
            trends["avg_usefulness_score"] = self._trend_direction(
                latest.avg_usefulness_score, avg_usefulness
            )

        # Responsiveness trend
        if older:
            avg_responsiveness = sum(
                s.avg_responsiveness_score for s in older
            ) / len(older)
            trends["avg_responsiveness_score"] = self._trend_direction(
                latest.avg_responsiveness_score, avg_responsiveness
            )

        return trends

    @staticmethod
    def _trend_direction(current, average, threshold=0.02):
        """
        Compare current value to average.
        Returns "up", "down", or "stable".
        """
        diff = current - average
        if diff > threshold:
            return "up"
        elif diff < -threshold:
            return "down"
        return "stable"
