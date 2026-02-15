"""
DBE — Daily Briefing Engine.

Presentation-layer intelligence engine that aggregates from SAE, PIE, PRIE,
and PGE to produce a daily intelligence summary for each user.

Public API:
    generate_daily_briefing(user) -> DailyBriefing
"""

from apps.core.ai_briefing.briefing_engine import generate_daily_briefing  # noqa: F401

__all__ = ["generate_daily_briefing"]
