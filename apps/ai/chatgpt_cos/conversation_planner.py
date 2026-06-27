# ==============================================================================
# File: apps/ai/chatgpt_cos/conversation_planner.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Executive Conversation Planning (P31 Phase 1) — a THIN, DETERMINISTIC
#   strategy + state layer that decides WHAT CONVERSATION to have before Beth
#   answers: (a) a GREETING opens with a light CHECK-IN first (agenda held until
#   Danny responds), (b) a CRITIQUE of Beth's prior answer triggers a REPAIR, and
#   (c) a CHECK-IN response hands off to the BRIEFING. No LLM director — the plan is
#   computed from owned truth. Conversation STATE persists in
#   AssistantConversation.metadata (the proven `pending_clarification` pattern — no
#   migration). Design: docs/BETH_CONVERSATION_PLANNING_DESIGN.md.
# ==============================================================================
import logging
import re

logger = logging.getLogger(__name__)

STATE_KEY = "conversation_state"

# A critique/correction of Beth's PREVIOUS answer (not a fresh question).
_CRITIQUE_CUES = (
    "does that sound right", "doesn't sound right", "dont sound right",
    "does that seem right", "doesn't seem right", "are you sure", "you sure about",
    "is that right", "is that correct", "is that accurate", "that's not right",
    "thats not right", "that isn't right", "that isnt right", "that's wrong",
    "thats wrong", "not first class", "wasn't first class", "wasnt first class",
    "that was not", "that wasn't", "that wasnt", "double check", "sanity check",
    "i don't think that", "i dont think that", "that can't be right",
    "that cant be right", "doesn't add up", "doesnt add up", "are you certain",
    "that doesn't look right", "that doesnt look right", "rethink that",
    "look again", "that's off", "thats off", "seems wrong", "not quite right",
    "really?", "seriously?", "for real?", "you certain", "that right?",
)

_GREETING_CUES = (
    "good morning", "good afternoon", "good evening", "morning beth", "evening beth",
    "afternoon beth", "hey beth", "hi beth", "hello beth", "good morning beth",
)
_GREETING_EXACT = {"morning", "good morning", "good evening", "good afternoon",
                   "hey", "hi", "hello", "gm", "hiya", "howdy"}


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def is_greeting(message):
    n = _norm(message)
    if not n:
        return False
    if n in _GREETING_EXACT:
        return True
    return any(n.startswith(c) or (" " + c) in n for c in _GREETING_CUES)


def is_critique(message):
    n = _norm(message)
    return any(c in n for c in _CRITIQUE_CUES)


def _looks_like_question(message):
    n = _norm(message)
    if "?" in (message or ""):
        return True
    return any(n.startswith(w) for w in (
        "what", "how", "when", "why", "where", "who", "which", "can you",
        "could you", "should i", "do i", "is ", "are ", "will ", "tell me",
        "show me", "give me", "remind me", "list "))


# --- Conversation STATE (deterministic; persisted in conversation.metadata) -----
def read_state(conversation):
    try:
        md = getattr(conversation, "metadata", None) or {}
        st = md.get(STATE_KEY)
        return st if isinstance(st, dict) else {}
    except Exception:
        return {}


def write_state(conversation, **fields):
    if conversation is None:
        return
    try:
        md = dict(getattr(conversation, "metadata", None) or {})
        st = dict(md.get(STATE_KEY) or {})
        st.update(fields)
        st["turn"] = int(st.get("turn", 0)) + 1
        md[STATE_KEY] = st
        conversation.metadata = md
        conversation.save(update_fields=["metadata"])
    except Exception:
        logger.warning("conversation_planner: write_state failed", exc_info=True)


def last_assistant_text(conversation):
    try:
        from apps.ai.models import AssistantMessage
        m = (AssistantMessage.objects.filter(conversation=conversation)
             .exclude(role="user").order_by("-created_at").first())
        return m.content if m else None
    except Exception:
        return None


def plan(user, conversation, message):
    """Return a deterministic conversation plan and PERSIST the next state.

    handler ∈ {repair, checkin_open, brief_after_checkin, route}. Only the first
    three intervene; `route` falls through to the normal lane pipeline UNCHANGED."""
    if conversation is None:
        return {"handler": "route"}
    state = read_state(conversation)
    cur = state.get("state")
    prior = last_assistant_text(conversation)
    has_prior = bool(prior) or bool(state.get("last_beth_act"))

    # 1) REPAIR — a critique of Beth's PREVIOUS answer.
    if is_critique(message) and has_prior:
        write_state(conversation, state="repair", objective="repair",
                    last_beth_act="repaired")
        return {"handler": "repair", "prior_answer": prior}

    # 2) GREETING — open with a light CHECK-IN first; hold the agenda.
    if is_greeting(message):
        write_state(conversation, state="check_in", objective="emotional_checkin",
                    last_beth_act="checked_in")
        return {"handler": "checkin_open"}

    # 3) Post-check-in response — brief now (unless Danny asked a fresh question).
    if cur == "check_in" and not is_critique(message):
        if _looks_like_question(message):
            write_state(conversation, state="engaged", last_beth_act="answered")
            return {"handler": "route"}
        write_state(conversation, state="briefing", objective="executive_briefing",
                    last_beth_act="briefed", feeling=_norm(message)[:120])
        return {"handler": "brief_after_checkin", "feeling": _norm(message)}

    # 4) Default — no conversational intervention.
    return {"handler": "route"}
