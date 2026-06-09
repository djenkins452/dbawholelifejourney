"""Health truth guard + diagnostic (P1 weight-contradiction fix — Layer 1).

The canonical current weight is SAE `get_module_state(user,'health')['weight_current']`.
Beth must never state a *current* weight that contradicts it (the 289.9-vs-287.3
trust break). This module provides:

  - correct_weight_contradictions(): source-agnostic, in-place correction of any
    CURRENT-weight assertion in Beth's reply that differs from canonical. Precise
    by design — it only touches phrases that assert the user's current weight, so
    goal weights, lifted weights, and historical/trend numbers are left intact.
  - log_weight_diagnostic(): log-only probe that records the canonical weight, all
    weight-like numbers in the assembled LLM context, all in the draft response,
    the route, and a message HASH — so we can pin exactly where a stale weight
    enters (context assembly vs LLM generation/history) and aim Layer 2 precisely.

No DB writes. No migration. Gated by flags (default ON):
  WLJ_BETH_WEIGHT_GUARD_ENABLED   — the correction guard
  WLJ_BETH_WEIGHT_DIAG_ENABLED    — the diagnostic logging
"""

from __future__ import annotations

import hashlib
import logging
import re

logger = logging.getLogger("apps.ai.health_truth")

# Plausible human body-weight range (lb or kg) — avoids "correcting" unrelated
# numbers that happen to sit near a weight word.
_PLAUSIBLE_MIN = 40.0
_PLAUSIBLE_MAX = 1000.0
_DEFAULT_TOL = 1.0  # lb/kg; below this we treat values as the same reading

# CURRENT-weight assertions ONLY. group(1)=prefix to keep, group(2)=the number,
# optional group(3)=trailing unit to keep. Anything not matching these (goal
# weights, "down from 295 to 289", "squat 225 lb") is deliberately left alone.
_CURRENT_WEIGHT_PATTERNS = (
    re.compile(r"(currently\s+(?:at|weigh(?:ing)?(?:\s+in\s+at)?)\s+)(\d{2,4}(?:\.\d)?)", re.I),
    re.compile(r"(current\s+weight\s*(?::|is|of)?\s*)(\d{2,4}(?:\.\d)?)", re.I),
    re.compile(r"(your\s+weight\s+is\s+(?:currently\s+|now\s+)?(?:at\s+)?)(\d{2,4}(?:\.\d)?)", re.I),
    re.compile(r"(you(?:'re|\s+are)\s+(?:currently\s+)?(?:at\s+|weighing\s+)?)(\d{2,4}(?:\.\d)?)(\s*(?:lbs?|pounds|kg))", re.I),
    re.compile(r"(weighing\s+(?:in\s+at\s+)?)(\d{2,4}(?:\.\d)?)", re.I),
)

# Any weight-like figure (number adjacent to a weight unit) — diagnostic only.
_ANY_WEIGHT_RE = re.compile(r"(\d{2,4}(?:\.\d)?)\s*(?:lbs?|pounds|kg)\b", re.I)


def _flag(name: str, default: bool = True) -> bool:
    try:
        from django.conf import settings
        return bool(getattr(settings, name, default))
    except Exception:
        return default


def weight_guard_enabled() -> bool:
    return _flag("WLJ_BETH_WEIGHT_GUARD_ENABLED", True)


def weight_diag_enabled() -> bool:
    return _flag("WLJ_BETH_WEIGHT_DIAG_ENABLED", True)


def ensure_health_fresh(user):
    """Repair a stale SAE health snapshot before a request-path read.

    Makes canonical health state fresh BY DESIGN (not corrected after the fact):
    if a weight/glucose/sleep row is newer than the snapshot, rebuild the health
    module so every consumer (cos_context, analyze lane, deterministic routes,
    dashboard reasoning) reads the same current value. Never raises.
    """
    try:
        from apps.core.ai_state.state_freshness import ensure_fresh
        return ensure_fresh(user, ["health"])
    except Exception:
        logger.debug("ensure_health_fresh failed (non-fatal)", exc_info=True)
        return set()


def get_fresh_weight(user):
    """Live latest WeightEntry — the authoritative source the UI and
    build_health_state read. Never stale. (value, unit) or (None, None).

    Root cause of the 287.3-vs-289.9 regression: the SAE health snapshot is NOT
    invalidated when a WeightEntry is written (no post_save fire_intelligence,
    and 'health' isn't an ensure_fresh module), so SAE.weight_current can lag.
    The truth guard must reference the LIVE table, not the stale snapshot.
    """
    try:
        from apps.health.models import WeightEntry
        row = (
            WeightEntry.objects.filter(user=user)
            .order_by("-recorded_at")
            .values_list("value", "unit")
            .first()
        )
        if row and row[0] is not None:
            return float(row[0]), (row[1] or "lb")
    except Exception:
        logger.debug("get_fresh_weight failed", exc_info=True)
    return None, None


