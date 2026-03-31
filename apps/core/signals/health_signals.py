# ==============================================================================
# File: apps/core/signals/health_signals.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic health signal layer — trend detection from state
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-24
# ==============================================================================
"""
Deterministic Health Signals.

Identifies trends and patterns from canonical health + medicine state.
Each signal describes ONE concept: direction, state, or emerging pattern.

Architecture: raw data → canonical state → THIS → summary / Beth / nudges

Public API:
    build_health_signals(health_state, medicine_state, current_dt) -> list[dict]

Rules:
    - Pure function: no DB queries, no user object, no caching, no side effects
    - Each signal represents ONE concept
    - Missing data → signal not emitted (never fabricated)
    - Trend = "unknown" when prior-period data is unavailable
    - No composite scoring, no ML, no probabilistic logic
"""

import logging

logger = logging.getLogger(__name__)

# ── Signal states ────────────────────────────────────────────────────────────

STRONG = "strong"
MODERATE = "moderate"
POOR = "poor"
LOW = "low"
NORMAL = "normal"
STABLE = "stable"
WATCH = "watch"
UNSTABLE = "unstable"

# ── Trends ───────────────────────────────────────────────────────────────────

IMPROVING = "improving"
DECLINING = "declining"
TREND_STABLE = "stable"
UNKNOWN = "unknown"


def _signal(key, state, trend=None, value=None, insight=None):
    """Build a signal dict."""
    sig = {
        "key": key,
        "state": state,
    }
    if trend is not None:
        sig["trend"] = trend
    if value is not None:
        sig["value"] = value
    if insight is not None:
        sig["insight"] = insight
    return sig


def _compute_trend(current, prior, threshold_pct=10):
    """
    Compare current vs prior value and return trend.

    Args:
        current: current period value
        prior: prior period value (None if unavailable)
        threshold_pct: percent change required to call improving/declining

    Returns:
        IMPROVING | DECLINING | TREND_STABLE | UNKNOWN
    """
    if prior is None or current is None:
        return UNKNOWN
    if prior == 0:
        return UNKNOWN

    change_pct = ((current - prior) / abs(prior)) * 100

    if change_pct > threshold_pct:
        return IMPROVING
    elif change_pct < -threshold_pct:
        return DECLINING
    else:
        return TREND_STABLE


# ── Signal 1: Medication Adherence Trend ────────────────────────────────────

def _signal_med_adherence(medicine_state):
    """
    Medication adherence signal.

    Inputs from canonical state:
        - adherence_7d: current 7-day adherence rate (0-100)
        - adherence_prior_7d: prior 7-day rate (if available)

    State classification:
        - >= 90% → strong
        - 70-89% → moderate
        - < 70% → poor

    Trend: compare current vs prior 7d (>10% change = improving/declining).
    """
    adherence = medicine_state.get("adherence_7d")
    active_count = medicine_state.get("active_count", 0)

    if adherence is None or active_count == 0:
        return None

    # Classify state
    if adherence >= 90:
        state = STRONG
    elif adherence >= 70:
        state = MODERATE
    else:
        state = POOR

    # Trend (prior_7d may not exist in canonical state yet)
    prior = medicine_state.get("adherence_prior_7d")
    trend = _compute_trend(adherence, prior)

    # Insight
    if state == POOR:
        if trend == DECLINING:
            insight = "Medication adherence has been declining this week"
        else:
            insight = "Medication adherence is low this week"
    elif state == MODERATE:
        if trend == IMPROVING:
            insight = "Medication adherence is improving"
        else:
            insight = "Medication adherence is moderate"
    else:
        if trend == DECLINING:
            insight = "Medication adherence has dipped slightly"
        else:
            insight = "Medication adherence is strong"

    return _signal(
        "med_adherence",
        state,
        trend=trend,
        value=round(adherence / 100, 2),
        insight=insight,
    )


# ── Signal 2: Sleep Recovery ───────────────────────────────────────────────

def _signal_sleep_recovery(health_state):
    """
    Sleep recovery signal.

    Inputs:
        - sleep_avg_duration_7d: average sleep in minutes (7d)
        - sleep_avg_duration_prior_7d: prior 7d average (if available)

    State classification:
        - >= 420 min (7h) → strong
        - 360-419 min (6-7h) → moderate
        - < 360 min (< 6h) → poor
    """
    avg = health_state.get("sleep_avg_duration_7d")
    entries = health_state.get("sleep_entries_7d", 0)

    if avg is None or entries == 0:
        return None

    # Classify state
    avg_hours = avg / 60.0
    if avg >= 420:
        state = STRONG
    elif avg >= 360:
        state = MODERATE
    else:
        state = POOR

    # Trend (prior may not exist yet)
    prior = health_state.get("sleep_avg_duration_prior_7d")
    trend = _compute_trend(avg, prior)

    # Insight
    if state == POOR:
        insight = "Sleep has been short this week"
    elif state == MODERATE:
        insight = "Sleep has been adequate but could improve"
    else:
        if trend == IMPROVING:
            insight = "Sleep has been strong and improving"
        else:
            insight = "Sleep has been strong this week"

    return _signal(
        "sleep_recovery",
        state,
        trend=trend,
        value=round(avg_hours, 1),
        insight=insight,
    )


