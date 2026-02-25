"""
EAE — Prompt Formatter (Phase 8.5).

Formats EAE arbitration output for injection into the LLM system prompt.
Replaces the raw CoS context intelligence sections with a controlled,
budgeted payload.
"""
import logging
from typing import Dict, List, Optional

from apps.core.ai_eae.bundler import CognitiveUnit
from apps.core.ai_eae.tone import get_tone_prompt

logger = logging.getLogger(__name__)


def format_for_prompt(
    units: List[CognitiveUnit],
    tone_band: str,
    escalation_level: int,
    primary_focus_label: str = '',
    drift_severity: float = 0.0,
) -> str:
    """
    Format EAE output for LLM system prompt injection.

    This replaces the raw intelligence dump with a concise, prioritized
    payload that respects the noise budget.

    Args:
        units: Surfaced cognitive units (ranked).
        tone_band: Selected tone band.
        escalation_level: Current escalation level (0-4).
        primary_focus_label: Current primary focus (if set).
        drift_severity: Current drift severity.

    Returns:
        Formatted string for system prompt injection.
    """
    parts = []

    # Section 1: Tone directive
    tone_prompt = get_tone_prompt(tone_band)
    parts.append(tone_prompt)

    # Section 2: Primary Focus (if set)
    if primary_focus_label:
        parts.append(f"\nPRIMARY FOCUS: {primary_focus_label}")

    # Section 3: Intelligence briefing
    if units:
        parts.append("\n--- INTELLIGENCE BRIEFING ---")
        for unit in units:
            prefix = f"[{unit.rank}]"
            if unit.unit_type == 'bundle':
                parts.append(f"{prefix} {unit.bundle_label}: {unit.title}")
            else:
                severity_icon = {
                    'critical': '!',
                    'warning': '*',
                    'positive': '+',
                    'info': '-',
                }.get(unit.severity, '-')
                parts.append(f"{prefix} {severity_icon} {unit.title}")

            if unit.why_this_matters:
                parts.append(f"    Why: {unit.why_this_matters[:150]}")

        parts.append("--- END BRIEFING ---")
    else:
        parts.append("\nNo priority items to surface. Proceed with user's request.")

    # Section 4: Escalation context (only at elevated+ levels)
    if escalation_level >= 2:
        level_labels = {
            2: "Active drift detected",
            3: "Critical drift — consequences matter",
            4: "Executive override — single focus only",
        }
        parts.append(f"\nSYSTEM STATE: {level_labels.get(escalation_level, '')}")

    return '\n'.join(parts)


def format_suppressed_for_audit(
    suppressed: List[Dict],
    override_events: List[Dict],
) -> List[Dict]:
    """
    Combine suppressed items and override events into a single audit list
    for EAEDecisionLog.suppressed_items_json.
    """
    audit = []

    for item in suppressed:
        audit.append({
            'title': item.get('title', ''),
            'engine': item.get('engine', ''),
            'module': item.get('module', ''),
            'score': item.get('score', 0),
            'reason': item.get('reason', 'BUDGET_CAP'),
        })

    for event in override_events:
        audit.append({
            'title': event.get('signal_type', ''),
            'engine': '',
            'module': '',
            'score': 0,
            'reason': f"OVERRIDE_{event.get('override_type', 'UNKNOWN').upper()}",
        })

    return audit
