"""
Proactive Insight Engine (PIE)

Event-driven + scheduled insight system that generates factual,
explainable insights across all WLJ modules.

Public API:
    run_insights(user, event) -> list[Insight]
"""

from apps.core.ai_insights.insight_engine import run_insights

# Import ALL rule modules so @register decorators fire and rules enter the
# registry.  Previously only rules_cross_domain was imported here, and the
# comment said "domain-specific rules are imported by their respective modules."
# In practice, no domain app performed that import, so the ISE
# run_pie_synthetic() scheduled task (which calls run_insights → get_rules)
# could only evaluate cross-domain rules.  Domain-specific scheduled_check
# rules (health, goals, behavior, compensatory, etc.) never fired on the
# scheduled cadence — causing "signal drought" for 6+ domains.
import apps.core.ai_insights.rules_behavior  # noqa: F401
import apps.core.ai_insights.rules_body_composition  # noqa: F401
import apps.core.ai_insights.rules_compensatory  # noqa: F401
import apps.core.ai_insights.rules_context  # noqa: F401
import apps.core.ai_insights.rules_cross_domain  # noqa: F401
import apps.core.ai_insights.rules_first_entry  # noqa: F401
import apps.core.ai_insights.rules_goals  # noqa: F401
import apps.core.ai_insights.rules_habits  # noqa: F401
import apps.core.ai_insights.rules_health  # noqa: F401
import apps.core.ai_insights.rules_journal  # noqa: F401
import apps.core.ai_insights.rules_labs_vitals  # noqa: F401
import apps.core.ai_insights.rules_meals  # noqa: F401
import apps.core.ai_insights.rules_scripture  # noqa: F401
import apps.core.ai_insights.rules_tasks  # noqa: F401
import apps.core.ai_insights.rules_transformation  # noqa: F401

__all__ = ["run_insights"]
