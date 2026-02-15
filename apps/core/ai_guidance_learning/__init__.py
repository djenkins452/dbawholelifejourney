"""
GLOE — Guidance Learning Optimization Engine.

Learns from user interactions with guidance to improve future prioritization.
Observes guidance lifecycle outcomes and builds a responsiveness profile.

GLOE does NOT generate guidance. It improves scoring used by PGE and DBE.

Public API:
    update_learning_profile(user) -> GuidanceLearningProfile
    log_learning_event(user, guidance_item, event_type) -> GuidanceLearningEvent
"""

from apps.core.ai_guidance_learning.learning_engine import update_learning_profile  # noqa: F401
from apps.core.ai_guidance_learning.learning_logger import log_learning_event  # noqa: F401

__all__ = ["update_learning_profile", "log_learning_event"]
