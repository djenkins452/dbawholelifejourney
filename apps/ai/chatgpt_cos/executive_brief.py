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
        row = dict(it)
        if mins is not None:
            from apps.core.cos_briefing.daily_agenda import _fmt_time
            row["_label"] = f"{title} at {_fmt_time(it.get('scheduled_time'))}"
        else:
            row["_label"] = title
        if mins is None or mins >= now_min - 5:        # unscheduled or future
            ahead.append(row)
        else:
            past.append(row)
    return ahead, past, now.hour


# A task that is part of the user's normal OPERATING RHYTHM (logging, tracking, weighing
# in, hydrating) — not a discrete commitment. It rides in the same daily cadence and
# should not compete with a real commitment ("pick up the motorcycle", "call the dentist")
# for the user's attention, even though it is a "task" by source_type.
_ROUTINE_OPERATING_RE = re.compile(
    r"^\s*(log|logging|track|record|update|weigh|weigh[\s-]?in|journal|check[\s-]?in|"
    r"hydrate|drink water|stretch|take (my|your) (vitamins|supplements)|meal prep)\b",
    re.IGNORECASE)


def _is_routine_operating_task(title):
    """A logging/tracking task that is part of the daily operating rhythm, not a
    meaningful commitment."""
    return bool(_ROUTINE_OPERATING_RE.match((title or "").strip()))


def _agenda_worth_surfacing(it):
    """Executive filter: a Chief of Staff does not read the whole list. Two kinds of work
    that don't deserve airtime next to a real commitment: (1) ROUTINE items by nature —
    a supplement dose, a scheduled routine (priority-tier classifier); (2) OPERATING-
    RHYTHM tasks — 'log nutrition', 'weigh in' — which are cadence, not commitments, even
    when stored as a 'task'. Keep meaningful items (appointments, real tasks, prescriptions,
    mission work); drop routine + operating-rhythm. Deterministic."""
    if _is_routine_operating_task(it.get("title")):
        return False
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import _pa_classify
        tier, _ = _pa_classify(it)
        return tier != "routine"
    except Exception:
        return True


def _agenda_narrative(user, recovery, deprioritized=()):
    """Weave the schedule into the story naturally — never 'coming up', never a past
    item as upcoming, and reconcile a strenuous item with a recovery day. Learned
    de-prioritized items (P36) are NOT elevated into the agenda."""
    ahead, past, hour = _rhythm_split(user)
    dep = [d.lower() for d in (deprioritized or []) if d]

    def _keep(it):
        lbl = (it.get("_label") or "").lower()
        return not any(t in lbl for t in dep)
    if dep:
        ahead = [it for it in ahead if _keep(it)]
        past = [it for it in past if _keep(it)]
    if hour >= 20:
        return _evening_or_empty(user)
    when = ("This morning" if hour < 12 else
            "This afternoon" if hour < 17 else "This evening")
    # EXECUTIVE FILTER: surface only what genuinely deserves attention — a routine
    # supplement or a "log X" reminder is not worth the same airtime as a real
    # commitment, so it is not listed at all.
    ahead_worth = [it["_label"] for it in ahead if _agenda_worth_surfacing(it)]
    past_worth = [it["_label"] for it in past if _agenda_worth_surfacing(it)]
    parts = []
    if ahead_worth:
        line = f"{when} the thing to keep on your radar is {_fmt_titles(ahead_worth[:2])}"
        if recovery:
            line += " — keep it light, none of it has to be heavy"
        parts.append(line + ".")
    else:
        parts.append("Your rhythm's otherwise clear, so the rest of the day is yours to use.")
    # END WITH JUDGMENT, not optionality: only raise a leftover if it's worth doing, and
    # say so plainly — never "it's your call".
    if past_worth:
        parts.append("One thing still open from earlier is " + _fmt_titles(past_worth[:1])
                     + " — worth closing that out today so it doesn't roll forward.")
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


