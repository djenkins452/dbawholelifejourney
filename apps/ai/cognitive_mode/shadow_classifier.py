"""Shadow cognitive-mode classifier (Phase 0).

A pure, deterministic, rule-based classifier: message -> predicted mode/domain.

Design constraints:
  - NO LLM call (we are not adding latency/cost to live traffic).
  - NO side effects, NO DB, NO Django imports — importable from tests bare.
  - Its job is to MEASURE, not to be the final production classifier.

It must be auditable: every prediction carries a short `reason` trace. Mode is the
PRIMARY signal we score (>=85% on the golden corpus). Domain is secondary and is
genuinely hard on context-dependent follow-ups (e.g. "evaluate my trend" with no
domain token); it is reported separately, not gated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .taxonomy import Mode, Domain, package_for


@dataclass
class ModePrediction:
    mode: str
    domain: object = None          # str | None
    coach_tail: bool = False
    confidence: float = 0.5
    reason: str = ""
    package_needed: list = field(default_factory=list)

    def as_log_dict(self) -> dict:
        return {
            "predicted_mode": self.mode,
            "predicted_domain": self.domain,
            "coach_tail": self.coach_tail,
            "mode_confidence": round(self.confidence, 3),
            "mode_reason": self.reason[:200],
            "package_needed": list(self.package_needed),
        }


# ---------------------------------------------------------------------------
# Signal vocabularies
# ---------------------------------------------------------------------------

_DOMAIN_TOKENS = [
    (Domain.GLUCOSE, ("glucose", "blood sugar", "blood glucose", "a1c", "cgm", "mg/dl")),
    (Domain.WEIGHT, ("weight", "weigh", "weighed", "pounds", " lbs", "the scale")),
    (Domain.BODY_COMPOSITION, ("body measurement", "measurements", "body fat",
                               "body composition", "waist", "bmi", "lean mass",
                               "muscle mass")),
    (Domain.NUTRITION, ("protein", "calorie", "calories", "macro", "macros", "carbs",
                        "carbohydrate", "fiber", "nutrition", "sugar intake")),
    (Domain.INTAKE, ("perfect amino", "supplement", "medication", "medicine",
                     "my meds", "the pill", "vitamin")),
    (Domain.FITNESS, ("workout", "exercise", "lifting", "cardio", "training",
                      "my reps", "my sets", "squat", "deadlift")),
    (Domain.SLEEP, ("sleep", "slept", "rest", "recovery")),
    (Domain.JOURNAL, ("journal", "mood", "journaling")),
    (Domain.FAITH, ("prayer", "scripture", "bible", "faith", "devotion")),
    (Domain.FINANCE, ("net worth", "spending", "budget", "expenses", "income")),
    (Domain.TASKS, ("task", "to-do", "to do list", "my tasks")),
]

_REFLECT_PHRASES = (
    "i feel", "i've been feeling", "ive been feeling", "feeling off", "feel off",
    "feel like myself", "feel disconnected", "feeling disconnected", "my mood",
    "what do you notice in my journal", "notice in my journaling",
    "living my values", "feel stuck", "feeling stuck", "feel anxious", "feel down",
)

_EXECUTE_PHRASES = (
    "what should i do next", "what should i do right now", "what should i do now",
    "what do i do next", "what's next", "whats next", "what now",
    "biggest risk", "what should i fix", "what's most broken", "whats most broken",
    "best use of", "next hour", "prioritize", "what's the priority",
    "what should i focus on next", "what's the best use",
)

# Strong, explicit judgment/interpretation signals -> ANALYZE.
_STRONG_ANALYZE_PHRASES = (
    "what do you think", "what are your thoughts", "your thoughts on", "thoughts on",
    "evaluate", "assess my", "analyze my", "what patterns", "any patterns",
    "do you notice", "what do you notice", "should i be worried", "worried about",
    "am i doing better", "am i doing worse", "how am i trending", "my trend",
    "how's my trend", "hows my trend", "what stands out", "read on my",
    "make of my", "interpret my",
)

# Soft analyze signals (broad self-assessment) -> ANALYZE if not caught as Retrieve.
_SOFT_ANALYZE_PHRASES = (
    "how am i doing", "how have i been doing", "how have i been", "how have i done",
    "how did i do", "am i on track", "where do i need", "where should i",
    "what areas", "which areas", "overall how", "in general how", "am i improving",
    "how's it going with my", "hows it going with my",
)

# Coaching tail -> recommendation appended to an Analyze. Measured, not a 5th lane.
_COACH_PHRASES = (
    "need to be doing", "should i change", "change anything", "do i need to",
    "push harder", "slow down", "doing better", "do better", "be doing differently",
    "anything differently", "should i adjust", "what should i adjust",
    "need to improve", "do i need to be doing", "should i be doing anything",
)

_POINT_VERBS = (
    "what is", "what's my", "whats my", "what was", "what were",
    "latest", "current", "currently", "how much", "how many",
    "when was", "when did", "show me", "tell me my", "give me my",
)

_TIMEPOINT_TOKENS = (
    "today", "right now", " now", "this morning", "tonight", "currently",
    "last", "most recent", "this week",
)

_HISTORY_RE = re.compile(r"\b(history|over time|past (?:month|week|few months|year))\b")


def _normalize(message: str) -> str:
    m = (message or "").lower().strip()
    m = m.replace("’", "'")
    m = re.sub(r"\s+", " ", m)
    return m


def _detect_domain(m: str):
    for domain, tokens in _DOMAIN_TOKENS:
        if any(t in m for t in tokens):
            return domain
    return Domain.NONE


def _detect_coach_tail(m: str) -> bool:
    return any(p in m for p in _COACH_PHRASES)


def _is_reflect(m: str) -> bool:
    return any(p in m for p in _REFLECT_PHRASES)


def _is_execute(m: str) -> bool:
    return any(p in m for p in _EXECUTE_PHRASES)


def _is_provenance(m: str) -> bool:
    if "coming from" in m or "come from" in m or "comes from" in m:
        return True
    if ("where is" in m or "where did" in m or "where does" in m) and "from" in m:
        return True
    return False


def _is_strong_analyze(m: str) -> bool:
    if any(p in m for p in _STRONG_ANALYZE_PHRASES):
        return True
    if _HISTORY_RE.search(m) and ("what" in m or "how" in m or "my" in m):
        return True
    return False


def _is_point_retrieve(m: str, domain) -> bool:
    # Comparison/delta lookups ("compare X to last time") -> grounded snapshot.
    if ("compare" in m or "difference" in m or "differences" in m or "vs " in m) and (
        "last time" in m or "last" in m or "previous" in m or "before" in m
    ):
        return True
    has_point_verb = any(v in m for v in _POINT_VERBS)
    has_timepoint = any(t in m for t in _TIMEPOINT_TOKENS)
    if has_point_verb and domain:
        return True
    # "how am I doing on protein today" — domain + concrete timepoint = point lookup.
    if domain and has_timepoint:
        return True
    return False


def _is_soft_analyze(m: str, coach_tail: bool) -> bool:
    if any(p in m for p in _SOFT_ANALYZE_PHRASES):
        return True
    if coach_tail:
        return True
    return False


def classify(message: str, user=None, page_context=None) -> ModePrediction:
    """Predict the cognitive mode for a message. Pure function.

    `user` / `page_context` are accepted for interface stability (the eventual
    production classifier may use page domain hints) but are NOT required and are
    unused in Phase 0 to keep the instrument deterministic and testable.
    """
    m = _normalize(message)
    domain = _detect_domain(m)
    coach_tail = _detect_coach_tail(m)

    def _p(mode, dom, conf, reason):
        return ModePrediction(
            mode=mode,
            domain=dom,
            coach_tail=coach_tail and mode == Mode.ANALYZE,
            confidence=conf,
            reason=reason,
            package_needed=package_for(mode, dom),
        )

    if not m:
        return _p(Mode.UNKNOWN, None, 0.2, "empty message")

    # Order matters: most specific / least ambiguous first.
    if _is_reflect(m):
        return _p(Mode.REFLECT, domain or Domain.JOURNAL, 0.9, "reflect: inner-state phrase")

    if _is_execute(m):
        return _p(Mode.EXECUTE, None, 0.9, "execute: next-action/risk/fix phrase")

    if _is_provenance(m):
        return _p(Mode.RETRIEVE, domain or Domain.INTAKE, 0.85, "retrieve: provenance phrase")

    if _is_strong_analyze(m):
        return _p(Mode.ANALYZE, domain, 0.9, "analyze: explicit judgment/interpretation verb")

    if _is_point_retrieve(m, domain):
        return _p(Mode.RETRIEVE, domain, 0.85, "retrieve: point-fact verb/timepoint/compare + domain")

    if _is_soft_analyze(m, coach_tail):
        return _p(Mode.ANALYZE, domain or Domain.CROSS_DOMAIN, 0.7,
                  "analyze: broad self-assessment" + (" + coach tail" if coach_tail else ""))

    return _p(Mode.UNKNOWN, domain, 0.45, "no confident mode signal")
