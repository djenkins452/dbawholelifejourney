# ==============================================================================
# File: apps/health/page_summaries.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context PAGE-SUMMARY providers for Health overview pages.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deterministic page-summary providers for Health overview/dashboard pages.

Registered at app-ready (see HealthConfig.ready). Each provider is user-scoped and
request-path-safe, and returns the uniform {title, content, kind} the assistant consumes
as Current Context focus — the SAME deterministic truth the page renders.
"""
from django.utils import timezone
from django.utils.dateformat import format as _dj_date

from apps.core.current_context import register_page_summary
from apps.health.services.weight_summary import build_weight_summary


def _d(dt):
    return _dj_date(timezone.localtime(dt), "M j, Y") if dt else "—"


@register_page_summary("health.weight")
def weight_page_summary(user, params):
    """The Weight overview page. Deterministic facts only — WLJ exposes the numbers; the
    model decides what they mean (no verdicts, no 'on track')."""
    facts = build_weight_summary(user, point_date=(params or {}).get("point"))
    if not facts:
        return {"title": "Weight", "kind": "weight overview",
                "content": "Weight overview — no weight entries logged yet."}

    lines = [f"Current weight: {facts['current_lb']} lb (as of {_d(facts['current_at'])})"]
    if facts.get("avg_30d_lb") is not None:
        lines.append(
            f"Last {facts['window_days']} days — average {facts['avg_30d_lb']} lb, "
            f"low {facts['low_30d_lb']} lb, high {facts['high_30d_lb']} lb "
            f"({facts['window_count']} entries)"
        )
    if facts.get("total_change_lb") is not None:
        tc = facts["total_change_lb"]
        lines.append(
            f"Total change (all recorded): {facts['first_lb']} lb on {_d(facts['first_at'])} "
            f"→ {facts['current_lb']} lb on {_d(facts['current_at'])} "
            f"= {'+' if tc > 0 else ''}{tc} lb"
        )
    lines.append(f"Entries logged: {facts['count']}")
    lines.append(f"Chart date range shown: {_d(facts['first_at'])} – {_d(facts['current_at'])}")
    if facts.get("point_lb") is not None:
        lines.append(f"Selected point: {facts['point_lb']} lb on {_d(facts['point_at'])}")

    return {"title": "Weight", "kind": "weight overview",
            "content": "Weight overview\n" + "\n".join(lines)}
