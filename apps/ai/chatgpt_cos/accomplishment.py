# ==============================================================================
# File: apps/ai/chatgpt_cos/accomplishment.py
# Capability: RECOGNIZE MISSION-SIGNIFICANT ACCOMPLISHMENTS (WI-2). When the user
# REPORTS something they did — "I made up my workouts from Wednesday and Friday",
# "I got my workout in" — that is not a workout fact to look up; it materially changes
# today's picture: exceptional effort → increased recovery need → priorities shift.
# Beth should recognize it, celebrate appropriately, and RECORD it as today's evidence
# so the rest of the executive reasoning (Decision Support / the brief) reflects
# everything already accomplished today — she stops reasoning from the morning state.
#
# The record is a per-user, per-day list of short labels in the cache; downstream
# consumers read `todays(user)`. Deterministic; declines questions (those are
# retrieval — workout_history owns them).
# ==============================================================================
import logging
import re

logger = logging.getLogger(__name__)

_WORKOUT_WORDS = ("workout", "workouts", "session", "sessions", "training", "lift",
                  "lifts", "lifting", "run", "ride", "rides", "cardio")
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_NUMWORDS = {"a": 1, "one": 1, "two": 2, "both": 2, "couple": 2, "three": 3, "few": 3,
             "four": 4, "five": 5}
_COMPLETED_CUES = ("i completed", "i finished", "i did my", "i got my", "got my workout in",
                   "i got in", "i knocked out", "knocked out my", "crushed my", "i hit my",
                   "nailed my", "got it done", "i completed my", "just finished my",
                   "i just did", "i already did", "i worked out")


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _is_question(raw):
    n = _norm(raw)
    if "?" in (raw or ""):
        return True
    return any(n.startswith(w) for w in (
        "did you", "did i", "can you", "do you", "have you", "what", "how", "when",
        "does ", "is my", "are my"))


class Accomplishment:
    def __init__(self, kind, label):
        self.kind = kind          # made_up | completed
        self.label = label        # "made up 2 workouts (Wednesday, Friday)"


def detect(message):
    """Recognize a first-person REPORT of a workout accomplishment, or None. Declines
    questions (retrieval) so it never steals 'did you see my workout?'."""
    raw = message or ""
    if _is_question(raw):
        return None
    n = _norm(raw)
    has_workout = any(f" {w} " in f" {n} " for w in _WORKOUT_WORDS)

    # "I made up my workouts from Wednesday and Friday" / "made up two missed sessions".
    if "made up" in n and has_workout:
        days = [d for d in _WEEKDAYS if d in n]
        cnt = None
        for w, v in _NUMWORDS.items():
            if f" {w} " in f" {n} ":
                cnt = max(cnt or 0, v)
        m = re.search(r"\b(\d+)\b", n)
        if m:
            cnt = max(cnt or 0, int(m.group(1)))
        if cnt is None:
            cnt = len(days) or 1
        daystr = f" ({', '.join(d.capitalize() for d in days)})" if days else ""
        label = f"made up {cnt} missed workout{'s' if cnt != 1 else ''}{daystr}"
        return Accomplishment("made_up", label)

    # "I got my workout in" / "I finished my session" / "I did my workout".
    if any(c in n for c in _COMPLETED_CUES) and has_workout:
        return Accomplishment("completed", "got today's workout in")
    return None


# ── Per-day evidence — persisted in the SHARED executive-evidence store, which
#    interpret() merges into the one executive picture. This module records; every
#    consumer reads through interpret()/ExecutiveSignals, not this cache directly. ──
def record(user, label):
    from apps.ai.chatgpt_cos.executive_evidence import record_accomplishment
    record_accomplishment(user, label)


def todays(user):
    """Today's reported accomplishment labels (list). Kept for compatibility; the
    canonical consumer path is interpret() → ExecutiveSignals.accomplishments."""
    from apps.ai.chatgpt_cos.executive_evidence import today
    return today(user).get("accomplishments", [])


def _compose(sig):
    if sig.kind == "made_up" and ("2" in sig.label or "3" in sig.label
                                  or "4" in sig.label or "5" in sig.label):
        return (f"That's a genuine win — {sig.label} means you've banked more work than "
                "today's plan asked for. That actually changes the picture: you've earned "
                "recovery now, and easing off later today wouldn't be slacking — it'd be "
                "smart. Nice work.")
    return (f"Good — that's {sig.label}. Solid work today; your body will want real "
            "recovery to turn that effort into progress.")


def answer(user, message, conversation=None):
    sig = detect(message)
    if sig is None:
        return None
    record(user, sig.label)
    return {"answer": _compose(sig), "tools_called": [], "tools_advertised": [],
            "lane": "accomplishment", "accomplishment": sig.label}
