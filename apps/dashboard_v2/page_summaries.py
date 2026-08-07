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
    """The Dashboard workspace — the viewed day's commitments as deterministic facts.

    Date-aware: when the page is navigated to a past day (``summary:dashboard.day;
    date=YYYY-MM-DD``) the provider reports THAT day, from the SAME
    ``build_dashboard_day_summary`` source the page renders — so the assistant and
    the page never disagree about "what did this day look like." Facts only.
    """
    import datetime as _dt

    from apps.core.utils import get_user_today

    params = params or {}
    target_date = None
    date_str = params.get("date")
    if date_str:
        try:
            target_date = _dt.date.fromisoformat(date_str)
        except (ValueError, TypeError):
            target_date = None

    user_today = get_user_today(user)
    is_today = target_date is None or target_date == user_today
    day_label = "Today" if is_today else (
        target_date.strftime("%a, %b ") + str(target_date.day))

    facts = build_dashboard_day_summary(user, target_date)

    if facts.get("status") == "pending":
        return {"title": day_label, "kind": "dashboard overview",
                "content": "Today's plan — being prepared (up-to-date figures load momentarily)."}

    if not facts.get("total"):
        empty = ("Today — no commitments scheduled." if is_today
                 else f"{day_label} — nothing was scheduled that day.")
        return {"title": day_label, "kind": "dashboard overview", "content": empty}

    if is_today:
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
    else:
        # A past day: retrospective facts only — no "now"-relative overdue/next.
        lines = [
            f"Intended that day: {facts['total']}",
            f"Completed: {facts['completed']}",
            f"Outstanding: {facts['remaining']}",
        ]
    by_type = facts.get("by_type") or {}
    if by_type:
        pretty = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in sorted(by_type.items()))
        lines.append(f"By type — {pretty}")

    heading = "Today's dashboard" if is_today else f"Daily review — {day_label}"
    return {"title": day_label, "kind": "dashboard overview",
            "content": heading + "\n" + "\n".join(lines)}
