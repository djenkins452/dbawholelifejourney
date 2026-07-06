# ==============================================================================
# File: apps/ai/chatgpt_cos/lanes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Conversation lane registry — framework-first routing (P6/P13).
# ==============================================================================
"""
Ordered conversation-lane registry for the ChatGPT CoS path.

    Foundational Facts -> Personal Reasoning -> Clarification -> General
    (the agentic tool loop remains the TERMINAL fallback in service.generate(), P8)

Each lane is a callable ``run(user, message) -> dict | None``. ``None`` means the
lane DECLINES and the router advances; the first non-None result wins. The two
existing lanes are WRAPPED, never modified (their decline/error semantics are
unchanged — they are called directly). The two new lanes (Clarification, General)
are deterministic-claim + self-contained-fallback, so they never raise.

Registry-based and template-based by design — NO special-case branching, NO
if/else tree. See docs/BETH_CONVERSATION_LANES.md for the lane contracts.
"""

import logging
import re

logger = logging.getLogger("apps.ai.chatgpt_cos")


# ---------------------------------------------------------------------------
# Lane 1 + 2 — existing lanes, WRAPPED (unchanged behavior; called directly so
# their own decline (None) and error semantics are byte-for-byte preserved).
# ---------------------------------------------------------------------------
def _foundational_lane(user, message, conversation=None):
    from apps.ai.chatgpt_cos.foundational_facts import answer_foundational_fact
    return answer_foundational_fact(user, message)


def _accomplishment_lane(user, message, conversation=None):
    """RECOGNIZE MISSION-SIGNIFICANT ACCOMPLISHMENTS: a first-person REPORT of what the
    user did ("I made up my workouts from Wednesday and Friday", "I got my workout in")
    is celebrated and RECORDED as today's evidence — so the rest of the executive
    reasoning reflects it. Runs before the retrieval lanes so a report isn't mistaken
    for a query. Declines questions."""
    from apps.ai.chatgpt_cos import accomplishment
    return accomplishment.answer(user, message, conversation)


def _sleep_history_lane(user, message, conversation=None):
    """HISTORICAL SLEEP RETRIEVAL: a sleep question about a specific/historical point
    in time ("what did I sleep on 7/1?", "the night before?", "last Monday?") is
    answered deterministically from the canonical record for THAT night — not "last
    night". Runs BEFORE the foundational fact lane (which always returns the current
    value). Declines for non-sleep questions and for "last night"/current, so existing
    behavior is untouched."""
    from apps.ai.chatgpt_cos import sleep_history
    return sleep_history.answer(user, message, conversation)


def _workout_history_lane(user, message, conversation=None):
    """WORKOUT RETRIEVAL: "did you see my workout?", "over 40,000 lbs total", "did I
    work out on 7/2?" — reads the canonical completed-workout truth (existence, total
    volume, duration) for the referenced day (default today). Declines otherwise."""
    from apps.ai.chatgpt_cos import workout_history
    return workout_history.answer(user, message, conversation)


def _weight_history_lane(user, message, conversation=None):
    """HISTORICAL WEIGHT RETRIEVAL: a weight question about a specific/historical date
    ("what was my weight on 7/1?") retrieves THAT day's canonical weight. Declines for
    non-weight questions and for current weight (no date), so existing paths are
    untouched. Runs BEFORE the foundational fact lane."""
    from apps.ai.chatgpt_cos import weight_history
    return weight_history.answer(user, message, conversation)


def _decision_support_lane(user, message, conversation=None):
    """Layer 2 DECISION SUPPORT: when the user is COMMUNICATING A DECISION (abandoning
    a plan, reprioritizing, accepting a tradeoff, giving up, or calling it a night)
    rather than asking for a fact, evaluate the tradeoff against the whole situation
    and help them decide — instead of retrieving facts (the production failure: "just
    need to take my nightly meds and I'm done" → a medication list). Declines for
    everything else, so fact/reasoning routing is unaffected. Runs BEFORE the
    foundational fact lane so a decision that merely NAMES a fact (meds, protein) is
    not mistaken for a request to retrieve it."""
    from apps.ai.chatgpt_cos import decision_support
    return decision_support.respond(user, message, conversation)


def _reconciliation_lane(user, message, conversation=None):
    """EXECUTIVE STATE RECONCILIATION: when the user supplies trustworthy evidence that
    an item Beth is treating as today's priority is NOT appropriate ("I already did
    that", "I did it yesterday", "I don't need one", "that's a morning-only activity",
    "that meeting was canceled", "I'm traveling / sick"), accept it, update the executive
    picture (defer the item out of today), and continue — instead of retrieving a fact
    (the production failure: 'I showered late yesterday … weighing in' → yesterday's
    weight → collapse). Runs BEFORE the retrieval lanes so the REASON isn't mistaken for
    a query. Declines everything else, so fact/reasoning routing is unaffected."""
    from apps.ai.chatgpt_cos import reconciliation
    return reconciliation.answer(user, message, conversation)


# Law 0 / Law 4 — DETERMINISTIC STATUS/COUNT questions belong to deterministic
# providers (workout/journal/appointments), NOT the reasoning planner. Conservative
# substrings: presence/status phrasings only, never the reasoning cues ("how is my
# fitness", "biggest health risk") which must still reach the planner.
_DETERMINISTIC_STATUS_PATTERNS = (
    # workout
    "did i work out", "did i workout", "have i worked out", "have i workout",
    "did i exercise", "did i train", "did i go to the gym", "workout today",
    "workout yesterday", "worked out today", "worked out yesterday",
    "do any workouts", "log a workout",
    # journal
    "did i journal", "have i journaled", "did i write a journal",
    "did i write in my journal", "journal entry today", "journaled today",
    "have i written a journal",
    # appointments / calendar
    "do i have any appointment", "any appointments", "appointments today",
    "appointment today", "on my calendar", "meetings today", "any meetings",
    "scheduled today", "what's on my calendar", "whats on my calendar",
    "do i have anything scheduled",
)


def _is_deterministic_status_question(message):
    """A yes/no or count question owned by a deterministic provider — answering it
    with the reasoning planner produces generic coaching for a plain fact (Law 0/4)."""
    t = (message or "").lower()
    return any(p in t for p in _DETERMINISTIC_STATUS_PATTERNS)


def _reasoning_lane(user, message, conversation=None):
    # Issue #1 reliability fix (isolated; not a reorder, not a health-intent
    # change): a clearly-GENERAL question carries no personal/health markers, so
    # the health planner would only decline it anyway. Skip the planner LLM for
    # those — it avoids a wasted call AND the shared circuit-breaker cascade that
    # was starving the General lane (the planner's rate-limit tripped the breaker
    # before the General call ran). Health/personal questions are unaffected
    # (_looks_general is False for anything with a pronoun or WLJ-domain word).
    if _looks_general(message):
        return None
    # CONTINUITY (Defect 2): a meta/follow-up about Beth's PRIOR answer ("why do you
    # say that?", "what do you mean?") must NOT enter the history-blind planner LLM —
    # which would re-answer from health truth and drop the conversational thread.
    # Decline so it falls through to the history-aware tool loop (loads conversation
    # history). `_looks_general` is False for these, so without this guard the planner
    # would steal them.
    if any(c in (message or "").lower() for c in _FOLLOWUP_CUES):
        return None
    # Law 0/4 (defect class): a deterministic STATUS/COUNT question ("did I work out
    # today?", "any appointments today?") belongs to a deterministic provider, not
    # the planner. DECLINE so it never becomes generic sleep coaching — it falls
    # through to deterministic retrieval instead.
    if _is_deterministic_status_question(message):
        logger.info("COS_REASONING_DECLINE_DETERMINISTIC user=%s",
                    getattr(user, "id", None))
        return None
    from apps.ai.chatgpt_cos.reasoning import answer_reasoning_question
    return answer_reasoning_question(user, message)


# ---------------------------------------------------------------------------
# Lane — Next Rhythm (P24): the SCHEDULED "what should I do next" answer, sourced
# from the canonical Rhythm API (the SAME engine the Dashboard renders), NOT from
# get_next_action (which is the URGENCY "focus right now" fact). Deterministic.
# ---------------------------------------------------------------------------
_NEXT_RHYTHM_SIGNALS = (
    "what should i do next", "whats next", "what is next", "what do i do next",
    "what should i work on next", "whats coming up next",
    "what's coming up next", "next on my schedule", "whats my next",
    "what's my next", "what comes next",
)


def _fmt_time(hhmm):
    try:
        from apps.core.cos_briefing.rhythm import _format_time_12h
        return _format_time_12h(hhmm)
    except Exception:
        return hhmm


# ---------------------------------------------------------------------------
# Lane — CoS Briefing (P26 DC#1): the holistic "tell me about my day / what needs
# my attention / wrap up my day" requests. Beth ALREADY owns this truth (rhythm +
# executive summary), so these MUST answer deterministically — never depend on the
# LLM, never fall to the tool loop. Sourced from build_daily_agenda (time-aware,
# always non-empty, no OpenAI).
# ---------------------------------------------------------------------------
_BRIEFING_SIGNALS = (
    "what needs my attention", "needs my attention", "what needs attention",
    "what should i know today", "what should i know", "what do i need to know",
    "plan the rest of my day", "plan the rest of the day", "plan my day",
    "plan the day", "help me plan", "wrap up my day", "wrap up the day",
    "wrap up my", "wind down", "end my day", "close out my day", "close out the day",
    "full check-in", "full check in", "give me a briefing", "brief me",
    "daily briefing", "what's on my plate", "whats on my plate",
    "where do things stand", "how's my day", "hows my day", "rest of my day",
    # Morning / greeting CoS entry points (P29 DC#2): a greeting is a request for
    # the deterministic morning briefing — it must never fall to the tool loop.
    "good morning", "good afternoon", "good evening", "morning beth",
    "start my day", "start the day", "begin my day", "kick off my day",
    "how is my day looking", "how's my day looking", "hows my day looking",
    "how is my day", "my day looking", "how does my day look", "what's my day like",
    # Time-constrained prioritization ("if I only have 30 minutes…") — the daily
    # agenda IS the prioritized-next-action answer (P29 DC#3 morning scenario).
    "if i only have", "i only have", "only have 30", "only have an hour",
    "30 minutes", "limited time", "short on time", "pressed for time",
    "if i have 30", "only got", "if i've got",
)