def get_canonical_weight(user):
    """Canonical current weight. Prefers the LIVE latest WeightEntry so the truth
    guard is never defeated by a stale SAE snapshot. Logs SAE drift for telemetry.
    Falls back to SAE only if the live read fails."""
    fresh, unit = get_fresh_weight(user)
    if fresh is not None:
        try:
            from apps.core.ai_state.state_engine import get_module_state
            sae = (get_module_state(user, "health") or {}).get("weight_current")
            if isinstance(sae, (int, float)) and abs(float(sae) - fresh) > 1.0:
                logger.warning(
                    "WEIGHT_STALE_SAE user=%s sae=%.1f live=%.1f — guard using live",
                    getattr(user, "id", "?"), float(sae), fresh,
                )
        except Exception:
            pass
        return fresh, unit
    # Fallback: SAE snapshot (live read failed).
    try:
        from apps.core.ai_state.state_engine import get_module_state
        h = get_module_state(user, "health") or {}
        w = h.get("weight_current")
        if w is not None:
            return float(w), h.get("weight_unit", "lb")
    except Exception:
        logger.debug("get_canonical_weight SAE fallback failed", exc_info=True)
    return None, None


def correct_weight_contradictions(text, canonical, unit="lb", tol=_DEFAULT_TOL):
    """Replace any CURRENT-weight assertion that contradicts `canonical`.

    Returns (corrected_text, corrections) where corrections is a list of
    (found_value, canonical_value). Never raises.
    """
    if not text or canonical is None or not weight_guard_enabled():
        return text, []
    try:
        canon = float(canonical)
    except (TypeError, ValueError):
        return text, []

    canon_str = f"{canon:.1f}"
    corrections = []

    def _fix(m):
        prefix = m.group(1)
        num = m.group(2)
        trailing = m.group(3) if (m.lastindex and m.lastindex >= 3) else ""
        try:
            val = float(num)
        except ValueError:
            return m.group(0)
        if not (_PLAUSIBLE_MIN <= val <= _PLAUSIBLE_MAX):
            return m.group(0)  # not a body weight — leave it
        if abs(val - canon) <= tol:
            return m.group(0)  # already canonical
        corrections.append((val, canon))
        return f"{prefix}{canon_str}{trailing}"

    out = text
    for pat in _CURRENT_WEIGHT_PATTERNS:
        out = pat.sub(_fix, out)
    return out, corrections


def extract_all_weight_values(text):
    """All weight-like numeric values in plausible body-weight range."""
    vals = []
    for m in _ANY_WEIGHT_RE.finditer(text or ""):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if _PLAUSIBLE_MIN <= v <= _PLAUSIBLE_MAX:
            vals.append(v)
    return sorted(set(vals))


def _hash_message(message: str) -> str:
    norm = re.sub(r"\s+", " ", (message or "").lower().strip())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def log_weight_diagnostic(user, route, message, llm_context, draft_response, canonical):
    """Log-only probe to pin where a stale weight enters. Never raises.

    Records canonical weight, weight numbers present in the assembled LLM
    CONTEXT vs the DRAFT response, the route, and a message hash. If a
    contradictory weight appears in the draft but NOT the context, the source is
    LLM generation/history; if it's in the context, the source is assembly.
    """
    if not weight_diag_enabled():
        return
    try:
        ctx_vals = extract_all_weight_values(llm_context or "")
        draft_vals = extract_all_weight_values(draft_response or "")
        contradiction = False
        in_context = None
        if canonical is not None:
            bad = [v for v in draft_vals if abs(v - float(canonical)) > _DEFAULT_TOL]
            contradiction = bool(bad)
            if bad:
                in_context = any(abs(v - b) <= _DEFAULT_TOL for v in ctx_vals for b in bad)
        logger.warning(
            "WEIGHT_DIAG user=%s route=%s canonical=%s ctx_weights=%s "
            "draft_weights=%s contradiction=%s stale_in_context=%s msg_hash=%s",
            getattr(user, "id", "?"), route, canonical, ctx_vals, draft_vals,
            contradiction, in_context, _hash_message(message),
        )
    except Exception:
        logger.debug("log_weight_diagnostic failed (non-fatal)", exc_info=True)
