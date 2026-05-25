"""
HealthBriefing composer (Phase 1A · C11).

Reads SAE state (health / medicine / medical), assembles a deterministic
HealthBriefing via the Layer 4 interpreted facts (C9) and the ranking
module (C10), and optionally persists a snapshot.

**Wave 3 invariant:** the composer is NOT wired to Beth, CoS context,
or any narration path. It runs only via explicit calls — the
management command in this commit, or the Celery beat job / event
hooks in C12. Beth integration is W5 (C14/C15) and gated behind
explicit prompt-addendum registration.

Design rules:

* Pure orchestration; reads SAE state via ``get_module_state`` only.
* Never queries raw domain rows. Composer is one layer above SAE,
  never below.
* Background execution. Never called from a request path
  (per the CLAUDE.md performance rule).
* Persisting a snapshot is opt-in (``persist=True`` by default; the
  management command can run with ``--no-persist`` for ad-hoc
  inspection without polluting the table).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.utils import timezone

from apps.core.ai_state.state_engine import get_module_state
from apps.core.health_briefing.contract import (
    COMPOSER_VERSION,
    DEFAULT_TTL_SECONDS,
    AcuteAlert,
    AcuteSeverity,
    ComposedOver,
    HealthBriefing,
    OverallStatus,
    Trend,
    TrendDirection,
    compute_briefing_id,
)
from apps.core.health_briefing.interpreted_facts import compute_all_facts
from apps.core.health_briefing.ranking import rank_facts
from apps.core.health_briefing.thresholds import ThresholdProfile, get_profile


logger = logging.getLogger(__name__)


# ── Trend helpers ────────────────────────────────────────────────────


# Pairwise trend = (recent_value, baseline_value, window_days).
# Direction is from the metabolic perspective: lower glucose = down = improving.


def _trend_from_pair(
    recent: Optional[float],
    baseline: Optional[float],
    window_days: int,
    flat_pct: float = 5.0,
    base_confidence: float = 0.7,
) -> Trend:
    if recent is None or baseline is None or baseline == 0:
        return Trend(
            direction=TrendDirection.INSUFFICIENT_DATA,
            magnitude=0,
            confidence=0.0,
            window_days=window_days,
        )
    delta_pct = (recent - baseline) / baseline * 100
    abs_pct = abs(delta_pct)
    # Magnitude 0..100 with a soft cap (15% change → magnitude ~85).
    magnitude = int(min(100, abs_pct * 6))
    if abs_pct <= flat_pct:
        direction = TrendDirection.FLAT
    elif delta_pct < 0:
        direction = TrendDirection.DOWN
    else:
        direction = TrendDirection.UP
    return Trend(
        direction=direction,
        magnitude=magnitude,
        confidence=round(base_confidence, 2),
        window_days=window_days,
    )


def _glucose_trends(health_state: Dict[str, Any]) -> Tuple[Trend, Trend, Trend]:
    a7 = health_state.get("glucose_avg_7d")
    a30 = health_state.get("glucose_avg_30d")
    a90 = health_state.get("glucose_avg_90d")
    return (
        _trend_from_pair(a7, a30, window_days=7),
        _trend_from_pair(a30, a90, window_days=30),
        # 90d standalone with no longer reference → insufficient; HbA1c
        # integration in Phase 2 can refine.
        _trend_from_pair(a90, None, window_days=90),
    )


def _weight_trend_30d(health_state: Dict[str, Any]) -> Trend:
    change = health_state.get("weight_change_30d")
    weight = health_state.get("weight_current")
    if change is None or weight is None or float(weight) == 0:
        return Trend(
            direction=TrendDirection.INSUFFICIENT_DATA,
            magnitude=0, confidence=0.0, window_days=30,
        )
    # Convert lb change → percent of body weight.
    delta_pct = (float(change) / float(weight)) * 100
    # Lower weight is "down" in this context.
    abs_pct = abs(delta_pct)
    magnitude = int(min(100, abs_pct * 25))
    if abs_pct <= 0.5:
        direction = TrendDirection.FLAT
    elif delta_pct < 0:
        direction = TrendDirection.DOWN
    else:
        direction = TrendDirection.UP
    return Trend(
        direction=direction, magnitude=magnitude,
        confidence=0.7, window_days=30,
    )


def _insulin_trend_30d(medicine_state: Dict[str, Any]) -> Optional[Trend]:
    daily_avg_30 = medicine_state.get("insulin_daily_avg_30d_units")
    total_7 = medicine_state.get("insulin_total_7d_units")
    if daily_avg_30 is None or total_7 is None:
        # Optional field on HealthBriefing — None when insulin
        # observation is absent. The composer treats this as "no
        # insulin claim possible" rather than "insulin is zero."
        return None
    recent_daily = float(total_7) / 7.0
    return _trend_from_pair(
        recent_daily, float(daily_avg_30),
        window_days=30, flat_pct=8.0, base_confidence=0.7,
    )


# ── Acute alert assembly ────────────────────────────────────────────


def _build_acute_alerts(
    health_state: Dict[str, Any],
    profile: ThresholdProfile,
) -> List[AcuteAlert]:
    alerts: List[AcuteAlert] = []
    latest = health_state.get("latest_glucose")
    unit = health_state.get("latest_glucose_unit") or "mg/dL"
    if latest is None:
        return alerts
    # Normalize to mg/dL for comparison.
    val_mg_dl = float(latest)
    if unit == "mmol/L":
        val_mg_dl *= 18.0
    cuts = profile.acute_glucose
    if val_mg_dl <= cuts.critical_low_mg_dl:
        alerts.append(AcuteAlert(
            key="glucose_critical_low",
            label="Critical low glucose",
            severity=AcuteSeverity.CRITICAL,
            why=f"Most recent reading {val_mg_dl:.0f} mg/dL",
            evidence_ref="latest_glucose",
        ))
    elif val_mg_dl >= cuts.critical_high_mg_dl:
        alerts.append(AcuteAlert(
            key="glucose_critical_high",
            label="Critical high glucose",
            severity=AcuteSeverity.CRITICAL,
            why=f"Most recent reading {val_mg_dl:.0f} mg/dL",
            evidence_ref="latest_glucose",
        ))
    elif val_mg_dl >= cuts.high_mg_dl:
        # High but not critical → only an acute alert if sustained;
        # for v1 we don't have a "sustained" signal yet, so this stays
        # in the watch_items channel via the glycemic_control fact
        # rather than as an acute. Future PIE rule can promote.
        pass
    return alerts


# ── Evidence assembly ───────────────────────────────────────────────


_HEALTH_EVIDENCE_FIELDS = (
    "latest_glucose", "latest_glucose_unit", "glucose_avg_7d",
    "glucose_avg_30d", "glucose_avg_90d", "time_in_range_pct_7d",
    "time_in_range_pct_30d", "glucose_variability_level",
    "overnight_avg_glucose", "weight_current", "weight_change_30d",
    "weight_trend", "sleep_avg_hours_7d", "sleep_last_night_hours",
    "workout_count_7d", "steps_avg_7d",
)
_MEDICINE_EVIDENCE_FIELDS = (
    "adherence_7d", "insulin_total_today_units",
    "insulin_total_7d_units", "insulin_total_30d_units",
    "insulin_daily_avg_30d_units",
)
_MEDICAL_EVIDENCE_FIELDS = (
    "recent_glycemic_labs",
)


def _build_evidence(
    health_state: Dict[str, Any],
    medicine_state: Dict[str, Any],
    medical_state: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    inputs_used: Dict[str, Any] = {}
    inputs_missing: List[str] = []
    for field in _HEALTH_EVIDENCE_FIELDS:
        val = health_state.get(field)
        if val is not None:
            inputs_used[field] = val
        else:
            inputs_missing.append(field)
    for field in _MEDICINE_EVIDENCE_FIELDS:
        val = medicine_state.get(field)
        if val is None:
            # Fall back to _contract.summary location.
            val = (medicine_state.get("_contract") or {}).get("summary", {}).get(field)
        if val is not None:
            inputs_used[field] = val
        else:
            inputs_missing.append(field)
    for field in _MEDICAL_EVIDENCE_FIELDS:
        val = medical_state.get(field)
        if val:
            inputs_used[field] = val
        else:
            inputs_missing.append(field)
    # Staleness flags are populated by C12 when timestamps become
    # available; for v1 we leave the list empty so the briefing schema
    # is honest about not yet checking.
    staleness_flags: List[str] = []
    return inputs_used, inputs_missing, staleness_flags


def _hash_evidence(inputs_used: Dict[str, Any]) -> str:
    """Stable SHA-256 of a JSON-serializable representation. Used to
    fold input identity into briefing_id."""
    try:
        canonical = json.dumps(
            inputs_used, default=str, sort_keys=True, separators=(",", ":"),
        )
    except (TypeError, ValueError):
        canonical = repr(sorted(inputs_used.items()))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Headline ─────────────────────────────────────────────────────────


_HEADLINE_TEMPLATES = {
    OverallStatus.THRIVING: "Metabolic profile looks strong across the board.",
    OverallStatus.IMPROVING: "Metabolic trajectory is improving.",
    OverallStatus.STABLE: "Metabolic profile is stable.",
    OverallStatus.MIXED: "Metabolic profile is mixed — progress alongside a concern.",
    OverallStatus.DECLINING: "Metabolic profile is moving in the wrong direction.",
    OverallStatus.AT_RISK: "Active concern requires attention.",
    OverallStatus.INSUFFICIENT_DATA: "Not enough data to characterize metabolic status.",
}


def _build_headline(ranking, inputs_used_count: int) -> str:
    return _HEADLINE_TEMPLATES[ranking.overall_status]


# ── Snapshot persistence ────────────────────────────────────────────


def _serialize_briefing(briefing: HealthBriefing) -> Dict[str, Any]:
    """Convert HealthBriefing to a plain dict (enums → strings,
    datetimes → ISO-8601). Used for snapshot.payload and for the
    explain mode."""
    def _ser(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if hasattr(value, "value") and isinstance(value, type(OverallStatus.STABLE)):
            return value.value
        return value

    return {
        "briefing_id": briefing.briefing_id,
        "user_id": briefing.user_id,
        "generated_at_utc": _ser(briefing.generated_at_utc),
        "composer_version": briefing.composer_version,
        "composed_over": {
            "start_utc": _ser(briefing.composed_over.start_utc),
            "end_utc": _ser(briefing.composed_over.end_utc),
        },
        "ttl_seconds": briefing.ttl_seconds,
        "overall_status": briefing.overall_status.value,
        "overall_confidence": briefing.overall_confidence,
        "risk_level": briefing.risk_level.value,
        "headline_summary": briefing.headline_summary,
        "glucose_trend_7d": _trend_to_dict(briefing.glucose_trend_7d),
        "glucose_trend_30d": _trend_to_dict(briefing.glucose_trend_30d),
        "glucose_trend_90d": _trend_to_dict(briefing.glucose_trend_90d),
        "weight_trend_30d": _trend_to_dict(briefing.weight_trend_30d),
        "insulin_trend_30d": _trend_to_dict(briefing.insulin_trend_30d) if briefing.insulin_trend_30d else None,
        "acute_alerts": [
            {
                "key": a.key, "label": a.label, "severity": a.severity.value,
                "why": a.why, "evidence_ref": a.evidence_ref,
            } for a in briefing.acute_alerts
        ],
        "top_positive_drivers": [
            {"key": d.key, "label": d.label, "score": d.score, "why": d.why}
            for d in briefing.top_positive_drivers
        ],
        "watch_items": [
            {"key": d.key, "label": d.label, "score": d.score, "why": d.why}
            for d in briefing.watch_items
        ],
        "inputs_used": briefing.inputs_used,
        "inputs_missing": briefing.inputs_missing,
        "staleness_flags": briefing.staleness_flags,
        "why": briefing.why,
        "positive_recognition_required": briefing.positive_recognition_required,
        "insufficient_data_flag": briefing.insufficient_data_flag,
    }


def _trend_to_dict(t: Trend) -> Dict[str, Any]:
    return {
        "direction": t.direction.value,
        "magnitude": t.magnitude,
        "confidence": t.confidence,
        "window_days": t.window_days,
    }


def _persist_snapshot(briefing: HealthBriefing) -> None:
    from apps.core.health_briefing.models import HealthBriefingSnapshot

    payload = _serialize_briefing(briefing)
    # Convert non-JSON-serializable values in inputs_used to strings.
    # JSONField will reject Decimals etc.; coerce here once.
    payload["inputs_used"] = json.loads(
        json.dumps(payload["inputs_used"], default=str)
    )
    expires_at = briefing.generated_at_utc + timedelta(seconds=briefing.ttl_seconds)
    HealthBriefingSnapshot.objects.update_or_create(
        briefing_id=briefing.briefing_id,
        defaults=dict(
            user_id=briefing.user_id,
            generated_at=briefing.generated_at_utc,
            composer_version=briefing.composer_version,
            payload=payload,
            expires_at=expires_at,
        ),
    )


# ── Public API ──────────────────────────────────────────────────────


def compose_briefing(
    user,
    *,
    profile: Optional[ThresholdProfile] = None,
    persist: bool = True,
    now: Optional[datetime] = None,
) -> HealthBriefing:
    """Compose a HealthBriefing for ``user``. Snapshot is persisted by
    default; pass ``persist=False`` for ad-hoc inspection."""
    profile = profile or get_profile()
    now = now or timezone.now()

    # Read SAE state (read-only).
    health_state = get_module_state(user, "health") or {}
    medicine_state = get_module_state(user, "medicine") or {}
    medical_state = get_module_state(user, "medical") or {}

    # Layer 4 facts + acute alerts.
    verdicts = compute_all_facts(health_state, medicine_state, profile)
    acute_alerts = _build_acute_alerts(health_state, profile)

    # Rank.
    ranking = rank_facts(verdicts, acute_alerts=acute_alerts, profile=profile)

    # Trends.
    gt7, gt30, gt90 = _glucose_trends(health_state)
    wt30 = _weight_trend_30d(health_state)
    it30 = _insulin_trend_30d(medicine_state)

    # Evidence.
    inputs_used, inputs_missing, staleness_flags = _build_evidence(
        health_state, medicine_state, medical_state,
    )
    evidence_hash = _hash_evidence(inputs_used)

    # Identity.
    briefing_id = compute_briefing_id(
        user_id=user.id,
        generated_at_utc=now,
        composer_version=COMPOSER_VERSION,
        evidence_hash=evidence_hash,
    )

    headline = _build_headline(ranking, len(inputs_used))

    briefing = HealthBriefing(
        briefing_id=briefing_id,
        user_id=user.id,
        generated_at_utc=now,
        composer_version=COMPOSER_VERSION,
        composed_over=ComposedOver(
            start_utc=now - timedelta(days=30),
            end_utc=now,
        ),
        ttl_seconds=DEFAULT_TTL_SECONDS,
        overall_status=ranking.overall_status,
        overall_confidence=ranking.overall_confidence,
        risk_level=ranking.risk_level,
        headline_summary=headline,
        glucose_trend_7d=gt7,
        glucose_trend_30d=gt30,
        glucose_trend_90d=gt90,
        weight_trend_30d=wt30,
        insulin_trend_30d=it30,
        acute_alerts=ranking.acute_alerts,
        top_positive_drivers=ranking.top_positive_drivers,
        watch_items=ranking.watch_items,
        inputs_used=inputs_used,
        inputs_missing=inputs_missing,
        staleness_flags=staleness_flags,
        why=ranking.why,
        positive_recognition_required=ranking.positive_recognition_required,
        insufficient_data_flag=ranking.insufficient_data_flag,
    )

    if persist:
        try:
            _persist_snapshot(briefing)
        except Exception:
            logger.error(
                "HealthBriefing snapshot persistence failed for user=%s",
                user.id, exc_info=True,
            )

    return briefing