# A bare greeting (possibly addressed to the assistant) is a morning-briefing entry.
_GREETING_PREFIXES = ("good morning", "good afternoon", "good evening", "morning",
                      "gm beth", "hey beth", "hi beth", "hello beth")


def _is_greeting(norm):
    if norm in ("morning", "gm", "good morning", "good evening", "good afternoon"):
        return True
    return any(norm.startswith(p) for p in _GREETING_PREFIXES)


def _cos_briefing_lane(user, message, conversation=None):
    """Deterministic CoS briefing/check-in (P26 DC#1 + P29 DC#2). 'Good morning',
    'what needs my attention?', 'help me plan the rest of the day', 'wrap up my
    day', 'how is my day looking?' — answered from the deterministic daily agenda
    (rhythm + executive summary). ALWAYS non-empty, NO OpenAI: a CoS capability
    Beth already has the truth for must never depend on the LLM or fall to the
    tool loop."""
    norm = _normalize(message)
    # "How am I doing overall?" is a WHOLE-LIFE executive question → the executive
    # briefing, NOT a health report. But a domain-scoped overview ("how am I doing on
    # my weight / health goals") stays a domain question — yield it to reasoning.
    overview = any(s in norm for s in _OVERVIEW_SIGNALS)
    if overview and any(d in norm for d in _OVERVIEW_DOMAIN_QUALIFIERS):
        overview = False
    if not (overview or any(s in norm for s in _BRIEFING_SIGNALS) or _is_greeting(norm)):
        return None
    # A FULL-briefing request ("what should I know", "brief me", "how's my day",
    # "what do I need to know", "how am I doing overall") gets the EXECUTIVE BRIEF
    # COMPOSER (P32) — orientation first, agenda last. Narrow asks ("wrap up", "30
    # minutes") stay on the agenda.
    full_brief = overview or any(s in norm for s in _FULL_BRIEF_SIGNALS)
    try:
        if full_brief:
            from apps.ai.chatgpt_cos.executive_brief import compose_executive_brief
            answer = compose_executive_brief(user)
        else:
            from apps.core.cos_briefing.daily_agenda import build_daily_agenda
            answer = build_daily_agenda(user)
    except Exception:
        logger.warning("cos_briefing: compose/agenda failed", exc_info=True)
        answer = None
    if not answer:
        return None
    return {"answer": answer, "tools_called": [], "tools_advertised": [],
            "lane": "cos_briefing"}


# Full-briefing intents -> the Executive Brief Composer (orientation-first).
_FULL_BRIEF_SIGNALS = (
    "what should i know", "what do i need to know", "what do i need to know about today",
    "brief me", "give me a briefing", "daily briefing", "full check-in", "full check in",
    "how is my day looking", "how's my day looking", "hows my day looking",
    "how is my day", "my day looking", "where do things stand", "what needs my attention",
    "needs my attention", "good morning", "good afternoon", "good evening",
)

# Whole-life "how am I doing overall?" → the executive briefing (spans the whole
# person), never a health report. Domain-scoped variants are excluded below.
_OVERVIEW_SIGNALS = (
    "how am i doing overall", "how am i doing", "how am i doing today", "how am i overall",
    "overall how am i", "how are things going", "how's everything going",
    "how is everything going", "how's everything", "how is everything", "how's my life",
    "how is my life", "give me an overview", "overall picture", "the big picture",
    "executive summary", "executive briefing", "how am i tracking overall",
)
# A domain qualifier makes "how am I doing" a DOMAIN question (health/weight/goals/…),
# which stays with reasoning/foundational — the whole-life briefing does not claim it.
_OVERVIEW_DOMAIN_QUALIFIERS = (
    "health", "weight", "glucose", "blood", "sleep", "workout", "exercise", "protein",
    "calorie", "nutrition", "goal", "faith", "prayer", "bible", "finance", "money",
    "budget", "relationship", "task", "habit", "streak", "on my",
)


# A request grounded to a goal/mission is OWNED by Goals — these markers all resolve
# in the goal pre-router (deictic or milestone), so yielding here never drops the
# request (P29 DC#1: goal grounding beats the generic schedule rhythm).
_GOAL_GROUNDED_MARKERS = (
    "this goal", "that goal", "this mission", "that mission", "my mission",
    "the mission", "our mission", "milestone", "next phase", "next checkpoint",
)


def _next_rhythm_lane(user, message, conversation=None):
    norm = _normalize(message)
    if not any(s in norm for s in _NEXT_RHYTHM_SIGNALS):
        return None
    # A goal/mission-grounded question ("what comes next in this mission") is owned
    # by Goals, not the schedule rhythm — yield to the goal pre-router.
    if any(g in norm for g in _GOAL_GROUNDED_MARKERS):
        return None
    # "What should I do next" is a VALUE question — the most valuable next action, not the
    # next thing on the clock. Consume the one brain's ranking; fall back to rhythm only
    # if it's unavailable.
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        pa = interpret(user).priority_action
        if pa and (pa.get("text") or "").strip():
            ans = f"The most valuable thing to do next is {pa['text'].strip()}"
            why = (pa.get("why") or "").strip()
            if why:
                ans += f" — {why}"
            return {"answer": ans + ".", "tools_called": [], "tools_advertised": [],
                    "lane": "next_rhythm"}
    except Exception:
        logger.warning("next_rhythm: priority_action failed", exc_info=True)
    try:
        from apps.core.cos_briefing.rhythm_api import (
            get_current_rhythm_item, get_next_rhythm_item,
        )
        item = get_current_rhythm_item(user)
        upcoming = get_next_rhythm_item(user)
    except Exception:
        logger.warning("next_rhythm: rhythm api failed", exc_info=True)
        item, upcoming = None, None
    if not item:
        answer = ("You're all caught up on today's rhythm — nothing scheduled "
                  "is left.")
    else:
        title = (item.get("title") or "your next item").strip()
        t = item.get("scheduled_time")
        when = f" ({_fmt_time(t)})" if t else ""
        answer = f"Next up: {title}{when}."
        # No URLs are fabricated — rhythm items carry no destination, so we omit.
        if upcoming and (upcoming.get("title") or "").strip():
            answer += f" After that: {upcoming['title'].strip()}."
    return {"answer": answer, "tools_called": [], "tools_advertised": [],
            "lane": "next_rhythm"}


# "What is the single most important thing I should do right now?" — arguably the CoS's
# most important question. It must ALWAYS have a deterministic answer and NEVER fall to
# the LLM (whose failure produced "I couldn't pull that together").
_MOST_IMPORTANT_SIGNALS = (
    "most important thing", "single most important", "the one thing i should",
    "one thing i should do", "top priority", "my top priority", "highest priority",
    "what matters most right now", "whats the most important", "what's the most important",
    "what should i focus on right now", "what should i do right now",
    "most important thing right now", "the single biggest thing",
)


def _deterministic_priority_answer(user):
    """The single most important action by EXECUTIVE VALUE (interpret().priority_action) —
    what actually matters now, not what's next on the schedule. Degrades gracefully
    through the deterministic chain if the ranking is unavailable. Never returns None."""
    from apps.ai.chatgpt_cos.executive_reasoning import frame
    # 0) EXECUTIVE PRIORITY WEIGHTING — the value-ranked top action (the one brain).
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        pa = interpret(user).priority_action
        if pa and (pa.get("text") or "").strip():
            why = (pa.get("why") or "").strip()
            return frame(
                assessment=f"The single most important thing right now is {pa['text'].strip()}",
                reasoning=why or None,
                action="do this first — it's the highest-value move right now, and it "
                       "outranks what's merely next on the schedule")
    except Exception:
        logger.warning("priority_now: priority_action failed", exc_info=True)
    # 1) HEALTH-CRITICAL time-sensitive actions outrank everything.
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import _health_critical_actions
        hc = _health_critical_actions(user)
        if hc:
            return frame(
                assessment=f"The single most important thing right now is health-critical — {hc[0]['text']}",
                reasoning=hc[0]["why"],
                action="Do that first")
    except Exception:
        logger.warning("priority_now: health-critical failed", exc_info=True)
    # 2) The canonical deterministic execution decision (build_execution_state → selector).
    try:
        from apps.ai.cos_services.tool_registry import _h_decision
        d = _h_decision(user, mode="execution") or {}
        msg = (d.get("message") or d.get("primary_action") or "").strip()
        _nothing = ("nothing pending", "nothing scheduled", "all caught up",
                    "nothing to do", "nothing right now")
        if msg and not any(k in msg.lower() for k in _nothing):
            reason = (d.get("reason") or "").strip()
            action = msg[0].lower() + msg[1:] if msg[:1].isupper() and " " in msg else msg
            return frame(
                assessment=f"The highest-leverage move right now is to {action}",
                reasoning=reason if reason and reason.lower() not in msg.lower() else None,
                action="Start there before anything else")
    except Exception:
        logger.warning("priority_now: execution decision failed", exc_info=True)
    # 3) Rhythm — the current scheduled item.
    try:
        from apps.core.cos_briefing.rhythm_api import get_current_rhythm_item
        item = get_current_rhythm_item(user)
        if item and (item.get("title") or "").strip():
            return frame(
                assessment=f"Right now, the thing in front of you is {item['title'].strip()}",
                action="that's the best use of this moment")
    except Exception:
        logger.warning("priority_now: rhythm failed", exc_info=True)
    # 4) Canonical last resort — a deterministic, honest answer, never an error.
    return frame(
        assessment="Right now, the best move is the next concrete step on today's top commitment",
        action=("if nothing's scheduled, a quick reset — water, a short walk, or your most "
                "important task — starts the next block with momentum"))


def _most_important_lane(user, message, conversation=None):
    """Deterministic answer to 'the single most important thing right now'. Reuses the
    execution-decision selectors + the health-critical rule; degrades gracefully so it
    NEVER errors or reaches the tool loop."""
    if not any(s in _normalize(message) for s in _MOST_IMPORTANT_SIGNALS):
        return None
    return {"answer": _deterministic_priority_answer(user), "tools_called": [],
            "tools_advertised": [], "lane": "priority_now"}


# "What is the biggest risk today?" is an EXECUTIVE-RISK question — a whole-life risk
# synthesis, NOT a health intent or a goal update (the production category error was
# answering it with mission pace). Domain-scoped risk ("biggest HEALTH risk", "risk to
# my GOAL") stays with domain reasoning via the qualifier guard.
_EXEC_RISK_SIGNALS = (
    "biggest risk", "biggest risks", "greatest risk", "top risk", "main risk",
    "what risk", "what risks", "what's my risk", "whats my risk", "what is my risk",
    "most at risk", "any risks", "any risk", "risk today", "risks today",
    "risk i should", "should i be worried about", "what am i at risk", "what should i be concerned",
)


