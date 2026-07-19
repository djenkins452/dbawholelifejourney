# WLJ Chief-of-Staff Domain Certification Standard

**Status:** RATIFIED 2026-07-19 (extracted from the Nutrition and Journal certifications).
**Scope:** the repeatable process for bringing any Layer-1 truth domain to Chief-of-Staff
conversational completeness. This is the engineering standard for **every future CoS
domain** (Faith is next). It sits alongside `docs/LAYER1_DOMAIN_FRAMEWORK.md` (which
certifies the *truth*) and `docs/WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md` (Truth → Reasoning →
Action → Experience). This doc governs the *conversational* certification of a domain.

---

## The Five Steps (in order — never skip, never reorder)

Each step ends only when the one below it can begin honestly. Do not implement past the
first failing layer.

### 1. Verify deterministic truth
Prove — with a runtime trace, not a guess — what deterministic truth the domain already
holds: its canonical `*Queries`/producers, its `DomainTruth` surfaces (`current` /
`history` / `describe` / `state`), and what the domain's own page/UI already shows.
Output: a map of *what exists* vs *what is genuinely missing*.

### 2. Expose existing truth (exposure, not construction)
Before building anything, ask the Meal question: **does the truth already exist and is it
merely unexposed?** Almost always yes. Expose it through the EXISTING shared surfaces —
declare `entity_types` / `history_metrics` / `analysis_subjects` that REUSE the canonical
producers. Zero new retrieval, zero reasoning in WLJ. Build genuinely-new deterministic
truth only when Step 1 proved it missing, and only as the smallest domain-owned aggregate
(never a reasoning engine, never free-text extraction).

### 3. Validate conversational routing
Truth being exposed is necessary, not sufficient. Run the real model and confirm it
*discovers and selects* the right tool/domain/subject. Routing failures are a DIFFERENT
layer from truth: tool selection, domain selection, **capability discovery**, entity
discovery. Fix them through **authoritative, drift-proof metadata** — the machine-readable
capability declaration and the plain-language routing semantics must be derived from ONE
source so they can never drift. Never a per-question prompt patch.

### 4. Production validation (Danny's gate)
Local certification with the real model is engineering evidence ONLY. The milestone is
`AWAITING VALIDATION` until Danny runs the questions in production against real data and
explicitly confirms. Impl + tests + deploy ≠ complete.

### 5. Close the milestone
Only after Danny's explicit production confirmation: mark complete, update roadmap/status/
changelog, remove milestone TODOs and any temporary diagnostics, confirm tests green and
the deployed SHA, and write a short post-mortem. Then STOP — do not roll into the next
domain.

---

## Invariants that held across Nutrition and Journal

- **Exposure beats construction.** Meal, nutrition analysis, and journal analysis were all
  *exposure* of existing truth (`get_meal_totals`, macro/mood history, `describe`) — not new
  intelligence. The one genuinely-new aggregate (nutrition `top_foods`) was small and
  domain-owned.
- **WLJ never renders a verdict.** WLJ supplies the deterministic evidence bundle; the model
  summarizes / interprets / advises / judges. WLJ never deterministically labels anything
  healthy, concerning, positive, successful, or a commitment.
- **Two advertising layers must be ONE source.** A capability declared in the catalog but not
  surfaced in the plain-language routing metadata is invisible to the model. Derive the
  routing metadata from the declaration; assert alignment in a contract test so it cannot
  silently drift.
- **Retrieve vs. search vs. analyze are distinct tools.** Chronological/latest → `get_entity`
  /`get_domain_state`; content/keyword ("entries mentioning X") → `search_history`; analytical
  synthesis ("themes / trends / patterns / advice about my records") → `get_analysis`. Keep
  the boundaries discoverable through tool contracts, not hardcoded per question.
- **Fix the first failing layer, bounded by blast radius.** Trace to the first divergence and
  fix only that; prefer removing the condition that made the whole class possible over adding
  a detector.
