# ==============================================================================
# File: apps/ai/chatgpt_cos/correction.py
# Capability: USER-CORRECTION TRUST-REPAIR.
#
# When the user CORRECTS a factual claim or recommendation Beth just made — "today is
# not strength training, it's cardio", "why didn't you know that?", "you should have
# checked my schedule" — that is a TRUST-REPAIR moment, not a request to move/change a
# plan. Production failure: the correction "today is cardio instead of strength" was
# caught by decision_support's change_mind cue ("instead of") and answered as a
# reschedule ("Tell me what you're moving to and I'll sanity-check it…") — completely
# off-context, a trust failure.
#
# This is DISTINCT from the existing repair paths:
#   • conversation_planner.is_meta_conversational → the user critiques Beth's TURN
#     ("that's not what I meant", "look at the message you gave me").
#   • priority_correction → the user corrects a PRIORITY ("you put X over my meds").
#   • reconciliation → the user gives evidence an item is already done / not today.
# None of them catch a bare FACTUAL correction of the world-fact Beth reasoned from.
#
# Recovery is deterministic and closes the loop: it re-reads the SAME source of truth
# Beth should have checked in the first place (apps/ai/chatgpt_cos/day_truth.py) and
# produces the corrected recommendation — acknowledge the miss, restate the corrected
# truth, name the source, give the corrected plan, no apology loop.
# ==============================================================================
import logging
import re

logger = logging.getLogger(__name__)

# (a) The user challenges Beth's factual accuracy / knowledge, or flags a miss.
_KNOWLEDGE_CHALLENGE = (
    "why didnt you know", "why dont you know", "why did you not know",
    "how did you not know", "how do you not know", "you should have known",
    "you should know that", "you didnt check", "you should have checked",
    "you didnt look at", "you should have looked", "didnt you know", "did you not know",
    "why didnt you", "why did you not", "why didnt you offer", "why didnt you mention",
    "you got that wrong", "you have that wrong", "you got it wrong", "you were wrong",
    "you have it wrong", "you had that wrong", "dont you know my", "you clearly didnt",
)
# (b) The user negates a claim Beth made and restates the correct fact.
_FACT_CORRECTION = (
    "thats not correct", "that isnt correct", "thats incorrect", "not correct",
    "thats not accurate", "that isnt accurate", "thats not true", "no thats not",
    "no its not", "no im not", "actually its", "actually im", "actually today",
    "actually thats", "today is not", "today isnt", "today is actually",
    "thats not my", "thats not what i do", "im not doing that today",
    "not today", "wrong day", "you mixed up", "you confused", "get that wrong",
)
# A NEGATION-then-RESTATEMENT shape: "not <thing> it's/that's <other thing>" — the user
# says what it is NOT and immediately what it IS ("not strength, it's cardio"). Kept
# high-precision (the corrective "its"/"thats" must directly follow the short negated
# phrase) so an ordinary "I'm not great but hanging in" / "didn't sleep well, today is
# rough" is never misread as a correction.
_NEG_CORRECTION_RE = re.compile(
    r"\bnot\b\s+\w+(?:\s+\w+){0,2}?[, ]+(?:its|it s|thats)\s+\w")

# First-person DECISION frame — the user choosing to change their OWN plan (a real
# change-of-mind), NOT correcting a fact. When present, "X instead of Y" is a decision
# for decision_support, not a correction. When ABSENT, a bare "it's cardio instead of
# strength" is a declarative correction of what Beth got wrong.
_DECISION_FRAME = (
    "im going to", "im gonna", "i am going to", "ill do", "i will", "i think ill",
    "i think im", "im doing", "i decided", "ive decided", "im gonna do", "lets do",
    "let me do", "i want to do", "i wanna", "im planning", "im switching", "im moving",
    "changed my mind", "change of plans", "on second thought", "second thoughts",
    "i might", "im leaning", "gonna do instead",
)


