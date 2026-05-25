"""
Ranking — deterministic assembly of briefing headline + drivers from
Layer 4 interpreted facts.

Inputs:
* a list of ``FactVerdict`` (from interpreted_facts.compute_all_facts)
* an optional list of acute alerts (assembled by the composer from SAE
  state — e.g., critical-low glucose readings) — these bypass ranking
  and always surface, and they downgrade the headline tone to
  ``at_risk`` / risk level ``acute``.
* a thresholds profile (for confidence floors)

Outputs (``RankingResult`` dataclass):
* top_positive_drivers (max 3, sorted by contribution descending)
* watch_items (max 3, sorted by |contribution| descending among negatives)
* overall_status (one of OverallStatus enum)
* overall_confidence (weighted average of sufficient-fact confidences)
* risk_level (one of RiskLevel enum)
* positive_recognition_required (bool — forces composer to surface a
  positive driver in narration when status is improving/stable/thriving
  and a positive driver exists)
* insufficient_data_flag (bool — true when every fact is INSUFFICIENT_DATA)
* why (≤5 short bullets, ordered by absolute contribution)

This module is pure. No DB, no I/O, no side effects on import.

The five-axis model from the Phase 0 lock (severity, momentum,
durability, confidence, staleness penalty) is approximated in v1 by:

* contribution carries severity × momentum (already signed in C9)
* durability is implicit (facts use multi-window inputs where possible)
* confidence is a direct field on FactVerdict
* staleness penalty is applied by the composer when it sets the
  ``staleness_flags`` on the briefing

PRIE/CDCE in Phase 1B will refine the five-axis model with true
regression slopes and source-diversity weights; v1 keeps it
deterministic and explainable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from apps.core.health_briefing.contract import (
    MAX_DRIVERS,
    MAX_WATCH_ITEMS,
    MAX_WHY_BULLETS,
    AcuteAlert,
    AcuteSeverity,
    Driver,
    OverallStatus,
    RiskLevel,
)
from apps.core.health_briefing.interpreted_facts import (
    VERDICT_INSUFFICIENT_DATA,
    FactVerdict,
)
from apps.core.health_briefing.thresholds import ThresholdProfile, get_profile


# ── Thresholds for status / risk classification ──────────────────────


THRIVING_NET_MIN = 35
IMPROVING_NET_MIN = 10
STABLE_NET_MIN = -10
MIXED_NET_MIN = -30
# Below MIXED_NET_MIN → DECLINING. Acute alert always promotes to AT_RISK.

# Risk thresholds.
MODERATE_NEGATIVE_FACT_MIN = -15
HIGH_NET_RISK_MAX = -25


@dataclass(frozen=True)
class RankingResult:
    overall_status: OverallStatus
    overall_confidence: float
    risk_level: RiskLevel
    top_positive_drivers: List[Driver] = field(default_factory=list)
    watch_items: List[Driver] = field(default_factory=list)
    acute_alerts: List[AcuteAlert] = field(default_factory=list)
    why: List[str] = field(default_factory=list)
    positive_recognition_required: bool = False
    insufficient_data_flag: bool = False


# ── Helpers ──────────────────────────────────────────────────────────


def _verdict_to_driver(v: FactVerdict) -> Driver:
    return Driver(
        key=v.key,
        label=v.label,
        score=float(v.contribution),
        why=v.why,
    )


def _classify_status(
    net: int,
    sufficient_count: int,
    acute_present: bool,
    has_any_decline: bool,
) -> OverallStatus:
    if acute_present:
        # Acute alerts force AT_RISK even when net contribution is
        # positive — the briefing must not paint a rosy picture
        # during an acute event.
        return OverallStatus.AT_RISK
    if sufficient_count == 0:
        return OverallStatus.INSUFFICIENT_DATA
    if net >= THRIVING_NET_MIN:
        return OverallStatus.THRIVING
    if net >= IMPROVING_NET_MIN:
        return OverallStatus.IMPROVING
    if net >= STABLE_NET_MIN:
        # In the stable band, a single concerning fact tilts to MIXED.
        return OverallStatus.MIXED if has_any_decline else OverallStatus.STABLE
    if net >= MIXED_NET_MIN:
        return OverallStatus.MIXED
    return OverallStatus.DECLINING


def _classify_risk(
    net: int,
    acute_present: bool,
    worst_negative_contribution: int,
) -> RiskLevel:
    if acute_present:
        return RiskLevel.ACUTE
    if net <= HIGH_NET_RISK_MAX:
        return RiskLevel.HIGH
    if worst_negative_contribution <= MODERATE_NEGATIVE_FACT_MIN:
        return RiskLevel.MODERATE
    if worst_negative_contribution < 0:
        return RiskLevel.LOW
    return RiskLevel.NONE


def _weighted_confidence(sufficient: List[FactVerdict]) -> float:
    """Confidence weighted by |contribution| + 1 so high-magnitude
    facts pull the headline confidence more strongly. Falls back to a
    simple average when all contributions are zero."""
    if not sufficient:
        return 0.0
    total_weight = 0.0
    weighted_sum = 0.0
    for v in sufficient:
        w = abs(v.contribution) + 1
        total_weight += w
        weighted_sum += v.confidence * w
    return round(weighted_sum / total_weight, 2)


# ── Public API ──────────────────────────────────────────────────────


def rank_facts(
    verdicts: List[FactVerdict],
    acute_alerts: Optional[List[AcuteAlert]] = None,
    profile: Optional[ThresholdProfile] = None,
) -> RankingResult:
    """Rank Layer 4 verdicts into briefing-ready drivers + headline.

    Determinism: same inputs always produce the same RankingResult.
    Order tiebreaker is the FactVerdict's original key (ASCII order)
    so test fixtures and replay are reproducible.
    """
    profile = profile or get_profile()
    acute_alerts = list(acute_alerts or [])

    sufficient = [v for v in verdicts if v.verdict != VERDICT_INSUFFICIENT_DATA]
    if not sufficient and not acute_alerts:
        # No data at all.
        return RankingResult(
            overall_status=OverallStatus.INSUFFICIENT_DATA,
            overall_confidence=0.0,
            risk_level=RiskLevel.NONE,
            insufficient_data_flag=True,
        )

    # Drivers and watch items.
    positives = sorted(
        [v for v in sufficient if v.contribution > 0],
        key=lambda v: (-v.contribution, v.key),
    )
    negatives = sorted(
        [v for v in sufficient if v.contribution < 0],
        key=lambda v: (v.contribution, v.key),  # most-negative first
    )

    top_positive_drivers = [
        _verdict_to_driver(v) for v in positives[:MAX_DRIVERS]
    ]
    watch_items = [
        _verdict_to_driver(v) for v in negatives[:MAX_WATCH_ITEMS]
    ]

    # Headline metrics.
    net = sum(v.contribution for v in sufficient)
    worst_neg = min((v.contribution for v in sufficient), default=0)
    acute_present = bool(acute_alerts)
    has_any_decline = bool(negatives)

    overall_status = _classify_status(
        net=net,
        sufficient_count=len(sufficient),
        acute_present=acute_present,
        has_any_decline=has_any_decline,
    )
    risk_level = _classify_risk(
        net=net,
        acute_present=acute_present,
        worst_negative_contribution=worst_neg,
    )
    overall_confidence = _weighted_confidence(sufficient)

    # Positive recognition: enforced when the headline is positive
    # OR stable AND a positive driver above the narration_floor exists.
    floor = profile.confidence_floors.narration_floor
    qualifying_positives = [
        v for v in positives if v.confidence >= floor
    ]
    positive_recognition_required = bool(qualifying_positives) and (
        overall_status in (
            OverallStatus.THRIVING,
            OverallStatus.IMPROVING,
            OverallStatus.STABLE,
            # MIXED also requires positive recognition because the
            # composer must surface progress alongside concern. AT_RISK
            # does not — acute coverage takes precedence.
            OverallStatus.MIXED,
        )
    )

    # Why bullets: sorted by absolute contribution among sufficient
    # facts; acute alerts prepended verbatim.
    by_abs = sorted(
        sufficient, key=lambda v: (-abs(v.contribution), v.key),
    )
    why: List[str] = []
    for a in acute_alerts:
        why.append(f"ACUTE: {a.label} — {a.why}")
    for v in by_abs:
        if len(why) >= MAX_WHY_BULLETS:
            break
        sign = "+" if v.contribution > 0 else ""
        why.append(f"{v.label} {v.verdict} ({sign}{v.contribution}): {v.why}")
    why = why[:MAX_WHY_BULLETS]

    return RankingResult(
        overall_status=overall_status,
        overall_confidence=overall_confidence,
        risk_level=risk_level,
        top_positive_drivers=top_positive_drivers,
        watch_items=watch_items,
        acute_alerts=acute_alerts,
        why=why,
        positive_recognition_required=positive_recognition_required,
        insufficient_data_flag=False,
    )