def _momentum_story(sig):
    """Narrate today's already-banked accomplishments — the brief presents the shared
    picture's `accomplishments` in its own context (ahead of plan → recovery latitude)."""
    acc = list(getattr(sig, "accomplishments", []) or [])
    if not acc:
        return ""
    joined = acc[0] if len(acc) == 1 else ", ".join(acc[:-1]) + " and " + acc[-1]
    return (f"First, you've already {joined} today — so you're ahead of where the day "
            "expected you to be. That gives you room to ease off later without losing "
            "any ground.")


def _foundation_story(sig):
    """The LISTENING/leading beat when the user has already laid the day's FOUNDATION
    (prayer, Bible reading). Acknowledged on its own terms — a strong start — never with
    the workout-recovery framing reserved for physical effort."""
    fnd = list(getattr(sig, "foundation", []) or [])
    if not fnd:
        return ""
    joined = fnd[0] if len(fnd) == 1 else ", ".join(fnd[:-1]) + " and " + fnd[-1]
    return (f"You've started the day the right way — you've already got your {joined} in, "
            "so the foundation of your day is set before anything else asks for you.")


def _mission_thesis(sig):
    """The day's THROUGH-LINE when the primary mission is advanced by daily health
    execution (parent→child). Frames nutrition/training/weight/sleep as the mission
    itself — one strategy — rather than a separate priority "to move forward". This is
    the dominant executive idea the rest of the read supports."""
    m = getattr(sig, "mission", None) or {}
    title = m.get("title")
    if not title or m.get("advanced_by") != "health":
        return ""
    return (f"And here's the through-line to hold onto: the everyday work you're already "
            f"putting in — your nutrition, your training, your weight and sleep — is "
            f"exactly what moves {title} forward. It isn't one more thing competing for "
            f"your time; it IS the mission, so you're advancing it today just by doing "
            "the day well.")


def _next_move_story(sig, user):
    """The single best NEXT move on a rested morning, using deterministic personal truth:
    get protein in early (concrete options), tied to the day's ACTUAL planned workout so
    the recommendation is prepared, not generic."""
    try:
        from apps.ai.chatgpt_cos.day_truth import todays_planned_workout, protein_options
        planned = todays_planned_workout(user)
        protein = protein_options(user)
    except Exception:
        logger.warning("executive_brief: next-move day-truth read failed", exc_info=True)
        planned, protein = None, ""
    # Lead with the ACTION (a concrete food), not the nutrient — a specific first move
    # is far easier to execute than "get protein".
    first = protein.split(",")[0].strip() if protein else "a protein-forward breakfast"
    if planned and planned.get("type") and not planned.get("completed"):
        when = f" at {planned['time']}" if planned.get("time") else ""
        return (f"Start with {first} this morning to get your protein in early — that "
                f"sets you up for your {planned['type']}{when} tonight.")
    return (f"Start with {first} this morning to get your protein in early — a strong "
            "base for the rest of the day.")


def _reconciliation_story(sig):
    """The LISTENING beat — narrate how the user's OWN report reconciled with the
    numbers. Fires only when the report meaningfully shaped the read, so Beth is
    visibly weighing lived experience against the objective signal, not ignoring it."""
    r = sig.reconciliation
    sh = getattr(sig, "sleep_hours", None)
    if isinstance(sh, (int, float)) and sh:
        _h = round(sh, 1)
        num = f"{int(_h) if _h == int(_h) else _h} hours"
    else:
        num = "a short night"
    if r == "positive_over_debt":
        # Hold BOTH truths — energy is fine AND the short night still matters — but say it
        # like a person, not with internal labels ("energy/recovery-management day").
        return (f"That's good to hear. {num[0].upper()}{num[1:]} is a little under what "
                "you're aiming for, but if you're feeling good, let's put that energy to "
                "work today. Just make an earlier night a priority so the short sleep "
                "doesn't start adding up.")
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
                "probably feels — your schedule isn't overloaded, just a handful of "
                "things on your list that aren't actually due today.")
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
        # Natural, confident framing — an em-dash apposition reads cleanly whether `risk`
        # is a short phrase ("sleep debt") or a full clause ("protein has been below
        # target the last few days"), and never over-dramatizes a routine shortfall.
        r = risk.rstrip(". ").strip()
        r = r[0].upper() + r[1:] if r else r
        out.append(f"One thing worth staying on top of today — {r}.")
    return " ".join(out)


