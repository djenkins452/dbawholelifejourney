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


import re


def _to_minutes(st):
    """Parse a rhythm scheduled_time ('HH:MM' or 'H:MM AM/PM') to minutes-of-day, or
    None when unscheduled."""
    if not st:
        return None
    s = str(st).strip().lower()
    m = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm)?", s)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap == "pm" and h != 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    return h * 60 + mi


def _fmt_titles(titles):
    titles = list(titles)
    if len(titles) == 1:
        return titles[0]
    if len(titles) == 2:
        return f"{titles[0]} and {titles[1]}"
    return ", ".join(titles[:-1]) + f", and {titles[-1]}"


def _rhythm_split(user):
    """Split rhythm items by the user's CLOCK (P33.1): (ahead_labels, past_titles,
    hour). 'remaining' items are merely INCOMPLETE — a 6:45 AM item still open at
    noon is PAST, not upcoming. Returns ([], [], hour) on failure."""
    try:
        from apps.core.utils import get_user_now
        from apps.core.cos_briefing.rhythm_api import get_remaining_rhythm_items
        now = get_user_now(user)
    except Exception:
        logger.warning("executive_brief: agenda time failed", exc_info=True)
        return [], [], 9
    now_min = now.hour * 60 + now.minute
    ahead, past = [], []
    try:
        items = get_remaining_rhythm_items(user) or []
    except Exception:
        logger.warning("executive_brief: rhythm items failed", exc_info=True)
        items = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = (it.get("title") or "").strip()
        if not title:
            continue
        mins = _to_minutes(it.get("scheduled_time"))
        if mins is None or mins >= now_min - 5:        # unscheduled or future
            if mins is not None:
                from apps.core.cos_briefing.daily_agenda import _fmt_time
                ahead.append(f"{title} at {_fmt_time(it.get('scheduled_time'))}")
            else:
                ahead.append(title)
        else:
            past.append(title)
    return ahead, past, now.hour


def _agenda_narrative(user, recovery, deprioritized=()):
    """Weave the schedule into the story naturally — never 'coming up', never a past
    item as upcoming, and reconcile a strenuous item with a recovery day. Learned
    de-prioritized items (P36) are NOT elevated into the agenda."""
    ahead, past, hour = _rhythm_split(user)
    dep = [d.lower() for d in (deprioritized or []) if d]
    if dep:
        ahead = [a for a in ahead if not any(t in a.lower() for t in dep)]
        past = [p for p in past if not any(t in p.lower() for t in dep)]
    if hour >= 20:
        return _evening_or_empty(user)
    when = ("This morning" if hour < 12 else
            "This afternoon" if hour < 17 else "This evening")
    parts = []
    if ahead:
        line = f"{when} you've still got {_fmt_titles(ahead[:3])}"
        if recovery:
            line += " — keep it light, none of it has to be heavy"
        parts.append(line + ".")
    else:
        parts.append("Your rhythm's clear for the rest of the day, so the time is yours.")
    if past:
        parts.append("Anything from earlier that's still open — like "
                     + _fmt_titles(past[:2]) + " — is your call, not a fresh start.")
    return " ".join(parts)


def _evening_or_empty(user):
    try:
        from apps.core.cos_briefing.daily_agenda import build_daily_agenda
        return _scrub((build_daily_agenda(user) or "").strip()).strip()
    except Exception:
        logger.warning("executive_brief: agenda fallback failed", exc_info=True)
        return ""


_RAW_WORKLOAD_RE = re.compile(r"\b\d+\s+(pending|open|outstanding|backlog)?\s*tasks?\b")


def _is_raw_workload_claim(t):
    """A raw task-count claim ('22 pending tasks') CONTRADICTS the interpreted
    workload — the interpretation owns workload, so the composer suppresses it."""
    tl = (t or "").lower()
    return bool(_RAW_WORKLOAD_RE.search(tl)) or "pending task" in tl \
        or "tasks pending" in tl or "task backlog" in tl


# ── Section composers (each returns a sentence/paragraph or "") ────────────
def _safe_interpret(user, low_energy=False, subjective=None):
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        return interpret(user, low_energy=low_energy, subjective=subjective)
    except Exception:
        logger.warning("executive_brief: interpretation failed", exc_info=True)
        from apps.ai.chatgpt_cos.executive_interpretation import ExecutiveSignals
        return ExecutiveSignals()


