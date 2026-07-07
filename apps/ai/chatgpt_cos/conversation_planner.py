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

# A META-CONVERSATIONAL reference to BETH'S OWN prior turn — the user is talking about
# the MESSAGE Beth just gave, not the world. "Look at the message you gave me", "read
# your last response", "that's not what I meant", "you misunderstood me". A human Chief
# of Staff hears this instantly as feedback about HER answer; without it Beth mistakes
# it for a new domain request (a plan change, a fact query). This is a STRUCTURED class
# — a second-person reference to Beth's speech/output, or a correction of her
# understanding — not an open-ended phrase whitelist. Gated on has_prior at the call
# site, so it only fires when there IS a prior Beth turn to refer to.
#
# (a) A DIRECTIVE to re-examine Beth's message, or an explicit reference to the
# message artifact she produced. Kept to unambiguous "look at / read your message"
# forms — bare recall ("remind me what you said about my weight") is intentionally
# NOT here; that belongs to the why_explainer / conversation-memory lanes.
_PRIOR_TURN_REFS = (
    "look at the message you", "look at your response", "look at your last",
    "look at your answer", "look at your message", "look at what you said",
    "look at what you wrote", "look at what you gave", "look back at your",
    "read your response", "read your last", "read your answer", "read your message",
    "read what you said", "read what you wrote", "reread your", "re-read your",
    "go back and read your", "go back to your", "check your last message",
    "check your last response", "the message you gave", "the message you sent",
    "the message you just gave", "your last message", "your last response",
    "your previous message", "your previous response", "your earlier message",
    "your earlier response", "what you wrote", "review your response",
    "review your last",
)
# (b) A correction of Beth's UNDERSTANDING of the user (not a critique of a fact).
_META_CORRECTION = (
    "that's not what i meant", "thats not what i meant", "not what i meant",
    "that's not what i asked", "thats not what i asked", "not what i asked",
    "that wasn't my question", "that wasnt my question", "that's not my question",
    "you misunderstood", "you misunderstand", "you're misunderstanding",
    "youre misunderstanding", "you misread", "you're misreading", "youre misreading",
    "you didn't answer", "you didnt answer", "you did not answer",
    "you're not answering", "youre not answering", "that doesn't answer",
    "that didn't answer", "i didn't ask that", "i didnt ask that",
    "i didn't ask for that", "i didnt ask for that", "you missed my point",
    "you're missing my point", "youre missing my point", "you got me wrong",
    "you took that wrong", "you misheard",
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


# ── CONVERSATIONAL NEED (posture) ────────────────────────────────────────────
# A Chief of Staff first works out WHAT KIND of conversation this is, then chooses how
# much to say and what posture to take — she does not answer every opener with a full
# briefing. This is a THIN classifier of the user's expressed NEED, not a script: it
# only decides whether the moment calls for problem-solving or listening instead of the
# default executive read; everything it doesn't recognize falls through UNCHANGED to the
# existing routing (greeting → check-in, feeling → brief, questions → their lanes).
NEED_PROBLEM_SOLVING = "problem_solving"     # the user is behind/overwhelmed → help, don't brief
NEED_PERSONAL_CONCERN = "personal_concern"   # a worry about a person/life → listen, don't brief

# Workload / capacity difficulty the user wants eased — the signal is being BEHIND or
# OVERWHELMED, not merely tired.
_PROBLEM_SOLVING_CUES = (
    "feel behind", "feeling behind", "falling behind", "fallen behind", "so behind",
    "way behind", "really behind", "already behind", "im behind", "i am behind",
    "get behind", "getting behind", "overwhelmed", "swamped", "buried", "drowning",
    "underwater", "slammed", "too much to do", "too much on", "so much to do",
    "so much going on", "cant keep up", "cannot keep up", "cant catch up",
    "cannot catch up", "no time", "not enough time", "stretched thin", "spread thin",
    "a lot on my plate", "lot on my plate", "in over my head", "crazy busy", "swamped",
    "drowning in", "snowed under",
)
# A worry ABOUT something — becomes a personal concern only when it is NOT about an
# executive domain (health/goals/work/money); those stay on their normal reasoning path.
_CONCERN_CUES = ("worried about", "worry about", "worrying about", "concerned about",
                 "anxious about", "nervous about", "scared about", "afraid for",
                 "upset about", "stressed about", "on my mind", "keeps me up about",
                 "can't stop thinking about", "cant stop thinking about")
_EXEC_DOMAIN_WORDS = (
    "weight", "protein", "glucose", "blood sugar", "a1c", "insulin", "sleep", "workout",
    "training", "cardio", "exercise", "nutrition", "calorie", "diet", "macro",
    "medication", "meds", "health", "goal", "mission", "france", "task", "deadline",
    "project", "money", "finance", "budget", "bill", "income", "work", "job",
    "today", "this week", "the week", "everything", "my schedule", "the day", "all this",
)


# A reply that self-qualifies as coping ("tired but okay") wants a light touch, not a
# problem-solving intervention.
_MANAGING_QUALIFIERS = ("but okay", "but ok", "but fine", "but good", "but alright",
                        "but managing", "but hanging in", "but doing okay", "not too bad",
                        "could be worse", "ill be fine", "im fine", "im okay", "im ok",
                        "still good", "nothing i cant handle", "nothing i can't handle")


def classify_need(message):
    """Classify the conversational NEED behind an opener → NEED_PROBLEM_SOLVING /
    NEED_PERSONAL_CONCERN / None. Deterministic and conservative: it fires only on a
    clear problem-to-solve or a clear personal worry; everything else returns None so
    the existing routing (orientation, execution, briefing) is untouched."""
    # Strip apostrophes so the apostrophe-free cue lexicons match ("i'm" → "im").
    n = re.sub(r"[’']", "", _norm(message))
    if not n:
        return None
    if any(c in n for c in _PROBLEM_SOLVING_CUES):
        return NEED_PROBLEM_SOLVING
    for cue in _CONCERN_CUES:
        idx = n.find(cue)
        if idx == -1:
            continue
        tail = n[idx + len(cue):]
        # A worry about an executive domain stays on its normal path; a worry about a
        # person / life situation is a listening moment.
        if not any(w in tail or w in n for w in _EXEC_DOMAIN_WORDS):
            return NEED_PERSONAL_CONCERN
    # NEGATIVE energy the user ISN'T already brushing off ("I'm exhausted") is a moment to
    # make the day easier, not to brief or to lecture on recovery — offer to help. A reply
    # that self-qualifies as managing ("tired but okay") stays a light orientation.
    if not _looks_like_question(n) and not any(q in n for q in _MANAGING_QUALIFIERS):
        try:
            from apps.ai.chatgpt_cos.executive_interpretation import classify_subjective_energy
            if classify_subjective_energy(message) == "negative":
                return NEED_PROBLEM_SOLVING
        except Exception:
            pass
    return None


def concern_object(message):
    """Best-effort extraction of WHAT the user is worried about ("worried about Haley"
    → "Haley"), for a natural acknowledgment. Returns "" when nothing clean is found."""
    n = _norm(message)
    for cue in ("worried about", "worry about", "worrying about", "concerned about",
                "anxious about", "nervous about", "scared about", "upset about",
                "stressed about", "thinking about"):
        idx = n.find(cue)
        if idx != -1:
            tail = n[idx + len(cue):].strip()
            # take up to a clause boundary
            for stop in (".", ",", ";", " and ", " but ", " because ", " right now",
                         " lately", " today"):
                p = tail.find(stop)
                if p != -1:
                    tail = tail[:p]
            tail = tail.strip(" .,!?")
            # Preserve the original casing of the object (names like "Haley").
            if tail and len(tail.split()) <= 5:
                # map back to original-case slice
                raw = re.sub(r"\s+", " ", (message or "").strip())
                m = re.search(re.escape(tail), raw, re.IGNORECASE)
                return m.group(0) if m else tail
    return ""


# A REFRESH / RE-CHECK request — the user changed their data and wants Beth to look at
# the CURRENT version. In an active task-review flow this is "re-read my tasks", NOT a
# critique of Beth's turn (even though "look again" is also a critique cue). Gated on the
# problem-solving context at the call site so it only overrides repair when appropriate.
_REFRESH_CUES = (
    "look again", "look at it again", "look at that again", "look once more",
    "look one more time", "take another look", "have another look", "another look",
    "check again", "check it again", "recheck", "re-check", "re check", "look now",
    "check now", "refresh", "re-look", "relook", "look back at it", "run it again",
    "look at my updated", "see the updated", "updated it", "updated them", "updated my",
    "i updated", "ive updated", "just updated", "i changed it", "i changed my",
    "changed it now", "made changes", "made some changes", "made a few changes",
    "made an update", "recheck it", "look at the current", "pull it up again",
)


def is_refresh_request(message):
    """True when the user is asking Beth to RE-READ the current state (they updated their
    data): 'look again', 'I updated my tasks', 'refresh', 'recheck'. Not a critique."""
    n = re.sub(r"[’']", "", _norm(message))
    return any(c in n for c in _REFRESH_CUES)


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


def refers_to_prior_turn(message):
    """True when the user is talking ABOUT Beth's own prior turn — pointing at the
    message she gave, or correcting how she understood them — rather than asking a new
    question about the world. Generalizes the critique cues to the whole meta-
    conversational class so 'look at the message you gave me' / 'that's not what I
    meant' / 'you misunderstood me' route to REPAIR instead of a domain lane."""
    n = _norm(message)
    if not n:
        return False
    return (any(c in n for c in _PRIOR_TURN_REFS)
            or any(c in n for c in _META_CORRECTION))


def is_meta_conversational(message):
    """A critique OF, or a reference TO, Beth's previous answer. The full trigger for
    the self-aware REPAIR path."""
    return is_critique(message) or refers_to_prior_turn(message)


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

    # 0.5) REFRESH within an active PROBLEM-SOLVING / task-review flow. The user updated
    #      their tasks and asked Beth to look again — that means RE-READ today's task/
    #      schedule truth and keep helping, NOT critique-repair (even though "look again"
    #      is also a critique cue). Gated on the problem-solving context so a genuine
    #      "look again [you got it wrong]" in any other context still routes to repair.
    if cur == "problem_solving" and is_refresh_request(message):
        write_state(conversation, state="problem_solving", objective="ease_the_load",
                    last_beth_act="refreshed")
        return {"handler": "problem_solving_refresh"}

    # 1) REPAIR — a critique OF, or a reference TO, Beth's PREVIOUS answer ("look at
    #    the message you gave me", "that's not what I meant"). Meta-conversational
    #    feedback is about MY turn, never a fresh domain request — catch it before the
    #    retrieval/decision lanes read it as a plan change or a fact query.
    if is_meta_conversational(message) and has_prior:
        write_state(conversation, state="repair", objective="repair",
                    last_beth_act="repaired")
        return {"handler": "repair", "prior_answer": prior}

    # 1.5) CONVERSATIONAL NEED — before defaulting to a check-in or a briefing, read what
    #      kind of conversation this is. A user who is BEHIND/OVERWHELMED needs help, not a
    #      briefing; a user WORRIED ABOUT A PERSON needs listening, not executive
    #      priorities. This overrides the greeting/brief defaults (so "good morning, I'm
    #      swamped" is problem-solving) but only fires on a clear need — otherwise routing
    #      is unchanged. Introduce executive priorities only when they serve the moment.
    need = classify_need(message)
    if need == NEED_PROBLEM_SOLVING:
        write_state(conversation, state="problem_solving", objective="ease_the_load",
                    last_beth_act="offered_help")
        return {"handler": "problem_solving"}
    if need == NEED_PERSONAL_CONCERN:
        write_state(conversation, state="listening", objective="engage_concern",
                    last_beth_act="listened")
        return {"handler": "personal_concern"}

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
    if cur == "check_in" and not is_meta_conversational(message):
        if _is_plausible_feeling(message):
            write_state(conversation, state="briefing", objective="executive_briefing",
                        last_beth_act="briefed", feeling=_norm(message)[:120])
            return {"handler": "brief_after_checkin", "feeling": _norm(message)}
        clear_state(conversation)
        return {"handler": "route"}

    # 4) Default — no conversational intervention.
    return {"handler": "route"}
