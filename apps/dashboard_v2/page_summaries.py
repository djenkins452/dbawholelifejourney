# ==============================================================================
# File: apps/dashboard_v2/page_summaries.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context PAGE-SUMMARY provider for the Dashboard workspace.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deterministic Current Context page-summary provider for the Dashboard.

Registered at app-ready (DashboardV2Config.ready). Reads the ONE shared source
(build_dashboard_day_summary), which is request-path-safe (SAE snapshot only). Facts
only — no verdicts; the model decides what the numbers mean. Serves both dashboard_v2
(/dashboard/) and dashboard_v3, which declare page_summary_key="dashboard.day".
"""

from apps.core.current_context import register_page_summary
from apps.core.execution.dashboard_day_summary import build_dashboard_day_summary


@register_page_summary("dashboard.day")
def dashboard_day_summary(user, params):
    """The Dashboard workspace — today's commitments as deterministic facts."""
    facts = build_dashboard_day_summary(user)

    if facts.get("status") == "pending":
        return {"title": "Today", "kind": "dashboard overview",
                "content": "Today's plan — being prepared (up-to-date figures load momentarily)."}

    if not facts.get("total"):
        return {"title": "Today", "kind": "dashboard overview",
                "content": "Today — no commitments scheduled."}

    lines = [
        f"Commitments today: {facts['total']}",
        f"Completed: {facts['completed']}",
        f"Remaining: {facts['remaining']}",
        f"Overdue: {facts['overdue']}",
        f"Still to come: {facts['upcoming']}",
    ]
    nxt = facts.get("next_item")
    if nxt and nxt.get("title"):
        when = f" at {nxt['time']}" if nxt.get("time") else ""
        lines.append(f"Next scheduled: {nxt['title']}{when}")
    by_type = facts.get("by_type") or {}
    if by_type:
        pretty = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in sorted(by_type.items()))
        lines.append(f"By type — {pretty}")

    return {"title": "Today", "kind": "dashboard overview",
            "content": "Today's dashboard\n" + "\n".join(lines)}
