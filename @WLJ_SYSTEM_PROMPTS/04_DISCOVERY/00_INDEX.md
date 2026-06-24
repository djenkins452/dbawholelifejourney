# WLJ System Discovery — Architecture Knowledge Model

**Mission:** Build a complete architectural knowledge model of the existing Whole Life Journey (WLJ) platform so an external conversational layer (ChatGPT) can reason holistically over the user's life **while the existing WLJ platform is preserved unchanged.**

**Method:** Read-only investigation across 30+ Django apps and ~28 `ai_*` intelligence packages, using a fan-out of subagents. Every detailed claim is proven with `file:line` references. Discrepancies between the existing reference docs and the actual code are recorded in each document's "gaps" section rather than silently reconciled.

**Constraint honored:** No code, data, models, engines, signals, state, dashboards, integrations, or user data were modified. This is documentation only — no redesign, no recommendations, no implementation plans.

---

## The Six Required Deliverables

| # | Document | File |
|---|----------|------|
| 1 | **WLJ System Architecture Overview** — whole-system mental model | [01_System_Architecture_Overview.md](01_System_Architecture_Overview.md) |
| 2 | **WLJ Domain & Data Catalog** — every domain's models, state, signals, APIs, UI (3 parts) | [02a](02a_Domain_Catalog_Health_Medical_Meals_Faith_Journal.md) · [02b](02b_Domain_Catalog_Purpose_Life_Calendar_Relationships_Finance.md) · [02c](02c_Domain_Catalog_Capture_Notes_Sports_BrainTraining_Misc.md) |
| 3 | **WLJ Engine Catalog** — 50+ engines: phase, cadence, status, file locations | [03_Engine_Catalog.md](03_Engine_Catalog.md) |
| 4 | **WLJ Context & Intelligence Pipeline** — how context reaches the LLM; current-state computation; history/memory | [04_Context_Intelligence_Pipeline.md](04_Context_Intelligence_Pipeline.md) |
| 5 | **WLJ UI & Dashboard Catalog** — every user-facing surface + its data sources | [05_UI_Dashboard_Catalog.md](05_UI_Dashboard_Catalog.md) |
| 6 | **WLJ ChatGPT Chief of Staff Readiness Assessment** — access needs, existing context, truth providers, gaps | [08_ChatGPT_CoS_Readiness_Assessment.md](08_ChatGPT_CoS_Readiness_Assessment.md) |

**Supporting reference (investigation areas 7–9):**

| Document | File |
|----------|------|
| **Integrations & Personalization Inventory** (areas 7 & 8) | [06_Integrations_and_Personalization.md](06_Integrations_and_Personalization.md) |
| **Chief of Staff (Beth) Dependency Analysis** (area 9) — reuse classification | [07_CoS_Dependency_Analysis.md](07_CoS_Dependency_Analysis.md) |

---

## Reading Order

1. **Start with [01](01_System_Architecture_Overview.md)** for the whole-system model.
2. **[02a/02b/02c](02a_Domain_Catalog_Health_Medical_Meals_Faith_Journal.md)** for what data exists and where each domain's truth lives.
3. **[03](03_Engine_Catalog.md)** for the intelligence engines.
4. **[04](04_Context_Intelligence_Pipeline.md)** for how it all reaches the conversation.
5. **[05](05_UI_Dashboard_Catalog.md)** for user-facing surfaces, **[06](06_Integrations_and_Personalization.md)** for integrations/personalization.
6. **[07](07_CoS_Dependency_Analysis.md)** then **[08](08_ChatGPT_CoS_Readiness_Assessment.md)** for the CoS boundary and readiness picture.

---

## Authoritative Companions (pre-existing, in `../03_REFERENCE/`)

These were treated as authoritative framing and verified against code:

- **WLJ ARCHITECTURE LAWS** — the 16 non-negotiable rules (truth hierarchy, phase boundaries, deterministic rendering, narration contract).
- **WLJ DOMAIN REGISTRY** — canonical domain list and classification.
- **WLJ SIGNAL ONTOLOGY** — `UnifiedSignal` shape, priority tiers, source precedence.

In-repo authoritative docs cross-referenced: `docs/INTELLIGENCE_ARCHITECTURE.md`, `docs/DOMAIN_INTELLIGENCE_ARCHITECTURE.md`, `docs/ENGINE_COS_REFERENCE.md`, `docs/ENGINE_INTEGRATION_GUIDE.md`, `docs/WLJ_VISUAL_TRUTH_CONTRACT.md`.

---

## Cross-Cutting Findings Worth Carrying Forward

These verified facts recur across the catalog and matter to any consumer of WLJ data:

- **Truth lives below the chat agent.** Only ~4 OpenAI chat call sites exist; everything that determines state/execution/risk is deterministic and CI-purity-guarded. The conversational CoS is a renderer, not the brain.
- **`CosDecisionView` (`/api/cos/decision/`) is the existing model** of a fully-deterministic, externally-consumable CoS surface ("NO LLM").
- **Some truth lives where you wouldn't expect by name:** medication adherence + medical providers are in `apps/health` (not `apps/medical`); there is no `Medication` model (`Intake` is unified med+supplement).
- **The assistant name is user data** (`UserPreferences.cos_display_name`, default `"Chief of Staff"`). "Beth" is one user's value — not a system default.
- **`dashboard_v3` is the production default** (env-gated, with v2 preserved as instant rollback).
- **HealthKit is the canonical glucose path;** Dexcom OAuth is deprecated; the ~3h CGM lag is upstream of WLJ.
- **Doc drift exists** (e.g., EAE = "Executive Arbitration Engine" in code, not "Evidence Aggregation"; ISE registry = 35 tasks, not "43+"). Code is authoritative; the catalogs record verified values.

---

*Generated: read-only WLJ architecture discovery session. Output is descriptive knowledge extraction only.*
