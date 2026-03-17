# ==============================================================================
# File: apps/core/ai_orchestrator/mandatory_insight_enforcer.py
# Description: Phase 6E — Mandatory insight enforcement layer (pre-LLM)
# Created: 2026-03-17
# ==============================================================================
"""
Mandatory Insight Enforcer — pre-LLM enforcement of must-surface insights.

Filters signal insights to those marked must_surface=True, ensuring the CoS
prompt includes them in a MANDATORY block the LLM cannot ignore.

Pipeline position:
    signals → interpreter → PIE → **enforcer (this)** → CoS prompt → LLM

Rules:
- Pure function, no DB, no LLM, no side effects
- Deterministic ordering: high priority first, then by insight_code
- Only passes through insights with must_surface=True
"""

import logging

logger = logging.getLogger(__name__)


def extract_mandatory_insights(insights):
    """
    Filter insights to those requiring mandatory surfacing.

    Args:
        insights: list of insight dicts from generate_signal_insights(),
            each may contain must_surface=True/False.

    Returns:
        list of mandatory insight dicts, ordered by priority (high first),
        then alphabetically by insight_code for determinism.
        Empty list if none are mandatory.
    """
    if not insights:
        return []

    mandatory = [i for i in insights if i.get('must_surface')]
    if not mandatory:
        return []

    # Deterministic ordering: high priority first, then by insight_code
    _priority_rank = {'high': 0, 'medium': 1, 'low': 2}
    mandatory.sort(key=lambda i: (
        _priority_rank.get(i.get('priority', 'medium'), 1),
        i.get('insight_code', ''),
    ))

    logger.info(
        "MANDATORY_INSIGHTS enforced=%d from=%d total_insights",
        len(mandatory), len(insights),
    )

    return mandatory


def format_mandatory_block(mandatory_insights):
    """
    Format mandatory insights into a prompt block for CoS injection.

    Args:
        mandatory_insights: list from extract_mandatory_insights().

    Returns:
        Formatted string block, or empty string if no mandatory insights.
    """
    if not mandatory_insights:
        return ''

    lines = [
        "=== MANDATORY INSIGHTS (REQUIRED — YOU MUST ADDRESS ALL) ===",
        "The following insights are REQUIRED. You MUST include and address "
        "every item below in your response. Do NOT omit or deprioritize any.",
    ]

    for idx, insight in enumerate(mandatory_insights, 1):
        priority = (insight.get('priority') or 'medium').upper()
        summary = insight.get('summary', '')
        domain = insight.get('domain', '')
        refs = ', '.join(insight.get('source_refs', []))
        domain_tag = f" [{domain}]" if domain else ""
        ref_tag = f" (Source: {refs})" if refs else ""
        lines.append(f"  {idx}. [{priority}]{domain_tag} {summary}{ref_tag}")

    lines.append("=== END MANDATORY INSIGHTS ===")

    return '\n'.join(lines)