def _deterministic_risk_answer(user):
    """The biggest EVIDENCE-BACKED risk today, synthesized across deterministic sources —
    an executive risk assessment, NEVER a goal update. Impact order: health-critical →
    computed risk intelligence → execution/at-risk decision → overdue commitments. If
    nothing rises to a real risk, explain WHY and offer the biggest opportunity. Never
    returns None."""
    from apps.ai.chatgpt_cos.executive_reasoning import frame
    # 1) Health-critical, time-sensitive — the highest-impact risk.
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import _health_critical_actions
        hc = _health_critical_actions(user)
        if hc:
            return frame(
                assessment=f"Your single biggest exposure today is health-critical — {hc[0]['text']}",
                reasoning=hc[0]["why"],
                action="Handle that first, before anything else")
    except Exception:
        logger.warning("executive_risk: health-critical failed", exc_info=True)
    # 2) Computed risk intelligence (Insight warning/critical, risk predictions).
    intel = {}
    try:
        from apps.ai.cos_intelligence import active_intelligence
        intel = active_intelligence(user) or {}
        if intel.get("risks"):
            r = intel["risks"][0]
            conf = f" at {r['confidence']} confidence" if r.get("confidence") else ""
            return frame(
                assessment=f"The biggest risk on my radar today is {r['text']}",
                reasoning=(f"that's a flagged {r['basis']}{conf}" if r.get("basis")
                           else f"the data flags it{conf}"),
                action="I'd get ahead of it before it compounds")
    except Exception:
        logger.warning("executive_risk: intelligence failed", exc_info=True)
    # 3) The deterministic at-risk decision (overdue commitments / deadlines).
    try:
        from apps.ai.cos_services.tool_registry import _h_decision
        d = _h_decision(user, mode="risk") or {}
        msg = (d.get("message") or d.get("primary_action") or "").strip()
        _none = ("no significant risk", "nothing at risk", "no risks", "nothing pressing",
                 "no meaningful risk", "nothing overdue", "all caught up", "nothing right now")
        if msg and not any(k in msg.lower() for k in _none):
            reason = (d.get("reason") or "").strip()
            return frame(
                assessment=f"The thing most at risk today is {msg}",
                reasoning=reason if reason and reason.lower() not in msg.lower() else None,
                action="I'd shore that up today")
    except Exception:
        logger.warning("executive_risk: decision failed", exc_info=True)
    # 4) No meaningful risk → ASSESSMENT (no real risk) + REASONING (why) + the EXECUTIVE
    #    opportunity as the lever (not a positive insight). Never a goal update.
    reasoning = ("nothing's overdue, there are no health-critical flags, and no warning "
                 "signals in your data")
    opp = _executive_opportunity(user)
    action = (f"if you want a lever instead, the opportunity is {opp['text']} — {opp['action']}"
              if opp else "steady progress on what matters most is the best use of the day")
    return frame(assessment="Honestly, nothing rises to a real risk today",
                 reasoning=reasoning, action=action)


def _executive_risk_lane(user, message, conversation=None):
    """First-class EXECUTIVE RISK synthesis for 'what's my biggest risk today?'. Reuses
    health-critical + risk intelligence + the at-risk decision; degrades gracefully and
    NEVER substitutes a goal update. Yields domain-scoped risk questions to reasoning."""
    norm = _normalize(message)
    if not any(s in norm for s in _EXEC_RISK_SIGNALS):
        return None
    # "biggest HEALTH risk" / "risk to my GOAL" is a DOMAIN question — let reasoning own it.
    if any(d in norm for d in _OVERVIEW_DOMAIN_QUALIFIERS):
        return None
    return {"answer": _deterministic_risk_answer(user), "tools_called": [],
            "tools_advertised": [], "lane": "executive_risk"}


# "What opportunity am I missing today?" — an EXECUTIVE OPPORTUNITY (a high-leverage
# move to seize), computed by interpret() from executive state. NOT a positive insight
# (protein/weight/streak are WINS, not opportunities). Domain-scoped is yielded.
_EXEC_OPP_SIGNALS = (
    "opportunity", "opportunities", "what am i missing", "what i am missing",
    "what should i capitalize", "what should i capitalise", "where's the leverage",
    "wheres the leverage", "where is the leverage", "biggest opportunity",
    "any opportunit", "opportunity today", "what could i seize", "what should i seize",
)


def _executive_opportunity(user):
    """interpret()'s executive OPPORTUNITY assessment (dict or None). The one brain
    computes it from executive state; consumers only present it."""
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        return interpret(user).opportunity
    except Exception:
        logger.warning("executive_opportunity: interpret failed", exc_info=True)
        return None


def _deterministic_opportunity_answer(user):
    """Answer 'what opportunity am I missing?' from the executive opportunity assessment
    (ASSESSMENT → REASONING → ACTION), or say honestly there is no standout opening —
    never a positive-insight recommendation, never invented."""
    from apps.ai.chatgpt_cos.executive_reasoning import frame
    opp = _executive_opportunity(user)
    if opp:
        return frame(assessment=f"The opportunity to seize today is {opp['text']}",
                     reasoning=opp.get("basis"), action=opp.get("action"))
    return frame(
        assessment="There's no standout opportunity to exploit today",
        reasoning="nothing in your executive state points to disproportionate upside from a single move right now",
        action="today is better suited to disciplined execution than opportunism — steady progress on what matters most is the win")


def _executive_opportunity_lane(user, message, conversation=None):
    """First-class EXECUTIVE OPPORTUNITY for 'what opportunity am I missing?'. Consumes
    interpret().opportunity (leverage × capacity × timing × probability); NEVER a
    positive-insight recommendation. Yields domain-scoped opportunity questions."""
    norm = _normalize(message)
    if not any(s in norm for s in _EXEC_OPP_SIGNALS):
        return None
    if any(d in norm for d in _OVERVIEW_DOMAIN_QUALIFIERS):
        return None
    return {"answer": _deterministic_opportunity_answer(user), "tools_called": [],
            "tools_advertised": [], "lane": "executive_opportunity"}


# "What pattern do you see in my life that I probably don't recognize yet?" — an
# EXECUTIVE PATTERN (a non-obvious whole-life pattern), computed by interpret() from
# already-computed cross-domain sources. NEVER a raw single-domain dashboard trend
# (protein/weight/sleep). Domain-scoped ("pattern in my sleep") yields.
_EXEC_PATTERN_SIGNALS = (
    "pattern", "patterns", "don't recognize", "dont recognize", "probably don't",
    "probably dont", "not noticing", "not aware of", "hidden connection",
    "hidden pattern", "connect the dots", "blind spot", "what do you notice",
    "notice about my life", "recognize yet", "what am i not seeing",
)


def _executive_pattern(user):
    """interpret()'s executive PATTERN assessment. Returns either the executive pattern
    ``{text, basis, action}`` or an honest-empty marker ``{observation: {text, module}|None}``.
    The one brain computes it from whole-life state; consumers only present it."""
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        return interpret(user).pattern
    except Exception:
        logger.warning("executive_pattern: interpret failed", exc_info=True)
        return None


def _deterministic_pattern_answer(user):
    """Answer 'what pattern do you see that I don't recognize?' from the executive
    pattern (ASSESSMENT → REASONING → ACTION). If nothing cross-domain clears the bar,
    answer honestly (no pattern yet · why · strongest single-domain observation labeled
    NOT a pattern · what evidence would promote it). Never invents a connection, never
    dresses a single-domain trend up as a whole-life pattern."""
    from apps.ai.chatgpt_cos.executive_reasoning import frame
    pat = _executive_pattern(user)
    if pat and pat.get("action"):
        return frame(
            assessment=f"The pattern you probably haven't connected yet is that {pat['text']}",
            reasoning=pat.get("basis"), action=pat.get("action"))
    # Honest empty — the four required parts.
    obs = (pat or {}).get("observation")
    parts = ["No whole-life pattern clears the bar today — nothing across your domains "
             "yet has enough corroborating evidence to call an executive pattern."]
    if obs:
        parts.append(
            f"The strongest single signal right now is \"{obs['text']}\" — but that's a "
            f"{obs['module']} observation, not a pattern: it lives in one area and you "
            "already see it on your dashboard.")
        parts.append(
            "It would become an executive pattern only if it started moving together "
            "with another part of your life — tracking with your sleep, mood, momentum, "
            "or adherence over several weeks. Until that corroboration shows up, I won't "
            "dress a single trend up as a whole-life pattern.")
    else:
        parts.append(
            "As a few more weeks of cross-domain data accumulate, real whole-life "
            "patterns can surface; today there simply isn't enough evidence to claim one "
            "honestly.")
    return " ".join(parts)


def _executive_pattern_lane(user, message, conversation=None):
    """First-class EXECUTIVE PATTERN for 'what pattern do you see that I don't recognize?'.
    Consumes interpret().pattern (whole-life synthesis, executive-value ranked); NEVER a
    single-domain trend. Yields domain-scoped pattern questions to domain reasoning."""
    norm = _normalize(message)
    if not any(s in norm for s in _EXEC_PATTERN_SIGNALS):
        return None
    if any(d in norm for d in _OVERVIEW_DOMAIN_QUALIFIERS):
        return None
    return {"answer": _deterministic_pattern_answer(user), "tools_called": [],
            "tools_advertised": [], "lane": "executive_pattern"}


# Honest capability-gap for goals — until a canonical goal engine exists, Beth
# says so plainly, in natural CoS language (no developer words). She NEVER tells
# the user to visit a "Goals area" (GB-5).
_GOALS_GAP = ("I don't have enough active goal information to include goals in "
              "today's check-in yet, but I can still help with your schedule, "
              "health, and priorities.")


def _goal_title(t):
    """Extract a title string from a goal entry that may be a plain string OR a rich
    dict ({title, context, evidence, target_date, ...}) — production returns dicts.
    Never raises; returns '' for anything untitled."""
    if isinstance(t, dict):
        return (t.get("title") or "").strip()
    return "" if t is None else str(t).strip()


