# WLJ Structured Import Orchestration — Governing Architecture

**Authority:** Governing (canonical architecture for all Chief-of-Staff structured multi-record import in WLJ)
**Status:** CURRENT — ratified 2026-07-19
**Audience:** Engineer
**Builds on:** `docs/WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md` (the arrival path, artifact seam, and deterministic spine this capability extends) and `docs/WLJ_LLM_TRUTH_ACTION_CONTRACT.md` (truth vs action boundary).

> This is the canonical architecture for how the WLJ Chief of Staff (CoS) turns a **single uploaded document that contains many logical records** — a historical journal export, a bank statement, a lab panel, a contact list — into **many deterministic, provenance-bearing records**, after showing the user a faithful preview and getting explicit confirmation. It is **not** journal-specific. Conform to this document or amend it deliberately.

---

## 1. Vision

A person hands the CoS one document that is really *N records* — "here are two weeks of my old journal," "import these expenses," "log all these readings." The CoS should **recognize the structure**, tell the user exactly what it found, show a **deterministic preview**, wait for **confirmation**, and then **deterministically create each record** with provenance and audit — never rewriting or summarizing the user's own words.

The recognition is the model's job (it already reads documents well). Everything after recognition — validation, the preview, confirmation policy, atomic creation, dedup, provenance, and audit — is **deterministic WLJ truth**. This is a **truth + action** capability, never a reasoning engine.

**One engine, every domain.** Journal, prayer/dream/gratitude journals, expenses, health readings, contacts, recipes — each is a **thin typed adapter** over the **same** generic Structured Import engine. Adding a domain is registering an adapter, not building another importer.

---

## 2. Constitutional placement (no Constitutional Review required)

This capability lives entirely inside the existing Constitution — **Article I.5–I.7** (the deterministic spine: *perceive → validate → dedup → confirm → execute → audit → provenance*). It is ordinary new capability, which the Constitution explicitly permits without review, **because** every record is:

- **validated** deterministically by WLJ (I.6),
- written through the **existing safe action path** — `IntentService.execute_intent → ActionHandler.handle_* ` — never a direct model side-effect or a raw bulk `objects.create` bypass (I.7),
- **confirmed** before any write (Truth/Action Contract §4),
- **audited** and **provenance-linked** back to the source artifact.

It would have required a Constitutional Review only if it built a bespoke reasoning/orchestration engine inside WLJ, or bypassed validation/the safe action path. It does neither. (The pre-existing `apps/journal/management/commands/import_chatgpt_journal.py` — direct create, no confirmation, no provenance, no audit, and it *rewrites* bodies — is exactly the anti-pattern this capability replaces for CoS-driven imports.)

---

## 3. The pipeline

```
User uploads ONE document (→ MultimodalArtifact, via the multimodal platform)
        │  model perceives structure
        ▼
Model emits ONE TYPED batch intent  (import_journal_entries, future import_expenses, …)
   carrying records[] + source_artifact_id + per-record confidence
        │
        ▼   ── the generic Structured Import engine (apps/ai/structured_import.py) ──
   1. resolve the registered adapter for that intent's domain
   2. artifact IDEMPOTENCY  — the same artifact never imports twice (StructuredImportRun exists?)
   3. per-record VALIDATION  — adapter.validate() → {valid | skipped(reason) | duplicate}
   4. PREVIEW               — build confirmation_detail → import_confirmation renderer (RESULTS, facts only)
        │  nothing is written yet
        ▼
   User confirms (bound confirmation; confirmed=true forwarded — DATA_CONFIRM_INTENTS)
        │
        ▼
   5. CREATE (atomic)       — adapter.create_one() per valid record, through the domain's safe write
   6. PROVENANCE            — StructuredImportRun records the batch; link_artifact() → the run
   7. AUDIT                 — per-record outcomes in the run manifest + domain event + tool-call audit
        │
        ▼
   Report ACTUAL created / skipped / duplicate / failed counts
```

**One typed intent = one preview = one confirmation gate** for the whole batch. WLJ never writes a partial batch without confirmation.

---

## 4. The reusable contract

### 4.1 Typed domain intents (Decision A — ratified)
The model calls a **typed** batch intent per domain (`import_journal_entries`, future `import_expenses`, `import_health_readings`), **never** a generic untyped `records[]` tool. Typed schemas give the model precise field names, improve validation and tool discoverability, and produce a faithful confirmation — while **all** typed intents dispatch into the **one** shared engine underneath. This matches Constitution principle #2 ("the model calls a normal named domain intent") and the `log_body_measurements` precedent.

### 4.2 The engine (`apps/ai/structured_import.py`) — domain-agnostic, built once
- `StructuredImportAdapter` (base): declares `domain`, `intent`, `renderer`, and implements `validate(raw_records) → (valid, skipped)`, `create_one(user, record) → object`, `dedupe_exists(user, record) → bool`, and `preview_detail(...)`.
- `register_import_adapter(adapter)` / `get_import_adapter(intent)` — the **adapter registry**.
- `run_structured_import(user, adapter, raw_records, *, source_artifact_id, source, confirmed, when) → ImportOutcome` — the whole spine (idempotency → validate → preview/confirm → atomic create → provenance → audit). Returns a plain `ImportOutcome` the thin handler maps to `ActionResult`.

