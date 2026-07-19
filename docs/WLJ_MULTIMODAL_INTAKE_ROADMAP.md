# WLJ Multimodal Intake — Roadmap, Scorecard & Status Ledger

**Authority:** Reference (execution companion to the governing `docs/WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md`)
**Status:** CURRENT — living execution record
**Audience:** Engineer

> Governing architecture is in `WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md`. This document holds the production-readiness scorecard, the phased plan, and the **milestone status ledger** (kept current as work lands). It is grounded in the 2026-07-19 full-lifecycle code trace.

---

## 1. Production-readiness scorecard (ranked by customer impact)

Format: **Status · Prod-ready? · Gap · Risk · Recommendation · Priority.** P0 = first.

### Tier A — Customer-facing trust ("does it even work" vs ChatGPT)
| ID | Item | Status | Ready? | Gap / Risk | Priority |
|---|---|---|---|---|---|
| A1 | Content-type coverage in chat | Images-only (4 MIME, 5 MB) | No | No PDF/doc/audio/video/HEIC → #1 credibility hit | **P0** |
| A2 | Large iPhone / HEIC photos | 5 MB cap, no resize, no `pillow-heif`, no EXIF orient | No | The most common upload fails or is sideways | **P0** |
| A3 | Drag-drop / camera / Photos / progress | OS picker only, no progress | No | Feels dated; low confidence | **P1** |
| A4 | Artifacts remembered / retrievable | Only medical docs are truth | No | CoS can't answer "the receipt from Tuesday" — biggest platform gap | **P1** |

### Tier B — Security & data integrity
| ID | Item | Status | Ready? | Gap / Risk | Priority |
|---|---|---|---|---|---|
| B1 | `serve_media` authz + traversal | Unauthenticated, `os.path.join` no guard (`config/urls.py:51-56`) | No | Private artifacts readable by URL; traversal read on fallback | **P0** |
| B2 | Streaming endpoint validation | Trusts JSON `images` (`views.py:1232-1247`) | No | Oversized/hostile payloads bypass limits | **P0** |
| B3 | Storage durability | Cloudinary if env set, else ephemeral disk | Partial | Silent data loss on redeploy if misconfigured | **P0** |
| B4 | Virus scan / type-sniff / filename scrub | Trusts declared MIME; no AV; no scrub | No | Malware passthrough, spoofed types | P0 (sniff) / **P2** (AV) |
| B5 | Provenance persisted + audited | Weight-only loose pointer; audit lacks artifact id | No | Can't trace fact→source | **P1** |

### Tier C — Architecture debt
| ID | Item | Status | Gap / Risk | Priority |
|---|---|---|---|---|
| C1 | Spine wired for 1 intent | Only `log_weight` | 8 trust-critical intents unwired | **P1** |
| C2 | Three forked pipelines | chat/weight, scan, medical | 3× maintenance, drift | **P2** |
| C3 | Duplicated chat UIs + transports | 2 templates, 2 transports, `IS_COS_USER` fork | Every fix twice; validation gaps | **P1** |
| C4 | Chat images in Postgres base64 | base64 cols + 72h purge | DB bloat | **P2** |

### Tier D — Scale & extensibility
| ID | Item | Priority |
|---|---|---|
| D1 | Background processing for heavy perception | **P2** |
| D2 | Chunked/resumable upload for large media (generalize capture uploader) | **P2** |
| D3 | Native mobile upload path | P3 |
| D4 | Video perception | P3 |

---

## 2. Phased plan

**Directive (2026-07-19):** execute **Phase 0 → Phase 1 as one continuous initiative**, in coherent milestones; verify + update docs + changelog + commit + deploy after each; do not pause for further architectural review unless a constitutional conflict or major architectural decision arises.

