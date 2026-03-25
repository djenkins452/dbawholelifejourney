"""
Behavior Score PIE rules — cross-domain behavioral adherence signals.

Rules:
  1. BehaviorScoreDropRule — warning when 7-day score drops below threshold
  2. BehaviorDomainWeaknessRule — info when a single domain is significantly weaker
  3. BehaviorMultiDomainDeclineRule — warning when 2+ domains declining
  4. FoundationalPatternBreakRule — warning on repeated foundational misses (3-day)
"""

import logging
from datetime import timedelta

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.rule_registry import register
from apps.core.ai_insights.models import build_dedupe_key

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


# ── Related signal types that may explain a behavioral pattern break ──
# These are insight_types from OTHER rules that fire independently.
# If present alongside a pattern break, they provide causal context.
_CONTEXT_SIGNAL_TYPES = {
    'motivation_drift',
    'overtraining_risk',
    'behavioral_instability',
    'compliance_risk',
    'financial_anxiety_cluster',
    'overextension_risk',
    # Context signals (rules_context.py)
    'injury_detected',
    'illness_detected',
    'fatigue_detected',
    'travel_active',
}


@register
class FoundationalPatternBreakRule(BaseInsightRule):
    """
    Warning when foundational commitments are repeatedly missed in a tight window.

    Triggers on:
      - Same domain: ≥2 missed in 3 days
      - Cross-domain: ≥3 missed total in 3 days

    Enriched with any related signals already in the system (motivation_drift,
    overtraining_risk, etc). Does NOT scan raw data — only reads existing signals.
    """

    rule_name = "foundational_pattern_break"
    module = "life"
    insight_type = "foundational_pattern_break"
    severity = "warning"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        try:
            from apps.core.behavior.behavior_score_engine import compute_behavior_score
            from apps.core.utils import get_user_today

            today = get_user_today(user)
            start_3d = today - timedelta(days=3)

            # Get 3-day behavior data
            result = compute_behavior_score(user, start_3d, today)
            domains = result.get('domains', [])
            if not domains:
                return []

            # Check triggers
            total_missed_3d = 0
            same_domain_break = False
            affected_domains = []

            for d in domains:
                missed = d.get('missed', 0)
                total_missed_3d += missed
                if missed >= 2:
                    same_domain_break = True
                    affected_domains.append(d['domain'])

            cross_domain_break = total_missed_3d >= 3

            if not same_domain_break and not cross_domain_break:
                return []

            # All domains with misses
            if not affected_domains:
                affected_domains = [
                    d['domain'] for d in domains if d.get('missed', 0) > 0
                ]

            # ── Enrich with related signals (ONLY existing signals) ──
            related_signals = self._gather_related_signals(user)

            # ── Build coaching context ──
            from django.utils import timezone
            today_str = str(timezone.now().date())

            domain_names = ', '.join(d.title() for d in affected_domains)
            has_context = bool(related_signals)

            if has_context:
                context_summary = '; '.join(
                    s['title'] for s in related_signals[:3]
                )
                message = (
                    f"Foundational items missed in {domain_names} "
                    f"({total_missed_3d} in 3 days). "
                    f"Possibly related: {context_summary}."
                )
            else:
                message = (
                    f"Foundational items missed in {domain_names} "
                    f"({total_missed_3d} in 3 days). "
                    f"No clear contextual signals — check in with the user."
                )

            return [{
                'insight_type': self.insight_type,
                'module': self.module,
                'severity': self.severity,
                'title': 'Foundational pattern break detected',
                'message': message,
                'explain_why': (
                    'Multiple foundational commitments missed in a short window '
                    'may indicate a life disruption, stress, illness, or need to '
                    'adjust the plan. Ask — do not assume.'
                ),
                'confidence_score': 0.75 if has_context else 0.60,
                'evidence': {
                    'rule_name': self.rule_name,
                    'affected_domains': affected_domains,
                    'total_missed_3d': total_missed_3d,
                    'same_domain_break': same_domain_break,
                    'cross_domain_break': cross_domain_break,
                    'related_signals': [
                        {'type': s['type'], 'title': s['title']}
                        for s in related_signals
                    ],
                    'has_context': has_context,
                    # Coaching directive for Beth
                    'coaching_mode': 'contextual' if has_context else 'open_inquiry',
                },
                'dedupe_key': build_dedupe_key(
                    user.id, self.insight_type, today_str
                ),
            }]

        except Exception as e:
            logger.warning("FoundationalPatternBreakRule failed: %s", e, exc_info=True)
            return []

    def _gather_related_signals(self, user):
        """
        Gather EXISTING signals that may explain a behavioral break.

        Reads from:
          1. Active PIE insights (recent, matching context types)
          2. SAE state (sleep, mood — pre-computed, no raw queries)

        Does NOT query raw data. Architecture-compliant.
        """
        related = []

        # 1. Check for active context insights from other engines
        try:
            from apps.core.ai_insights.models import Insight
            from django.utils import timezone as _tz

            cutoff = _tz.now() - timedelta(hours=72)
            context_insights = Insight.objects.filter(
                user=user,
                status__in=['new', 'read'],
                created_at__gte=cutoff,
                insight_type__in=_CONTEXT_SIGNAL_TYPES,
            ).order_by('-created_at')[:5]

            for i in context_insights:
                related.append({
                    'type': i.insight_type,
                    'title': i.title,
                    'severity': i.severity,
                    'source': 'insight',
                })
        except Exception:
            pass

        # 2. Check SAE state for sleep and mood indicators
        try:
            from apps.core.ai_state import get_module_state

            health_state = get_module_state(user, 'health')
            if health_state:
                sleep_avg = health_state.get('sleep_avg_duration_7d')
                if sleep_avg and sleep_avg < 390:  # < 6.5 hours
                    related.append({
                        'type': 'sleep_deficit',
                        'title': f'Sleep averaging {sleep_avg // 60}h {sleep_avg % 60}m (below 6.5h)',
                        'severity': 'info',
                        'source': 'state',
                    })

            journal_state = get_module_state(user, 'journal')
            if journal_state:
                last_mood = journal_state.get('last_mood')
                if last_mood and last_mood in ('low', 'very_low', 'anxious', 'sad', 'stressed'):
                    related.append({
                        'type': 'mood_low',
                        'title': f'Recent mood: {last_mood}',
                        'severity': 'info',
                        'source': 'state',
                    })
        except Exception:
            pass

        return related
