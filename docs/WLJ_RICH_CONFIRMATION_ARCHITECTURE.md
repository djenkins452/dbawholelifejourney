# WLJ Rich Confirmation — Governing Architecture

**Authority:** Governing (canonical architecture for ALL Chief-of-Staff deterministic-action confirmation)
**Status:** CURRENT — ratified 2026-07-20
**Audience:** Engineer
**Builds on:** the existing bound-confirmation engine (`apps/ai/model_interface/confirmation.py`, `apps/ai/cos_services/action_interface.py`) and the model-interface runtime. This is an EVOLUTION of that one engine — **never a second confirmation mechanism.**

> Every deterministic action the CoS confirms — imports, saves, deletes, bulk actions, merges — flows through ONE Rich Confirmation capability. The user may respond by **clicking an action** or by **typing naturally**; both resolve the SAME bound confirmation through the SAME deterministic engine. Buttons are just another input. No feature builds its own confirmation UI. Conform to this document or amend it deliberately.

---

## 1. The problem this fixes

A confirmation had two defects: (1) on the live model-interface path the structured confirmation was minted for the *model* and **discarded before it reached the browser**, so the user saw only text and never a button; (2) resolving a typed "yes" depended on the **model** choosing to call `resolve_pending_action` — and in production it didn't, so a valid journal-import confirmation was **lost** and "yes" was treated as unrelated text.

Rich Confirmation removes both: the confirmation becomes a **durable, bound, presentation-independent record** surfaced to every client, and BOTH a clicked button and a typed confirm/cancel resolve it **deterministically** — the model is no longer the load-bearing path for "yes."

---

## 2. Principles (non-negotiable)

1. **One engine.** The bound confirmation (`{id, action, params, …}` + `resolve_pending_action`) is the single source of truth and the single resolver. Rich Confirmation extends its *storage* (durable, conversation-bound, carries the display model) and its *resolver* (adds a `choice`), and *surfaces* it — it does not add a parallel path.
2. **Both inputs converge deterministically.** Click → `POST /assistant/api/confirm/` → `resolve_pending_action`. Typed confirm/cancel (matching the confirmation's own aliases) → a deterministic pre-parser → `resolve_pending_action`. Only genuinely ambiguous text falls through to the model. **A button click never costs a model call and never depends on model interpretation.**
3. **The card and the action come from the SAME record.** The buttons the user sees and the deterministic action WLJ executes are built from one bound confirmation, so they can never drift.
4. **Presentation-independent.** The engine emits a data model (title, summary, preview, actions); the client decides rendering — desktop pills, mobile stacked, voice ignores buttons. One shared renderer (`wlj-confirmation.js`), never per-surface or per-feature UI.
5. **Safe by construction.** User-scoped, conversation-bound, single-use, expiring, idempotent, audited, replay-protected, and protected against resolving another user's or a stale/already-resolved action.
6. **Binary by default, N-way capable.** Every confirmation gets a zero-config binary action set (primary + Cancel). Multi-option flows (Medication Merge) declare an explicit `actions` list and resolve via the same resolver's `choice` — the contract is N-way from day one.

---

## 3. The confirmation contract (presentation-independent)

Emitted on the assistant turn and persisted on the message:

```json
{
  "confirmation_id": "…",
  "status": "pending",            // pending | resolved | cancelled | expired
  "expires_in": 300,
  "title": "Import journal entries",
  "summary": "I found 8 journal entries.",
  "preview": ["7 will be imported", "1 will be skipped", "Aug 30 – Sep 10, 2022"],
  "actions": {
    "primary":   {"key":"confirm","label":"Import","style":"primary",
                  "aliases":["yes","import","proceed","go ahead","looks good","do it","confirm"]},
    "secondary": [{"key":"cancel","label":"Cancel","style":"secondary",
                  "aliases":["no","cancel","stop","never mind","don't do it"]}]
  }
}
```

- **`key`** — the outcome submitted to the resolver. **`label`** — display. **`style`** — `primary | secondary | danger`. **`aliases`** — the natural-language equivalents (the SAME vocabulary the typed pre-parser matches).
- **Binary default** is derived generically from the action + its `confirmation_detail` (import/measurement/delete/generic). **N-way** is an explicit `actions` list the handler supplies.

---

## 4. Storage & lifecycle (the durable bound record)

The bound confirmation is stored user-scoped and **conversation-bound**, carrying the display model and the deterministic action:

`{ confirmation_id, user, conversation_id, source_artifact_id?, action, params, view(title/summary/preview/actions), status, choice?, created, expires }`

- **Single-use / replay-proof:** resolving consumes it (status → resolved/cancelled); a second submit returns `already_resolved`.
- **Expiring:** a TTL (default 300s); an expired submit returns `expired`. The card renders the expired/resolved state on reload.
- **User + conversation scoped:** resolution validates the id belongs to THIS user (and, for the typed path, THIS conversation) — never "whatever is stored."
- **Audited:** every mint and resolution writes a `ToolCallLog` (kind=action).
- **Reload-durable display:** the confirmation `view` is persisted on the `AssistantMessage`, so history/reload re-render the card in its current status.

---

## 5. Resolution — both paths, one primitive

```
CLICK  → POST /assistant/api/confirm/ {confirmation_id, choice}
             → resolve_pending_action(user, confirmation_id, confirm=(choice!="cancel"), choice)
TYPE   → deterministic pre-parser: open confirmation for (user, conversation)?
             → message matches an action's aliases? → resolve_pending_action(...)      [no model]
             → else → model dispatch (model sees pending_confirmations, resolves or clarifies)
```

Both converge on `resolve_pending_action`, which executes the bound action through the existing safe path (`execute_action → execute_intent → UAIO`) with `confirmed=True`, returns the REAL result, and consumes the record. The result is delivered as the next assistant turn.

---

## 6. Transport (the card must reach every client)

The `confirmation` object is surfaced on: the **non-streaming** chat response (`response_data.confirmation`), the **streaming** SSE `done` event data, **conversation-history serialization**, and therefore **reloaded conversations** — on both the **desktop panel** and the **mobile drawer**. A confirmation card never exists only on the initial live turn.

---

## 7. The shared client renderer (`wlj-confirmation.js`)

ONE module both surfaces consume (loaded platform-wide, like `wlj-attachments.js`). Renders: title, summary, preview details, primary + secondary actions with primary/secondary/danger styles; expired / already-resolved / executing (disabled) states; a clear execution result; responsive desktop + mobile; accessible (roles, `aria`, keyboard). A click POSTs to `/assistant/api/confirm/`, disables the card while executing, then renders the returned result. Typed responses still flow through the chat input. No feature-specific confirmation UI anywhere.

---

## 8. Scope & fast-follow

- **Now:** full **binary** Rich Confirmation across the whole CoS (imports, measurements, journal imports, saves, deletes, bulk actions, other binary confirmations), contract N-way-ready.
- **Fast-follow (first N-way consumer):** **Medication Merge** — choices Merge / Keep Both / Cancel — by declaring an `actions` list and resolving via the resolver's `choice`. No new mechanism.
- **Out of scope:** the in-domain bespoke flows (calendar `decision_options`, medication `confirm_draft`) except as the medication N-way pilot adopts this contract.

---

*Execution status lives in the changelog + roadmap + memory, never in this governing document.*
