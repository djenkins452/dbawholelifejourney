"""
EAE — Executive Arbitration Engine (Phase 8.5).

Main arbitration pipeline. This is the single entry point for all arbitration
decisions. Chains: collect → score → dedup → bundle → override filter →
budget → escalation → tone → focus → format → audit.

Public API:
    arbitrate(user, channel, ...) -> EAEResult
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from django.utils import timezone

from apps.core.ai_eae.budget import apply_budget
from apps.core.ai_eae.bundler import CognitiveUnit, bundle_signals
from apps.core.ai_eae.constants import (
    CHANNEL_CHAT,
    CROSS_CHANNEL_DEDUP_HOURS,
    DEFAULT_INTENSITY_MULTIPLIER,
    get_intensity,
)
from apps.core.ai_eae.dedup import deduplicate
from apps.core.ai_eae.escalation import evaluate_escalation
from apps.core.ai_eae.focus import ensure_focus_in_units, evaluate_focus
from apps.core.ai_eae.formatter import (
    format_for_prompt,
    format_suppressed_for_audit,
)
from apps.core.ai_eae.models import EAEDecisionLog, EAEState
from apps.core.ai_eae.override import (
    filter_overridden_signals,
    get_active_overrides,
)
from apps.core.ai_eae.scorer import score_signals
from apps.core.ai_eae.signal_collector import collect_signals
from apps.core.ai_eae.tone import select_tone

logger = logging.getLogger(__name__)


# =============================================================================
# EAE RESULT — Output of arbitration
# =============================================================================


@dataclass
class EAEResult:
    """Complete output of an EAE arbitration decision."""

    # Surfaced intelligence
    cognitive_units: List[CognitiveUnit] = field(default_factory=list)
    prompt_injection: str = ''

    # State
    escalation_level: int = 0
    drift_risk_severity: float = 0.0
    tone_band: str = 'reflective_gentle'
    primary_focus_label: str = ''

    # Budget
    noise_budget_used: int = 0
    noise_budget_max: int = 3

    # Audit
    total_candidates: int = 0
    surfaced_count: int = 0
    suppressed_count: int = 0
    suppressed_items: List[Dict] = field(default_factory=list)
    override_events: List[Dict] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)
    source_engines: List[str] = field(default_factory=list)
    arbitration_duration_ms: int = 0
    decision_id: str = ''


# =============================================================================
# GET OR CREATE STATE
# =============================================================================


def _get_or_create_state(user) -> EAEState:
    """Get or create EAEState for a user."""
    state, created = EAEState.objects.get_or_create(
        user=user,
        defaults={
            'escalation_level': 0,
            'drift_risk_severity': 0.0,
            'focus_date': date.today(),
            'noise_budget_date': date.today(),
        },
    )
    if created:
        logger.debug("EAE: Created new state for user %s", user.pk)
    return state


# =============================================================================
# MAIN ARBITRATION PIPELINE
# =============================================================================


def arbitrate(
    user,
    channel: str = CHANNEL_CHAT,
    recent_deliveries: Optional[List[Dict]] = None,
) -> EAEResult:
    """
    Run the full EAE arbitration pipeline.

    This is the SOLE entry point for arbitration. All intelligence surfacing
    decisions flow through here.

    Pipeline:
        1. Collect signals from all engines
        2. Score and normalize
        3. Deduplicate
        4. Bundle into cognitive units
        5. Filter overridden signals
        6. Apply noise budget
        7. Evaluate escalation
        8. Select tone
        9. Evaluate primary focus
        10. Format for prompt
        11. Log decision

    Args:
        user: Django User instance.
        channel: Delivery channel (chat, push, briefing, etc.)
        recent_deliveries: Recently delivered notifications for cross-channel dedup.

    Returns:
        EAEResult with surfaced units, prompt injection, and audit data.
    """
    start_time = time.monotonic()
    result = EAEResult()
    reason_codes = []

    try:
        # Get intensity multiplier
        intensity = get_intensity(user)

        # Get or create state
        state = _get_or_create_state(user)
        state.reset_daily_counters(date.today())

        # ─── Step 1: Collect signals ───
        signal_set = collect_signals(user)
        result.total_candidates = len(signal_set.signals)
        result.drift_risk_severity = signal_set.drift_risk_severity

        if not signal_set.signals:
            reason_codes.append('NO_SIGNALS')
            result.reason_codes = reason_codes
            result.prompt_injection = format_for_prompt([], 'reflective_gentle', 0)
            _finalize(state, result, start_time, user, channel)
            return result

        # ─── Step 2: Score and normalize ───
        scored = score_signals(signal_set, user, intensity)
        result.source_engines = list({s.engine for s in scored})

        # ─── Step 3: Deduplicate ───
        if recent_deliveries is None:
            recent_deliveries = _load_recent_deliveries(user)
        scored = deduplicate(scored, channel, recent_deliveries)

        # ─── Step 4: Bundle into cognitive units ───
        units = bundle_signals(scored)

        # ─── Step 5: Filter overridden signals ───
        active_overrides = get_active_overrides(user)
        units, override_events = filter_overridden_signals(units, active_overrides)
        result.override_events = override_events
        if override_events:
            reason_codes.append('OVERRIDES_APPLIED')

        # ─── Step 6: Apply noise budget ───
        surfaced, suppressed, budget = apply_budget(
            units=units,
            channel=channel,
            capacity_score=signal_set.capacity_score,
            daily_used=state.noise_budget_used_today,
            intensity=intensity,
        )
        result.cognitive_units = surfaced
        result.noise_budget_used = len(surfaced)
        result.noise_budget_max = budget
        result.surfaced_count = len(surfaced)
        result.suppressed_count = len(units) - len(surfaced) + len(override_events)
        result.suppressed_items = format_suppressed_for_audit(suppressed, override_events)

        if len(surfaced) < len(units):
            reason_codes.append('BUDGET_CAP')

        # ─── Step 7: Evaluate escalation ───
        new_level = evaluate_escalation(state, signal_set.drift_risk_severity, intensity)
        result.escalation_level = new_level

        # ─── Step 8: Select tone ───
        tone = select_tone(new_level, signal_set.drift_risk_severity, intensity)
        result.tone_band = tone

        # ─── Step 9: Evaluate primary focus ───
        focus_unit = evaluate_focus(state, surfaced, signal_set.drift_risk_severity, intensity)
        if focus_unit:
            result.primary_focus_label = state.primary_focus_label
            surfaced = ensure_focus_in_units(surfaced, state.primary_focus_label)
            result.cognitive_units = surfaced

        # ─── Step 10: Format for prompt ───
        result.prompt_injection = format_for_prompt(
            units=surfaced,
            tone_band=tone,
            escalation_level=new_level,
            primary_focus_label=state.primary_focus_label,
            drift_severity=signal_set.drift_risk_severity,
        )

        reason_codes.append('NORMAL_OPERATION')
        result.reason_codes = reason_codes

        # ─── Step 11: Finalize and log ───
        _finalize(state, result, start_time, user, channel)

    except Exception as e:
        logger.error("EAE arbitration failed for user %s: %s", user.pk, e, exc_info=True)
        result.reason_codes = ['ERROR', str(e)[:100]]
        result.prompt_injection = format_for_prompt([], 'reflective_gentle', 0)
        result.arbitration_duration_ms = int((time.monotonic() - start_time) * 1000)

    return result


# =============================================================================
# HELPERS
# =============================================================================


def _load_recent_deliveries(user) -> List[Dict]:
    """Load recent DNE deliveries for cross-channel dedup."""
    try:
        from apps.core.ai_eae.signal_collector import _collect_recent_deliveries
        return _collect_recent_deliveries(user, hours=CROSS_CHANNEL_DEDUP_HOURS)
    except Exception:
        return []


def _finalize(state: EAEState, result: EAEResult, start_time: float, user, channel: str):
    """Save state and log decision."""
    duration_ms = int((time.monotonic() - start_time) * 1000)
    result.arbitration_duration_ms = duration_ms

    # Update state
    state.last_arbitration_at = timezone.now()
    state.noise_budget_used_today += result.noise_budget_used
    state.save()

    # Log decision (append-only, best-effort)
    try:
        log = EAEDecisionLog.objects.create(
            user=user,
            channel=channel,
            escalation_level=result.escalation_level,
            drift_risk_severity=result.drift_risk_severity,
            tone_band=result.tone_band,
            primary_focus_label=result.primary_focus_label,
            cognitive_units_json=[u.to_dict() for u in result.cognitive_units],
            suppressed_items_json=result.suppressed_items,
            total_candidates=result.total_candidates,
            surfaced_count=result.surfaced_count,
            suppressed_count=result.suppressed_count,
            noise_budget_used=result.noise_budget_used,
            noise_budget_max=result.noise_budget_max,
            override_events_json=result.override_events,
            reason_codes=result.reason_codes,
            source_engines=result.source_engines,
            arbitration_duration_ms=duration_ms,
        )
        result.decision_id = str(log.decision_id)
    except Exception as e:
        logger.warning("EAE: Failed to log decision: %s", e)

    logger.info(
        "EAE: Arbitration complete for user %s [%s] in %dms — "
        "L%d, tone=%s, surfaced=%d/%d, suppressed=%d",
        user.pk, channel, duration_ms,
        result.escalation_level, result.tone_band,
        result.surfaced_count, result.total_candidates,
        result.suppressed_count,
    )
