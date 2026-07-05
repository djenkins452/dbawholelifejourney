# ==============================================================================
# File: apps/ai/chatgpt_cos/reconciliation.py
# Capability: EXECUTIVE STATE RECONCILIATION. When the user supplies trustworthy
# first-person evidence that changes the executive picture about a specific item Beth
# is treating as today's priority — "I already did that", "I did it yesterday", "I don't
# need one", "that's a morning-only activity, too late now", "that meeting was canceled",
# "I'm traveling / I'm sick" — a world-class Chief of Staff does NOT retrieve a fact and
# does NOT argue. She ACCEPTS the evidence, UPDATES her understanding (stops treating the
# item as today's priority), RECALCULATES, and CONTINUES the conversation.
#
# Production failure that motivated this: Beth surfaced "Next up: Shower (overdue)"; the
# user said "I don't really need one, I showered late yesterday; too late to measure,
# that's a first-thing-in-the-morning activity like weighing in." Beth answered with
# yesterday's WEIGHT (the weight_history lane grabbed "weighing in"), then collapsed to
# "I couldn't pull that together." She never reconciled her executive state.
#
# GENERAL, NOT HARDCODED: the affected items are resolved from the user's OWN rhythm
# (get_remaining_rhythm_items) and from the item Beth just surfaced in her previous
# message — never a fixed list of task names. The deferral is recorded into the shared
# executive-evidence store so interpret() folds it into the ONE picture and every
# consumer stops surfacing it. Deterministic, request-path safe, degrades gracefully.
# ==============================================================================
import logging
import re

logger = logging.getLogger(__name__)

# ── Reconciliation speech-acts: trustworthy first-person evidence that an item is not
#    today's priority. Matched against a normalized (apostrophe-stripped) message. ──
_ALREADY_DONE = (
    "already did", "already done", "did it already", "did that already", "i did that",
    "already took", "i took my", "already had", "already got", "took them already",
    "just did it", "i did it", "handled it already", "already handled",
)
_DONE_RECENTLY = (
    "did it yesterday", "did that yesterday", "late yesterday", "last night",
    "earlier today", "did it this morning", "yesterday", "night before",
)
_DONT_NEED = (
    "dont need one", "dont need it", "dont need to", "dont really need", "no need to",
    "dont need a", "dont have to", "dont really need one", "really need one",
)
_WRONG_TIME = (
    "too late to", "too late for", "too late now", "morning activity", "morning thing",
    "first thing in the morning", "morning only", "only in the morning",
    "only matters in the morning", "only meaningful in the morning", "not appropriate",
    "not the right time", "wrong time of day", "afternoon is too late",
)
_CANCELED = (
    "was canceled", "was cancelled", "got canceled", "got cancelled", "is canceled",
    "is cancelled", "called off", "was called off", "no longer happening",
)
_UNAVAILABLE = (
    "im traveling", "im out of town", "im on the road", "im sick", "im ill",
    "not feeling well", "under the weather", "im away", "out of town today",
)
_NO_LONGER = ("no longer true", "not true anymore", "thats no longer", "no longer need")

# A "decline about the thing Beth just surfaced" — lets an unnamed 'one'/'it' resolve to
# the item Beth surfaced in her previous message (referential).
_DECLINE_ACTS = _DONT_NEED + _ALREADY_DONE + _DONE_RECENTLY + _NO_LONGER

_STOPWORDS = {"the", "a", "an", "my", "your", "and", "or", "to", "of", "in", "on", "for",
              "take", "do", "get", "log", "check"}


def _norm(s):
    s = (s or "").lower().replace("-", " ").replace("/", " ")
    s = s.replace("'", "").replace("’", "")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _is_question(raw):
    if "?" in (raw or ""):
        return True
    n = _norm(raw)
    return any(n.startswith(w) for w in (
        "what", "when", "how", "did i", "do i", "can you", "did you", "is my",
        "are my", "was my", "whats", "hows"))


def _title_stems(title):
    """Significant word-stems of a rhythm item title (drop stopwords / short words)."""
    stems = []
    for w in _norm(title).split():
        if len(w) >= 4 and w not in _STOPWORDS:
            stems.append(w[:5])
    return stems


def _rhythm_items(user):
    try:
        from apps.core.cos_briefing.rhythm_api import get_remaining_rhythm_items
        return [it for it in (get_remaining_rhythm_items(user) or [])
                if (it.get("title") or "").strip()]
    except Exception:
        logger.warning("reconciliation: rhythm read failed", exc_info=True)
        return []


def _prior_assistant_text(conversation):
    if conversation is None:
        return ""
    try:
        from apps.ai.models import AssistantMessage
        m = (AssistantMessage.objects.filter(conversation=conversation, role="assistant")
             .order_by("-created_at").values_list("content", flat=True).first())
        return m or ""
    except Exception:
        return ""


class Reconciliation:
    def __init__(self, items, reasons, resume):
        self.items = items          # [rhythm item dict] — the affected items
        self.reasons = reasons      # [str] — WHY, in the user's terms
        self.resume = resume        # str — when to pick them back up


