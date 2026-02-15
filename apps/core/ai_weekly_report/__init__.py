"""
WIRE — Weekly Intelligence Report Engine.

Generates one intelligence report per user per week summarizing state changes,
key insights, important predictions, and guidance engagement.
WIRE aggregates existing intelligence only — it does NOT generate new intelligence.
"""

from apps.core.ai_weekly_report.report_engine import (
    generate_weekly_report,
    get_latest_weekly_report,
)

__all__ = ["generate_weekly_report", "get_latest_weekly_report"]