def _strategic_summary(user):
    """The Goals & Commitments view of the ONE executive understanding — the SAME
    strategic context interpret()/the Executive Briefing/Opportunity consume: mission +
    where it stands + active commitments + today's highest-leverage move. Returns a
    composed string, or None ONLY when there is genuinely no mission and no active goals.
    Consumes the existing brain; it is NOT a second strategic source — it reads
    interpret() (strategic_focus, highest_leverage), get_domain_state('purpose') (the
    mission/active-goal snapshot), and select_active_mission_goal() (the very pick
    build_goal_state itself uses, as the existence source of truth).

    ROBUSTNESS CONTRACT: active goals may be plain strings OR rich dicts; a formatting
    failure must NEVER surface as "no active goal information" while goals actually exist
    — it degrades to a simple truthful summary instead (origin: prod TypeError on
    dict-shaped active_titles falling back to _GOALS_GAP)."""
    sig = None
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        sig = interpret(user)
    except Exception:
        logger.warning("goals_checkin: interpret failed", exc_info=True)
    mission, active_titles, active_count = None, [], 0
    try:
        from apps.ai.cos_services import get_domain_state
        st = (get_domain_state(user, "purpose").get("state") or {})
        if isinstance(st.get("mission"), dict):
            mission = st["mission"]
        # active_titles may be plain strings OR rich dicts — normalize to title strings.
        active_titles = [tt for tt in (_goal_title(t) for t in (st.get("active_titles") or []))
                         if tt]
        active_count = int(st.get("active_goal_count") or 0)
    except Exception:
        logger.warning("goals_checkin: purpose state read failed", exc_info=True)
    # The canonical mission pick build_goal_state ITSELF builds from — so Beth NEVER
    # claims "no goals" while a mission exists, even if the snapshot is momentarily stale.
    mission_goal = None
    try:
        from apps.purpose.mission_selection import select_active_mission_goal
        mission_goal = select_active_mission_goal(user)
    except Exception:
        pass

    strategic = (getattr(sig, "strategic_focus", "") or "").strip() if sig else ""
    title = (_goal_title((mission or {}).get("title")) or strategic
             or (getattr(mission_goal, "title", "") if mission_goal is not None else "")).strip()
    # Honest-empty ONLY when there is genuinely nothing strategic anywhere in WLJ.
    if not title and active_count == 0 and not active_titles and mission_goal is None:
        return None

    # Compose the rich summary. If ANY formatting step fails, degrade to a simple but
    # TRUE summary — goals exist, so never fall through to the "no goal information" gap.
    try:
        focus = _goal_title((mission or {}).get("current_focus"))
        parts = []
        if title:
            stand = []
            dr = (mission or {}).get("days_remaining")
            if isinstance(dr, int) and dr >= 0:
                stand.append(f"{dr} days to target")
            tl = str((mission or {}).get("momentum_trend") or "").lower()
            if any(w in tl for w in ("declin", "down", "fall", "slow", "stall")):
                stand.append("momentum has dipped — worth a deliberate push")
            elif any(w in tl for w in ("ris", " up", "improv", "strong", "accel")):
                stand.append("momentum is strong")
            tail = (" — " + ", ".join(stand)) if stand else ""
            parts.append(f"Your mission is {title}{tail}.")
        others = [t for t in active_titles if t and t != title][:3]
        if others:
            parts.append("Other active commitments: " + ", ".join(others) + ".")
        elif active_count > 1 and title:
            parts.append(f"You have {active_count} active goals in all.")
        # Today's move — the CONCRETE next action. Prefer the mission's current milestone
        # (the real lever) over the generic "move it forward"; fall back to interpret()'s
        # highest_leverage, then to a plain nudge.
        lever = (getattr(sig, "highest_leverage", "") or "").strip() if sig else ""
        if focus and title:
            parts.append("The move that matters most today is advancing your current "
                         f"milestone: {focus}.")
        elif lever:
            parts.append(f"The highest-leverage move today is {lever}.")
        elif title:
            parts.append(f"Today, the most valuable thing you can do is move {title} forward.")
        composed = " ".join(p for p in parts if p)
        if composed:
            return composed
    except Exception:
        logger.warning("goals_checkin: summary composition failed", exc_info=True)
    # Degraded but TRUTHFUL fallback — goals DO exist here; never claim otherwise.
    if title:
        return f"You do have active goals. Your primary mission is {title}."
    return "You do have active goals and commitments — I can walk through them with you."


# Direct goal/commitment questions must consume the SAME strategic understanding as the
# check-in and the Executive Briefing — never a divergent LLM path that could contradict.
_GOALS_CHECKIN_SIGNALS = (
    "goals and commitments", "goals & commitments", "goals check-in", "goals checkin",
    "goal check-in", "how are my goals", "how do my goals", "how are my commitments",
    "how's my mission", "hows my mission", "how is my mission", "my goals looking",
    "goals looking", "my goals today", "my commitments today",
    "what commitment matters", "which commitment matters", "what strategic goal",
    "which strategic goal", "strategic goal should i", "goal should i move forward",
    "move forward on my goal", "check in on my goals", "check in on my mission",
)


def _goals_checkin_lane(user, message, conversation=None):
    """Goals & Commitments as a first-class deterministic surface — answers goal/mission/
    commitment questions from `_strategic_summary` (interpret()'s understanding), so it
    never contradicts the Executive Briefing/Opportunity. Honest-empty degrades to the
    goal-gap message; it never drifts to a generic lane."""
    norm = _normalize(message)
    if not any(s in norm for s in _GOALS_CHECKIN_SIGNALS):
        return None
    ans = _strategic_summary(user)
    return {"answer": ans or _GOALS_GAP, "tools_called": [],
            "tools_advertised": [], "lane": "goals_checkin"}


# ---------------------------------------------------------------------------
# Lane 3 — Clarification (DETERMINISTIC; never calls OpenAI). Registry of
# ambiguity types -> closed trigger set + a templated clarifying question.
# Add a new ambiguity type by appending a dict — no code changes elsewhere.
# ---------------------------------------------------------------------------
AMBIGUITY_TYPES = (
    {
        "type": "daily_checkin_candidate",
        # "check in" means (Danny): "look at my day and tell me what to do next
        # and what's coming up." Framed as a Daily Check-In clarification — the
        # full Daily Check-In Lane is intentionally NOT built in this phase, and
        # NO calendar/task/goal/health data is pulled here.
        "triggers": ("check in", "checkin", "daily check in", "morning check in",
                     "evening check in", "check in with me", "do a check in"),
        "response": (
            "I can help with a daily check-in. Do you want me to focus on:\n"
            "1. what's coming up today,\n"
            "2. what you should do next,\n"
            "3. health and energy,\n"
            "4. goals and commitments,\n"
            "5. or a full Whole Life check-in?"
        ),
        # Each option carries a deterministic RESOLVER (computed at reply time
        # from canonical engines — no OpenAI, no deflection). The static
        # 'resolution' is only a non-deflecting fallback if the resolver yields
        # nothing. CoS voice: Beth synthesizes; she never sends the user to a
        # dashboard/page/area or tells them to ask again.
        "options": [
            {"n": 1, "aliases": ("today", "coming up"), "resolver": "agenda",
             "resolution": "I'm having trouble assembling your day right now — try once more in a moment."},
            {"n": 2, "aliases": ("next", "do next"), "resolver": "next",
             "resolution": "I'm lining up your next step — give me a moment."},
            {"n": 3, "aliases": ("health", "energy"), "resolver": "health",
             "resolution": "I don't have enough recent health data to give you a full read yet."},
            {"n": 4, "aliases": ("goals", "commitments"), "resolver": "goals_gap",
             "resolution": _GOALS_GAP},
            {"n": 5, "aliases": ("whole life", "full", "everything"), "resolver": "full_checkin",
             "resolution": "I'm assembling your full check-in — give me a moment."},
        ],
    },
    {
        "type": "unspecified_help",
        "triggers": ("help me", "i need help", "can you help", "help"),
        "response": (
            "What would you like help with? For example, I can help with your "
            "health, goals, schedule, faith journey, projects, or answer "
            "general questions."
        ),
        "options": [
            {"n": 1, "aliases": ("health", "energy"), "resolver": "health",
             "resolution": "I don't have enough recent health data to give you a full read yet."},
            {"n": 2, "aliases": ("goals", "commitments"), "resolver": "goals_gap",
             "resolution": _GOALS_GAP},
            {"n": 3, "aliases": ("schedule", "calendar", "day"), "resolver": "next",
             "resolution": "I'm lining up your schedule — give me a moment."},
            {"n": 4, "aliases": ("faith", "prayer", "bible"), "resolver": None,
             "resolution": "I don't have your faith journey ready for today's check-in yet, but I can help with your schedule, health, and priorities."},
            {"n": 5, "aliases": ("project", "projects", "work"), "resolver": "next",
             "resolution": "I'm lining up your next step — give me a moment."},
            {"n": 6, "aliases": ("general", "question", "questions"), "resolver": None,
             "resolution": "Of course — ask your question and I'll answer it."},
        ],
    },
    {
        "type": "unspecified_review",
        "triggers": ("review this", "review that", "can you review", "review"),
        "response": (
            "What would you like me to review? A document, your goals, your "
            "schedule, or something else?"
        ),
        "options": [
            {"n": 1, "aliases": ("document", "doc", "file"), "resolver": None,
             "resolution": "Send the document over and I'll read it for you."},
            {"n": 2, "aliases": ("goal", "goals"), "resolver": "goals_gap",
             "resolution": _GOALS_GAP},
            {"n": 3, "aliases": ("schedule", "calendar", "day"), "resolver": "agenda",
             "resolution": "I'm assembling your day — give me a moment."},
            {"n": 4, "aliases": ("something", "other", "else"), "resolver": None,
             "resolution": "Tell me what you'd like me to review and I'll dig in."},
        ],
    },
)


def _normalize(message):
    norm = (message or "").strip().lower()
    norm = norm.replace("-", " ").replace("/", " ")
    norm = re.sub(r"[^\w\s]", "", norm)        # drop punctuation
    return re.sub(r"\s+", " ", norm).strip()


def clarify(message):
    """Deterministic clarification. Returns a clarification dict or None.

    A multi-word trigger matches as a substring only within a SHORT (<=4-word)
    request; a single-word trigger must match EXACTLY — so genuinely specific
    requests are never stolen into a clarification."""
    norm = _normalize(message)
    if not norm:
        return None
    words = norm.split()
    for spec in AMBIGUITY_TYPES:
        for trig in spec["triggers"]:
            multi = " " in trig
            if norm == trig or (multi and trig in norm and len(words) <= 4):
                return {
                    "answer": spec["response"],
                    "tools_called": [],
                    "tools_advertised": [],
                    "lane": "clarification",
                    "ambiguity_type": spec["type"],
                }
    return None


