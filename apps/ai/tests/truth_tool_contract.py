# ==============================================================================
# File: apps/ai/tests/truth_tool_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: THE approved truth-tool set, in one place.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""One list, imported by every contract that guards the truth-tool surface.

Two tests held separate copies of this set (`test_personal_truth` and
`test_principles_not_prescriptions`), which is how both could sit red together while a
third file added tools — the same duplication that let the lane registry drift.

Adding a tool here is a deliberate act: the point of the contract is that the surface
the model sees cannot grow by accident.

REVIEWED 2026-09-02: `get_consistency`, `get_change_point` and `get_ranked_entity` are
the reusable capabilities from the Health Knowledge certification; `get_data_health`
answers "is this domain actually reporting"; `get_execution_review` is the day-review
surface. All five are registered and exercised by their own tests — the lists simply
never learned about them.
"""

APPROVED_TRUTH_TOOLS = {
    "get_domain_state",
    "search_history",
    "get_history",
    "get_readings",
    "get_event_frequency",
    "get_comparison",
    "get_adherence",
    "get_entity",
    "get_analysis",
    "get_user_truth",
    "get_foundational_health_facts",
    "get_consistency",
    "get_change_point",
    "get_ranked_entity",
    "get_data_health",
    "get_execution_review",
}
