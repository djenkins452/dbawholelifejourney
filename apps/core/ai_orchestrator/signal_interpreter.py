# ==============================================================================
# File: apps/core/ai_orchestrator/signal_interpreter.py
# Description: Phase 6C — Deterministic signal semantic normalizer
# Created: 2026-03-17
# ==============================================================================
"""
Signal interpreter — deterministic semantic normalization layer.

Sits between signals and intelligence engines (PIE/PRIE/PGE).
Produces machine-readable enrichment: meaning codes, semantic classes,
priority hints. NO natural language, NO insights, NO guidance.

Pipeline position:
    signals → interpreter → PIE / PRIE / PGE → CoS → LLM
"""

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent → Semantic mapping (deterministic, machine-oriented)
# ---------------------------------------------------------------------------

_INTENT_SEMANTICS = {
    'bill_due': {
        'semantic_class': 'financial_obligation',
        'meaning_code': 'upcoming_financial_obligation',
        'priority_hint': 'time_sensitive',
    },
    'recurring_obligation': {
        'semantic_class': 'financial_obligation',
        'meaning_code': 'recurring_financial_commitment',
        'priority_hint': 'recurring',
    },
    'schedule_commitment': {
        'semantic_class': 'time_commitment',
        'meaning_code': 'upcoming_schedule_block',
        'priority_hint': 'time_sensitive',
    },
    # Faith calendar signals — biblical day detection (derived_pattern)
    'biblical_day_detected': {
        'semantic_class': 'faith_calendar_event',
        'meaning_code': 'biblical_significance_day',
        'priority_hint': 'contextual',
    },
}


def interpret_signals(daily_signals):
    """
    Deterministic semantic normalization of signal-layer data.

    Reads daily_signals (including intents list from SignalSnapshot),
    produces machine-readable interpreted_signals for downstream engines.

    Args:
        daily_signals: list of signal dicts from _build_signal_aware_context().
            Each may contain 'intents': ['bill_due', ...]

    Returns:
        dict with 'interpreted_signals' list, or empty dict if nothing to interpret.
        Each entry:
            signal_type, domain, intent, semantic_class, meaning_code,
            priority_hint, confidence, source_refs
    """
    if not daily_signals:
        return {}

    interpreted = []
    seen_intents = set()

    for signal in daily_signals:
        intents = signal.get('intents') or []
        for intent in intents:
            if intent in seen_intents:
                continue
            semantics = _INTENT_SEMANTICS.get(intent)
            if not semantics:
                continue

            seen_intents.add(intent)
            interpreted.append({
                'signal_type': signal.get('signal_type', ''),
                'domain': signal.get('domain', ''),
                'intent': intent,
                'semantic_class': semantics['semantic_class'],
                'meaning_code': semantics['meaning_code'],
                'priority_hint': semantics['priority_hint'],
                'confidence': signal.get('confidence', 0.0),
                'source_refs': [signal.get('signal_type', '')],
            })

    if not interpreted:
        return {}

    return {'interpreted_signals': interpreted}