# --- Clarification STATE (deterministic; persisted in conversation.metadata;
# no migration, no OpenAI). The clarification lane records a pending question;
# the clarification_reply lane (front of the registry) resolves the user's reply
# deterministically and clears the state. Stale state self-clears when the next
# message is not a reply, so it never hijacks an unrelated request. ---
def _spec_for(ambiguity_type):
    return next((a for a in AMBIGUITY_TYPES if a["type"] == ambiguity_type), None)


def _set_pending(conversation, ambiguity_type):
    spec = _spec_for(ambiguity_type)
    if conversation is None or not spec:
        return
    try:
        md = dict(getattr(conversation, "metadata", None) or {})
        md["pending_clarification"] = {
            "ambiguity_type": ambiguity_type,
            "options": [
                {"n": o["n"], "aliases": list(o.get("aliases", ())),
                 "resolution": o["resolution"], "resolver": o.get("resolver")}
                for o in spec.get("options", [])
            ],
        }
        conversation.metadata = md
        conversation.save(update_fields=["metadata"])
    except Exception:
        logger.warning("clarification: set_pending failed", exc_info=True)


def _clear_pending(conversation):
    if conversation is None:
        return
    try:
        md = dict(getattr(conversation, "metadata", None) or {})
        if md.pop("pending_clarification", None) is not None:
            conversation.metadata = md
            conversation.save(update_fields=["metadata"])
    except Exception:
        logger.warning("clarification: clear_pending failed", exc_info=True)


_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
             "sixth": 6, "last": -1}


def parse_clarification_reply(message, options):
    """Deterministically map a SHORT reply to one pending option, or None.
    Handles: bare number / 'option N', ordinals, yes/no, and label aliases."""
    norm = _normalize(message)
    if not norm or not options:
        return None
    words = norm.split()
    n = len(options)
    if len(words) <= 3:
        m = re.search(r"\b([1-9][0-9]*)\b", norm)
        if m:
            i = int(m.group(1))
            if 1 <= i <= n:
                return options[i - 1]
    if len(words) <= 4:
        for w in words:
            if w in _ORDINALS:
                o = _ORDINALS[w]
                if o == -1:
                    return options[-1]
                if 1 <= o <= n:
                    return options[o - 1]
    if norm in ("yes", "y", "yeah", "yep", "sure"):
        return options[0]
    if norm in ("no", "n", "nope") and n >= 2:
        return options[1]
    if len(words) <= 4:
        for opt in options:
            for alias in opt.get("aliases", []):
                if alias and alias in norm:
                    return opt
    return None


# --- Deterministic clarification RESOLVERS (canonical engines only; NO OpenAI,
# NO new truth, NO deflection). Each selected option carries a 'resolver' tag. ---
def _health_overall_summary(user):
    """Deterministic overall-health summary via the EXISTING health reasoning
    engine's deterministic path (retrieve -> curate -> fallback). No LLM."""
    try:
        from apps.ai.chatgpt_cos.reasoning.plan import synthesize_health_plan
        from apps.ai.chatgpt_cos.reasoning.stages import (
            _health_progress_fallback, build_working_memory, retrieve_truth,
        )
        plan = synthesize_health_plan("overall_progress")
        wm = build_working_memory(plan, retrieve_truth(user, plan), user)
        return _health_progress_fallback(wm) or None
    except Exception:
        logger.warning("clarification: health summary failed", exc_info=True)
        return None


def _next_rhythm_summary(user):
    try:
        from apps.core.cos_briefing.rhythm_api import (
            get_current_rhythm_item, get_next_rhythm_item,
        )
        item = get_current_rhythm_item(user)
        if not item:
            return "You're all caught up on today's rhythm — nothing scheduled is left."
        t = item.get("scheduled_time")
        s = (f"Next up: {(item.get('title') or 'your next item').strip()}"
             f"{(' (' + _fmt_time(t) + ')') if t else ''}.")
        up = get_next_rhythm_item(user)
        if up and (up.get("title") or "").strip():
            s += f" After that: {up['title'].strip()}."
        return s
    except Exception:
        return None


def resolve_clarification_option(user, opt):
    """Compute a selected option's answer deterministically. Falls back to the
    option's non-deflecting static text if a resolver yields nothing."""
    resolver = (opt or {}).get("resolver")
    static = (opt or {}).get("resolution") or "Got it."
    try:
        if resolver == "agenda":
            from apps.core.cos_briefing.daily_agenda import build_daily_agenda
            return build_daily_agenda(user) or static
        if resolver == "next":
            return _next_rhythm_summary(user) or static
        if resolver == "health":
            return _health_overall_summary(user) or static
        if resolver == "goals_gap":
            # Consume the ONE executive understanding — honest-empty ONLY if truly no goals.
            return _strategic_summary(user) or _GOALS_GAP
        if resolver == "full_checkin":
            from apps.core.cos_briefing.daily_agenda import build_daily_agenda
            out = build_daily_agenda(user) or ""
            health = _health_overall_summary(user)
            if health:
                out += " On your health: " + health
            goals = _strategic_summary(user)
            out = ((out + " On your goals: " + goals) if goals
                   else (out + " " + _GOALS_GAP)).strip()
            return out or static
    except Exception:
        logger.warning("clarification: resolve failed resolver=%s", resolver,
                       exc_info=True)
    return static


def _clarification_reply_lane(user, message, conversation=None):
    if conversation is None:
        return None
    md = getattr(conversation, "metadata", None) or {}
    pending = md.get("pending_clarification")
    if not pending:
        return None
    opt = parse_clarification_reply(message, pending.get("options") or [])
    if opt is None:
        _clear_pending(conversation)        # not a reply -> clear stale, route fresh
        return None
    _clear_pending(conversation)
    answer = resolve_clarification_option(user, opt)    # deterministic synthesis
    logger.info("COS_CLARIFY_RESOLVED user=%s type=%s option=%s resolver=%s",
                getattr(user, "id", None), pending.get("ambiguity_type"),
                opt.get("n"), opt.get("resolver"))
    return {
        "answer": answer, "tools_called": [], "tools_advertised": [],
        "lane": "clarification_reply",
        "ambiguity_type": pending.get("ambiguity_type"),
        "resolved_option": opt.get("n"),
    }


def _clarification_lane(user, message, conversation=None):
    result = clarify(message)
    if result is not None:
        _set_pending(conversation, result.get("ambiguity_type"))
    return result


# ---------------------------------------------------------------------------
# Lane 4 — General Conversation (SANDBOXED: no personal/SAE data ever reaches
# the prompt). Conservative claim: only clearly NON-personal general-knowledge
# requests. Anything personal/WLJ-domain DECLINES (-> tool loop, which can fetch
# real data) so a personal question never gets a guessed/contaminated answer.
# ---------------------------------------------------------------------------
_PERSONAL_PRONOUNS = {"my", "i", "me", "mine", "myself", "our", "we", "us"}
_DOMAIN_WORDS = (
    "weight", "glucose", "blood sugar", "sleep", "calorie", "protein", "steps",
    "goal", "habit", "task", "project", "schedule", "calendar", "today",
    "tonight", "this week", "faith", "prayer", "bible reading plan", "journal",
    "mood", "energy", "workout", "fitness", "nutrition", "medication",
    "appointment", "my day",
)
_GENERAL_OPENERS = (
    "who ", "who was", "who is", "what is", "what was", "what are", "what's",
    "whats ", "explain", "define", "tell me about", "write out", "how does",
    "how do", "how did", "how come", "when did", "when was", "where is",
    "where was", "why is", "why do", "why does", "describe", "what does",
)


# Meta/follow-up cues that reference BETH'S PRIOR ANSWER, not the world. These are
# conversational, NOT general-knowledge — they must reach the history-aware tool loop
# (which loads conversation_history) so continuity survives a follow-up (Defect 3).
_FOLLOWUP_CUES = (
    "why do you say", "why would you say", "what makes you say", "why do you think that",
    "what do you mean", "how do you know", "how do you figure", "based on what",
    "says who", "explain that", "what are you basing", "why is that",
)


def _looks_general(message):
    norm = (message or "").strip().lower()
    if not norm:
        return False
    if any(c in norm for c in _FOLLOWUP_CUES):  # follow-up about the prior turn
        return False
    tokens = set(re.findall(r"[a-z']+", norm))
    if tokens & _PERSONAL_PRONOUNS:           # personal -> not general
        return False
    # EXTERNAL/definitional framing ("what is a healthy weight generally?") is
    # general even though it contains a domain word — claim it for the general lane
    # so it never retrieves personal data (P26 DC#3).
    from apps.ai.chatgpt_cos.foundational_facts import external_general_signal
    if external_general_signal(norm):
        return True
    if any(d in norm for d in _DOMAIN_WORDS):  # WLJ-domain -> not general
        return False
    return any(norm.startswith(o) or (" " + o) in norm for o in _GENERAL_OPENERS)


def _cos_name(user):
    try:
        prefs = getattr(user, "preferences", None)
        if prefs is not None and hasattr(prefs, "get_cos_name"):
            return prefs.get_cos_name() or "your Chief of Staff"
    except Exception:
        pass
    return "your Chief of Staff"


def general_answer(user, message):
    """Sandboxed general-knowledge answer, or None if not clearly general.
    The prompt carries NO personal data. Always returns an answer once it claims
    (deterministic fallback on LLM failure — P5)."""
    if not _looks_general(message):
        return None
    return _general_llm_answer(user, message)


def general_continuation(user, message, prior=None):
    """Continue an ACTIVE general-knowledge thread (Conversation Continuity).

    Same sandbox as ``general_answer`` (NO personal data) but does NOT re-run the
    stateless ``_looks_general`` gate — the ACTIVE SUBJECT, not per-message
    keyword matching, keeps the thread alive — and carries the recent general
    exchange so follow-ups ('who wrote them?', 'how come…') resolve in context.
    This is what lets a general conversation CONTINUE across differently-phrased
    follow-ups instead of being re-classified from scratch every turn."""
    return _general_llm_answer(user, message, prior=prior, lane="general_continuity")


