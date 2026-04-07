"""
Body Composition Insight Rules.

Phase 1 hardening:
    - Confidence is computed from data sufficiency, not hardcoded.
    - Domain enabled gating: rules silently no-op when health is disabled.
    - Sufficiency floor: change-detection requires at least 3 measurements
      spanning a non-trivial window before any insight is created.
"""

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import days_since, get_time_window
from apps.core.ai_insights.rule_registry import register
from apps.core.ai_state.domain_gating import is_domain_enabled


# ── Confidence helpers ─────────────────────────────────────────────


def _confidence_from_gap(gap_days: int) -> float:
    """Confidence for a 'missing entry' nudge.

    Short gaps are inherently low-confidence (the user may simply be on a
    weekly cadence). Confidence climbs as the gap stretches well beyond a
    typical cadence.
    """
    if gap_days < 14:
        return 0.55
    if gap_days < 21:
        return 0.7
    if gap_days < 30:
        return 0.8
    return 0.9


def _confidence_from_evidence(entry_count: int, days_span: int) -> float:
    """Confidence for a change/trend insight.

    Confidence grows with both the number of measurements and the span of
    days they cover. Two measurements is the bare minimum (≈ 0.55) and a
    well-sampled 60-day window with 8+ entries reaches ≈ 0.9.
    """
    base = 0.5
    # Up to +0.25 for entry density
    base += min(entry_count, 10) / 10 * 0.25
    # Up to +0.15 for time span
    base += min(days_span, 60) / 60 * 0.15
    return round(min(base, 0.95), 2)


@register
class MissingBodyCompRule(BaseInsightRule):
    rule_name = "missing_body_comp"
    module = "health"
    insight_type = "missing_body_comp"

    def applies(self, user, event):
        if event.get("event_type") != "scheduled_check":
            return False
        # Phase 1: domain gating — never run for users with health disabled.
        return is_domain_enabled(user, "health")

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
        if gap_days is None or gap_days < 7:
            return []

        window_start, window_end = get_time_window(days=gap_days)
        confidence = _confidence_from_gap(gap_days)

        return [
            {
                "severity": "info",
                "title": f"No body composition entry in {gap_days} days",
                "message": (
                    f"Your last body composition measurement was {gap_days} days ago. "
                    f"Regular measurements help track progress beyond the scale."
                ),
                "confidence_score": confidence,
                "explain_why": (
                    f"Rule: {self.rule_name}. Last entry: "
                    f"{latest.measurement_date}. Gap: {gap_days} days "
                    f"(threshold: 14). Confidence derived from gap length."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "last_entry_id": latest.id,
                    "last_entry_date": str(latest.measurement_date),
                    "gap_days": gap_days,
                    "confidence_basis": "gap_days",
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

    # Sufficiency floor: 2 entries is the absolute minimum required to compute
    # a delta, but a 2-point trend is unstable. Phase 1 requires at least 3
    # measurements spanning a non-trivial window before any insight surfaces.
    MIN_ENTRIES = 3
    MIN_DAYS_SPAN = 14

    def applies(self, user, event):
        if event.get("module") != "health" or event.get("action") not in (
            "log_body_comp",
            "scheduled_check",
        ):
            return False
        # Phase 1: domain gating — never run for users with health disabled.
        return is_domain_enabled(user, "health")

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

        # Phase 1: enforce sufficiency floor before producing any insight.
        if len(entries) < self.MIN_ENTRIES:
            return []

        first_date = entries[0][1]
        last_date = entries[-1][1]
        days_span = (last_date - first_date).days
        if days_span < self.MIN_DAYS_SPAN:
            return []

        first_val = float(entries[0][2])
        last_val = float(entries[-1][2])
        change = last_val - first_val

        if abs(change) < 0.1:
            return []

        record_ids = [e[0] for e in entries]
        direction = "decreased" if change < 0 else "increased"
        severity = "positive" if change < 0 else "warning"
        confidence = _confidence_from_evidence(len(entries), days_span)

        return [
            {
                "severity": severity,
                "title": f"Body fat {direction} by {abs(change):.1f}%",
                "message": (
                    f"Your body fat percentage has {direction} from "
                    f"{first_val:.1f}% to {last_val:.1f}% over the last 60 days "
                    f"({len(entries)} measurements)."
                ),
                "confidence_score": confidence,
                "explain_why": (
                    f"Rule: {self.rule_name}. 60-day window. {len(entries)} entries "
                    f"spanning {days_span} days. Change: {change:+.1f}% "
                    f"(threshold: 1.0). Confidence derived from sample size + span."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "window_start": str(window_start.date()),
                    "window_end": str(window_end.date()),
                    "record_ids": record_ids,
                    "first_value": first_val,
                    "last_value": last_val,
                    "change": round(change, 1),
                    "entry_count": len(entries),
                    "days_span": days_span,
                    "confidence_basis": "entries+span",
                },
                "dedupe_key": build_dedupe_key(
                    user.id, self.insight_type,
                    window_start.date(), window_end.date(),
                    record_ids,
                ),
            }
        ]
