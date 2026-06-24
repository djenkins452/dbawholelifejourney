# WLJ ChatGPT Chief of Staff — Readiness Assessment

**Document 6 of 6 — WLJ System Discovery & Architecture Knowledge Extraction**

Purpose: Without recommending solutions, identify (a) what an external ChatGPT Chief of Staff would need access to, (b) what context already exists, (c) what deterministic truth providers already exist, and (d) what information gaps currently exist.

This document is **objective and descriptive only**. It proposes no integration design, no implementation plan, and no changes to WLJ. It is the factual readiness picture that any future joint decision (Danny + ChatGPT + Claude) would build on. All underlying claims are proven with `file:line` in companion docs 02–07.

Governing constraint (from the assignment): the WLJ platform — data models, domains, engines, pipelines, signals, storage, UI, telemetry, dashboards, APIs, and user data — is **not changing**. The only layer under reconsideration is the **conversational Chief of Staff experience.**

---

## 1. What a ChatGPT Chief of Staff Would Need Access To

For ChatGPT to reason over the user's complete life *the way Beth does today*, it would need to consume the same five-tier truth stack the in-process CoS consumes (Architecture Laws 1–2). Stated as access requirements, not solutions:

| Need | What it means | Where WLJ already produces it |
|------|---------------|-------------------------------|
| **Canonical current state** | Per-domain "where things stand now" without re-querying raw rows | SAE — `build_*_state()`, `get_module_state`/`get_metric` (`apps/core/ai_state/`) |
| **Execution / "today" truth** | What's done, overdue, recoverable; next action; biggest risk; fix priority | `execution_truth_engine.py:81`, `today_execution.py:34`, `execution_state.py:46`, `selectors.py:145/254/326` |
| **Signals** | Deterministic interpretations across domains, prioritized & deduped | `unified_feed.py`, `signal_renderer.py` |
| **Composed CoS context** | A single structured object blending the above for narration | `build_cos_context` (`ai_orchestrator/cos_context.py`), `build_cos_intelligence` (`cos_intelligence.py:253`) |
| **History & memory** | Trends, prior insights/briefings, personal facts | `UserState`, `DailyBriefing`, `Insight`/`Prediction`/`GuidanceItem`, `PersonalFact`/`ContextSnapshot` (`ai_memory/`) |
| **Personalization** | Preferences, feature flags, assistant name, notification prefs | `UserPreferences` (`apps/users/models.py`), `context_processors.py` |
| **Action execution (if it is to *do* things, not just advise)** | The write path that mutates domain state | UAIO Phase-2 path: intent → `intent_service.execute_intent` → `action_handlers` |
| **Identity / auth scoping** | Per-user data isolation | allauth user model + entitlements (`apps/users`, `apps/billing`, `apps/security`) |

Two distinct capability levels are implied by the above and worth separating factually:

- **Advisory CoS** (read-only): needs tiers 1–6 only. Everything required already exists as deterministic, structured output.
- **Acting CoS** (read + write): additionally needs the Phase-2 execution path, which today is tightly bound to the OpenAI function-calling loop (see §4).

---

## 2. What Context Already Exists

WLJ is unusually well-prepared on the **read** side. The context an external CoS would narrate over is already computed, structured, and (in several cases) already serialized:

### 2.1 Already-structured state objects
- `build_cos_context` / `build_executive_context` return a **full state dict** (not prose) — the same object the current prompt assembly consumes (`cos_context.py`).
- `build_cos_intelligence` (`cos_intelligence.py:253`) is the "standing" composed CoS read — consistent with the platform rule that the CoS consumes composed briefings, not raw signals.
- SAE `build_*_state()` builders return structured per-domain state for health, faith, journal, goals/habits, execution, capture, etc. (`state_builder.py`, `MODULE_BUILDERS` registry `:5576`).

### 2.2 Already-serialized, LLM-free HTTP endpoints
These already return clean structured state to an HTTP caller with **no LLM in the path** (07 §endpoints):

| Endpoint | Returns | LLM? |
|----------|---------|------|
| `CosDecisionView` — `/api/cos/decision/` | Deterministic decision (execution/risk/fix), explicitly "NO LLM" (`views.py:2230`) | None |
| `DriftDetectionView` | Drift telemetry | None |
| `DailyPrioritiesView` | Day's priorities | None |
| `WeeklyAnalysisView` / `MonthlyAnalysisView` | Period rollups | None |
| `GoalProgressView` | Goal progress | None |
| Domain JSON APIs (e.g., `calendar_engine`) | Time blocks, events, balance | None |

`StateAssessmentView` is **mixed** (SAE metrics + a cached LLM synthesis). The chat endpoints (`/api/chat/`, `/api/chat/stream/`, `/api/briefing/`) wrap LLM narration but already ship a structured sidecar (`actions_taken` / `options` / `navigation`).

