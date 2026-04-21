"""
CoS Direct-Read Allowlist (Phase 2 of metric-trust cleanup, 2026-04-21)
-----------------------------------------------------------------------

``cos_context.py`` is state-first. The canonical path for domain truth
is SAE (``get_state_value`` / ``get_metric`` / ``get_module_state``).

A small number of direct ORM reads are tolerated. Each must be
enumerated here with a stable label, the target model, a
classification, and a rationale. The CI purity test in
``apps/core/ai_state/tests_metric_access.py`` (``CosReadAllowlistTests``)
fails if:

* a direct read appears in ``cos_context.py`` whose model is not in
  this allowlist;
* a model's read count in ``cos_context.py`` exceeds the declared
  count below (new reads must be justified via this file);
* a model is listed here but no longer read (drop the entry instead
  of letting it rot).

Adding a new allowed read is a two-step change: add code + add
entry. This is intentional.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict


class ReadClassification(str, Enum):
    ENGINE_OUTPUT = "engine_output"
    SELF_STATE = "self_state"
    CONTINUITY = "continuity"
    REFERENCE_DATA = "reference_data"
    STRUCTURED_LOOKUP = "structured_lookup"
    GAP_PENDING_STATE = "gap_pending_state"


@dataclass(frozen=True)
class AllowedRead:
    model: str
    count: int
    classification: ReadClassification
    rationale: str


# Each entry: keyed by the model name as it appears in source. ``count``
# is the number of ``<Model>.objects.<method>`` call sites in
# ``cos_context.py``. The purity test compares grep reality to this.
COS_READ_ALLOWLIST: Dict[str, AllowedRead] = {
    # ── Engine outputs (canonical intelligence pipeline) ──────
    "Insight": AllowedRead(
        model="Insight",
        count=1,
        classification=ReadClassification.ENGINE_OUTPUT,
        rationale="Active PIE insights (top 5 by recency) for CoS prompt.",
    ),
    "Prediction": AllowedRead(
        model="Prediction",
        count=1,
        classification=ReadClassification.ENGINE_OUTPUT,
        rationale="Active PRIE predictions (top 5 by confidence) for CoS prompt.",
    ),
    "GuidanceItem": AllowedRead(
        model="GuidanceItem",
        count=1,
        classification=ReadClassification.ENGINE_OUTPUT,
        rationale="Active PGE guidance (top 5 by priority) for CoS prompt.",
    ),
    "DomainCorrelation": AllowedRead(
        model="DomainCorrelation",
        count=2,
        classification=ReadClassification.ENGINE_OUTPUT,
        rationale=(
            "Active CDCE correlations. Two read sites: executive-context "
            "summary (top 5) + signal-aware context correlator."
        ),
    ),
    "SignalSnapshot": AllowedRead(
        model="SignalSnapshot",
        # 1 read (today's daily signals) + 1 coordination write. Counted
        # together because the allowlist compares raw .objects. call sites.
        count=2,
        classification=ReadClassification.ENGINE_OUTPUT,
        rationale=(
            "Today's EAE signal snapshots for CoS narration. Second "
            "entry is a coordination write that also goes through "
            "SignalSnapshot.objects."
        ),
    ),
    "GoalMomentumSnapshot": AllowedRead(
        model="GoalMomentumSnapshot",
        count=2,
        classification=ReadClassification.ENGINE_OUTPUT,
        rationale=(
            "Latest and previous momentum snapshots per active goal, "
            "for momentum trend narration."
        ),
    ),

    # ── Self-state (CoS's own coordination table) ─────────────
    "CoSSituationState": AllowedRead(
        model="CoSSituationState",
        count=3,
        classification=ReadClassification.SELF_STATE,
        rationale=(
            "CoS arbitration + learning-mode gate + write-suppression "
            "gate read CoS's own state table. Not domain truth."
        ),
    ),

    # ── Structured lookups (single records, no truth derivation) ──
    "HouseholdMembership": AllowedRead(
        model="HouseholdMembership",
        count=1,
        classification=ReadClassification.STRUCTURED_LOOKUP,
        rationale="Single membership record for household context.",
    ),
    "UserOperatingProfile": AllowedRead(
        model="UserOperatingProfile",
        count=1,
        classification=ReadClassification.STRUCTURED_LOOKUP,
        rationale="User's declared operating profile (single record).",
    ),
    "_UserModel": AllowedRead(
        model="_UserModel",
        count=1,
        classification=ReadClassification.STRUCTURED_LOOKUP,
        rationale="User identity resolution by id (lazy import).",
    ),
    "_LMUser": AllowedRead(
        model="_LMUser",
        count=1,
        classification=ReadClassification.STRUCTURED_LOOKUP,
        rationale="Learning-mode user identity resolution by id.",
    ),
    "LifeGoal": AllowedRead(
        model="LifeGoal",
        count=1,
        classification=ReadClassification.STRUCTURED_LOOKUP,
        rationale=(
            "FK resolution to look up GoalMomentumSnapshot per active "
            "goal. Goal metadata for narration comes from SAE "
            "goals.active_titles / upcoming_titles / overdue_titles."
        ),
    ),

    # ── Continuity (specific events / messages for follow-up) ─
    "CalendarEvent": AllowedRead(
        model="CalendarEvent",
        count=1,
        classification=ReadClassification.CONTINUITY,
        rationale="Today's scheduled calendar events for timeline context.",
    ),
    "AssistantMessage": AllowedRead(
        model="AssistantMessage",
        count=1,
        classification=ReadClassification.CONTINUITY,
        rationale=(
            "Last non-fallback assistant message timestamp, used to "
            "decide daily-brief vs light greeting."
        ),
    ),

    # ── Reference data (static catalogs, not user truth) ──────
    "ScriptureVerse": AllowedRead(
        model="ScriptureVerse",
        count=1,
        classification=ReadClassification.REFERENCE_DATA,
        rationale="Bible verse lookup for faith-section context.",
    ),

    # ── State gaps (pending canonical SAE support) ────────────
    "LabResult": AllowedRead(
        model="LabResult",
        count=3,
        classification=ReadClassification.GAP_PENDING_STATE,
        rationale=(
            "No canonical medical state builder yet surfaces recent "
            "labs / trending tests / per-test time series. All three "
            "sites call log_state_gap('medical.*'). Close by adding "
            "build_medical_state fields in a later phase."
        ),
    ),
}


# Models that the purity test should not count under any circumstance —
# standard library / third-party queryset patterns that happen to match
# the `.objects.` grep but are not domain reads.
ALLOWLIST_IGNORE_MODELS: frozenset = frozenset()
