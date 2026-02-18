"""
Whole Life Journey — Executive Briefing Formatter

Project: Whole Life Journey
Path: apps/core/ai_orchestrator/briefing_formatter.py
Purpose: Format CoS responses in structured executive briefing style

Description:
    Wraps raw LLM responses and engine outputs in a structured
    executive briefing format. Used for proactive messages,
    interventions, and intelligence summaries.

Public API:
    - format_briefing(sections) -> str
    - format_cos_response(response, context=None) -> str

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

logger = logging.getLogger(__name__)


def format_briefing(sections):
    """
    Format structured sections into an executive briefing.

    Args:
        sections: list of dicts with keys:
            - label: str (e.g., "Situation", "Risk Level")
            - content: str
            - optional: bool (if True, skip when content is empty)

    Returns:
        str — formatted briefing text.
    """
    lines = []

    for section in sections:
        label = section.get('label', '')
        content = section.get('content', '')
        optional = section.get('optional', False)

        if optional and not content:
            continue

        if label:
            lines.append(f"{label}: {content}")
        else:
            lines.append(content)

    return '\n'.join(lines)


def format_cos_response(response, context=None):
    """
    Format an LLM response with CoS executive framing.

    If context is provided and contains relevant metrics,
    appends alignment/risk data to the response.

    Args:
        response: Raw LLM response string.
        context: Optional CoS context dict.

    Returns:
        str — response with optional CoS framing.
    """
    if not context:
        return response

    # Only add metrics footer for substantive responses
    if len(response) < 20:
        return response

    alignment = context.get('alignment_score', None)
    drift_risk = context.get('drift_probability', {}).get('probability_24h', None)

    footer_parts = []
    if alignment is not None and alignment < 90:
        footer_parts.append(f"Alignment: {alignment}%")
    if drift_risk is not None and drift_risk > 30:
        footer_parts.append(f"24h Risk: {drift_risk}%")

    if footer_parts:
        return f"{response}\n\n{' | '.join(footer_parts)}"

    return response


def build_intervention_briefing(trigger_type, message, evidence=None,
                                alignment_score=None, recommendation=None):
    """
    Build a structured intervention briefing.

    Args:
        trigger_type: The intervention trigger type.
        message: Core message content.
        evidence: Optional evidence dict.
        alignment_score: Optional current alignment %.
        recommendation: Optional recommended action.

    Returns:
        str — formatted intervention briefing.
    """
    sections = [
        {'label': 'Situation', 'content': message},
    ]

    if evidence:
        risk = evidence.get('severity', evidence.get('identity_cost', 0))
        if risk:
            risk_level = 'High' if risk > 70 else 'Moderate' if risk > 40 else 'Low'
            sections.append({'label': 'Risk Level', 'content': risk_level})

        impact = evidence.get('impact_description', '')
        if impact:
            sections.append({
                'label': 'Impact Forecast',
                'content': impact,
                'optional': True,
            })

    if recommendation:
        sections.append({'label': 'Recommendation', 'content': recommendation})

    if alignment_score is not None:
        sections.append({
            'label': 'Alignment',
            'content': f'{alignment_score}%',
            'optional': True,
        })

    return format_briefing(sections)
