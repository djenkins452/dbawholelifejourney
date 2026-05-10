"""
Narration Contract — prompt-section trust tiers and preamble.

Every section appended to the LLM system prompt declares a tier. The
tier determines what kind of authority the section carries and how the
LLM is allowed to use it.

This is NOT a new decision engine — it is a narration-governance layer
that sits on top of the existing deterministic engines (build_today_
execution, build_execution_state, signal renderer, selectors).

Tiers (strict authority order):

    canonical_item_truth — The ONLY authority for whether an item is
        completed, overdue, recoverable, at risk, or "next." The LLM
        must quote it; rephrasing item state away from canonical is
        forbidden.

    rollup_summary — Domain or window-level aggregations. Reports
        counts and booleans about a GROUP. MUST NOT be converted into
        per-item completion claims. "prayer: DONE" describes the
        prayer rollup; it does NOT mean any specific routine item is
        completed.

    advisory — Recommendations, suggestions, maintenance plans.
        MUST NOT determine state, urgency, or selection.

    contextual — Background information (signals, goals, sports,
        learning, time-of-day). MUST NOT override canonical.

State determination rules (STRICT):

    - "X is done"          ⇐ ONLY canonical_item_truth.
    - "X is overdue"       ⇐ ONLY canonical_item_truth.
    - "X is at risk"       ⇐ ONLY canonical at_risk_actions list.
    - "next action is X"   ⇐ ONLY canonical NEXT ACTION.
    - "fix X first"        ⇐ ONLY canonical FIX line.

Companion modules:

    apps/ai/narration_contract_validator.py — post-response soft
        validator. Detects state claims in the LLM response and flags
        ones not traceable to canonical_item_truth.

    apps/core/ai_orchestrator/contradiction_telemetry.py — pre-prompt
        contradiction detection (rollup says DONE while a child item
        is pending).
"""

# ── Trust-tier constants (strings to keep the prompt readable) ──────
TIER_CANONICAL = "canonical_item_truth"
TIER_ROLLUP = "rollup_summary"
TIER_ADVISORY = "advisory"
TIER_CONTEXTUAL = "contextual"

ALL_TIERS = (TIER_CANONICAL, TIER_ROLLUP, TIER_ADVISORY, TIER_CONTEXTUAL)

# Claim families recognized by the validator. Centralized here so the
# validator and the contract preamble stay aligned.
CLAIM_FAMILIES = (
    "completed",
    "overdue",
    "at_risk",
    "next_action",
    "fix_priority",
)


def section_header(tier: str, title: str) -> str:
    """Format a single section header. Always emits the tier marker.

    The marker is `[TIER:<tier>]` followed by the section title. The
    LLM is instructed by the preamble to read every `[TIER:...]` line
    as a binding declaration of the section that follows.
    """
    if tier not in ALL_TIERS:
        # Defensive: an unknown tier is a programming error. Log via
        # a sentinel marker so the validator and operator can spot it.
        tier = f"INVALID:{tier}"
    return f"[TIER:{tier}] {title}"


def narration_contract_preamble() -> str:
    """The preamble inserted at the very top of the chat system prompt.

    This text is the contract between the system and the LLM. Every
    section appearing later carries a [TIER:...] header that binds the
    LLM to the rules below.

    The preamble is intentionally short and direct. Long preambles get
    skimmed; this one is meant to be read.
    """
    return (
        "=" * 64 + "\n"
        "NARRATION CONTRACT (READ FIRST — APPLIES TO ALL SECTIONS BELOW)\n"
        + "=" * 64 + "\n\n"
        "Each section below is tagged with [TIER:<tier>]. The tiers have\n"
        "STRICT authority rules:\n\n"
        "  canonical_item_truth — The ONLY authority for whether an item\n"
        "    is completed, overdue, recoverable, at risk, or 'next.'\n"
        "    Quote it verbatim. Do not paraphrase the item state.\n\n"
        "  rollup_summary — A domain-level or window-level aggregate.\n"
        "    Reports counts and booleans about a GROUP. NEVER convert a\n"
        "    rollup label into a per-item completion claim. 'prayer: DONE'\n"
        "    means 'the prayer rollup is satisfied today' — it does NOT\n"
        "    mean a specific routine item titled 'Prayer Time' or 'Wake\n"
        "    up' has been checked.\n\n"
        "  advisory — Suggestions, recommendations, maintenance plans.\n"
        "    NEVER use advisory content to determine what is done,\n"
        "    overdue, at risk, or what action to take next.\n\n"
        "  contextual — Background information (time-of-day, signals,\n"
        "    goals, learning). NEVER override canonical_item_truth with\n"
        "    contextual content.\n\n"
        "STATE DETERMINATION RULES (STRICT):\n"
        "  • 'X is done'          ⇐ ONLY a canonical_item_truth section\n"
        "                            asserting X completed.\n"
        "  • 'X is overdue'       ⇐ ONLY canonical_item_truth tagging X\n"
        "                            overdue.\n"
        "  • 'X is at risk'       ⇐ ONLY a canonical at_risk_actions\n"
        "                            entry for X.\n"
        "  • 'next action is X'   ⇐ ONLY the canonical NEXT ACTION line.\n"
        "  • 'fix X first'        ⇐ ONLY the canonical FIX line.\n\n"
        "If a rollup_summary and a canonical_item_truth section disagree,\n"
        "canonical wins. If a rollup_summary has no matching canonical\n"
        "entry, narrate the rollup AS a rollup ('morning medications are\n"
        "2/3 done') — NEVER infer which specific dose was taken.\n\n"
        "DEFAULT TIER FOR UNTAGGED SECTIONS:\n"
        "  Any section in this prompt that does NOT carry an explicit\n"
        "  [TIER:...] header is treated as 'contextual' by default. It\n"
        "  cannot determine state, urgency, completion, or selection.\n"
        + "=" * 64
    )


# ── Validator helpers ──────────────────────────────────────────────
# Centralized so the validator and contradiction telemetry agree.

def is_canonical_tier(tier: str) -> bool:
    return tier == TIER_CANONICAL


def is_rollup_tier(tier: str) -> bool:
    return tier == TIER_ROLLUP


def is_state_determining_tier(tier: str) -> bool:
    """Whether a tier may settle 'completed/overdue/at risk/next/fix'
    questions about specific items.

    Currently only canonical_item_truth qualifies.
    """
    return tier == TIER_CANONICAL
