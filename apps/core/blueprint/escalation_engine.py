"""
Whole Life Journey - Escalation Engine (Phase 3)

Path: apps/core/blueprint/escalation_engine.py
Purpose: Persistent escalation continuity, recovery gate, behavioral trends.

Phase 3 policy:
    - Escalation can increase immediately if thresholds demand.
    - De-escalation requires the Hybrid Recovery Rule (all 5 criteria).
    - Threshold overrides are supreme (always escalate if met).
    - EscalationState acts as a FLOOR for activation state.
    - All time usage via single time authority (Phase 2).

Public API:
    - resolve_activation_state(user, trajectory_signals, user_input) -> str
    - compute_recovery_eligibility(user, reference_time) -> (bool, dict)
    - update_daily_escalation_state(user) -> None
    - compute_behavioral_trends(user) -> list[BehavioralTrend]
"""

import datetime
import logging

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


# =========================================================================
# CONSTANTS — map to cos_context.py activation labels
# =========================================================================

ACTIVATION_CLEAN = 'CLEAN'
ACTIVATION_EARLY_EROSION = 'EARLY_EROSION'
ACTIVATION_STRUCTURAL_DRIFT = 'STRUCTURAL_DRIFT'

STATE_TO_LEVEL = {
    ACTIVATION_CLEAN: 0,
    ACTIVATION_EARLY_EROSION: 1,
    ACTIVATION_STRUCTURAL_DRIFT: 2,
}

LEVEL_TO_STATE = {v: k for k, v in STATE_TO_LEVEL.items()}


# =========================================================================
# STEP 2 — RECOVERY GATE (Hybrid Recovery Rule)
# =========================================================================


def compute_recovery_eligibility(user, reference_time=None):
    """
    Determine if user is eligible for one-level de-escalation.

    All 5 criteria must be met over the last 7 days:
    1) 7 consecutive clean days (no drift threshold events, no Tier 1 misses,
       no blocked renegotiations)
    2) >= 3 honored commitments in window
    3) 0 Tier 1 misses (missed blocks) in window
    4) 0 blocked renegotiations in window
    5) 0 new drift threshold events in window

    Args:
        user: User instance.
        reference_time: datetime (timezone-aware). Defaults to now via
                        single time authority.

    Returns:
        (eligible: bool, reasons: dict)
    """
    if reference_time is None:
        reference_time = _get_reference_time(user)

    window_start = reference_time - datetime.timedelta(days=7)
    reasons = {}

    # --- Criterion 1 & 5: drift threshold events in window ---
    from .models import DriftEvent
    drift_events_count = DriftEvent.objects.filter(
        user=user,
        occurred_at__gte=window_start,
        occurred_at__lte=reference_time,
    ).count()
    reasons['drift_events_in_window'] = drift_events_count
    criterion_5 = drift_events_count == 0

    # --- Criterion 2: >= 3 honored commitments ---
    from .models import Commitment
    honored_count = Commitment.objects.filter(
        user=user,
        status=Commitment.STATUS_CLOSED_SUCCESS,
        updated_at__gte=window_start,
        updated_at__lte=reference_time,
    ).count()
    reasons['honored_commitments'] = honored_count
    criterion_2 = honored_count >= 3

    # --- Criterion 3: 0 Tier 1 misses ---
    # Tier 1 misses = DriftEvents with tier=1 in window
    tier1_misses = DriftEvent.objects.filter(
        user=user,
        tier=1,
        occurred_at__gte=window_start,
        occurred_at__lte=reference_time,
    ).count()
    reasons['tier1_misses'] = tier1_misses
    criterion_3 = tier1_misses == 0

    # --- Criterion 4: 0 blocked renegotiations ---
    from .models import CommitmentRenegotiation
    blocked_reneg = CommitmentRenegotiation.objects.filter(
        commitment__user=user,
        was_blocked=True,
        created_at__gte=window_start,
        created_at__lte=reference_time,
    ).count()
    reasons['blocked_renegotiations'] = blocked_reneg
    criterion_4 = blocked_reneg == 0

    # --- Criterion 1: 7 consecutive clean days ---
    # A "clean day" has no drift events, no Tier 1 misses, no blocked reneg.
    # We check each of the 7 days individually.
    clean_day_count = 0
    for day_offset in range(7):
        day = (reference_time - datetime.timedelta(days=day_offset)).date()
        day_start = datetime.datetime.combine(
            day, datetime.time.min, tzinfo=reference_time.tzinfo,
        )
        day_end = datetime.datetime.combine(
            day, datetime.time.max, tzinfo=reference_time.tzinfo,
        )

        day_drift = DriftEvent.objects.filter(
            user=user,
            occurred_at__gte=day_start,
            occurred_at__lte=day_end,
        ).exists()

        day_blocked = CommitmentRenegotiation.objects.filter(
            commitment__user=user,
            was_blocked=True,
            created_at__gte=day_start,
            created_at__lte=day_end,
        ).exists()

        if not day_drift and not day_blocked:
            clean_day_count += 1
        else:
            break  # Consecutive = must not break chain

    reasons['consecutive_clean_days'] = clean_day_count
    criterion_1 = clean_day_count >= 7

    eligible = all([criterion_1, criterion_2, criterion_3, criterion_4, criterion_5])
    reasons['eligible'] = eligible
    reasons['criteria'] = {
        'consecutive_clean_days_met': criterion_1,
        'honored_commitments_met': criterion_2,
        'zero_tier1_misses_met': criterion_3,
        'zero_blocked_renegotiations_met': criterion_4,
        'zero_drift_events_met': criterion_5,
    }

    return eligible, reasons


