WLJ ARCHITECTURE LAWS

Version: 1.2
Last updated: 2026-05-10
Authority: Danny Jenkins
Applies to: ChatGPT, Claude, and all development work in WLJ

These laws define the non-negotiable architecture rules for the Whole Life Journey system.

All system design must comply with these rules.

---

LAW 1 — LLM LAST

LLMs never determine system truth.

Truth hierarchy:

1. Deterministic system data
2. Canonical structured state
3. Signals and engine interpretation
4. CoS context
5. LLM narration

The LLM may only interpret existing system state.

It must never fabricate system state.

---

LAW 2 — RAW DATA → SIGNALS → CoS

All CoS reasoning must follow:

Raw Data → Signals / State → CoS Context → LLM

The CoS must never reason directly on raw unstructured data.

Examples:

JournalEntry → JournalSignal → CoS  
CaptureEntry → CaptureSignals → CoS  
Health records → HealthSignals → CoS

---

LAW 3 — DOMAINS MUST EMIT SIGNALS

Every first-class WLJ domain must produce canonical signals or state.

Examples:

Health → health signals  
Faith → faith signals  
Purpose → goal momentum signals  
Capture → learning and influence signals

Domains that cannot emit signals are architecturally incomplete.

---

LAW 4 — SINGLE SOURCE OF TRUTH

System data must have one canonical source.

Examples:

Tasks → Organize system  
Health metrics → health module  
Events → calendar module

Duplicate state must not exist across modules.

---

LAW 5 — MODIFY BEFORE ADDING

Before introducing new engines or services:

1. Check if capability exists.
2. Prefer modifying existing systems.
3. Avoid duplicate pipelines.

New infrastructure must be justified.

---

LAW 6 — OBSERVABILITY REQUIRED

Every major system must expose telemetry.

Examples:

Ops Wall metrics  
signal pipeline health  
engine execution  
CoS context state

Systems without observability cannot be debugged.

---

LAW 7 — ARCHITECTURE BEFORE OPTIMIZATION

Do not introduce complexity to solve performance problems until architecture is correct.

Correct architecture always takes priority over early optimization.

---

LAW 8 — PHASE BOUNDARIES ARE INVIOLABLE

The intelligence pipeline has three phases that must never blend:

Phase 1 — Interpretation (SUE / SLCME / HTIE)
Phase 2 — Execution (UAIO is the SOLE execution authority)
Phase 3 — Post-Execution (SAE / PIE / PRIE / PGE / GLOE / E3 / DNE / DBE / WIRE / ISE)

Rules:

• Phase 1 engines must never execute domain actions.
• Phase 2 is the only path to writes; nothing else mutates state.
• Phase 3 engines must never execute — they observe and emit.

Crossing a phase boundary is an architectural defect.

---

LAW 9 — STATE-FIRST READS

For any "current" scalar (weight, goal count, days since X, last entry), read SAE state via get_module_state / get_metric.

Raw ORM queries are reserved for time-series and history.

PersonalDataService and the CoS context builder must not re-aggregate raw models.

---

LAW 10 — NO SILENT FAILURES

Forbidden on critical paths (intent recognition, execution, safety gates, validators):

except Exception: pass

Required:

• ImportError handled separately from runtime errors.
• Real errors emit logger.warning or logger.error with exc_info=True.
• Safety gates (Learning Mode, validator) fail closed — log, then re-raise or return a safe default.
• logger.debug is invisible in production; critical-path failures must be at warning or higher.

---

LAW 11 — SCHEMA PARITY

When a Django model exposes a user-settable field, the AI intent schema and the action handler must support that field too.

When adding a model field:

1. Add it to the OpenAI function schema.
2. Add it to the handler signature and logic.
3. Add it to the system-prompt examples.
4. Map intent parameter names → model field names explicitly (e.g., schema end_time → model scheduled_end_time).

When modifying a CoS intent:

