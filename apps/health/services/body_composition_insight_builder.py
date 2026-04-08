"""
Body Composition Insight Builder — deterministic formatter for UI display.

Converts pre-computed body composition intelligence (from SAE state / DHS)
into user-facing insight text with severity levels and trend arrows.

Architecture:
    - Pure function: reads pre-computed SAE state, no DB queries
    - Called in HealthHomeView (request path — fast, no computation)
    - Produces structured output for template rendering
    - NEVER shows contradictory signals
    - Degrades gracefully to "insufficient data" when confidence is low

Usage:
    from apps.health.services.body_composition_insight_builder import build_body_comp_insight
    insight = build_body_comp_insight(health_state)
"""

import logging

logger = logging.getLogger(__name__)

# Minimum confidence to show a definitive conclusion
MIN_CONFIDENCE_FOR_VERDICT = 0.5


def build_body_comp_insight(health_state):
    """
    Convert pre-computed body comp intelligence into a user-facing insight.

    Args:
        health_state: dict from get_module_state(user, 'health') — contains
            DHS fields (fat_loss_phase, muscle_loss_risk_level, etc.)
            and latest metric values (body_fat_current, bmi_current, etc.)

    Returns:
        dict with headline, severity, details — or None if insufficient data.
        {
            "headline": str,                    # 1-2 sentences, plain language
            "severity": "green"|"yellow"|"red",
            "details": [                        # Supporting context metrics
                {"label": str, "value": str, "trend": "up"|"down"|"stable"|None},
            ],
        }
    """
    if not health_state:
        return None

    fat_loss_quality = health_state.get("fat_loss_quality_label")
    muscle_risk = health_state.get("muscle_loss_risk_level")
    muscle_preservation = health_state.get("muscle_preservation_status")
    plateau_status = health_state.get("plateau_status")
    recomp = health_state.get("recomposition_flag_14d")
    phase = health_state.get("fat_loss_phase")
    speed_label = health_state.get("fat_loss_speed_label")
    speed_pct = health_state.get("fat_loss_speed_pct_per_week")
    plateau_risk = health_state.get("plateau_risk_label")

    # Need at least one intelligence field to produce an insight
    if not fat_loss_quality or fat_loss_quality == "INSUFFICIENT_DATA":
        return None

    # ── Confidence gate (from body_comp_signal via physical_decision) ──
    fat_confidence = health_state.get("fat_confidence")
    if fat_confidence is not None and fat_confidence < MIN_CONFIDENCE_FOR_VERDICT:
        return _insufficient_data_insight(health_state)

    # ── Contradiction check ──
    if _has_contradictory_signals(health_state):
        return _mixed_signals_insight(health_state)

    # ── Determine severity and headline ──
    severity = "green"
    headline = ""

    if muscle_risk == "HIGH" or fat_loss_quality == "MUSCLE_LOSS_RISK":
        severity = "red"
        headline = (
            "Muscle loss risk is elevated — a significant portion of weight loss "
            "may be lean mass. Consider increasing protein and resistance training."
        )
    elif speed_label == "TOO_FAST":
        severity = "red"
        headline = (
            "Weight loss pace is too aggressive — this increases muscle loss risk "
            "and metabolic adaptation."
        )
    elif plateau_status == "TRUE_PLATEAU":
        severity = "yellow"
        headline = (
            "Weight loss has plateaued. This is normal — consider adjusting "
            "calorie intake or training intensity."
        )
    elif recomp:
        severity = "green"
        headline = (
            "Body recomposition in progress — fat is decreasing while muscle "
            "mass is holding steady or increasing."
        )
    elif fat_loss_quality in ("EXCELLENT", "GOOD") and muscle_preservation == "HIGH_QUALITY":
        severity = "green"
        headline = "Body composition is improving — effective fat loss with strong muscle preservation."
    elif fat_loss_quality == "MIXED" or muscle_risk == "MODERATE":
        severity = "yellow"
        if muscle_risk == "MODERATE":
            headline = "Some muscle loss detected alongside fat loss — monitor protein intake."
        elif plateau_risk == "HIGH" or plateau_risk == "RISING":
            headline = "Weight loss is slowing — you may be approaching a plateau."
        else:
            headline = "Body composition signals are mixed — progress is uneven this period."
    elif phase == "RAPID_INITIAL_LOSS":
        severity = "green"
        headline = "Early-phase fat loss is progressing well."
    elif phase == "STABLE_FAT_LOSS":
        severity = "green"
        headline = "Fat loss is steady and sustainable."
    elif phase == "REBOUND_RISK":
        # Only show rebound risk if we have sufficient waist data confirming it
        # Otherwise downgrade to mixed signals
        if _has_waist_confirmation(health_state):
            severity = "red"
            headline = "Rebound risk detected — weight trend is reversing."
        else:
            severity = "yellow"
            headline = (
                "Weight trend may be reversing — more measurements needed to confirm."
            )
    else:
        severity = "green"
        headline = "Body composition is progressing steadily."

    # ── Build supporting details ──
    details = _build_details(
        fat_loss_quality, speed_label, speed_pct,
        muscle_preservation, phase, plateau_risk,
    )

    return {
        "headline": headline,
        "severity": severity,
        "details": details,
    }


