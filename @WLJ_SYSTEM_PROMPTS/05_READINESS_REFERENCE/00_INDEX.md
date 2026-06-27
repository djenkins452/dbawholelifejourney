# WLJ — Holistic Context Readiness Audit for ChatGPT CoS

**Question:** Does WLJ already expose sufficient deterministic truth for ChatGPT to operate as Danny's primary holistic Chief of Staff — capable of answering questions like *"Why has my weight loss slowed down?"* from deterministic truth, not LLM guessing?

**Method:** Read-only code verification (3 focused subagents over SAE state builders, the retrieval/search/screen layer, and the cross-domain reasoning path). Code is authoritative. Every claim carries `file:line` evidence. No code, data, or infrastructure was modified or proposed.

---

## Deliverables

| # | Document | File |
|---|----------|------|
| 1 | **Holistic Context Readiness Matrix** — every proposed `get_*_context()` / `search_*()` function graded COMPLETE/PARTIAL/MISSING | [01_Holistic_Context_Readiness_Matrix.md](01_Holistic_Context_Readiness_Matrix.md) |
| 2 | **Deterministic Truth Gap Analysis** — all missing providers, split into TRUTH / WIRING / SERIALIZATION gaps | [02_Deterministic_Truth_Gap_Analysis.md](02_Deterministic_Truth_Gap_Analysis.md) |
| 3 | **Cross-Domain Reasoning Readiness** — can WLJ deterministically explain weight/stress/productivity/motivation/routine changes? | [03_Cross_Domain_Reasoning_Readiness.md](03_Cross_Domain_Reasoning_Readiness.md) |
| 4 | **Recommended Minimal Context Package** — the minimal always-loaded deterministic context, mapped to existing providers | [04_Recommended_Minimal_Context_Package.md](04_Recommended_Minimal_Context_Package.md) |

Builds on the system discovery in `../04_DISCOVERY_REFERENCE/`.

---

## The Verdict in Three Sentences

1. **The deterministic truth substrate is largely present** — SAE computes per-domain state for every domain, 7 of 10 cross-domain reasoning factors are deterministically computed, and a real law-compliant root-cause composer exists for the weight question.
2. **The access surface is not** — almost none of the state is serialized over HTTP for an external consumer, two complete deterministic search engines are dead code (zero callers), and content/text (journal bodies, transcripts, action items) is absent from state.
3. **Holistic assembly is the bottleneck, not truth** — the one root-cause composer ingests only 5 physical-health domains, stranding 6 computed factors (stress, travel, routine, execution overload, relationship, calendar); CDCE is fixed-detector, weight-blind, and decoupled from it.

**Bottom line:** WLJ *possesses* enough deterministic truth to begin holistic CoS reasoning, but does not yet *expose or assemble* it into a holistic answer beyond a narrow physical-health core. The dominant gaps are **wiring, serialization, and composition aperture** — not absent intelligence.

---

## Highest-Signal Findings (all `file:line`-proven inside)

- **Two full deterministic search engines are unwired dead code:** `SearchService` (unified + 7 per-domain searchers, `apps/ai/search_service.py:30`) and `search_notes_cos` (hybrid FTS+embeddings, `apps/notes/services.py:419`). Both have zero production callers — invisible to the CoS.
- **No HTTP serialization of SAE module state.** `get_module_state` (`state_engine.py:74`) is internal-only; the only exposed deterministic surfaces are calendar APIs, `CosDecisionView`, and a summarized state endpoint.
- **The weight root-cause composer is real but 5-domain-bound:** `_render_structured_assessment` (`apps/ai/deterministic_router.py:6279`), filter `rel = {sleep, nutrition, workouts, glucose, medication}` (`:6308`), `_ROOT_CAUSE_RULES['weight']` = 2 rules (`:6204`). Stress, travel, routine, execution-overload, relationship, and calendar are computed elsewhere but never reach it.
- **CDCE runs 7 hardcoded detectors** (`cdce_engine.py:893`), none weight-related, and is decoupled from the root-cause composer.
- **SAE stores aggregates/verdicts, not text** — journal entry bodies, reflections, saved verses, interaction logs, capture action items are absent from deterministic state.
- **`get_screen_context` exists in-app** (DOM-scrape → `page_context` → page-awareness prompt, `personal_assistant.py:166`) but is per-page-type and not reachable by an external CoS.
- **The minimal always-loaded context is already computed** — it is essentially the output of `build_cos_context` / `build_executive_context`; the open problem is exposing it, not computing it.

---

*Read-only audit. Descriptive only — no implementation, redesign, or infrastructure proposed.*
