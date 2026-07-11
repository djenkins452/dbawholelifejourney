# WLJ Multimodal Truth — "An Arrival Path, Not a Pipeline"

**Status:** Slice 1b shipped (2026-07-11) — the scale photo → `log_weight` path is LIVE end-to-end
on the model-interface runtime (upload → artifact → perception → candidate → deterministic path →
confirmation round-trip → provenance). Slice 1 (2026-07-11) established the deterministic spine.
Governing principle established. **Scope is still ONLY the scale photo** — no glucose/receipts/
contacts/PDFs yet.

## Principle
An uploaded image/PDF/scan/receipt/screenshot is a **new way the conversational model ARRIVES
at the same intents and truth reads it already emits.** It is NOT a new subsystem, NOT OCR, NOT
image parsing, NOT another intelligence layer.

- **OpenAI owns:** perception, OCR, extraction, reasoning, summarization, planning.
- **WLJ owns:** artifact storage + provenance, deterministic validation, duplicate detection,
  confirmation policy, action execution, audit. **WLJ never interprets pixels.**

## The spine (entirely reused)
```
Upload → store artifact (hash + provenance) → model PERCEIVES image in the turn
      → emits candidate = existing named-intent tool call, tagged source_artifact_id + confidence
      → WLJ validates the extraction (intent schema + plausibility)
      → duplicate detection (artifact hash + fact-level)
      → confirmation POLICY (WLJ decides; perception raises the bar)
      → execute_intent → UAIO → write canonical truth
      → link artifact → record (provenance) + audit
      → OpenAI narrates
```
A "candidate" is simply an intent **in the pending-confirmation state** we already had — no new
execution concept.

## Components
- **`apps/capture/models.py :: MultimodalArtifact`** — the ONE new storage seam. `{user, sha256,
  content_type, storage_ref, kind, status, resolved_intent/object_type/object_id}`. Unique
  `(user, sha256)` = artifact-level dedup. Links to the deterministic record it produced.
- **`apps/ai/multimodal.py`** — deterministic helpers: `store_artifact` (hash dedup),
  `validate_weight` (plausibility), `find_duplicate_weight` (fact dedup), `requires_confirmation`
  (policy), `link_artifact` (provenance). Pure; no OCR, no parsing.
- **Intents** carry optional `source_artifact_id` + `confidence` (log_weight first). The handler
  runs validation → dedup → confirmation policy → execute → provenance, reusing the existing path.
- **Perception seam:** `services._call_api_with_tools(images=…)` now attaches images to the user
  turn so the model can PERCEIVE and call tools together; `model_interface.generate(images=…)`.

## Live wiring (slice 1b) — the model-interface runtime
The chat turn carries the image all the way to the model-interface runtime and back, for BOTH
sync chat and streaming/background generation:

1. **Chat view → gateway.** `AssistantChatView` (multipart) and `AssistantChatStreamView` (JSON:
   `image_data`/`image_mime_type` or an `images` list) extract the upload and pass it to
   `CoSGateway.respond(...)`. The gateway resolves the runtime ONCE; for `use_model_interface`
   users that is `ModelInterfaceRuntime` — **image turns are never routed to legacy Beth.**
2. **Runtime stores the artifact + builds the perception payload.**
   `ModelInterfaceRuntime.respond` calls `multimodal.ingest_uploads(user, …)`, which stores each
   image as a `MultimodalArtifact` (hash dedup, provenance-ready `artifact_id`) BEFORE generation —
   so the artifact exists regardless of sync/streaming — and returns `(images, attachments)`.
3. **Both paths receive images + attachments.** Non-streaming calls
   `generate(images=…, attachments=…)`; streaming dispatches
   `run_model_interface_generation.delay(…, images=…, attachments=…)` (base64 + dict — Celery-safe).
4. **The model receives everything it needs.** `generate` passes `images` to the tool loop
   (perception) and threads `attachments` into `current_context.attachments` (schema 2.3) — each
   with its `artifact_id`. The constitution's ATTACHMENTS clause tells the model to read the value
   and call `log_weight(value, unit, source_artifact_id, confidence)`.
5. **The candidate routes through the SAME deterministic path.** `log_weight` is now in the
   model-interface write set (`ALLOWED_WRITE_INTENTS`) and the action allowlist
   (`DAY1_ACTION_ALLOWLIST`); the dispatch sends it through
   `action_interface.request_action → execute_action → handle_log_weight` → validate → dedup →
   confirmation POLICY → UAIO → provenance link + audit.
6. **Confirmation round-trip.** `handle_log_weight` computes confirmation from the CANDIDATE DATA
   (low confidence / duplicate / sensitive intent). `execute_action` surfaces that handler-returned
   `confirmation_required` as an env status (not a failure), so `request_action` mints a BOUND
   confirmation. On the user's "yes", `resolve_pending_action(confirmation_id, confirm=true)`
   re-executes with `confirmed=true`; `execute_action` forwards `confirmed` for
   `_DATA_CONFIRM_INTENTS` so the handler bypasses its own data gate and writes (provenance still
   links because `source_artifact_id` was stored in the bound confirmation's params).
7. **Results, not intentions.** Beth reports only the REAL `ActionResult` — she never claims a log
   happened unless WLJ confirms the write; she asks first when confirmation is required and reports
   rejection/duplicate outcomes accurately.

Tests: `apps/ai/tests/test_multimodal_wiring.py` (17) — routing, artifact creation, current-context
attachment, high-confidence write, low-confidence/duplicate confirmation + approval/rejection
round-trip, implausible rejection, artifact- & fact-level dedup, provenance link, streaming
passthrough, and typed logging unchanged. Perception (the model reading pixels) is NOT unit-tested
(no API key); the deterministic spine is fully covered here + in `test_multimodal.py` (14).

## Confirmation policy (WLJ owns the decision; the model only proposes)
Confirm when: the intent writes **clinical / financial / identity** truth; OR perception
**confidence < 0.85**; OR a **duplicate** is suspected; OR the value is **implausible** (rejected
outright). High-confidence, low-risk, reversible writes auto-execute with an undo affordance.

## The invariant that protects the architecture
**A candidate is untrusted until deterministically validated; sensitive/low-confidence candidates
are untrusted until confirmed.** Fabrication-prevention applied to perception. A misread label is a
validation/confirmation event — NEVER a reason to build an OCR/parser inside WLJ.

## Scaling (audio / video / documents / wearables)
The spine is modality-agnostic: `Attachment → perception → candidates → validate → execute →
audit`. Only *ingestion* differs per modality (voice → transcript; video → frames; PDF → pages;
wearable screenshot → image). Each new modality adds an ingestion normalizer, then rejoins the one
candidate pipeline. WLJ never gains per-modality intelligence — only per-modality storage.

## Integrates with
- **Truth/Action contract** (`WLJ_LLM_TRUTH_ACTION_CONTRACT.md`) — candidates are the existing
  intents; provenance source `user_upload:artifact_id` in the truth envelope; audit chain.
- **Current Context** — an upload is a Pillar-4 focus ("what the user just showed me"), parallel to
  the `wlj-context` page focus.

Tests: `apps/ai/tests/test_multimodal.py` (14 — store/dedup, validation, policy, execute, provenance).
