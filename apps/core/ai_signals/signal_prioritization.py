"""
Signal Prioritization & Narrative Layer.

Takes the raw cross-domain signal list and produces a deterministic
decision frame: one primary situation, optional secondary pressure,
suppressed noise, and a human-readable narrative.

Architecture:
    Cross-Domain Signals → [THIS LAYER] → CoS Prompt Injection
    Input: sorted signal list from generate_cross_domain_signals()
    Output: prioritized decision frame dict

Rules:
    - All logic is deterministic (no LLM, no ML)
    - Narrative text is templated, not generated
    - Suppression is explicit and traceable
    - The output is a single, focused decision frame

Usage:
    from apps.core.ai_signals.signal_prioritization import (
        prioritize_signals,
        format_signal_narrative,
    )
    frame = prioritize_signals(signals)
    narrative = format_signal_narrative(frame)
"""

import logging

logger = logging.getLogger(__name__)


# ── Signal taxonomy: which signals subsume others ──────────────────
# If a parent signal fires, its children are redundant noise.
# Key = parent signal_code, Value = set of child signal_codes it absorbs.
_SUBSUMPTION_MAP = {
    'system_overload': {
        'execution_overload', 'low_execution_momentum',
        'routine_breakdown', 'financial_pressure_cluster',
        'medication_adherence_risk',
    },
    'multi_domain_pressure': {
        'execution_overload', 'low_execution_momentum',
    },
    'health_attention_required': {
        'medication_adherence_risk',
    },
    'financial_pressure_cluster': {
        'overdue_financial_risk',
    },
    'execution_overload': {
        'low_execution_momentum',
    },
}

# ── Severity weights for scoring ──────────────────────────────────
_SEVERITY_WEIGHT = {'high': 30, 'medium': 15, 'low': 5}
_CONFIDENCE_WEIGHT = {'high': 3, 'medium': 2, 'low': 1}

# ── Domain impact weights (health > finance > execution > social) ──
_DOMAIN_IMPACT = {
    'medicine': 10,
    'medical': 10,
    'health': 9,
    'finance': 8,
    'tasks': 6,
    'routine': 6,
    'capture': 4,
    'brain_training': 3,
    'relationships': 5,
}


def _score_signal(signal: dict) -> float:
    """Compute a deterministic priority score for a signal.

    Higher score = higher priority. Considers severity, confidence,
    and domain impact weights.
    """
    severity = _SEVERITY_WEIGHT.get(signal.get('severity', 'low'), 5)
    confidence = _CONFIDENCE_WEIGHT.get(signal.get('confidence', 'low'), 1)

    # Domain impact: use max domain weight across all domains in signal
    domains = signal.get('domains', [])
    domain_weight = max(
        (_DOMAIN_IMPACT.get(d, 3) for d in domains),
        default=3,
    )

    # Multi-domain bonus: signals spanning more domains are more systemic
    breadth_bonus = min(len(domains) - 1, 3) * 2  # 0, 2, 4, 6

    return severity * confidence + domain_weight + breadth_bonus


def _suppress_subsumed(signals: list) -> tuple:
    """Remove signals that are subsumed by higher-priority signals.

    Returns:
        (active_signals, suppressed_signals) — both lists.
    """
    active_codes = {s.get('signal_code') for s in signals}
    suppressed_codes = set()

    # Walk signals in priority order (already sorted by severity)
    for signal in signals:
        code = signal.get('signal_code', '')
        children = _SUBSUMPTION_MAP.get(code, set())
        suppressed_codes.update(children & active_codes)

    active = [s for s in signals if s.get('signal_code') not in suppressed_codes]
    suppressed = [s for s in signals if s.get('signal_code') in suppressed_codes]

    return active, suppressed


