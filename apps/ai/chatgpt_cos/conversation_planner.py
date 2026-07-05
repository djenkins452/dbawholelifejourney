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
    # "You missed what I told you" — a challenge that Beth failed to reflect reported
    # evidence. Routes to the self-aware repair so she names the executive mistake.
    "did you not read", "did you even read", "you didnt read", "you did not read",
    "did you read my", "read my response", "read what i", "you missed", "you ignored",
    "you forgot what i", "i just told you", "did you miss",
)

_GREETING_CUES = (
    "good morning", "good afternoon", "good evening", "morning beth", "evening beth",
    "afternoon beth", "hey beth", "hi beth", "hello beth", "good morning beth",
)
_GREETING_EXACT = {"morning", "good morning", "good evening", "good afternoon",
                   "hey", "hi", "hello", "gm", "hiya", "howdy"}

# A check-in ("how are you feeling?") expects a short AFFECTIVE self-report. These
# recognise a plausible feeling reply so that ANYTHING ELSE (a question, an
# unrelated new subject, a general-knowledge query) is treated as a PIVOT that
# abandons the check-in — an interrupted or failed check-in must never trap the
# next conversation in personal coaching.
_FEELING_WORDS = (
    "tired", "exhausted", "good", "great", "fine", "ok", "okay", "meh", "rough",
    "stressed", "stress", "anxious", "overwhelmed", "drained", "low", "awful",
    "struggling", "heavy", "off", "tough", "hard", "better", "worse", "happy",
    "sad", "angry", "frustrated", "calm", "energized", "motivated", "alright",
    "decent", "blah", "fantastic", "terrible", "not bad", "not great", "not good",
    "so-so", "could be better", "hanging in", "been better", "pretty good",
    "really good", "doing well", "doing ok", "doing okay", "doing good", "doing fine",
)
_FEELING_LEADS = (
    "i'm ", "im ", "i am ", "i feel", "feeling ", "i've been", "ive been",
    "i have been", "just ", "a bit", "a little", "kind of", "kinda", "honestly",
    "pretty ", "not ",
)


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


def _opens_with_feeling(n):
    """The reply OPENS with affect — a feeling lead ("I'm…", "feeling…") or a feeling
    word within its first few words. This lets an ELABORATED feeling answer ("I'm
    feeling good, rested — I know 6.4 isn't my 7 hours, but that's good for me") still
    read as a check-in reply, while a long UNRELATED statement or request (which does
    not open with affect) is not trapped as one."""
    head = " ".join(n.split()[:8])
    if any(head.startswith(lead) for lead in _FEELING_LEADS):
        return True
    padded = f" {head} "
    return any(f" {w} " in padded for w in _FEELING_WORDS)


def _is_plausible_feeling(message):
    """True when the message reads as an AFFECTIVE reply to a check-in — INCLUDING an
    elaborated one. A question, an imperative/new subject, or a general-knowledge query
    is NOT a feeling — it is a pivot that abandons the check-in (so a failed/interrupted
    check-in cannot trap an unrelated conversation).

    Root-cause note: length is NOT the test. An honest feeling answer is often long
    ("I'm feeling good. Rested actually. I know 6.4 isn't my 7 hours, but 6.4 is good
    for me.") — the old 14-word cap misread that as a subject change and dropped the
    primary morning happy path to a generic failure. What matters is whether the reply
    OPENS with affect, not how many words follow."""
    n = _norm(message)
    if not n or _looks_like_question(message):
        return False
    # A short reply carrying any affect word is clearly a feeling.
    if len(n.split()) <= 14 and any(f in n for f in _FEELING_WORDS):
        return True
    # A longer reply is a feeling ONLY when it OPENS affectively — so an elaborated
    # "I'm good, rested, …" counts, but a long request/new subject does not.
    if _opens_with_feeling(n):
        return True
    return any(n.startswith(lead) for lead in _FEELING_LEADS)


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


def clear_state(conversation):
    """Abandon the current conversation state so a pending personal interaction
    (e.g. an interrupted/failed check-in) cannot contaminate the next turn."""
    if conversation is None:
        return
    try:
        md = dict(getattr(conversation, "metadata", None) or {})
        if md.pop(STATE_KEY, None) is not None:
            conversation.metadata = md
            conversation.save(update_fields=["metadata"])
    except Exception:
        logger.warning("conversation_planner: clear_state failed", exc_info=True)


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

    # 3) Post-check-in response. A check-in expects a short AFFECTIVE reply — brief
    #    on that. ANYTHING ELSE (a question, a general-knowledge query, an unrelated
    #    new subject) is a PIVOT: ABANDON the check-in and route normally. This is
    #    the self-heal that a pending check-in previously lacked (unlike pending
    #    clarification, which already clears on a non-reply), so an interrupted or
    #    FAILED check-in can no longer trap the next unrelated conversation in
    #    personal coaching.
    if cur == "check_in" and not is_critique(message):
        if _is_plausible_feeling(message):
            write_state(conversation, state="briefing", objective="executive_briefing",
                        last_beth_act="briefed", feeling=_norm(message)[:120])
            return {"handler": "brief_after_checkin", "feeling": _norm(message)}
        clear_state(conversation)
        return {"handler": "route"}

    # 4) Default — no conversational intervention.
    return {"handler": "route"}
