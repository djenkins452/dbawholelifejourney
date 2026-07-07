# ==============================================================================
# File: apps/ai/chatgpt_cos/reasoning_mode.py
# Capability: CONVERSATIONAL INTENT EVOLUTION — recognize when the KIND of reasoning the
# user needs changes DURING a conversation, while the conversational mission stays the
# same. A Chief of Staff knows a discussion naturally moves along a ladder:
#
#     STATUS  →  DIAGNOSIS  →  PLANNING  →  DECISION
#
# The user never announces these transitions ("How's my France goal?" → "I'm having a
# hard time breaking 289" is Status → Diagnosis, same mission). Beth must recognize the
# shift and change her REASONING MODE — pivot from a status summary into investigation —
# without losing the mission.
#
# This module is the thin, DETERMINISTIC, DOMAIN-AGNOSTIC classifier of that mode. The
# cues are linguistic (struggle / plateau / confusion / unexpected-change), never domain
# words, so the same classifier serves goals, work, relationships, faith, finances,
# projects, and habits equally.
#
# LADDER ARCHITECTURE, INCREMENTAL ACTIVATION: all four modes are modeled here so the
# ladder exists cleanly, but only the STATUS → DIAGNOSIS transition is WIRED LIVE (the
# `_diagnostic_lane` consumes DIAGNOSIS). PLANNING and DECISION are recognized and
# phase-tagged below — SCAFFOLDED, not yet routed — to be activated one at a time after
# Diagnosis is validated through production conversations (low blast radius; one reasoning
# transition strengthened at a time).
# ==============================================================================
import re

STATUS = "status"          # "how am I doing?" — handled by the existing status/brief lanes
DIAGNOSIS = "diagnosis"    # "help me understand what changed" — WIRED LIVE (diagnostic lane)
PLANNING = "planning"      # "what should I do about it?" — SCAFFOLDED (Phase: after Diagnosis)
DECISION = "decision"      # "should I do X or Y?"        — SCAFFOLDED (Phase: after Planning)

# ── DIAGNOSIS (LIVE) ─────────────────────────────────────────────────────────
# The user has introduced a PROBLEM TO UNDERSTAND: struggle, a plateau/slowdown, an
# unexpected result or change-from-before, confusion/why, or lost motivation. This is the
# signal to stop reporting status and start investigating. Domain-agnostic by design.
_DIAGNOSIS_CUES = (
    # struggle
    "hard time", "a hard time", "having trouble", "having a hard time", "struggling",
    "cant seem to", "cant get", "difficult to", "im stuck", "stuck at", "stuck on",
    "stuck around", "cant break", "cant get past", "cant get below", "cant get under",
    # plateau / slowdown
    "not falling off", "not coming off", "not dropping", "wont budge", "not budging",
    "not moving", "not going down", "plateau", "plateaued", "stalled", "stalling",
    "slowing down", "slowed down", "flatlined", "stopped losing", "not losing",
    "not making progress", "spinning my wheels", "no progress", "stopped making",
    "wont come off", "wont go down", "not shifting",
    # unexpected / change vs before
    "weird lately", "off lately", "not like before", "unlike before", "like the beginning",
    "like the start", "used to be", "used to come", "used to fall", "used to drop",
    "harder than it used to", "different than before", "different from before",
    "something changed", "not the same", "changed lately", "acting up", "acting weird",
    # confusion / why
    "dont understand why", "cant figure out", "not sure why", "no idea why",
    "whats going on with", "why is my", "why isnt", "why am i not", "why wont",
    "why has", "why did my", "whats happening with", "what happened to my",
    "cant work out why", "makes no sense",
    # motivation / slipping
    "motivation isnt", "motivation is gone", "lost my motivation", "no motivation",
    "isnt there anymore", "slipping", "losing steam", "burned out on", "burnt out on",
    "lost my drive", "cant stay consistent",
)

# ── PLANNING (SCAFFOLDED — NOT wired live) ───────────────────────────────────
# "OK, so what do I do about it?" — the user has understood the problem and now wants a
# plan/action. Recognized for the ladder; NOT yet consumed. Promotion trigger: activate a
# planning lane once the Diagnosis transition is validated in production.
_PLANNING_CUES = (
    "what should i do", "what do i do about", "how do i fix", "how do i get past",
    "how do i break through", "whats the plan", "help me plan", "what would help",
    "how do i turn this around", "what can i change", "where do i start",
)

# ── DECISION (SCAFFOLDED — NOT wired live) ───────────────────────────────────
# "Should I do X or Y?" — a tradeoff/commitment. Recognized for the ladder; NOT yet
# consumed. Promotion trigger: activate after Planning is validated. (Note: an explicit
# voiced decision is already handled by the decision_support lane; this ladder rung is the
# conversational transition INTO deciding, to be wired when Planning lands.)
_DECISION_CUES = (
    "should i", "is it worth", "do you think i should", "which is better",
    "or should i", "worth it to", "better to", "i'm thinking of", "im thinking of",
)


def _norm(message):
    return re.sub(r"[’']", "", (message or "").strip().lower())


def classify_mode(message):
    """Return the reasoning MODE the message calls for — DIAGNOSIS / PLANNING / DECISION —
    or None when it carries no mode-transition signal (the implicit STATUS default, which
    the existing status/brief/reasoning lanes already handle unchanged).

    Only DIAGNOSIS is consumed downstream today; PLANNING/DECISION are returned for the
    ladder's completeness but are SCAFFOLDED — no lane acts on them yet."""
    n = _norm(message)
    if not n:
        return None
    if any(c in n for c in _DIAGNOSIS_CUES):
        return DIAGNOSIS
    if any(c in n for c in _PLANNING_CUES):
        return PLANNING       # scaffolded — recognized, not yet wired live
    if any(c in n for c in _DECISION_CUES):
        return DECISION       # scaffolded — recognized, not yet wired live
    return None


def is_diagnostic_shift(message):
    """True when the user has moved from status into DIAGNOSIS (the only transition wired
    live). A thin public predicate for the diagnostic lane."""
    return classify_mode(message) == DIAGNOSIS
