"""
PIL — Persona Engine (Entry Point).

Main entry point for the Persona Intelligence Layer.
Coordinates persona profile lookup, tone intensity adaptation,
and message rendering.

This is the ONLY public API for PIL.

Project: Whole Life Journey
Path: apps/core/ai_persona/persona_engine.py

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

logger = logging.getLogger(__name__)


def render_with_persona(user, base_message, message_type,
                        domain=None, priority=None, severity=None):
    """
    Apply the user's coaching style persona to a base message.

    This is the single public API for PIL. All intelligence engines
    should call this function to apply persona rendering.

    Args:
        user: Django User instance.
        base_message: str — the raw intelligence message.
        message_type: str — "guidance", "briefing", or "weekly_report".
        domain: Optional str — module name (health, goals, etc.).
        priority: Optional int — 1-5 priority from PGE.
        severity: Optional str — severity level from insight.

    Returns:
        str — persona-rendered message.
        ALWAYS returns base_message on any error (fail-safe).
    """
    if not base_message or not base_message.strip():
        return base_message

    try:
        # Step 1: Get user's coaching style key
        persona_key = _get_persona_key(user)

        # Step 2: Load persona profile
        from apps.core.ai_persona.persona_registry import get_persona_profile

        profile = get_persona_profile(persona_key)

        # Step 3: Build context
        context = {
            "message_type": message_type,
            "domain": domain,
            "priority": priority,
            "severity": severity,
        }

        # Step 4: Calculate tone intensity
        from apps.core.ai_persona.persona_adaptation import calculate_tone_intensity

        intensity = calculate_tone_intensity(user, persona_key, context)

        # Step 5: Render with persona
        from apps.core.ai_persona.persona_renderer import render

        result = render(profile, base_message, intensity, context)

        return result or base_message

    except Exception as e:
        logger.warning(f"PIL: Persona rendering failed for user {user.id}: {e}")
        return base_message  # FAIL-SAFE: always return original


def _get_persona_key(user):
    """
    Get the coaching style key from user preferences.

    Falls back to 'supportive' if preferences are unavailable.
    """
    try:
        key = getattr(user.preferences, "ai_coaching_style", "supportive")
        return key or "supportive"
    except Exception:
        return "supportive"