def _close_out_story(user, sig):
    """The NIGHT posture (executive stance = close_out). The day is over: reflect on
    what it held, acknowledge it, and orient to rest — NEVER plan the day, name today's
    priorities, or tell the user not to fall behind (those are morning/midday framings
    that read as incoherent at bedtime). Health-critical, time-sensitive actions still
    lead — an overdue nightly dose matters before sleep — then the day closes."""
    story = []
    # A time-sensitive clinical action still comes first, framed for bedtime.
    for hc in (getattr(sig, "health_critical", None) or [])[:1]:
        story.append(f"Before you settle in — {hc['text']}. {hc['why'][:1].upper()}"
                     f"{hc['why'][1:]}, so take care of that first, then rest.")
    # Reflect what the day actually held (banked accomplishments), in a closing frame.
    acc = list(getattr(sig, "accomplishments", []) or [])
    if acc:
        joined = acc[0] if len(acc) == 1 else ", ".join(acc[:-1]) + " and " + acc[-1]
        story.append(f"Looking back on today, you {joined} — that's a solid day behind "
                     "you.")
    else:
        story.append("Looking back, today's basically done — and there's nothing left "
                     "that has to be forced tonight.")
    # Close it. Calm, short, no forward planning.
    story.append("Let the rest of the list wait for tomorrow; the best thing you can do "
                 "now is wind down and get some real rest.")
    out = " ".join(s for s in story if s).strip()
    return _scrub(out) or out


def _orientation_when(user):
    try:
        from apps.ai.chatgpt_cos.response_coherence import part_of_day
        return "this " + part_of_day(user)
    except Exception:
        return "today"


def _orientation_open(sig, subjective, low_energy):
    """One adaptive sentence that acknowledges what the user reported and orients them —
    ahead / steady / lighter — WITHOUT enumerating domains."""
    acc = list(getattr(sig, "accomplishments", []) or []) \
        + list(getattr(sig, "foundation", []) or [])
    if low_energy or subjective == "negative":
        return "Thanks for telling me — let's keep the load light and steady, then."
    if acc or subjective == "positive":
        return ("Sounds like you're off to a strong start — you're actually ahead of "
                "where I'd expect you to be right now.")
    return "You're in good shape heading into the day."


def _orientation_next(user, sig):
    """The SINGLE next thing worth keeping in front of the executive — the next
    meaningful scheduled item, else the one value-ranked priority. Never a list."""
    try:
        ahead, _past, _hour = _rhythm_split(user)
        worth = [it.get("_label") for it in ahead if _agenda_worth_surfacing(it)]
        worth = [w for w in worth if w]
        if worth:
            return f"The next thing I'd keep in front of you is {worth[0]}."
    except Exception:
        logger.warning("orientation: rhythm read failed", exc_info=True)
    pa = getattr(sig, "priority_action", None) or {}
    text = (pa.get("text") or "").strip()
    if text:
        return f"The one thing I'd keep in front of you is {text}."
    return ""


