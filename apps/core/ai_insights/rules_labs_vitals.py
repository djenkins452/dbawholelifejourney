"""
Labs & Vitals Insight Rules — Out-of-range detection (no diagnosis).
"""

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import get_time_window
from apps.core.ai_insights.rule_registry import register

MEDICAL_DISCLAIMER = (
    "\n\n_Educational information only — not medical advice. "
    "Please consult your healthcare provider for medical guidance._"
)


@register
class RepeatedOutOfRangeRule(BaseInsightRule):
    rule_name = "repeated_out_of_range"
    module = "medical"
    insight_type = "repeated_out_of_range"

    def applies(self, user, event):
        return event.get("module") == "medical" or event.get(
            "event_type"
        ) == "scheduled_check"

    def evaluate(self, user, event):
        from apps.medical.models import LabResult

        window_start, window_end = get_time_window(days=30)
        abnormal_results = list(
            LabResult.objects.filter(
                user=user,
                collected_at__gte=window_start,
                collected_at__lte=window_end,
                abnormal_flag__in=["L", "H", "LL", "HH"],
                status="active",
            )
            .values("raw_test_name", "abnormal_flag", "id", "collected_at", "value_text")
            .order_by("raw_test_name", "collected_at")
        )

        if not abnormal_results:
            return []

        # Group by test name
        grouped = {}
        for r in abnormal_results:
            name = r["raw_test_name"]
            if name not in grouped:
                grouped[name] = []
            grouped[name].append(r)

        insights = []
        for test_name, results in grouped.items():
            if len(results) < 2:
                continue

            record_ids = [r["id"] for r in results]
            dates = [str(r["collected_at"].date()) if r["collected_at"] else "unknown" for r in results]
            values = [r["value_text"] for r in results]

            insights.append(
                {
                    "severity": "warning",
                    "title": f"{test_name} out of range {len(results)} times",
                    "message": (
                        f"Your {test_name} has been flagged out of range "
                        f"{len(results)} times in the last 30 days "
                        f"(dates: {', '.join(dates)})."
                        f"{MEDICAL_DISCLAIMER}"
                    ),
                    "confidence_score": 0.85,
                    "explain_why": (
                        f"Rule: {self.rule_name}. 30-day window. {test_name} flagged "
                        f"'{results[0]['abnormal_flag']}' on {len(results)} occasions."
                    ),
                    "evidence": {
                        "rule_name": self.rule_name,
                        "test_name": test_name,
                        "record_ids": record_ids,
                        "dates": dates,
                        "values": values,
                        "flags": [r["abnormal_flag"] for r in results],
                    },
                    "dedupe_key": build_dedupe_key(
                        user.id,
                        f"{self.insight_type}_{test_name}",
                        window_start.date(),
                        window_end.date(),
                        record_ids,
                    ),
                }
            )

        return insights
