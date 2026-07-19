# WLJ Multimodal Intake — Governing Architecture

**Authority:** Governing (canonical architecture for all multimodal intake in WLJ)
**Status:** CURRENT — ratified 2026-07-19
**Audience:** Engineer
**Companion (execution):** `docs/WLJ_MULTIMODAL_INTAKE_ROADMAP.md` (scorecard + phased milestones + status ledger). Implementation progress lives there and in the changelog — **never in this document.**
**Companion (closure):** `docs/WLJ_MULTIMODAL_PLATFORM_COMPLETION_REPORT.md` — the initiative completion report. **Initiative status: 🏁 CLOSED 2026-07-19** (all milestones shipped + deployed; full production-readiness certification passed, 169 tests). This governing document remains the canonical contract for any FUTURE multimodal work.

> This is the canonical architecture for how a person provides content — images, video, audio, documents, structured files — to the WLJ Chief of Staff (CoS), and how that content becomes deterministic, provenance-bearing, permanently retrievable truth. Every domain (Meals, Fitness, Medical, Faith, Journal, Finance, Relationships, Operations, HR, and future domains) leverages this ONE platform rather than building its own upload path. Conform to this document or amend it deliberately.

---

## 1. Vision

A WLJ user can hand the Chief of Staff **any** practical piece of content as naturally as they would in ChatGPT — a photo of a scale, a lab PDF, a voice note, a spreadsheet, a workout export — and trust that WLJ **understood it, validated it, remembered it, and can act on it forever.**

The differentiator over a general assistant is not perception (the model does that). It is that WLJ turns perceived content into **deterministic truth with provenance** that is validated, permanently retrievable, and safe to act on. ChatGPT forgets the image after the turn; WLJ keeps the *truth* (and, by policy, the artifact) with a verifiable chain back to what the user provided.

**One platform, every domain.** Multimodal intake is a foundational platform capability, not a per-domain feature. A receipt, a lab result, a body-weight photo, and a GPX track all enter through the **same** ingress, become the **same** kind of artifact, and pass through the **same** truth spine — differing only in which domain intent the model calls.

---

## 2. Architectural principles (non-negotiable)

1. **The model perceives; WLJ never interprets pixels or bytes.** WLJ hashes content for identity, stores it, and exposes it to the model. Reading what an image/PDF/audio *says* is the model's job. WLJ contains **no OCR engine, no vision reasoning, no content interpretation** as a reasoning capability. (Deterministic *extraction* utilities — e.g. pdfplumber text, Whisper transcription — are permitted **only** as mechanical decoders feeding the model or a deterministic parser; they are not reasoning.)
2. **Perceived content becomes a normal named intent.** There is no separate "perception → truth" translator. The model emits an existing domain intent tool call, tagged with `source_artifact_id` + `confidence`. WLJ then runs the deterministic spine. This keeps multimodal a **new arrival path to the same intents**, never a parallel truth system.
3. **One arrival path, one artifact seam, one truth spine.** Ingress, the artifact record, and the validate→dedup→confirm→execute→audit→link spine are singular and domain-agnostic. Domain-specific extraction may exist, but it **feeds** the shared seam; it does not fork it.
4. **Deterministic truth boundary.** Every fact written from an artifact is validated deterministically (range/type/policy), deduplicated (fact-level and artifact-level idempotency), confirmed where policy requires, executed through the existing safe action path, audited, and **provenance-linked** back to the artifact.
5. **Artifacts are first-class truth.** A stored artifact is a retrievable truth entity with its own provenance, Current Context, and long-term retrieval surface — not fire-and-forget perception.
6. **Provider-agnostic.** Perception is requested through the single provider seam. No provider name is a system identity. Swapping providers must not touch ingress, storage, the artifact seam, the spine, or retrieval.
7. **Safety and durability are platform guarantees, not per-caller diligence.** Authentication, authorization, validation, type-sniffing, durable storage, and audit are enforced **once** at the platform layer so no domain can accidentally bypass them.

---

## 3. The lifecycle (the canonical pipeline)

```
User attaches  →  INGRESS            (one surface: validate, sniff, normalize, size-manage)
               →  ARTIFACT           (durable store + sha256 identity + dedup + provenance record)
               →  PERCEPTION         (model reads content via the provider seam)
               →  INTENT             (model calls an existing domain intent, tagged source_artifact_id + confidence)
               →  TRUTH SPINE        (validate → dedup → confirm → execute → audit → link)
               →  RETRIEVAL          (artifact + extracted truth are permanent, retrievable, Current-Context-aware)
```

Each stage is a shared platform primitive:

