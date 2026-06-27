# D4 — AI Medication/Supplement CRUD: Decision Spike

**Sprint 1C deliverable. Decision spike only — no implementation (correct per the spike's own conclusion).**
Date: 2026-06-27. Conforms to the Medication Intelligence Canon (frozen) and the Phase 4 roadmap.

## Verdict: DEFER implementation to Sprint 12 (Epic E11), gated on the safety classifier (E7-S4, Sprint 7).

Implementing AI writes to canonical medication state now is **not low-risk** (the precondition for implementing in this spike). The safe path depends on infrastructure that does not yet exist. The spike confirms the *channel* and produces the contract for when it is built.

---

## 1. Current state (evidence)

**AI intake intents today are LOG-ONLY** (`apps/ai/intents/__init__.py:78-81`): `take_medication`, `take_supplement`, `take_intake_by_time`, `email_intake_list`. Each is `ActionCategory.LOG, RiskLevel.LOW, AuthorityLevel.CONFIRM` (`apps/core/ai_orchestrator/action_policy.py:144-148`) and creates an **`IntakeLog`** row via `action_handlers` — never an `Intake` regimen record. No create/update/delete/pause/discontinue intent exists.

**The safe write channel already exists** and is the correct one to reuse:
`IntentService.execute_intent` → `action_policy` (authority/risk) → `crud_confirmation` gate ("No write executes without explicit user confirmation"; A/B/C, Action/Details/Impact, Before→After) → `action_handlers.handle_<intent>` → model. UAIO is the sole write authority.

**No direct Beth/ChatGPT model writes today** (confirmed): the modern CoS `DAY1_ACTION_ALLOWLIST` (`apps/ai/cos_services/action_execution.py:53-67`) contains **no** medication mutation — not even `take_medication`. Medication logging is a legacy-path action that still passes through `action_policy` CONFIRM + handlers.

## 2. Missing CRUD actions & per-action decision

None are "allowed now"; none are "denied" (all are legitimate future capabilities); all are **confirmation-required + deferred**.

| Action | Decision | Risk | Notes / dependency |
|--------|----------|------|--------------------|
| `create_medication` / `create_supplement` | **Confirmation-required; DEFER → Sprint 12** | **MEDIUM** | Must route through Confidence-Review semantics (dose ambiguity, Rx-vs-supplement, duplicate detection — Sprints 3–4) + safety classifier. A wrong NL-extracted dose entering canonical state is a clinical-safety risk. |
| `update_dose` | **Confirmation-required; DEFER → Sprint 12** | **MEDIUM–HIGH** | Dose is clinically sensitive. Must write a `MedicationEvent(dose_changed)` + capture reason → requires the ledger (Sprint 3, E4-S1 `record_medication_change()`). |
| `update_schedule` / `update_medication` (name/purpose/etc.) | Confirmation-required; DEFER → Sprint 12 | MEDIUM | Before→After confirmation; non-dose fields lower risk but same channel. |
| `pause` / `resume` | Confirmation-required; DEFER (candidate for Sprint 5) | LOW–MEDIUM | Reversible, non-destructive — the earliest-eligible CRUD once the safety classifier lands. |
| `discontinue` / `complete` | Confirmation-required; DEFER → Sprint 12 | MEDIUM | Writes `MedicationEvent(discontinued)`; **never hard-delete** (Canon — preserve history). |
| `delete` / `archive` | Confirmation-required; DEFER → Sprint 12 | LOW | Soft-delete only; lowest priority. |

## 3. Why not now (the missing preconditions)

1. **No safety classifier (E7-S4, Sprint 7).** The Canon forbids Beth from anything that reads as prescribing. Creating/changing a medication by voice is exactly where a "prescribe-like" request must be screened *before* a write. That gate does not exist yet.
2. **No Confidence-Review / duplicate-detection semantics (Sprints 3–4).** Medication creation must blank low-confidence fields, force Rx-vs-supplement, and detect duplicates/old-bottle — none of which the chat path can do today.
3. **No `MedicationEvent` ledger / `record_medication_change()` writer (Sprint 3, E4-S1).** Dose/discontinue changes must be recorded as immutable history through the single dual-write authority; it does not exist yet.
4. **Risk mismatch.** Existing intake actions are `RiskLevel.LOW`. Regimen CRUD is MEDIUM–HIGH and must not inherit LOW handling.

Building CRUD now would mean a medication write path with no safety screen, no confidence review, and no history ledger — the opposite of the Canon's fail-closed posture.

## 4. Safe action contract (for Sprint 12 implementation)

When built, every AI medication-CRUD intent MUST:
1. Register via the full 5-point intent checklist (schema parity: schema ↔ handler ↔ engine set ↔ dispatcher ↔ prompt).
2. Be classified `AuthorityLevel.CONFIRM` + `RiskLevel.MEDIUM` (dose ≥ MEDIUM) in `action_policy`.
3. Pass the **safety classifier** first — decline+redirect if the request reads as prescribing / dose advice.
4. Render the **`crud_confirmation`** gate (Action/Details/Impact; Before→After for updates) — no write without explicit user confirmation.
5. Execute only via `IntentService → UAIO → action_handlers.handle_<intent>` → `record_medication_change()` (the single Intake+ledger dual-writer). **No direct model writes from Beth/ChatGPT.**
6. For the modern CoS path, be added to the allowlist explicitly (today it is intentionally absent).

## 5. Implementation plan (deferred)

Sequenced behind its dependencies, not in Sprint 1:
- **Sprint 3:** `MedicationEvent` + `record_medication_change()` (E4-S1) — the write target.
- **Sprint 5 (candidate):** `pause`/`resume` intents (reversible, lowest risk) once the safety classifier exists.
- **Sprint 7:** safety classifier (E7-S4) — hard prerequisite for any create/update/dose intent.
- **Sprint 12 (E11):** `create_medication`/`create_supplement`/`update_*`/`discontinue` intents, MEDIUM risk, confirmation + safety-gated, Confidence-Review-aligned.

## 6. Sprint 1C outcome

D4 implementation is **correctly deferred** — consistent with the frozen roadmap (E11/Sprint 12) and the Canon. The existing `action_policy → crud_confirmation → IntentService → UAIO → action_handlers` channel is confirmed as the safe path; no direct Beth/ChatGPT medication writes exist today. No code shipped in Sprint 1C, by design.
