# Document 4 — Recommended Minimal Context Package

**Purpose:** Without designing APIs, identify the minimal deterministic information ChatGPT would need **loaded at all times** to operate as Danny's Chief of Staff — i.e., the standing context that should be present on every turn before any on-demand retrieval.

**Framing:** This is an identification of *what information*, mapped to the *existing deterministic provider* that already produces it. It is not an API design, not an implementation, and not a schema proposal. Each item below already exists in code; the table shows where.

**Two tiers:**
- **Always-loaded (standing context)** — small, cheap, present every turn. Answers "where does Danny stand right now" and "what should he do."
- **On-demand (retrieved when the question requires it)** — larger or domain-specific; pulled only when relevant. Listed for boundary clarity, since the example question ("why has weight loss slowed") shows when standing context is insufficient.

---

## 1. Always-Loaded Standing Context (the minimal package)

These are the deterministic objects that should be resident every turn. All already exist; most are already assembled inside `build_cos_context` (`apps/core/ai_orchestrator/cos_context.py:3555`) — i.e., WLJ already computes this exact bundle for the in-process CoS today.

| # | Minimal context item | Why it must always be present | Existing deterministic provider (file:line) |
|---|----------------------|-------------------------------|---------------------------------------------|
| 1 | **Identity & personalization** — user, assistant display name, active feature flags, key preferences | Scopes every answer; sets the CoS's name and which modules even exist for this user | `UserPreferences` + `get_cos_name()` `apps/users/models.py:694/701`; flags `apps/core/context_processors.py:203` |
| 2 | **Time & "today" anchor** — current date/time, active block, day phase | Almost every CoS judgment is time-relative (overdue vs due-today vs future) | `get_active_block` `apps/core/execution/active_block.py:145`; HTIE time pipeline; `DailyProgressService.get_today()` (injected `cos_context.py:8355`) |
| 3 | **Execution truth / today's state** — what's done, overdue, recoverable; next action; biggest risk; fix priority | This is the core "what should Danny do now" — the most-used CoS function | `get_execution_truth` `execution_truth_engine.py:81`; `build_today_execution` `today_execution.py:34`; `build_execution_state` `execution_state.py:46`; selectors `selectors.py:145/254/326` |
| 4 | **Executive / dashboard summary** — strategic state summary, top risk flags, momentum/opportunities, recommended focus | The holistic "30,000-ft view" the CoS reasons from; already a composed object | `build_executive_context` `cos_context.py:9079`; `build_cos_intelligence` `apps/ai/cos_intelligence.py:253` |
| 5 | **Top signals (prioritized, deduped)** — the current foundational+important signals across domains | The deterministic interpretation layer; what's notable right now without raw queries | unified feed `apps/core/ai_signals/unified_feed.py`; rendered via `signal_renderer.py`; risk flags `cos_context.py:9094` |
| 6 | **Health vital snapshot** — current weight + trend, glucose state, sleep, recovery (foundational domain) | Health is a foundational-tier domain; its current state contextualizes most life reasoning | `build_health_state` `state_builder.py:321` (weight `:358`, glucose `:1018`, sleep `:598`, recovery `:1126`) |
| 7 | **Situational awareness / right-now focus** — the computed "current situation" verdict | Tells the CoS what mode the day is in (normal/recovery/etc.) before it speaks | `compute_situation_for_user` `situation_computer.py:23`; `compute_right_now_focus` `right_now.py:133`; `CoSSituationState` (15-min recompute) |
| 8 | **Trust-tier framing** — which context is canonical vs advisory | Prevents the LLM from converting rollups into per-item truth (Law 16) | narration contract tiers `narration_contract.py:51-56` |

**Observation:** items 1–8 are *already produced and already bundled* for the current CoS. `build_cos_context` is, in effect, the existing minimal-context package. The standing-context question is therefore largely **answered by an existing object** — the open question is serialization (it is internal-only today; see Document 2 §1), not computation.

---

## 2. On-Demand Context (retrieved only when the question requires it)

The example *"why has my weight loss slowed down?"* demonstrates the boundary: the standing package (above) tells the CoS *that* weight-loss has slowed (item 6) and *what's* notable (item 5), but a causal answer needs domain detail the standing package deliberately omits to stay small.

| Triggering need | On-demand provider (file:line) | Readiness note (from Docs 1–3) |
|---|---|---|
| Full per-domain state (faith, journal, goals, relationships, meals, finance, etc.) | `get_module_state(user, module)` `state_engine.py:74` + builders | Computed; **not serialized** externally |
| Weight/sleep/nutrition root-cause explanation | `_render_structured_assessment` `deterministic_router.py:6279` | Exists; **5-domain aperture only** |
| Cross-domain correlations | CDCE `DomainCorrelation` `cdce_engine.py`; 7 detectors `:893` | Fixed detectors; weight-blind |
| History lookup (time-based) | `query_event_history` → `EventResolver` `ai_events/resolver.py:24` | Date/count only; **no keyword search** |
| Document / note / capture retrieval | detail views; `SearchService` `search_service.py:30`; `search_notes_cos` `notes/services.py:419` | Search engines **unwired (dead code)** |
| Capture transcript / theme search | `SearchService.search_capture` `search_service.py:1383` | Unwired; live search excludes transcripts |
| Current screen context | in-app `page_context` pipeline `personal_assistant.py:166` | In-app only; not externally reachable |

---

## 3. The Minimal Package, Stated Plainly

To operate as Danny's Chief of Staff at all times, ChatGPT minimally needs, on every turn:

1. **Who** — identity, assistant name, enabled modules/preferences.
2. **When** — now, active block, day phase.
3. **What's due / done / at risk** — execution truth + next action / biggest risk / fix priority.
4. **The big picture** — executive summary: strategic state, risk flags, momentum, recommended focus.
5. **What's notable** — the prioritized, deduped signal set.
6. **Foundational health vitals** — weight+trend, glucose, sleep, recovery.
7. **The current situation verdict** — what mode the day is in.
8. **Trust framing** — which of the above is canonical vs advisory.

Everything else (deep domain detail, causal explanations, history, documents, captures, screen state) is **on-demand**, fetched when the conversation requires it.

**Closing finding:** WLJ already computes the entire always-loaded package — it is essentially the output of `build_cos_context` / `build_executive_context`. The minimal standing context is therefore a *solved computation problem* in WLJ today; what is unresolved is (a) exposing it to an external consumer (serialization) and (b) the on-demand layer's wiring/aperture gaps catalogued in Documents 2 and 3. This document identifies the information set only; it proposes no mechanism for delivering it.
