# WLJ Documentation Inventory

**Status:** CURRENT · Milestone artifact (2026-07-11)
**Purpose:** Classify every doc so the current architecture is unambiguous and engineering history is preserved (never deleted). Anchored on the 2026-07-09 pivot: **WLJ owns deterministic truth; the conversational model owns reasoning.** A doc whose core thesis is a reasoning/conductor/classifier engine *inside* WLJ, or that treats a user AI name ("Beth") as a fixed system identity, is **HISTORICAL**.

---

## 1. Summary

| Classification | Count | Meaning |
|---|---|---|
| CURRENT | 97 | Describes today's design; authoritative |
| HISTORICAL | 39 | Real past design, no longer current; preserved as history (banner applied) |
| SUPERSEDED | 3 | Replaced by a named successor |
| ARCHIVE | 49 | Completed one-off reports/handoffs/trackers |
| **Total** | **188** | |
| MISSING | 3 real + 7 stale-path | Referenced but absent / relocated |

**Milestone action taken:** the clearly-historical reasoning-engine docs receive the standard banner (see §4). The **uncertain** set (§6) is intentionally NOT auto-classified — it requires Danny's judgment because several are still linked as CURRENT from `CLAUDE.md`.

---

## 2. HISTORICAL (39) — retired reasoning-in-WLJ / "Beth engine" framing

These describe the retired approach where WLJ contained the reasoning/conductor/lanes/classifier that drove the turn. They are preserved for rationale and receive the HISTORICAL banner.

`BETH_ARCHITECTURAL_PRINCIPLES` · `BETH_CHANGE_CONTROL` · `BETH_GOLDEN_BEHAVIORS` · `BETH_ROLLBACK_AND_RECOVERY` · `BETH_REGRESSION_TEST_MATRIX` · `BETH_PRODUCTION_VALIDATION_CHECKLIST` · `BETH_CONVERSATION_LANES` · `BETH_CONVERSATION_PLANNING_DESIGN` · `BETH_DOMAIN_REASONING_FRAMEWORK` · `BETH_HEALTH_INTENT_CONTRACTS` · `BETH_P25_PERSONAL_TRUTH_FIRST` · `BETH_PHASE0_SHADOW_CLASSIFIER_PLAN` · `BETH_PERSONAL_KNOWLEDGE_DESIGN` · `BETH_PERSONAL_UNDERSTANDING_ONTOLOGY` · `BETH_GOLD_STANDARD_ACCEPTANCE` · `BETH_CHIEF_OF_STAFF_ACCEPTANCE_SUITE` · `BETH_DOMAIN_DEPENDENCY_GRAPH` · `BETH_DOMAIN_MATURITY_MATRIX` · `BETH_TRUTH_COVERAGE_AUDIT` · `BETH_TRUTH_GAP_ANALYSIS` · `BETH_HOLISTIC_TRUTH_ROADMAP` · `cos_context_architecture` · `PHASE_8_EAE_DESIGN_SPEC` · `WLJ_DOCUMENTATION_SUITE` · `archive/ARCHITECTURE_EVOLUTION_FINAL` · `archive/ARCHITECTURE_EVOLUTION_IMPLEMENTATION_BLUEPRINT`

*(The above 26 are clearly historical and are bannered. The remaining HISTORICAL candidates from the audit — `INTELLIGENCE_ARCHITECTURE`, `DOMAIN_INTELLIGENCE_ARCHITECTURE`, `ENGINE_COS_REFERENCE`, `ENGINE_INTEGRATION_GUIDE`, `LAYER2_CONSTITUTION`, `LAYER2_CERTIFICATION`, `LAYER2_INVENTORY`, `COMPARISON_SEMANTICS_MATRIX`, `CONVERSATION_OBJECT_MATRIX`, `INTENT_FULFILLMENT_MATRIX`, `BETH_LAYER1_TRUTH_INVENTORY`, `assistant/SELF_IMPROVEMENT`, `assistant/RUNBOOK`, `WLJ_WHOLE_LIFE_EXECUTIVE_UNDERSTANDING` — are held in §6 for human judgment because they are either CLAUDE.md-linked or formally "certified & frozen," and mislabeling a possibly-current doc is worse than deferring.)*

## 3. SUPERSEDED (3)

| File | Successor |
|---|---|
| `WLJ_EXECUTIVE_CONTEXT_ENVELOPE_DESIGN.md` ("ABSORBED 2026-07-09") | `WLJ_MODEL_INTERFACE_DESIGN.md` |
| `archive/ARCHITECTURE_EVOLUTION_ASSESSMENT.md` | `archive/ARCHITECTURE_EVOLUTION_FINAL.md` |
| `archive/ARCHITECTURE_EVOLUTION_REFINEMENT.md` | `archive/ARCHITECTURE_EVOLUTION_FINAL.md` |

## 4. The HISTORICAL banner

Every file in §2 is prefixed with:

```
> ⚠️ HISTORICAL ARCHITECTURE — NOT CURRENT DESIGN.
> DO NOT RESTORE WITHOUT CONSTITUTIONAL REVIEW (docs/WLJ_CONSTITUTION.md §3).
> Predates the 2026-07-09 truth/reasoning pivot. Preserved as engineering history.
```

