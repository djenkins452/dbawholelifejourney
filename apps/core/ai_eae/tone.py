"""
EAE — Tone Band Selection (Phase 8.4).

Deterministically selects communication tone based on escalation level
and drift severity. The tone band is injected into the LLM system prompt
to control response style.

Bands:
    REFLECTIVE_GENTLE: Warm, observational, invitational
    REFLECTIVE_FIRM: Factual, structured, encouraging
    DIRECT_CLEAR: No fluff, priorities first, direct
    DIRECT_URGENT: Consequences visible, compressed
    EXECUTIVE_OVERRIDE: Minimal words, single action, no options
"""
import logging

from apps.core.ai_eae.constants import (
    ESCALATION_TONE_MAP,
    TONE_DIRECT_CLEAR,
    TONE_DIRECT_URGENT,
    TONE_EXECUTIVE_OVERRIDE,
    TONE_REFLECTIVE_FIRM,
    TONE_REFLECTIVE_GENTLE,
    apply_intensity,
)

logger = logging.getLogger(__name__)

# Tone prompt injections — what the LLM sees
TONE_PROMPTS = {
    TONE_REFLECTIVE_GENTLE: (
        "TONE: Warm and observational. Invite, don't direct. "
        "Use reflective questions. Acknowledge progress. "
        "Keep it light and encouraging."
    ),
    TONE_REFLECTIVE_FIRM: (
        "TONE: Factual and structured. Be clear about what matters today. "
        "Encourage, but don't avoid the truth. "
        "Frame priorities as opportunities, not obligations."
    ),
    TONE_DIRECT_CLEAR: (
        "TONE: Direct and clear. Lead with the priority. "
        "No fluff or preamble. State what's important and why. "
        "Offer one concrete next step."
    ),
    TONE_DIRECT_URGENT: (
        "TONE: Urgent and direct. This matters now. "
        "State the consequence of inaction clearly. "
        "Compress to essentials only. One action, one reason."
    ),
    TONE_EXECUTIVE_OVERRIDE: (
        "TONE: Executive override. Minimal words. "
        "One single action. No options, no alternatives. "
        "This is the priority. Everything else waits."
    ),
}

# Ordered by intensity (for intensity-adjusted selection)
TONE_ORDER = [
    TONE_REFLECTIVE_GENTLE,    # 0
    TONE_REFLECTIVE_FIRM,      # 1
    TONE_DIRECT_CLEAR,         # 2
    TONE_DIRECT_URGENT,        # 3
    TONE_EXECUTIVE_OVERRIDE,   # 4
]


def select_tone(
    escalation_level: int,
    drift_severity: float = 0.0,
    intensity: float = 1.0,
) -> str:
    """
    Select tone band based on escalation level.

    Higher intensity shifts tone one step firmer at the same escalation level.

    Args:
        escalation_level: Current EAE escalation level (0-4).
        drift_severity: Current drift severity (for edge-case tuning).
        intensity: Intensity multiplier.

    Returns:
        Tone band string constant.
    """
    # Base tone from escalation level
    base_tone = ESCALATION_TONE_MAP.get(escalation_level, TONE_REFLECTIVE_GENTLE)
    base_index = TONE_ORDER.index(base_tone)

    # Intensity adjustment: shift tone index
    if intensity > 1.2:
        # Higher intensity → one step firmer
        adjusted_index = min(base_index + 1, len(TONE_ORDER) - 1)
    elif intensity < 0.8:
        # Lower intensity → one step gentler
        adjusted_index = max(base_index - 1, 0)
    else:
        adjusted_index = base_index

    tone = TONE_ORDER[adjusted_index]

    logger.debug(
        "EAE tone: L%d + intensity=%.1f → %s",
        escalation_level, intensity, tone,
    )

    return tone


def get_tone_prompt(tone_band: str) -> str:
    """Get the LLM prompt injection for a tone band."""
    return TONE_PROMPTS.get(tone_band, TONE_PROMPTS[TONE_REFLECTIVE_GENTLE])
