# ==============================================================================
# File: apps/ai/chatgpt_cos/p25_classifier.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P25 Personal Truth First — SHADOW classifier (instrumentation only).
# ==============================================================================
"""
P25 — Personal Truth First, SHADOW classifier.

`classify_request` decides whether a request needs Danny's personal WLJ truth:
    PERSONAL   — needs WLJ truth (retrieve + reason over it)
    EXTERNAL   — general knowledge, no personal truth
    MIXED      — WLJ truth grounds a general answer
    AMBIGUOUS  — can't tell -> clarify rather than guess

**SHADOW ONLY.** Nothing here changes routing or behavior. `log_p25_shadow`
emits one telemetry line per request comparing the *current* lane outcome to the
P25 classification so we can prove accuracy on real traffic before activation
(Phase 3). Deterministic-first — it reuses the SAME predicates the live lanes
already use (no LLM, no SAE warm, no side effects). See
docs/BETH_P25_PERSONAL_TRUTH_FIRST.md.
"""

import logging

logger = logging.getLogger("apps.ai.chatgpt_cos")

# Map the current live lane outcome -> the P25 class it implies, so we can log
# agreement. MIXED has no current-architecture equivalent, so a shadow MIXED is
# an EXPECTED disagreement (it marks where P25 would change behavior).
LANE_TO_P25 = {
    "foundational_facts": "PERSONAL",
    "personal_reasoning": "PERSONAL",
    "next_rhythm": "PERSONAL",
    "clarification_reply": "PERSONAL",     # resolving a personal clarification
    "clarification": "AMBIGUOUS",
    "general_conversation": "EXTERNAL",
    "tool_loop": "PERSONAL",               # the personal catch-all today
}

_EXPLICIT_GENERAL = ("in general", "generally", "most people", "for most",
                     "on average", "typically")
_ADVICE = ("should i", "good for me", "bad for me", "recommend", "is it ok",
           "is it okay", "what's the best", "whats the best")


def classify_request(message, user=None, conversation=None):
    """Return {classification, confidence, signal}. Deterministic; no LLM."""
    # Reuse the live lanes' deterministic predicates (no circular import: lanes
    # does not import this module).
    from apps.ai.chatgpt_cos.lanes import (
        _DOMAIN_WORDS, _NEXT_RHYTHM_SIGNALS, _PERSONAL_PRONOUNS,
        _looks_general, _normalize, clarify,
    )

    norm = _normalize(message)
    if not norm:
        return {"classification": "AMBIGUOUS", "confidence": 0.30, "signal": "empty"}

    tokens = set(norm.split())
    pronoun = bool(tokens & _PERSONAL_PRONOUNS)
    domain = any(d in norm for d in _DOMAIN_WORDS)
    rhythm = any(s in norm for s in _NEXT_RHYTHM_SIGNALS)
    personal_shape = (
        rhythm or "review my" in norm or ("my " in norm and domain)
    )
    advice = (any(a in norm for a in _ADVICE)
              or ("best" in tokens and "for me" in norm))
    trig = clarify(message)

    # Ordered SEMANTIC rules (this is the explicit gate — NOT lane order).
    if trig is not None:
        return {"classification": "AMBIGUOUS", "confidence": 0.95,
                "signal": "ambiguity_trigger:" + trig.get("ambiguity_type", "?")}
    if any(g in norm for g in _EXPLICIT_GENERAL):
        return {"classification": "EXTERNAL", "confidence": 0.90,
                "signal": "explicit_general"}
    if personal_shape:
        return {"classification": "PERSONAL", "confidence": 0.92,
                "signal": "personal_shape"}
    if advice and (pronoun or domain):
        return {"classification": "MIXED", "confidence": 0.80,
                "signal": "advice_personal"}
    if pronoun or domain:
        return {"classification": "PERSONAL", "confidence": 0.90,
                "signal": "personal_marker"}
    if _looks_general(message):
        return {"classification": "EXTERNAL", "confidence": 0.90,
                "signal": "general_shape"}
    return {"classification": "AMBIGUOUS", "confidence": 0.40,
            "signal": "unclassified"}


def log_p25_shadow(message, user=None, conversation=None, current_lane="tool_loop"):
    """Emit one shadow-comparison line. Never raises, never affects routing."""
    try:
        r = classify_request(message, user, conversation)
        current_p25 = LANE_TO_P25.get(current_lane, "PERSONAL")
        agree = (r["classification"] == current_p25)
        logger.info(
            "BETH_P25_SHADOW current_lane=%s current_p25=%s shadow_class=%s "
            "confidence=%.2f signal=%s agree=%s qlen=%d",
            current_lane, current_p25, r["classification"], r["confidence"],
            r["signal"], agree, len(message or ""),
        )
    except Exception:
        logger.warning("BETH_P25_SHADOW failed", exc_info=True)