- **Ingress** — the single front door. Accepts the full supported content set (§5), authenticates and authorizes the uploader, sniffs true type from bytes (never trusts the declared MIME), normalizes (e.g. HEIC→JPEG, EXIF orientation), manages size intelligently (client + server resize/compression before rejecting), reports progress, and supports background/resumable transfer for large media. Both the streaming and non-streaming chat transports — and every domain surface — call the **same** ingress validation.
- **Artifact** — every accepted upload becomes a durable artifact: original bytes persisted to object storage (durable, never conditional), a `sha256` content identity, artifact-level dedup, and a provenance record. The artifact is the anchor everything else points to.
- **Perception** — the model receives the content (image as data/URL, PDF/audio decoded or natively input where the provider supports it) and reads it. WLJ requests; it does not interpret.
- **Intent** — the model calls a normal domain intent carrying `source_artifact_id` and `confidence`. No bespoke perception intents.
- **Truth spine** — one domain-agnostic mechanism: deterministic validation, fact-level + artifact-level idempotency/dedup, a confirmation policy (clinical/financial/identity always confirm; below a confidence floor confirm; duplicates confirm), execution via the existing action handlers, a truth-request audit row that records the artifact, and a persisted provenance link.
- **Retrieval** — the artifact and its extracted truth are exposed as a Truth Surface, declared as Current Context on their pages, and browsable/searchable long-term.

---

## 4. Production standards

Any content intake — chat or domain — must satisfy these platform standards:

**Security**
- All uploaded media is served **only** through an authenticated, authorized path (or a signed, expiring object-storage URL). No public, guessable media URLs for personal content.
- Path construction for any served file is traversal-safe (`safe_join`/normalized); a crafted path can never escape the media root.
- True content type is determined by **byte sniffing**; the client-declared MIME is advisory only.
- Filenames are sanitized before storage.
- Document/office content classes are virus-scanned before they are treated as trusted.
- Executable/script-bearing formats (e.g. active SVG) are never served inline as their claimed type.

**Validation & integrity**
- **One** validation layer enforces size, type, and count for **both** chat transports and every domain surface — no transport or endpoint may skip it.
- Every artifact has a `sha256` identity; the same bytes never create two artifacts (artifact-level idempotency) and never write two facts (fact-level dedup).

**Durability & lifecycle**
- Original artifacts are stored to **durable object storage unconditionally** in production; a misconfiguration must fail fast, never silently fall back to ephemeral disk.
- Retention is by artifact class and policy: **facts are permanent**; raw bytes may expire by explicit retention policy (e.g. transient chat images), but never as an accident of storage location.

**Provenance**
- Every fact created from an artifact carries a **persisted** link to that artifact (not merely a response-payload note). The question "where did this fact come from?" always has a deterministic answer.

**Error handling, retry, observability**
- Ingress failures are explicit and recoverable (the user can retry/resume; large-media transfer is resumable where practical).
- Heavy perception/extraction runs in **background workers** (never on the request path — see `WLJ_REQUEST_PATH_SAFETY.md`); the UI shows honest processing status ("understanding your document…"), not a bare spinner.
- Perception is **audited as a truth request**; artifact lifecycle events are logged; storage durability and artifact integrity are monitored operationally.

**Experience (the ChatGPT-parity bar)**
- Drag-and-drop, paste, camera, photo library, and file browser intake.
- Multiple simultaneous files; large iPhone photos accepted without unnecessary rejection.
- Visible upload progress and processing status; background uploads where practical.
- Minimal friction: resize/normalize before rejecting; "file too large" only when genuinely unavoidable.

---

## 5. Supported media types

The platform targets the broadest practical range. Support tiers: **Perceived** (model reads it), **Extracted** (deterministically decoded to feed the model/parser), **Stored** (durably kept + retrievable even if not yet perceived).

| Class | Formats | Target handling |
|---|---|---|
| **Images** | HEIC/HEIF, JPG, PNG, WEBP, TIFF, GIF (static/animated), screenshots, Live Photos, multiple images, large iPhone photos | Perceived. HEIC decoded/normalized; EXIF-oriented; intelligently resized; original preserved. |
| **Video** | MOV, MP4, HEVC, slow-motion, time-lapse | Stored + Extracted (frame sampling / provider video input where available); perception as provider support matures. |
| **Audio** | M4A, MP3, WAV, AAC | Extracted via transcription, then Perceived as text through the same arrival path. |
| **Documents** | PDF, DOCX, XLSX, PPTX, TXT, Markdown, CSV | PDF perceived (native input where available, else extracted text + OCR fallback); office/text/CSV extracted to text/tables. |
| **Structured** | JSON, XML, GPX, FIT, Apple Health export (zip/XML), additional wearable exports | Extracted deterministically into domain intents (e.g. GPX→activity, Health export→metrics). |
| **Other (as appropriate)** | EML, ICS, vCard, RTF, ZIP containers, unknown text | Stored; text-bearing content read by the model; unknown binary stored + surfaced for later. |

**Fallback rule:** an unrecognized but text-bearing file is stored as an artifact and its text made available to the model; an unrecognized binary is stored and surfaced, never silently dropped.

---

## 6. Relationship to the Constitution

Multimodal intake is a **strict application** of the ratified truth/action architecture — it introduces no new constitutional article and requires no Constitutional Review.