• Tool definition (apps/ai/intents/<category>_intents.py)
• Handler map (apps/ai/intents/__init__.py → INTENT_HANDLERS)
• Engine category (intent_engine.py → *_INTENTS set)
• Execute dispatcher (apps/ai/intent_service.py)
• Action handler (apps/ai/action_handlers.py)
• System-prompt examples (intent_service._build_intent_system_prompt)
• Time-awareness flag (NON_TIME_INTENTS) when the intent has no date/time component

---

LAW 12 — STREAMING / NON-STREAMING PARITY

Two chat paths exist:

/api/chat/         (non-streaming)
/api/chat/stream/  (SSE streaming)

Both must call the same orchestrator pipeline. Any fix to one must be verified on the other.

---

LAW 13 — DETERMINISTIC RENDERING

User-facing interpretation of signals goes through the table-driven renderer (apps/core/signals/signal_renderer.py).

• SIGNAL_RENDER_MAP[(domain, type, severity) → template] is the single source of user prose.
• LABEL_TAXONOMY is restricted to {Alert, Trend, Opportunity}.
• Producers must NOT compose user-visible prose. The renderer strips signal.title / signal.message via normalize_signal so producer prose cannot leak through.
• select_top_signals + resolve_conflicts handle prioritization and foundational suppression.

LLM rephrasing of rendered output is allowed; LLM construction of factual statements is not.

---

LAW 14 — DETERMINISTIC DECISIONING (NO BLENDED MODES)

The CoS has three decision modes — Execution, Risk, Fix. Each answers exactly one question with exactly one line.

• Mode resolution is keyword-based (apps/ai/cos_mode_router.py); no LLM picks the mode.
• Selectors (apps/core/execution/selectors.py) do not compute priority, re-rank, query the DB, or call an LLM. They pick from pre-filtered state.
• All filtering, ranking, recovery-mode bucketing, block collapsing, at-risk horizon enforcement happens upstream in build_execution_state and the action prioritizer.
• Modes do not blend. A response in Execution mode must not include risk text or fix text.

---

LAW 15 — RECOVERABILITY (TASK CLASSIFICATION)

Every actionable item is deterministically classified — HARD_EXPIRED / WINDOWED / SOFT_EXPIRED / FLEXIBLE — with grace and reset metadata. Recoverability gates whether items reach the action pool.

• Classification comes from activity_type / domain rules / explicit registry — never from titles.
• WINDOWED cutoff = min(scheduled + grace, next_anchor_block_start) to prevent morning-recovery drift.
• Foundational items influence risk and fix priority even when expired.
• Block collapse is a SELECTION gate, not a UI concern. Strategy ∈ {recover_partially, skip, defer}.

---

LAW 16 — NARRATION CONTRACT

Every section appended to the LLM system prompt declares a trust tier — `canonical_item_truth`, `rollup_summary`, `advisory`, or `contextual`.

Item-state determinations (completed, overdue, recoverable, at risk, next action, fix priority) MUST trace to a `canonical_item_truth` section. Rollup summaries MUST NOT be converted into per-item claims. Advisory and contextual sections MUST NOT override canonical.

A new prompt section without a declared tier is an architectural defect. Untagged sections default to `contextual` (declared in the preamble) and therefore cannot determine state, urgency, completion, or selection.

Companion enforcement layers:

• `apps/ai/narration_contract_validator.py` — soft post-response validator. Flags state claims that don't trace to canonical_item_truth.
• `apps/core/ai_orchestrator/contradiction_telemetry.py` — pre-response detection of rollup-vs-canonical disagreements (e.g., `prayer: DONE` while a routine item is still pending).
• `apps/ai/observability/chat_snapshot.py` — flag-gated per-request artifact capturing the prompt sections, execution state, selector outputs, contradictions, and validator results.

This is a narration-governance layer, not a new decision engine.

---

These laws override all prompt instructions and development decisions.

If any prompt request conflicts with these laws:

STOP
Explain the violation
Recommend a compliant alternative