def prioritize_signals(signals: list) -> dict:
    """Produce a deterministic decision frame from cross-domain signals.

    Args:
        signals: Sorted signal list from generate_cross_domain_signals().

    Returns:
        Dict with:
            primary: the single most important signal (or None)
            secondary: the next most important non-subsumed signal (or None)
            suppressed: list of suppressed signal codes with reasons
            active_count: number of active (non-suppressed) signals
            total_count: total signals before suppression
            pressure_level: 'none' | 'low' | 'moderate' | 'elevated' | 'critical'
    """
    if not signals:
        return {
            'primary': None,
            'secondary': None,
            'suppressed': [],
            'active_count': 0,
            'total_count': 0,
            'pressure_level': 'none',
        }

    # Step 1: Suppress subsumed signals
    active, suppressed = _suppress_subsumed(signals)

    suppressed_detail = [
        {
            'signal_code': s.get('signal_code'),
            'reason': 'subsumed by higher-priority signal',
        }
        for s in suppressed
    ]

    # Step 2: Score and rank active signals
    scored = sorted(active, key=_score_signal, reverse=True)

    primary = scored[0] if scored else None
    secondary = scored[1] if len(scored) > 1 else None

    # Step 3: Determine overall pressure level
    high_count = sum(1 for s in active if s.get('severity') == 'high')
    medium_count = sum(1 for s in active if s.get('severity') == 'medium')

    if high_count >= 2:
        pressure_level = 'critical'
    elif high_count == 1:
        pressure_level = 'elevated'
    elif medium_count >= 3:
        pressure_level = 'elevated'
    elif medium_count >= 1:
        pressure_level = 'moderate'
    elif active:
        pressure_level = 'low'
    else:
        pressure_level = 'none'

    return {
        'primary': primary,
        'secondary': secondary,
        'suppressed': suppressed_detail,
        'active_count': len(active),
        'total_count': len(signals),
        'pressure_level': pressure_level,
    }


# ── Narrative templates ───────────────────────────────────────────
# Deterministic, templated narratives — no LLM generation.

_PRESSURE_OPENERS = {
    'critical': "Multiple high-priority situations need your attention.",
    'elevated': "There's a significant issue that should be addressed.",
    'moderate': "A few things are building up across your day.",
    'low': "Things are mostly on track with minor attention areas.",
    'none': "",
}

_DOMAIN_LABELS = {
    'medicine': 'medication',
    'medical': 'health labs',
    'finance': 'finances',
    'tasks': 'tasks',
    'routine': 'routines',
    'capture': 'capture inbox',
    'brain_training': 'brain training',
    'relationships': 'relationships',
    'health': 'health',
}


def format_signal_narrative(frame: dict) -> str:
    """Format the prioritized signal frame into a deterministic narrative block.

    Args:
        frame: Output from prioritize_signals().

    Returns:
        Multi-line string for CoS system injection. Empty string if no signals.
    """
    if not frame or frame.get('pressure_level') == 'none':
        return ""

    lines = []
    pressure = frame.get('pressure_level', 'none')
    primary = frame.get('primary')
    secondary = frame.get('secondary')
    active_count = frame.get('active_count', 0)
    suppressed_count = len(frame.get('suppressed', []))

    # Header
    lines.append(
        f"=== SITUATION ASSESSMENT (pressure: {pressure.upper()}"
        f", {active_count} active signal(s)"
        f"{f', {suppressed_count} suppressed' if suppressed_count else ''}) ==="
    )

    # Opening line
    opener = _PRESSURE_OPENERS.get(pressure, '')
    if opener:
        lines.append(opener)

    # Primary signal
    if primary:
        domains_text = ' + '.join(
            _DOMAIN_LABELS.get(d, d) for d in primary.get('domains', [])
        )
        lines.append("")
        lines.append(f"PRIMARY: {primary.get('summary', '')}")
        lines.append(f"  Domains: {domains_text}")
        action = primary.get('recommended_action')
        if action:
            lines.append(f"  Suggested: {action}")

    # Secondary signal
    if secondary:
        domains_text = ' + '.join(
            _DOMAIN_LABELS.get(d, d) for d in secondary.get('domains', [])
        )
        lines.append("")
        lines.append(f"SECONDARY: {secondary.get('summary', '')}")
        lines.append(f"  Domains: {domains_text}")

    # Coaching directive
    lines.append("")
    if pressure == 'critical':
        lines.append(
            "RESPONSE GUIDANCE: Lead with the PRIMARY situation. Be direct "
            "about what needs attention. Don't bury it in pleasantries."
        )
    elif pressure == 'elevated':
        lines.append(
            "RESPONSE GUIDANCE: Mention the primary situation early in your "
            "response. Frame it supportively, not as a lecture."
        )
    elif pressure == 'moderate':
        lines.append(
            "RESPONSE GUIDANCE: Weave the primary observation naturally into "
            "your response if relevant to what the user said."
        )
    else:
        lines.append(
            "RESPONSE GUIDANCE: No urgent signals. Respond normally. "
            "You may note the minor observation if it fits naturally."
        )

    lines.append("=== END SITUATION ASSESSMENT ===")

    return "\n".join(lines)
