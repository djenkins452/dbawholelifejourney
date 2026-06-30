WLJ MASTER PROMPT — DEBUGGING MODE

System Context

The system being developed is **Whole Life Journey (WLJ)** — a Django-based personal operating system with an AI Chief of Staff named **Beth**.

Beth orchestrates tasks, health, faith, journaling, goals, and daily planning using deterministic engines combined with LLM reasoning.

The architecture follows an **LLM-last approach**:

1. Deterministic system truth
2. Verified structured state
3. LLM reasoning
4. Natural language narration

The LLM must **never fabricate state**.

Beth must only report data derived from deterministic system records.

---

WORK MODE: DEBUGGING

The goal of this session is **diagnosis and stabilization**, not architectural redesign.

Do NOT propose fixes until the root cause is proven.

Follow this workflow strictly.

STEP 1 — TRACE

Trace the exact execution path that produced the behavior.

Example path:

send_message()
→ _generate_response()
→ router / handler
→ context builder
→ state query
→ LLM prompt

Identify the exact functions and files involved.

---

STEP 2 — CANONICAL SOURCE

Identify the **source of truth** for the data in question.

Examples:

Tasks → Organize page query
Health → SAE health module
Medicine → SAE medicine module
Goals → SAE goals module
Events → LifeEvents query

Beth must match the canonical system.

---

STEP 3 — AUDIT

Search the codebase for **every location retrieving this data**.

Classify each location:

• Canonical
• Functional mismatch
• Harmful filter
• Redundant logic

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

---

STEP 6 — VERIFY

Explain how the fix will be validated.

Example:

User prompt:
"How many tasks do I have today?"

Expected:
Beth Now count == Organize page Now bucket

---

PROMPT CHALLENGE RULE

Before implementing any change:

1. Review the current codebase state.
2. If any instruction in this prompt conflicts with the current architecture, stop and explain why.
3. Prefer modifying existing systems over introducing new ones.
4. Do not implement speculative fixes.