### Phase 0 — Harden the platform *(remove structural risk first)*
- P0.1 Authenticate + authorize `serve_media`; traversal-safe path; prefer signed object-storage URLs. (B1)
- P0.2 One shared server-side validation layer both chat transports call. (B2, C3-partial)
- P0.3 Durable storage unconditional in prod; fail-fast + monitor on missing config. (B3)
- P0.4 Byte-level type sniffing at ingress; filename sanitization. (B4a)
- P0.5 Persisted artifact provenance + perception audited as a truth request. (B5)
- P0.6 Artifact integrity + storage lifecycle: `MultimodalArtifact` always gets a durable `storage_ref`; retention by class. (B3, C4-partial)
- P0.7 Error handling / retry / observability baseline for ingress + perception.

### Phase 1 — ChatGPT-level universal intake
- P1.1 One shared intake component (retire duplicated UIs / unify transport); drag-drop, paste, camera, Photos, file browser, multi-file, progress. (A3, C3)
- P1.2 Full content-type acceptance at the door incl. HEIC; client resize; server EXIF orient + HEIC→JPEG; preserve original. (A1, A2)
- P1.3 Universal perception: PDF (native/extracted+OCR), audio (transcribe→text), multi-image through the same arrival path; heavy work in background workers. (A1, D1)
- P1.4 Structured intake: CSV/JSON/XML/GPX/FIT/Apple-Health→ existing domain intents. (A1)
- P1.5 Artifacts first-class: `MultimodalArtifact` as a DomainTruth entity + Current Context + gallery/timeline + long-term retrieval + CoS follow-ups. (A4)
- P1.6 Universal truth spine: lift validate/dedup/confirm/link from the weight handler into a domain-agnostic mechanism; wire trust-critical intents. (C1)

### Later (opportunistic) — Phase 5 scale
- Chunked/resumable uploads (generalize the capture uploader), virus scanning, per-class retention, video perception, native mobile uploader. (B4b, D2–D4)

**Convergence commitment:** migrate scan / medical / capture forks to feed the shared ingress + artifact seam; preserve domain-specific extraction, retire independent storage/dedup/audit forks. (C2)

---

