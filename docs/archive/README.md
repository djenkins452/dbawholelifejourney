# Archived Documents

These documents are preserved for historical rationale but **no longer describe the
current architecture.** They predate the 2026-07-09 architecture pivot in which WLJ
stopped building its own conversational reasoning layer.

**Current canonical architecture:** `../WLJ_LLM_TRUTH_ACTION_CONTRACT.md`
(WLJ owns deterministic truth, preferences, history, actions, audit; a provider-agnostic
conversational model owns reasoning and conversation).

Do not treat anything here as governing. Read it only to understand *why* prior
decisions were made.

## Contents

- **`CoSEvaluation.md`, `CoSEvaluation_v2..v8.md`** — the iterative point-in-time
  evaluations of the retired Chief-of-Staff reasoning/lane architecture. Durable lesson
  (that the model authors coherently while WLJ-assembled fragments contradict) is
  carried forward in `WLJ_LLM_TRUTH_ACTION_CONTRACT.md` §3.1 and the reframed
  `WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md`.
- **`ARCHITECTURE_EVOLUTION_ASSESSMENT/REFINEMENT/FINAL/IMPLEMENTATION_BLUEPRINT.md`** —
  the evolution planning series for the retired orchestration model.

## Recommended for a future archive pass (not yet moved — needs a link-check)

The broader "build-Beth's-brain" corpus (`BETH_CONVERSATION_*`, `COS_*_PLAN/REPORT`,
`PHASE4/5/8_*`, `UAL_V2_*`, `UNIVERSAL_ARBITRATION_*`, `EXECUTIVE_OPERATOR_*`,
`cos_context_architecture.md`, `cos_full_picture_report.md`,
`cos_persistent_learning_upgrade.md`, `WLJ_SYSTEM_INTELLIGENCE_STATE.md`,
`SYSTEM_AUDIT_2026_03_14.md`, `BETH_PHASE0_SHADOW_CLASSIFIER_PLAN.md`,
`BETH_DIAGNOSTIC_REPORT.md`) is a candidate for archival after extracting any deterministic
truth-inventory content, but was left in place this pass to bound blast radius and allow a
dedicated cross-reference check first.

*Archived: 2026-07-09 (Phase I of the LLM truth/action realignment).*
