"""
WLJ Signal Rendering Framework (Phase 1).

Single canonical interpretation layer that turns a UnifiedSignal into
deterministic user-facing text — Label / Meaning / Action.

ARCHITECTURE LAWS (do not violate):
    - LLM-last: NO LLM is invoked here. Renderer is a pure table lookup.
    - Single source of truth: input is `UnifiedSignal`
      (apps.core.ai_signals.unified_feed). No new signal object.
    - Renderer MUST NOT depend on `signal.title` or `signal.message` —
      those are producer-authored prose. The renderer renders ONLY from
      the (domain, type, severity) triple.
    - Phase 1 coverage: Health/Medical, Faith, Life (tasks/routines).
      Other domains return None and callers fall through to legacy
      rendering. No ad-hoc per-domain branching.

CONTRACT:
    render_signal(signal, context) -> {
        "label": str,         # one of LABEL_TAXONOMY
        "message": str,       # 1-2 short sentences, plain English
        "action": str,        # exactly one in-app action
        "priority": str,      # foundational | important | supporting
        "domain": str,        # signal.domain
    } | None

Returns None when no template matches — caller falls through to legacy
rendering during the Phase 1/2/3 migration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Taxonomy + priority
# ══════════════════════════════════════════════════════════════════════

# Allowed label vocabulary. Anything outside this set is rejected at
# render time. "Unclear" / "Mixed" / "Needs clarity" are explicitly
# banned per spec — they confuse instead of inform.
LABEL_TAXONOMY = {"Alert", "Trend", "Opportunity"}


# Domain → priority tier. Drives suppression + ordering. Priority is
# what the renderer EMITS; severity is what the producer AUTHORED.
DOMAIN_PRIORITY: Dict[str, str] = {
    # foundational — health is the foundation; always surfaces.
    "health": "foundational",
    "medical": "foundational",
    # important — habits / fuel / sleep.
    "meals": "important",
    "nutrition": "important",
    "sleep": "important",
    "habits": "important",
    "faith": "important",  # foundational personally, but tier-2 in priority math
    # supporting — organization / output.
    "life": "supporting",
    "tasks": "supporting",
    "routine": "supporting",
    "organization": "supporting",
}

_PRIORITY_ORDER = {"foundational": 0, "important": 1, "supporting": 2}
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "positive": 4}


# ══════════════════════════════════════════════════════════════════════
# Type aliases — Phase 1 translation layer
# ══════════════════════════════════════════════════════════════════════
# Producers (PIE/PRIE/PGE/CDCE) currently emit their own type strings.
# Rather than touch producers in Phase 1, we translate known producer
# types to renderer types here. Producers will be updated to emit
# canonical renderer types directly in a later phase, at which point
# this map can shrink.
#
# Keys: producer-emitted (domain, type) tuples (lowercased).
# Values: canonical renderer type string.
#
# Add entries only for the three Phase 1 domains.

_TYPE_ALIAS: Dict[tuple, str] = {
    # Health vitals (CDCE / physical_decision style)
    ("health", "glucose_alert_high"): "glucose_high",
    ("health", "glucose_alert_elevated"): "glucose_elevated",
    ("health", "glucose_alert_low"): "glucose_low",
    ("health", "blood_pressure_alert"): "blood_pressure_high",
    ("health", "bp_high"): "blood_pressure_high",
    # Faith
    ("faith", "reading_streak"): "faith_reading_streak",
    ("faith", "missed_prayer"): "faith_prayer_missed",
    # Life
    ("life", "task_overload"): "tasks_overloaded",
    ("life", "routine_breakdown"): "routine_breakdown",
}


def _alias(domain: str, type_: str) -> str:
    """Translate producer-emitted type to renderer type. Logs when
    used so we can track migration progress."""
    key = ((domain or "").lower(), (type_ or "").lower())
    aliased = _TYPE_ALIAS.get(key)
    if aliased and aliased != type_:
        logger.info(
            "[SIGNAL_RENDERER] alias_used domain=%s producer_type=%s -> %s",
            domain, type_, aliased,
        )
        return aliased
    return type_


# ══════════════════════════════════════════════════════════════════════
# Render map — the canonical (domain, type, severity) → template table
# ══════════════════════════════════════════════════════════════════════
# Severity normalization: producers may emit critical/warning/etc.
# The renderer accepts the canonical UnifiedSignal severities:
# {critical, high, medium, low, positive}.
#
# RULES (locked by spec):
#   - max 1-2 sentences
#   - exactly ONE action
#   - plain English; no clinical numbers / units in text
#   - NO "Unclear" / "Mixed" labels
#   - exactly the keys: label, message, action, priority

SIGNAL_RENDER_MAP: Dict[tuple, Dict[str, str]] = {
    # ── Health / Medical: glucose ─────────────────────────────────────
    ("health", "glucose_high", "high"): {
        "label": "Glucose Alert",
        "priority": "foundational",
        "message": "Your glucose has been running high this week.",
        "action": "Log your next 3 meals and add a fasting reading tomorrow.",
    },
    ("health", "glucose_high", "critical"): {
        "label": "Glucose Alert",
        "priority": "foundational",
        "message": "Your glucose has been running high this week.",
        "action": "Log your next 3 meals and add a fasting reading tomorrow.",
    },
    ("health", "glucose_elevated", "medium"): {
        "label": "Glucose Trend",
        "priority": "foundational",
        "message": "Your glucose is trending higher than normal.",
        "action": "Tighten meal consistency today and log your next meals.",
    },
    ("health", "glucose_low", "high"): {
        "label": "Glucose Alert",
        "priority": "foundational",
        "message": "Your recent glucose readings are low.",
        "action": "Have a fast-acting carb and recheck in 15 minutes.",
    },
    ("health", "glucose_low", "critical"): {
        "label": "Glucose Alert",
        "priority": "foundational",
        "message": "Your recent glucose readings are low.",
        "action": "Have a fast-acting carb and recheck in 15 minutes.",
    },
    # ── Health / Medical: blood pressure ─────────────────────────────
    ("health", "blood_pressure_high", "high"): {
        "label": "Blood Pressure Alert",
        "priority": "foundational",
        "message": "Your blood pressure is running high.",
        "action": "Log daily readings this week.",
    },
    ("health", "blood_pressure_high", "critical"): {
        "label": "Blood Pressure Alert",
        "priority": "foundational",
        "message": "Your blood pressure is running high.",
        "action": "Log daily readings this week.",
    },
    # ── Faith ────────────────────────────────────────────────────────
    ("faith", "faith_reading_streak", "positive"): {
        "label": "Faith Opportunity",
        "priority": "important",
        "message": "Your reading streak is compounding.",
        "action": "Open today's reading now to keep it going.",
    },
    ("faith", "faith_prayer_missed", "medium"): {
        "label": "Faith Trend",
        "priority": "important",
        "message": "Prayer has slipped this week.",
        "action": "Open prayer now to reset the day.",
    },
    # ── Life / tasks / routines ──────────────────────────────────────
    ("life", "tasks_overloaded", "high"): {
        "label": "Tasks Alert",
        "priority": "supporting",
        "message": "Your task list is piling up.",
        "action": "Move one task to later today to clear pressure.",
    },
    ("life", "tasks_overloaded", "medium"): {
        "label": "Tasks Trend",
        "priority": "supporting",
        "message": "Your task list is heavier than usual.",
        "action": "Move one task to later today to clear pressure.",
    },
    ("life", "routine_breakdown", "high"): {
        "label": "Routine Alert",
        "priority": "supporting",
        "message": "Your morning routine has slipped this week.",
        "action": "Run today's routine in order — start with the first item.",
    },
    ("life", "routine_breakdown", "medium"): {
        "label": "Routine Trend",
        "priority": "supporting",
        "message": "Your morning routine has been inconsistent.",
        "action": "Run today's routine in order — start with the first item.",
    },
}


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def normalize_signal(signal: Any) -> Dict[str, Any]:
    """
    Strip a UnifiedSignal down to the fields the renderer is allowed
    to read. Producers' authored prose (`title`, `message`) is
    DELIBERATELY excluded so rendering stays purely deterministic.

    Accepts:
        - UnifiedSignal dataclass
        - dict (e.g. `UnifiedSignal.to_dict()` output)
    """
    def _get(attr, default=None):
        if hasattr(signal, attr):
            return getattr(signal, attr)
        if isinstance(signal, dict):
            return signal.get(attr, default)
        return default

    domain = (_get("domain") or "").lower()
    raw_type = (_get("type") or "").lower()
    type_ = _alias(domain, raw_type)
    severity = (_get("severity") or "").lower()

    return {
        "domain": domain,
        "type": type_,
        "severity": severity,
        "action": _get("action_text") or _get("action") or "",
        "confidence": float(_get("confidence") or 0.0),
        "_raw_type": raw_type,
        "_signal_class": _get("signal_class") or "",
        "_priority_score": float(_get("priority_score") or 0.0),
        "_dedupe_key": _get("dedupe_key") or "",
    }


def render_signal(signal: Any, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, str]]:
    """
    Render a UnifiedSignal to user-facing text via deterministic table
    lookup.

    Returns:
        dict with keys {label, message, action, priority, domain} on a
        successful match.
        None when no template matches — caller MUST fall back to legacy
        rendering during Phase 1/2/3 migration.

    `context` is reserved for future per-user personalization (active
    block, time-of-day). Phase 1 does not consume it; the parameter is
    accepted to lock the call signature.
    """
    norm = normalize_signal(signal)
    key = (norm["domain"], norm["type"], norm["severity"])
    template = SIGNAL_RENDER_MAP.get(key)

    if not template:
        logger.info(
            "[SIGNAL_RENDERER] no_template domain=%s type=%s severity=%s "
            "raw_type=%s — caller falls back to legacy",
            norm["domain"], norm["type"], norm["severity"],
            norm.get("_raw_type"),
        )
        return None

    label = template["label"]
    if label not in {l for l in LABEL_TAXONOMY} and not any(
        label.endswith(allowed) or label.startswith(allowed)
        for allowed in LABEL_TAXONOMY
    ):
        # Defensive: a template author tried to use a banned label.
        logger.warning(
            "[SIGNAL_RENDERER] banned_label label=%s key=%s — using "
            "'Alert' fallback", label, key,
        )
        label = "Alert"

    rendered = {
        "label": label,
        "message": template["message"],
        "action": template["action"],
        "priority": template["priority"],
        "domain": norm["domain"],
    }

    logger.info(
        "[SIGNAL_RENDERER] render domain=%s type=%s severity=%s "
        "label=%s priority=%s matched_template_key=%s",
        norm["domain"], norm["type"], norm["severity"],
        label, template["priority"], key,
    )
    return rendered


# ══════════════════════════════════════════════════════════════════════
# Selection + conflict resolution
# ══════════════════════════════════════════════════════════════════════

def _signal_recency_key(signal: Any) -> Any:
    """Return a sortable recency value (newer first). Falls back to 0
    when no timestamp is present."""
    for attr in ("created_at", "timestamp", "_created_at"):
        v = (getattr(signal, attr, None)
             if not isinstance(signal, dict)
             else signal.get(attr))
        if v is not None:
            return v
    return 0


def select_top_signals(signals: List[Any], max_n: int = 2) -> List[Dict[str, Any]]:
    """
    Render + sort + take top N. Deterministic, table-driven.

    Sort order (per spec section 6):
        1. priority (foundational > important > supporting)
        2. severity (critical > high > medium > low > positive)
        3. confidence (lower = more urgent)
        4. recency (newer first)

    Foundational signals always surface — they cannot be pushed out of
    the top N by lower-priority items.

    Returns: list of {signal, rendered} dicts, length 0..max_n. Signals
    that don't render (return None) are dropped.
    """
    pool: List[Dict[str, Any]] = []
    for s in signals or []:
        rendered = render_signal(s)
        if rendered is None:
            continue
        pool.append({"signal": s, "rendered": rendered})

    if not pool:
        logger.info("[SIGNAL_RENDERER] top_selected=[] from_pool=0")
        return []

    # Conflict resolution first — drops dominated signals.
    pool = resolve_conflicts(pool)

    def _key(item):
        r = item["rendered"]
        s = item["signal"]
        norm = normalize_signal(s)
        return (
            _PRIORITY_ORDER.get(r["priority"], 9),
            _SEVERITY_ORDER.get(norm["severity"], 9),
            norm["confidence"],  # lower confidence sorts first → more urgent
            # negate recency so newer wins (we sort ascending)
            _negative_recency(s),
        )

    pool.sort(key=_key)

    selected = pool[:max_n]

    logger.info(
        "[SIGNAL_RENDERER] top_selected=%s from_pool=%d",
        [(it["rendered"]["domain"], it["rendered"]["label"]) for it in selected],
        len(pool),
    )
    return selected


def _negative_recency(signal: Any):
    """Helper for sort key — newer recency sorts smaller (i.e. wins)."""
    v = _signal_recency_key(signal)
    try:
        # Datetime: subtract from a far-future date so newer = smaller.
        from datetime import datetime, timezone as _tz
        if isinstance(v, datetime):
            sentinel = datetime(2099, 1, 1, tzinfo=_tz.utc)
            if v.tzinfo is None:
                v = v.replace(tzinfo=_tz.utc)
            return (sentinel - v).total_seconds()
    except Exception:
        pass
    try:
        return -float(v)
    except (TypeError, ValueError):
        return 0


def resolve_conflicts(pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Drop signals dominated by a foundational signal in the same domain.

    Rule (per spec section 7 + guardrails):
        If a foundational signal exists in domain D, suppress all
        lower-priority (important, supporting) signals in domain D.
        Cross-domain coexistence is allowed.

    Logs every suppression with a clear reason.
    """
    foundational_domains = {
        item["rendered"]["domain"]
        for item in pool
        if item["rendered"]["priority"] == "foundational"
    }
    if not foundational_domains:
        return pool

    survivors: List[Dict[str, Any]] = []
    for item in pool:
        r = item["rendered"]
        if (
            r["priority"] != "foundational"
            and r["domain"] in foundational_domains
        ):
            logger.info(
                "[SIGNAL_RENDERER] suppress reason=foundational_dominates "
                "domain=%s suppressed_label=%s suppressed_priority=%s",
                r["domain"], r["label"], r["priority"],
            )
            continue
        survivors.append(item)
    return survivors