def _has_contradictory_signals(health_state):
    """Detect mutually exclusive signal combinations.

    Returns True if the data contains contradictions that should prevent
    a confident display. Specific contradictions:
    - speed_label == "GAINING" but fat_loss_quality in ("GOOD", "EXCELLENT")
    - phase == "REBOUND_RISK" but fat_loss_quality in ("GOOD", "EXCELLENT")
    """
    speed = health_state.get("fat_loss_speed_label")
    quality = health_state.get("fat_loss_quality_label")
    phase = health_state.get("fat_loss_phase")

    # Weight gaining but fat loss quality says good → contradiction
    if speed == "GAINING" and quality in ("GOOD", "EXCELLENT"):
        return True

    # Rebound risk but fat loss quality says good → contradiction
    if phase == "REBOUND_RISK" and quality in ("GOOD", "EXCELLENT"):
        return True

    return False


def _has_waist_confirmation(health_state):
    """Check if health state suggests waist data is available and confirming.

    Phase 4: `waist_trend` in the AI state is a STRING ("increasing" /
    "decreasing" / "stable" / "insufficient_data") produced by
    build_health_state() as of Phase 3. Previously this reader did
    `waist_trend > 0.1`, assuming a numeric delta — that raised
    TypeError against the string value and was silently swallowed by
    the caller's except block, so "waist confirmation" was effectively
    never available. A rebound is confirmed when the waist is growing.
    """
    waist_trend = health_state.get("waist_trend")
    return waist_trend == "increasing"


def _insufficient_data_insight(health_state):
    """Return a safe insight when confidence is too low for a verdict."""
    details = []

    # Explain what's missing
    reasons = []
    sufficiency = health_state.get("sufficiency")
    if sufficiency:
        if sufficiency.get("weight_points_7d", 0) < 3:
            reasons.append("Fewer than 3 weight entries this week")
        if sufficiency.get("waist_points_14d", 0) < 2:
            reasons.append("Fewer than 2 waist measurements in 14 days")
        if sufficiency.get("body_fat_source") == "scale":
            reasons.append("Body fat data from scale only (low accuracy)")
    else:
        reasons.append("Limited measurement data available")

    if reasons:
        details.append({
            "label": "Why",
            "value": "; ".join(reasons),
            "trend": None,
        })

    return {
        "headline": (
            "Not enough data to assess body composition changes. "
            "Log weight regularly and take waist measurements for accurate tracking."
        ),
        "severity": "yellow",
        "details": details,
    }


def _mixed_signals_insight(health_state):
    """Return a safe insight when signals contradict each other."""
    details = []

    conflict_adjustments = health_state.get("conflict_adjustments", [])
    if conflict_adjustments:
        details.append({
            "label": "Note",
            "value": "Some measurements disagree — more data needed",
            "trend": None,
        })

    # Still show whatever quality/speed data is available
    fat_loss_quality = health_state.get("fat_loss_quality_label")
    if fat_loss_quality and fat_loss_quality != "INSUFFICIENT_DATA":
        details.append({
            "label": "Fat Loss Quality",
            "value": _humanize_label(fat_loss_quality),
            "trend": None,
        })

    return {
        "headline": (
            "Body composition signals are mixed — some indicators conflict. "
            "Continue tracking for a clearer picture."
        ),
        "severity": "yellow",
        "details": details,
    }


def _build_details(fat_loss_quality, speed_label, speed_pct,
                   muscle_preservation, phase, plateau_risk):
    """Build the supporting details list."""
    details = []

    if fat_loss_quality and fat_loss_quality != "INSUFFICIENT_DATA":
        details.append({
            "label": "Fat Loss Quality",
            "value": _humanize_label(fat_loss_quality),
            "trend": None,
        })

    if speed_label and speed_label != "INSUFFICIENT_DATA":
        speed_str = _humanize_label(speed_label)
        if speed_pct:
            try:
                speed_str += f" ({float(speed_pct):.1f}%/week)"
            except (TypeError, ValueError):
                pass
        details.append({
            "label": "Loss Speed",
            "value": speed_str,
            "trend": _speed_trend(speed_label),
        })

    if muscle_preservation and muscle_preservation != "INSUFFICIENT_DATA":
        details.append({
            "label": "Muscle Preservation",
            "value": _humanize_label(muscle_preservation),
            "trend": None,
        })

    if phase:
        details.append({
            "label": "Phase",
            "value": _humanize_label(phase),
            "trend": _phase_trend(phase),
        })

    if plateau_risk and plateau_risk != "LOW":
        details.append({
            "label": "Plateau Risk",
            "value": _humanize_label(plateau_risk),
            "trend": "up" if plateau_risk == "RISING" else None,
        })

    return details


def _humanize_label(label):
    """Convert ENUM_STYLE labels to Title Case."""
    if not label:
        return ""
    return label.replace("_", " ").title()


def _speed_trend(speed_label):
    """Map fat loss speed to a trend direction."""
    if speed_label in ("SAFE", "SLOW"):
        return "stable"
    elif speed_label in ("FAST", "TOO_FAST"):
        return "down"  # losing fast
    elif speed_label == "GAINING":
        return "up"
    return None


def _phase_trend(phase):
    """Map fat loss phase to a trend direction."""
    if phase in ("RAPID_INITIAL_LOSS", "STABLE_FAT_LOSS", "RECOMPOSITION"):
        return "down"  # fat going down = good
    elif phase in ("PLATEAU", "REBOUND_RISK"):
        return "up"  # stalling or reversing
    return None
