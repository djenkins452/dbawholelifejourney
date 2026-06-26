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
def _foundational_lane(user, message):
    from apps.ai.chatgpt_cos.foundational_facts import answer_foundational_fact
    return answer_foundational_fact(user, message)


def _reasoning_lane(user, message):
    from apps.ai.chatgpt_cos.reasoning import answer_reasoning_question
    return answer_reasoning_question(user, message)


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
    },
    {
        "type": "unspecified_help",
        "triggers": ("help me", "i need help", "can you help", "help"),
        "response": (
            "What would you like help with? For example, I can help with your "
            "health, goals, schedule, faith journey, projects, or answer "
            "general questions."
        ),
    },
    {
        "type": "unspecified_review",
        "triggers": ("review this", "review that", "can you review", "review"),
        "response": (
            "What would you like me to review? A document, your goals, your "
            "schedule, or something else?"
        ),
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


def _clarification_lane(user, message):
    return clarify(message)


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


def _general_lane(user, message):
    return general_answer(user, message)


# ---------------------------------------------------------------------------
# The ordered registry + router. The tool loop is NOT in the registry — it is
# the terminal fallback in service.generate() when route_message() returns None.
# ---------------------------------------------------------------------------
LANE_REGISTRY = (
    ("foundational_facts", _foundational_lane),
    ("personal_reasoning", _reasoning_lane),
    ("clarification", _clarification_lane),
    ("general_conversation", _general_lane),
)


def route_message(user, message):
    """Try each lane in order; return the first non-None result (tagged with its
    lane), or None if every lane declines (caller runs the tool-loop fallback)."""
    uid = getattr(user, "id", None)
    tried = []                      # Issue #1 trace: which lanes were consulted
    for name, fn in LANE_REGISTRY:
        tried.append(name)
        result = fn(user, message)
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
