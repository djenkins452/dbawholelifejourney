"""
Developer-facing explanation mode for HealthBriefing.

**Not user-facing. Not Beth-facing.** Used by:

* the ``run_health_briefing`` management command for local inspection
* the (later) replay command to render historical snapshots
* test fixtures and debugging

Output format (stable; suitable for diff/snapshot tests):

    HealthBriefing user=4081 briefing_id=abc123…
      composed_at:   2026-05-25T15:30:00+00:00
      headline:      Metabolic trajectory is improving.
      status:        improving (confidence 0.82)
      risk_level:    low

    Drivers (positive):
      + Glycemic Control tight (+18)   — 85% time-in-range
      + Insulin Dependence decreasing (+15) — Recent daily 12.0u vs 30d avg 18.0u
      + Weight Trajectory improving (+12) — Weight down 3.0 lb over 30d

    Watch items:
      - Glycemic Trajectory declining (-5) — 7d avg 5 mg/dL above recent baseline

    Acute alerts: none

    Trends:
      glucose 7d:  down  magnitude=22 confidence=0.7
      glucose 30d: down  magnitude=14 confidence=0.7
      glucose 90d: insufficient_data
      weight 30d:  down  magnitude=12 confidence=0.7
      insulin 30d: down  magnitude=18 confidence=0.7

    Why:
      1. Glycemic Control tight (+18): 85% time-in-range
      2. Insulin Dependence decreasing (+15): Recent daily 12.0u vs 30d avg 18.0u
      3. Weight Trajectory improving (+12): Weight down 3.0 lb over 30d
      4. Glycemic Trajectory declining (-5): 7d avg 5 mg/dL above recent baseline

    Evidence (used: 12 fields, missing: 6 fields, stale: 0)
      latest_glucose=132, glucose_avg_7d=125, ...

The explanation is deterministic: same briefing produces identical
output. No randomness, no LLM, no Beth.
"""

from __future__ import annotations

from typing import Optional

from apps.core.health_briefing.contract import (
    HealthBriefing,
    Trend,
    TrendDirection,
)


def _format_trend(label: str, trend: Optional[Trend]) -> str:
    if trend is None:
        return f"  {label:<13} not observed (None)"
    if trend.direction == TrendDirection.INSUFFICIENT_DATA:
        return f"  {label:<13} insufficient_data"
    return (
        f"  {label:<13} {trend.direction.value:<5} "
        f"magnitude={trend.magnitude:<3} confidence={trend.confidence}"
    )


def explain_briefing(briefing: HealthBriefing) -> str:
    """Return a multi-line developer-facing explanation of a briefing."""
    lines: list[str] = []

    lines.append(
        f"HealthBriefing user={briefing.user_id} "
        f"briefing_id={briefing.briefing_id[:12]}…"
    )
    lines.append(f"  composed_at:   {briefing.generated_at_utc.isoformat()}")
    lines.append(f"  headline:      {briefing.headline_summary}")
    lines.append(
        f"  status:        {briefing.overall_status.value} "
        f"(confidence {briefing.overall_confidence})"
    )
    lines.append(f"  risk_level:    {briefing.risk_level.value}")
    if briefing.insufficient_data_flag:
        lines.append("  insufficient_data_flag: TRUE")
    if briefing.positive_recognition_required:
        lines.append("  positive_recognition_required: TRUE")

    lines.append("")
    lines.append("Drivers (positive):")
    if briefing.top_positive_drivers:
        for d in briefing.top_positive_drivers:
            score_str = f"+{int(d.score)}"
            lines.append(f"  + {d.label} ({score_str}) — {d.why}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("Watch items:")
    if briefing.watch_items:
        for d in briefing.watch_items:
            lines.append(f"  - {d.label} ({int(d.score)}) — {d.why}")
    else:
        lines.append("  (none)")

    lines.append("")
    if briefing.acute_alerts:
        lines.append("Acute alerts:")
        for a in briefing.acute_alerts:
            lines.append(f"  ! [{a.severity.value}] {a.label} — {a.why}")
    else:
        lines.append("Acute alerts: none")

    lines.append("")
    lines.append("Trends:")
    lines.append(_format_trend("glucose 7d:", briefing.glucose_trend_7d))
    lines.append(_format_trend("glucose 30d:", briefing.glucose_trend_30d))
    lines.append(_format_trend("glucose 90d:", briefing.glucose_trend_90d))
    lines.append(_format_trend("weight 30d:", briefing.weight_trend_30d))
    lines.append(_format_trend("insulin 30d:", briefing.insulin_trend_30d))

    lines.append("")
    lines.append("Why:")
    if briefing.why:
        for i, bullet in enumerate(briefing.why, start=1):
            lines.append(f"  {i}. {bullet}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append(
        f"Evidence (used: {len(briefing.inputs_used)} fields, "
        f"missing: {len(briefing.inputs_missing)} fields, "
        f"stale: {len(briefing.staleness_flags)})"
    )
    if briefing.inputs_used:
        sample_keys = sorted(briefing.inputs_used.keys())[:6]
        lines.append(
            "  used (first 6): " + ", ".join(
                f"{k}={briefing.inputs_used[k]}" for k in sample_keys
            )
        )
    if briefing.inputs_missing:
        sample_missing = sorted(briefing.inputs_missing)[:6]
        lines.append("  missing (first 6): " + ", ".join(sample_missing))

    return "\n".join(lines)
