# ==============================================================================
# File: apps/core/ai_insights/compensatory.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Compensatory Reasoning Engine — commitment vs actual analysis
# Created: 2026-03-14 (Architecture Evolution Phase 6)
# ==============================================================================
"""
CompensatoryReasoningService — Compensatory Reasoning Engine

Compares planned commitments (from DailyScheduleService) against actual activity
(from DailyActivityService / SignalSnapshots) to produce safe, hedged compensatory
analysis using verified signals only.

Architecture: Three-layer safety model:
    Layer 1: Hard gate — Non-compensable commitments (medication, non_negotiable)
    Layer 2: Allowlist — Explicit compensatory pairs with max_offset_pct
    Layer 3: Beth prompt rules — Language framing (handled in Phase 8)

Part of the WLJ Architecture Evolution — Layer 5 support (Beth Reasoning).
"""

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Layer 1 — Hard Gate: Non-Compensable Rules
# =============================================================================

NON_COMPENSABLE_RULES = {
    # Domain-level blocks — these signal types can never be compensated
    'medication_adherence': 'Medication adherence cannot be offset by other activities.',
}

# Any commitment with commitment_level='non_negotiable' is also non-compensable
# (handled in _check_non_compensable)


# =============================================================================
# Layer 2 — Allowlist: Explicit Compensatory Pairs
# =============================================================================

COMPENSATORY_PAIRS = [
    {
        'missed_domain': 'health',
        'missed_signal': 'health_activity',
        'compensating_signal': 'health_activity',
        'max_offset_pct': 0.50,
        'rationale': 'Steps/walking partially compensate for missed structured exercise.',
        'requires_signal_class': ['verified_action', 'verified_measurement'],
    },
    {
        'missed_domain': 'health',
        'missed_signal': 'health_activity',
        'compensating_signal': 'mental_reflection',
        'max_offset_pct': 0.15,
        'rationale': 'Reflecting on health shows awareness but does not replace exercise.',
        'requires_signal_class': [
            'verified_action', 'verified_measurement', 'inferred_behavior',
        ],
    },
    {
        'missed_domain': 'faith',
        'missed_signal': 'faith_practice',
        'compensating_signal': 'faith_practice',
        'max_offset_pct': 0.30,
        'rationale': 'Prayer supports faith growth but reading has independent value.',
        'requires_signal_class': ['verified_action'],
    },
    {
        'missed_domain': 'mind',
        'missed_signal': 'mental_reflection',
        'compensating_signal': 'faith_practice',
        'max_offset_pct': 0.25,
        'rationale': 'Scripture reading supports mental reflection but is not equivalent.',
        'requires_signal_class': ['verified_action'],
    },
]


