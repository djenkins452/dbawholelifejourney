"""
Ops Feed — Human-readable cognitive feed formatter.

Converts EngineRun and DecisionRecord rows into structured,
scannable feed lines for the Operations Wall.

Project: Whole Life Journey
Path: apps/core/ai_observability/ops_feed.py
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def get_recent_feed(since=None, limit=50, engine_filter=None):
    """
    Get recent operations feed entries.

    Args:
        since: datetime — only events after this time. Defaults to 5 min ago.
        limit: Max entries to return.
        engine_filter: Optional engine name to filter by.

    Returns:
        list of feed line dicts, newest first.
    """
    from apps.core.ai_observability.models import DecisionRecord, EngineRun

    if since is None:
        since = timezone.now() - timedelta(minutes=5)

    # Gather runs and decisions
    runs_qs = EngineRun.objects.filter(started_at__gt=since).order_by("-started_at")
    decisions_qs = DecisionRecord.objects.filter(created_at__gt=since).order_by(
        "-created_at"
    )

    if engine_filter:
        runs_qs = runs_qs.filter(engine_name=engine_filter)
        decisions_qs = decisions_qs.filter(engine_name=engine_filter)

    runs = list(runs_qs[:limit])
    decisions = list(decisions_qs[:limit])

    feed = []

    # Format runs
    for run in runs:
        feed.append(_format_run(run))

    # Format decisions (only if not already covered by a run)
    run_traces = {r.trace_id for r in runs}
    for dec in decisions:
        feed.append(_format_decision(dec))

    # Sort by time descending
    feed.sort(key=lambda x: x["sort_time"], reverse=True)
    return feed[:limit]


def _format_run(run):
    """Format an EngineRun into a feed line."""
    time_str = run.started_at.strftime("%H:%M:%S") if run.started_at else "??:??:??"

    action = f"{run.status.upper()}"
    detail = f"duration={run.duration_ms}ms"

    severity = "info"
    if run.status == "error":
        severity = "error"
        action = f"ERROR: {run.error_type}"
        detail = run.error_message[:100] if run.error_message else ""
    elif run.duration_ms > 1000:
        severity = "warn"
        action = f"SLOW ({run.duration_ms}ms)"

    return {
        "time": time_str,
        "sort_time": run.started_at.isoformat() if run.started_at else "",
        "engine": run.engine_name,
        "type": "run",
        "action": action,
        "detail": detail,
        "severity": severity,
        "trace_id": run.trace_id,
        "user_id": run.user_id,
    }


def _format_decision(dec):
    """Format a DecisionRecord into a feed line."""
    time_str = dec.created_at.strftime("%H:%M:%S") if dec.created_at else "??:??:??"

    # Engine-specific formatting
    if dec.engine_name == "UAL" and dec.decision_type == "arbitration":
        scenario = dec.decision.replace("SCENARIO=", "")
        conf_str = f"({dec.confidence:.2f})" if dec.confidence else ""
        action = f"{scenario} {conf_str}".strip()
        detail = dec.rationale[:100] if dec.rationale else ""
        severity = "warn" if scenario != "STABLE_EXECUTION" else "info"
    elif dec.engine_name == "ICQG" and dec.decision_type == "suppression":
        action = f"suppressed: {dec.decision}"
        detail = dec.rationale[:100] if dec.rationale else ""
        severity = "info"
    else:
        action = dec.decision[:60]
        detail = dec.rationale[:80] if dec.rationale else ""
        severity = "info"

    return {
        "time": time_str,
        "sort_time": dec.created_at.isoformat() if dec.created_at else "",
        "engine": dec.engine_name,
        "type": "decision",
        "action": action,
        "detail": detail,
        "severity": severity,
        "trace_id": dec.trace_id,
        "user_id": dec.user_id,
    }
