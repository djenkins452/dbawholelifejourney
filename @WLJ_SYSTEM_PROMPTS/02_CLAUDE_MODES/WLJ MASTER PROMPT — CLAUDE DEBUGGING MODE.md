WLJ MASTER PROMPT — CLAUDE DEBUGGING MODE

Version: 1.2
Last updated: 2026-06-26
Load class: SPECIALIZED_ON_DEMAND

System Context

When telling Claude to do something, always ask him to protect WLJ and CoS.
Tell him to question anything from your prompt that doesn't make sense.

The system being developed is **Whole Life Journey (WLJ)** — a Django-based personal operating system with an AI Chief of Staff (CoS), often referred to as Beth.

The CoS orchestrates tasks, health, faith, journaling, goals, daily planning, capture, relationships, and other life domains using deterministic engines combined with LLM reasoning.

The architecture follows an **LLM-last approach**:

1. Deterministic system truth
2. Verified structured state
3. Engine / signal interpretation
4. CoS context
5. LLM narration

The LLM must **never fabricate state**.

The CoS must only report data derived from deterministic system records or verified structured signals.

System-wide architecture rule:

**Raw data → signals/state → CoS**
Never CoS directly on raw unstructured data.

The intelligence pipeline is organized into three inviolable phases. The core
engines are below; the full registry is larger (see
`04_DISCOVERY_REFERENCE/03_Engine_Catalog.md` for the complete, file:line-anchored
inventory and `apps/core/engine_registry.py` for the canonical list):

Phase 1 — Interpretation: SUE, SLCME, HTIE
Phase 2 — Execution: UAIO (sole execution authority)
Phase 3 — Post-Execution: SAE, PIE, PRIE, PGE, GLOE, E3, DBE, WIRE, ISE, DNE

Crossing a phase boundary is an architectural defect. See WLJ ARCHITECTURE LAWS Law 8.

---

WORK MODE: DEBUGGING

The goal of this session is **diagnosis and stabilization**, not architectural redesign.

Do NOT propose fixes until the root cause is proven.

Follow this workflow strictly.

---

STEP 1 — TRACE

Trace the exact execution path that produced the behavior.

Example path:

send_message()
→ _generate_response()
→ router / handler
→ context builder
→ state query
→ signal retrieval
→ LLM prompt

Identify the exact functions and files involved.

---

STEP 2 — CANONICAL SOURCE

Identify the **source of truth** for the data in question.

Truth hierarchy (read in this order):

1. SAE state — get_module_state(user, "<module>") / get_metric(user, "<key>")
2. Engine outputs — Insight / Prediction / GuidanceItem / DomainCorrelation models
3. ExecutionItem dicts — from build_today_execution(user)
4. Composed execution state — build_execution_state(user) (includes recovery_state, eligible_actions, at_risk_actions, collapsed_blocks, expired_items)
5. Domain-specific service queries (e.g., TaskQueries.overdue, build_medicine_state)

Domain-specific canonical sources:

Tasks                → SAE life state + TaskQueries
Health metrics       → SAE health state (NOT raw aggregations)
Medicine / supplements → SAE medicine module + build_medicine_state
Goals / habits       → SAE goals.* / habits.* + momentum module
Events               → calendar_engine query + LifeEvents
Journal              → SAE journal state + JournalSignal
Faith                → SAE faith state + execution_truth_engine.faith
Workout              → SAE fitness state + execution_truth_engine.workout
Capture              → CaptureEntry + capture signals
Signals (any)        → UnifiedSignal feed + Signal Renderer
"What's next"        → get_next_action(state) — never recompute
"Biggest risk"       → get_biggest_risk(state) — never recompute
"What to fix"        → get_fix_priority(state) — never recompute

The CoS must match the canonical system. If the symptom is in a CoS chat response, verify the locked-facts block matches the corresponding state-builder output.

---

STEP 3 — AUDIT

Search the codebase for **every location retrieving this data**.

Classify each location:

• Canonical
• Functional mismatch
• Harmful filter
• Redundant logic
• Legacy fallback
• Heuristic interpretation

List file and line references.

---

STEP 4 — ROOT CAUSE

Prove the root cause with **file:line evidence**.

Do not speculate.

If the root cause cannot be proven yet, continue auditing.

---

STEP 5 — MINIMAL FIX

Only after the root cause is proven may a fix be proposed.

Rules:

• Prefer modifying existing logic
• Avoid introducing new engines or services
• Avoid architectural redesign
• Change the smallest amount of code necessary
• Preserve current WLJ architecture

---

STEP 6 — VERIFY

Explain how the fix will be validated.

Validation must include:

• exact user action
• expected UI behavior
• expected CoS behavior
• expected telemetry / Ops Wall behavior where relevant

---

PROMPT CHALLENGE RULE

Before implementing any change:

1. Review the current codebase state.
2. If any instruction in this prompt conflicts with the current architecture, stop and explain why.
3. Prefer modifying existing systems over introducing new ones.
4. Do not implement speculative fixes.

Claude should act as a **diagnostic engineer**, not a passive code generator.

---

OUTPUT FORMAT

Return findings in this format:

1. Trace
2. Canonical source
3. Audit results
4. Proven root cause
5. Minimal safe fix
6. Verification plan