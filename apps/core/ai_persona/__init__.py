"""
PIL — Persona Intelligence Layer.

Rendering layer that applies coaching style tone to intelligence outputs.
PIL is NOT an intelligence engine. It never modifies what gets generated,
only how it is worded at render time.

Project: Whole Life Journey
Path: apps/core/ai_persona/__init__.py

Public API:
    render_with_persona(user, base_message, message_type, **context) -> str

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from apps.core.ai_persona.persona_engine import render_with_persona  # noqa: F401

__all__ = ["render_with_persona"]