def _general_llm_answer(user, message, prior=None, lane="general_conversation"):
    """Shared sandboxed general-knowledge LLM call. NO personal data in the
    prompt. Always returns an answer dict (graceful outage fallback — P5)."""
    system = (
        f"You are {_cos_name(user)}, the user's Chief of Staff — but you can also "
        "answer general questions like a knowledgeable, warm assistant. Answer "
        "the user's general-knowledge question accurately and concisely. This is "
        "a GENERAL question: do NOT reference, assume, or invent any of the "
        "user's personal data, health, goals, faith, or schedule. If you are not "
        "sure of a fact, say so briefly rather than guessing."
    )
    if prior:
        # Continuity context — the immediately-prior general answer so the
        # follow-up resolves naturally. Still strictly general (no personal data).
        system += (
            "\n\nThis is a CONTINUING general-knowledge conversation. For context, "
            "the most recent thing you told the user was:\n\"" +
            (prior or "").strip()[:1200] +
            "\"\nAnswer their follow-up as a natural continuation of that thread, "
            "staying strictly on general knowledge; do NOT pivot to the user's "
            "personal data, health, goals, faith practice, or schedule."
        )
    # --- Issue #1 instrumentation (root-cause trace; no behavior change) ---
    from django.core.cache import cache
    breaker_before = bool(cache.get("openai_rate_limited"))
    answer = None
    call_outcome = "none"
    try:
        from django.conf import settings
        from apps.ai.services import ai_service
        raw = ai_service._call_api(
            system, message, max_tokens=500, temperature=0.5,
            endpoint="cos_chat", user=user,
            # Use the SAME model as the rest of the CoS chat (the tool loop passes
            # COS_MODEL). Defaulting to self.model (OPENAI_MODEL) made the general
            # lane diverge: tool-loop questions ("Give me John 3:16") used COS_MODEL
            # and worked, while general-lane questions ("What is Metformin used
            # for?") used a DIFFERENT model and failed when the two settings differ.
            model=getattr(settings, "COS_MODEL", None),
            # Foreground, user-waiting, no deterministic fallback — a transient
            # breaker from another call must not blank this out (Failure #4).
            bypass_breaker=True,
        )
        if raw is None:
            call_outcome = "none"
        elif not raw.strip():
            call_outcome = "empty"
        else:
            call_outcome = "content"
        answer = raw
    except Exception:
        call_outcome = "raised"
        logger.warning("COS_GENERAL_LANE_LLM_FAILED user=%s",
                       getattr(user, "id", None), exc_info=True)
        answer = None
    answer = (answer or "").strip()
    fallback_used = not answer
    if not answer:
        # OpenAI is unavailable. General knowledge needs the model and WLJ has no
        # offline knowledge source by design, so we degrade GRACEFULLY: acknowledge
        # the outage honestly and invite a retry. Do NOT pivot to personal domains
        # (goals/health/schedule/faith) — that is inappropriate for an EXTERNAL
        # knowledge question and leaks personal-domain concepts into a general answer.
        answer = (
            "I normally answer general questions like that directly, but my external "
            "knowledge service is temporarily unavailable right now. Please try again "
            "in a minute.")
    logger.info(
        "BETH_GENERAL_CALL user=%s lane=%s breaker_before=%s call_outcome=%s "
        "fallback_used=%s qlen=%d",
        getattr(user, "id", None), lane, breaker_before, call_outcome,
        fallback_used, len(message or ""),
    )
    return {
        "answer": answer,
        "tools_called": [],
        "tools_advertised": [],
        "lane": lane,
    }


def _general_lane(user, message, conversation=None):
    return general_answer(user, message)


# ---------------------------------------------------------------------------
# The ordered registry + router. The tool loop is NOT in the registry — it is
# the terminal fallback in service.generate() when route_message() returns None.
#
#   clarification_reply  — resolves a pending clarification (front)
#   foundational_facts   — deterministic personal scalar facts
#   clarification        — deterministic ambiguity detection (BEFORE the planner,
#                          so ambiguous prompts like "check in" are clarified
#                          rather than over-claimed by the reasoning planner)
#   next_rhythm          — canonical SCHEDULED "what's next" (P24, deterministic)
#   personal_reasoning   — the LLM-planner health reasoning lane
#   general_conversation — sandboxed general knowledge (kept AFTER reasoning;
#                          general-before-personal is NOT yet approved — pending
#                          Issue #1 production telemetry)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Executive Conversation Planning (P31 Phase 1). A deterministic planner decides
# WHAT CONVERSATION to have before the fact-routing lanes run: a GREETING opens
# with a light CHECK-IN (agenda HELD), a CRITIQUE triggers a REPAIR, and a
# CHECK-IN response hands off to the deterministic BRIEFING. All NO-OpenAI.
# ---------------------------------------------------------------------------
_NEGATIVE_FEELING = ("tired", "exhausted", "rough", "not great", "not good", "bad",
                     "stressed", "anxious", "overwhelmed", "drained", "low", "awful",
                     "struggling", "heavy", "off", "tough", "hard")
_BRIEFING_CUES = ("coming up", "next up", "priority", "agenda", "scheduled", "begin",
                  "your day", "start with", "first up", "on your plate")


def _greeting_word(user, message=None):
    """Time-aware greeting (P33.1): driven by the user's CURRENT clock, not by the
    word they typed — so 'good morning' at 12:05 PM is answered 'Good afternoon'."""
    try:
        from apps.core.utils import get_user_now
        hour = get_user_now(user).hour
    except Exception:
        return "Hello"
    if 4 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    return "Good evening"


def _overnight_facts(user):
    """1–2 concrete overnight facts + a strong-signal flag + the GROUNDED sleep
    fact (for temporal-trust follow-ups). Cache-first (SAE), best-effort.

    Temporal Grounding: the sleep statement is built by `sleep_last_night_grounded`
    which NEVER mislabels a 7-night average as 'last night' and attaches the window
    / record date / freshness, so 'which last night? is that stale?' can be
    verified deterministically instead of failing."""
    facts, strong, sleep_fact = [], False, None
    try:
        from apps.ai.cos_services import get_domain_state
        from apps.ai.chatgpt_cos.temporal_grounding import sleep_last_night_grounded
        env = get_domain_state(user, "health")
        st = (env.get("state") if isinstance(env, dict) else None) or {}
        sentence, is_strong, sleep_fact = sleep_last_night_grounded(user, st)
        if sentence:
            facts.append(sentence)
            strong = strong or is_strong
    except Exception:
        logger.warning("checkin: overnight facts failed", exc_info=True)
    return facts[:2], strong, sleep_fact


def _morning_checkin(user, message):
    greeting = _greeting_word(user, message)
    facts, strong, sleep_fact = _overnight_facts(user)
    parts = [f"{greeting}, Danny."]
    if facts:
        parts.append(" ".join(facts))
    if strong:
        parts.append("Before we dive into today — how are you feeling this morning, "
                     "and is there anything you want me to know first?")
    else:
        parts.append("Before we get into the day — how are you feeling, and is there "
                     "anything you want to tell me first?")
    result = {"answer": " ".join(parts), "tools_called": [], "tools_advertised": [],
              "lane": "conversation_checkin"}
    # Ground the time-relative sleep statement as the ACTIVE SUBJECT so a
    # freshness/temporal challenge ('what date are you calling last night? is
    # that stale?') routes into deterministic trust-verification, not a failure.
    if sleep_fact and sleep_fact.get("value") is not None:
        result["fact_key"] = "sleep_last_night"
        result["fact"] = sleep_fact
        result["active_subject"] = {"fact_key": "sleep_last_night", "fact": sleep_fact}
    return result


def _post_checkin_brief(user, message, feeling):
    f = (feeling or "").lower()
    # Listening & Evidence Reconciliation: the user's OWN report is evidence the brief
    # must weigh against the objective sleep read — not ignore.
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import classify_subjective_energy
        subjective = classify_subjective_energy(feeling)
    except Exception:
        subjective = None
    # Persist the reported state into the ONE executive picture so it evolves today's
    # understanding for every consumer — not just this brief.
    if subjective:
        try:
            from apps.ai.chatgpt_cos.executive_evidence import record_subjective
            record_subjective(user, subjective)
        except Exception:
            pass
    heavy = subjective == "negative" or any(w in f for w in _NEGATIVE_FEELING)
    lead = ("Thanks for telling me. " if heavy else "Got it. ")
    try:
        from apps.ai.chatgpt_cos.executive_brief import compose_executive_brief
        answer = compose_executive_brief(user, lead=lead, low_energy=heavy,
                                         subjective=subjective)
    except Exception:
        logger.warning("post_checkin_brief: compose failed", exc_info=True)
        answer = lead + "Here's your day at a glance."
    return {"answer": answer, "tools_called": [], "tools_advertised": [],
            "lane": "conversation_brief"}


def _repair_response(user, message, prior_answer):
    """Self-aware repair (P32): OWN the miss, name what went wrong (do NOT ask Danny
    to diagnose it), then deliver a proper EXECUTIVE briefing — not an unrelated fact."""
    prior = (prior_answer or "").lower()
    # If Danny reported a mission-significant accomplishment today, the miss was almost
    # certainly EXECUTIVE — I treated the headline as a passing fact. Name THAT precisely
    # (a Chief of Staff demonstrates understanding, not generic remorse).
    try:
        from apps.ai.chatgpt_cos.executive_evidence import today as _rep_ev
        _accs = _rep_ev(user).get("accomplishments") or []
    except Exception:
        _accs = []
    if _accs:
        _joined = (_accs[0] if len(_accs) == 1
                   else ", ".join(_accs[:-1]) + " and " + _accs[-1])
        parts = [
            "You're right, and I can name exactly what I missed.",
            f"You told me you'd {_joined} today — that erased today's workout debt and was "
            "the single biggest change to your executive picture. I treated it as a passing "
            "fact and led with sleep and your evening plan instead of making it the headline "
            "and building my recommendation around it.",
            "Here's the read the way it should have come:",
        ]
    else:
        parts = ["You're right — let me own that."]
        # Self-diagnose. If the prior answer led with the agenda/tasks, name THAT (the
        # specific failure mode); otherwise acknowledge the missing executive read.
        if any(c in prior for c in _BRIEFING_CUES) or _looks_agenda_led(prior):
            parts.append("I led with the agenda instead of orienting you to the day. "
                         "That's on me — the calendar is supporting detail, not the headline.")
        else:
            parts.append("I gave you the facts without the executive read you needed.")
        parts.append("Here's the briefing the way it should have come:")
    lead = " ".join(parts)
    try:
        from apps.ai.chatgpt_cos.executive_brief import compose_executive_brief
        answer = compose_executive_brief(user, lead=lead)
    except Exception:
        logger.warning("repair: compose failed", exc_info=True)
        answer = lead
    return {"answer": answer, "tools_called": [], "tools_advertised": [],
            "lane": "conversation_repair"}


