# ==============================================================================
# File: apps/core/ai_orchestrator/signal_insight_engine.py
# Description: Phase 6D — Deterministic PIE layer for interpreted signals
# Created: 2026-03-17
# ==============================================================================
"""
Signal Insight Engine — deterministic PIE activation layer.

Consumes interpreted_signals (from signal_interpreter.py) and produces
structured, human-meaningful insights for CoS context.

Pipeline position:
    signals → interpreter → **PIE (this)** / PRIE / PGE → CoS → LLM

Rules:
- Deterministic only — no LLM, no DB queries
- Insight-only — no actions, no predictions
- Consumes signal-layer data only — no raw model access
- Generic over meaning_codes — not email- or finance-specific
"""

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Meaning code → Insight rule mapping (deterministic)
# ---------------------------------------------------------------------------

_INSIGHT_RULES = {
    'upcoming_financial_obligation': {
        'insight_code': 'bill_due_detected',
        'default_domain': 'finance',
        'summary': 'A bill-related obligation appears to be coming due soon.',
        'priority_when_time_sensitive': 'high',
        'priority_default': 'medium',
        'must_surface': True,
    },
    'recurring_financial_commitment': {
        'insight_code': 'recurring_obligation_detected',
        'default_domain': 'finance',
        'summary': 'A recurring financial commitment has been identified.',
        'priority_when_time_sensitive': 'medium',
        'priority_default': 'medium',
        'must_surface': False,
    },
    'upcoming_schedule_block': {
        'insight_code': 'schedule_commitment_detected',
        'default_domain': 'life',
        'summary': 'A scheduled commitment has been identified.',
        'priority_when_time_sensitive': 'high',
        'priority_default': 'medium',
        'must_surface': True,
    },
}


def generate_signal_insights(interpreted_signals):
    """
    Convert interpreted signals into structured insight objects.

    Args:
        interpreted_signals: list of dicts from interpret_signals(), each with:
            meaning_code, semantic_class, priority_hint, confidence,
            domain, source_refs, signal_type, intent

    Returns:
        list of insight dicts, each with:
            insight_code, domain, priority, summary,
            source_meaning_codes, source_refs, confidence,
            must_surface (bool)
        Empty list if no insights generated.
    """
    if not interpreted_signals:
        return []

    # Build insights, keyed for dedup
    # Key: (insight_code, domain)
    dedup = {}

    for signal in interpreted_signals:
        meaning_code = signal.get('meaning_code', '')
        rule = _INSIGHT_RULES.get(meaning_code)
        if not rule:
            continue

        domain = signal.get('domain') or rule['default_domain']
        confidence = signal.get('confidence', 0.0)
        priority_hint = signal.get('priority_hint', '')

        # Context-aware priority
        if priority_hint == 'time_sensitive':
            priority = rule['priority_when_time_sensitive']
        else:
            priority = rule['priority_default']

        dedup_key = (rule['insight_code'], domain)

        if dedup_key in dedup:
            existing = dedup[dedup_key]
            # Merge: keep highest confidence, union source refs/codes
            if confidence > existing['confidence']:
                existing['confidence'] = confidence
            if meaning_code not in existing['source_meaning_codes']:
                existing['source_meaning_codes'].append(meaning_code)
            for ref in signal.get('source_refs', []):
                if ref and ref not in existing['source_refs']:
                    existing['source_refs'].append(ref)
            # Escalate priority if any contributor is higher
            if priority == 'high' and existing['priority'] != 'high':
                existing['priority'] = priority
            # Escalate must_surface if any contributor requires it
            if rule.get('must_surface', False):
                existing['must_surface'] = True
        else:
            dedup[dedup_key] = {
                'insight_code': rule['insight_code'],
                'domain': domain,
                'priority': priority,
                'summary': rule['summary'],
                'source_meaning_codes': [meaning_code],
                'source_refs': list(signal.get('source_refs', [])),
                'confidence': confidence,
                'must_surface': rule.get('must_surface', False),
            }

    insights = list(dedup.values())

    if insights:
        logger.info(
            "PIE_SIGNAL_INSIGHTS generated=%d from=%d interpreted_signals",
            len(insights), len(interpreted_signals),
        )

    return insights