# ── Signal 3: Activity Momentum ────────────────────────────────────────────

def _signal_activity_momentum(health_state):
    """
    Activity momentum signal.

    Inputs:
        - steps_avg_7d: average daily steps (7d)
        - steps_avg_prior_7d: prior 7d average (if available)

    State classification:
        - >= 7500 → strong
        - 3000-7499 → moderate
        - < 3000 → low
    """
    avg = health_state.get("steps_avg_7d")
    entries = health_state.get("steps_entries_7d", 0)

    if avg is None or entries == 0:
        return None

    # Classify state
    if avg >= 7500:
        state = STRONG
    elif avg >= 3000:
        state = MODERATE
    else:
        state = LOW

    # Trend (prior may not exist yet)
    prior = health_state.get("steps_avg_prior_7d")
    trend = _compute_trend(avg, prior)

    # Insight
    if state == LOW:
        if trend == DECLINING:
            insight = "Activity levels are trending down this week"
        else:
            insight = "Activity has been low this week"
    elif state == MODERATE:
        insight = "Activity is at a moderate level"
    else:
        if trend == IMPROVING:
            insight = "Activity is strong and trending up"
        else:
            insight = "Activity has been strong this week"

    return _signal(
        "activity_momentum",
        state,
        trend=trend,
        value=round(avg),
        insight=insight,
    )


# ── Signal 4: Cardiometabolic Stability ────────────────────────────────────

def _signal_cardio_stability(health_state, current_dt):
    """
    Cardiometabolic stability signal.

    Combines BP, glucose, and HR into a single stability assessment.

    Inputs (all from canonical state, freshness-gated):
        - bp_systolic, bp_diastolic, last_bp_entry
        - latest_glucose, latest_glucose_unit, last_glucose_entry
        - latest_heart_rate, last_heart_rate_entry

    State classification:
        - all normal → stable
        - one elevated → watch
        - multiple abnormal → unstable
    """
    from apps.health.services.health_priority_service import _is_fresh

    concerns = 0
    metrics_present = 0

    # Blood pressure
    sys = health_state.get("bp_systolic")
    dia = health_state.get("bp_diastolic")
    if sys is not None and dia is not None:
        if _is_fresh("last_bp_entry", health_state, current_dt, "bp"):
            metrics_present += 1
            if sys >= 140 or dia >= 90:
                concerns += 1

    # Glucose
    glucose = health_state.get("latest_glucose")
    if glucose is not None:
        if _is_fresh("last_glucose_entry", health_state, current_dt, "glucose"):
            metrics_present += 1
            unit = health_state.get("latest_glucose_unit", "mg/dL")
            mg_dl = glucose * 18.0 if unit == "mmol/L" else glucose
            if mg_dl < 70 or mg_dl > 180:
                concerns += 1

    # Heart rate
    hr = health_state.get("latest_heart_rate")
    if hr is not None:
        if _is_fresh("last_heart_rate_entry", health_state, current_dt, "heart_rate"):
            metrics_present += 1
            if hr > 100:
                concerns += 1

    # Need at least 1 fresh metric to emit a signal
    if metrics_present == 0:
        return None

    # Classify
    if concerns == 0:
        state = STABLE
        insight = "Vitals are stable overall"
    elif concerns == 1:
        state = WATCH
        insight = "One vital sign is outside the normal range"
    else:
        state = UNSTABLE
        insight = "Multiple vital signs need attention"

    return _signal(
        "cardio_stability",
        state,
        value=concerns,
        insight=insight,
    )


# ── Signal 5: Body Composition ────────────────────────────────────────────