def _looks_agenda_led(prior):
    """The prior answer opened with the agenda (tasks/times) rather than orientation."""
    head = (prior or "")[:160]
    return any(c in head for c in ("coming up", "next up", "your agenda",
                                   "first up", "at ", "scheduled", "drink", "shower"))


def _conversation_planner_lane(user, message, conversation=None):
    """P31: run the deterministic conversation planner. Intervenes only for repair /
    morning check-in / post-check-in briefing; otherwise declines (the planner has
    already persisted the next conversation state)."""
    if conversation is None:
        return None
    try:
        from apps.ai.chatgpt_cos import conversation_planner as cp
        p = cp.plan(user, conversation, message)
    except Exception:
        logger.warning("conversation_planner_lane failed", exc_info=True)
        return None
    handler = p.get("handler")
    if handler == "repair":
        return _repair_response(user, message, p.get("prior_answer"))
    if handler == "checkin_open":
        return _morning_checkin(user, message)
    if handler == "brief_after_checkin":
        return _post_checkin_brief(user, message, p.get("feeling"))
    return None


# Follow-up cue sets — all answered DETERMINISTICALLY from the active topic's stored
# fact (no LLM, no topic switch). Order matters: most specific first.
_TIME_FOLLOWUP_CUES = ("at what time", "what time", "when was that", "when was it",
                       "when did that", "and when", "what time was")
_TIME_FOLLOWUP_EXACT = {"when", "when?", "and when?", "when was this?", "what time?"}
_CURRENT_CUES = ("is that current", "is that recent", "is it current", "is that up to date",
                 "how recent", "when was it recorded", "when was that recorded", "is it stale")
# Positive-framed ("is that good/safe?") vs negative-framed ("should I be concerned?")
# — same fact, opposite polarity in the answer.
_CONCERN_POSITIVE = ("is that good", "is that ok", "is that okay", "is that safe",
                     "is that normal", "is that fine", "is that healthy")
_CONCERN_NEGATIVE = ("should i be concerned", "should i worry", "is that bad",
                     "anything to worry", "is that dangerous")
_CONCERN_CUES = _CONCERN_POSITIVE + _CONCERN_NEGATIVE
# "what did I eat?" / "what were they?" → read the supporting MEALS off the active topic.
_SUPPORTING_MEAL_CUES = ("what did i eat", "what were they", "what were those",
                         "which meals", "what did that include", "what made that up",
                         "what made up the", "what was that from", "what's that from")
# Topic-aware meta (TF4) + conversational patterns (TF5) — resolve against the active object.
_IS_AVERAGE_CUES = ("is that an average", "is that the average", "is that a single",
                    "single reading", "is that just one", "is that one reading",
                    "is that averaged", "average or a single")
_WHAT_CHANGED_CUES = ("what changed", "what caused that", "what caused it",
                      "why the change", "what made it change", "why did it change")
_MORE_CUES = ("anything else", "go deeper", "tell me more", "what else", "more detail",
              "any more", "is there more")
# "compared to yesterday / my average?" → comparison from supporting facts.
_COMPARISON_PRIOR_CUES = ("compared to yesterday", "vs yesterday", "versus yesterday",
                          "than yesterday", "more or less than yesterday")
_COMPARISON_AVG_CUES = ("compared to last week", "compared to usual", "vs my average",
                        "versus my average", "than usual", "than my average",
                        "what's the trend", "whats the trend", "compared to normal")
_MEANING_CUES = ("why is that important", "why is that reading important", "why does that matter",
                 "what does that mean", "what does that mean for me", "why is that significant",
                 "why is this important", "what does this mean")
# Bare one-word "why" follow-ups — the most natural form, which the verbose _FOLLOWUP_CUES
# missed (production blocker: "How am I doing?" → "Why?" → Assistant unavailable). EXACT
# match only, so a real reasoning question ("why did I gain weight?") is never swallowed.
_WHY_EXACT = {"why", "why though", "but why", "and why", "how come", "how so",
              "why not", "why that", "why is that", "and why is that"}


def _why_explainer_lane(user, message, conversation=None):
    """DETERMINISTIC active-topic follow-ups: a question about Beth's prior answer is
    answered from the STORED fact — timestamp, concern level, health meaning, currency,
    or basis — all from the SAME fact object. No LLM reconstruction, no topic switch.
    Front of the registry so it claims the follow-up before any lane re-answers."""
    if conversation is None:
        return None
    norm = (message or "").strip().lower()
    norm_bare = norm.rstrip("?.! ")        # "Why?" → "why"
    from apps.ai.chatgpt_cos.conversation_memory import (
        get_last_answer, compose_why, compose_when, compose_concern,
        compose_meaning, compose_is_current, compose_supporting, compose_comparison,
        compose_is_average, compose_what_changed, compose_more,
    )
    # Pick the handler by cue (specific → general).
    handler, kw = None, {}
    if any(c in norm for c in _IS_AVERAGE_CUES):
        handler = compose_is_average
    elif any(c in norm for c in _WHAT_CHANGED_CUES):
        handler = compose_what_changed
    elif any(c in norm for c in _MORE_CUES):
        handler = compose_more
    elif any(c in norm for c in _COMPARISON_PRIOR_CUES):
        handler, kw = compose_comparison, {"kind": "prior"}
    elif any(c in norm for c in _COMPARISON_AVG_CUES):
        handler, kw = compose_comparison, {"kind": "average"}
    elif any(c in norm for c in _SUPPORTING_MEAL_CUES):
        # "what did I eat?" / "what were they?" — answer from the supporting facts on
        # the active topic (the meals behind a calorie total). Declines if none, so a
        # standalone meal question still routes normally.
        handler, kw = compose_supporting, {"label": "meals"}
    elif norm in _TIME_FOLLOWUP_EXACT or any(c in norm for c in _TIME_FOLLOWUP_CUES):
        handler = compose_when
    elif any(c in norm for c in _CURRENT_CUES):
        handler = compose_is_current
    elif any(c in norm for c in _MEANING_CUES):
        handler = compose_meaning
    elif any(c in norm for c in _CONCERN_CUES):
        handler = compose_concern
        kw = {"positive_frame": any(c in norm for c in _CONCERN_POSITIVE)}
    elif norm_bare in _WHY_EXACT or any(c in norm for c in _FOLLOWUP_CUES):
        handler = compose_why
    else:
        return None
    last = get_last_answer(conversation)
    if not last:
        return None
    # A follow-up to a GENERAL / EXTERNAL answer belongs to general_continuity —
    # never explain general knowledge as "your tracked data". Yield so a
    # referential follow-up ("why is that term…?") continues the general thread.
    if last.get("lane") in ("general_conversation", "general_continuity"):
        return None
    answer = handler(last, user, **kw)
    if not answer:
        return None
    # Advance the standing conversation goal when the follow-up implies one.
    goal = None
    if handler is compose_comparison:
        goal = "trend" if kw.get("kind") == "average" else "compare"
    elif handler is compose_what_changed:
        goal = "investigate"
    return {"answer": answer, "lane": "why_explainer",
            "fast_path": "conversation_memory", "goal": goal}


def _temporal_lane(user, message, conversation=None):
    """Temporal Grounding + VERIFY MODE (the Conversation Operating Model's trust
    dimension).

    (1) Current date/time/timezone — always answerable deterministically.
    (2) When the user CHALLENGES the validity/freshness/source of Beth's prior
    statement, the conversation has become a TRUST INVESTIGATION — its purpose
    changed from getting advice to establishing trust. Beth CHANGES OPERATING
    MODE: she stops answering/coaching and enters deterministic VERIFY mode over
    her LAST assertion (prove the record, source, timestamp, freshness; acknowledge
    uncertainty honestly; never restate the claim as settled). Runs FIRST so a
    trust challenge is addressed before any lane can re-answer or coach. Declines
    when there's no clock question and no prior assertion to verify."""
    from apps.ai.chatgpt_cos import temporal_grounding as tg
    res = tg.answer_datetime(user, message)
    if res is not None:
        return res
    if conversation is None:
        return None
    from apps.ai.chatgpt_cos.conversation_memory import get_last_answer
    last = get_last_answer(conversation)

    def _keep_subject(result):
        # Keep the grounded fact as the active subject so a MULTI-TURN thread
        # (clarify → clarify, or clarify → challenge) keeps its anchor.
        fact = (last or {}).get("fact") or \
            ((last or {}).get("active_subject") or {}).get("fact")
        if fact and isinstance(result, dict):
            result["fact_key"] = (last or {}).get("fact_key") or fact.get("key")
            result["fact"] = fact
            result["active_subject"] = {"fact_key": result["fact_key"], "fact": fact}
        return result

    # A genuine TRUST CHALLENGE (correctness/freshness/provenance) → VERIFY mode.
    # Checked FIRST — a challenge takes precedence over a look-alike clarification.
    if tg.is_trust_challenge(message):
        res = tg.verify_last_claim(user, last, message)
        if res is not None:
            return _keep_subject(res)
    # A CLARIFICATION question about the prior statement → just ANSWER it directly.
    # A world-class CoS answers "which date?" without escalating into verification.
    if tg.is_clarification_question(message):
        res = tg.answer_clarification(user, last, message)
        if res is not None:
            return _keep_subject(res)
    return None


def _referential_lane(user, message, conversation=None):
    """REFERENTIAL follow-ups: a bare reference ('what about yesterday?', 'compared to
    today', 'how about last week?') resolves against the active topic — same subject,
    new timeframe or comparison — without the user restating it. Runs after the
    why_explainer (which handles same-fact follow-ups) and before the reasoning/generic
    lanes, so a reference never drifts into unrelated coaching."""
    if conversation is None:
        return None
    from apps.ai.chatgpt_cos.conversation_memory import get_last_answer
    from apps.ai.chatgpt_cos.referential import resolve_referential
    last = get_last_answer(conversation)
    if not last:
        return None
    return resolve_referential(user, message, last)


