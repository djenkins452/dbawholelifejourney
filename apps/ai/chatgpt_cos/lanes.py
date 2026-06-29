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
    if not (any(s in norm for s in _BRIEFING_SIGNALS) or _is_greeting(norm)):
        return None
    # A FULL-briefing request ("what should I know", "brief me", "how's my day",
    # "what do I need to know") gets the EXECUTIVE BRIEF COMPOSER (P32) — orientation
    # first, agenda last. Narrow asks ("wrap up", "30 minutes") stay on the agenda.
    full_brief = any(s in norm for s in _FULL_BRIEF_SIGNALS)
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


# Honest capability-gap for goals — until a canonical goal engine exists, Beth
# says so plainly, in natural CoS language (no developer words). She NEVER tells
# the user to visit a "Goals area" (GB-5).
_GOALS_GAP = ("I don't have enough active goal information to include goals in "
              "today's check-in yet, but I can still help with your schedule, "
              "health, and priorities.")


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
            return _GOALS_GAP
        if resolver == "full_checkin":
            from apps.core.cos_briefing.daily_agenda import build_daily_agenda
            out = build_daily_agenda(user) or ""
            health = _health_overall_summary(user)
            if health:
                out += " On your health: " + health
            out = (out + " " + _GOALS_GAP).strip()
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
    "how do", "how did", "when did", "when was", "where is", "where was",
    "why is", "why do", "why does", "describe", "what does",
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
    system = (
        f"You are {_cos_name(user)}, the user's Chief of Staff — but you can also "
        "answer general questions like a knowledgeable, warm assistant. Answer "
        "the user's general-knowledge question accurately and concisely. This is "
        "a GENERAL question: do NOT reference, assume, or invent any of the "
        "user's personal data, health, goals, faith, or schedule. If you are not "
        "sure of a fact, say so briefly rather than guessing."
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
        "BETH_GENERAL_CALL user=%s breaker_before=%s call_outcome=%s "
        "fallback_used=%s qlen=%d",
        getattr(user, "id", None), breaker_before, call_outcome,
        fallback_used, len(message or ""),
    )
    return {
        "answer": answer,
        "tools_called": [],
        "tools_advertised": [],
        "lane": "general_conversation",
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
    """1–2 concrete overnight/yesterday facts + a strong-signal flag. Cache-first
    (SAE), best-effort: any missing fact is simply omitted."""
    facts, strong = [], False
    try:
        from apps.ai.cos_services import get_domain_state
        env = get_domain_state(user, "health")
        st = (env.get("state") if isinstance(env, dict) else None) or {}
        h = st.get("sleep_last_night_hours") or st.get("sleep_avg_hours_7d")
        if isinstance(h, (int, float)) and h > 0:
            if h < 6.5:
                facts.append(f"You got about {h:g} hours of sleep last night — a bit short.")
                strong = True
            else:
                facts.append(f"You got about {h:g} hours of sleep last night.")
    except Exception:
        logger.warning("checkin: overnight facts failed", exc_info=True)
    return facts[:2], strong


def _morning_checkin(user, message):
    greeting = _greeting_word(user, message)
    facts, strong = _overnight_facts(user)
    parts = [f"{greeting}, Danny."]
    if facts:
        parts.append(" ".join(facts))
    if strong:
        parts.append("Before we dive into today — how are you feeling this morning, "
                     "and is there anything you want me to know first?")
    else:
        parts.append("Before we get into the day — how are you feeling, and is there "
                     "anything you want to tell me first?")
    return {"answer": " ".join(parts), "tools_called": [], "tools_advertised": [],
            "lane": "conversation_checkin"}


def _post_checkin_brief(user, message, feeling):
    f = (feeling or "").lower()
    heavy = any(w in f for w in _NEGATIVE_FEELING)
    lead = ("Thanks for telling me. " if heavy else "Got it. ")
    try:
        from apps.ai.chatgpt_cos.executive_brief import compose_executive_brief
        answer = compose_executive_brief(user, lead=lead, low_energy=heavy)
    except Exception:
        logger.warning("post_checkin_brief: compose failed", exc_info=True)
        answer = lead + "Here's your day at a glance."
    return {"answer": answer, "tools_called": [], "tools_advertised": [],
            "lane": "conversation_brief"}


def _repair_response(user, message, prior_answer):
    """Self-aware repair (P32): OWN the miss, name what went wrong (do NOT ask Danny
    to diagnose it), then deliver a proper EXECUTIVE briefing — not an unrelated fact."""
    prior = (prior_answer or "").lower()
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
_MEANING_CUES = ("why is that important", "why is that reading important", "why does that matter",
                 "what does that mean", "what does that mean for me", "why is that significant",
                 "why is this important", "what does this mean")


def _why_explainer_lane(user, message, conversation=None):
    """DETERMINISTIC active-topic follow-ups: a question about Beth's prior answer is
    answered from the STORED fact — timestamp, concern level, health meaning, currency,
    or basis — all from the SAME fact object. No LLM reconstruction, no topic switch.
    Front of the registry so it claims the follow-up before any lane re-answers."""
    if conversation is None:
        return None
    norm = (message or "").strip().lower()
    from apps.ai.chatgpt_cos.conversation_memory import (
        get_last_answer, compose_why, compose_when, compose_concern,
        compose_meaning, compose_is_current, compose_supporting,
    )
    # Pick the handler by cue (specific → general).
    handler, kw = None, {}
    if any(c in norm for c in _SUPPORTING_MEAL_CUES):
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
    elif any(c in norm for c in _FOLLOWUP_CUES):
        handler = compose_why
    else:
        return None
    last = get_last_answer(conversation)
    if not last:
        return None
    answer = handler(last, user, **kw)
    if not answer:
        return None
    return {"answer": answer, "lane": "why_explainer",
            "fast_path": "conversation_memory"}


LANE_REGISTRY = (
    ("why_explainer", _why_explainer_lane),
    ("clarification_reply", _clarification_reply_lane),
    ("conversation_planner", _conversation_planner_lane),
    ("foundational_facts", _foundational_lane),
    ("clarification", _clarification_lane),
    ("next_rhythm", _next_rhythm_lane),
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