def _reconciliation_story(sig):
    """The LISTENING beat — narrate how the user's OWN report reconciled with the
    numbers. Fires only when the report meaningfully shaped the read, so Beth is
    visibly weighing lived experience against the objective signal, not ignoring it."""
    r = sig.reconciliation
    sh = getattr(sig, "sleep_hours", None)
    num = f"{round(sh, 1)} hours" if isinstance(sh, (int, float)) and sh else "a short night"
    if r == "positive_over_debt":
        return (f"That's actually encouraging. {num[0].upper()}{num[1:]} is below your "
                "long-term goal, but what matters more this morning is that you're telling "
                "me you feel refreshed — and I trust your lived experience. So rather than "
                "treating today as an energy-management day, I'll pay attention to how your "
                "energy actually holds up. Good start; we'll adjust only if it fades.")
    if r == "confirmed_good":
        return ("Good to hear — and the numbers don't argue with you. Nothing about this "
                "morning says slow down, so let's put that energy to work.")
    if r == "negative_no_debt":
        return ("On paper you got a reasonable night, but you're telling me you're running "
                "low — and I'll trust that over the number. Let's keep the load light and "
                "protect your energy today.")
    if r == "confirmed_low":
        return ("That matches what I was seeing — a short night, and you're feeling it. So "
                "energy is the real constraint today.")
    return ""


def _cap(s):
    s = (s or "").strip()
    return (s[0].upper() + s[1:]) if s else s


# ── Narrative beats (P35): the composer is a SPEECHWRITER. Every executive opinion
# below comes from a signal (interpretation owns the judgment); the composer only
# chooses the words, transitions, and emphasis (communication). ───────────────────
def _thesis(sig):
    """NARRATES sig.workload (the judgment). No new conclusion is created here."""
    wl = sig.workload
    if wl in ("light", "manageable"):
        return ("Looking at everything together, today is more manageable than it "
                "probably feels — you don't have an overloaded schedule, just a "
                "healthy backlog that isn't actually due now.")
    if wl == "full":
        return ("Looking at the whole picture, today is full but workable if we're "
                "deliberate about the order things happen in.")
    return ("Looking at the whole picture, today is genuinely heavy, so the move is "
            "to protect the few things that truly matter and let the rest slide.")


def _energy_story(sig, low_energy):
    """NARRATES sig.primary_challenge / sig.challenge_reason — the conclusion that
    energy is the real limiter lives in interpretation. The composer only phrases it
    and cites the supporting evidence (sleep + the conversation's own report)."""
    if sig.primary_challenge != "energy":
        return ""
    parts = ["The bigger challenge today isn't your task list — it's your energy."]
    bits = []
    if sig.sleep_hours:
        bits.append(f"you slept only about {round(sig.sleep_hours)} hours last night")
    if low_energy:
        bits.append("you've told me you're feeling stretched")
    if bits:
        parts.append(_cap(" and ".join(bits)) + ".")
    reason = sig.challenge_reason or "more than the number of open items"
    parts.append("That combination matters " + reason + ".")
    return " ".join(parts)


def _join_levers(levers):
    levers = [l for l in levers if l]
    if len(levers) <= 1:
        return levers[0] if levers else ""
    return ", ".join(levers[:-1]) + ", and " + levers[-1]


def _recommendation(sig):
    """NARRATES sig.disposition + sig.recommendation_levers — the priorities and the
    'what I'd do today' stance are interpretation's judgment, phrased here."""
    disp = _scrub(sig.disposition)
    if not disp:
        return ""
    sentence = "Because of that, " + disp + "."
    levers = _join_levers(sig.recommendation_levers or [])
    if levers:
        sentence += " If we " + levers + ", I'll count today as a win."
    return sentence


def _priority_story(sig):
    """The non-energy day. NARRATES sig.highest_leverage (interpretation's leverage
    judgment) and sig.biggest_risk — the composer does not pick either."""
    if sig.today_count:
        n = sig.today_count
        head = (f"What genuinely needs you today is the {n} item"
                f"{'s' if n != 1 else ''} actually due")
    else:
        head = "Nothing is strictly due today, so this is a day you get to choose"
    lever = _scrub(sig.highest_leverage)
    if lever:
        head += "; beyond that, the real leverage is " + lever
    out = [_cap(head) + "."]
    risk = _scrub(sig.biggest_risk)
    if risk:
        out.append("Keep an eye on " + risk + " — that's the one thing that could "
                   "quietly derail the day.")
    return " ".join(out)


