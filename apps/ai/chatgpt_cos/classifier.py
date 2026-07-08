# ==============================================================================
# File: apps/ai/chatgpt_cos/classifier.py
# THE CONDUCTOR — the Classifier (its attention). Reads a turn and decides WHAT KIND of
# move the user made (the speech act) and therefore WHICH capability SHOULD own it. It
# never answers and never reads domain truth for meaning — classification stays shallow and
# deterministic (contract G1/G2/G4). Orchestration only.
#
# STEP 2a (this file): SHADOW / ADVISORY ONLY. It classifies every turn and its decision is
# LOGGED (speech_act, expected_owner, confidence) — the current router still answers, so
# there is ZERO behavior change. This is the orchestration-investigation instrument: every
# turn now records "which capability SHOULD have owned this" so a mis-ownership (e.g. a
# critique of Beth's guidance answered as a goals question) shows up as data, not archaeology.
# Later steps (2b/2c) make it authoritative for the unambiguous speech acts.
#
# Speech-act PRECEDENCE ladder (approved stabilization design) — first match wins,
# from "about this exact exchange" outward to "about the world":
#   1 screen · 2 meta/repair · 3 continuation · 4 correction · 5 reasoning_mode ·
#   6 retrieval · 7 orientation · 8 general · 9 fallback
# The classifier's cue sets are its OWN, shallow, form-level, domain-agnostic signals — it
# does NOT import any capability (that is what keeps the Conductor a closed core).
# ==============================================================================
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Classification:
    speech_act: str          # screen|meta|continuation|correction|reasoning_mode|retrieval|orientation|general|fallback
    expected_owner: str      # the capability FAMILY that should own the turn
    confidence: str          # high | medium | low
    signal: str = ""         # the cue that fired (diagnostics only)


# ── 1 · SCREEN / deixis (pointing at what's on screen) ───────────────────────
_SCREEN_CUES = (
    "what page am i on", "what page is this", "what page", "which page", "this page",
    "on this page", "current page", "what screen", "this screen", "what am i looking at",
    "what's on this screen", "whats on this screen", "on my screen",
)
_SCREEN_DEICTIC = ("summarize this", "explain this", "what is this", "whats this",
                   "what do you think of this", "what about this one")

# ── 2 · META / REPAIR (about Beth's OWN prior turn or guidance) ──────────────
# Critique of her GUIDANCE — she overlooked / omitted something she should have surfaced.
_GUIDANCE_CRITIQUE = (
    "you let me slide", "let me slide", "you overlooked", "overlooked", "you left out",
    "left out", "you didnt mention", "didnt mention", "you did not mention", "you skipped",
    "skipped", "you forgot to", "forgot to flag", "you missed", "you didnt include",
    "didnt include", "you didnt flag", "you ignored", "you should have", "you shouldve",
    "you failed to", "you didnt tell me", "why didnt you mention", "why didnt you tell me",
)
_PRIOR_TURN_REF = (
    "your last message", "your last response", "your previous message", "your earlier",
    "what you said", "what you wrote", "look at your response", "read your response",
    "the message you gave", "the message you sent", "your answer above",
)
_META_CORRECTION = (
    "thats not what i meant", "not what i meant", "thats not what i asked",
    "you misunderstood", "you misread", "you didnt answer", "you did not answer",
    "that doesnt answer", "i didnt ask that", "i didnt ask for that",
    "you missed my point", "you got me wrong", "you took that wrong",
)
_FACT_CRITIQUE = (
    "are you sure", "you sure about", "is that right", "is that correct", "is that accurate",
    "thats wrong", "thats not right", "that isnt right", "doesnt add up", "double check",
    "that cant be right", "that doesnt look right", "seems wrong", "why did you", "really?",
)

# ── 3 · CONTINUATION (continues the active thread, not a new subject) ─────────
_CONTINUATION_CUES = (
    "tell me more", "go on", "and then", "what about", "what else", "how so", "for example",
    "like what", "go deeper", "keep going", "say more", "anything else", "more on that",
    "expand on that", "and why", "why not", "such as",
)
_BARE_FOLLOWUPS = frozenset((
    "why", "why though", "but why", "and why", "how come", "so", "then what", "more",
    "continue", "elaborate", "keep going", "and", "more please", "go on",
))
_REFERENTIAL = frozenset((
    "that", "those", "them", "it", "this", "these", "they", "he", "she", "him", "her",
))

