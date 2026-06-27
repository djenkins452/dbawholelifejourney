# ==============================================================================
# File: apps/ai/chatgpt_cos/executive_brief.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Executive Brief Composer (P32). COMPOSES the output of systems that
#   already exist — executive_summary (trajectory/assessment/needs_attention/
#   biggest_risk/recommendations) + the time-aware daily_agenda — into a coherent
#   Chief-of-Staff briefing. It is NOT a planner, reasoning engine, or prioritizer:
#   it owns only HOW the facts are ordered and narrated. Deterministic, request-path
#   safe, degrades gracefully. Structure: orientation -> assessment -> priorities ->
#   risk -> highest-leverage move -> AGENDA LAST (never the headline). The composer
#   (not the agenda) owns the temporal decision.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)


def _scrub(s):
    """Strip generic-coaching phrases from echoed executive-summary prose so the
    brief never leaks banned language (reuses the P30 substance-preserving scrubber)."""
    try:
        from apps.ai.chatgpt_cos.reasoning.stages import _scrub_coaching
        return _scrub_coaching(s) or ""
    except Exception:
        return s or ""


def _text(item):
    """Defensively extract a display string from a signal (str or dict), scrubbed of
    coaching language."""
    if not item:
        return ""
    if isinstance(item, str):
        raw = item.strip()
    elif isinstance(item, dict):
        raw = (item.get("message") or item.get("title") or item.get("phrase")
               or item.get("concern") or "").strip()
    else:
        raw = str(item).strip()
    return _scrub(raw).strip()


def _ensure_sentence(s):
    s = (s or "").strip()
    if s and s[-1] not in ".!?":
        s += "."
    return s


def _safe_exec_summary(user):
    try:
        from apps.core.cos_briefing.executive_summary import build_executive_summary
        es = build_executive_summary(user)
        return es if isinstance(es, dict) else {}
    except Exception:
        logger.warning("executive_brief: exec summary failed", exc_info=True)
        return {}


def _agenda(user):
    try:
        from apps.core.cos_briefing.daily_agenda import build_daily_agenda
        return _scrub((build_daily_agenda(user) or "").strip()).strip()
    except Exception:
        logger.warning("executive_brief: agenda failed", exc_info=True)
        return ""


# ── Section composers (each returns a sentence/paragraph or "") ────────────
def _orientation(es):
    lenses = es.get("executive_lenses") or {}
    overall = (_text(lenses.get("overall")) or _text(es.get("headline"))
               or _text(es.get("trajectory")))
    return ("Where things stand: " + _ensure_sentence(overall)) if overall else ""


def _assessment(es, low_energy=False):
    """A one-line executive read: strong / recovery / heavier / steady day."""
    if low_energy:
        return ("Overall read: let's treat today as a recovery day — protect your "
                "energy and keep the load light.")
    traj = _text(es.get("trajectory")).lower()
    has_risk = bool(_text(es.get("biggest_risk")))
    n_attn = len([i for i in (es.get("needs_attention") or []) if _text(i)])
    if has_risk or n_attn >= 3:
        label = "a heavier day with something real to manage"
    elif any(w in traj for w in ("strong", "ahead", "improv", "rising", "thriv")):
        label = "a strong day — you're in good shape"
    elif any(w in traj for w in ("recover", "behind", "declin", "slip", "falling")):
        label = "a recovery day — steady the ship before pushing"
    else:
        label = "a steady, manageable day"
    return f"Overall read: this is shaping up to be {label}."


def _priorities(es):
    na = [_text(i) for i in (es.get("needs_attention") or [])]
    titles = [t for t in na if t][:3]
    if titles:
        return "What matters today: " + "; ".join(titles) + "."
    return ("What matters today: nothing is flagged as needing attention — a clean "
            "slate, so it's your call on where to focus.")


def _risk(es):
    r = _text(es.get("biggest_risk"))
    return ("Your biggest risk right now: " + _ensure_sentence(r)) if r else ""


def _recommendation(es):
    recs = es.get("recommendations") or []
    rec = next((_text(x) for x in recs if _text(x)), "")
    if not rec:
        rec = _text((es.get("executive_lenses") or {}).get("opportunity"))
    return ("Highest-leverage move: " + _ensure_sentence(rec)) if rec else ""


def compose_executive_brief(user, *, lead="", low_energy=False):
    """Compose a Chief-of-Staff executive briefing. Orientation first, AGENDA LAST.
    Always non-empty; degrades gracefully when data is thin. Deterministic — works
    with OpenAI disabled."""
    es = _safe_exec_summary(user)
    blocks = []
    if lead:
        blocks.append(lead.strip())
    for section in (_orientation(es), _assessment(es, low_energy=low_energy),
                    _priorities(es), _risk(es), _recommendation(es)):
        if section:
            blocks.append(section)
    agenda = _agenda(user)
    if agenda:
        # AGENDA LAST and framed as supporting detail — never "coming up" as a
        # headline. The daily_agenda is itself time-aware (past != upcoming).
        blocks.append("Then, on today's agenda — " + agenda)
    body = [b for b in blocks if b]
    if not body or (lead and len(body) == 1):
        body.append("Here's your executive read: nothing urgent is flagged right "
                    "now, and the day looks manageable from here.")
    return "\n\n".join(body)


# ── Executive-presence quality scorer (Acceptance evolution, P32) ──────────
def score_executive_presence(text):
    """Score a briefing for EXECUTIVE PRESENCE (not correctness). Deterministic
    heuristics over the rendered text. Returns {dimension: bool, ..., score: 0..1}.
    Used by scenario-based Acceptance to grade conversation quality."""
    t = (text or "").lower()
    dims = {
        "orientation": any(k in t for k in (
            "where things stand", "where you stand", "here's where", "you stand",
            "executive read", "where do i stand")),
        "assessment": any(k in t for k in (
            "overall read", "overall,", "shaping up", "strong day", "recovery day",
            "steady", "heavier day", "manageable day")),
        "prioritization": any(k in t for k in (
            "what matters today", "matters today", "your biggest", "priorit",
            "needs attention", "clean slate")),
        "synthesis": (len(t) > 120 and t.count("\n") >= 1),   # composed, not one line
        "temporal_awareness": ("coming up" not in t) or ("still ahead" in t
                                                          or "left today" in t),
        "actionability": any(k in t for k in (
            "highest-leverage move", "next step", "best next", "focus on",
            "start with", "a good next")),
        "agenda_ordering": _agenda_is_last(t),
    }
    score = round(sum(1 for v in dims.values() if v) / len(dims), 2)
    dims["score"] = score
    return dims


def _agenda_is_last(t):
    """The agenda must NOT be the headline: orientation/priorities precede it."""
    agenda_marker = next((m for m in ("on today's agenda", "today's agenda",
                                      "on your agenda", "coming up") if m in t), None)
    if agenda_marker is None:
        return True                       # no agenda section -> trivially fine
    pos = t.find(agenda_marker)
    lead_in = any(k in t[:pos] for k in (
        "where things stand", "overall read", "what matters today", "biggest risk",
        "highest-leverage", "executive read"))
    return lead_in