# =========================================================================
# STEP 3 — ACTIVATION INTEGRATION (floor + asymmetric up/down)
# =========================================================================


def resolve_activation_state(user, trajectory_signals, user_input=''):
    """
    Phase 3 activation resolver with persistent escalation floor.

    1. Compute current_state from trajectory_signals + user_input (existing logic).
    2. Fetch or create EscalationState.
    3. Apply threshold override supremacy.
    4. Apply floor rule (no silent downgrade).
    5. De-escalation only via Hybrid Recovery Rule.
    6. Record transitions as EscalationEvents.
    7. Write DecisionRecord for observability.

    Args:
        user: User instance.
        trajectory_signals: dict from _build_trajectory_signals().
        user_input: str — current user message.

    Returns:
        str — CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT
    """
    from .models import EscalationState, EscalationEvent

    # A) Compute from existing logic (unchanged semantics)
    computed_state = _compute_activation_from_signals(trajectory_signals, user_input)
    computed_level = STATE_TO_LEVEL.get(computed_state, 0)

    reference_time = _get_reference_time(user)

    # B) Fetch or create EscalationState
    with transaction.atomic():
        esc_state, created = EscalationState.objects.select_for_update().get_or_create(
            user=user,
        )

        previous_level = esc_state.current_level

        # C) Threshold override supremacy: if computed is higher, escalate immediately
        if computed_level > esc_state.current_level:
            esc_state.current_level = computed_level
            esc_state.last_escalation_at = reference_time
            esc_state.consecutive_clean_days = 0
            esc_state.save()

            EscalationEvent.objects.create(
                user=user,
                from_level=previous_level,
                to_level=computed_level,
                trigger=EscalationEvent.TRIGGER_THRESHOLD_OVERRIDE,
                rationale={
                    'computed_state': computed_state,
                    'trajectory_signals_summary': _summarize_signals(trajectory_signals),
                    'user_input_had_erosion': bool(_detect_erosion_markers(user_input)),
                },
            )
            _write_decision_record(
                user, previous_level, computed_level, computed_level,
                trigger='THRESHOLD_OVERRIDE',
                recovery_eligible=False,
                recovery_reasons={},
                floor_applied=False,
            )
            return LEVEL_TO_STATE[computed_level]

        # D+E) Floor rule + de-escalation gate
        if computed_level < esc_state.current_level:
            # Attempt de-escalation — check recovery gate
            eligible, reasons = compute_recovery_eligibility(user, reference_time)

            if eligible:
                # Allow drop by exactly 1 level
                new_level = max(esc_state.current_level - 1, 0)
                esc_state.current_level = new_level
                esc_state.last_de_escalation_at = reference_time
                esc_state.save()

                EscalationEvent.objects.create(
                    user=user,
                    from_level=previous_level,
                    to_level=new_level,
                    trigger=EscalationEvent.TRIGGER_RECOVERY_DECAY,
                    rationale=reasons,
                )
                _write_decision_record(
                    user, previous_level, new_level, computed_level,
                    trigger='RECOVERY_DECAY',
                    recovery_eligible=True,
                    recovery_reasons=reasons,
                    floor_applied=False,
                )
                return LEVEL_TO_STATE[new_level]
            else:
                # Floor holds — maintain current level
                _write_decision_record(
                    user, previous_level, esc_state.current_level, computed_level,
                    trigger='FLOOR_APPLIED',
                    recovery_eligible=False,
                    recovery_reasons=reasons,
                    floor_applied=True,
                )
                return LEVEL_TO_STATE[esc_state.current_level]

        # Same level — no change, no event needed
        # But update peak if needed
        _update_peak_level(esc_state, reference_time)
        esc_state.save()

        return LEVEL_TO_STATE[esc_state.current_level]