### 2.3 Already-stored history
Persistent history exists and is queryable: `UserState` snapshots, `DailyBriefing` (one/day, snapshotted), the `Insight`/`Prediction`/`GuidanceItem` inboxes, and the memory models (`PersonalFact` permanent, `LearnedMapping`, `ContextSnapshot`, `ClarificationLog`). Notes provides a searchable long-term knowledge layer (FTS + embeddings).

**Conclusion for §2:** the holistic, cross-domain, time-aware life picture an external CoS would need *already exists as deterministic output today*. `CosDecisionView` is the clearest existing proof that WLJ can expose a fully deterministic, externally-consumable CoS surface.

---

## 3. What Deterministic Truth Providers Already Exist (Crown Jewels)

These are the ~17 components that compute truth with **zero LLM** and are the assets WLJ wants to preserve (07, full table). They are the substrate any conversational layer — Beth or ChatGPT — narrates over:

- **State:** SAE `state_builder.py`, `metric_access.py:46`
- **Signals:** `signal_renderer.py`, `unified_feed.py`
- **Execution:** `execution_state.py:46`, `selectors.py:145/254/326`, `execution_truth_engine.py:81` (Law 14)
- **Recoverability:** `task_classifier.py:100`, `recoverability.py:85` (Law 15)
- **Locked facts:** `cos_fact_statements.py:22`
- **Validators (governance):** `cos_truth_validator.py:94`, `contradiction_telemetry.py:95`, `narration_contract_validator.py`
- **Situational awareness:** `situational_awareness.py:534`, `situation_computer.py:23`, `right_now.py:133`
- **Composed reads:** `cos_intelligence.py:253`
- **Mode routing:** `cos_mode_router.py` (keyword-based; no LLM picks the mode)
- **Active CoS v2 modules** (`apps/cos/`): diagnostic, specificity, temporal, signal_prioritizer, behavior_forecast, goal_gap_analyzer

The truth/narration boundary is **clean and enforced**: only ~4 LLM call sites exist (all in `services.py` / `intent_service.py`), there is a Law-9 allowlist, and a CI purity test guards against raw-query drift. This is the single most important readiness fact: **the intelligence is not in the chat agent.** The chat agent is a renderer of intelligence computed elsewhere.

---

## 4. What Is Coupled to the Current (Beth) Implementation

These components are specific to the in-process OpenAI chat agent and do **not** transfer unchanged to an external conversational layer (07, "tightly coupled" bucket). Listed for completeness — this is a description of coupling, not a removal plan:

- **The chat loop:** `personal_assistant.py` (`send_message` / `send_message_stream`) — orchestrates the OpenAI calls, prompt assembly, post-processing.
- **The only OpenAI chat call sites:** `apps/ai/services.py:424/562`.
- **Intent recognition via function-calling:** `intent_service.py` (`:216`, `:1141`) — OpenAI tool schemas + dispatch.
- **The write path:** `action_handlers.py` (the intent→execute→handler chain, bound to the OpenAI tool schemas and the Law-11 schema-parity chain).
- **Prompt-assembly framing:** `cos_context.format_cos_system_injection`, the narration-contract preamble, LOCKED-STATE and anti-fabrication blocks — these shape *how* the current LLM is constrained.
- **Conversational-only layers:** `apps/core/ai_persona/*` (post-LLM tone), greeting / response governor / optimizer, `tts_service.py`, `cos/services/tone_service.py` + `persona_service.py`.

A nuance worth recording: many providers expose a **structured dict internally but only a prose string at the chat boundary** (`executive_briefing`, `situational_awareness` `format_*_injection`, the `beth_*` renderers). In each such pair, the *dict-producing half* is the reusable deterministic asset; the *string-formatting half* is conversational packaging.

**Obsolete components found:** none. `apps/cos/` (CoS v2 action framework) is fully active — installed (`settings.py:184`) and wired into cos_context, the scheduler, and `personal_assistant`.

---

## 5. Information Gaps (Current, Factual)

These are gaps that exist **today**, stated objectively. They are not framed as problems to fix in this document — they are simply the known edges of the current system, surfaced by the investigation.

### 5.1 Surface / consumability gaps (read side)
- **No single external "give me everything" CoS endpoint.** Clean structured state exists, but it is spread across many endpoints (`CosDecisionView`, drift, priorities, weekly/monthly, goal-progress) plus internal dict-producers reachable only inside the Python chat loop. An external consumer today would assemble the picture from multiple surfaces, not one.
- **Some composed state is prose-only at the boundary.** `executive_briefing`, `situational_awareness`, and the `beth_*` renderers emit narration strings at the chat edge even though they hold a structured dict upstream. The structured form is not currently serialized out.
- **`StateAssessmentView` mixes deterministic metrics with cached LLM synthesis** — i.e., it is not a pure truth surface.