Engineering history is **never deleted** — only labeled.

## 5. CURRENT (95) — the authoritative set

The 95 current docs are the governing + reference set. The apex is `WLJ_CONSTITUTION.md`; the governing docs are `WLJ_PRODUCT_VISION`, `WLJ_LLM_TRUTH_ACTION_CONTRACT`, `WLJ_ARCHITECTURE_LAWS`, `WLJ_CONDUCTOR_DEVELOPMENT_MODEL`, `WLJ_CURRENT_CONTEXT_CONTRACT`, `WLJ_VISUAL_TRUTH_CONTRACT`, `WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE`, `LAYER1_DOMAIN_FRAMEWORK`. The rest are live domain/reference/operational docs (Legacy, Medication, Security suite, Signal taxonomy, SAE contract, iOS, Bible plans, billing, calendar, finance, etc.) plus the milestone docs added today (`WLJ_CONSTITUTION`, `WLJ_ACCEPTANCE_BASELINE`, `WLJ_OPS_WALL_COVERAGE`, `WLJ_CURRENT_CONTEXT_HELP_COVERAGE`, `WLJ_DOCUMENTATION_INVENTORY`, `WLJ_RELEASE_POLICY`, `WLJ_PRODUCTION_RUNBOOKS`, `WLJ_SECURITY_PRIVACY_RETENTION`, `WLJ_KNOWN_LIMITATIONS`, `WLJ_MILESTONE_COS_ARCHITECTURE`). Full per-file reasons are in the milestone audit record.

**Added 2026-07-11:** `WLJ_OPERATIONS_VISION` — the governing (living) design document for the new
**WLJ Operations** subsystem (a Layer 1 truth domain; 9-phase roadmap + maintained status ledger).
CURRENT and self-maintaining per its own §11 Claude-responsibilities contract. Companion engineering
plan `WLJ_OPERATIONS_PHASE2_PLAN.md` (Phase II Deterministic Recovery blueprint + risk register) —
CURRENT PLAN, not yet implemented.

## 6. Uncertain — REQUIRES DANNY'S JUDGMENT (not auto-classified)

These sit on the CURRENT/HISTORICAL/SUPERSEDED boundary. **Decide before bannering:**

1. `INTELLIGENCE_ARCHITECTURE.md`, `DOMAIN_INTELLIGENCE_ARCHITECTURE.md`, `ENGINE_COS_REFERENCE.md`, `ENGINE_INTEGRATION_GUIDE.md` — "14-engine cognitive stack / THE CONDUCTOR" framing reads HISTORICAL, **but all are linked as authoritative from `CLAUDE.md`** and the underlying SAE/signal engines are surviving truth infrastructure. Likely "CURRENT-but-stale" needing a refresh, not retirement. **If retired, CLAUDE.md must be updated in the same change.**
2. `LAYER2_CONSTITUTION`, `LAYER2_CERTIFICATION`, `LAYER2_INVENTORY` — "Executive Reasoning reasons over truth in WLJ" (certified 2026-06-30, pre-pivot). HISTORICAL vs SUPERSEDED-by-`WLJ_LLM_TRUTH_ACTION_CONTRACT`.
3. `COMPARISON_SEMANTICS_MATRIX`, `CONVERSATION_OBJECT_MATRIX`, `INTENT_FULFILLMENT_MATRIX` — deterministic answer/comparison machinery (arguably CURRENT truth) wrapped in "Beth answers" framing.
4. `BETH_LAYER1_TRUTH_INVENTORY` — hybrid; names `LAYER1_CONSTITUTION` as the new entry point → likely SUPERSEDED.
5. `assistant/SELF_IMPROVEMENT`, `assistant/RUNBOOK` — older self-improvement system; likely SUPERSEDED by `WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE`.
6. `WLJ_WHOLE_LIFE_EXECUTIVE_UNDERSTANDING` — recent north-star but opens with "Beth must behave like…" identity framing; borderline.
7. `NUTRITION_LOG_UPGRADE_PLAN / UI_REDESIGN / USABILITY_CHECKLIST` — if the redesign shipped, these are ARCHIVE not CURRENT.
8. `WLJ_Data_Dictionary` (2026-03) — may be stale against current schema.
9. `CISO_SECURITY_PROJECT_MASTER_PROMPT` — one-off generator prompt → possibly ARCHIVE.

## 7. MISSING / stale-path references (housekeeping)

**Truly missing:**
- `docs/business/README.md` and `docs/business/MASTER_PROMPT.md` — referenced by `wlj_claude_beacon.md`; `docs/business/` does not exist.
- `docs/wlj_claude_original_backup.md` — referenced historically; intentionally deleted (contained a hardcoded key). Expected absence.

**Stale paths (file moved to `docs/archive/`, callers still point at `docs/` root):**
- `ARCHITECTURE_EVOLUTION_FINAL.md`, `CoSEvaluation_v3.md … v8.md` — referenced by `ENGINE_COS_REFERENCE.md` and the changelog at their old root paths.

*Fix these references opportunistically when touching the citing docs; they are not milestone blockers.*