def _compute_activation_from_signals(trajectory_signals, user_input=''):
    """
    Pure computation of activation state from trajectory signals + user input.
    Same semantics as the original determine_activation_state().
    """
    renegotiations = trajectory_signals.get('renegotiation_patterns', [])
    tier1_skips = trajectory_signals.get('tier1_skip_patterns', [])
    consecutive = trajectory_signals.get('consecutive_tier1_skips', 0)

    has_structural = (
        bool(renegotiations)
        or bool(tier1_skips)
        or consecutive >= 2
    )

    if has_structural:
        return ACTIVATION_STRUCTURAL_DRIFT

    if _detect_erosion_markers(user_input):
        return ACTIVATION_EARLY_EROSION

    return ACTIVATION_CLEAN


def _detect_erosion_markers(user_input):
    """Delegate to the canonical erosion marker detector."""
    if not user_input:
        return []
    try:
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        return detect_erosion_markers(user_input)
    except ImportError:
        return []


def _summarize_signals(trajectory_signals):
    """Create a small summary dict for logging."""
    return {
        'renegotiation_patterns': len(trajectory_signals.get('renegotiation_patterns', [])),
        'tier1_skip_patterns': len(trajectory_signals.get('tier1_skip_patterns', [])),
        'consecutive_tier1_skips': trajectory_signals.get('consecutive_tier1_skips', 0),
    }


def _update_peak_level(esc_state, reference_time):
    """Update peak_level_7d from recent events."""
    from .models import EscalationEvent

    window_start = reference_time - datetime.timedelta(days=7)
    recent_peak = EscalationEvent.objects.filter(
        user=esc_state.user,
        created_at__gte=window_start,
    ).order_by('-to_level').values_list('to_level', flat=True).first()

    peak = max(esc_state.current_level, recent_peak or 0)
    esc_state.peak_level_7d = peak


# =========================================================================
# STEP 4 — BEHAVIORAL TREND COMPUTATION
# =========================================================================


def compute_behavioral_trends(user, reference_time=None):
    """
    Deterministic daily trend computation per behavior_key.

    Compares last 7 days vs prior 7 days:
    - improving: drift events decreased AND/OR honor rate increased
    - declining: drift events increased OR Tier 1 misses increased
    - stable: otherwise

    Confidence = min(1.0, data_points / 20)

    Args:
        user: User instance.
        reference_time: datetime (timezone-aware).

    Returns:
        list of BehavioralTrend instances (saved).
    """
    from .models import BehavioralTrend, DriftEvent, Commitment

    if reference_time is None:
        reference_time = _get_reference_time(user)

    current_end = reference_time
    current_start = reference_time - datetime.timedelta(days=7)
    prior_end = current_start
    prior_start = prior_end - datetime.timedelta(days=7)

    # Get drift events grouped by behavior_key for both windows
    current_drifts = (
        DriftEvent.objects.filter(
            user=user,
            occurred_at__gte=current_start,
            occurred_at__lt=current_end,
        )
        .values('behavior_key')
        .annotate(count=Count('id'))
    )
    prior_drifts = (
        DriftEvent.objects.filter(
            user=user,
            occurred_at__gte=prior_start,
            occurred_at__lt=prior_end,
        )
        .values('behavior_key')
        .annotate(count=Count('id'))
    )

    current_map = {d['behavior_key']: d['count'] for d in current_drifts}
    prior_map = {d['behavior_key']: d['count'] for d in prior_drifts}

    # Commitment honor rates
    current_honored = Commitment.objects.filter(
        user=user,
        status=Commitment.STATUS_CLOSED_SUCCESS,
        updated_at__gte=current_start,
        updated_at__lt=current_end,
    ).count()
    prior_honored = Commitment.objects.filter(
        user=user,
        status=Commitment.STATUS_CLOSED_SUCCESS,
        updated_at__gte=prior_start,
        updated_at__lt=prior_end,
    ).count()

    # Union of all behavior keys
    all_keys = set(current_map.keys()) | set(prior_map.keys())
    if not all_keys:
        # No drift data — create a single "overall" trend
        all_keys = {'overall'}

    results = []
    for bkey in all_keys:
        curr_count = current_map.get(bkey, 0)
        prev_count = prior_map.get(bkey, 0)
        data_points = curr_count + prev_count

        # Determine direction
        if prev_count > 0 and curr_count < prev_count:
            direction = BehavioralTrend.TREND_IMPROVING
        elif curr_count > prev_count:
            direction = BehavioralTrend.TREND_DECLINING
        elif current_honored > prior_honored and curr_count <= prev_count:
            direction = BehavioralTrend.TREND_IMPROVING
        else:
            direction = BehavioralTrend.TREND_STABLE

        confidence = min(1.0, data_points / 20.0)

        trend, _ = BehavioralTrend.objects.update_or_create(
            user=user,
            behavior_key=bkey,
            defaults={
                'trend_direction': direction,
                'confidence': confidence,
                'data_points': data_points,
                'window_start': current_start.date(),
                'window_end': current_end.date(),
            },
        )
        results.append(trend)

    return results


