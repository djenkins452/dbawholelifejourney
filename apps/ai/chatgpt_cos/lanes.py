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


def _next_rhythm_lane(user, message, conversation=None):
    norm = _normalize(message)
    if not any(s in norm for s in _NEXT_RHYTHM_SIGNALS):
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


def _looks_general(message):
    norm = (message or "").strip().lower()
    if not norm:
        return False
    tokens = set(re.findall(r"[a-z']+", norm))
    if tokens & _PERSONAL_PRONOUNS:           # personal -> not general
        return False
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
        from apps.ai.services import ai_service
        raw = ai_service._call_api(
            system, message, max_tokens=500, temperature=0.5,
            endpoint="cos_chat", user=user,
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
        answer = ("I can usually help with that, but I couldn't reach it just "
                  "now. Please try again.")
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
LANE_REGISTRY = (
    ("clarification_reply", _clarification_reply_lane),
    ("foundational_facts", _foundational_lane),
    ("clarification", _clarification_lane),
    ("next_rhythm", _next_rhythm_lane),
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