class CompensatoryReasoningService:
    """
    Compensatory Reasoning Engine.

    Compares planned commitments against actual activity and produces
    safe compensatory analysis following the three-layer safety model.

    Usage:
        gaps = CompensatoryReasoningService.analyze_commitment_gap(user, date)
        for gap in gaps:
            if gap['is_compensable'] and gap['compensating_signals']:
                # Beth can frame partial progress
                print(gap['framing'])
    """

    @staticmethod
    def analyze_commitment_gap(user, date):
        """
        Compare DailyScheduleService (planned) vs DailyActivityService (actual).

        Returns list of gap analyses for missed commitments:
        {
            commitment: dict,              # The missed commitment
            compensating_signals: list,     # Signals that partially offset
            net_assessment: str,            # 'positive_partial', 'negative', 'neutral'
            offset_pct: float,             # 0.0-1.0 actual offset achieved
            framing: str,                  # Pre-built text for Beth
            is_compensable: bool,          # False for non-negotiable/medication
        }
        """
        from apps.dashboard.services.daily_schedule_service import DailyScheduleService
        from apps.dashboard.services.daily_activity_service import DailyActivityService

        try:
            schedule = DailyScheduleService.get_daily_schedule(user, date)
            activity = DailyActivityService.get_daily_activity(user, date)
        except Exception as e:
            logger.warning(
                "Failed to load schedule/activity for compensatory analysis "
                "user=%s date=%s: %s", user.pk, date, e,
            )
            return []

        # Identify missed commitments
        missed = CompensatoryReasoningService._find_missed_commitments(
            schedule, activity,
        )

        results = []
        for commitment in missed:
            gap = CompensatoryReasoningService._analyze_single_gap(
                user, date, commitment,
            )
            results.append(gap)

        return results

    @staticmethod
    def _find_missed_commitments(schedule, activity):
        """
        Compare schedule against activity to find missed commitments.

        A commitment is "missed" if no matching activity record exists.
        Match is by source_type + source_id overlap.
        """
        # Build set of completed source identifiers
        completed_keys = set()
        for act in activity:
            key = f"{act.get('source_type', '')}:{act.get('source_id', '')}"
            completed_keys.add(key)

        missed = []
        for item in schedule:
            key = f"{item.get('source_type', '')}:{item.get('source_id', '')}"
            status = item.get('status', 'scheduled')

            # Skip if already completed or cancelled
            if status in ('completed', 'canceled', 'cancelled'):
                continue
            if key in completed_keys:
                continue

            missed.append(item)

        return missed

    @staticmethod
    def _analyze_single_gap(user, date, commitment):
        """Analyze a single missed commitment for compensatory signals."""
        domain = commitment.get('domain', '')
        commitment_level = commitment.get('commitment_level', 'optional')

        # Layer 1: Hard gate
        is_non_compensable = CompensatoryReasoningService._check_non_compensable(
            commitment,
        )

        if is_non_compensable:
            return {
                'commitment': commitment,
                'compensating_signals': [],
                'net_assessment': 'negative',
                'offset_pct': 0.0,
                'framing': (
                    f"You missed: {commitment.get('title', 'a commitment')}. "
                    "No compensatory offset applies."
                ),
                'is_compensable': False,
            }

        # Layer 2: Find compensating signals from allowlist
        compensating = CompensatoryReasoningService._find_compensating_signals(
            domain, commitment, user, date,
        )

        # Calculate total offset
        total_offset = sum(c['offset_pct'] for c in compensating)
        total_offset = min(1.0, total_offset)  # Cap at 100%

        # Determine net assessment
        if total_offset >= 0.3:
            net_assessment = 'positive_partial'
        elif total_offset > 0:
            net_assessment = 'neutral'
        else:
            net_assessment = 'negative'

        # Build framing text
        framing = CompensatoryReasoningService._build_framing(
            commitment, compensating, total_offset, net_assessment,
        )

        return {
            'commitment': commitment,
            'compensating_signals': compensating,
            'net_assessment': net_assessment,
            'offset_pct': round(total_offset, 3),
            'framing': framing,
            'is_compensable': True,
        }

    @staticmethod
    def _check_non_compensable(commitment):
        """
        Hard gate: returns True if commitment cannot be compensated.

        Non-compensable conditions:
        1. Source type maps to a non-compensable signal (e.g., medication)
        2. commitment_level is 'non_negotiable'
        """
        # Check commitment_level
        if commitment.get('commitment_level') == 'non_negotiable':
            return True

        # Check source_type mapping
        source_type = commitment.get('source_type', '')
        # Medicine schedules are always non-compensable
        if source_type in ('medicine_schedule', 'SOURCE_MEDICINE_SCHEDULE'):
            return True

        # Check domain-based non-compensable rules
        domain = commitment.get('domain', '')
        # Map source types to signal types for rule lookup
        signal_type = CompensatoryReasoningService._source_to_signal_type(
            source_type, domain,
        )
        if signal_type in NON_COMPENSABLE_RULES:
            return True

        return False

    @staticmethod
    def _source_to_signal_type(source_type, domain):
        """Map CalendarEvent source_type to signal taxonomy signal_type."""
        mapping = {
            'medicine_schedule': 'medication_adherence',
            'SOURCE_MEDICINE_SCHEDULE': 'medication_adherence',
            'workout_schedule': 'health_activity',
            'SOURCE_WORKOUT_SCHEDULE': 'health_activity',
            'faith_routine': 'faith_practice',
            'SOURCE_FAITH_ROUTINE': 'faith_practice',
            'habit': 'productivity_progress',
            'SOURCE_HABIT': 'productivity_progress',
            'task': 'productivity_progress',
            'SOURCE_TASK': 'productivity_progress',
        }
        if source_type in mapping:
            return mapping[source_type]

        # Fallback: infer from domain
        domain_signal = {
            'health': 'health_activity',
            'faith': 'faith_practice',
            'mind': 'mental_reflection',
            'life': 'productivity_progress',
            'work': 'productivity_progress',
            'finance': 'financial_health',
            'relationships': 'relational_engagement',
        }
        return domain_signal.get(domain, '')

    @staticmethod
    def _find_compensating_signals(missed_domain, commitment, user, date):
        """
        Find allowlisted compensating signals with verified signal_class.

        Queries SignalSnapshot for the date and checks against COMPENSATORY_PAIRS.
        Only returns signals whose signal_class is in the pair's requires_signal_class.
        """
        from apps.core.ai_eae.models import SignalSnapshot

        source_type = commitment.get('source_type', '')
        missed_signal = CompensatoryReasoningService._source_to_signal_type(
            source_type, missed_domain,
        )

        if not missed_signal:
            return []

        # Find applicable compensatory pairs
        applicable_pairs = [
            pair for pair in COMPENSATORY_PAIRS
            if pair['missed_domain'] == missed_domain
            and pair['missed_signal'] == missed_signal
        ]

        if not applicable_pairs:
            return []

        # Get all signals for this user/date
        snapshots = {
            s.signal_type: s
            for s in SignalSnapshot.objects.filter(user=user, date=date)
        }

        compensating = []
        for pair in applicable_pairs:
            comp_signal = pair['compensating_signal']

            # Skip if the compensating signal is the same as the missed one
            # and refers to the exact same source (self-compensation)
            # But allow same signal_type if different source (e.g., walking
            # compensating for missed gym workout — both health_activity)
            snapshot = snapshots.get(comp_signal)
            if not snapshot:
                continue

            # Gate: signal_class must be in the pair's required classes
            if snapshot.signal_class not in pair['requires_signal_class']:
                logger.debug(
                    "Signal %s has class %s, not in required %s — skipping",
                    comp_signal, snapshot.signal_class,
                    pair['requires_signal_class'],
                )
                continue

            # Calculate offset: signal score * max_offset_pct
            offset = snapshot.score * pair['max_offset_pct']

            compensating.append({
                'signal_type': comp_signal,
                'signal_class': snapshot.signal_class,
                'signal_score': snapshot.score,
                'max_offset_pct': pair['max_offset_pct'],
                'offset_pct': round(offset, 3),
                'rationale': pair['rationale'],
                'source_signals': snapshot.source_signals,
            })

        return compensating

    @staticmethod
    def _build_framing(commitment, compensating, total_offset, net_assessment):
        """
        Build pre-framed text for Beth to use in responses.

        Follows compensatory reasoning language rules:
        - Never "okay" or "fully replaced"
        - Maximum: "partially offset"
        - Forward guidance always included
        - Double-hedge for inferred_behavior
        """
        title = commitment.get('title', 'a commitment')

        if not compensating:
            return (
                f"You missed: {title}. No compensating activity was detected today."
            )

        # Build compensating activity descriptions
        comp_descriptions = []
        has_inferred = False
        for c in compensating:
            signal_label = c['signal_type'].replace('_', ' ').title()
            score_pct = int(c['signal_score'] * 100)

            if c['signal_class'] == 'inferred_behavior':
                has_inferred = True
                comp_descriptions.append(
                    f"it seems like you engaged in {signal_label} "
                    f"(~{score_pct}% level, based on journal)"
                )
            else:
                comp_descriptions.append(
                    f"you showed {signal_label} activity "
                    f"({score_pct}% level)"
                )

        comp_text = "; ".join(comp_descriptions)
        offset_pct_display = int(total_offset * 100)

        # Build the framing
        if has_inferred:
            # Double-hedge for inferred behavior
            framing = (
                f"While you missed {title}, {comp_text}. "
                f"This may partially offset the gap (~{offset_pct_display}%), "
                f"though the evidence is indirect."
            )
        elif net_assessment == 'positive_partial':
            framing = (
                f"While you missed {title}, {comp_text}. "
                f"This partially offsets the gap (~{offset_pct_display}%)."
            )
        else:
            framing = (
                f"While you missed {title}, {comp_text}. "
                f"This provides a small offset (~{offset_pct_display}%)."
            )

        # Always add forward guidance
        domain = commitment.get('domain', '')
        domain_label = domain.replace('_', ' ').title() if domain else 'this area'
        framing += f" Tomorrow, let's aim to get back on track with {domain_label}."

        return framing

    @staticmethod
    def get_daily_gap_summary(user, date):
        """
        High-level summary for CoS context injection.

        Returns a dict suitable for adding to the CoS context:
        {
            'date': str,
            'total_missed': int,
            'compensable_count': int,
            'non_compensable_count': int,
            'positive_partial_count': int,
            'gaps': [gap_dict, ...],
        }
        """
        gaps = CompensatoryReasoningService.analyze_commitment_gap(user, date)

        return {
            'date': str(date),
            'total_missed': len(gaps),
            'compensable_count': sum(1 for g in gaps if g['is_compensable']),
            'non_compensable_count': sum(
                1 for g in gaps if not g['is_compensable']
            ),
            'positive_partial_count': sum(
                1 for g in gaps if g['net_assessment'] == 'positive_partial'
            ),
            'gaps': gaps,
        }
