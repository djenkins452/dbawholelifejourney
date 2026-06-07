# ==============================================================================
# File: apps/health/services/double_progression.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Double Progression Strength Service — earned, deterministic
#              progression recommendations based on real workout history.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-07
# ==============================================================================
"""
Double Progression Strength Intelligence — replace generic PR-chasing advice
with EARNED progression based on real workout history.

Training philosophy (explicit, locked in code):
    The goal is NOT constant PR chasing. The goal is SUSTAINABLE PROGRESSION
    that supports consistency, injury avoidance, muscle preservation during
    weight loss, metabolic health, and long-term functional strength.

    PRs remain evidence of progress, NEVER the trigger word for advice.

Readiness contract — completion = earned, NOT survival = earned:
    Two users may both "complete" 3 sessions at 50 lb × 10 reps. One executed
    every working set cleanly; the other barely scraped through with form
    breaks. This service treats those situations as fundamentally different.
    Progression is recommended ONLY when the data clears the readiness gate.
    When uncertain, the service HOLDS — stay-consistent always beats
    increase-load.

Ladder model (approved):
    compound  / heavier movements:  10 → 12 → +weight        (joint cost high)
    isolation / safer  movements:   10 → 12 → 15 → +weight   (lower risk)

Path A classification (no migration):
    Pattern table over Exercise.name + Exercise.muscle_group + Exercise.load_type.
    Unknown → isolation ladder (the SAFER default — smaller step, more reps
    before adding load).

Output is a structured dict per exercise — the caller (PIE rule / Guidance
rule) renders copy from (rationale_key + numbers). Coaching copy is NEVER
hardcoded inside this service: logic ≠ copy.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)


# ─── Tunables ────────────────────────────────────────────────────────────

#: Number of consecutive successful sessions required at the same weight
#: before any progression recommendation may fire. Matches the existing
#: weight-prefill service convention for consistency.
REQUIRED_SESSIONS = 3

#: Two recorded weights are considered the SAME working weight when their
#: difference is ≤ this many lb (accommodates half-plate increments + any
#: scale-rounding noise from the input UI).
SAME_WEIGHT_TOLERANCE_LB = Decimal("0.5")

#: Maximum age of the most-recent session in days. Older histories are
#: treated as stale — no progression on data that hasn't been touched in
#: weeks. Conservative because a 55-y/o type-II diabetic recovering from
#: a layoff needs to re-establish baseline before earning load.
MAX_RECENT_SESSION_AGE_DAYS = 14

#: Weight step per ladder type, in lb. Picked to be small and earnable —
#: never aggressive. Isolation steps stay small even when the ladder runs
#: longer; compounds get a touch more headroom.
WEIGHT_STEP_LB = {
    "compound": Decimal("5"),
    "isolation": Decimal("2.5"),
}

#: Rep target ladder per exercise type. Order matters — each entry is the
#: rep number the user is currently trying to earn at the current weight.
#: When the TOP entry is earned across REQUIRED_SESSIONS, the recommendation
#: switches from "more reps" to "small weight increase + return to bottom".
REP_LADDER = {
    "compound":  [10, 12],            # 10 → 12 → +weight (joint longevity)
    "isolation": [10, 12, 15],        # 10 → 12 → 15 → +weight (safer)
}

#: Substrings (lowercased) that, when present in either ExerciseSet.notes
#: or WorkoutExercise.notes during the K-session window, indicate the user
#: did NOT complete the work comfortably. This is the readiness gate's
#: explicit "survival vs earned" signal in the absence of RPE.
FAILURE_NOTE_SUBSTRINGS = (
    "failed", "fail", "missed", "form broke", "form break", "form broken",
    "broke form", "couldn't", "could not", "had to drop", "lost form",
    "shaky", "struggled",
)

#: SAE fitness signals that, when sufficiently low, suppress all
#: progression recommendations.
MIN_WORKOUTS_7D = 1
MIN_WORKOUTS_30D = 8     # less than 2/week over a month → no advancement

#: Sleep statuses below which progression is suppressed.
POOR_SLEEP_STATUSES = {"poor"}
MIN_SLEEP_HOURS_FOR_PROGRESSION = 5.0

#: Recovery score below which progression is suppressed (only consulted
#: when the field is present in state).
MIN_RECOVERY_SCORE = 50


# ─── Classification (Path A — no migration) ──────────────────────────────

#: Lowercased substrings in Exercise.name that mark a movement as compound
#: regardless of muscle_group. Matched as substrings, longer entries first.
_COMPOUND_NAME_PATTERNS = (
    "deadlift", "romanian deadlift", "back squat", "front squat", "squat",
    "bench press", "incline press", "overhead press", "shoulder press",
    "military press", "barbell row", "bent over row", "pendlay row",
    "t-bar row", "row",
    "leg press", "hack squat", "lunge", "split squat", "step-up",
    "pull-up", "pullup", "chin-up", "chinup", "dip", "rdl",
    "clean", "snatch", "thruster",
)

#: Lowercased substrings that mark a movement as isolation regardless of
#: any compound-sounding word in the name (e.g. "leg extension" must NOT
#: match "leg press" → check isolation patterns FIRST when both could fire).
_ISOLATION_NAME_PATTERNS = (
    "curl", "extension", "raise", "fly", "flye", "pushdown", "pulldown",
    "kickback", "shrug", "calf raise", "calf", "crunch", "twist",
    "rear delt", "reverse fly", "concentration", "preacher",
    "lateral", "front raise", "leg curl", "leg extension",
    "tricep extension", "tricep kickback", "cable curl",
)

#: muscle_group fallback for names that miss both pattern lists.
_COMPOUND_MUSCLE_GROUPS = {"chest", "back", "legs", "glutes", "quads", "hamstrings"}


def classify_exercise(exercise) -> str:
    """Return ``"compound"`` or ``"isolation"`` for an Exercise instance.

    Path A: pure-Python pattern match over name + muscle_group. No DB,
    no migration. Unknown → ``"isolation"`` (the SAFER ladder — smaller
    step, more reps to earn before adding load). This is the conservative
    default the user explicitly approved.
    """
    name = (getattr(exercise, "name", "") or "").lower()

    # Isolation patterns first — "leg extension" must beat any future
    # "extension"-adjacent compound entry.
    for pat in _ISOLATION_NAME_PATTERNS:
        if pat in name:
            return "isolation"

    for pat in _COMPOUND_NAME_PATTERNS:
        if pat in name:
            return "compound"

    muscle = (getattr(exercise, "muscle_group", "") or "").lower()
    if muscle in _COMPOUND_MUSCLE_GROUPS:
        return "compound"

    # Conservative default — small step, longer ladder, more sessions
    # to earn the weight increase. Safer when in doubt.
    return "isolation"


# ─── Public API ──────────────────────────────────────────────────────────

#: All stages the service may emit. The PIE/Guidance message builders
#: dispatch on these — never on the older fitness state strings.
STAGE_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
STAGE_HOLDING              = "HOLDING"
STAGE_EARNED_REPS          = "EARNED_REP_PROGRESSION"
STAGE_REP_RANGE_TRANSITION = "REP_RANGE_TRANSITION"
STAGE_EARNED_WEIGHT        = "EARNED_WEIGHT_INCREASE"

ALL_STAGES = (
    STAGE_INSUFFICIENT_HISTORY,
    STAGE_HOLDING,
    STAGE_EARNED_REPS,
    STAGE_REP_RANGE_TRANSITION,
    STAGE_EARNED_WEIGHT,
)


def evaluate_double_progression(user, *, exercise_id=None, fitness_state=None,
                                health_state=None) -> list[dict]:
    """Return per-exercise Double Progression recommendations.

    Args:
        user: Django User. Only their data is read.
        exercise_id: optional — limit to a single Exercise PK.
        fitness_state: optional pre-read SAE ``fitness`` module dict.
            When provided, ZERO extra SAE reads occur. Caller pattern:
            pass the dict already in scope inside the PIE rule.
        health_state: optional pre-read SAE ``health`` dict (for sleep /
            recovery readiness signals).

    Returns:
        A list of dicts, one per exercise active in the user's last 30
        days. Each dict has the shape documented in the module docstring:

            {
              "exercise_id":   int,
              "exercise_name": str,
              "ladder_type":   "compound" | "isolation",
              "stage":         one of ALL_STAGES,
              "current":       {"weight_lb": float, "reps": int, "sessions": int},
              "next_target":   {"weight_lb": float, "reps": int} | None,
              "rationale_key": "earned_reps"
                              | "earned_range"
                              | "earned_weight"
                              | "stable"
                              | "insufficient",
              "safety_holds":  list[str],
            }

        Stage INSUFFICIENT_HISTORY entries are omitted from the list
        — the caller never has to filter them out.

    Determinism: idempotent. Same inputs → same output. No state writes.
    """
    history = _build_per_exercise_history(user, exercise_id=exercise_id)
    if not history:
        return []

    # Resolve readiness signals ONCE (shared across all exercises).
    safety_holds = _readiness_safety_holds(
        user, fitness_state=fitness_state, health_state=health_state,
    )

    out = []
    for exercise, sessions in history.items():
        rec = _evaluate_single_exercise(exercise, sessions, safety_holds)
        if rec["stage"] == STAGE_INSUFFICIENT_HISTORY:
            continue
        out.append(rec)
    out.sort(key=lambda r: r["exercise_name"].lower())
    return out


# ─── Internals ───────────────────────────────────────────────────────────


def _build_per_exercise_history(user, *, exercise_id=None) -> dict:
    """Pull the last ~30 days of working-set history per exercise.

    Returns ``{Exercise: [session_dict, …]}`` ordered most-recent-first.
    Each session_dict has:
        {
          "session_id":  int,
          "date":        date,
          "top_weight":  Decimal | None,
          "top_reps":    list[int],         # reps of every set at top_weight
          "all_sets":    list[(weight, reps)],   # diagnostic, non-warmup only
          "any_failure": bool,              # readiness gate input
        }
    """
    from apps.health.models import ExerciseSet

    cutoff = (timezone.now() - timedelta(days=30)).date()

    qs = ExerciseSet.objects.filter(
        workout_exercise__session__user=user,
        workout_exercise__session__date__gte=cutoff,
        workout_exercise__session__status="active",
        workout_exercise__session__completed_at__isnull=False,
        workout_exercise__exercise__category="resistance",
        is_warmup=False,
    ).select_related(
        "workout_exercise__exercise",
        "workout_exercise__session",
        "workout_exercise",
    ).order_by(
        "-workout_exercise__session__date",
        "-workout_exercise__session_id",
        "set_number",
    )
    if exercise_id is not None:
        qs = qs.filter(workout_exercise__exercise_id=exercise_id)

    # Group → exercise → session_id → set list
    by_exercise_session = defaultdict(lambda: defaultdict(list))
    session_dates = {}
    session_workout_notes = defaultdict(str)
    for s in qs:
        ex = s.workout_exercise.exercise
        sess_id = s.workout_exercise.session_id
        sess_date = s.workout_exercise.session.date
        by_exercise_session[ex][sess_id].append(s)
        session_dates[sess_id] = sess_date
        # Concatenate workout_exercise.notes once per (exercise, session).
        we_notes = (s.workout_exercise.notes or "")
        if we_notes:
            session_workout_notes[(ex.id, sess_id)] = we_notes

    history = {}
    for ex, sess_map in by_exercise_session.items():
        ordered_sessions = sorted(
            sess_map.items(),
            key=lambda kv: session_dates.get(kv[0]) or cutoff,
            reverse=True,
        )
        sess_list = []
        for sess_id, sets in ordered_sessions:
            # Top working weight = max non-warmup weight this session.
            weights = [s.weight for s in sets if s.weight is not None]
            if not weights:
                # Bodyweight-only session for this exercise — still trackable
                # as a rep-only ladder (weight bucket = None).
                rep_list = [s.reps for s in sets if s.reps is not None]
                if not rep_list:
                    continue
                top_w = None
                top_rep_list = rep_list
            else:
                top_w = max(weights)
                top_rep_list = [
                    s.reps for s in sets
                    if s.weight is not None
                    and s.reps is not None
                    and _within_tolerance(s.weight, top_w)
                ]
            failure_text = " ".join(
                (s.notes or "") for s in sets
            ).lower()
            workout_text = session_workout_notes.get((ex.id, sess_id), "").lower()
            any_failure = any(
                tag in failure_text or tag in workout_text
                for tag in FAILURE_NOTE_SUBSTRINGS
            )
            sess_list.append({
                "session_id": sess_id,
                "date": session_dates[sess_id],
                "top_weight": top_w,
                "top_reps": top_rep_list,
                "all_sets": [(s.weight, s.reps) for s in sets],
                "any_failure": any_failure,
            })
        if sess_list:
            history[ex] = sess_list
    return history


def _within_tolerance(a, b) -> bool:
    """True when two Decimals/floats are within SAME_WEIGHT_TOLERANCE_LB."""
    if a is None or b is None:
        return a is b
    return abs(Decimal(str(a)) - Decimal(str(b))) <= SAME_WEIGHT_TOLERANCE_LB


def _readiness_safety_holds(user, *, fitness_state=None, health_state=None) -> list[str]:
    """Resolve all global readiness signals into a list of hold reasons.

    Fail-closed: any uncertainty defaults to holding. Reads ONLY from
    already-built SAE state — never live-computes. The PIE rule passes
    pre-read dicts so this is zero extra queries on the request/event
    path.
    """
    holds = []

    # Tolerate missing state — the PIE event always provides at least
    # an empty dict, but for safety treat absence as low-data.
    fitness = fitness_state or {}
    health = health_state or {}

    workouts_7d = fitness.get("workouts_7d")
    workouts_30d = fitness.get("workouts_30d")

    if workouts_7d is None or workouts_30d is None:
        # No SAE fitness data at all — too uncertain to advance.
        holds.append("low_consistency")
    else:
        if workouts_7d < MIN_WORKOUTS_7D or workouts_30d < MIN_WORKOUTS_30D:
            holds.append("low_consistency")

    sleep_status = (health.get("sleep_status") or "").lower()
    last_sleep_hours = health.get("sleep_last_night_hours")
    if sleep_status in POOR_SLEEP_STATUSES:
        holds.append("poor_sleep")
    elif last_sleep_hours is not None and last_sleep_hours < MIN_SLEEP_HOURS_FOR_PROGRESSION:
        holds.append("poor_sleep")

    recovery = fitness.get("recovery_score_today")
    if recovery is not None and recovery < MIN_RECOVERY_SCORE:
        holds.append("low_recovery")

    if health.get("illness_active"):
        holds.append("illness")

    return holds


def _evaluate_single_exercise(exercise, sessions: list, global_holds: list[str]) -> dict:
    """Classify one exercise's recent history into a stage + next target.

    Readiness gate is integrated here so a fail-closed HOLD is impossible
    to bypass — even if the K-session pattern looks ready, any per-exercise
    or global hold downgrades to HOLDING.
    """
    ladder_type = classify_exercise(exercise)
    ladder = REP_LADDER[ladder_type]
    step = WEIGHT_STEP_LB[ladder_type]
    exercise_id = getattr(exercise, "id", None)
    exercise_name = getattr(exercise, "name", "")

    # Stage 0 — insufficient history.
    if len(sessions) < REQUIRED_SESSIONS:
        return _make_rec(
            exercise_id, exercise_name, ladder_type,
            stage=STAGE_INSUFFICIENT_HISTORY,
            current=_summary_current(sessions[0] if sessions else None, len(sessions)),
            next_target=None,
            rationale_key="insufficient",
            safety_holds=[],
        )

    most_recent_date = sessions[0]["date"]
    age_days = (timezone.now().date() - most_recent_date).days
    holds = list(global_holds)
    if age_days > MAX_RECENT_SESSION_AGE_DAYS:
        holds.append("stale_history")

    # Take the K most recent sessions for this exercise.
    window = sessions[:REQUIRED_SESSIONS]

    # Are all K at a consistent top weight?
    top_weights = [s["top_weight"] for s in window]
    if any(w is None for w in top_weights):
        # Bodyweight-only history is supported as a degenerate rep-only
        # ladder (weight stays None — we just look at reps).
        all_same_weight = all(w is None for w in top_weights)
        consistent_weight = None
    else:
        max_w = max(top_weights)
        min_w = min(top_weights)
        all_same_weight = (max_w - min_w) <= SAME_WEIGHT_TOLERANCE_LB
        consistent_weight = max_w if all_same_weight else None

    current_summary = _summary_current(window[0], len(window))

    if not all_same_weight:
        # Weight is moving around — no plateau, no progression rec.
        # Honest neutral state.
        return _make_rec(
            exercise_id, exercise_name, ladder_type,
            stage=STAGE_HOLDING,
            current=current_summary,
            next_target=None,
            rationale_key="stable",
            safety_holds=holds,
        )

    # Failure-notes gate — readiness contract: completion = earned,
    # survival ≠ earned. ANY failure note in the window forces HOLD.
    if any(s["any_failure"] for s in window):
        holds.append("form_signal")

    # Per-set completion gate — every working set at the top weight
    # across the window must have reached the current rep target. We
    # determine the current rep target by walking the ladder.
    rep_target = _determine_current_rep_target(window, ladder)
    all_sets_at_target = _all_sets_meet_target(window, rep_target)

    # If holds already set, fail closed immediately — even if the
    # numerical pattern looks ready, recovery / consistency / form
    # holds beat advancement.
    if holds:
        return _make_rec(
            exercise_id, exercise_name, ladder_type,
            stage=STAGE_HOLDING,
            current=current_summary,
            next_target=None,
            rationale_key="stable",
            safety_holds=holds,
        )

    # Walk the ladder to decide which stage we're in.
    # Per-set rule: ALL working sets at the top weight must have hit
    # the current rep target for K consecutive sessions.
    if not all_sets_at_target:
        # Numerical pattern not yet earned — stay consistent.
        return _make_rec(
            exercise_id, exercise_name, ladder_type,
            stage=STAGE_HOLDING,
            current=current_summary,
            next_target=None,
            rationale_key="stable",
            safety_holds=[],
        )

    # We earned the current rep target. Where in the ladder are we?
    idx = ladder.index(rep_target)
    if idx < len(ladder) - 1:
        # Move up the rep ladder, same weight.
        next_reps = ladder[idx + 1]
        # Distinguish stage 1 (entering middle target) from stage 2
        # (transitioning to top target — e.g. 12 → 15 on isolation).
        stage = STAGE_REP_RANGE_TRANSITION if idx >= 1 else STAGE_EARNED_REPS
        rationale = "earned_range" if stage == STAGE_REP_RANGE_TRANSITION else "earned_reps"
        next_target = {
            "weight_lb": float(consistent_weight) if consistent_weight is not None else None,
            "reps": next_reps,
        }
    else:
        # Top of the ladder earned — recommend small weight increase,
        # reset to bottom rep target.
        if consistent_weight is None:
            # Bodyweight-only top — we can't recommend a weight bump.
            # Stay at top reps; honest hold.
            return _make_rec(
                exercise_id, exercise_name, ladder_type,
                stage=STAGE_HOLDING,
                current=current_summary,
                next_target=None,
                rationale_key="stable",
                safety_holds=[],
            )
        next_weight = consistent_weight + step
        stage = STAGE_EARNED_WEIGHT
        rationale = "earned_weight"
        next_target = {
            "weight_lb": float(next_weight),
            "reps": ladder[0],
        }

    return _make_rec(
        exercise_id, exercise_name, ladder_type,
        stage=stage,
        current=current_summary,
        next_target=next_target,
        rationale_key=rationale,
        safety_holds=[],
    )


def _determine_current_rep_target(window: list, ladder: list[int]) -> int:
    """Pick the rep target the user is currently trying to earn.

    We look at the MINIMUM "max reps reached at top weight" across the
    window (the worst session — the one that determines whether the rep
    target is truly earned). Then snap that down to the nearest ladder
    rung at or below it. If the worst session is below the bottom rung,
    we still target the bottom rung (the lowest meaningful target).
    """
    worst_max_reps = None
    for s in window:
        if not s["top_reps"]:
            return ladder[0]
        max_in_session = max(s["top_reps"])
        if worst_max_reps is None or max_in_session < worst_max_reps:
            worst_max_reps = max_in_session

    if worst_max_reps is None:
        return ladder[0]

    # Snap down to ladder. Smallest rung ≥ ladder[0] that we can claim.
    target = ladder[0]
    for rung in ladder:
        if rung <= worst_max_reps:
            target = rung
        else:
            break
    return target


def _all_sets_meet_target(window: list, rep_target: int) -> bool:
    """True iff EVERY top-weight set in EVERY session in the window
    reached ``rep_target`` reps.

    This is the explicit readiness gate: not "max reps in any single
    set" — every set must clear the bar. One short set = not earned.
    """
    for s in window:
        if not s["top_reps"]:
            return False
        if min(s["top_reps"]) < rep_target:
            return False
    return True


def _summary_current(session, k_sessions) -> dict:
    """Shape the "current" sub-dict for the output rec."""
    if session is None:
        return {"weight_lb": None, "reps": None, "sessions": 0}
    top_w = session["top_weight"]
    top_rep_max = max(session["top_reps"]) if session["top_reps"] else None
    return {
        "weight_lb": float(top_w) if top_w is not None else None,
        "reps": top_rep_max,
        "sessions": k_sessions,
    }


def _make_rec(exercise_id, exercise_name, ladder_type, *, stage, current,
              next_target, rationale_key, safety_holds) -> dict:
    """Final output shape — typed, deterministic, copy-free."""
    return {
        "exercise_id": exercise_id,
        "exercise_name": exercise_name,
        "ladder_type": ladder_type,
        "stage": stage,
        "current": current,
        "next_target": next_target,
        "rationale_key": rationale_key,
        "safety_holds": list(safety_holds),
    }


# ─── Copy builder (consumed by PIE + Guidance rules) ────────────────────
#
# Lives here ONLY because it's the single canonical mapping from
# (rationale_key + numbers) → user-facing message. Rules dispatch on
# rationale_key and never embed their own coaching string. Logic ≠ copy
# is preserved: changing the wording here does NOT touch detection
# logic above this line.

def render_recommendation_copy(rec: dict) -> str:
    """Build the user-facing sentence from a recommendation dict.

    Pure function. Same rec → same string. PRs are never mentioned.
    """
    name = rec["exercise_name"]
    current = rec["current"]
    target = rec.get("next_target")
    holds = rec.get("safety_holds") or []

    # Safety holds always render the same "stay consistent" line — the
    # reason chip is rendered in the caller's evidence dict, not in copy.
    if holds:
        reason_phrase = _hold_reason_phrase(holds)
        return (
            f"Stay consistent on {name} — {reason_phrase} "
            f"appear to be catching up."
        )

    stage = rec["stage"]
    weight = current.get("weight_lb")
    weight_str = f"{weight:g} lb" if weight else "bodyweight"

    if stage == STAGE_EARNED_REPS or stage == STAGE_REP_RANGE_TRANSITION:
        cur_reps = current.get("reps") or "your current reps"
        next_reps = target["reps"] if target else None
        return (
            f"You've been consistent on {name} at {weight_str} — "
            f"{rec['current']['sessions']} sessions at {cur_reps} reps. "
            f"Consider moving toward {next_reps} reps before increasing weight."
        )

    if stage == STAGE_EARNED_WEIGHT and target is not None:
        cur_reps = current.get("reps") or 0
        nxt_w = target["weight_lb"]
        nxt_reps = target["reps"]
        # Suggest a small range: the step plus one higher option, but
        # NEVER aggressive. For compound the range is 5–7.5; for
        # isolation it's 2.5–5.
        higher = float(nxt_w) + (2.5 if rec["ladder_type"] == "isolation" else 2.5)
        return (
            f"Three clean sessions on {name} at {weight_str} × {cur_reps} reps. "
            f"Consider a small increase — {nxt_w:g} or {higher:g} lb — "
            f"and return to {nxt_reps} reps."
        )

    if stage == STAGE_HOLDING:
        return (
            f"{name} is still settling — stay consistent at this weight "
            f"for another session."
        )

    # Unknown stage / no current — fall back to a safe, generic line.
    return (
        f"Stay consistent on {name} — your progression signals are still settling."
    )


def _hold_reason_phrase(holds: list[str]) -> str:
    """Pick the most user-meaningful hold reason for the message."""
    # Order intentionally mirrors what the user can DO something about.
    priority = (
        "illness", "form_signal", "poor_sleep", "low_recovery",
        "low_consistency", "stale_history",
    )
    label = {
        "illness": "recovering from illness",
        "form_signal": "form and recovery",
        "poor_sleep": "recovery and sleep",
        "low_recovery": "recovery",
        "low_consistency": "workout frequency",
        "stale_history": "training rhythm",
    }
    for k in priority:
        if k in holds:
            return label[k]
    return "recovery"
