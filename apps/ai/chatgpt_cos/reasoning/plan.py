# ==============================================================================
# File: apps/ai/chatgpt_cos/reasoning/plan.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reasoning Lane — the structured Retrieval Plan + constrained vocab
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
Retrieval Plan — the Planner LLM's only output.

The planner UNDERSTANDS the request and emits a structured plan that names which
deterministic truth to retrieve. It never answers the user and never invents
truth. The vocabulary below is a closed set: anything the planner emits outside
it is dropped during parsing (the planner cannot fabricate truth sources).
"""

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Implemented reasoning intents (this milestone). The planner may also return
# "other" for anything not yet built — the engine then declines (falls through).
# Two domains are implemented: HEALTH (reference) and GOALS (domain #2). Each
# quartet is intentionally differentiated per the intent contracts.
HEALTH_IMPLEMENTED = ("biggest_health_risk", "overall_progress",
                      "health_focus_today", "health_concerns")
GOAL_IMPLEMENTED = ("biggest_goal_risk", "goals_progress",
                    "goals_focus_today", "goal_concerns",
                    # Differentiated goal intents — six distinct questions, six
                    # distinct answers (no more collapse to goals_progress).
                    "goal_on_track", "goal_why_priority", "goal_next_milestone",
                    "goal_failure_modes", "goal_confidence")
IMPLEMENTED_INTENTS = HEALTH_IMPLEMENTED + GOAL_IMPLEMENTED
ALLOWED_INTENTS = IMPLEMENTED_INTENTS + ("other",)

ALLOWED_RESPONSE_MODES = ("lookup", "reasoning", "mixed")
ALLOWED_URGENCY = ("low", "normal", "high")

# Closed vocabulary of truth sources the retrieval layer knows how to fetch.
ALLOWED_DOMAINS = (
    "health", "fitness", "nutrition", "goals", "faith", "tasks", "execution",
)
ALLOWED_TRUTH = (
    "risk_decision", "execution_decision", "fix_decision",
    "standing_context", "foundational_health",
    "health_state", "goals_state", "habits_state",
    "fitness_state", "nutrition_state",
)

# Single source of truth for intent -> (domain, required truth keys). Both the
# resilience planner (synthesize_plan) and the per-intent truth SCOPE in
# stages.py derive from this, so a new domain is registered in ONE place.
_HEALTH_REQUIRED = ("health_state", "foundational_health")
_GOALS_REQUIRED = ("goals_state", "habits_state")
INTENT_DOMAINS = {
    "biggest_health_risk": ("health", _HEALTH_REQUIRED),
    "overall_progress": ("health", _HEALTH_REQUIRED),
    "health_focus_today": ("health", _HEALTH_REQUIRED),
    "health_concerns": ("health", _HEALTH_REQUIRED),
    "biggest_goal_risk": ("goals", _GOALS_REQUIRED),
    "goals_progress": ("goals", _GOALS_REQUIRED),
    "goals_focus_today": ("goals", _GOALS_REQUIRED),
    "goal_concerns": ("goals", _GOALS_REQUIRED),
    "goal_on_track": ("goals", _GOALS_REQUIRED),
    "goal_why_priority": ("goals", _GOALS_REQUIRED),
    "goal_next_milestone": ("goals", _GOALS_REQUIRED),
    "goal_failure_modes": ("goals", _GOALS_REQUIRED),
    "goal_confidence": ("goals", _GOALS_REQUIRED),
}


@dataclass
class RetrievalPlan:
    intent: str
    response_mode: str
    domains: list
    required_truth: list
    optional_truth: list
    reasoning_style: str
    urgency: str
    confidence: float
    raw: dict = field(default_factory=dict)

    def as_dict(self):
        return {
            "intent": self.intent,
            "response_mode": self.response_mode,
            "domains": self.domains,
            "required_truth": self.required_truth,
            "optional_truth": self.optional_truth,
            "reasoning_style": self.reasoning_style,
            "urgency": self.urgency,
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------
# Resilience matcher (NOT the primary path): when the LLM planner is
# unavailable or misclassifies, route an implemented HEALTH reasoning question
# deterministically so the reasoning lane ALWAYS produces an answer and never
# falls through to the legacy tool loop. The LLM planner remains primary.
# ---------------------------------------------------------------------------
# Ordered MOST-SPECIFIC first — the matcher returns the first intent whose
# signals hit, so time/action cues and plural-survey cues are checked before the
# singular-superlative risk cues (which would otherwise swallow them). See
# docs/BETH_HEALTH_INTENT_CONTRACTS.md "Disambiguation".
_HEALTH_INTENT_SIGNALS = (
    # 1. Today / actionable → health_focus_today (time-bound action).
    ("health_focus_today", ("today", "right now what should i do",
                            "what to do first", "focus today", "do first today")),
    # 2. Plural survey → health_concerns (a ranked LIST, not a single priority).
    ("health_concerns", ("health concerns", "my concerns", "any concerns",
                         "concerns do i", "health issues", "what issues",
                         "what's off", "whats off", "list my health",
                         "anything wrong with my health")),
    # 3. Superlative single risk → biggest_health_risk (the ONE top priority).
    ("biggest_health_risk", ("biggest health risk", "biggest risk", "health risk",
                             "single biggest", "most important health",
                             "what's wrong", "whats wrong", "should i worry",
                             "worried about my health", "what needs attention",
                             "what to improve", "what should i focus on",
                             "biggest health concern", "main health concern",
                             "top health concern", "biggest concern", "health concern",
                             # health concern/risk/problem phrasing (P: deterministic
                             # capability gap — these fell to the tool loop with OpenAI
                             # down). WLJ owns health truth; these MUST route here.
                             "health issue", "concerns you most", "concern you most",
                             "what concerns you", "main health problem", "health problem",
                             "main problem", "watching with my health", "be watching",
                             "should i watch", "what should i watch", "what to watch",
                             "anything concerning", "concerning in my health",
                             "anything wrong", "anything off", "red flag", "warning sign")),
    # 4. Progress / status → overall_progress (executive summary / trajectory).
    ("overall_progress", ("how am i doing", "how am i tracking", "overall",
                          "on track", "progress", "health goals",
                          "doing with my health", "health summary",
                          "summary of my health", "summarize my health",
                          "my diabetes", "diabetes doing", "diabetes going",
                          "diabetes status", "blood sugar control", "my a1c",
                          "how's my health", "hows my health", "my health status")),
)


# Goal intent signals — goal-SPECIFIC cues only (every signal contains "goal"),
# so they never match a health-only message (health routing stays byte-identical)
# and a "health goals" phrase still routes to health (there is no bare "goals"
# signal). Ordered MOST-SPECIFIC first within the domain, mirroring health.
_GOAL_INTENT_SIGNALS = (
    # 1. Today / actionable → goals_focus_today (time-bound goal action).
    ("goals_focus_today", ("goal today", "goal to focus on", "which goal should i",
                           "what goal should i", "goal for today", "which goal today",
                           "goal to work on today", "advance a goal")),
    # 2. Plural survey → goal_concerns (a ranked LIST of slipping goals/habits).
    ("goal_concerns", ("goal concerns", "goals at risk", "goals am i behind",
                       "behind on my goals", "goals are slipping", "stalled goals",
                       "goals stalling", "which goals are", "what goals are wrong",
                       "problems with my goals")),
    # 3. Superlative single risk → biggest_goal_risk (the ONE goal most at risk).
    ("biggest_goal_risk", ("biggest goal risk", "biggest goal", "goal at risk",
                           "goal most at risk", "most important goal",
                           "which goal is at risk", "top goal risk",
                           "what goal needs")),
    # 4. Progress / status → goals_progress (executive summary / trajectory).
    ("goals_progress", ("how am i doing on my goals", "on my goals",
                        "with my goals", "my goals progress", "goal progress",
                        "goals progress", "how are my goals", "how's my goals",
                        "hows my goals", "tracking on my goals",
                        "on track with my goals", "doing on my goals",
                        "doing with my goals", "am i on track with my goals")),
)

# Goal signals are checked BEFORE health signals so a goal-specific phrase wins
# over a generic health cue (e.g. "how am I doing on my goals" → goals_progress,
# not overall_progress). Health-only messages match no goal signal, so existing
# health routing is unchanged.
_DOMAIN_INTENT_SIGNALS = _GOAL_INTENT_SIGNALS + _HEALTH_INTENT_SIGNALS


def deterministic_intent(message):
    """Best-effort deterministic match to an IMPLEMENTED intent, or None.

    Multi-domain (health + goals); goal-specific cues are checked first, then a
    MEANING-based foundational classifier so foundational CoS questions route even
    with no goal name and no planner/OpenAI. The LLM planner remains primary —
    this is the resilience path."""
    text = (message or "").lower()
    for intent, sigs in _DOMAIN_INTENT_SIGNALS:
        if intent in IMPLEMENTED_INTENTS and any(s in text for s in sigs):
            return intent
    foundational = _foundational_intent(message)
    if foundational in IMPLEMENTED_INTENTS:
        return foundational
    return None


# Backward-compatible alias (generalize-with-alias): existing callers/tests using
# the health-named function keep working; it now matches goal intents too.
deterministic_health_intent = deterministic_intent


# ---------------------------------------------------------------------------
# Named-goal PRE-ROUTER (runs BEFORE the planner — see engine.answer_reasoning_
# question). A question that references a named active goal, the mission, or uses
# "my mission"/"this goal"/"that goal" is OWNED by the Goals domain and must never
# be stolen by the health planner (root cause #1). Deterministic, gated on goal
# context + title length so it never captures an unrelated (e.g. health) question.
# ---------------------------------------------------------------------------
# Deictic references to a goal/mission that name no title but clearly point at one.
# Kept narrow on purpose: a bare "my goal" is excluded because phrases like "my
# goal weight" are HEALTH questions — only unambiguous goal/mission deixis qualifies.
_GOAL_DEICTIC = (
    "my mission", "this goal", "that goal", "this mission", "that mission",
    "the mission", "our mission",   # "mission" is goal-specific; "my/the goal" is
    # deliberately NOT here — it collides with "my goal weight" (health) and would
    # shadow the richer milestone phrasing in _foundational_goal_intent. A bare goal
    # reference is resolved by the distinctive-token path (framing-gated) instead.
    "how is my goal going", "how's my goal going", "hows my goal going",
    "how is my goal progressing", "how's my goal progressing",
)

# ---------------------------------------------------------------------------
# Goal IDENTITY resolution (P27 DC#1). Goal questions are recognized by goal
# IDENTITY before intent wording — not by matching the FULL title string. A
# distinctive token from an active goal's title ("France" from "France 2027 Family
# 18K Mission") identifies the goal; goal FRAMING (a progress/status/forward/risk
# cue) confirms it is a goal question, so a general question that merely mentions
# the token ("the capital of France") is NOT stolen. Generic/structural title
# words never identify a goal.
# ---------------------------------------------------------------------------
_TITLE_STOPWORDS = frozenset({
    "mission", "missions", "goal", "goals", "plan", "plans", "project", "projects",
    "target", "targets", "family", "personal", "life", "phase", "year", "years",
    "journey", "challenge", "vision", "objective", "milestone", "milestones",
    "the", "and", "for", "with", "your", "this", "that", "into", "from", "every",
})
_GOAL_FRAMING = (
    "going", "doing", "progress", "progressing", "status", "update", "tracking",
    "track", "on pace", "behind", "ahead", "forward", "leverage", "threat", "risk",
    "milestone", "confiden", "focus", "next step", "derail", "watch", "slipping",
    "priority", "achieve", "on track", "how is", "how's", "hows", "how am i doing",
    "move this", "move it", "goal", "mission", "succeed", "make it",
    "should i do", "do today", "do for", "work on", "next move", "advance",
)


def _distinctive_title_tokens(titles):
    """Identifying tokens from active goal titles — alphabetic, >=4 chars, not a
    generic/structural or domain-collision word. Pure."""
    toks = set()
    for t in titles or []:
        for w in re.findall(r"[a-z][a-z']{3,}", str(t or "").lower()):
            if w not in _TITLE_STOPWORDS and w not in _DOMAIN_COLLISION_WORDS:
                toks.add(w)
    return toks


def _has_goal_framing(text):
    return any(f in text for f in _GOAL_FRAMING)

# Length gate: a matched title must be at least this long to count (a 1–3 char
# title is too generic to safely own a question).
_MIN_TITLE_MATCH_LEN = 4

# A bare single-word title that collides with another domain's vocabulary (a goal
# literally named "Health"/"Sleep"/…) must NOT steal that domain's questions. A
# multi-word title that merely contains such a word still matches as a phrase.
_DOMAIN_COLLISION_WORDS = frozenset({
    "health", "weight", "sleep", "glucose", "fitness", "nutrition", "habits",
    "habit", "faith", "tasks", "task", "finance", "finances", "money",
})


def _infer_named_goal_intent(text):
    """Pick the goal intent for a message ALREADY known to be about a named goal.
    Six distinct intents — checked MOST-SPECIFIC first so e.g. 'next milestone'
    and 'why is this my priority' never collapse to goals_progress."""
    t = text
    # Confidence assessment.
    if any(k in t for k in ("how confident", "confident are you", "confidence",
                            "will i achieve", "will i hit", "will i make", "chances of",
                            "chance of", "likely to achieve", "odds of", "probability",
                            "going to make it")):
        return "goal_confidence"
    # Failure-mode analysis. (In a named-goal context, "fail"/"threat" is unambiguous.)
    # NOTE: checked BEFORE biggest_goal_risk so "biggest THREAT" is a failure-mode
    # question, not a single-risk question.
    if any(k in t for k in ("fail", "cause this", "cause the", "cause it to",
                            "go wrong", "derail", "what would stop", "what could stop",
                            "what might stop", "fall apart", "blow this", "give up on",
                            "threat", "threaten", "watch out for", "watch out", "jeopard",
                            "what could hurt", "knock me off")):
        return "goal_failure_modes"
    # Strategic rationale — why it's the priority.
    if ("why" in t and any(k in t for k in ("priority", "matter", "matters",
                                            "important", "highest", "top goal",
                                            "this goal", "this mission"))):
        return "goal_why_priority"
    # Next milestone / current phase only.
    if any(k in t for k in ("milestone", "next phase", "current phase", "next step in",
                            "what phase", "comes next", "next checkpoint",
                            "what's after", "whats after", "where should i be next")):
        return "goal_next_milestone"
    # Trajectory — on track / on pace / behind. ("behind" is a TRAJECTORY verdict,
    # not a slipping-concerns list.)
    if any(k in t for k in ("on track", "on pace", "on schedule", "behind schedule",
                            "still on track", "make it in time", "going to make it",
                            "will i finish in time", "behind", "am i behind",
                            "falling behind", "fallen behind", "keeping pace", "caught up")):
        return "goal_on_track"
    # Focus today / move-the-needle action.
    if any(k in t for k in ("what should i do", "focus on today", "do today",
                            "work on today", "action today", "next step today",
                            "what should i focus", "focus on", "focus for",
                            "what to focus", "where to focus", "work on", "what should i work",
                            "next move", "best move", "advance", "move the needle",
                            "highest leverage", "highest-leverage", "move this forward",
                            "move it forward")):
        return "goals_focus_today"
    # Single biggest risk.
    if any(k in t for k in ("biggest", "most at risk", "at risk", "worried",
                            "in trouble")):
        return "biggest_goal_risk"
    # Slipping / concerns. ("behind on" removed — trajectory is owned by on_track.)
    if any(k in t for k in ("concerns", "slipping", "stalling", "stalled",
                            "problems with", "drifting", "needs attention")):
        return "goal_concerns"
    # Default — progress summary.
    return "goals_progress"


# ---------------------------------------------------------------------------
# Foundational CoS questions classified by MEANING, not exact wording — so they
# ALWAYS route to a deterministic intent even with no goal name, no deictic, and
# no planner/OpenAI. These refer to the user's PRIMARY MISSION (goal) or health
# in general. Health-context words steer ambiguous phrases to health, not goals.
# ---------------------------------------------------------------------------
_HEALTH_CONTEXT_WORDS = ("health", "healthy", "physically", "physical", "weight",
                         "glucose", "blood sugar", "blood pressure", "sleep", "a1c",
                         "diabetes", "nutrition", "fitness")


def _foundational_goal_intent(text):
    """A GOAL intent for a foundational, mission-implicit question, or None. Gated
    so it never steals a health/general question."""
    t = (text or "").lower()
    health_ctx = any(w in t for w in _HEALTH_CONTEXT_WORDS)
    if any(k in t for k in ("next milestone", "next checkpoint", "next step toward",
                            "where should i be next", "what milestone", "which milestone",
                            "current milestone", "what's after", "whats after",
                            "what comes next in", "next phase of")):
        return "goal_next_milestone"
    if ("why" in t and any(k in t for k in ("priority", "matter", "matters", "important",
                                            "highest", "this goal", "this mission",
                                            "keep focusing", "keep working on"))):
        return "goal_why_priority"
    if any(k in t for k in ("how confident", "will i achieve", "will i make it",
                            "my odds", "odds of", "chances of", "chance of", "how likely",
                            "do you think i'll", "do you think i will", "going to make it",
                            "will i succeed", "will i be ready", "likely is success")):
        return "goal_confidence"
    if not health_ctx and any(k in t for k in ("on track", "on pace", "behind schedule",
                              "am i behind", "adjust the timeline", "make it in time",
                              "finish in time", "still okay for", "still ok for")):
        return "goal_on_track"
    if not health_ctx and any(k in t for k in ("biggest risk", "most at risk",
                              "worries you most", "what worries you", "goal needs the most")):
        return "biggest_goal_risk"
    # Failure analysis — "what should I watch out for", "what could derail this".
    if not health_ctx and any(k in t for k in ("watch out for", "watch for", "what to watch",
                              "could go wrong", "might go wrong", "could derail", "would derail",
                              "ways this could fail", "ways it could fail", "what would stop",
                              "what could stop", "could cause this to fail", "fall apart")):
        return "goal_failure_modes"
    # Move-the-needle action — "move this forward", "highest leverage action".
    if not health_ctx and any(k in t for k in ("move this forward", "move it forward",
                              "move forward on", "push this forward", "push it forward",
                              "move the needle", "highest leverage", "highest-leverage",
                              "biggest lever", "best use of my time on this",
                              "best next move", "how do i advance this")):
        return "goals_focus_today"
    if not health_ctx and any(k in t for k in ("which goals are slipping", "goals slipping",
                              "goals drifting", "goals need attention", "goals at risk")):
        return "goal_concerns"
    return None


def _foundational_intent(text):
    """A GOAL or HEALTH intent for a foundational question, or None. Used by the
    deterministic resilience path so these questions answer even with OpenAI down."""
    g = _foundational_goal_intent(text)
    if g:
        return g
    t = (text or "").lower()
    if any(k in t for k in ("how is my health", "how's my health", "hows my health",
                            "how healthy am i", "how am i doing physically",
                            "how am i physically", "how is my physical",
                            "my health right now", "how am i health wise",
                            "how's my physical health")):
        return "overall_progress"
    return None


def named_goal_intent(message, goal_titles, mission_title=None):
    """Deterministic pre-router decision (pure — no DB). Returns (intent, matched)
    where `intent` is a forced GOAL intent (or None) and `matched` is the title
    string that matched (or "<deictic>" / None). Backward-compatible: callers may
    use the truthiness of the returned intent.

    DEICTIC-FIRST: an unambiguous goal deictic ("my mission", "this goal", …) is
    OWNED by Goals and routes WITHOUT any title — goal deixis must not depend on
    titles existing (root cause: empty request-path snapshot). Title matching is
    the secondary path, length-gated and collision-guarded so it never steals an
    unrelated (e.g. health) question.
    """
    text = (message or "").lower().strip()
    if not text:
        return None, None

    # 1) Deictic — title-INDEPENDENT (must work with a cold/empty snapshot).
    if any(d in text for d in _GOAL_DEICTIC):
        return _infer_named_goal_intent(text), "<deictic>"

    # 2) Named-title match (secondary).
    titles = [str(t).strip() for t in (goal_titles or []) if t]
    if mission_title:
        titles.append(str(mission_title).strip())
    for t in titles:
        tl = t.lower()
        if len(tl) < _MIN_TITLE_MATCH_LEN:
            continue
        if " " not in tl and tl in _DOMAIN_COLLISION_WORDS:
            continue                     # bare domain word — never steal that domain
        if re.search(r"\b" + re.escape(tl) + r"\b", text):
            return _infer_named_goal_intent(text), t

    # 3) DISTINCTIVE-TOKEN identity (P27 DC#1) — a goal is referenced by a rare
    # identifying token from its title ("France", "France 2027 …") rather than the
    # full string, CONFIRMED by goal framing so a general mention is never stolen.
    if _has_goal_framing(text):
        for tok in _distinctive_title_tokens(titles):
            if re.search(r"\b" + re.escape(tok) + r"\b", text):
                return _infer_named_goal_intent(text), tok

    # 4) Foundational goal MEANING — a mission-implicit question ("what is my next
    # milestone?", "why is this my priority?", "how confident are you?") with no
    # name and no deictic. Title-independent and OpenAI-independent.
    fg = _foundational_goal_intent(text)
    if fg:
        return fg, "<meaning>"
    return None, None


def _active_goal_titles_db(user):
    """Lightweight canonical fallback: read active goal/mission titles DIRECTLY
    from the DB (titles only, one indexed query — a READ, never a recompute or SAE
    build; P24-compliant). Used only when the request-path snapshot has no titles.
    Returns (titles, mission_title)."""
    try:
        from apps.purpose.models import LifeGoal
        rows = list(LifeGoal.objects.filter(user=user, status="active")
                    .values_list("title", "is_primary_mission")[:25])
    except Exception:
        logger.warning("BETH_GOAL_ROUTE_DB_FALLBACK_FAILED user=%s",
                       getattr(user, "id", None), exc_info=True)
        return [], None
    titles = [t for t, _ in rows if t]
    mission_title = next((t for t, primary in rows if primary and t), None)
    return titles, mission_title


def preroute_named_goal(user, message):
    """Pre-router: a question that names an active goal/mission — or uses a goal
    deictic — is OWNED by Goals. Reads canonical titles READ-ONLY (snapshot first,
    then a lightweight DB title read if the snapshot is cold). Returns a forced
    GOAL intent or None. Fully instrumented (BETH_GOAL_ROUTE_*)."""
    if not message:
        return None
    uid = getattr(user, "id", None)
    logger.info("BETH_GOAL_ROUTE_START user=%s qlen=%d msg=%r",
                uid, len(message or ""), (message or "")[:140])

    # 1) Snapshot (warm, read-only).
    snap_status, snap_titles, mission_title = "error", [], None
    try:
        from apps.ai.cos_services import get_domain_state
        envelope = get_domain_state(user, "purpose")  # allow_build=False
        snap_status = envelope.get("status") if isinstance(envelope, dict) else "error"
        state = envelope.get("state") if isinstance(envelope, dict) else None
        state = state if isinstance(state, dict) else {}
        snap_titles = [t.get("title") for t in (state.get("active_titles") or [])
                       if isinstance(t, dict) and t.get("title")]
        mission = state.get("mission")
        mission_title = mission.get("title") if isinstance(mission, dict) else None
    except Exception:
        logger.warning("BETH_GOAL_ROUTE_STATE_FAILED user=%s", uid, exc_info=True)

    intent, matched = named_goal_intent(message, snap_titles, mission_title)

    # 2) DB title fallback — only if the snapshot gave us nothing to match on AND
    #    the deictic path didn't already resolve it.
    db_count = 0
    if intent is None and not snap_titles:
        db_titles, db_mission = _active_goal_titles_db(user)
        db_count = len(db_titles)
        if db_titles or db_mission:
            intent, matched = named_goal_intent(message, db_titles, db_mission)
            if intent is not None:
                logger.info(
                    "BETH_GOAL_ROUTE_FALLBACK user=%s db_titles=%d matched=%r intent=%s",
                    uid, db_count, matched, intent)

    if intent is not None:
        logger.info(
            "BETH_GOAL_ROUTE_RESULT user=%s fired=True snap_status=%s "
            "snap_titles=%d db_titles=%d matched=%r intent=%s",
            uid, snap_status, len(snap_titles), db_count, matched, intent)
        return intent

    logger.info(
        "BETH_GOAL_ROUTE_NO_MATCH user=%s fired=False snap_status=%s "
        "snap_titles=%d db_titles=%d", uid, snap_status, len(snap_titles), db_count)
    return None


def synthesize_plan(intent):
    """A domain-scoped RetrievalPlan for the resilience path, scoped by intent.

    Health intents map to the same domain + required_truth as before, so health
    behavior is byte-identical; goal intents map to goals truth."""
    domain, required = INTENT_DOMAINS.get(intent, ("health", _HEALTH_REQUIRED))
    return RetrievalPlan(
        intent=intent, response_mode="reasoning", domains=[domain],
        required_truth=list(required),
        optional_truth=[], reasoning_style="resilience_fallback",
        urgency="normal", confidence=0.0,
        raw={"source": "deterministic_fallback"},
    )


# Backward-compatible alias.
synthesize_health_plan = synthesize_plan


def _coerce_list(value, allowed):
    if not isinstance(value, list):
        return []
    # keep only known vocabulary — the planner cannot invent truth sources
    return [v for v in value if isinstance(v, str) and v in allowed]


def parse_plan(text):
    """Parse the planner's text into a validated RetrievalPlan, or None.

    Tolerant of code fences / prose around the JSON. Unknown intents/domains/
    truth keys are normalized or dropped — never trusted blindly."""
    if not text:
        return None
    raw = None
    # Strip code fences and grab the first {...} block.
    cleaned = re.sub(r"```(?:json)?", "", str(text)).strip()
    try:
        raw = json.loads(cleaned)
    except Exception:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            return None
        try:
            raw = json.loads(m.group(0))
        except Exception:
            return None
    if not isinstance(raw, dict):
        return None

    intent = raw.get("intent")
    if intent not in ALLOWED_INTENTS:
        intent = "other"
    mode = raw.get("response_mode")
    if mode not in ALLOWED_RESPONSE_MODES:
        mode = "reasoning"
    urgency = raw.get("urgency")
    if urgency not in ALLOWED_URGENCY:
        urgency = "normal"
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return RetrievalPlan(
        intent=intent,
        response_mode=mode,
        domains=_coerce_list(raw.get("domains"), ALLOWED_DOMAINS),
        required_truth=_coerce_list(raw.get("required_truth"), ALLOWED_TRUTH),
        optional_truth=_coerce_list(raw.get("optional_truth"), ALLOWED_TRUTH),
        reasoning_style=str(raw.get("reasoning_style") or "")[:64],
        urgency=urgency,
        confidence=max(0.0, min(1.0, confidence)),
        raw=raw if isinstance(raw, dict) else {},
    )