def _reasons_and_resume(norm):
    """Deterministic, natural reasons + a resume window from the detected evidence."""
    reasons, morning = [], False
    if any(c in norm for c in _WRONG_TIME):
        morning = any(c in norm for c in (
            "morning", "first thing", "weighing in", "weigh")) or "morning" in norm
        reasons.append("it's a first-thing-in-the-morning activity that this part of the "
                       "day is too late for" if morning
                       else "now isn't the right time of day for it")
    if any(c in norm for c in _DONE_RECENTLY):
        reasons.append("you already took care of it recently")
    elif any(c in norm for c in _ALREADY_DONE):
        reasons.append("you've already done it")
    if any(c in norm for c in _DONT_NEED) and not reasons:
        reasons.append("you don't need it today")
    if any(c in norm for c in _CANCELED):
        reasons.append("it's been canceled")
    if any(c in norm for c in _UNAVAILABLE):
        reasons.append("you're not in a position to do it today")
    if any(c in norm for c in _NO_LONGER) and not reasons:
        reasons.append("it no longer applies")
    resume = "tomorrow morning" if morning else "tomorrow"
    return reasons, resume


def detect(user, message, conversation=None):
    """Recognize an executive-state reconciliation and resolve the affected item(s) from
    the user's OWN rhythm + the item Beth just surfaced. Returns a ``Reconciliation`` or
    ``None`` (so normal routing is unaffected when nothing reconciles)."""
    raw = message or ""
    if _is_question(raw):
        return None
    norm = _norm(raw)
    if not norm:
        return None
    acts = (_ALREADY_DONE + _DONE_RECENTLY + _DONT_NEED + _WRONG_TIME + _CANCELED
            + _UNAVAILABLE + _NO_LONGER)
    if not any(c in norm for c in acts):
        return None

    items = _rhythm_items(user)
    if not items:
        return None
    prior = _norm(_prior_assistant_text(conversation))
    decline = any(c in norm for c in _DECLINE_ACTS)

    affected, seen = [], set()
    for it in items:
        title = it["title"].strip()
        stems = _title_stems(title)
        if not stems:
            continue
        named = any(st in norm for st in stems)
        surfaced = any(st in prior for st in stems)
        if named or (surfaced and decline):
            key = title.lower()
            if key not in seen:
                seen.add(key)
                affected.append(it)
    if not affected:
        return None
    reasons, resume = _reasons_and_resume(norm)
    return Reconciliation(items=affected, reasons=reasons, resume=resume)


# ── Composition — Beth ACCEPTS, updates, recalculates, and continues. ──────────────
def _join(names):
    names = [n for n in names if n]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + ", and " + names[-1]


def _next_step(user, deferred_titles):
    """The executive next step after reconciliation — from the ONE picture (interpret).
    Never re-derives; just presents what the executive read already concluded."""
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        sig = interpret(user)
    except Exception:
        logger.warning("reconciliation: interpret failed", exc_info=True)
        return ""
    opp = getattr(sig, "opportunity", None)
    if opp and opp.get("action"):
        return f"With your capacity today, I'd {opp['action']}."
    lev = (getattr(sig, "highest_leverage", "") or "").strip()
    if lev:
        return f"The highest-leverage use of the rest of the day is {lev}."
    strat = (getattr(sig, "strategic_focus", "") or "").strip()
    if strat:
        return f"That frees the rest of the day to move {strat} forward."
    return ""


def _remaining_clause(user, deferred_titles):
    """What's left on today's rhythm once the reconciled items are removed."""
    dl = {t.lower() for t in deferred_titles}
    rest = [it["title"].strip() for it in _rhythm_items(user)
            if it["title"].strip().lower() not in dl]
    if not rest:
        return "That clears your routine for the rest of today."
    return f"That leaves {_join(rest[:4])} on today's rhythm."


def compose(user, rec):
    titles = [it["title"].strip() for it in rec.items]
    plural = len(titles) > 1
    parts = ["That makes sense."]
    parts.append(f"I'll stop treating {_join(titles)} as "
                 f"{'today’s priorities' if plural else 'today’s priority'}.")
    if rec.reasons:
        them = "them" if plural else "it"
        parts.append(f"Since {_join(rec.reasons)}, we'll pick {them} back up {rec.resume}.")
    else:
        them = "them" if plural else "it"
        parts.append(f"We'll pick {them} back up {rec.resume}.")
    parts.append(_remaining_clause(user, titles))
    step = _next_step(user, titles)
    if step:
        parts.append(step)
    return " ".join(p for p in parts if p)


def answer(user, message, conversation=None):
    """Lane entry: if the message reconciles executive state, record the deferral(s),
    update the ONE picture, and return a composed accept-and-continue response;
    otherwise return ``None`` so fact/reasoning routing is unaffected."""
    rec = detect(user, message, conversation)
    if rec is None:
        return None
    try:
        from apps.ai.chatgpt_cos.executive_evidence import record_deferral
        reason = rec.reasons[0] if rec.reasons else ""
        for it in rec.items:
            record_deferral(user, it["title"].strip(), reason=reason, resume=rec.resume)
    except Exception:
        logger.warning("reconciliation: record_deferral failed", exc_info=True)
    try:
        text = compose(user, rec)
    except Exception:
        logger.warning("reconciliation: compose failed", exc_info=True)
        return None
    if not text:
        return None
    return {"answer": text, "tools_called": [], "tools_advertised": [],
            "lane": "reconciliation",
            "reconciled": [it["title"].strip() for it in rec.items]}
