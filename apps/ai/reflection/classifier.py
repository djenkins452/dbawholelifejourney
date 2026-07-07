# ==============================================================================
# File: apps/ai/reflection/classifier.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic Executive Reflection classifier (Phase 4).
# ==============================================================================
"""
DETERMINISTIC assessment + failure classification. No LLM: the disposition is
COMPOSED from evidence, never narrated into existence (WLJ Law 2).

Order of operations mirrors the ratified lifecycle:
  1. ASSESS      — outcome verdict + trust delta ("was I successful?")
  2. CLASSIFY    — failure LOCUS ("why / where?"), only when something went wrong

The load-bearing rule (P2/P3): a correction that touches a TRUTH-BACKED domain is
checked FIRST and is NEVER learnable — it routes to an Executive Improvement
Opportunity regardless of what the deterministic source says (missing, stale, or
wrong). Only communication/preference signals, with truth provably not implicated,
are eligible to learn. Everything else defaults to insufficient-evidence.
"""

import re

# --- Assessment cue sets ------------------------------------------------------
_POSITIVE = (
    "thank", "thanks", "perfect", "exactly", "that helped", "that was helpful",
    "helpful", "great", "love it", "appreciate", "well done", "nailed it",
    "spot on", "makes sense", "good call",
)
_NEGATIVE = (
    "not helpful", "didnt help", "did not help", "unhelpful", "not what i",
    "thats not", "that isnt", "frustrat", "useless", "you missed", "not right",
)

# --- Truth-backed domains: a correction about these is NEVER learnable ---------
# Reuse the correction lane's curated word-sets so detection stays consistent.
from apps.ai.chatgpt_cos.correction import _WORKOUT_WORDS, _PROTEIN_WORDS

_TRUTH_DOMAINS = {
    "workout": _WORKOUT_WORDS,
    "nutrition": _PROTEIN_WORDS,
    "schedule": ("schedule", "calendar", "appointment", "meeting", "event",
                 "agenda", "booked"),
    "medication": ("medication", "meds", "dose", "pill", "prescription",
                   "insulin", " med "),
    "sleep": ("sleep", "slept", "bedtime", "woke", "rem", "hours of sleep"),
    "weight": ("weight", "weigh", "lbs", "pounds", " kg", "body fat"),
    "steps": ("steps", "step count", "distance walked"),
    "finance": ("budget", "spent", "balance", "transaction", "account", "bill"),
    "task": ("task", "due", "overdue", "deadline", "to do", "todo"),
}

# --- Communication signals (style / tone / format / address) — learnable -------
_COMMUNICATION = (
    "call me", "stop calling", "dont call me", "do not call me", "dont say",
    "stop saying", "too formal", "too long", "too short", "too wordy", "tone",
    "dont use the word", "stop using", "be brief", "keep it short", "less detail",
    "one at a time", "dont list", "dont address me",
)

# --- Preference signals (personalization) — learnable -------------------------
_PREFERENCE = (
    "i prefer", "id rather", "i would rather", "i like it when", "i dont like when",
    "use metric", "use imperial", "in celsius", "in fahrenheit", "always show me",
    "always give me", "i want you to always", "from now on", "please always",
    "please dont always", "going forward",
)


def _norm(s):
    """Lowercase; strip apostrophes; normalize separators (mirrors correction.py)."""
    s = re.sub(r"[’']", "", (s or "").lower())
    return re.sub(r"[\-/]", " ", re.sub(r"\s+", " ", s)).strip()


def _first_hit(n, cues):
    for c in cues:
        if c in n:
            return c
    return ""


def assess(message, response_text, is_correction):
    """(outcome, trust_delta). Deterministic. 'Was I successful?' before 'why?'."""
    n = _norm(message)
    if is_correction or any(c in n for c in _NEGATIVE):
        return "failure", "decreased"
    if any(c in n for c in _POSITIVE):
        return "success", "increased"
    return "neutral", "maintained"


def _truth_domain(n):
    for domain, words in _TRUTH_DOMAINS.items():
        if any(w in n for w in words):
            return domain
    return None


