"""Cognitive mode taxonomy + context-package requirements.

Single source of truth for:
  - the cognitive MODES Beth can operate in
  - the DOMAINS a question can target
  - which grounded facts an Analyze/Coach answer for a given domain *would* need

Pure data + tiny helpers. No Django, no DB, no side effects — safe to import
anywhere, including from tests, without migrations.

Taxonomy decision (Phase 0): FOUR top-level modes, with Coach folded into Analyze
as a boolean tail flag rather than a fifth lane. Rationale: Analyze and Coach share
the identical context package and differ only by an appended recommendation; a
separate top-level mode would double classifier confusion for zero context benefit,
and every extra lane is a new misroute surface. We still *measure* coach demand via
``coach_tail``. ``ANALYZE_COACH`` is retained only as an accepted reporting value.
"""

from __future__ import annotations


class Mode:
    """Top-level cognitive modes."""

    RETRIEVE = "retrieve"        # single grounded fact / point lookup / provenance
    ANALYZE = "analyze"          # multi-signal synthesis / interpretation / judgment
    ANALYZE_COACH = "analyze_coach"  # reporting-only alias; runtime uses ANALYZE + coach_tail
    EXECUTE = "execute"          # next action / prioritization / risk / fix
    REFLECT = "reflect"          # emotional / faith / journal interpretation
    UNKNOWN = "unknown"          # no confident signal (a high rate is itself a finding)

    ALL = (RETRIEVE, ANALYZE, ANALYZE_COACH, EXECUTE, REFLECT, UNKNOWN)
    # Modes the shadow classifier may actually emit (ANALYZE_COACH is folded in):
    EMITTABLE = (RETRIEVE, ANALYZE, EXECUTE, REFLECT, UNKNOWN)

    # The two "reasoning" modes — used to compute route_mismatch downstream.
    REASONING = (ANALYZE, REFLECT)


class Domain:
    """Question domains. Mirrors WLJ canonical-state domains where relevant."""

    WEIGHT = "weight"
    GLUCOSE = "glucose"
    NUTRITION = "nutrition"
    BODY_COMPOSITION = "body_composition"
    INTAKE = "intake"            # medications / supplements / provenance
    FITNESS = "fitness"
    SLEEP = "sleep"
    JOURNAL = "journal"          # mood / reflection
    FAITH = "faith"
    TASKS = "tasks"
    FINANCE = "finance"
    CROSS_DOMAIN = "cross_domain"  # "how am I doing overall"
    NONE = None


# ---------------------------------------------------------------------------
# Package requirements: for a given (mode, domain), what grounded facts SHOULD
# be assembled for a high-quality answer. Phase 0 uses this only to compute
# `package_needed` for the gap analysis (needed-vs-available). It does NOT drive
# any live behavior.
# ---------------------------------------------------------------------------

# The reference Analyze:weight package (from the pressure test). Noise trimmed,
# safety-critical facts added (med changes, completeness, goal target, threshold).
_WEIGHT_ANALYZE_PACKAGE = [
    "weight_current",
    "weight_start",
    "weight_velocity",
    "weight_trend_30_60_90",
    "waist_change",
    "body_comp_deltas",
    "med_changes_in_window",     # safety-critical: dose change reframes the whole story
    "weight_goal_target",        # intentional vs unintentional loss
    "healthy_loss_threshold",    # makes "sustainable" a deterministic boundary
    "resistance_training_flag",  # confounder flag only (fat vs muscle), not full detail
    "age",
    "diabetes_context",
    "data_completeness",         # drives confidence gate
]

_GLUCOSE_ANALYZE_PACKAGE = [
    "glucose_summary",           # averages, TIR, projected A1C, trend_7d_vs_30d
    "glucose_latest",            # latest event for grounding (never the average)
    "med_changes_in_window",
    "nutrition_adequacy_flag",
    "data_completeness",
]

_NUTRITION_ANALYZE_PACKAGE = [
    "nutrition_macros_today",
    "nutrition_targets",
    "nutrition_adherence_trend",
    "data_completeness",
]

_CROSS_DOMAIN_ANALYZE_PACKAGE = [
    "execution_summary",
    "health_headline",
    "weight_trend_30_60_90",
    "glucose_summary",
    "journal_sentiment_trend",
    "goal_momentum",
    "data_completeness",
]

PACKAGE_REQUIREMENTS = {
    (Mode.ANALYZE, Domain.WEIGHT): _WEIGHT_ANALYZE_PACKAGE,
    (Mode.ANALYZE, Domain.GLUCOSE): _GLUCOSE_ANALYZE_PACKAGE,
    (Mode.ANALYZE, Domain.NUTRITION): _NUTRITION_ANALYZE_PACKAGE,
    (Mode.ANALYZE, Domain.CROSS_DOMAIN): _CROSS_DOMAIN_ANALYZE_PACKAGE,
    (Mode.ANALYZE, Domain.BODY_COMPOSITION): [
        "body_comp_snapshot", "body_comp_deltas", "data_completeness",
    ],
    # Retrieve packages are single-fact by definition.
    (Mode.RETRIEVE, Domain.GLUCOSE): ["glucose_latest"],
    (Mode.RETRIEVE, Domain.WEIGHT): ["weight_current"],
    (Mode.RETRIEVE, Domain.NUTRITION): ["nutrition_macros_today"],
    (Mode.RETRIEVE, Domain.BODY_COMPOSITION): ["body_comp_snapshot"],
    (Mode.RETRIEVE, Domain.INTAKE): ["intake_provenance"],
    (Mode.REFLECT, Domain.JOURNAL): [
        "journal_recent_entries", "journal_sentiment_trend", "mood_trend",
    ],
}


def package_for(mode: str, domain) -> list:
    """Facts a high-quality answer for (mode, domain) would require.

    Falls back to a coarse default so the gap analysis always has *something*
    to compare against. Returns a copy so callers can't mutate the registry.
    """
    facts = PACKAGE_REQUIREMENTS.get((mode, domain))
    if facts is not None:
        return list(facts)
    if mode == Mode.ANALYZE:
        return ["data_completeness"]
    return []
