"""
Proactive Insight Engine (PIE)

Event-driven + scheduled insight system that generates factual,
explainable insights across all WLJ modules.

Public API:
    run_insights(user, event) -> list[Insight]
"""

from apps.core.ai_insights.insight_engine import run_insights

__all__ = ["run_insights"]
