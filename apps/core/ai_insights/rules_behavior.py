"""
Behavior Score PIE rules — cross-domain behavioral adherence signals.

Rules:
  1. BehaviorScoreDropRule — warning when 7-day score drops below threshold
  2. BehaviorDomainWeaknessRule — info when a single domain is significantly weaker
  3. BehaviorMultiDomainDeclineRule — warning when 2+ domains declining
"""

import logging
from datetime import timedelta

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.rule_registry import register
from apps.core.ai_insights.utils import build_dedupe_key

logger = logging.getLogger(__name__)

# Minimum total expected occurrences across all domains before signals fire.
# Prevents false positives from low data volume.
_MIN_EXPECTED_THRESHOLD = 5


@register
class BehaviorScoreDropRule(BaseInsightRule):
    """Warning when 7-day composite behavior score is below 60%."""

    rule_name = "behavior_score_drop"
    module = "life"
    insight_type = "behavior_score_drop"
    severity = "warning"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        try:
            from apps.core.behavior.behavior_score_engine import compute_behavior_score_7d
            result = compute_behavior_score_7d(user)
            score = result.get('score')
            if score is None:
                return []

            domains = result.get('domains', [])
            total_expected = sum(d.get('expected', 0) for d in domains)
            if total_expected < _MIN_EXPECTED_THRESHOLD:
                return []  # Not enough data to fire signal
            if score >= 60:
                return []

            weakest = result.get('weakest_domain', '')

            from django.utils import timezone
            today = timezone.now().date()

            return [{
                'insight_type': self.insight_type,
                'module': self.module,
                'severity': self.severity,
                'title': f'Behavior score below threshold ({score:.0f}%)',
                'message': (
                    f'Your 7-day behavior score is {score:.0f}%. '
                    f'Weakest area: {weakest}.'
                ),
                'explain_why': (
                    'Behavior score measures consistency across medication, '
                    'workout, and routine adherence.'
                ),
                'confidence_score': min(0.9, 1.0 - (score / 100)),
                'evidence': {
                    'rule_name': self.rule_name,
                    'score': score,
                    'weakest_domain': weakest,
                    'domain_count': len(domains),
                },
                'dedupe_key': build_dedupe_key(
                    user.id, self.insight_type, str(today)
                ),
            }]
        except Exception as e:
            logger.warning("BehaviorScoreDropRule failed: %s", e, exc_info=True)
            return []


@register
class BehaviorDomainWeaknessRule(BaseInsightRule):
    """Info when one domain is significantly weaker than the composite."""

    rule_name = "behavior_domain_weakness"
    module = "life"
    insight_type = "behavior_domain_weakness"
    severity = "info"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        try:
            from apps.core.behavior.behavior_score_engine import compute_behavior_score_7d
            result = compute_behavior_score_7d(user)
            score = result.get('score')
            if score is None:
                return []

            domains = result.get('domains', [])
            total_expected = sum(d.get('expected', 0) for d in domains)
            if total_expected < _MIN_EXPECTED_THRESHOLD:
                return []
            if len(domains) < 2:
                return []

            from django.utils import timezone
            today = timezone.now().date()

            insights = []
            for d in domains:
                d_adherence = d.get('adherence')
                if d_adherence is None:
                    continue
                gap = score - d_adherence
                if gap >= 20:  # domain is 20+ points below composite
                    insights.append({
                        'insight_type': self.insight_type,
                        'module': self.module,
                        'severity': self.severity,
                        'title': f'{d["domain"].title()} adherence is lagging',
                        'message': (
                            f'{d["domain"].title()} adherence ({d_adherence:.0f}%) is '
                            f'significantly below your overall score ({score:.0f}%).'
                        ),
                        'explain_why': (
                            f'{d["domain"].title()} has {d["missed"]} missed and '
                            f'{d["late"]} late out of {d["expected"]} expected.'
                        ),
                        'confidence_score': min(0.8, gap / 50),
                        'evidence': {
                            'rule_name': self.rule_name,
                            'domain': d['domain'],
                            'domain_adherence': d_adherence,
                            'composite_score': score,
                            'gap': gap,
                        },
                        'dedupe_key': build_dedupe_key(
                            user.id, self.insight_type, d['domain'], str(today)
                        ),
                    })
            return insights
        except Exception as e:
            logger.warning("BehaviorDomainWeaknessRule failed: %s", e, exc_info=True)
            return []


@register
class BehaviorMultiDomainDeclineRule(BaseInsightRule):
    """Warning when 2+ domains have adherence below 50%."""

    rule_name = "behavior_multi_domain_decline"
    module = "life"
    insight_type = "behavior_multi_domain_decline"
    severity = "warning"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        try:
            from apps.core.behavior.behavior_score_engine import compute_behavior_score_7d
            result = compute_behavior_score_7d(user)
            domains = result.get('domains', [])

            total_expected = sum(d.get('expected', 0) for d in domains)
            if total_expected < _MIN_EXPECTED_THRESHOLD:
                return []

            weak_domains = [
                d for d in domains
                if d.get('adherence') is not None and d['adherence'] < 50
            ]
            if len(weak_domains) < 2:
                return []

            from django.utils import timezone
            today = timezone.now().date()

            domain_names = ', '.join(d['domain'].title() for d in weak_domains)

            return [{
                'insight_type': self.insight_type,
                'module': self.module,
                'severity': self.severity,
                'title': f'Multiple behavioral domains declining',
                'message': (
                    f'{len(weak_domains)} domains below 50% adherence: '
                    f'{domain_names}.'
                ),
                'explain_why': (
                    'When multiple behavioral domains decline simultaneously, '
                    'it may indicate a broader pattern disruption.'
                ),
                'confidence_score': 0.8,
                'evidence': {
                    'rule_name': self.rule_name,
                    'weak_domains': [
                        {'domain': d['domain'], 'adherence': d['adherence']}
                        for d in weak_domains
                    ],
                },
                'dedupe_key': build_dedupe_key(
                    user.id, self.insight_type, str(today)
                ),
            }]
        except Exception as e:
            logger.warning("BehaviorMultiDomainDeclineRule failed: %s", e, exc_info=True)
            return []