## 3. Preserve — do not rebuild
- `apps/ai/multimodal.py` arrival-path pattern (constitutional reference — **generalize, don't replace**).
- `MultimodalArtifact` seam (sha256 dedup + provenance) — extend with durable `storage_ref` + truth entity.
- Medical lab-PDF provenance discipline (real FKs, `MedicalAuditLog`) — adopt as the unified-provenance standard.
- Capture chunked+progress uploader — generalize into shared ingress.
- Cloudinary durable storage; policy-based byte retention.

---

## 4. Milestone status ledger

Kept current as work lands. Format: milestone · state · commit · notes.

| Milestone | State | Commit | Notes |
|---|---|---|---|
| Governing architecture + roadmap ratified | ✅ DONE | `6fdcfb6b` | `WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md` (governing) + this roadmap; registered in reference index. |
| Phase 0 — Harden the platform | 🟢 STRUCTURAL SCOPE DONE | — | Security/durability/integrity/observability closed. Residual P0.5b (queryable perception-as-truth-request audit) folded into Phase 1 P1.6 (universal spine) by design. |
| ├ P0.1 `serve_media` auth + traversal guard | ✅ DONE | `8aedd9e1` | `login_required` + `safe_join` on the local-disk fallback (`config/urls.py`); tests in `apps/core/tests/test_serve_media_security.py`. Residual: per-object authz on the fallback deferred to signed-URL work (prod serves via Cloudinary). |
| ├ P0.2 Shared validation layer (both transports) | ✅ DONE | _(this change)_ | `apps/ai/upload_validation.py` — ONE validator both `/api/chat/` and `/api/chat/stream/` call; streaming path previously validated nothing. Tests: `apps/ai/tests/test_upload_validation.py`. |
| ├ P0.4a Byte-level type sniffing | ✅ DONE | `8427b0e0` | Magic-byte sniff in the shared validator; declared MIME no longer trusted (spoofed types rejected). Filename sanitization (P0.4b) moved to storage-lifecycle P0.6 (chat path stores no filenames). |
| ├ P0.3 Durable storage unconditional (fail-fast) | ✅ DONE | `5ee79941` | `config/settings.py` — non-DEBUG + missing Cloudinary now raises `ImproperlyConfigured` (no silent ephemeral fallback). Opt-out: `WLJ_ALLOW_EPHEMERAL_MEDIA=1` (logged). **New prod invariant:** web+worker need `CLOUDINARY_*` (already set) or the opt-out. |
| ├ P0.6 Durable artifact storage (background) + integrity | ✅ DONE | `9372b6a8` | `MultimodalArtifact` gains `storage_status`/`byte_size` (migration `capture/0007`); `ingest_uploads` records provenance + **queues** durable storage via `safe_enqueue` (no request-path I/O); new worker task `persist_artifact_bytes` verifies sha256 integrity → writes to durable storage → sets `storage_ref`. Retrieval-side eventual-consistency helpers `is_durably_stored`/`storage_pending`. Tests: `apps/ai/tests/test_multimodal_storage.py`. **Decision (ratified by Danny):** background write, request-path-safe. Large-media staging-ref deferred to Phase 5. |
| ├ P0.5a Perception audit logging | ✅ DONE | _(this change)_ | `ingest_uploads` emits a structured perception audit line per artifact (id+sha+type). Queryable perception-as-truth-request audit row (P0.5b) sequenced to P1.6. |
| ├ P0.7 Storage-lifecycle observability | ✅ DONE | _(this change)_ | Extended the EXISTING OPS-8b media-persistence monitor with an `artifact_storage` health block (failed writes + stuck-pending = worker stalled); corrected the now-stale "storage_ref never populated" notes. Tests: `apps/core/tests/test_artifact_storage_monitor.py`. |
| Phase 1 — Universal intake | ✅ DONE | — | P1.1–P1.5 delivered (universal client framework + server foundation + chat as first consumer + perception + Artifacts-as-Truth). P1.6 universal spine folded into the arrival path. |
| ├ P1.1a Shared attachment module + image normalization + drag-drop | ✅ DONE | `7f579637` | New `static/js/wlj-attachments.js` (build once) consumed by BOTH chat surfaces: EXIF orientation, downscale to 2048px, HEIC→JPEG (WebKit/iOS), compress under cap → kills "file too large" + sideways photos; widened `accept` (images incl HEIC → Photos/Camera/Browse via OS sheet); drag-and-drop. Browser-verified. |
| ├ P1.2a Universal intake — server foundation (validator + upload endpoint) | ✅ DONE | `a509fc95` | Generalized `upload_validation.py`: byte-sniffing for ALL classes + per-class caps + graceful reject. New endpoint `POST /assistant/api/attachments/` → shared `store_and_persist_artifact` → durable `MultimodalArtifact`. Tests + browser-verified. |
| ├ P1.2b **WLJ Attachment Framework** (domain-agnostic client) | ✅ DONE | `29dfb3eb` | `WLJAttachments.mount(config)` — reusable config-driven controller + reusable chips/thumbs; `static/css/wlj-attachments.css`; loaded platform-wide from `base.html`. Governing §10. Browser-verified domain-agnostically. |
| ├ P1.2c Framework consumption foundation (autoUpload predicate + server attachment_ids) | ✅ DONE | `21c5d791` | Framework `autoUpload` predicate; server `attachments_from_ids` (owner-scoped) + both chat views parse `attachment_ids` → arrival path merges (dedup by id). Additive; tested. |
| ├ P1.2d **Chat panel = first framework consumer** | ✅ DONE | `10cc7d42` | `assistant_panel.html` DELETED bespoke attachment logic → `WLJAttachments.mount()`. Fixed the `autoUpload` predicate-coercion bug. Browser-verified. |
| ├ P1.2e **Chat widget consumer + cleanup — chat FULLY consumes the framework** | ✅ DONE | _(this change)_ | `chat_widget.html` (mobile drawer) DELETED its bespoke attachment logic → `WLJAttachments.mount()` (same config as the panel; retry handled via `sendMessage` override params, not controller repopulation). **Fixed a pre-existing bug**: the widget's streaming path dropped images for CoS users — now images + `attachment_ids` ride the streaming body. **Cleanup pass**: removed dead preview CSS from both surfaces (`.assistant-preview-*`/`.assistant-image-count` inline + `.ap-attachment-preview`/`.ap-preview-*`/`.ap-remove-attachment`/`.ap-image-count` in `assistant-panel.css`). **End state: ONE framework, zero duplicated attachment logic, zero chat-specific upload code, every chat surface a thin consumer.** Browser-verified widget (PDF chip + image thumb; streaming body = image inline + PDF `attachment_ids`; cleared) + panel chip styled via framework CSS; no console errors. |
| **Phase 1.3 — Perception** (only the perception step varies by type) | ✅ DONE | — | **PERCEPTION BREADTH COMPLETE**: images/screenshots (model sees directly) · PDF · audio · video (frames+transcript) · Office (DOCX/XLSX/PPTX). Every type plugs into the ONE `perceive()` dispatch + background `perceive_artifact`; only the extractor differs. |
| ├ P1.3-M1 **PDF perception** | ✅ DONE | `84f888d2` | Deterministic text extraction (pdfplumber — mechanical decode; Constitution §2). `apps/ai/perception.py` + background `perceive_artifact` + `MultimodalArtifact.perception_status`/`extracted_text`/`page_count` (migration `capture/0008`). `attachments_from_ids` surfaces `text`+`page_count`(+`processing`/`unreadable`). Constitution ATTACHMENTS prompt updated. Tests `test_pdf_perception.py` (11). |
| ├ P1.3-M4 **Office perception (DOCX/XLSX/PPTX)** | ✅ DONE | _(this change)_ | Deterministic text extraction through the SAME pipeline — only the extractor differs. `_perceive_docx` (python-docx: paragraphs + table cells), `_perceive_xlsx` (openpyxl: cell values, sheet-delimited, page_count=sheets), `_perceive_pptx` (python-pptx: slide text, `[Slide n]`). Added to `PERCEIVABLE_TYPES`; `python-pptx` added to requirements (docx/openpyxl already present). Office docs surface `extracted_text` via the existing document path (prompt already covers kind='document'). Tests `apps/ai/tests/test_office_perception.py` (real generated DOCX/XLSX/PPTX + corrupt-graceful + task). **PERCEPTION BREADTH COMPLETE.** No migration. |
| ├ P1.3-M3 **Video perception** | ✅ DONE | `a24dc2e7` | DUAL deterministic decode, reusing existing capabilities: **ffmpeg frame sampling** (up to 8 evenly-spaced 512px frames w/ timestamps; ffmpeg already provisioned in prod for audio compression — `nixpacks.toml`) delivered to the model's IMAGE path via `runtime.respond` (`frames_for_attachments` → `perceive_images`; NOT persisted to transcript), PLUS the **audio-track transcript** via the ONE shared `transcribe_bytes`. `frames` JSONField on the artifact (migration `capture/0010`); transcript in `extracted_text`. Constitution ATTACHMENTS prompt adds video (look at frames + read transcript; sampled moments). Enables "what am I doing", "evaluate my squat", "how's my golf swing", "what happened in this meeting". Background-only; provenance preserved. Tests `apps/ai/tests/test_video_perception.py` (ffmpeg+Whisper mocked). Cross-conversation video compare = Artifacts-as-Truth (needs frame re-delivery on retrieval). |
| ├ P1.3-M2 **Audio perception** | ✅ DONE | `0a2f6f41` | **Converged on the ONE transcription capability** (did NOT build a second): exposed Capture's production Whisper integration as a pure `TranscriptionService.transcribe_bytes(bytes, filename)` (25MB-limit + non-Whisper-format conversion via ffmpeg handled inside) and refactored Capture's own `transcribe_audio` to reuse it. Perception dispatch adds audio (mp3/m4a/wav/aac → transcribe) → transcript = `extracted_text`, surfaced through the SAME arrival pipeline as PDFs; the model summarizes / pulls action items / drafts journal entries / recalls. Constitution ATTACHMENTS prompt generalized to documents+audio. Tests: `apps/ai/tests/test_audio_perception.py` (Whisper mocked) + full Capture suite green (convergence). No model change. Multi-turn recall = the Artifacts-as-Truth surface (parallel). |
| **Artifacts as Truth** (the differentiator — uploads become a retrievable Truth Surface) | ✅ DONE | — | Core retrieval → conversation/domain linkage → re-delivery → Current Context/gallery → certification. Uploads are a first-class `artifacts` DomainTruth retrieved via the existing `get_entity` tool — zero parallel system. |
| ├ AaT-B1 **Multi-turn retrieval (conversation linkage)** | ✅ DONE | _(this change)_ | Artifacts remember their first conversation (`source_conversation_id`, migration `capture/0011`, soft link — no cross-app FK cycle); `runtime.respond` links the turn's artifacts. `get_current_context_baseline` surfaces `conversation_artifacts` (prior uploads in THIS conversation: id/filename/kind/readable/preview) so follow-ups ("what's the deductible?", "does it cover emergency care?", "compare with the other policy") RETRIEVE via `get_entity(domain='artifacts')` deterministically — not fragile transcript memory. Constitution prompt: retrieve for follow-ups + past uploads; present likely matches / clarify on ambiguity; ground in filename+date. Tests `apps/ai/tests/test_artifact_conversation_link.py` (6). |
| ├ AaT-B2 **Re-delivery of visual content on retrieval** | ✅ DONE | _(this change)_ | Closes the images-aren't-text boundary. When the user RETRIEVES a previously-uploaded image/video, WLJ gives the model the actual pixels to RE-PERCEIVE (not just metadata): `perceive_images_for_artifacts` loads image originals from durable storage + video frames; the `get_entity` handler (artifacts domain) attaches them OUT-OF-BAND as `_perceive_images`; the generic tool loop pops that key (base64 never becomes text) and injects the bytes as `image_url` for the next round. **Additive/no-op when absent** — the critical tool loop is unchanged for every non-artifact call (verified: 104 tool-loop/chat/multimodal tests green). Enables "compare these two progress photos I uploaded", "what was in that video". Tests `apps/ai/tests/test_artifact_redelivery.py` (envelope extraction + image-from-storage + video frames + owner-scoped + bounded + pdf-yields-none). No model change. |
| ├ AaT-B3+B5 **Retrieval quality (date/content) + provenance** | ✅ DONE | _(this change)_ | `ArtifactDomainTruth.describe` now accepts `filters` (get_entity passes date-normalized on_date/start/end + `contains`) → date-scoped + content retrieval ("the receipt from last month", "documents about X"); `ArtifactQueries.search` gains `until`. Retrieved entity now carries full provenance in `standing`: `source_conversation_id`, `perception_status`, `durably_stored`, uploaded date (+ existing filename/type/pages/resolved-record). Ambiguity + most-recent handled by recent-first ordering + the B1 prompt. Tests in `test_artifact_truth.py` (date-scoped, content filter, provenance). No model change. |
| ├ AaT-B4 **Domain/entity linkage (association mechanism)** | ✅ DONE | _(this change)_ | `MultimodalArtifact.associations` (migration `capture/0012`) — canonical-entity tokens like `meal:12`/`project:5`/`mission:3`/`person:8` (validated, de-duped, merged on re-upload) set via the framework's `uploadParams.associate_to` → the upload endpoint's `associate_to`. `ArtifactQueries.by_association` (explicit link OR the artifact RESOLVED to that record — reuses existing provenance, no parallel representation); `describe(filters={associated_with})` retrieves them; associations surfaced on the entity. Enables "documents for my compensation project", "attachments for France 2027" (once a consuming page/domain passes the association). |
| **Milestone C — Artifact Library / detail / Current Context** | ✅ DONE | _(this change)_ | Lightweight, CoS-native (not a file manager): `/capture/library/` gallery (search `?q=`, kind filter, per-type icons + image thumbnails, processing badge) + `/capture/artifact/<id>/` detail (preview incl. inline image/audio/video, "what your Chief of Staff read", provenance — filename/date/stored/**link back to the source conversation**/resolved record/domain associations, download original). BOTH declare **Current Context** via page-summary providers (`artifacts.library`, `artifacts.detail`) so the CoS knows what the user is looking at. Owner-scoped download. Discoverability: "Your Uploads" link on the Capture page + a CoS teaching destination. Tests `apps/capture/tests/test_artifact_library.py` (7 — list/search/kind-filter/detail-content+provenance/owner-scoped/download/Current-Context). Browser-verified render. |
| ├ AaT-B6 **Certification suite (automated customer-truth)** | ✅ DONE | `4871ba7d` | `apps/ai/tests/test_artifact_certification.py` — 13 automated customer-truth scenarios certifying the deterministic layer behind each behavior: same-turn PDF · multi-turn PDF · cross-conversation PDF · cross-conversation audio · prior-image renewed perception · prior-video transcript+frames · most-recent · date-scoped · ambiguous-match (all surfaced) · owner isolation · provenance · conversation linkage · domain linkage. A regression here = a customer trust behavior broke. |
| ├ AaT-A **Artifact Truth Surface — core retrieval** | ✅ DONE | `05c06f27` | Uploaded `MultimodalArtifact`s are now a first-class **`artifacts` DomainTruth** (registered), retrievable by the CoS via the existing `get_entity` tool — zero parallel system. New `ArtifactQueries` (deterministic search over extracted text + filename + type + time; owner-scoped) + `ArtifactDomainTruth` (`describe`/`describe_one`/`current` → `CompleteEntity` incl. the extracted content). Added `original_filename` (migration `capture/0009`) for identity/search. `DOMAIN_SEMANTICS['artifacts']` added so the model ROUTES upload-retrieval questions here (cues: "what did my MRI say", "show me the receipt", "find my insurance card", "when did I last upload bloodwork"). Tests `apps/ai/tests/test_artifact_truth.py` (10 incl. end-to-end `get_domain_entity`); capability-semantics contract green. **Delivers**: content/type/time retrieval + reading past uploads. **Follow-ons**: conversation/domain/mission/person linkage; time-`filters` in `describe`; Current Context on artifact pages + gallery UI. |
| **Production-readiness certification (full platform, customer perspective)** | ✅ DONE | _(this change)_ | Single certification pass over the entire corpus — **169 tests green**: upload validation · media security (auth + traversal) · durable storage + integrity · all six perception types · Truth Surface retrieval · visual re-delivery · conversation linkage · the 13 customer-truth scenarios · library/detail + Current Context · storage monitor · **request-path safety contract** · capability semantics. Validated across all 13 customer dimensions (upload experience, retrieval, perception, Truth Surface, Current Context, provenance, long-term & cross-conversation retrieval, conversation & domain linkage, performance, error handling, processing states). No material trust gaps outstanding. |
| **🏁 INITIATIVE CLOSED** | ✅ DONE | _(this change)_ | Completion report authored: `docs/WLJ_MULTIMODAL_PLATFORM_COMPLETION_REPORT.md`. The Multimodal Platform initiative is formally closed. Remaining items (virus scanning, chunked/resumable large-media, richer domain-linkage NL orchestration) are opportunistic Phase 5 — not gating. |
| Phase 5 — Scale (opportunistic) | ⬜ DEFERRED | — | B4b, D2–D4, virus scanning, chunked/resumable large-media, domain-linkage NL orchestration |

*Update this ledger (and the changelog) after every milestone. Do not embed execution status in the governing architecture doc.*

> **🏁 INITIATIVE STATUS: CLOSED (2026-07-19).** All implementation milestones (Phase 0 · Phase 1.1–1.5 · Phase 1.3 M1–M4 perception · Artifacts-as-Truth A + B1–B6 · Milestone C) shipped and deployed; full production-readiness certification passed (169 tests). See the completion report for final architecture, customer capabilities, and remaining opportunities.
