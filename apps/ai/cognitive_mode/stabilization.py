"""Beth Stabilization Sprint — surgical trust-break guards.

These are intentionally small, high-confidence, reversible guards that stop the
worst live failures while the broader cognitive architecture is built. They do
NOT replace routing, handlers, or models. Everything here is gated by a single
kill switch (``WLJ_BETH_STABILIZATION_ENABLED``, default ON) so the whole sprint
can be disabled instantly via settings without a code revert.

Pure predicates + one deterministic composer. No DB writes, no LLM, no mutation.

Wiring (3 small edits, all guarded by ``stabilization_enabled()``):
  - deterministic_router.classify_and_route : Analyze override + Health Analyze v0
  - personal_assistant._cos_mode_shortcut   : Execute-contamination guard
  - personal_assistant.send_message         : unsafe-mutation filter

See docs/wlj_claude_changelog.md (2026-06-07 stabilization sprint).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def stabilization_enabled() -> bool:
    """Master kill switch. Default ON; flip to False in settings to revert."""
    try:
        from django.conf import settings
        return bool(getattr(settings, "WLJ_BETH_STABILIZATION_ENABLED", True))
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Fix 1 — Analyze intent override vocabulary
# High-confidence analyze phrasing that must NOT be swallowed by greedy
# Retrieve/Execute/data routes and must NEVER trigger task mutation.
# ---------------------------------------------------------------------------
_ANALYZE_PHRASES = (
    "what do you think",
    "what do you notice",
    "what stands out",
    "do you notice",
    "notice lately",
    "evaluate",
    "patterns",
    "anything concerning",
    "should i be worried",
    "do i need to change anything",
    "need to change anything",
    "how am i doing overall",
    "how does this look",
    "how is this looking",
    "am i doing okay",
    "am i doing ok",
    "am i on track",
    # Temporal analysis cues — strong intent to interpret, not look up a value:
    "my weight history",
    "weight history",
    "history?",
    " trend",
    "trending",
)


def is_analyze_request(msg_lower: str) -> bool:
    """True when the message is a high-confidence Analyze/interpretation ask."""
    if not msg_lower:
        return False
    return any(p in msg_lower for p in _ANALYZE_PHRASES)


# ---------------------------------------------------------------------------
# Fix 2 — Health context + explicit-execute vocabularies
# ---------------------------------------------------------------------------
# Concrete health-domain tokens ONLY. Deliberately EXCLUDES generic temporal
# words (trend/history/overall/progress) — including those as "health context"
# caused cross-domain bleed (e.g. "my spending trends" -> health package). Those
# generic words remain Analyze cues above; health context requires a real health
# token so the Health Analyze v0 composer never fires on a non-health question.
_HEALTH_TOKENS = (
    "weight", "weigh", "glucose", "blood sugar", "blood glucose", "a1c",
    "nutrition", "protein", "calorie", "calories", "macro", "macros",
    "workout", "exercise", "lifting", "cardio", "training",
    "sleep", "recovery", "body composition", "body fat", "waist",
    "measurements", "my health", "health?", " health ", "vitals",
    "fitness", "blood pressure", "heart rate", "steps",
)


def is_health_context(msg_lower: str) -> bool:
    """True when the message references a concrete health domain."""
    if not msg_lower:
        return False
    return any(t in msg_lower for t in _HEALTH_TOKENS)


_EXPLICIT_EXECUTE_PHRASES = (
    "what should i do next",
    "what do i do next",
    "what should i focus on",
    "what do i need to do",
    "what is my priority",
    "what's my priority",
    "whats my priority",
    "what's the priority",
    "next action",
    "what should i tackle",
)


def is_explicit_execute_request(msg_lower: str) -> bool:
    """True only for explicit next-action asks (these MAY use the execute path
    even in a health context)."""
    if not msg_lower:
        return False
    return any(p in msg_lower for p in _EXPLICIT_EXECUTE_PHRASES)


# ---------------------------------------------------------------------------
# Fix 3 — Accidental-mutation guard
# Rule: natural coaching/question language must NEVER mutate state. We suppress a
# mutation intent only when the message is QUESTION-FORM and lacks an explicit
# mutation phrase. Imperative mutations ("push my 3pm to 4", "delete that task")
# are NOT question-form and are left untouched — keeping blast radius tiny.
# ---------------------------------------------------------------------------
MUTATION_INTENTS = frozenset({
    "mutate_task", "complete_task", "skip_task", "delete_task",
    "update_goal_progress",  # writes; guard if phrased as a question
})

_EXPLICIT_MUTATION_PHRASES = (
    "mark complete", "mark it complete", "mark as complete", "mark done",
    "mark as done", "mark task", "complete task", "complete the task",
    "complete my", "completed task", "check off", "cross off",
    "update task", "change task", "edit task", "rename task",
    "delete task", "delete the", "remove task", "move task", "move the",
    "reschedule", "push my", "push the", "bump my", "shift my",
    "set due date", "due date to", "skip task", "skip the",
    "finished my", "i finished", "i completed", "done with", "took my",
)

_QUESTION_STARTS = (
    "do ", "does ", "did ", "should ", "shall ", "what ", "how ", "why ",
    "can ", "could ", "would ", "is ", "are ", "am ", "will ", "may ",
    "you think", "think i",
)


def _is_question_form(msg_lower: str) -> bool:
    m = (msg_lower or "").strip()
    if not m:
        return False
    if m.endswith("?"):
        return True
    return any(m.startswith(s) for s in _QUESTION_STARTS)


def is_explicit_mutation(msg_lower: str) -> bool:
    if not msg_lower:
        return False
    return any(p in msg_lower for p in _EXPLICIT_MUTATION_PHRASES)


def should_block_mutation(intent_type: str, msg_lower: str) -> bool:
    """True if this mutation intent should be suppressed as accidental.

    Only blocks when the intent is a mutation AND the message is question-form
    AND there is no explicit mutation phrase. Conservative by design.
    """
    if intent_type not in MUTATION_INTENTS:
        return False
    if is_explicit_mutation(msg_lower):
        return False
    return _is_question_form(msg_lower)


def filter_unsafe_mutations(actionable_intents, message):
    """Drop mutation intents that look like accidental writes from coaching
    language. Returns (kept_intents, suppressed_intents). Never raises."""
    try:
        if not actionable_intents:
            return actionable_intents, []
        msg_lower = (message or "").lower()
        kept, suppressed = [], []
        for ir in actionable_intents:
            itype = getattr(ir, "intent_type", "")
            if should_block_mutation(itype, msg_lower):
                suppressed.append(ir)
            else:
                kept.append(ir)
        return kept, suppressed
    except Exception:
        logger.warning("filter_unsafe_mutations failed — passing through", exc_info=True)
        return actionable_intents, []


# ---------------------------------------------------------------------------
# Fix 4 — Temporary Health Analyze v0 (deterministic, grounded, no LLM)
# Reads canonical SAE state and composes a Situation / What I Notice /
# Recommendation answer. Returns None when there's essentially no health data
# (caller then falls through to existing behavior). Invents nothing.
# ---------------------------------------------------------------------------

def _safe_state(user, module):
    try:
        from apps.core.ai_state.state_engine import get_module_state
        return get_module_state(user, module) or {}
    except Exception:
        logger.debug("health_analyze_v0: state read failed for %s", module, exc_info=True)
        return {}


def _user_age(user):
    try:
        dob = getattr(getattr(user, "profile", None), "date_of_birth", None) or \
              getattr(getattr(user, "preferences", None), "date_of_birth", None)
        if not dob:
            return None
        from apps.core.ai_state.state_engine import get_user_state  # noqa
        from datetime import date
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except Exception:
        return None


_WEIGHT_TREND_PHRASING = {
    "decreasing": "trending down",
    "increasing": "trending up",
    "stable": "holding steady",
}


def build_health_analyze_v0(user) -> str | None:
    """Deterministic grounded health analysis. None when insufficient data."""
    try:
        health = _safe_state(user, "health")
        fitness = _safe_state(user, "fitness")
        nutrition = _safe_state(user, "nutrition")

        weight = health.get("weight_current")
        glucose_summary = health.get("glucose_summary") or {}
        sleep_avg = health.get("sleep_avg_hours_7d")
        workouts_7d = fitness.get("workouts_7d")
        body_comp = health.get("body_composition") or {}

        # Insufficient-data guard: need at least one real health signal.
        if (weight is None and not glucose_summary and sleep_avg is None
                and not workouts_7d and not body_comp):
            return None

        # ── Situation ──────────────────────────────────────────────
        situation_bits = []
        if weight is not None:
            unit = health.get("weight_unit") or "lb"
            chg = health.get("weight_change_30d")
            trend = _WEIGHT_TREND_PHRASING.get(health.get("weight_trend"), None)
            line = f"You're at {weight} {unit}"
            if chg is not None and trend:
                line += f", {trend} ({chg:+} {unit} over 30 days)"
            elif trend:
                line += f", {trend}"
            situation_bits.append(line + ".")
        situation = " ".join(situation_bits) or "Here's how your health signals look right now."

        # ── What I Notice ──────────────────────────────────────────
        notices = []
        wtrend = health.get("weight_trend")
        if wtrend == "decreasing":
            notices.append("Weight is trending down steadily.")
        elif wtrend == "increasing":
            notices.append("Weight has been trending up.")

        gtrend = glucose_summary.get("trend_7d_vs_30d") or ""
        if gtrend == "improving":
            notices.append("Glucose is improving versus your 30-day baseline.")
        elif gtrend == "worsening":
            notices.append("Glucose has drifted up versus your 30-day baseline.")
        elif health.get("glucose_context") in ("Normal", "Stable"):
            notices.append("Glucose is holding in a stable range.")

        if isinstance(workouts_7d, int):
            if workouts_7d >= 3:
                notices.append(f"Workout consistency is solid ({workouts_7d} in the last 7 days).")
            elif workouts_7d == 0:
                notices.append("No workouts logged in the last 7 days.")
            else:
                notices.append(f"Workouts are light this week ({workouts_7d} in 7 days).")

        strend = health.get("sleep_trend")
        consistency = health.get("sleep_consistency_score")
        if sleep_avg is not None:
            if strend == "decreasing" or (isinstance(consistency, (int, float)) and consistency < 50):
                notices.append(f"Sleep is a soft spot (~{sleep_avg}h avg).")
            else:
                notices.append(f"Sleep is averaging ~{sleep_avg}h.")

        bc_summary = body_comp.get("trend_summary") or []
        if bc_summary:
            notices.append(str(bc_summary[0]))

        pc = nutrition.get("protein_compliance_pct")
        if isinstance(pc, (int, float)):
            if pc < 80:
                notices.append(f"Protein is running under target ({round(pc)}% today).")
            else:
                notices.append(f"Protein is on target ({round(pc)}% today).")

        if not notices:
            notices.append("Signals are stable but there isn't enough recent data to spot a clear trend yet.")

        # ── Recommendation (optional, conservative, non-clinical) ──
        recommendation = _build_recommendation(
            wtrend, workouts_7d, sleep_avg, strend, consistency, pc, user)

        # ── Assemble deterministic shape ───────────────────────────
        parts = [
            situation,
            "",
            "What I notice:",
        ]
        parts += [f"• {n}" for n in notices]
        if recommendation:
            parts += ["", recommendation]
        return "\n".join(parts)
    except Exception:
        logger.warning("build_health_analyze_v0 failed — falling through", exc_info=True)
        return None


def _build_recommendation(wtrend, workouts_7d, sleep_avg, strend, consistency, pc, user) -> str | None:
    """Pick the single biggest grounded opportunity. Cautious, no medical claims."""
    # Identify the weakest signal deterministically.
    weak = None
    if isinstance(workouts_7d, int) and workouts_7d == 0:
        weak = "getting at least one or two workouts back on the board this week"
    elif sleep_avg is not None and (strend == "decreasing" or (isinstance(consistency, (int, float)) and consistency < 50)):
        weak = "improving sleep consistency"
    elif isinstance(pc, (int, float)) and pc < 80:
        weak = "getting protein closer to target"

    losing_well = wtrend == "decreasing" and (not isinstance(workouts_7d, int) or workouts_7d >= 2)

    if losing_well and weak:
        return (f"My read: the weight trend looks sustainable, so I wouldn't push dramatically "
                f"harder right now. The bigger opportunity looks like {weak}.")
    if losing_well:
        return ("My read: the weight trend looks sustainable and consistent — steady as you go. "
                "Nothing here suggests you need to push harder.")
    if weak:
        return f"My read: the clearest opportunity right now is {weak}."
    return None
