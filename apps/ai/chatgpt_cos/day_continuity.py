# ==============================================================================
# File: apps/ai/chatgpt_cos/day_continuity.py
# Capability: DAY CONTINUITY — Beth works ALONGSIDE the executive all day rather than
# waking up fresh every time he opens chat. She continues the day: she knows whether she
# has already oriented Danny today, what has already been covered, and — the primary
# determinant — whether the executive picture has MATERIALLY CHANGED since. Time of day
# and new chat sessions are secondary signals; the decision is driven by continuity +
# operational change, not by "how much time passed".
#
# This is NOT long-term memory and NOT learning (Phase 4). It is a LIGHT, EPHEMERAL,
# per-user, per-LOCAL-DAY ledger of what has been established today, kept in cache (expires
# at local midnight). Request-path safe: it only reads/writes a tiny dict and derives a
# fingerprint from the ExecutiveSignals the orientation path ALREADY computes — never any
# new heavy computation.
#
# Decision (reasoned, never "IF afternoon THEN"):
#   • First conversation today            → full orientation (as before)
#   • Oriented + picture MATERIALLY changed → concise UPDATED orientation (the delta)
#   • Oriented + nothing material changed  → continue naturally (no replay), any time
# ==============================================================================
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

_KEY_PREFIX = "wlj:cos:day_continuity"
_TTL_FALLBACK = 20 * 3600


def _local_now(user):
    from apps.core.utils import get_user_now
    return get_user_now(user)


def _key(user):
    uid = getattr(user, "id", None)
    try:
        day = _local_now(user).date().isoformat()
    except Exception:
        day = "na"
    return f"{_KEY_PREFIX}:{uid}:{day}"


def _ttl(user):
    """Seconds until local midnight (+buffer) so the ledger is strictly TODAY's."""
    try:
        from datetime import datetime, time, timedelta
        now = _local_now(user)
        midnight = datetime.combine((now + timedelta(days=1)).date(), time.min,
                                    tzinfo=now.tzinfo)
        return max(300, min(int((midnight - now).total_seconds()) + 120, 26 * 3600))
    except Exception:
        return _TTL_FALLBACK


def read_day(user):
    try:
        return cache.get(_key(user)) or {}
    except Exception:
        return {}


def is_first_today(user):
    """True when Beth has not yet oriented the executive today."""
    return not read_day(user).get("oriented")


# ── The day's executive-picture FINGERPRINT (material-change detection) ───────
def _num(x):
    try:
        return int(x or 0)
    except Exception:
        return 0


def _t(v):
    if isinstance(v, dict):
        return (v.get("text") or "").strip().lower()[:80]
    return str(v or "").strip().lower()[:80]


def compute_fingerprint(sig):
    """A compact, comparable snapshot of the facts that define today's orientation — read
    straight off the already-computed ExecutiveSignals (no new work)."""
    if sig is None:
        return {}
    hc = getattr(sig, "health_critical", None) or []
    mission = getattr(sig, "mission", None) or {}
    return {
        "priority": _t(getattr(sig, "priority_action", None)),
        "risk": _t(getattr(sig, "biggest_risk", "")),
        "today": _num(getattr(sig, "today_count", 0)),
        "overdue": _num(getattr(sig, "overdue_count", 0)),
        "done": len(getattr(sig, "accomplishments", None) or []),
        "foundation": len(getattr(sig, "foundation", None) or []),
        "hc": sorted(_t(h) for h in hc),
        "focus": _t(mission.get("current_focus")),
    }


