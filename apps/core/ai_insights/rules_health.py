"""
Health Insight Rules — Weight trends and missing logging detection.
"""

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import (
    compute_simple_trend,
    days_since,
    get_time_window,
    requires_min_points,
)
from apps.core.ai_insights.rule_registry import register

MEDICAL_DISCLAIMER = (
    "\n\n_Educational information only — not medical advice. "
    "Please consult your healthcare provider for medical guidance._"
)


@register
class WeightTrendUpRule(BaseInsightRule):
    rule_name = "weight_trend_up"
    module = "health"
    insight_type = "weight_trend_up"

    def applies(self, user, event):
        return event.get("module") == "health" and event.get("action") in (
            "update_weight",
            "log_weight",
            "scheduled_check",
        )

    def evaluate(self, user, event):
        from apps.health.models import WeightEntry

        window_start, window_end = get_time_window(days=14)
        entries = (
            WeightEntry.objects.filter(
                user=user,
                recorded_at__gte=window_start,
                recorded_at__lte=window_end,
                status="active",
            )
            .order_by("recorded_at")
            .values_list("id", "recorded_at", "value", "unit")
        )

        entries_list = list(entries)
        if not requires_min_points(entries_list, 2):
            return []

        values_with_dates = [(e[1], float(e[2])) for e in entries_list]
        trend = compute_simple_trend(values_with_dates)

        if not trend or trend["direction"] != "up" or trend["net_change"] < 1:
            return []

        record_ids = [e[0] for e in entries_list]
        unit = entries_list[0][3]

        return [
            {
                "severity": "warning",
                "title": f"Weight trending up ({trend['net_change']:+.1f} {unit})",
                "message": (
                    f"Over the last 14 days, your weight has increased from "
                    f"{trend['first_value']:.1f} to {trend['last_value']:.1f} {unit} "
                    f"({trend['net_change']:+.1f} {unit} across {trend['count']} entries)."
                    f"{MEDICAL_DISCLAIMER}"
                ),
                "confidence_score": 0.85,
                "explain_why": (
                    f"Rule: {self.rule_name}. 14-day window from {window_start.date()} "
                    f"to {window_end.date()}. {trend['count']} entries show net change "
                    f"of {trend['net_change']:+.1f} {unit} (threshold: +1)."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "window_start": str(window_start.date()),
                    "window_end": str(window_end.date()),
                    "record_ids": record_ids,
                    "first_value": trend["first_value"],
                    "last_value": trend["last_value"],
                    "net_change": trend["net_change"],
                    "entry_count": trend["count"],
                },
                "dedupe_key": build_dedupe_key(
                    user.id, self.insight_type,
                    window_start.date(), window_end.date(),
                    record_ids,
                ),
            }
        ]


@register
class WeightTrendDownRule(BaseInsightRule):
    rule_name = "weight_trend_down"
    module = "health"
    insight_type = "weight_trend_down"

    def applies(self, user, event):
        return event.get("module") == "health" and event.get("action") in (
            "update_weight",
            "log_weight",
            "scheduled_check",
        )

    def evaluate(self, user, event):
        from apps.health.models import WeightEntry

        window_start, window_end = get_time_window(days=14)
        entries = (
            WeightEntry.objects.filter(
                user=user,
                recorded_at__gte=window_start,
                recorded_at__lte=window_end,
                status="active",
            )
            .order_by("recorded_at")
            .values_list("id", "recorded_at", "value", "unit")
        )

        entries_list = list(entries)
        if not requires_min_points(entries_list, 2):
            return []

        values_with_dates = [(e[1], float(e[2])) for e in entries_list]
        trend = compute_simple_trend(values_with_dates)

        if not trend or trend["direction"] != "down" or trend["net_change"] > -1:
            return []

        record_ids = [e[0] for e in entries_list]
        unit = entries_list[0][3]

        return [
            {
                "severity": "positive",
                "title": f"Weight trending down ({trend['net_change']:+.1f} {unit})",
                "message": (
                    f"Great progress! Over the last 14 days, your weight has decreased "
                    f"from {trend['first_value']:.1f} to {trend['last_value']:.1f} {unit} "
                    f"({trend['net_change']:+.1f} {unit} across {trend['count']} entries)."
                ),
                "confidence_score": 0.85,
                "explain_why": (
                    f"Rule: {self.rule_name}. 14-day window. {trend['count']} entries "
                    f"show net change of {trend['net_change']:+.1f} {unit}."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "window_start": str(window_start.date()),
                    "window_end": str(window_end.date()),
                    "record_ids": record_ids,
                    "net_change": trend["net_change"],
                    "entry_count": trend["count"],
                },
                "dedupe_key": build_dedupe_key(
                    user.id, self.insight_type,
                    window_start.date(), window_end.date(),
                    record_ids,
                ),
            }
        ]


@register
class MissingWeightLoggingRule(BaseInsightRule):
    rule_name = "missing_weight_logging"
    module = "health"
    insight_type = "missing_weight_logging"
    min_confidence_to_notify = 0.9

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        from apps.health.models import WeightEntry

        latest = (
            WeightEntry.objects.filter(user=user, status="active")
            .order_by("-recorded_at")
            .first()
        )

        if not latest:
            return []

        gap_days = days_since(latest.recorded_at)
        if gap_days is None or gap_days < 7:
            return []

        window_start, window_end = get_time_window(days=gap_days)

        return [
            {
                "severity": "info",
                "title": f"No weight entry in {gap_days} days",
                "message": (
                    f"Your last weight entry was {gap_days} days ago "
                    f"on {latest.recorded_at.strftime('%B %d, %Y')}. "
                    f"Regular tracking helps identify trends."
                ),
                "confidence_score": 0.9,
                "explain_why": (
                    f"Rule: {self.rule_name}. Last entry: {latest.recorded_at.date()}. "
                    f"Gap: {gap_days} days (threshold: 7)."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "last_entry_id": latest.id,
                    "last_entry_date": str(latest.recorded_at.date()),
                    "gap_days": gap_days,
                },
                "dedupe_key": build_dedupe_key(
                    user.id, self.insight_type,
                    window_start.date(), window_end.date(),
                    [latest.id],
                ),
            }
        ]
