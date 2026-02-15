"""
PIL — Persona Profiles.

Defines the PersonaProfile dataclass that holds tone template
configuration for a coaching style.

Project: Whole Life Journey
Path: apps/core/ai_persona/persona_profiles.py

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class PersonaProfile:
    """
    Tone template configuration for a coaching style.

    Used by the renderer to apply persona voice to intelligence messages.
    Each profile defines patterns for greetings, closings, and message
    framing at different urgency levels.
    """

    persona_key: str
    display_name: str
    # Overall tone category: "warm", "direct", "intense", "chill", "nurturing"
    base_tone: str = "warm"

    # Opening lines — randomly selected based on intensity
    greeting_patterns: List[str] = field(default_factory=list)

    # {message} templates for positive/neutral content
    encouragement_frames: List[str] = field(default_factory=list)

    # {message} templates for concerning trends (priority 3)
    warning_frames: List[str] = field(default_factory=list)

    # {message} templates for critical items (priority 1-2)
    urgency_frames: List[str] = field(default_factory=list)

    # Sign-off lines — randomly selected based on intensity
    closing_patterns: List[str] = field(default_factory=list)

    # Style-specific interjections sprinkled in at high intensity
    flavor_expressions: List[str] = field(default_factory=list)

    # Whether this persona adapts intensity based on GLOE/ICQG signals
    adaptation_enabled: bool = True

    # How sensitive to adaptation signals (0.0-1.0, higher = more reactive)
    adaptation_sensitivity: float = 0.5
