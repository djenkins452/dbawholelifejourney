"""
Body Composition Insight Rules.
"""

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import days_since, get_time_window
from apps.core.ai_insights.rule_registry import register


@register
class MissingBodyCompRule(BaseInsightRule):
    rule_name = "missing_body_comp"
    module = "health"
    insight_type = "missing_body_comp"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        from apps.health.models import BodyCompositionEntry

        latest = (
            BodyCompositionEntry.objects.filter(user=user, status="active")
            .order_by("-measurement_date")
            .first()
        )

        if not latest:
            return []

        gap_days = days_since(latest.created_at)
        if gap_days is None or gap_days < 30:
            return []

        window_start, window_end = get_time_window(days=gap_days)

        return [
            {
                "severity": "info",
                "title": f"No body composition entry in {gap_days} days",
                "message": (
                    f"Your last body composition measurement was {gap_days} days ago. "
                    f"Regular measurements help track progress beyond the scale."
                ),
                "confidence_score": 0.8,
                "explain_why": (
                    f"Rule: {self.rule_name}. Last entry: "
                    f"{latest.measurement_date}. Gap: {gap_days} days (threshold: 30)."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "last_entry_id": latest.id,
                    "last_entry_date": str(latest.measurement_date),
                    "gap_days": gap_days,
                },
                "dedupe_key": build_dedupe_key(
                    user.id, self.insight_type,
                    window_start.date(), window_end.date(),
                    [latest.id],
                ),
            }
        ]


@register
class BodyFatChangeRule(BaseInsightRule):
    rule_name = "body_fat_change"
    module = "health"
    insight_type = "body_fat_change"

    def applies(self, user, event):
        return event.get("module") == "health" and event.get("action") in (
            "log_body_comp",
            "scheduled_check",
        )

    def evaluate(self, user, event):
        from apps.health.models import BodyCompositionEntry

        window_start, window_end = get_time_window(days=60)
        entries = list(
            BodyCompositionEntry.objects.filter(
                user=user,
                metric_name="body_fat_pct",
                measurement_date__gte=window_start.date(),
                measurement_date__lte=window_end.date(),
                status="active",
            )
            .order_by("measurement_date")
            .values_list("id", "measurement_date", "value")
        )

        if len(entries) < 2:
            return []

        first_val = float(entries[0][2])
        last_val = float(entries[-1][2])
        change = last_val - first_val

        if abs(change) < 2.0:
            return []

        record_ids = [e[0] for e in entries]
        direction = "decreased" if change < 0 else "increased"
        severity = "positive" if change < 0 else "warning"

        return [
            {
                "severity": severity,
                "title": f"Body fat {direction} by {abs(change):.1f}%",
                "message": (
                    f"Your body fat percentage has {direction} from "
                    f"{first_val:.1f}% to {last_val:.1f}% over the last 60 days "
                    f"({len(entries)} measurements)."
                ),
                "confidence_score": 0.8,
                "explain_why": (
                    f"Rule: {self.rule_name}. 60-day window. {len(entries)} entries. "
                    f"Change: {change:+.1f}% (threshold: 2.0)."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "window_start": str(window_start.date()),
                    "window_end": str(window_end.date()),
                    "record_ids": record_ids,
                    "first_value": first_val,
                    "last_value": last_val,
                    "change": round(change, 1),
                },
                "dedupe_key": build_dedupe_key(
                    user.id, self.insight_type,
                    window_start.date(), window_end.date(),
                    record_ids,
                ),
            }
        ]
