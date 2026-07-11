# WLJ Multimodal Truth — "An Arrival Path, Not a Pipeline"

**Status:** Slice 1 shipped (2026-07-11) — scale photo → `log_weight`. Governing principle established.

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