def compose_executive_brief(user, *, lead="", low_energy=False, subjective=None):
    """Compose ONE coherent executive CONVERSATION by NARRATING ExecutiveSignals
    (P35: the composer is a speechwriter — it never invents priorities, leverage,
    recommendations, or executive opinions; those come from interpretation). Synthesis
    over enumeration, no headings, evidence only when it strengthens the point,
    conflicts already reconciled upstream. Deterministic; degrades gracefully.

    `subjective` ('positive'/'negative'/None) is the user's OWN reported state; when it
    shaped the read, the brief LEADS with the reconciliation (the listening beat)
    instead of the generic thesis — so the user hears that Beth weighed what they said."""
    sig = _safe_interpret(user, low_energy=low_energy, subjective=subjective)
    story = []
    if lead:
        story.append(lead.strip())
    recon = _reconciliation_story(sig)
    if recon:
        # The user gave us evidence — reconcile it FIRST, then the day.
        story.append(recon)
        if sig.reconciliation in ("positive_over_debt", "confirmed_good"):
            story.append(_priority_story(sig))          # not an energy day
        else:                                           # negative_no_debt / confirmed_low
            story.append(_energy_story(sig, True))
            story.append(_recommendation(sig))
    else:
        story.append(_thesis(sig))
        if sig.primary_challenge == "energy":
            story.append(_energy_story(sig, low_energy))
            story.append(_recommendation(sig))
        else:
            story.append(_priority_story(sig))
    if sig.backlog_can_wait:
        story.append("The rest of your backlog can wait — none of it is due today.")
    agenda = _agenda_narrative(user, sig.ease_load, deprioritized=sig.deprioritized)
    if agenda:
        story.append(agenda)
    out = " ".join(s for s in story if s).strip()
    if not out:
        out = ("Here's the short version: nothing urgent is flagged right now, and "
               "the day looks manageable from here.")
    return _scrub(out) or out


# ── Executive-presence quality scorer (Acceptance evolution, P32) ──────────
# Internal report headings — implementation artifacts a human CoS would never speak.
_REPORT_HEADINGS = (
    "where things stand", "overall read", "what matters today:", "highest-leverage move:",
    "your biggest risk right now:", "today's agenda —", "on today's agenda", "still ahead:")


def score_executive_presence(text):
    """Score a briefing for EXECUTIVE NARRATIVE quality (P34) — does it read like a
    Chief of Staff thinking with you, or like generated sections? Returns
    {dimension: bool, ..., score}. Headings/repetition are now PENALIZED."""
    t = (text or "").lower()
    dims = {
        # no visible report headings / implementation artifacts
        "no_report_headings": not any(h in t for h in _REPORT_HEADINGS),
        # synthesis — connects the picture rather than enumerating sections
        "synthesis": any(k in t for k in (
            "looking at everything", "whole picture", "together", "the bigger challenge",
            "more than", "matters more")),
        # explains WHY conclusions/priorities matter
        "explains_why": any(k in t for k in (
            "because", "that matters", "which is why", "that combination", "so the move",
            "that's where", "compounds", "so this is")),
        # expresses executive judgment (a recommendation in the first person)
        "judgment": any(k in t for k in (
            "i wouldn't", "i'd", "i'll count", "i'll call", "the real leverage",
            "what genuinely needs you", "the move is", "i'd treat")),
        # actionable and integrated
        "actionability": any(k in t for k in (
            "protect", "keep", "take care", "move", "handle", "focus", "your call")),
        # temporal correctness (never frames items as upcoming when past)
        "temporal_ok": "coming up" not in t,
        # conversational — prose, not colon-delimited section blocks
        "conversational": (len(t) > 120 and t.count(":") <= 1 and "\n\n" not in t),
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
    import re as _re
    dims = {
        # workload is an interpreted band, not a bare verdict from a count
        "workload_interpreted": any(k in t for k in (
            "manageable", "overloaded schedule", "full but workable", "genuinely heavy",
            "recovery day", "more manageable than", "workable")),
        # a large backlog is named as backlog/strategic/upcoming, not "today's load"
        "backlog_distinguished": (any(k in t for k in (
            "backlog", "longer-term", "upcoming", "strategic", "can wait"))
            if mentions_many else True),
        # never ASSERTS overload (a negated "no overloaded schedule" is fine)
        "no_count_overload": not (bool(_re.search(
            r"(is|are|you're|youre)\s+overload", t)) or "high workload" in t),
        # today's commitments lead, not the total pending number
        "today_first": any(k in t for k in (
            "due today", "actually due", "genuinely due", "strictly due",
            "nothing is due", "clean slate")),
        # P33.1: the interpreted conclusion is NOT contradicted later by a raw count
        "no_raw_workload": not _is_raw_workload_claim(t),
        # P33.1: the composer owns temporal framing — never frames items as "coming up"
        "no_past_as_coming_up": "coming up" not in t,
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