def update_daily_escalation_state(user, reference_time=None):
    """
    Daily update of EscalationState for a user.

    Updates consecutive_clean_days and peak_level_7d.
    Called by ISE scheduler or on first message of the day.

    Args:
        user: User instance.
        reference_time: datetime (timezone-aware).
    """
    from .models import EscalationState, DriftEvent, CommitmentRenegotiation

    if reference_time is None:
        reference_time = _get_reference_time(user)

    esc_state, created = EscalationState.objects.get_or_create(user=user)

    # Compute consecutive clean days (count back from yesterday)
    clean_days = 0
    for day_offset in range(1, 31):  # Up to 30 days back
        day = (reference_time - datetime.timedelta(days=day_offset)).date()
        day_start = datetime.datetime.combine(
            day, datetime.time.min, tzinfo=reference_time.tzinfo,
        )
        day_end = datetime.datetime.combine(
            day, datetime.time.max, tzinfo=reference_time.tzinfo,
        )

        has_drift = DriftEvent.objects.filter(
            user=user,
            occurred_at__gte=day_start,
            occurred_at__lte=day_end,
        ).exists()

        has_blocked = CommitmentRenegotiation.objects.filter(
            commitment__user=user,
            was_blocked=True,
            created_at__gte=day_start,
            created_at__lte=day_end,
        ).exists()

        if not has_drift and not has_blocked:
            clean_days += 1
        else:
            break

    esc_state.consecutive_clean_days = clean_days
    _update_peak_level(esc_state, reference_time)
    esc_state.save()

    logger.info(
        "Phase 3: Updated escalation state for user %s — "
        "level=%s, clean_days=%d, peak_7d=%d",
        user.id, esc_state.current_level, clean_days, esc_state.peak_level_7d,
    )


# =========================================================================
# OBSERVABILITY — DecisionRecord integration
# =========================================================================


def _write_decision_record(
    user, from_level, to_level, computed_level,
    trigger, recovery_eligible, recovery_reasons, floor_applied,
):
    """
    Write a DecisionRecord for escalation transition observability.

    Non-blocking: failures are logged but do not interrupt pipeline.
    """
    try:
        from apps.core.ai_observability.models import DecisionRecord

        DecisionRecord.objects.create(
            decision_type='other',
            engine_name='ESC',
            decision=f"ESCALATION={LEVEL_TO_STATE.get(to_level, 'UNKNOWN')}",
            rationale=(
                f"From level {from_level} to {to_level} "
                f"(computed={computed_level}). "
                f"Trigger={trigger}. "
                f"Recovery eligible={recovery_eligible}. "
                f"Floor applied={floor_applied}."
            ),
            inputs_summary={
                'from_level': from_level,
                'to_level': to_level,
                'computed_level': computed_level,
                'trigger': trigger,
                'recovery_eligible': recovery_eligible,
                'recovery_reasons': recovery_reasons,
                'floor_applied': floor_applied,
            },
            user_id=user.id,
        )
    except Exception as e:
        logger.warning("Phase 3: Failed to write DecisionRecord: %s", e)


# =========================================================================
# HELPERS — time authority
# =========================================================================


def _get_reference_time(user=None):
    """Single time authority — reuse Phase 2 pattern."""
    if user:
        try:
            from apps.core.utils import get_current_local_datetime
            return get_current_local_datetime(user)
        except Exception:
            pass
    return timezone.now()