- **`WLJ_LLM_TRUTH_ACTION_CONTRACT.md` (Article I).** Perception is the model's; truth, validation, action, provenance, and audit are WLJ's. The arrival path reuses the existing truth boundary (composed truth, freshness/confidence/source envelope) and action boundary (safe deterministic path + audit). Multimodal adds a **source** of intents, not a new authority.
- **No reasoning in WLJ.** The spine is deterministic policy (validate/dedup/confirm/idempotency/link). Making artifacts retrievable is a **truth surface**, not a reasoning capability.
- **`WLJ_PRODUCT_VISION.md` (simplicity).** Building one reusable platform and converging the historical per-domain forks onto it *reduces* WLJ complexity. As frontier perception improves, this platform gets simpler, not more elaborate.
- **`WLJ_REQUEST_PATH_SAFETY.md`.** All heavy extraction/perception is background work; request paths only enqueue and read pre-computed/pending state.

---

## 7. Relationship to Current Context

Every page that displays an artifact **declares it as Current Context** so the CoS knows what the user is looking at (per `WLJ_CURRENT_CONTEXT_CONTRACT.md`):

- An artifact **detail** page (a document, a capture, an image) declares a focused object: `app.model:pk` via the artifact model's `context_ref`.
- An artifact **gallery/timeline** (overview) declares a deterministic page summary: `summary:<key>` via a registered provider.

Artifact models therefore participate in the Narratable/`UserOwnedModel` protocol so a single declaration makes them context-aware. "The user is looking at this receipt / this lab PDF" is always answerable.

---

## 8. Relationship to Truth Surfaces

The stored artifact and its extracted facts are exposed through the existing deterministic Truth Surfaces (per `WLJ_TRUTH_SURFACES.md`) — they do **not** get a parallel retrieval system:

- The artifact is a **Domain Entity** surface: reachable by name/date through the owning domain's `DomainTruth` (`describe`/`describe_one`), exactly as medical lab documents already are. The reference standard for provenance-rich artifact truth is the Medical lab-document entity.
- Extracted facts remain in their domains' canonical truth (a weight is Health truth; a receipt total is Finance truth) with a provenance link to the artifact.
- A missing provider changes **which** surface answers "show me that receipt," never whether it is possible. Artifact retrieval must never require the model to reason over raw bytes — WLJ returns the composed artifact truth.

---

## 9. Relationship to the Model Interface

Intake plugs into the Model Interface seam (per `WLJ_MODEL_INTERFACE_DESIGN.md`) without special-casing:

- Ingress happens **before** generation; the resulting `(images, attachments)` are injected into the turn by the Model Interface runtime.
- **Images** are delivered to perception through the provider seam; **attachments** are surfaced as **data** (each `artifact_id` + type) in the executive/standing context so the model can cite and act on them — WLJ never ships interpreted content, only the artifact and the model's own reading.
- The intent the model emits flows through the normal action interface; the artifact id rides on the intent and into the audit ledger.
- Streaming and non-streaming paths share one ingress and one validation layer (parity is mandatory).

---

## 10. Long-term extensibility

- **The WLJ Attachment Framework (client).** The attachment UI is a single **domain-agnostic** component (`static/js/wlj-attachments.js` + `static/css/wlj-attachments.css`, loaded platform-wide from `base.html`). It knows nothing about the domain it serves; a consuming page calls `WLJAttachments.mount(config)` and declares behavior — `classes` (allowed content), `maxItems`, `endpoint` (upload destination), `uploadParams` (artifact association, e.g. `{associate_to:'meal:12'}`), `previewStyle`, and `onUploaded/onChange/onProgress/onError`. The controller exposes a generic interface (`getArtifactIds`, `getImagesPayload`, `clear`, `remove`, `hasPending`) and renders reusable chips/thumbs (per-type icons, size, progress, remove). Chat, Meals, Medical, Journal, Finance, Operations, and future domains all mount the **same** component with different config — never a per-domain uploader or per-domain chip markup. This is the client expression of "build once, reuse everywhere."
- **New media type** → add a decoder/normalizer at ingress and (if structured) a mapping to existing intents. No new pipeline, no new storage seam.
- **New domain** → it mounts the Attachment Framework and consumes the platform (ingress + artifact + spine + retrieval), defining only its intents; it never builds an upload path or bespoke chips.
- **New provider / native modality** (e.g. native video or audio input) → swap behind the provider seam; ingress, artifact, spine, and retrieval are unchanged.
- **New wearable/export format** → a deterministic parser maps it into existing domain intents through the same arrival path.
- **Convergence commitment:** historical forks (scan drafts/prefills, medical lab-PDF import, capture audio) are migrated to feed this platform's ingress + artifact seam over time; their domain-specific extraction is preserved, their independent storage/dedup/audit forks are retired.

---

*Canonical architecture. Execution status, scorecard, and milestone history live in `docs/WLJ_MULTIMODAL_INTAKE_ROADMAP.md` and the changelog — not here.*