def _signal_body_composition(health_state):
    """
    Body composition signal.

    Reads pre-computed DailyHealthSummary intelligence fields from SAE state.
    Synthesizes a single signal representing overall body comp trajectory.

    Inputs (all from DHS via SAE state):
        - fat_loss_quality_label: EXCELLENT|GOOD|MIXED|MUSCLE_LOSS_RISK|INSUFFICIENT_DATA
        - muscle_loss_risk_level: LOW|MODERATE|HIGH
        - muscle_preservation_status: HIGH_QUALITY|MODERATE_QUALITY|MUSCLE_RISK|INSUFFICIENT_DATA
        - plateau_status: TRUE_PLATEAU|RECOMP|WATER|INSUFFICIENT_DATA
        - recomposition_flag_14d: bool
        - fat_loss_phase: RAPID_INITIAL_LOSS|STABLE_FAT_LOSS|RECOMPOSITION|PLATEAU|REBOUND_RISK
    """
    fat_loss_quality = health_state.get("fat_loss_quality_label")
    muscle_risk = health_state.get("muscle_loss_risk_level")
    muscle_preservation = health_state.get("muscle_preservation_status")
    plateau = health_state.get("plateau_status")
    recomp = health_state.get("recomposition_flag_14d")
    phase = health_state.get("fat_loss_phase")

    # Need at least fat_loss_quality to emit a signal
    if not fat_loss_quality or fat_loss_quality == "INSUFFICIENT_DATA":
        return None

    # ── State classification ──
    if recomp or (
        fat_loss_quality in ("EXCELLENT", "GOOD")
        and muscle_preservation == "HIGH_QUALITY"
    ):
        state = STRONG
    elif muscle_risk == "HIGH" or fat_loss_quality == "MUSCLE_LOSS_RISK":
        state = POOR
    elif (
        fat_loss_quality == "MIXED"
        or muscle_risk == "MODERATE"
        or plateau == "TRUE_PLATEAU"
    ):
        state = WATCH
    else:
        state = MODERATE

    # ── Trend from fat_loss_phase ──
    if phase in ("RAPID_INITIAL_LOSS", "STABLE_FAT_LOSS"):
        trend = IMPROVING
    elif phase in ("PLATEAU", "REBOUND_RISK"):
        trend = DECLINING
    elif phase == "RECOMPOSITION":
        trend = IMPROVING
    else:
        trend = UNKNOWN

    # ── Insight text ──
    if state == POOR:
        if muscle_risk == "HIGH":
            insight = "Significant muscle loss detected — consider increasing protein and resistance training"
        else:
            insight = "Body composition trends need attention — fat loss quality is declining"
    elif state == WATCH:
        if plateau == "TRUE_PLATEAU":
            insight = "Weight loss has stalled — may need to adjust approach"
        elif muscle_risk == "MODERATE":
            insight = "Some muscle loss detected alongside fat loss"
        else:
            insight = "Body composition signals are mixed this period"
    elif state == STRONG:
        if recomp:
            insight = "Body recomposition in progress — fat decreasing while muscle holds steady"
        else:
            insight = "Body composition is improving — effective fat loss with muscle preservation"
    else:
        insight = "Body composition is progressing steadily"

    return _signal(
        "body_composition",
        state,
        trend=trend,
        insight=insight,
    )


# ── Signal 6: Metabolic Efficiency ───────────────────────────────────────

def _signal_metabolic_efficiency(health_state):
    """
    Metabolic efficiency signal.

    Tracks BMR trend relative to weight loss to detect metabolic adaptation.
    Only emitted if user has BMR data.

    Inputs:
        - bmr_current: latest BMR in kcal/day (from BodyCompositionEntry via SAE)
        - fat_loss_speed_label: SAFE|SLOW|FAST|TOO_FAST|GAINING (from DHS via SAE)
        - plateau_status: from DHS via SAE
    """
    bmr = health_state.get("bmr_current")
    speed_label = health_state.get("fat_loss_speed_label")
    plateau = health_state.get("plateau_status")

    if bmr is None:
        return None  # No BMR data → don't emit

    # ── State classification ──
    # Without historical BMR comparison, use speed_label + plateau as proxy
    if speed_label in ("SAFE", "SLOW") and plateau != "TRUE_PLATEAU":
        state = STRONG
        insight = "Metabolism is holding steady during weight loss"
    elif speed_label == "TOO_FAST" or (
        plateau == "TRUE_PLATEAU" and speed_label not in ("GAINING", None)
    ):
        state = POOR
        insight = "Metabolic adaptation may be occurring — consider a diet break or refeed"
    elif speed_label == "FAST":
        state = WATCH
        insight = "Weight loss pace is aggressive — monitor for metabolic slowdown"
    else:
        state = MODERATE
        insight = "Metabolic rate is within normal range"

    return _signal(
        "metabolic_efficiency",
        state,
        value=round(bmr),
        insight=insight,
    )


# ── Main builder ─────────────────────────────────────────────────────────────

def build_health_signals(health_state, medicine_state, current_dt):
    """
    Build deterministic health signals from canonical state.

    Args:
        health_state: dict from get_module_state(user, 'health')
        medicine_state: dict from get_module_state(user, 'medicine')
        current_dt: user's current local aware datetime

    Returns:
        list of signal dicts. Empty list if no data available.
        Each signal is atomic and self-contained.
    """
    health_state = health_state or {}
    medicine_state = medicine_state or {}

    signals = []

    sig = _signal_med_adherence(medicine_state)
    if sig:
        signals.append(sig)

    sig = _signal_sleep_recovery(health_state)
    if sig:
        signals.append(sig)

    sig = _signal_activity_momentum(health_state)
    if sig:
        signals.append(sig)

    sig = _signal_cardio_stability(health_state, current_dt)
    if sig:
        signals.append(sig)

    sig = _signal_body_composition(health_state)
    if sig:
        signals.append(sig)

    sig = _signal_metabolic_efficiency(health_state)
    if sig:
        signals.append(sig)

    return signals
