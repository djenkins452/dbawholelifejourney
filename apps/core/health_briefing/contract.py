"""
HealthBriefing v1 — dataclass contract and enums.

Defines the shape of the deterministic briefing object Beth consumes for
health narration. This module contains types only — no composition logic,
no I/O, no behavior. Importing it is free of side effects.

Enums use ``str, Enum`` so values serialize as plain strings in JSON
payloads (HealthBriefingSnapshot.payload) without custom encoders.

Dataclasses are frozen to guarantee the briefing is immutable once
constructed. The composer assembles fresh briefings; it never mutates.

Field rationale lives in the Phase 0 architecture lock; do not add fields
here without updating that record. The contract is intentionally lean
(see "Reframed Roadmap"): additions go through a phase trigger, not ad-hoc.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Versioning ───────────────────────────────────────────────────────

SCHEMA_VERSION: int = 1
COMPOSER_VERSION: str = "1.0.0"

# Locked Phase 0 default. Briefings older than this are considered stale
# at the consumer (CoS). The composer regenerates on a 30-minute cadence
# plus event-triggered recomputes, so this value should always cover the
# next scheduled tick with margin.
DEFAULT_TTL_SECONDS: int = 1800

# Hard caps on ranked lists. Enforced in __post_init__.
MAX_DRIVERS: int = 3
MAX_WATCH_ITEMS: int = 3
MAX_WHY_BULLETS: int = 5


# ── Enums ────────────────────────────────────────────────────────────


class OverallStatus(str, Enum):
    THRIVING = "thriving"
    IMPROVING = "improving"
    STABLE = "stable"
    MIXED = "mixed"
    DECLINING = "declining"
    AT_RISK = "at_risk"
    INSUFFICIENT_DATA = "insufficient_data"


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    ACUTE = "acute"


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    INSUFFICIENT_DATA = "insufficient_data"


class AcuteSeverity(str, Enum):
    HIGH = "high"
    CRITICAL = "critical"


# ── Component dataclasses ────────────────────────────────────────────


@dataclass(frozen=True)
class ComposedOver:
    """Single time window summary covering all input rollups."""

    start_utc: datetime
    end_utc: datetime


@dataclass(frozen=True)
class Trend:
    """One trajectory horizon. Direction + normalized magnitude + confidence."""

    direction: TrendDirection
    magnitude: int  # 0..100
    confidence: float  # 0.0..1.0
    window_days: int

    def __post_init__(self) -> None:
        if not 0 <= self.magnitude <= 100:
            raise ValueError(f"Trend.magnitude must be 0..100, got {self.magnitude}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Trend.confidence must be 0.0..1.0, got {self.confidence}"
            )
        if self.window_days <= 0:
            raise ValueError(
                f"Trend.window_days must be positive, got {self.window_days}"
            )


@dataclass(frozen=True)
class AcuteAlert:
    """An acute health condition Beth MUST mention verbatim or near-verbatim."""

    key: str
    label: str
    severity: AcuteSeverity
    why: str
    evidence_ref: str  # key into HealthBriefing.inputs_used


@dataclass(frozen=True)
class Driver:
    """A pre-ranked positive driver or watch item. Beth must not re-rank."""

    key: str
    label: str
    score: float  # composite contribution score; higher = more important
    why: str


# ── Briefing ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HealthBriefing:
    """
    Deterministic metabolic intelligence briefing.

    Constructed by ``apps.core.health_briefing.composer`` from SAE state,
    engine outputs, and interpreted facts. Persisted in
    ``HealthBriefingSnapshot`` for replay. Consumed by Beth via a named
    slot in ``cos_context``.
    """

    # ── Identity ──
    briefing_id: str  # sha256, see compute_briefing_id()
    user_id: int
    generated_at_utc: datetime
    composer_version: str
    composed_over: ComposedOver
    ttl_seconds: int

    # ── Headline (Beth may not contradict) ──
    overall_status: OverallStatus
    overall_confidence: float  # 0.0..1.0
    risk_level: RiskLevel
    headline_summary: str

    # ── Trajectory (Phase 1A: glucose + weight + optional insulin) ──
    glucose_trend_7d: Trend
    glucose_trend_30d: Trend
    glucose_trend_90d: Trend
    weight_trend_30d: Trend
    insulin_trend_30d: Optional[Trend]  # None if insulin observation absent

    # ── Acute channel (must_mention semantics built in) ──
    acute_alerts: List[AcuteAlert] = field(default_factory=list)

    # ── Ranked drivers (composer pre-ranks; Beth must not re-rank) ──
    top_positive_drivers: List[Driver] = field(default_factory=list)
    watch_items: List[Driver] = field(default_factory=list)

    # ── Evidence (lean v1: values only, source meta lives in snapshot) ──
    inputs_used: Dict[str, Any] = field(default_factory=dict)
    inputs_missing: List[str] = field(default_factory=list)
    staleness_flags: List[str] = field(default_factory=list)

    # ── Explainability ──
    why: List[str] = field(default_factory=list)

    # ── Narration control ──
    positive_recognition_required: bool = False
    insufficient_data_flag: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.overall_confidence <= 1.0:
            raise ValueError(
                f"overall_confidence must be 0.0..1.0, got {self.overall_confidence}"
            )
        if self.ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be positive, got {self.ttl_seconds}")
        if len(self.top_positive_drivers) > MAX_DRIVERS:
            raise ValueError(
                f"top_positive_drivers exceeds MAX_DRIVERS={MAX_DRIVERS}"
            )
        if len(self.watch_items) > MAX_WATCH_ITEMS:
            raise ValueError(f"watch_items exceeds MAX_WATCH_ITEMS={MAX_WATCH_ITEMS}")
        if len(self.why) > MAX_WHY_BULLETS:
            raise ValueError(f"why exceeds MAX_WHY_BULLETS={MAX_WHY_BULLETS}")
        if self.insufficient_data_flag and self.overall_status != OverallStatus.INSUFFICIENT_DATA:
            raise ValueError(
                "insufficient_data_flag requires overall_status=insufficient_data"
            )

        for alert in self.acute_alerts:
            if alert.evidence_ref and alert.evidence_ref not in self.inputs_used:
                raise ValueError(
                    f"AcuteAlert {alert.key!r} references missing evidence "
                    f"{alert.evidence_ref!r}"
                )


# ── ID computation ───────────────────────────────────────────────────


def compute_briefing_id(
    user_id: int,
    generated_at_utc: datetime,
    composer_version: str,
    evidence_hash: str,
) -> str:
    """
    Deterministic SHA-256 of the inputs that define a briefing's identity.

    Replay relies on this being stable for identical inputs and changing
    when any input changes. The ``evidence_hash`` argument lets the
    composer fold a hash of ``inputs_used`` into the id without making
    this function depend on the contract structure.
    """
    raw = "|".join(
        [
            str(user_id),
            generated_at_utc.isoformat(),
            composer_version,
            evidence_hash,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