def _agreement_check(user, domain, n):
    """Re-read the deterministic source for `domain` and compare to the user's
    correction. Returns (functional_locus, engineering_category, evidence).

    - source missing            -> truth_retrieval / state       (missing state)
    - source present & AGREES    -> reasoning / pipeline           (truth was there; Beth didn't use it)
    - source present & DISAGREES -> truth_retrieval / serialization (stale/wrong truth)
    - no accessor wired          -> truth_retrieval / retrieval     (unverifiable; still not learnable)
    """
    if domain == "workout":
        try:
            from apps.ai.chatgpt_cos.day_truth import todays_planned_workout
            planned = todays_planned_workout(user)
        except Exception:
            planned = None
        if not planned or not planned.get("type"):
            return "truth_retrieval", "state", {
                "source": "todays_planned_workout", "value": None,
                "note": "no deterministic workout for today",
            }
        stype = (planned.get("type") or "").lower()
        # Negation-aware: a correction like "cardio not strength" contains BOTH
        # terms, so a bare substring test is wrong. The source AGREES only when its
        # value is present AND not explicitly negated by the user.
        negated = bool(stype) and (f"not {stype}" in n)
        present = bool(stype) and (stype in n)
        if present and not negated:
            return "reasoning", "pipeline", {
                "source": "todays_planned_workout", "value": stype, "agrees": True,
                "note": "truth was available; Beth reasoned past it",
            }
        return "truth_retrieval", "serialization", {
            "source": "todays_planned_workout", "value": stype, "agrees": False,
            "note": "deterministic source disagrees with the user (stale/wrong)",
        }
    # Truth-backed domain with no wired accessor: unverifiable, but STILL a
    # deterministic-faculty concern — not learnable.
    return "truth_retrieval", "retrieval", {
        "source": None, "domain": domain,
        "note": "truth-domain correction with no deterministic accessor to verify",
    }


def _result(outcome, trust, locus, category, disposition, topic, evidence, conf):
    return {
        "outcome": outcome,
        "trust_delta": trust,
        "locus": locus,
        "engineering_category": category,
        "disposition": disposition,
        "topic": topic,
        "evidence": dict(evidence or {}),
        "confidence": round(float(conf), 3),
    }


def classify(user, message, response_text, is_correction):
    """Assess then classify. Returns a disposition dict (see _result).

    Precedence guarantees the safety property: truth-domain corrections win over
    any style/preference cue, so a correction that even MENTIONS a truth-backed
    domain can never be learned — it becomes an EIO (P3).
    """
    n = _norm(message)
    outcome, trust = assess(message, response_text, is_correction)
    corrective = is_correction or trust == "decreased"

    # 1) TRUTH / REASONING / EXECUTION — never learnable. Checked FIRST.
    if corrective:
        domain = _truth_domain(n)
        if domain:
            locus, category, evidence = _agreement_check(user, domain, n)
            evidence["user_message"] = (message or "")[:500]
            return _result(outcome, trust, locus, category, "eio", domain,
                           evidence, 0.8)

    # 2) COMMUNICATION (style/tone/address) — learnable, bounded.
    if any(c in n for c in _COMMUNICATION):
        return _result(outcome, trust, "communication", "", "learn",
                       "communication",
                       {"signal": "communication", "phrase": _first_hit(n, _COMMUNICATION)},
                       0.7)

    # 3) PREFERENCE (personalization) — learnable, bounded.
    if any(c in n for c in _PREFERENCE):
        return _result(outcome, trust, "preference", "", "learn", "preference",
                       {"signal": "preference", "phrase": _first_hit(n, _PREFERENCE)},
                       0.7)

    # 4) Positive outcome, nothing to fix -> reinforce.
    if outcome == "success":
        return _result(outcome, trust, "none", "", "reinforce", "", {}, 0.7)

    # 5) A failure we cannot localize -> honest default. No learning, no EIO.
    if corrective:
        return _result(outcome, trust, "indeterminate", "", "insufficient_evidence",
                       "", {}, 0.3)

    # 6) Unremarkable turn.
    return _result(outcome, trust, "none", "", "observe", "", {}, 0.5)
