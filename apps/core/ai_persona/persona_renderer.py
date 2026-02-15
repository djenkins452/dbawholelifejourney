"""
PIL — Persona Renderer.

Pure function that applies template-based tone transformations
to a base message. Zero database access — all data is pre-computed
and passed in.

Project: Whole Life Journey
Path: apps/core/ai_persona/persona_renderer.py

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import random


def render(persona_profile, base_message, intensity, context):
    """
    Apply persona voice to a base message.

    Args:
        persona_profile: PersonaProfile dataclass instance.
        base_message: str — the original intelligence message.
        intensity: float 0.6-1.4.
        context: dict with optional keys:
            - message_type: str ("guidance", "briefing", "weekly_report")
            - priority: int (1-5)
            - domain: str

    Returns:
        str — persona-rendered message.

    Rendering layers (applied based on intensity):
        0.6-0.7: greeting only
        0.7-0.9: greeting + closing
        0.9-1.1: greeting + frame selection + closing
        1.1-1.3: greeting + frame + flavor expressions + closing
        1.3-1.4: greeting + frame + heavy flavor + closing
    """
    if not base_message or not base_message.strip():
        return base_message

    # Use deterministic random seeded by message content
    # This ensures same message always gets same rendering (no flickering)
    rng = random.Random(hash(base_message))

    parts = []

    # Greeting (intensity >= 0.6, i.e. always)
    greeting = _select_greeting(persona_profile, intensity, rng)
    if greeting:
        parts.append(greeting)

    # Frame the message (intensity >= 0.9)
    if intensity >= 0.9:
        framed = _apply_frame(persona_profile, base_message, intensity, context, rng)
        parts.append(framed)
    else:
        parts.append(base_message)

    # Flavor expressions (intensity >= 1.1)
    if intensity >= 1.1 and persona_profile.flavor_expressions:
        flavor = _select_flavor(persona_profile, intensity, rng)
        if flavor:
            parts.append(flavor)

    # Closing (intensity >= 0.7)
    if intensity >= 0.7:
        closing = _select_closing(persona_profile, intensity, rng)
        if closing:
            parts.append(closing)

    return " ".join(parts)


def _select_greeting(profile, intensity, rng):
    """
    Pick a greeting from profile.greeting_patterns.

    Always applied (intensity >= 0.6 is the minimum).
    Returns empty string if no patterns available.
    """
    if not profile.greeting_patterns:
        return ""
    return rng.choice(profile.greeting_patterns)


def _select_closing(profile, intensity, rng):
    """
    Pick a closing from profile.closing_patterns.

    Applied when intensity >= 0.7.
    Returns empty string if no patterns available.
    """
    if not profile.closing_patterns:
        return ""
    return rng.choice(profile.closing_patterns)


def _apply_frame(profile, base_message, intensity, context, rng):
    """
    Select the appropriate frame (encouragement/warning/urgency) based on
    context priority and apply the {message} template.

    Frame selection:
    - priority 1-2 → urgency_frames
    - priority 3 → warning_frames
    - priority 4-5 or no priority → encouragement_frames
    - message_type "briefing"/"weekly_report" → encouragement_frames
    """
    context = context or {}
    priority = context.get("priority")
    message_type = context.get("message_type", "")

    # Briefings and reports always use encouragement framing
    if message_type in ("briefing", "weekly_report"):
        frames = profile.encouragement_frames
    elif priority is not None:
        if priority <= 2:
            frames = profile.urgency_frames
        elif priority == 3:
            frames = profile.warning_frames
        else:
            frames = profile.encouragement_frames
    else:
        frames = profile.encouragement_frames

    # Fallback: if no frames defined for that type, use encouragement
    if not frames:
        frames = profile.encouragement_frames

    # Final fallback: return raw message
    if not frames:
        return base_message

    template = rng.choice(frames)

    # Apply template
    if "{message}" in template:
        return template.format(message=base_message)
    else:
        # Template doesn't have placeholder — prepend it
        return f"{template} {base_message}"


def _select_flavor(profile, intensity, rng):
    """
    At intensity >= 1.1, select 1 flavor expression.
    At intensity >= 1.3, select up to 2 (joined).
    """
    if not profile.flavor_expressions:
        return ""

    if intensity >= 1.3 and len(profile.flavor_expressions) >= 2:
        selections = rng.sample(
            profile.flavor_expressions,
            min(2, len(profile.flavor_expressions)),
        )
        return " ".join(selections)
    else:
        return rng.choice(profile.flavor_expressions)
