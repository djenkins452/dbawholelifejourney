# ==============================================================================
# File: apps/core/ai_insights/rules_compensatory.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Compensatory Progress PIE rule
# Created: 2026-03-14 (Architecture Evolution Phase 6)
# ==============================================================================
"""
Compensatory Progress Rule — fires when compensatory analysis finds
positive partial offset for a missed commitment.

Produces insights with severity 'positive' and type 'compensatory_progress'.
"""

import logging

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.rule_registry import register

logger = logging.getLogger(__name__)


@register
class CompensatoryProgressRule(BaseInsightRule):
    """
    Detects when a user has missed a commitment but compensating signals
    indicate partial progress, and generates a positive insight.

    Fires on scheduled_check events (nightly batch) or on explicit
    compensatory analysis triggers.
    """

    rule_name = "compensatory_progress"
    module = "core"
    insight_type = "compensatory_progress"
    min_confidence_to_store = 0.5
    min_confidence_to_notify = 0.7

    def applies(self, user, event):
        return event.get("action") in (
            "scheduled_check",
            "compensatory_analysis",
        )

    def evaluate(self, user, event):
        from apps.core.utils import get_user_today
        from apps.core.ai_insights.compensatory import CompensatoryReasoningService

        date = event.get("date") or get_user_today(user)

        try:
            gaps = CompensatoryReasoningService.analyze_commitment_gap(user, date)
        except Exception as e:
            logger.warning(
                "Compensatory analysis failed for user %s: %s",
                user.pk, e, exc_info=True,
            )
            return []

        insights = []
        for gap in gaps:
            # Only generate insights for positive partial offsets
            if gap['net_assessment'] != 'positive_partial':
                continue
            if not gap['is_compensable']:
                continue

            commitment_title = gap['commitment'].get('title', 'a commitment')
            domain = gap['commitment'].get('domain', 'general')
            offset_pct = int(gap['offset_pct'] * 100)

            # Build compensating signal summary
            comp_summary = ", ".join(
                c['signal_type'].replace('_', ' ')
                for c in gap['compensating_signals']
            )

            insights.append({
                'severity': 'positive',
                'title': f'Partial progress despite missed {domain} commitment',
                'message': gap['framing'],
                'confidence_score': min(
                    0.9,
                    0.5 + gap['offset_pct'],
                ),
                'explain_why': (
                    f"You missed \"{commitment_title}\" but compensating "
                    f"activity ({comp_summary}) provided ~{offset_pct}% offset. "
                    f"This shows continued engagement in {domain}."
                ),
                'evidence': {
                    'commitment': {
                        'title': commitment_title,
                        'domain': domain,
                        'commitment_level': gap['commitment'].get(
                            'commitment_level', 'optional',
                        ),
                    },
                    'compensating_signals': [
                        {
                            'signal_type': c['signal_type'],
                            'signal_class': c['signal_class'],
                            'score': c['signal_score'],
                            'offset_pct': c['offset_pct'],
                        }
                        for c in gap['compensating_signals']
                    ],
                    'total_offset_pct': gap['offset_pct'],
                    'date': str(date),
                },
                'dedupe_key': build_dedupe_key(
                    'compensatory_progress',
                    user.pk,
                    f"{domain}:{commitment_title}:{date}",
                ),
            })

        return insights
