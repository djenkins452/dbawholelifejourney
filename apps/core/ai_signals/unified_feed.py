"""
Unified Signal Feed (Phase 3 — signal consolidation layer).

A thin adapter over the existing intelligence engines. Not a new engine.
Normalizes signals from PIE / PRIE / PGE / CDCE / cross-domain / EAE
into a single shape, deduplicates by ``dedupe_key`` + content similarity,
scores on a single priority axis, and bucketizes for CoS consumption.

Sources (already loaded by ``cos_context.build_cos_context`` — this
module does NOT re-query the DB when called with an existing context):

* active_insights            ← PIE (Insight model)
* active_predictions         ← PRIE (Prediction model)
* active_guidance            ← PGE (GuidanceItem model)
* cross_domain_correlations  ← CDCE (DomainCorrelation model)
* cross_domain_signals       ← cross_domain_signals.generate_cross_domain_signals
* ranked_signals.top_signal  ← cos_context._rank_top_signals (for drift synthetic)

Output: ``{top: [...], critical: [...], positive: [...]}`` of
``UnifiedSignal`` dicts plus a short deterministic ``signal_summary``
string for CoS narration.

This module does not compute domain truth. All normalization is
deterministic; no LLM, no ML, no DB writes.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────

SOURCE_INSIGHT = "insight"
SOURCE_PREDICTION = "prediction"
SOURCE_GUIDANCE = "guidance"
SOURCE_CORRELATION = "correlation"
SOURCE_CROSS_DOMAIN = "cross_domain"
SOURCE_DRIFT = "drift"

# Higher precedence = kept as the canonical representative in a dedupe
# cluster. Guidance wins because it carries an actionable recommendation.
SOURCE_PRECEDENCE: Dict[str, int] = {
    SOURCE_GUIDANCE: 5,
    SOURCE_INSIGHT: 4,
    SOURCE_PREDICTION: 3,
    SOURCE_CROSS_DOMAIN: 2,
    SOURCE_CORRELATION: 1,
    SOURCE_DRIFT: 0,
}

CLASS_RISK = "risk"
CLASS_OPPORTUNITY = "opportunity"
CLASS_MOMENTUM = "momentum"
CLASS_STATUS = "status"

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_POSITIVE = "positive"

# Severity → 0..5 integer for priority math.
_SEVERITY_ORDINAL: Dict[str, int] = {
    SEVERITY_CRITICAL: 5,
    SEVERITY_HIGH: 4,
    SEVERITY_MEDIUM: 3,
    SEVERITY_POSITIVE: 2,
    SEVERITY_LOW: 1,
}

# Action templates by (domain, signal_class). Used only when the dedupe
# cluster contains no guidance message. Kept small; extend deliberately.
_ACTION_TEMPLATES: Dict[Tuple[str, str], str] = {
    ("tasks", CLASS_RISK): "Complete your next task block before anything else.",
    ("health", CLASS_RISK): "Check the affected vital and take the one safest action.",
    ("goals", CLASS_RISK): "Pick the overdue goal and advance one milestone today.",
    ("habits", CLASS_RISK): "Do the at-risk habit now — don't break the streak.",
    ("faith", CLASS_MOMENTUM): "Keep your reading plan on schedule — you're compounding.",
    ("finance", CLASS_RISK): "Open the overdue bill and decide pay-now vs defer.",
}


@dataclass
class UnifiedSignal:
    """Normalized cross-source signal for CoS consumption."""

    source: str
    source_id: Optional[Any]
    domain: str
    type: str
    title: str
    message: str
    severity: str
    confidence: float
    priority_score: float
    signal_class: str
    action_text: Optional[str] = None
    action_type: Optional[str] = None
    dedupe_key: str = ""
    related_entities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Per-source normalizers ──────────────────────────────────────────

def _clamp_confidence(value: Any) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    if f < 0:
        return 0.0
    if f > 1:
        # PIE/PGE may emit 0-100. Rescale.
        if f <= 100:
            return f / 100.0
        return 1.0
    return f


def _compute_priority_score(
    severity: str,
    confidence: float,
    urgency_ordinal: int = 3,
) -> float:
    """priority_score = severity*0.5 + urgency*0.3 + confidence*0.2, normalized 0-1."""
    sev_norm = _SEVERITY_ORDINAL.get(severity, 1) / 5.0
    urg_norm = max(0, min(5, urgency_ordinal)) / 5.0
    conf_norm = max(0.0, min(1.0, confidence))
    score = sev_norm * 0.5 + urg_norm * 0.3 + conf_norm * 0.2
    return round(score, 4)


def _insight_signal_class(severity: str) -> str:
    if severity == SEVERITY_POSITIVE:
        return CLASS_MOMENTUM
    if severity in (SEVERITY_CRITICAL, SEVERITY_HIGH, "warning"):
        return CLASS_RISK
    return CLASS_STATUS


def _normalize_insight_severity(sev: str) -> str:
    """PIE uses 'critical' / 'warning' / 'info' / 'positive'."""
    if sev == "warning":
        return SEVERITY_HIGH
    if sev == "info":
        return SEVERITY_LOW
    if sev in _SEVERITY_ORDINAL:
        return sev
    return SEVERITY_LOW


def _normalize_insight(i: Dict[str, Any]) -> UnifiedSignal:
    severity = _normalize_insight_severity(i.get("severity", ""))
    conf = _clamp_confidence(i.get("confidence", 0))
    klass = _insight_signal_class(severity)
    return UnifiedSignal(
        source=SOURCE_INSIGHT,
        source_id=i.get("_id"),
        domain=i.get("module") or "",
        type=str(i.get("type") or ""),
        title=i.get("title") or "",
        message=i.get("message") or "",
        severity=severity,
        confidence=conf,
        priority_score=_compute_priority_score(severity, conf),
        signal_class=klass,
        dedupe_key=i.get("_dedupe_key") or "",
    )


def _normalize_prediction(p: Dict[str, Any]) -> UnifiedSignal:
    conf = _clamp_confidence(p.get("confidence", 0))
    # Predictions don't carry explicit severity; use confidence-proximity
    # to predicted_date to pick severity. High confidence + near date = high.
    severity = SEVERITY_MEDIUM if conf >= 0.7 else SEVERITY_LOW
    # Urgency bonus from predicted_date proximity.
    urgency = 3
    raw_date = p.get("_predicted_date_raw")
    if raw_date:
        try:
            from django.utils import timezone as _tz
            now = _tz.now()
            day = raw_date.date() if hasattr(raw_date, "date") else raw_date
            days_away = (day - now.date()).days
            if days_away <= 0:
                urgency = 5
            elif days_away <= 3:
                urgency = 4
            elif days_away <= 7:
                urgency = 3
            else:
                urgency = 2
        except Exception:
            pass
    return UnifiedSignal(
        source=SOURCE_PREDICTION,
        source_id=p.get("_id"),
        domain=p.get("module") or "",
        type=str(p.get("type") or ""),
        title=p.get("type") or "Prediction",
        message=p.get("explanation") or "",
        severity=severity,
        confidence=conf,
        priority_score=_compute_priority_score(severity, conf, urgency),
        signal_class=CLASS_RISK,
        dedupe_key=p.get("_dedupe_key") or "",
    )


def _normalize_guidance(g: Dict[str, Any]) -> UnifiedSignal:
    conf = _clamp_confidence(g.get("_confidence_score") or 0)
    # Guidance priority is 1-10 (lower = higher). Map to severity.
    try:
        prio = int(g.get("priority") or 5)
    except (TypeError, ValueError):
        prio = 5
    if prio <= 2:
        severity = SEVERITY_CRITICAL
    elif prio <= 4:
        severity = SEVERITY_HIGH
    elif prio <= 6:
        severity = SEVERITY_MEDIUM
    else:
        severity = SEVERITY_LOW
    klass = CLASS_RISK  # guidance is action-oriented by design
    return UnifiedSignal(
        source=SOURCE_GUIDANCE,
        source_id=g.get("_id"),
        domain=g.get("module") or "",
        type=str(g.get("guidance_type") or ""),
        title=g.get("title") or "",
        message=g.get("message") or "",
        severity=severity,
        confidence=conf,
        priority_score=_compute_priority_score(severity, conf),
        signal_class=klass,
        action_text=g.get("message") or None,
        action_type="do_now" if prio <= 3 else "schedule",
        dedupe_key=g.get("_dedupe_key") or "",
    )


def _normalize_correlation(c: Dict[str, Any]) -> UnifiedSignal:
    strength = c.get("strength") or ""
    if strength == "strong":
        severity = SEVERITY_HIGH
    elif strength == "moderate":
        severity = SEVERITY_MEDIUM
    else:
        severity = SEVERITY_LOW
    conf = _clamp_confidence(c.get("score", 0))
    domains = c.get("domains") or []
    domain = ",".join(domains) if isinstance(domains, (list, tuple)) else str(domains)
    return UnifiedSignal(
        source=SOURCE_CORRELATION,
        source_id=c.get("_id"),
        domain=domain,
        type=str(c.get("type") or ""),
        title=c.get("type") or "Correlation",
        message=c.get("narrative") or "",
        severity=severity,
        confidence=conf,
        priority_score=_compute_priority_score(severity, conf),
        signal_class=CLASS_STATUS,
        dedupe_key=c.get("_dedupe_key") or "",
    )


def _cross_domain_severity(raw: str) -> str:
    if raw == "high":
        return SEVERITY_HIGH
    if raw == "medium":
        return SEVERITY_MEDIUM
    return SEVERITY_LOW


def _cross_domain_confidence(raw: str) -> float:
    return {"high": 0.9, "medium": 0.6, "low": 0.3}.get(raw, 0.5)


def _normalize_cross_domain(s: Dict[str, Any]) -> UnifiedSignal:
    severity = _cross_domain_severity(s.get("severity", "low"))
    conf = _cross_domain_confidence(s.get("confidence", "medium"))
    domains = s.get("domains") or []
    domain = ",".join(domains) if isinstance(domains, (list, tuple)) else str(domains)
    code = s.get("signal_code") or ""
    klass = (
        CLASS_MOMENTUM if "momentum" in code or "positive" in code
        else CLASS_RISK
    )
    return UnifiedSignal(
        source=SOURCE_CROSS_DOMAIN,
        source_id=code or None,
        domain=domain,
        type=code,
        title=_humanize_cross_domain_code(code),
        message=s.get("summary") or "",
        severity=severity,
        confidence=conf,
        priority_score=_compute_priority_score(severity, conf),
        signal_class=klass,
        dedupe_key=f"xd:{code}" if code else "",
    )


def _humanize_cross_domain_code(code: str) -> str:
    if not code:
        return "Cross-domain signal"
    return code.replace("_", " ").strip().capitalize()


def _normalize_drift(drift: Dict[str, Any]) -> Optional[UnifiedSignal]:
    """Synthesize a drift UnifiedSignal from ranked_signals.top_signal if
    the top signal is of source_type 'drift'. Caller gates upstream."""
    conf = _clamp_confidence(drift.get("confidence") or 0)
    sev = SEVERITY_HIGH if conf >= 0.5 else SEVERITY_MEDIUM
    return UnifiedSignal(
        source=SOURCE_DRIFT,
        source_id=None,
        domain="drift",
        type="behavioral_drift",
        title=drift.get("title") or "Behavioral drift",
        message=drift.get("message") or "",
        severity=sev,
        confidence=conf,
        priority_score=_compute_priority_score(sev, conf),
        signal_class=CLASS_RISK,
        dedupe_key=drift.get("_dedupe_key") or "drift",
    )


# ── Deduplication ────────────────────────────────────────────────────

def _dedupe_bucket_key(sig: UnifiedSignal) -> str:
    """Coarse fallback grouping when dedupe_key is missing."""
    title_head = (sig.title or "").lower().strip()[:40]
    return f"{sig.domain}|{sig.signal_class}|{title_head}"


def _dedupe_signals(signals: Iterable[UnifiedSignal]) -> List[UnifiedSignal]:
    """Collapse signals into clusters by dedupe_key (preferred) or by
    (domain, signal_class, title_head). Within a cluster, keep the
    highest-precedence source as canonical; inherit action_text from
    any guidance member if the canonical has none.
    """
    clusters: Dict[str, List[UnifiedSignal]] = {}
    for sig in signals:
        if sig.dedupe_key:
            key = f"dk:{sig.dedupe_key}"
        else:
            key = _dedupe_bucket_key(sig)
        clusters.setdefault(key, []).append(sig)

    deduped: List[UnifiedSignal] = []
    for members in clusters.values():
        # Sort by precedence then priority_score for tiebreak.
        members.sort(
            key=lambda s: (
                SOURCE_PRECEDENCE.get(s.source, 0),
                s.priority_score,
            ),
            reverse=True,
        )
        canonical = members[0]
        # Inherit action from any guidance member if canonical has none.
        if not canonical.action_text:
            for m in members:
                if m.source == SOURCE_GUIDANCE and m.action_text:
                    canonical.action_text = m.action_text
                    canonical.action_type = m.action_type or canonical.action_type
                    break
        deduped.append(canonical)
    return deduped


# ── Action extraction ────────────────────────────────────────────────

def _attach_templated_actions(signals: List[UnifiedSignal]) -> None:
    """In-place fill of action_text from templates when still missing."""
    for sig in signals:
        if sig.action_text:
            continue
        template = _ACTION_TEMPLATES.get((sig.domain, sig.signal_class))
        if template:
            sig.action_text = template
            sig.action_type = sig.action_type or "do_now"


# ── Bucketing ────────────────────────────────────────────────────────

def bucket_signals(
    signals: List[UnifiedSignal],
    *,
    top_n: int = 5,
) -> Dict[str, List[UnifiedSignal]]:
    """
    Partition a deduped signal list into:

    * ``top``      — top-N by priority_score (excludes pure positives
                     unless there are too few actionable signals).
    * ``critical`` — severity in {critical, high} AND signal_class == risk.
    * ``positive`` — signal_class in {momentum, opportunity}.

    Sorting is stable and deterministic.
    """
    # Sort once; everything else is a filter.
    sorted_signals = sorted(
        signals,
        key=lambda s: (s.priority_score, _SEVERITY_ORDINAL.get(s.severity, 0)),
        reverse=True,
    )

    actionable = [
        s for s in sorted_signals
        if s.signal_class in (CLASS_RISK, CLASS_OPPORTUNITY, CLASS_STATUS)
    ]
    positive = [
        s for s in sorted_signals
        if s.signal_class in (CLASS_MOMENTUM, CLASS_OPPORTUNITY)
    ]
    critical = [
        s for s in sorted_signals
        if s.signal_class == CLASS_RISK
        and s.severity in (SEVERITY_CRITICAL, SEVERITY_HIGH)
    ]

    # If no actionable signals, fill top from positives so CoS still
    # has something to anchor on.
    top_source = actionable if actionable else positive
    top = top_source[:top_n]

    return {
        "top": top,
        "critical": critical[:top_n],
        "positive": positive[:top_n],
    }


# ── Summary text ─────────────────────────────────────────────────────

def compose_signal_summary(buckets: Dict[str, List[UnifiedSignal]]) -> str:
    """
    Short, deterministic synthesis for CoS to anchor narrative. Not
    intended to replace the system prompt — this is a compact fact
    line the prompt can reference.
    """
    parts: List[str] = []
    crit = buckets.get("critical") or []
    top = buckets.get("top") or []
    positive = buckets.get("positive") or []

    if crit:
        titles = ", ".join(s.title for s in crit[:3] if s.title)
        parts.append(f"{len(crit)} critical: {titles}")
    if top and not crit:
        titles = ", ".join(s.title for s in top[:3] if s.title)
        if titles:
            parts.append(f"Top focus: {titles}")
    if positive:
        titles = ", ".join(s.title for s in positive[:2] if s.title)
        if titles:
            parts.append(f"Momentum: {titles}")

    return " | ".join(parts)


# ── Public API ───────────────────────────────────────────────────────

def get_unified_signals_from_context(
    cos_context: Dict[str, Any],
) -> List[UnifiedSignal]:
    """
    Build the unified, deduped, scored signal list from a CoS context
    that has already loaded the individual sources.

    This is the primary entry point because CoS already loads all the
    upstream engine outputs during ``build_cos_context``; re-querying
    here would be wasteful and would violate the request-path
    performance rule.
    """
    raw: List[UnifiedSignal] = []

    for i in cos_context.get("active_insights") or []:
        raw.append(_normalize_insight(i))
    for p in cos_context.get("active_predictions") or []:
        raw.append(_normalize_prediction(p))
    for g in cos_context.get("active_guidance") or []:
        raw.append(_normalize_guidance(g))
    for c in cos_context.get("cross_domain_correlations") or []:
        raw.append(_normalize_correlation(c))
    for s in cos_context.get("cross_domain_signals") or []:
        raw.append(_normalize_cross_domain(s))

    # Drift: surface only if ranked_signals.top_signal is a synthetic
    # drift signal, and emit a single UnifiedSignal representing it.
    ranked = cos_context.get("ranked_signals") or {}
    top = ranked.get("top_signal") or {}
    if top.get("source_type") == "drift":
        drift_sig = _normalize_drift(top)
        if drift_sig is not None:
            raw.append(drift_sig)

    deduped = _dedupe_signals(raw)
    _attach_templated_actions(deduped)
    return deduped


def build_signal_buckets(
    cos_context: Dict[str, Any],
    *,
    top_n: int = 5,
) -> Dict[str, Any]:
    """
    Convenience wrapper used by cos_context.py: returns a context-ready
    payload with the three bucket lists as plain dicts plus the short
    ``signal_summary`` string.
    """
    unified = get_unified_signals_from_context(cos_context)
    buckets = bucket_signals(unified, top_n=top_n)
    return {
        "top_signals": [s.to_dict() for s in buckets["top"]],
        "critical_signals": [s.to_dict() for s in buckets["critical"]],
        "positive_signals": [s.to_dict() for s in buckets["positive"]],
        "signal_summary": compose_signal_summary(buckets),
    }
