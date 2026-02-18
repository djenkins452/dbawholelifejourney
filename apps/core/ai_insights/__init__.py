"""
Proactive Insight Engine (PIE)

Event-driven + scheduled insight system that generates factual,
explainable insights across all WLJ modules.

Public API:
    run_insights(user, event) -> list[Insight]
"""

from apps.core.ai_insights.insight_engine import run_insights

# Import rule modules so @register decorators fire and rules enter the registry.
# Domain-specific rules are imported by their respective modules;
# cross-domain rules must be imported here since they span modules.
import apps.core.ai_insights.rules_cross_domain  # noqa: F401

__all__ = ["run_insights"]