### 5.2 Write-path coupling gap
- **Actions cannot currently be invoked except through the OpenAI function-calling loop.** The Phase-2 execution path (intent → `execute_intent` → `action_handlers`) is bound to the OpenAI tool schemas and the Law-11 parity chain. An "advisory-only" external CoS is fully served by existing reads; an "acting" external CoS would be interacting with a write path that is presently entangled with the in-process LLM agent.

### 5.3 Domain coverage / signal gaps (from the catalogs)
- **Renderer coverage is partial.** Only Health, Medical, Faith, Life are wired to the canonical deterministic renderer; Meals, Purpose, Journal, Capture, Brain Training, Finance, Relationships, Sports, Notes still use bespoke rendering (Domain Registry "Phase 2 candidates").
- **Some domains emit weak or no signals.** Brain Training emits **no** signals and does no logging (pull-only). Sports emits awareness signals but does **not** actually modify routine interpretation (the registry implies it does; the behavior is unimplemented). Travel is a **planned** domain — no app, model, or UI exists; only a `TravelActiveRule` insight stub.
- **Documented-but-absent artifacts.** Several signals/models named in capability docs are not in code (e.g., Journal `GratitudeEntry` + `mood_trend`/`mood_declining` declared in `capabilities.py` but absent; `brain_training/capabilities.py` names non-existent `TrainingSession`/`TrainingScore`). Faith/Journal PIE rule counts are lower in code than docs claim. (Full list in 02a/02c "gaps.")

### 5.4 Attribution gaps (where truth physically lives ≠ where it's expected)
- **Medication adherence and medical providers live in `apps/health`** (`Intake`, `MedicalProvider`), not `apps/medical`. A consumer reasoning by domain name could look in the wrong place. There is **no** standalone `Medication` model — `Intake` is the unified med+supplement model.

### 5.5 Personalization / identity facts to carry forward
- **The assistant name is user data, not a constant.** `UserPreferences.cos_display_name`; default is the neutral `"Chief of Staff"`. "Beth" is one user's value. Any externally-facing CoS would read the name from preferences, not assume it.
- **Owner push delivery is currently inert.** APNs code works, but no `MobileDevice` is registered for the owner, so proactive push no-ops for him (in-app delivery works). This is environmental, not a code defect.

### 5.6 Documentation drift (meta-gap)
- Several reference docs have drifted from code: stale line numbers (`calendar_engine_discovery.md`), an engine name mismatch (**EAE = "Executive Arbitration Engine"** in code vs "Evidence Aggregation" in docs), ISE task count (docs "43+", registry **35**), and a stale scan architecture doc. Code is authoritative; the discovery catalogs (02–07) record the verified values.

---

## 6. Readiness Summary

| Dimension | Current readiness (factual) |
|-----------|------------------------------|
| **Deterministic life-state computation** | Exists and is mature. ~17 LLM-free truth providers; CI-guarded purity boundary. |
| **Structured context for narration** | Exists as dicts (`build_cos_context`, `build_cos_intelligence`, SAE builders). |
| **Externally-consumable (serialized) read surfaces** | Partially exists — several pure-deterministic JSON endpoints (`CosDecisionView` is the model case); not yet unified, and some composed state is prose-only at the edge. |
| **History / memory** | Exists and is persisted (UserState, DailyBriefing, Insight/Prediction/Guidance, PersonalFact, Notes). |
| **Personalization / identity** | Exists (UserPreferences, feature flags, user-configurable assistant name). |
| **Integrations (life-data inflow)** | Exist and are unchanged (HealthKit canonical, Stripe, Twilio, allauth/MFA, Google). |
| **Action / write path** | Exists but is coupled to the in-process OpenAI function-calling loop. |
| **Coverage uniformity** | Uneven — foundational domains rich; several domains render bespoke or emit weak/no signals; Travel unbuilt. |

**Bottom line (descriptive):** the holistic intelligence an external ChatGPT Chief of Staff would narrate over is *already computed deterministically and already preserved in WLJ's state/signal/execution layers*. The current Beth implementation is a thin, well-bounded conversational renderer over that substrate. What already exists most strongly is **read-side truth**; the clearest existing gaps are **(a) a unified, fully-serialized external read surface**, **(b) the write path's coupling to the OpenAI loop**, and **(c) uneven signal/renderer coverage across non-foundational domains.**

This document states those facts. It does not prescribe how to address them — that is a later, joint decision.

---

*Generated by read-only architecture discovery. No code or data was modified. Companion: 07_CoS_Dependency_Analysis.md (full classification table), 04_Context_Intelligence_Pipeline.md (call-chain), 01_System_Architecture_Overview.md (whole-system model).*