# ── 4 · CORRECTION / RECONCILIATION (correcting a fact, or deferring an item) ─
_CORRECTION = (
    "actually its", "actually it", "no its", "no it", "thats not it", "i said", "i meant",
    "rather than", "not that its", "instead its", "correction",
)
_RECONCILE = (
    "i already did", "already did that", "did it yesterday", "did that yesterday",
    "i did that", "thats canceled", "is canceled", "not today", "did it this morning",
    "already done", "i finished that", "i took care of that", "handled that already",
)

# ── 5 · REASONING MODE (struggle / diagnosis / decision within a subject) ────
# Domain-AGNOSTIC (no domain words) — the KIND of thinking, not the topic.
_STRUGGLE = (
    "hard time", "having trouble", "cant seem to", "cannot seem to", "struggling with",
    "stuck on", "stuck at", "plateau", "plateaued", "stalled", "not working", "isnt working",
    "not moving", "wont budge", "losing steam", "lost motivation", "motivation isnt",
    "burned out", "burnt out", "weird lately", "off lately", "not like before",
    "dont understand why", "cant figure out", "why isnt", "why arent", "why cant i",
    "why do i keep", "keeps happening", "not falling off",
)
_DECISION = (
    "should i", "is it worth", "worth it", "thinking of dropping", "thinking about dropping",
    "give up on", "should i keep", "should i quit", "do i keep going", "is it time to",
    "call it a night", "call it a day",
)

# ── 6 · RETRIEVAL (a NEW deterministic fact request — form, not domain) ──────
_RETRIEVAL_STARTS = (
    "how much", "how many", "what is my", "whats my", "what was my", "what did i",
    "when did i", "did i", "have i", "what are my", "how long did i", "how many times",
    "what's my", "when was my", "do i have",
)

# ── 7 · ORIENTATION / BRIEFING (greeting, check-in, "what do I need to know") ─
_GREETING = (
    "good morning", "good afternoon", "good evening", "good day", "morning beth",
    "evening beth", "afternoon beth", "hey beth", "hi beth", "hello beth",
)
_GREETING_EXACT = frozenset(("morning", "gm", "hey", "hi", "hello", "hiya", "howdy",
                             "good morning", "good evening", "good afternoon"))
_AGENDA = (
    "what do i need to know", "brief me", "whats on my plate", "what's on my plate",
    "hows my day", "how is my day", "plan my day", "plan the day", "whats next",
    "what's next", "what should i do next", "where do i stand", "give me a briefing",
    "catch me up", "how am i doing", "wrap up my day", "close out my day",
)

# ── 8 · GENERAL KNOWLEDGE (external; no personal reference) ───────────────────
_GENERAL_STARTS = (
    "who is", "who was", "what is a", "what is the", "what are the", "how does",
    "how do you", "whats the difference", "what's the difference", "define ", "explain ",
    "tell me about", "when did the", "where is the",
)


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _has(n, cues):
    return any(c in n for c in cues)