def compose_orientation(user, *, lead="", low_energy=False, subjective=None,
                        skip_continuity=False):
    """ORIENTATION, not a briefing — executive conversational discipline. A Chief of
    Staff acknowledges the executive, orients them to where the day stands, names the
    SINGLE next thing worth keeping in front of them, hands the conversation back with a
    question, and then STOPS. She does not enumerate every domain she knows about; the
    full executive read is reserved for an explicit request ('what do I need to know?').
    Health-critical, time-sensitive actions still lead. At night, defers to the close-out.

    DAY CONTINUITY: if Beth has already oriented Danny today and nothing MATERIAL has
    changed, she continues the day instead of re-orienting (a lighter 'welcome back' or,
    on a real change, a concise delta). `skip_continuity=True` is passed by the opening
    check-in→brief exchange so that first orientation is never collapsed mid-exchange."""
    sig = _safe_interpret(user, low_energy=low_energy, subjective=subjective)
    if not skip_continuity:
        try:
            from apps.ai.chatgpt_cos import day_continuity as dc
            decision = dc.assess(user, sig=sig)
            if decision.mode != "orient_full":
                text = dc.compose_continuation(user, sig, decision)
                dc.mark_established(user, decision.fingerprint, topics={"orientation"})
                return _scrub(text) or text
        except Exception:
            logger.warning("compose_orientation: continuity gate failed", exc_info=True)
    if (getattr(sig, "stance", None) or {}).get("stance") == "close_out":
        return compose_executive_brief(user, lead=lead, low_energy=low_energy,
                                       subjective=subjective)
    parts = []
    if lead:
        parts.append(lead.strip())
    for hc in (getattr(sig, "health_critical", None) or [])[:1]:
        parts.append(f"Before anything else — {hc['text']}. Take care of that first.")
    parts.append(_orientation_open(sig, subjective, low_energy))
    nxt = _orientation_next(user, sig)
    if nxt:
        parts.append(nxt)
    parts.append(f"What do you need from me {_orientation_when(user)}?")
    out = " ".join(p for p in parts if p).strip()
    # Record today's orientation so a later unprompted opener continues the day.
    try:
        from apps.ai.chatgpt_cos import day_continuity as dc
        dc.mark_established(user, dc.compute_fingerprint(sig), topics={"orientation"})
    except Exception:
        logger.warning("compose_orientation: mark_established failed", exc_info=True)
    return _scrub(out) or out


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
    # EXECUTIVE STANCE (situational grounding): at NIGHT the day is over — Beth closes
    # it out rather than planning it. Without this gate the composer welds a morning
    # execution thesis ("today is full but workable … I'll count today a win") to a
    # bedtime wind-down tail — the exact production incoherence. A `lead` (e.g. a repair
    # preamble) is preserved ahead of the close-out.
    if (getattr(sig, "stance", None) or {}).get("stance") == "close_out":
        close = _close_out_story(user, sig)
        return " ".join(s for s in (lead.strip() if lead else "", close) if s).strip()
    story = []
    if lead:
        story.append(lead.strip())
    # HEALTH-CRITICAL FIRST: a time-sensitive clinical action (e.g. overdue prescription
    # doses) outranks routine, convenience, momentum, and strategic items — Beth leads
    # with it and directs the action, never buries it in the agenda. Generic: whatever
    # interpret() flagged health_critical, not a medication special-case.
    for hc in (getattr(sig, "health_critical", None) or [])[:1]:
        story.append(f"Before anything else — {hc['text']}. That's the highest-priority "
                     f"action because {hc['why']}. Take care of that first.")
    # FOUNDATION FIRST: if the user has already laid the day's spiritual foundation
    # (prayer, Bible reading), lead the read by acknowledging it — a strong start that
    # frames everything after it. Never a workout-recovery framing (interpret separates
    # foundation from physical effort).
    foundation = _foundation_story(sig)
    if foundation:
        story.append(foundation)
    # MISSION THROUGH-LINE: the dominant executive idea. When the primary mission is
    # advanced by the user's daily health execution, name that ONE strategy up front so
    # the rest of the read (energy, the next move, what can wait) supports it — instead
    # of the mission reading as a separate priority to "move forward".
    mission_thesis = _mission_thesis(sig)
    if mission_thesis:
        story.append(mission_thesis)
    # The brief reflects what the user has already done today — straight from the one
    # executive picture (interpret merged it), no consumer-specific cache read.
    momentum = _momentum_story(sig)
    if momentum:
        story.append(momentum)
    recon = _reconciliation_story(sig)
    if recon:
        # The user gave us evidence — reconcile it FIRST, then the day.
        story.append(recon)
        if sig.reconciliation in ("positive_over_debt", "confirmed_good"):
            # A rested morning: the executive move is the concrete NEXT step (protein
            # early, tied to tonight's actual workout), grounded in deterministic truth.
            story.append(_next_move_story(sig, user))
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
        story.append("The rest of what's on your list can wait — none of it is due today.")
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
