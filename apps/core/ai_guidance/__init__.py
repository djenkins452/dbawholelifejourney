"""
PGE -- Proactive Guidance Engine.

Evaluates user state, insights, and predictions to determine what
the user should be proactively shown. PGE does NOT execute actions.
It selects, ranks, and surfaces important guidance.

Public API:
    generate_guidance(user) -> list[GuidanceItem]
    get_active_guidance(user, limit=5) -> QuerySet[GuidanceItem]
"""

from apps.core.ai_guidance.guidance_engine import generate_guidance  # noqa: F401
import apps.core.ai_guidance.guidance_rules_transformation  # noqa: F401  -- register transformation rules