def classify(message, *, has_prior=False, page_context=None):
    """Classify a turn's SPEECH ACT and the capability family that should own it. Shallow,
    deterministic, domain-agnostic; never raises (a classification failure must never break
    a turn — it degrades to a low-confidence fallback)."""
    try:
        n = re.sub(r"[’']", "", _norm(message))
        raw = _norm(message)
        words = n.split()
        is_question = "?" in (message or "") or (words and words[0] in (
            "what", "how", "when", "why", "where", "who", "which", "did", "do", "is",
            "are", "can", "could", "should", "have", "has"))

        # 1 · SCREEN
        if _has(n, _SCREEN_CUES):
            return Classification("screen", "screen", "high", "screen_cue")
        if page_context and _has(n, _SCREEN_DEICTIC):
            return Classification("screen", "screen", "medium", "screen_deictic")

        # 2 · META / REPAIR — a move ABOUT Beth's own prior turn.
        if _has(n, _GUIDANCE_CRITIQUE):
            return Classification("meta", "repair", "high", "guidance_critique")
        if has_prior and (_has(n, _PRIOR_TURN_REF) or _has(n, _META_CORRECTION)):
            return Classification("meta", "repair", "high", "prior_turn_ref")
        if has_prior and _has(n, _FACT_CRITIQUE):
            return Classification("meta", "repair", "medium", "fact_critique")

        # 3 · CONTINUATION — an elliptical/referential follow-up to the active thread.
        if has_prior:
            bare = n.rstrip("?.! ")
            if bare in _BARE_FOLLOWUPS or _has(n, _CONTINUATION_CUES):
                return Classification("continuation", "continuation", "medium", "followup_cue")
            toks = set(re.findall(r"[a-z]+", n))
            if (toks & _REFERENTIAL) and len(words) <= 12 and "my " not in raw:
                return Classification("continuation", "continuation", "low", "referential")

        # 4 · CORRECTION / RECONCILIATION
        if _has(n, _RECONCILE):
            return Classification("correction", "correction", "high", "reconcile")
        if _has(n, _CORRECTION):
            return Classification("correction", "correction", "medium", "correction")

        # 5 · REASONING MODE (struggle / diagnosis / decision)
        if _has(n, _STRUGGLE):
            return Classification("reasoning_mode", "reasoning_mode", "medium", "struggle")
        if _has(n, _DECISION):
            return Classification("reasoning_mode", "reasoning_mode", "medium", "decision")

        # 6 · RETRIEVAL — a new deterministic fact request (interrogative + personal).
        if any(n.startswith(s) for s in _RETRIEVAL_STARTS):
            return Classification("retrieval", "retrieval", "high", "retrieval_start")
        if is_question and (" my " in f" {n} " or n.startswith("my ")):
            return Classification("retrieval", "retrieval", "medium", "personal_question")

        # 7 · ORIENTATION / BRIEFING
        if n in _GREETING_EXACT or any(n.startswith(g) or (" " + g) in n for g in _GREETING):
            return Classification("orientation", "orientation", "high", "greeting")
        if _has(n, _AGENDA):
            return Classification("orientation", "orientation", "high", "agenda")

        # 8 · GENERAL KNOWLEDGE — external, no personal reference.
        if any(n.startswith(s) for s in _GENERAL_STARTS) and " my " not in f" {n} ":
            return Classification("general", "general", "medium", "general_start")

        # 9 · FALLBACK — nothing grounded matched.
        return Classification("fallback", "fallback", "low", "none")
    except Exception:
        logger.warning("classifier.classify failed", exc_info=True)
        return Classification("fallback", "fallback", "low", "error")


# ── Map an ACTUAL winning lane → its speech-act family, so the shadow log can record
# whether the router agreed with the Classifier. Uses the specific result lane when
# available (e.g. 'conversation_repair'), falling back to the registry name. Metadata only.
_LANE_FAMILY = {
    "page_reference": "screen",
    "conversation_repair": "meta", "temporal": "meta",
    "why_explainer": "continuation", "referential": "continuation",
    "general_continuity": "continuation", "mission": "continuation",
    "correction": "correction", "reconciliation": "correction",
    "priority_correction": "correction",
    "self_report": "reasoning_mode", "decision_support": "reasoning_mode",
    "diagnostic": "reasoning_mode", "problem_solving": "reasoning_mode",
    "thinking_partner": "reasoning_mode", "goals_checkin": "reasoning_mode",
    "executive_risk": "reasoning_mode", "executive_opportunity": "reasoning_mode",
    "executive_pattern": "reasoning_mode",
    "sleep_history": "retrieval", "weight_history": "retrieval",
    "workout_history": "retrieval", "foundational_facts": "retrieval",
    "clarification": "retrieval", "clarification_reply": "retrieval",
    "why_explainer_fact": "retrieval",
    "conversation_checkin": "orientation", "conversation_brief": "orientation",
    "day_continuity": "orientation", "next_rhythm": "orientation",
    "priority_now": "orientation", "cos_briefing": "orientation",
    "conversation_planner": "orientation",
    "general_conversation": "general",
    "tool_loop_fallback": "fallback",
    # 'personal_reasoning' resolves to a reasoning/retrieval answer in practice.
    "personal_reasoning": "reasoning_mode",
}


def owner_family(lane):
    """The speech-act family a winning lane belongs to (for shadow agreement logging).
    Returns 'unknown' for an unmapped lane — never raises."""
    return _LANE_FAMILY.get(lane or "", "unknown")
