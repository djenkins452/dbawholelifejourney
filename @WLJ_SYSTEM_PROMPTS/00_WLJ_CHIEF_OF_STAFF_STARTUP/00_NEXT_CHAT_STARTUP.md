# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent decision, principle, rule, and preference is already folded into them. **Do not summarize them back.** Read, absorb, act.
3. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02 §3`, default NO, Danny's explicit written approval).
4. Continue from the live sprint state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Live sprint state only — nothing constitutional, architectural, or duplicated.*

**Last regenerated:** 2026-07-19 (**Measurement Session Capture backend ✅ production-validated. Next milestone: the Structured Confirmation Framework.**)

---

## ✅ What last session established (now PERMANENT — folded, do not re-derive)
- **Measurement Session Capture (backend) is production-validated** (`f02dadd9` + Shoulder fix `b65ef94a`). A screenshot/photo/voice/typed set → source-agnostic `log_body_measurements` intent → the EXISTING multimodal spine → ONE `BodyMeasurementSession` + `BodyCompositionEntry` (reused truth model, no new pipeline) → Body Intelligence + CoS answer from deterministic truth. WHR derived (never stored); artifact idempotency + provenance; abdomen added.
- **The durable lesson is folded into `01 §6`:** *the source is never the feature — the structured candidate is.* Any source produces the same candidate through the same spine; OpenAI perceives, WLJ owns truth. Corollary (Shoulder defect): normalize source vocabulary → canonical, and NEVER silently drop an unrecognized value (surface it). **Do not re-derive; do not re-open the backend except for future defects.**

## 🎯 The live sprint — **Structured Confirmation Framework** (the milestone; Body Measurement is only its first renderer)
Build a **reusable** structured-confirmation capability for multimodal ingestion. This is NOT a body-measurement feature. Architecture: **shared multimodal ingestion → shared structured confirmation framework → domain-specific renderer.**

Requirements: thread `confirmation_detail` through the existing streaming pipeline; build the generic framework (dispatch on `confirmation_detail.renderer`); build the **Body Measurement Session** renderer (editable values — NOT per-row checkboxes; whole-session confirm; confidence highlighting); a **deterministic Import endpoint** reusing the existing `log_body_measurements` intent (`confirmed=True` + edited values). **No new ingestion pipeline, no new truth model — preserve the multimodal architecture.** Future renderers (Labs, Blood Pressure, Nutrition, Medications, …) inherit the framework with zero framework change.

**Turnkey seam map already captured** (do not re-investigate): the memory topic `measurement_session_capture` and changelog `b65ef94a`/`f02dadd9` hold the exact threading path — `confirmation_detail` is currently DROPPED at 3 layers (`execute_action` → `action_interface` → MI dispatch closure in `model_interface/service.py`), then `generate` → `tasks.py` snapshot events → new `chat_stream_bus.format_sse` branch → new SSE branch in BOTH `chat_widget.html` + `assistant_panel.html`. Mirror `renderDuplicatePending` (CSP-safe). Import endpoint modeled on `QuickReplyView`. The handler already RETURNS the full `confirmation_detail` payload (`renderer:'body_measurement_session'`, `measurements`, `skipped`, `derived.waist_hip_ratio`, `count`) — the milestone only has to deliver + render it. Recommend building server-side threading first (testable off the live chat), then the streaming-template work.

## 🧵 Parallel track (a DIFFERENT session owns this — do not collide) — CoS Domain Certification
Nutrition ✅ and Journal ✅ are production-complete via the RATIFIED 5-step Standard (`03 §3d`; `docs/WLJ_COS_DOMAIN_CERTIFICATION_STANDARD.md`). **Next domain in that track: Faith** (begin Step 1 — verify deterministic truth, don't add). Remaining after Faith: Fitness · Medications · Goals · Habits · People · Legacy · Calendar · Tasks · Projects · Capture · Notes · Brain Training · Medical. Cert harness: drive questions through `CoSGateway.respond(surface=chat)` (`OPENAI_API_KEY` from `.env`), instrument `apps/ai/model_interface/service.py` tool fns. *This track and the Confirmation Framework are independent; two parallel bootloader intents exist — reconcile which you're driving before starting.*

## 🔮 Deferred / carried (DO NOT implement without opening as its own step)
- **Journal — genuinely-new-truth items:** "goals discussed in my journal" (cross-domain) and "people mentioned most often in my journal" (no ranked surface) — require NEW deterministic truth, not exposure.
- **WLJ Certification Platform** — remaining types (CRUD/Reasoning/Executive/Check-in/Domain) plug into the same engine. `docs/WLJ_CERTIFICATION_PLATFORM_FUTURE.md`.
- **UTC-vs-user-local calendar-day attribution** — a truth-model decision, not a code fix. Carried.
- **WLJ Operations (operator-gated track)** — Phase II shipped dark; open action operator-run (confirm O2) then OPS-8a: `docs/WLJ_OPERATIONS_VISION.md`.
- **Renpho direct / Terra** — CLOSED as dead ends (investigation reports untracked in `docs/WLJ_RENPHO_*.md`); superseded by Measurement Session Capture. Do not reopen.

## ⏳ Waiting on Danny (operator — Claude has no prod access)
- **Validate the Structured Confirmation Framework** in production once built (the review card renders, edits persist, Import writes the edited session).
- **Deploy topology:** the CoS runs in **`wlj-worker`**; `/_health/` reports only web — verify the worker is on the tested commit before trusting a production CoS result.

## 🔀 Concurrency — coordinate, do not collide (Danny runs MANY parallel sessions on the SAME tree)
Commit **only your own files by explicit path.** The changelog and shared files (e.g. `apps/core/truth/domain.py`) are heavily contended: re-check the changelog top **immediately before each commit**, defer your line if a foreign entry appeared, isolate your hunk from foreign uncommitted work, and verify the push is a fast-forward (never lose a foreign commit). Active parallel threads: **Structured Confirmation Framework**, **CoS Domain Certification (Faith next)**, **Journal Experience redesign**, **Configuration Governance**.