def material_changes(prev, cur):
    """Human-readable list of what has MATERIALLY changed since the last orientation.
    Empty list ⇒ nothing worth re-orienting for (continue naturally)."""
    if not prev:
        return []
    ch = []
    if cur.get("done", 0) > prev.get("done", 0):
        n = cur["done"] - prev["done"]
        ch.append(f"you've knocked out {n} more thing{'s' if n != 1 else ''} "
                  "since we last talked")
    if cur.get("foundation", 0) > prev.get("foundation", 0):
        ch.append("you've laid your foundation for the day")
    if cur.get("hc") != prev.get("hc"):
        if cur.get("hc") and not prev.get("hc"):
            ch.append("a health-critical item has come up")
        elif prev.get("hc") and not cur.get("hc"):
            ch.append("the health-critical item is cleared")
        else:
            ch.append("the health-critical picture has shifted")
    if cur.get("priority") and cur.get("priority") != prev.get("priority"):
        ch.append("your most important next move has changed")
    if (cur.get("overdue", 0) != prev.get("overdue", 0)
            or cur.get("today", 0) != prev.get("today", 0)):
        ch.append("your schedule has shifted")
    if cur.get("risk") and cur.get("risk") != prev.get("risk"):
        ch.append("there's a new risk worth flagging")
    if cur.get("focus") and cur.get("focus") != prev.get("focus"):
        ch.append("you've reached a new milestone on your mission")
    return ch


class Decision:
    """mode ∈ {orient_full, reorient_delta, continue}. `sig` is the ExecutiveSignals used
    (carried so a caller doesn't recompute), `fingerprint` is today's snapshot to store."""
    def __init__(self, mode, changes, fingerprint, sig):
        self.mode = mode
        self.changes = changes
        self.fingerprint = fingerprint
        self.sig = sig


def assess(user, sig=None):
    """Reason about day continuity: first orientation, a material change worth a concise
    re-orientation, or nothing changed (continue). Never raises."""
    if sig is None:
        try:
            from apps.ai.chatgpt_cos.executive_interpretation import interpret
            sig = interpret(user)
        except Exception:
            sig = None
    fp = compute_fingerprint(sig)
    day = read_day(user)
    if not day.get("oriented"):
        return Decision("orient_full", [], fp, sig)
    changes = material_changes(day.get("fingerprint") or {}, fp)
    return Decision("reorient_delta" if changes else "continue", changes, fp, sig)


def mark_established(user, fingerprint, topics=None):
    """Record that Beth has oriented the executive today, with the current picture
    fingerprint and the topics covered. Idempotent; extends the day's ledger."""
    try:
        day = read_day(user)
        now = _local_now(user)
        day["oriented"] = True
        day["fingerprint"] = fingerprint or {}
        day["last_seen"] = now.isoformat()
        day.setdefault("first_seen", now.isoformat())
        day["topics"] = sorted(set(day.get("topics") or []) | set(topics or []))
        day["count"] = _num(day.get("count")) + 1
        cache.set(_key(user), day, _ttl(user))
    except Exception:
        logger.warning("day_continuity.mark_established failed", exc_info=True)


# ── Natural continuation voice (daypart-aware, never a replayed orientation) ──
def _daypart(user):
    try:
        from apps.core.truth.daypart import resolve
        return resolve(user) or {}
    except Exception:
        return {}


def _hello(user):
    phase = _daypart(user).get("phase")
    return {"morning": "Good morning again", "midday": "Welcome back",
            "evening": "Good evening", "night": "Good evening"}.get(phase, "Welcome back")


def _open_question(user):
    stance = _daypart(user).get("stance")
    if stance == "close_out":
        return "How are you holding up as you wrap up today?"
    if stance == "wind_down":
        return "How's the day landing?"
    return "How are things going?"


def _join(items):
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + ", and " + items[-1]


def compose_continuation(user, sig, decision):
    """The RETURNING-conversation response: continue the day. On a material change, surface
    the DELTA concisely (not a replay); otherwise acknowledge progress and hand back. Never
    re-runs the morning orientation (no sleep recap, no full agenda)."""
    parts = [f"{_hello(user)}, Danny."]
    if decision.mode == "reorient_delta" and decision.changes:
        delta = _join(decision.changes)
        parts.append((delta[0].upper() + delta[1:]).rstrip(".") + ".")
        pa = getattr(sig, "priority_action", None)
        if isinstance(pa, dict) and (pa.get("text") or "").strip():
            parts.append("The one thing to keep in front of you now is "
                         f"{pa['text'].strip().rstrip('.')}.")
    else:
        parts.append("You've already made good progress today, and nothing new has come "
                     "up since we last talked.")
    parts.append(_open_question(user))
    return " ".join(p for p in parts if p).strip()
