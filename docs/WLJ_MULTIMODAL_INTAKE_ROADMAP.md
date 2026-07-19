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
| Phase 1 — Universal intake | 🟡 IN PROGRESS | — | P1.1–P1.6 |
| ├ P1.1a Shared attachment module + image normalization + drag-drop | ✅ DONE | `7f579637` | New `static/js/wlj-attachments.js` (build once) consumed by BOTH chat surfaces: EXIF orientation, downscale to 2048px, HEIC→JPEG (WebKit/iOS), compress under cap → kills "file too large" + sideways photos; widened `accept` (images incl HEIC → Photos/Camera/Browse via OS sheet); drag-and-drop. Browser-verified. |
| ├ P1.2a Universal intake — server foundation (validator + upload endpoint) | ✅ DONE | `a509fc95` | Generalized `upload_validation.py`: byte-sniffing for ALL classes + per-class caps + graceful reject. New endpoint `POST /assistant/api/attachments/` → shared `store_and_persist_artifact` → durable `MultimodalArtifact`. Tests + browser-verified. |
| ├ P1.2b **WLJ Attachment Framework** (domain-agnostic client) | ✅ DONE | _(this change)_ | `WLJAttachments.mount(config)` — reusable, config-driven controller (`classes`/`maxItems`/`endpoint`/`uploadParams`/`previewStyle`/callbacks) with XHR upload+progress, reusable chips/thumbs + per-type icons, `getArtifactIds`/`getImagesPayload`/`remove`/`clear`. New `static/css/wlj-attachments.css`; loaded platform-wide from `base.html` (drop-in on any page). Governing doc §10 records it. Browser-verified domain-agnostically (scratch mount: PDF→document, PNG→image, WAV→audio all uploaded; 2 chips + 1 thumb; remove works; no double-load; no console errors). NEXT: adopt in chat surfaces + send-wiring; then per-domain adoption (Meals/Medical/…). |
| Phase 5 — Scale (opportunistic) | ⬜ DEFERRED | — | B4b, D2–D4 |

*Update this ledger (and the changelog) after every milestone. Do not embed execution status in the governing architecture doc.*
