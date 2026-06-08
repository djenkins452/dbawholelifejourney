"""Golden corpus — labeled real-failure prompts.

Doubles as (a) the shadow classifier's unit-test oracle and (b) the model A/B
prompt set. Every entry comes from a real reported Beth failure or a clear
boundary case added for discrimination.

Scoring policy:
  - MODE is the primary metric (target >=85% exact, counting `acceptable_modes`).
  - DOMAIN is reported separately, NOT gated — stateless classification of
    context-dependent follow-ups (e.g. "evaluate my trend") genuinely cannot
    recover the domain from the message alone.
  - `must_not_route_to` documents the live-path failure each prompt must avoid;
    used later (with the probe) to flag real misroutes, not scored here.
"""

from __future__ import annotations

from .taxonomy import Mode, Domain


# Each entry: id, message, expected_mode, expected_domain, coach_tail_expected,
# acceptable_modes (besides expected), must_not_route_to, notes.
GOLDEN = [
    # --- the headline failures you reported ---
    {
        "id": "weight_history_analyze",
        "message": "What do you think about my weight history?",
        "expected_mode": Mode.ANALYZE,
        "expected_domain": Domain.WEIGHT,
        "coach_tail_expected": False,
        "acceptable_modes": [],
        "must_not_route_to": ["create_task", "deterministic_single_fact", "execute"],
        "notes": "Canonical 'analyze -> task list' failure.",
    },
    {
        "id": "weight_eval_coach",
        "message": ("No, I want you to evaluate my trend and tell me if I need to be "
                    "doing better, or slower, or anything else you pick up."),
        "expected_mode": Mode.ANALYZE,
        "expected_domain": Domain.WEIGHT,   # context-dependent; not gated
        "coach_tail_expected": True,
        "acceptable_modes": [],
        "must_not_route_to": ["deterministic_single_fact", "generic_advice"],
        "notes": "Analyze + coaching tail; domain only knowable from prior turn.",
    },
    {
        "id": "glucose_last_event",
        "message": "What was my last blood glucose reading and when?",
        "expected_mode": Mode.RETRIEVE,
        "expected_domain": Domain.GLUCOSE,
        "coach_tail_expected": False,
        "acceptable_modes": [],
        "must_not_route_to": ["weekly_average", "glucose_summary"],
        "notes": "Event retrieve; must not answer with the 7-day average.",
    },
    {
        "id": "protein_today",
        "message": "How am I doing on protein today?",
        "expected_mode": Mode.RETRIEVE,
        "expected_domain": Domain.NUTRITION,
        "coach_tail_expected": False,
        "acceptable_modes": [],
        "must_not_route_to": ["sleep_coaching", "macro_coaching"],
        "notes": "'how am I doing' + specific metric + today = point retrieve.",
    },
    {
        "id": "body_comp_compare",
        "message": "Compare my body measurements to last time.",
        "expected_mode": Mode.RETRIEVE,
        "expected_domain": Domain.BODY_COMPOSITION,
        "coach_tail_expected": False,
        "acceptable_modes": [Mode.ANALYZE],   # genuinely straddles retrieve/analyze
        "must_not_route_to": ["i_dont_have_them"],
        "notes": "Delta lookup via body-comp snapshot.",
    },
    {
        "id": "perfect_amino_source",
        "message": "Where is Perfect Amino coming from?",
        "expected_mode": Mode.RETRIEVE,
        "expected_domain": Domain.INTAKE,
        "coach_tail_expected": False,
        "acceptable_modes": [],
        "must_not_route_to": ["generic"],
        "notes": "Provenance retrieve.",
    },
    {
        "id": "what_next",
        "message": "What should I do next?",
        "expected_mode": Mode.EXECUTE,
        "expected_domain": Domain.NONE,
        "coach_tail_expected": False,
        "acceptable_modes": [],
        "must_not_route_to": ["generic_advice"],
        "notes": "Execution mode.",
    },
    {
        "id": "feel_off",
        "message": "I feel off lately.",
        "expected_mode": Mode.REFLECT,
        "expected_domain": Domain.JOURNAL,
        "coach_tail_expected": False,
        "acceptable_modes": [],
        "must_not_route_to": ["clinical", "generic"],
        "notes": "Reflect mode.",
    },
    {
        "id": "overall_checkin",
        "message": "How am I doing overall?",
        "expected_mode": Mode.ANALYZE,
        "expected_domain": Domain.CROSS_DOMAIN,
        "coach_tail_expected": False,
        "acceptable_modes": [],
        "must_not_route_to": ["task_list"],
        "notes": "Broad analyze; must not become a task checklist.",
    },
    {
        "id": "should_i_worry",
        "message": "Should I be worried?",
        "expected_mode": Mode.ANALYZE,
        "expected_domain": Domain.NONE,
        "coach_tail_expected": False,
        "acceptable_modes": [],
        "must_not_route_to": ["dismissive_oneliner"],
        "notes": "Judgment request; domain context-dependent.",
    },

    # --- boundary cases added for discrimination / stability ---
    {
        "id": "current_weight_retrieve",
        "message": "What is my current weight?",
        "expected_mode": Mode.RETRIEVE,
        "expected_domain": Domain.WEIGHT,
        "coach_tail_expected": False,
        "acceptable_modes": [],
        "must_not_route_to": ["analyze"],
        "notes": "Clean point retrieve — must NOT escalate to analyze.",
    },
    {
        "id": "biggest_risk_execute",
        "message": "What's the biggest risk right now?",
        "expected_mode": Mode.EXECUTE,
        "expected_domain": Domain.NONE,
        "coach_tail_expected": False,
        "acceptable_modes": [],
        "must_not_route_to": ["generic"],
        "notes": "Risk = execute mode.",
    },
    {
        "id": "patterns_analyze",
        "message": "What patterns do you notice in my data?",
        "expected_mode": Mode.ANALYZE,
        "expected_domain": Domain.CROSS_DOMAIN,
        "coach_tail_expected": False,
        "acceptable_modes": [],
        "must_not_route_to": ["single_fact"],
        "notes": "Pattern synthesis = analyze.",
    },
    {
        "id": "doing_differently_coach",
        "message": "Should I be doing anything differently?",
        "expected_mode": Mode.ANALYZE,
        "expected_domain": Domain.NONE,
        "coach_tail_expected": True,
        "acceptable_modes": [],
        "must_not_route_to": ["generic_advice"],
        "notes": "Coaching ask with no domain -> analyze + coach tail.",
    },
    {
        "id": "last_workout_retrieve",
        "message": "What was my last workout?",
        "expected_mode": Mode.RETRIEVE,
        "expected_domain": Domain.FITNESS,
        "coach_tail_expected": False,
        "acceptable_modes": [],
        "must_not_route_to": ["analyze"],
        "notes": "Point retrieve, fitness.",
    },
]


def mode_is_correct(entry: dict, predicted_mode: str) -> bool:
    """True if `predicted_mode` satisfies the entry's expected/acceptable modes.

    ANALYZE_COACH is treated as ANALYZE for scoring (Coach is a tail flag, not a
    distinct emitted mode).
    """
    norm = Mode.ANALYZE if predicted_mode == Mode.ANALYZE_COACH else predicted_mode
    allowed = {entry["expected_mode"], *entry.get("acceptable_modes", [])}
    allowed = {Mode.ANALYZE if a == Mode.ANALYZE_COACH else a for a in allowed}
    return norm in allowed