# ---------------------------------------------------------------------------
# Lane — General Conversation Continuity. Conversation Continuity is a
# first-class CoS capability: an ACTIVE conversation continues until the user
# EXPLICITLY changes subject. Beth tracks the Active Subject for PERSONAL threads
# (why_explainer / referential), but a general/EXTERNAL thread ("Who was
# Jezebel?" → "How come the Bible has Matthew, Mark, Luke, John?") had no
# continuity: the stateless `_looks_general` re-classified each turn, so a
# differently-phrased follow-up fell through to the personal-coaching lanes and
# Beth abandoned the active discussion for unrelated sleep guidance.
#
# This lane closes that class. When the last answer came from the general lane
# (the Active Subject is an external thread) and the new message CONTINUES the
# inquiry — a question / follow-up, not an explicit personal request — it stays
# in the general lane. It is placed BEFORE the personal lanes (next_rhythm /
# cos_briefing / personal_reasoning) precisely so unsolicited personal coaching
# can never interrupt an active unrelated conversation.
# ---------------------------------------------------------------------------

# The ONLY things that end an active general thread: the user EXPLICITLY turns to
# their own data/life. A personal-agenda cue, or a personal pronoun tied to a WLJ
# domain word ("how's MY sleep", "what's on MY calendar").
_PERSONAL_AGENDA_CUES = (
    "what's next", "whats next", "what is next", "what should i do",
    "what do i do next", "check in", "how am i doing", "how am i tracking",
    "plan my day", "plan the day", "my agenda", "what's on my", "whats on my",
    "brief me", "how's my day", "hows my day", "wrap up my", "what needs my",
    "where do i stand", "how am i", "should i", "do i have", "what do i have",
)

# Multi-word follow-up cues that clearly reference the prior general answer.
_CONTINUATION_CUES = (
    "tell me more", "go on", "and then", "what about", "what else", "how so",
    "for example", "such as", "like what", "go deeper", "keep going",
    "expand on that", "say more", "anything else", "more on that", "who else",
)
# Bare follow-ups (EXACT match) — elliptical asks that only make sense as a
# continuation of the prior answer.
_BARE_FOLLOWUPS = frozenset((
    "why", "why though", "but why", "and why", "how come", "how so", "why not",
    "why that", "why is that", "so", "then what", "more", "go on", "continue",
    "elaborate", "keep going", "and then", "go deeper", "and", "more please",
))
# Pronouns that BACK-REFERENCE the prior answer — the mark of an elliptical
# follow-up. NOT the personal possessives (my/our); those signal a personal pivot.
_REFERENTIAL_TOKENS = frozenset((
    "that", "those", "them", "it", "this", "these", "they", "he", "she", "him",
    "his", "her", "its", "their", "there",
))
_ELLIPTICAL_STARTS = ("and ", "but ", "or ", "also ", "what about", "how about")

# WLJ-owned PERSONAL-TRUTH markers — a question about the user's own data/life
# (health/diabetes/milestone/…) that must reach deterministic providers, NEVER be
# captured as general/external.
_PERSONAL_TRUTH_MARKERS = (
    "how is my", "how's my", "hows my", "how are my", "how am i", "is my ",
    "what is my", "what's my", "whats my", "my health", "my diabetes",
    "my next milestone", "my milestone", "my mission", "my progress", "my a1c",
    "my blood sugar", "my medication", "am i on track", "how's my",
)


def _is_explicit_personal_request(message):
    """True when the message turns to the user's OWN data/life — the only thing
    that ends an active general/external thread. Recognises WLJ-owned personal
    truth (health/diabetes/milestone/…) so it can never be captured as general."""
    norm = (message or "").strip().lower()
    if not norm:
        return True
    tokens = set(re.findall(r"[a-z']+", norm))
    if (tokens & _PERSONAL_PRONOUNS) and any(d in norm for d in _DOMAIN_WORDS):
        return True
    if any(c in norm for c in _PERSONAL_AGENDA_CUES):
        return True
    return any(c in norm for c in _PERSONAL_TRUTH_MARKERS)


def _is_continuation(message):
    """True ONLY for a genuine ELLIPTICAL / REFERENTIAL follow-up to the prior
    general answer: a bare follow-up cue ('why?'), a conjunctive elliptical ('and
    the Old Testament?'), or a SHORT question that back-references the prior
    subject ('why is that term…?'). A SELF-CONTAINED new question (general,
    boundary, or personal) is NOT a continuation — continuity is never a
    catch-all — so it routes normally."""
    n = (message or "").strip().lower()
    if not n:
        return False
    if n.rstrip("?.! ") in _BARE_FOLLOWUPS:
        return True
    if any(c in n for c in _CONTINUATION_CUES):
        return True
    if len(n.split()) <= 10 and any(n.startswith(s) for s in _ELLIPTICAL_STARTS):
        return True
    tokens = set(re.findall(r"[a-z']+", n))
    return bool(tokens & _REFERENTIAL_TOKENS) and len(n.split()) <= 14


def _general_continuity_lane(user, message, conversation=None):
    """Continue an ACTIVE general/external thread so a personal-coaching lane can
    never hijack it. Claims ONLY when: (1) the last answer came from the general
    lane, (2) the message is NOT an explicit personal request, and (3) it is a
    continuation (a question / follow-up). Otherwise declines so the normal lanes
    run — a genuine personal pivot is always honoured."""
    if conversation is None:
        return None
    from apps.ai.chatgpt_cos.conversation_memory import get_last_answer
    last = get_last_answer(conversation)
    if not last or last.get("lane") not in (
            "general_conversation", "general_continuity"):
        return None  # no active external thread → nothing to continue
    if _is_explicit_personal_request(message):
        return None  # user explicitly changed subject to something personal
    if not _is_continuation(message):
        return None  # a personal statement/command, not a continued inquiry
    return general_continuation(user, message, prior=last.get("answer") or "")


LANE_REGISTRY = (
    # Temporal Grounding runs FIRST: current date/time is always answerable, and
    # a freshness/temporal challenge to a grounded time-relative statement enters
    # deterministic trust-verification before any other lane (or coaching) can
    # claim it. It declines for everything else, so normal routing is unaffected.
    ("temporal", _temporal_lane),
    ("why_explainer", _why_explainer_lane),
    ("referential", _referential_lane),
    ("clarification_reply", _clarification_reply_lane),
    ("conversation_planner", _conversation_planner_lane),
    # Layer 2 DECISION SUPPORT runs BEFORE fact retrieval: a voiced decision that
    # merely names a fact ("just need to take my nightly meds and I'm done") is a
    # tradeoff to evaluate, not a fact to look up. Declines for real questions.
    ("decision_support", _decision_support_lane),
    # EXECUTIVE STATE RECONCILIATION: trustworthy evidence that an item isn't today's
    # priority ("I did it yesterday", "that's a morning activity", "meeting canceled")
    # updates the picture — BEFORE retrieval lanes so the REASON isn't read as a query.
    ("reconciliation", _reconciliation_lane),
    # RECOGNIZE ACCOMPLISHMENTS: a report of what was done today ("I made up my
    # workouts") is celebrated + recorded as today's evidence — before the retrieval
    # lanes so it isn't mistaken for a query.
    ("accomplishment", _accomplishment_lane),
    # HISTORICAL SLEEP RETRIEVAL runs BEFORE the foundational fact lane so a sleep
    # question about a specific night ("what did I sleep on 7/1?") retrieves THAT
    # night instead of always returning "last night". Declines otherwise.
    ("sleep_history", _sleep_history_lane),
    # HISTORICAL WEIGHT RETRIEVAL — same, for "what was my weight on 7/1?".
    ("weight_history", _weight_history_lane),
    # WORKOUT RETRIEVAL — "did you see my workout?", "over 40,000 lbs total".
    ("workout_history", _workout_history_lane),
    ("foundational_facts", _foundational_lane),
    ("clarification", _clarification_lane),
    # Continue an active EXTERNAL/general thread BEFORE any personal-coaching lane
    # can claim the follow-up (Conversation Continuity).
    ("general_continuity", _general_continuity_lane),
    # Goals & Commitments — a deterministic consumer of interpret()'s strategic
    # understanding, so goal questions never contradict the Executive Briefing.
    ("goals_checkin", _goals_checkin_lane),
    ("next_rhythm", _next_rhythm_lane),
    # "The single most important thing right now" — always deterministic, never the LLM.
    ("priority_now", _most_important_lane),
    # "What's my biggest risk today?" — whole-life executive risk synthesis, never a
    # health intent or a goal update.
    ("executive_risk", _executive_risk_lane),
    # "What opportunity am I missing?" — executive opportunity (leverage×capacity×timing),
    # never a positive insight.
    ("executive_opportunity", _executive_opportunity_lane),
    # "What pattern do you see that I don't recognize?" — whole-life executive pattern,
    # never a single-domain dashboard trend.
    ("executive_pattern", _executive_pattern_lane),
    ("cos_briefing", _cos_briefing_lane),
    ("personal_reasoning", _reasoning_lane),
    ("general_conversation", _general_lane),
)


def route_message(user, message, conversation=None):
    """Try each lane in order; return the first non-None result (tagged with its
    lane), or None if every lane declines (caller runs the tool-loop fallback)."""
    uid = getattr(user, "id", None)
    tried = []                      # Issue #1 trace: which lanes were consulted
    for name, fn in LANE_REGISTRY:
        tried.append(name)
        result = fn(user, message, conversation)
        if result is not None:
            if isinstance(result, dict):
                result.setdefault("lane", name)
                # RESPONSE COHERENCE: re-ground the FINISHED response's sense of time
                # before it is recorded or presented, so no composed answer ever mixes
                # two parts of day (e.g. an evening greeting + a "this morning" check-in).
                # One choke point → every composed response reads as one coherent person.
                if result.get("answer"):
                    try:
                        from apps.ai.chatgpt_cos.response_coherence import harmonize
                        result["answer"] = harmonize(result["answer"], user)
                    except Exception:
                        logger.warning("route: coherence pass failed", exc_info=True)
                # Record the structured memory of this turn so the NEXT follow-up is
                # explained deterministically (conversation memory).
                try:
                    from apps.ai.chatgpt_cos.conversation_memory import record_last_answer
                    record_last_answer(conversation, name, result)
                except Exception:
                    pass
            # 'planner_invoked' = the reasoning lane (which runs the planner) was
            # consulted before the winner. Pair with the adjacent COS_REASONING_PLAN
            # line for the planner RESULT, and BETH_GENERAL_CALL for breaker/outcome.
            logger.info("COS_LANE_TRACE user=%s tried=%s winner=%s planner_invoked=%s",
                        uid, ",".join(tried), name, "personal_reasoning" in tried)
            return result
    logger.info("COS_LANE_TRACE user=%s tried=%s winner=tool_loop_fallback "
                "planner_invoked=%s", uid, ",".join(tried),
                "personal_reasoning" in tried)
    return None