def _norm(s):
    # Lowercase; strip apostrophes; normalize separators — mirrors decision_support.
    s = re.sub(r"[’']", "", (s or "").lower())
    return re.sub(r"[\-/]", " ", re.sub(r"\s+", " ", s)).strip()


def _has_decision_frame(n):
    return any(c in n for c in _DECISION_FRAME)


def is_factual_correction(message):
    """True when the user is correcting a FACT/recommendation Beth made (not changing
    their own plan, not critiquing her turn). Deterministic; gate on a prior Beth turn
    at the call site."""
    n = _norm(message)
    if not n:
        return False
    if any(c in n for c in _KNOWLEDGE_CHALLENGE):
        return True
    if any(c in n for c in _FACT_CORRECTION):
        return True
    # A negation paired with a corrective connector, e.g. "it's cardio not strength".
    if _NEG_CORRECTION_RE.search(n):
        return True
    # "X instead of Y" / "X rather than Y" as a bare DECLARATIVE (no first-person
    # decision frame) is correcting a fact, not the user changing their own plan.
    if ("instead of" in n or "rather than" in n) and not _has_decision_frame(n):
        return True
    return False


# Domains a correction can be about — drives which deterministic source we re-check.
_WORKOUT_WORDS = ("workout", "work out", "strength", "cardio", "training", "train",
                  "exercise", "gym", "lift", "bike", "ride", "run", "pickleball",
                  "session", "schedule")
_PROTEIN_WORDS = ("protein", "breakfast", "nutrition", "eat", "meal", "food", "macro")


def _mentions(n, words):
    return any(w in n for w in words)


def respond(user, message, conversation=None):
    """Trust-repair: acknowledge the specific miss, restate the corrected truth from the
    deterministic source Beth should have checked, name that source, and give the
    corrected recommendation. Returns a lane result dict, or None to decline."""
    n = _norm(message)
    parts = []
    handled = False

    if _mentions(n, _WORKOUT_WORDS):
        handled = True
        planned = None
        try:
            from apps.ai.chatgpt_cos.day_truth import todays_planned_workout
            planned = todays_planned_workout(user)
        except Exception:
            logger.warning("correction: planned workout read failed", exc_info=True)
        parts.append("You're right, and I can name the miss precisely: I recommended a "
                     "workout from your goals instead of checking what's actually on "
                     "your schedule today.")
        if planned and planned.get("type"):
            when = f" at {planned['time']}" if planned.get("time") else ""
            parts.append(f"Today's plan is {planned['type']}{when} — I should have read "
                         "your workout schedule first, not inferred a session from your "
                         "training goals.")
            if planned.get("completed"):
                parts.append(f"And you've already done it — so today's movement is "
                             "handled; nothing more to add there.")
            else:
                parts.append(f"So the move is simple: keep your {planned['type']}"
                             f"{when} as planned and make it count.")
        else:
            parts.append("I don't see a workout on your schedule for today, so I should "
                         "have said that plainly instead of prescribing a type — tell me "
                         "what you're doing and I'll build around it, not override it.")

    if _mentions(n, _PROTEIN_WORDS):
        handled = True
        try:
            from apps.ai.chatgpt_cos.day_truth import protein_options
            opts = protein_options(user)
        except Exception:
            opts = "eggs, Greek yogurt, or a protein shake"
        lead = "" if parts else ("You're right — if I say focus on protein, I owe you "
                                 "the how, not just the what. ")
        parts.append(f"{lead}For ~30g at your next meal: {opts}. Pick whichever fits "
                     "your morning and you're set.")

    if not handled:
        # A factual correction we can't tie to a specific deterministic source: own it,
        # name the general failure (reasoning from goals/assumptions instead of your
        # actual state), and offer to re-ground — never a defensive loop.
        parts.append("You're right — I got that wrong, and I'd rather fix it than defend "
                     "it. I reasoned from a general assumption instead of your actual "
                     "state. Tell me the correct detail and I'll rebuild the "
                     "recommendation from what's really true for you today.")

    return {"answer": " ".join(parts), "tools_called": [], "tools_advertised": [],
            "lane": "correction_recovery"}
