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
def _safe_interpret(user):
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        return interpret(user)
    except Exception:
        logger.warning("executive_brief: interpretation failed", exc_info=True)
        from apps.ai.chatgpt_cos.executive_interpretation import ExecutiveSignals
        return ExecutiveSignals()


def _orientation(sig, es):
    # Lead with the INTERPRETED executive thesis (workload judged by horizon), not a
    # raw metric or trajectory phrase.
    head = _scrub(sig.headline) or _text(es.get("headline")) or _text(es.get("trajectory"))
    return ("Where things stand: " + _ensure_sentence(head)) if head else ""


def _assessment(sig, low_energy=False):
    summary = _scrub(sig.workload_summary)
    if low_energy or sig.recovery_needed:
        base = "Overall read: treat today as a recovery day"
        if summary:
            base += " — " + summary
        return base + ". Protect your energy before pushing performance."
    base = "Overall read: " + (summary or f"a {sig.workload} day")
    return base + f" — so this is a {sig.workload} day, not an overloaded one."


def _priorities(sig, es):
    """Today's COMMITMENTS first — never the total pending count as a priority."""
    bits = []
    if sig.today_count:
        bits.append(f"{sig.today_count} item{'s' if sig.today_count != 1 else ''} due today")
    if sig.overdue_count:
        bits.append(f"{sig.overdue_count} overdue to clear")
    na = [_text(i) for i in (es.get("needs_attention") or [])]
    bits.extend([t for t in na if t][:2])
    if bits:
        return "What matters today: " + "; ".join(bits) + "."
    return ("What matters today: nothing is due today and nothing is flagged — a "
            "clean slate, so it's your call on where to focus.")


def _risk(sig):
    r = _scrub(sig.biggest_risk)
    return ("Your biggest risk right now: " + _ensure_sentence(r)) if r else ""


def _recommendation(sig):
    rec = _scrub(sig.highest_leverage)
    return ("Highest-leverage move: " + _ensure_sentence(rec)) if rec else ""


def compose_executive_brief(user, *, lead="", low_energy=False):
    """Compose a Chief-of-Staff executive briefing from INTERPRETED ExecutiveSignals
    (P33) — orientation first, AGENDA LAST. The composer NARRATES judgment; it never
    re-infers conclusions from raw metrics (e.g. '22 pending' never becomes
    'overload'). Always non-empty; degrades gracefully; deterministic."""
    sig = _safe_interpret(user)
    es = _safe_exec_summary(user)
    blocks = []
    if lead:
        blocks.append(lead.strip())
    for section in (_orientation(sig, es), _assessment(sig, low_energy=low_energy),
                    _priorities(sig, es), _risk(sig), _recommendation(sig)):
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


def score_executive_judgment(text):
    """Score a briefing for EXECUTIVE JUDGMENT (P33) — does it interpret facts like a
    Chief of Staff, or report raw counts? Deterministic heuristics. Returns
    {dimension: bool, ..., score}."""
    t = (text or "").lower()
    mentions_many = any(str(n) in t for n in range(11, 100)) or "backlog" in t \
        or "pending" in t or "open item" in t
    dims = {
        # workload is an interpreted band, not a bare verdict from a count
        "workload_interpreted": any(
            f"workload is {w}" in t or f"a {w} day" in t or f"{w} day" in t
            for w in ("light", "manageable", "full", "heavy", "overloaded")),
        # a large backlog is named as backlog/strategic/upcoming, not "today's load"
        "backlog_distinguished": (any(k in t for k in (
            "backlog", "longer-term", "upcoming", "strategic"))
            if mentions_many else True),
        # never concludes overload from a raw count (overload only with a real today-load)
        "no_count_overload": not ("overload" in t and "due today" not in t),
        # today's commitments lead, not the total pending number
        "today_first": any(k in t for k in (
            "due today", "nothing is due today", "clean slate")),
    }
    dims["score"] = round(sum(1 for v in dims.values() if v) / len(dims), 2)
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
