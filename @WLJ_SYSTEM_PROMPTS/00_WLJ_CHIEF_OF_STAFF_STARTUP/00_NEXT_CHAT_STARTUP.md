# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent decision, principle, rule, and preference is already folded into them. **Do not summarize them back.** Read, absorb, act.
3. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02 §3`, default NO, Danny's explicit written approval).
4. Continue from the live sprint state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Live sprint state only — nothing constitutional, architectural, or duplicated.*

**Last regenerated:** 2026-07-20 (**Conversation State Management shipped + governance-FROZEN; Faith certification close-out (round 2) shipped. Both AWAITING Danny prod validation. Next: Timestamp Precision Phase 2 + CoS Domain Certification (Fitness).**)

---

## ✅ Folded into permanent docs this session (do NOT re-derive — read the doc, don't restate it here)
- **Conversation State Management** — now a **foundational, architecturally FROZEN** capability. Lesson in `01 §6`; durable rules in `03 §3e` (one deterministic writer authority; the model never writes truth) + `03 §3f` (compact/deterministic/reference-oriented + the **Expansion Test**); full governing doc `docs/WLJ_CONVERSATION_STATE_ARCHITECTURE.md` (§4a writers · §4b artifact re-delivery + adapter separation + coverage · §5a Permitted Data · §5b Expansion Test). CI: `test_conversation_state_{writer,schema}_contract.py`. **Extend ONLY via the Expansion Test — it is a system eliminator, not another system.**

## 🎯 Live work — pick your track (Danny runs several in parallel; reconcile which you're driving before starting)
- **Timestamp Precision Phase 2/3** (`docs/WLJ_TIMESTAMP_PRECISION.md`; principle in `03 §7`). **Phase 2** = persist `observed_precision` per-domain, certification-gated (Health first — 8 remaining noon-fabricating ingest sites: glucose, blood pressure, body-temperature, body-comp, sleep, generic daily, blood-oxygen, HR-events). **Phase 3** = presentation adopts (Health Sync JSON emits precision; iOS renders DAY without a clock; web/CoS call `format_instant`). **Do NOT big-bang it.**
- **CoS Domain Certification** (RATIFIED 5-step, `03 §3d`; `docs/WLJ_COS_DOMAIN_CERTIFICATION_STANDARD.md`). Nutrition ✅ Journal ✅ prod-complete; **Faith close-out (round 2) shipped, AWAITING Danny prod validation.** **Next domain: Fitness**, then Medications · Goals · Habits · People · Legacy · Calendar · Tasks · Projects · Capture · Notes · Brain Training · Medical.
- **Conversation State migration inventory (audit only, no code yet)** — the biggest architecture *reduction* is retiring the two non-prod runtimes' duplicate conversation systems (`chatgpt_cos` conductor/conversation_memory ~440 lines; then legacy Beth), which Conversation State + `confirmation.py` now make redundant. **Gated on runtime consolidation** (all users → `model_interface`), a rollout decision — not a Conversation State feature. Durable records (`JournalConversation`, `*Session`, `ConversationMemory`) stay put.
- **Parallel tracks other sessions own (do not collide):** Timestamp Precision · Rich Confirmation (`resolve_typed_confirmation` on `confirmation.py`) · Structured Import Orchestration · Journal Experience · Meals Ingredient Intelligence · Configuration Governance.

## 🔮 Deferred / carried (open as its own step before implementing)
- **Timestamp Precision Phase 2/3** and the remaining Health precision rollout (above).
- **Artifact perception adapters (Conversation State is already ready; only adapters extend):** PDF page-rendering, DOCX embedded content, OCR for scanned documents — extend *perception* for `document`/`audio` **without touching Conversation State** (§4b.2). Documents/audio use the text surface today.
- **Faith refinements** (product polish, none blocking): structured relationship/goal/event pickers for Prayer; reminder-scheduling UI; a Collection model; longitudinal journal-theme analysis in the Mirror; grounded "because you…" reasons; a Current Context page-summary provider for Faith Today.
- **Journal genuinely-new-truth:** "goals discussed in my journal", "people mentioned most often in my journal" — require NEW deterministic truth, not exposure.
- **WLJ Certification Platform** remaining types · **UTC-vs-user-local calendar-day attribution** · **WLJ Operations** operator-gated Phase II → OPS-8a (`docs/WLJ_OPERATIONS_VISION.md`).
- **Long-term product idea ONLY — tabled, NOT active work:** Faith **Life Seasons / Life Chapters / narrative organization.** Do not open without Danny's explicit go.
- **Renpho direct / Terra — CLOSED** (dead ends; superseded by Measurement Session Capture). Do not reopen.

## ⏳ Waiting on Danny (operator — Claude has no prod access)
- **Validate in production:** **Conversation State** (upload an image/video → follow-ups stay on it; a pending "yes" resolves the right confirmation), **Faith domain certification** (the 10 close-out questions on real data), plus the still-open Faith First Light + Health Sync validations from prior sessions.
- **Deploy topology:** the CoS runs in **`wlj-worker`**; `/_health/` reports only the web commit — verify the worker is on the tested commit before trusting a production CoS result.

## 🔀 Concurrency — coordinate, do not collide (Danny runs MANY parallel sessions on the SAME tree)
Commit **only your own files by explicit path.** The changelog and shared files (`apps/core/truth/domain.py`, `apps/ai/multimodal.py`, `apps/ai/cos_services/*`, this bootloader) are heavily contended: re-check the changelog top **immediately before each commit**, defer your line if a foreign entry appeared, isolate your hunk from foreign uncommitted work, and verify the push is a fast-forward (never lose a foreign commit). A concurrent session may push the shared branch — including *your* just-made commit — so a "nothing to push" can be normal; re-fetch and confirm your SHA is on remote.