### 4.3 The preview presenter (`apps/ai/import_confirmation.py`) — generalized, not forked
The **existing** generic presenter is extended (not duplicated) with a `kind="record"` render mode alongside the original `kind="measurement"`. A record-kind import shows: how many records were found, the **date range**, how many **have a time** vs **have no time**, which dates were **skipped** (and why), which **will be created**, and which **will not** (with reasons — duplicate, marked-skipped, invalid). Facts only, never a verdict — every line derives from structured fields the adapter set. Body-measurement output is unchanged.

### 4.4 Provenance, idempotency, audit (`StructuredImportRun`)
One generic model records each batch: user, target domain, source artifact, source label, and created/skipped/duplicate/failed counts plus a per-record `manifest`. It is the **artifact-idempotency key** (an artifact that already produced a run for a domain never re-imports) and the **per-record audit**. `link_artifact()` points the artifact at the run. Per-record dedup is the adapter's deterministic key (e.g. journal: user + date + time + title).

---

## 5. What stays the model's job vs WLJ's job

| Step | Owner |
|---|---|
| Recognize "this upload is a journal to import" and call the intent with `source_artifact_id` | **Model** (perception) |
| **Determine every record's date, time, boundary, and skipped state** — from the document's own explicit headers; validate; decide what can/can't be created and why; render the preview; require confirmation; create atomically; dedup; provenance; audit; report actual counts | **WLJ** (deterministic) |

WLJ never interprets the document bytes and never rewrites the user's words. The **body is stored faithfully** (escaped, paragraph-preserved HTML via the Rich Text pipeline) — never summarized.

### 5.1 Deterministic date grounding (NON-NEGOTIABLE — "never invent a date")

**Dates are deterministic truth, never a model output.** When a source **document** is uploaded, WLJ parses the record dates, times, boundaries, and skipped days **only** from the document's own **explicit date headers** — read from the artifact's extracted text — and **ignores any date the model proposes**. A model-transcribed date can be wrong; the document is the sole authority.

- The model does **not** transcribe or normalize dates for an uploaded journal — it passes `source_artifact_id` and an empty `entries`; WLJ reads the document. (`entries` is used **only** for a journal typed directly into the chat, where there is no document to ground against.)
- A date is valid **only** if it comes from an explicit header actually present in the source. WLJ **never infers** a year, month, or boundary, and **never manufactures** a date.
- When WLJ cannot confidently recognize a header (no headers found, an unparseable/invalid calendar date, or a prose line that merely begins with a date), it **reports uncertainty** — it imports nothing rather than risk a wrong date. Better to under-import and ask than to fabricate.
- The parser tolerates real export quirks (leading list numbers, weekday names, `Sept`/abbreviations, 2- or 4-digit years, a time smushed onto the year) but treats only header-shaped lines as boundaries.

**Certification (permanent fixture):** `apps/ai/tests/test_journal_import_date_grounding.py` — a journal document spanning **Aug 29 – Sep 8 2022** (Sep 5 skipped). It asserts the parser extracts exactly the source's dates, preserves times, identifies the skipped day, and — the regression that created this rule — that when the model **fabricates** Oct-2023 dates, **not one** of them is ever created. (Origin: the 2026-07-20 production defect where a Sept-2022 journal was reported as "6 entries from October 10–15, 2023.")

---

## 6. Scope boundary (explicit)

- This is the **CoS-orchestrated** import path (conversational: upload → recognize → preview → confirm). It is a **different entry point** from the existing **in-domain file-upload importers** (Legacy GEDCOM, medical lab-PDF, finance CSV/OFX, meals receipts, contacts VCF, HealthKit). Those are **out of scope** for this milestone and are **not** consolidated here — doing so is unnecessary blast radius on working code. They may migrate onto this engine opportunistically later.
- Recognition quality is the model's; WLJ's guarantee is that nothing is created without validation, confirmation, provenance, and audit, and that reported counts are the *actual* results of execution.

---

## 7. Adding a new domain (the whole checklist)

1. Add a typed `import_<domain>_<records>` tool schema (with `source_artifact_id` + per-record `confidence`).
2. Write a thin `StructuredImportAdapter` subclass (validate / create_one / dedupe_exists / preview_detail) and `register_import_adapter(...)`.
3. Register a preview renderer (`register_import_renderer(key, kind="record", …)`).
4. Wire the standard intent registration (handler map, engine category, execute dispatcher, `handle_import_<domain>` thin handler, `DAY1_ACTION_ALLOWLIST`, `ALLOWED_WRITE_INTENTS`, `DATA_CONFIRM_INTENTS`, `_ALWAYS_CONFIRM_INTENTS`, `action_policy`).
5. Add a certification test that drives a realistic model-produced batch through the engine and asserts preview + creation + dedup + provenance + counts.

Journal is the reference implementation (`apps/ai/import_adapters/journal_import.py`).

---

*Companion execution/status lives in the changelog and the memory topic, never in this governing document.*
