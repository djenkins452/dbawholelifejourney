"""Phase 0 Health Retrieval Probe — LOG ONLY.

For every health question, logs safe metadata so we can pin WHY glucose/nutrition
returned stale/alternate values WITHOUT a blind fix:

  domain, question class (latest/today/summary), route fired + name, canonical
  latest value, canonical summary value, value(s) in the answer, whether the
  summary value appears in the assembled LLM context, whether memory was
  injected, a stale-contradiction flag, and a message HASH (never raw text).

No behavior change. No DB writes. Gated by WLJ_BETH_HEALTH_PROBE_ENABLED
(default ON). Every function is guaranteed not to raise.
"""

from __future__ import annotations

import hashlib
import logging
import re

logger = logging.getLogger("apps.ai.health_retrieval")


def probe_enabled() -> bool:
    try:
        from django.conf import settings
        return bool(getattr(settings, "WLJ_BETH_HEALTH_PROBE_ENABLED", True))
    except Exception:
        return True


# Domain detection (first match wins; order matters — glucose before nutrition).
_DOMAIN_KEYWORDS = (
    ("glucose", ("glucose", "blood sugar", "blood glucose", "a1c", "cgm")),
    ("nutrition", ("calorie", "calories", "protein", "carbs", "carbohydrate",
                   "macro", "macros", "nutrition", "fiber")),
    ("weight", ("weight", "weigh", "weighed", "pounds", " lbs")),
    ("sleep", ("sleep", "slept")),
    ("workout", ("workout", "exercise", "training", "gym", "lift", "lifting")),
)

_SUMMARY_CUES = ("average", "avg", "trend", "this week", "past week", "lately",
                 "how has", "how have", "weekly", "on average", "been sleeping")
_TODAY_CUES = ("today", "so far today")
_LATEST_CUES = ("last", "latest", "current", "most recent", "when", "how did",
                "right now", "tonight", "this morning")

_NUM_RE = re.compile(r"\d{1,4}(?:\.\d)?")


def classify(message: str):
    """(domain, question_class) or (None, None) if not a health question."""
    m = (message or "").lower()
    domain = None
    for d, kws in _DOMAIN_KEYWORDS:
        if any(k in m for k in kws):
            domain = d
            break
    if domain is None:
        return None, None
    if any(c in m for c in _SUMMARY_CUES):
        qclass = "summary"
    elif any(c in m for c in _TODAY_CUES):
        qclass = "today"
    elif any(c in m for c in _LATEST_CUES):
        qclass = "latest"
    else:
        qclass = "status"
    return domain, qclass


def _canonical(user, domain):
    """(latest_value, summary_value). Values may be numbers or strings (workout)."""
    try:
        from apps.core.ai_state.state_engine import get_module_state
        if domain == "glucose":
            h = get_module_state(user, "health") or {}
            gl = h.get("glucose_latest") or {}
            return gl.get("value"), h.get("glucose_avg_7d")
        if domain == "weight":
            h = get_module_state(user, "health") or {}
            w = h.get("weight_current")
            return w, w
        if domain == "nutrition":
            n = get_module_state(user, "nutrition") or {}
            return n.get("daily_calories"), n.get("rolling_7d_calories_avg")
        if domain == "sleep":
            h = get_module_state(user, "health") or {}
            return h.get("sleep_last_night_hours"), h.get("sleep_avg_hours_7d")
        if domain == "workout":
            f = get_module_state(user, "fitness") or {}
            lw = f.get("last_workout") or {}
            return lw.get("name"), f.get("workouts_7d")
    except Exception:
        return None, None
    return None, None


def _nums(text):
    out = []
    for x in _NUM_RE.findall(text or ""):
        try:
            out.append(float(x))
        except ValueError:
            pass
    return out


def _approx_in(value, numbers, tol=0.5):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return any(abs(n - v) <= tol for n in numbers)


def _hash(message: str) -> str:
    norm = re.sub(r"\s+", " ", (message or "").lower().strip())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def log_health_retrieval(user, message, *, route_name, route_fired, handler,
                         response, memory_injected, llm_context):
    """Emit one safe-metadata log line for a health question. Never raises."""
    if not probe_enabled():
        return
    try:
        domain, qclass = classify(message or "")
        if domain is None:
            return
        latest, summary = _canonical(user, domain)
        answer_nums = _nums(response)
        summary_in_context = (
            isinstance(summary, (int, float))
            and _approx_in(summary, _nums(llm_context))
        )
        # Stale contradiction: a latest/today question whose answer contains the
        # SUMMARY value but NOT the canonical latest/today value.
        stale = False
        if qclass in ("latest", "today") and isinstance(summary, (int, float)) \
                and isinstance(latest, (int, float)):
            stale = _approx_in(summary, answer_nums) and not _approx_in(latest, answer_nums)
        logger.warning(
            "HEALTH_PROBE domain=%s qclass=%s route_fired=%s route=%s handler=%s "
            "canon_latest=%s canon_summary=%s answer_nums=%s memory_injected=%s "
            "summary_in_context=%s stale=%s msg_hash=%s",
            domain, qclass, route_fired, route_name, handler, latest, summary,
            answer_nums, memory_injected, summary_in_context, stale, _hash(message),
        )
    except Exception:
        logger.debug("health retrieval probe failed (non-fatal)", exc_info=True)
