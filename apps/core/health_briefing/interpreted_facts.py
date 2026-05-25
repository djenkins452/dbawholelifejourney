"""
Layer 4 — composer-internal interpreted facts.

Each function takes the relevant SAE state dict(s) and a ThresholdProfile
and returns a single ``FactVerdict``. These are **not** stored signals —
they are intermediate verdicts the composer (C11) assembles into a
HealthBriefing. Single source of truth: each fact has exactly one
producer (Law 4).

The seven v1 facts:

* glycemic_control_state    — quality of in-range control (TIR + CV + avg)
* glycemic_trajectory       — multi-horizon glucose slope (7d/30d/90d)
* insulin_dependence_state  — insulin daily-avg trend
* weight_trajectory_state   — multi-horizon weight slope
* exercise_response_state   — workout cadence quality
* sleep_recovery_state      — sleep duration adequacy + consistency
* adherence_state           — medication adherence rate

Every function:

* Reads only from state dicts; never queries the DB directly.
* Never raises on missing data — returns INSUFFICIENT_DATA with empty
  contribution and zero confidence.
* Returns a signed ``contribution`` in [-100, +100] suitable for the
  developer-facing explanation mode (C11 explain.py): positive →
  metabolic improvement, negative → metabolic concern.
* Returns a ``why`` string short enough for the explanation feed.

This module is pure: no I/O, no Django imports, no side effects on import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from apps.core.health_briefing.thresholds import ThresholdProfile, get_profile


# ── Verdict enums ────────────────────────────────────────────────────


VERDICT_INSUFFICIENT_DATA = "insufficient_data"

# Trajectory facts (glycemic_trajectory, insulin_dependence_state,
# weight_trajectory_state). For metabolic facts we want positive direction
# = improving health.
VERDICT_IMPROVING = "improving"
VERDICT_STABLE = "stable"
VERDICT_DECLINING = "declining"
VERDICT_VOLATILE = "volatile"  # high variance, no clear direction

# State facts (glycemic_control_state, exercise_response_state,
# sleep_recovery_state, adherence_state).
VERDICT_STRONG = "strong"
VERDICT_ADEQUATE = "adequate"
VERDICT_POOR = "poor"
VERDICT_TIGHT = "tight"       # glycemic_control only
VERDICT_LOOSE = "loose"       # glycemic_control only
VERDICT_UNCONTROLLED = "uncontrolled"  # glycemic_control only

# Insulin direction-specific (positive contribution when decreasing).
VERDICT_DECREASING = "decreasing"
VERDICT_INCREASING = "increasing"


# ── FactVerdict dataclass ────────────────────────────────────────────


@dataclass(frozen=True)
class FactVerdict:
    """One composer-internal verdict. Frozen for safety."""

    key: str                       # canonical fact key (e.g., "glycemic_control")
    label: str                     # short human-readable label
    verdict: str                   # one of the verdict enums above
    confidence: float              # 0.0..1.0
    contribution: int              # signed [-100, +100] for explain mode
    why: str                       # one-line human-readable reason
    inputs_used: Dict[str, Any] = field(default_factory=dict)
    inputs_missing: List[str] = field(default_factory=list)

    @property
    def is_sufficient(self) -> bool:
        return self.verdict != VERDICT_INSUFFICIENT_DATA


def _insufficient(key: str, label: str, *, missing: List[str], reason: str = "insufficient data") -> FactVerdict:
    return FactVerdict(
        key=key,
        label=label,
        verdict=VERDICT_INSUFFICIENT_DATA,
        confidence=0.0,
        contribution=0,
        why=reason,
        inputs_used={},
        inputs_missing=list(missing),
    )


# ── glycemic_control_state ───────────────────────────────────────────


def glycemic_control_state(
    health_state: Dict[str, Any],
    profile: Optional[ThresholdProfile] = None,
) -> FactVerdict:
    """Verdict on the quality of in-range glucose control today.

    Uses time-in-range (preferring 7d, falling back to 30d) combined
    with the existing glucose_variability_level. The TIR thresholds
    that decide tight / acceptable / loose / uncontrolled live in
    code below; clinical-target tuning is Phase 6 (per-user profile).
    """
    profile = profile or get_profile()
    label = "Glycemic control"

    tir_7d = health_state.get("time_in_range_pct_7d")
    tir_30d = health_state.get("time_in_range_pct_30d")
    cv_level = health_state.get("glucose_variability_level")
    avg_7d = health_state.get("glucose_avg_7d")

    primary_tir = tir_7d if tir_7d is not None else tir_30d
    if primary_tir is None and avg_7d is None:
        return _insufficient(
            "glycemic_control", label,
            missing=["time_in_range_pct_7d", "glucose_avg_7d"],
            reason="No glucose aggregates available",
        )

    # Determine verdict from TIR if present; else fall back to avg
    # (rough heuristic; 7d avg < 140 mg/dL is widely cited as good
    # control, > 180 as uncontrolled).
    if primary_tir is not None:
        if primary_tir >= 80:
            verdict = VERDICT_TIGHT
            contribution = 18
        elif primary_tir >= 70:
            verdict = VERDICT_ADEQUATE
            contribution = 10
        elif primary_tir >= 50:
            verdict = VERDICT_LOOSE
            contribution = -8
        else:
            verdict = VERDICT_UNCONTROLLED
            contribution = -20
        why_base = f"{primary_tir:.0f}% time-in-range"
    else:
        if avg_7d <= 140:
            verdict = VERDICT_ADEQUATE
            contribution = 8
        elif avg_7d <= 180:
            verdict = VERDICT_LOOSE
            contribution = -8
        else:
            verdict = VERDICT_UNCONTROLLED
            contribution = -20
        why_base = f"7d avg {avg_7d} mg/dL"

    # Variability layer: high variability dampens the score by 5
    # regardless of TIR (still oscillating).
    if cv_level == "high":
        contribution -= 5
        why = f"{why_base}, high variability"
    elif cv_level == "moderate":
        why = f"{why_base}, moderate variability"
    else:
        why = why_base

    # Confidence: scales with TIR availability and sample-window
    # presence. Both windows present + variability info → high.
    confidence = 0.5
    if tir_7d is not None:
        confidence += 0.2
    if tir_30d is not None:
        confidence += 0.15
    if cv_level is not None:
        confidence += 0.1
    confidence = min(confidence, profile.confidence_floors.single_source_cap)

    inputs_used = {
        k: v for k, v in (
            ("time_in_range_pct_7d", tir_7d),
            ("time_in_range_pct_30d", tir_30d),
            ("glucose_variability_level", cv_level),
            ("glucose_avg_7d", avg_7d),
        ) if v is not None
    }
    return FactVerdict(
        key="glycemic_control",
        label=label,
        verdict=verdict,
        confidence=round(confidence, 2),
        contribution=contribution,
        why=why,
        inputs_used=inputs_used,
        inputs_missing=[],
    )


# ── glycemic_trajectory ─────────────────────────────────────────────


def glycemic_trajectory(
    health_state: Dict[str, Any],
    profile: Optional[ThresholdProfile] = None,
) -> FactVerdict:
    """Verdict on glucose direction over time.

    Compares 7d average to 30d, and 30d to 90d. Improvement = lower
    avg over time. v1 uses these two pairwise deltas; PRIE projection
    (Phase 1B) will refine with a true regression slope.
    """
    profile = profile or get_profile()
    label = "Glycemic trajectory"

    a7 = health_state.get("glucose_avg_7d")
    a30 = health_state.get("glucose_avg_30d")
    a90 = health_state.get("glucose_avg_90d")

    if a7 is None and a30 is None:
        return _insufficient(
            "glycemic_trajectory", label,
            missing=["glucose_avg_7d", "glucose_avg_30d"],
            reason="Not enough glucose history",
        )

    deltas: List[int] = []
    inputs: Dict[str, Any] = {}
    if a7 is not None and a30 is not None:
        deltas.append(a30 - a7)  # positive = improving (older was higher)
        inputs["glucose_avg_7d"] = a7
        inputs["glucose_avg_30d"] = a30
    if a30 is not None and a90 is not None:
        deltas.append(a90 - a30)
        inputs["glucose_avg_90d"] = a90

    if not deltas:
        return _insufficient(
            "glycemic_trajectory", label,
            missing=["glucose_avg_30d", "glucose_avg_90d"],
            reason="Single window available; no trajectory possible",
        )

    avg_delta = sum(deltas) / len(deltas)
    # Magnitude → contribution score; clip at ±25.
    contribution = max(-25, min(25, int(round(avg_delta))))

    if avg_delta >= 8:
        verdict = VERDICT_IMPROVING
        why = f"7d avg {abs(avg_delta):.0f} mg/dL below recent baseline"
    elif avg_delta <= -8:
        verdict = VERDICT_DECLINING
        why = f"7d avg {abs(avg_delta):.0f} mg/dL above recent baseline"
    else:
        verdict = VERDICT_STABLE
        why = f"Glucose holding within ±{abs(avg_delta):.0f} mg/dL"

    confidence = 0.6 if len(deltas) == 1 else 0.85
    confidence = min(confidence, profile.confidence_floors.single_source_cap)

    return FactVerdict(
        key="glycemic_trajectory",
        label=label,
        verdict=verdict,
        confidence=round(confidence, 2),
        contribution=contribution,
        why=why,
        inputs_used=inputs,
        inputs_missing=[],
    )


# ── insulin_dependence_state ─────────────────────────────────────────


def insulin_dependence_state(
    medicine_state: Dict[str, Any],
    profile: Optional[ThresholdProfile] = None,
) -> FactVerdict:
    """Verdict on insulin requirement trajectory.

    v1 looks at the 30-day daily-average vs the 7-day total / 7. If
    the user has no insulin observation, returns INSUFFICIENT_DATA
    explicitly — Beth must not infer trajectory from absent data.
    """
    profile = profile or get_profile()
    label = "Insulin dependence"

    daily_avg_30 = medicine_state.get("insulin_daily_avg_30d_units")
    total_7 = medicine_state.get("insulin_total_7d_units")

    if daily_avg_30 is None and total_7 is None:
        return _insufficient(
            "insulin_dependence", label,
            missing=["insulin_daily_avg_30d_units", "insulin_total_7d_units"],
            reason="No insulin doses logged in the last 30 days",
        )

    if daily_avg_30 is None or total_7 is None:
        # Have one window but not both — record current state only.
        present = total_7 if total_7 is not None else daily_avg_30
        return FactVerdict(
            key="insulin_dependence",
            label=label,
            verdict=VERDICT_STABLE,
            confidence=0.4,
            contribution=0,
            why=f"Current insulin load tracked ({present:.0f}u)",
            inputs_used={
                k: v for k, v in (
                    ("insulin_total_7d_units", total_7),
                    ("insulin_daily_avg_30d_units", daily_avg_30),
                ) if v is not None
            },
            inputs_missing=[
                k for k, v in (
                    ("insulin_total_7d_units", total_7),
                    ("insulin_daily_avg_30d_units", daily_avg_30),
                ) if v is None
            ],
        )

    recent_daily = total_7 / 7.0
    # Positive delta = decreasing (recent daily lower than 30d avg).
    delta = daily_avg_30 - recent_daily
    pct_change = (delta / daily_avg_30 * 100) if daily_avg_30 > 0 else 0.0

    # Scale contribution by percent change, max ±25.
    contribution = max(-25, min(25, int(round(pct_change * 0.6))))

    if pct_change >= 8:
        verdict = VERDICT_DECREASING
        why = (
            f"Recent daily {recent_daily:.1f}u vs 30d avg {daily_avg_30:.1f}u "
            f"({pct_change:.0f}% lower)"
        )
    elif pct_change <= -8:
        verdict = VERDICT_INCREASING
        why = (
            f"Recent daily {recent_daily:.1f}u vs 30d avg {daily_avg_30:.1f}u "
            f"({abs(pct_change):.0f}% higher)"
        )
    else:
        verdict = VERDICT_STABLE
        why = f"Insulin holding near 30d avg {daily_avg_30:.1f}u/day"

    confidence = 0.75
    confidence = min(confidence, profile.confidence_floors.single_source_cap)

    return FactVerdict(
        key="insulin_dependence",
        label=label,
        verdict=verdict,
        confidence=round(confidence, 2),
        contribution=contribution,
        why=why,
        inputs_used={
            "insulin_total_7d_units": total_7,
            "insulin_daily_avg_30d_units": daily_avg_30,
        },
        inputs_missing=[],
    )


# ── weight_trajectory_state ──────────────────────────────────────────


def weight_trajectory_state(
    health_state: Dict[str, Any],
    profile: Optional[ThresholdProfile] = None,
) -> FactVerdict:
    """Verdict on weight direction.

    v1 reuses the existing weight_trend / weight_change_30d fields
    populated by the SAE health builder. PRIE projection rule
    (Phase 1B) can refine.
    """
    profile = profile or get_profile()
    label = "Weight trajectory"

    trend = health_state.get("weight_trend")
    change_30d = health_state.get("weight_change_30d")
    weight = health_state.get("weight_current")

    if trend in (None, "insufficient_data") and change_30d is None:
        return _insufficient(
            "weight_trajectory", label,
            missing=["weight_trend", "weight_change_30d"],
            reason="Not enough weight history",
        )

    contribution = 0
    if change_30d is not None:
        # Lower weight (negative change) → positive contribution for
        # metabolic context. Cap at ±15.
        contribution = max(-15, min(15, int(round(-float(change_30d)))))

    if trend == "down" or (change_30d is not None and float(change_30d) <= -1.0):
        verdict = VERDICT_IMPROVING
        magnitude = abs(float(change_30d)) if change_30d is not None else 0.0
        why = f"Weight down {magnitude:.1f} lb over 30d"
    elif trend == "up" or (change_30d is not None and float(change_30d) >= 1.0):
        verdict = VERDICT_DECLINING
        magnitude = abs(float(change_30d)) if change_30d is not None else 0.0
        why = f"Weight up {magnitude:.1f} lb over 30d"
    else:
        verdict = VERDICT_STABLE
        why = "Weight stable over 30d"

    confidence = 0.7 if change_30d is not None else 0.5
    confidence = min(confidence, profile.confidence_floors.single_source_cap)

    inputs_used = {
        k: v for k, v in (
            ("weight_trend", trend),
            ("weight_change_30d", change_30d),
            ("weight_current", weight),
        ) if v is not None
    }
    return FactVerdict(
        key="weight_trajectory",
        label=label,
        verdict=verdict,
        confidence=round(confidence, 2),
        contribution=contribution,
        why=why,
        inputs_used=inputs_used,
        inputs_missing=[],
    )


# ── exercise_response_state ──────────────────────────────────────────


def exercise_response_state(
    health_state: Dict[str, Any],
    profile: Optional[ThresholdProfile] = None,
) -> FactVerdict:
    """Verdict on exercise cadence / load.

    v1 uses workout_count_7d / steps_avg_7d if present. Glucose-
    response correlation is CDCE territory (Phase 1B); not here.
    """
    profile = profile or get_profile()
    label = "Exercise response"

    workouts_7d = health_state.get("workout_count_7d")
    steps_avg = health_state.get("steps_avg_7d")

    if workouts_7d is None and steps_avg is None:
        return _insufficient(
            "exercise_response", label,
            missing=["workout_count_7d", "steps_avg_7d"],
            reason="No recent activity logged",
        )

    contribution = 0
    why_parts: List[str] = []
    if workouts_7d is not None:
        if workouts_7d >= 4:
            contribution += 12
            why_parts.append(f"{workouts_7d} workouts/7d")
            verdict_w = VERDICT_STRONG
        elif workouts_7d >= 2:
            contribution += 5
            why_parts.append(f"{workouts_7d} workouts/7d")
            verdict_w = VERDICT_ADEQUATE
        else:
            contribution -= 3
            why_parts.append(f"{workouts_7d} workouts/7d")
            verdict_w = VERDICT_POOR
    else:
        verdict_w = None

    if steps_avg is not None:
        if steps_avg >= 8000:
            contribution += 5
            why_parts.append(f"{int(steps_avg):,} steps/d")
        elif steps_avg < 4000:
            contribution -= 3
            why_parts.append(f"{int(steps_avg):,} steps/d")

    if verdict_w is not None:
        verdict = verdict_w
    elif contribution >= 5:
        verdict = VERDICT_STRONG
    elif contribution <= -3:
        verdict = VERDICT_POOR
    else:
        verdict = VERDICT_ADEQUATE

    confidence = 0.4
    if workouts_7d is not None:
        confidence += 0.25
    if steps_avg is not None:
        confidence += 0.15
    confidence = min(confidence, profile.confidence_floors.single_source_cap)

    inputs_used = {
        k: v for k, v in (
            ("workout_count_7d", workouts_7d),
            ("steps_avg_7d", steps_avg),
        ) if v is not None
    }
    return FactVerdict(
        key="exercise_response",
        label=label,
        verdict=verdict,
        confidence=round(confidence, 2),
        contribution=contribution,
        why=", ".join(why_parts) or "Activity logged",
        inputs_used=inputs_used,
        inputs_missing=[],
    )


# ── sleep_recovery_state ─────────────────────────────────────────────


def sleep_recovery_state(
    health_state: Dict[str, Any],
    profile: Optional[ThresholdProfile] = None,
) -> FactVerdict:
    """Verdict on sleep duration (and last-night quality if available).

    v1 uses sleep_avg_hours_7d. HRV-based recovery modeling is Phase 3.
    """
    profile = profile or get_profile()
    label = "Sleep recovery"

    avg_hours_7d = health_state.get("sleep_avg_hours_7d")
    last_night = health_state.get("sleep_last_night_hours")

    if avg_hours_7d is None and last_night is None:
        return _insufficient(
            "sleep_recovery", label,
            missing=["sleep_avg_hours_7d", "sleep_last_night_hours"],
            reason="No sleep data",
        )

    primary = avg_hours_7d if avg_hours_7d is not None else last_night
    if primary >= 7.5:
        verdict = VERDICT_STRONG
        contribution = 10
        why = f"{primary:.1f}h avg sleep"
    elif primary >= 6.5:
        verdict = VERDICT_ADEQUATE
        contribution = 3
        why = f"{primary:.1f}h avg sleep"
    elif primary >= 5.5:
        verdict = VERDICT_POOR
        contribution = -5
        why = f"Only {primary:.1f}h avg sleep"
    else:
        verdict = VERDICT_POOR
        contribution = -12
        why = f"Severely short sleep: {primary:.1f}h avg"

    confidence = 0.6 if avg_hours_7d is not None else 0.4
    confidence = min(confidence, profile.confidence_floors.single_source_cap)

    inputs_used = {
        k: v for k, v in (
            ("sleep_avg_hours_7d", avg_hours_7d),
            ("sleep_last_night_hours", last_night),
        ) if v is not None
    }
    return FactVerdict(
        key="sleep_recovery",
        label=label,
        verdict=verdict,
        confidence=round(confidence, 2),
        contribution=contribution,
        why=why,
        inputs_used=inputs_used,
        inputs_missing=[],
    )


# ── adherence_state ──────────────────────────────────────────────────


def adherence_state(
    medicine_state: Dict[str, Any],
    profile: Optional[ThresholdProfile] = None,
) -> FactVerdict:
    """Verdict on medication adherence over the last 7 days."""
    profile = profile or get_profile()
    label = "Medication adherence"

    # The existing SAE medicine_state exposes adherence either as a
    # flat key or under _contract.summary; check both for robustness.
    rate = medicine_state.get("adherence_7d")
    if rate is None:
        contract = medicine_state.get("_contract") or {}
        rate = (contract.get("summary") or {}).get("adherence_7d")

    if rate is None:
        return _insufficient(
            "adherence", label,
            missing=["adherence_7d"],
            reason="No adherence data available",
        )

    if rate >= 95:
        verdict = VERDICT_STRONG
        contribution = 12
        why = f"{rate:.0f}% adherence"
    elif rate >= 80:
        verdict = VERDICT_ADEQUATE
        contribution = 4
        why = f"{rate:.0f}% adherence"
    elif rate >= 60:
        verdict = VERDICT_POOR
        contribution = -8
        why = f"Only {rate:.0f}% adherence"
    else:
        verdict = VERDICT_POOR
        contribution = -18
        why = f"Adherence at {rate:.0f}% — sustained gap"

    return FactVerdict(
        key="adherence",
        label=label,
        verdict=verdict,
        confidence=0.7,
        contribution=contribution,
        why=why,
        inputs_used={"adherence_7d": rate},
        inputs_missing=[],
    )


# ── Registry ─────────────────────────────────────────────────────────


ALL_FACTS = (
    "glycemic_control",
    "glycemic_trajectory",
    "insulin_dependence",
    "weight_trajectory",
    "exercise_response",
    "sleep_recovery",
    "adherence",
)


def compute_all_facts(
    health_state: Dict[str, Any],
    medicine_state: Dict[str, Any],
    profile: Optional[ThresholdProfile] = None,
) -> List[FactVerdict]:
    """Compute every Layer 4 fact for one user. Order is stable for
    deterministic explain-mode output."""
    profile = profile or get_profile()
    return [
        glycemic_control_state(health_state, profile),
        glycemic_trajectory(health_state, profile),
        insulin_dependence_state(medicine_state, profile),
        weight_trajectory_state(health_state, profile),
        exercise_response_state(health_state, profile),
        sleep_recovery_state(health_state, profile),
        adherence_state(medicine_state, profile),
    ]
