# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent decision, principle, rule, and preference is already folded into them. **Do not summarize them back.** Read, absorb, act.
3. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02 §3`, default NO, Danny's explicit written approval).
4. Continue from the live sprint state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Live sprint state only — nothing constitutional, architectural, or duplicated.*

**Last regenerated:** 2026-07-20 (**Journal unified-draft lifecycle shipped (M-D1…M-D4) — the reference implementation of the CoS relationship. New primary direction ratified: One Chief of Staff, many workspaces. All AWAITING Danny prod validation.**)

---

## 🧭 PRIMARY FOCUS — evolve the CoS from a page capability into a PLATFORM capability
**The governing mental model is folded into `01 §6` ("One Chief of Staff, many workspaces") — read it there, don't restate it.** In one line: WLJ is **one Chief of Staff across every domain**, not per-page AI; the relationship never changes, only the **workspace** changes; **Current Context** is now a *defining* product capability; **navigation is a CoS decision**. **Journal is the first fully-realized workspace and the reference implementation.**

**START WITH INVESTIGATION — no code until these are answered with runtime evidence (trace, don't speculate; reuse-first):**
1. Which existing CoS components are **already reusable across domains**? (Model Interface seam, Executive Context Envelope, Current Context, Conversation State, `confirmation.py`, truth surfaces, action/audit path.)
2. Which Journal pieces are **truly Journal-specific** (`JournalConversation`/`written_body`, `journal_conversation.py`, the Playbook/Memory prompts, generate/review/Save)?
3. Which pieces should become **generic CoS capabilities** (the durable draft-session shape, autosave-to-draft, Finish&Review→review→Save, workspace-scoped conversation)?
4. How does **Current Context currently flow** into the CoS today (server-side `<meta wlj-context>` → baseline → Executive Context Envelope)?
5. How should **workspace navigation** integrate with the existing Current Context architecture (CoS-decided navigate vs answer-in-place)?
6. Which services **already support** this (Model Interface, `CoSGateway`, Current Context providers, `TeachingDestination`/Action router for navigation targets)?
7. What can be **generalized without breaking any existing Journal behavior**?

**Guardrails (from Danny, verbatim intent):** do NOT redesign the Journal or the CoS architecture without evidence; do NOT create multiple assistants, duplicate conversation systems, or domain-specific AI engines; improve through **composition, not duplication**. Preserve everything already built — recognize it as CoS capabilities.

## ✅ Shipped this session — Journal unified-draft lifecycle (the reference implementation; AWAITING prod validation)
- **One draft, all three modes** (`9efa68c2`,`c359f662`,`6237946a`): `JournalConversation.written_body` (mig `0017`) is the Just Write typed channel beside the conversation `transcript`; **all three modes share ONE daily draft; a `JournalEntry` exists only at Save.** Autosave `POST journal:draft_autosave` (sanitized, request-path-safe, never fabricates an empty draft); draft-aware editor prefills/autosaves/completes-on-Save (classic behavior preserved when flag off / edits / ai_camera / prompts); `generate_entry` **composes both channels** (a pure Just Write draft passes through un-rewritten — fidelity); a draft that holds a conversation routes to **Finish & Review** so the conversation is never dropped; `respond()` folds typed notes into the prompt (§13 "reads what's there"). Runtime-validated (type→reload→resumed; mobile). Flag `features.journal.write_together` (owner-only). Detail: changelog + `journal_experience_redesign` memory.
- **Vocabulary FIXED (ratified this session):** **Journal Draft → Resume → Finish & Review → Review → Save Journal → `JournalEntry` → Truth Discovery → Publish to Legacy.** The Journal is **Saved**; **"Publish" is Legacy-only.** Never "Today's Journal" / "Finish Today" / "Save Entry".

## 🎯 Parallel tracks (other sessions may own — reconcile which you're driving; the strategic direction above is primary)
- **CoS Domain Certification** (RATIFIED 5-step, `03 §3d`). Nutrition ✅ Journal ✅ prod-complete; Faith close-out (round 2) shipped, AWAITING prod validation. **Next domain: Fitness**, then Medications · Goals · Habits · People · Legacy · Calendar · Tasks · Projects · Capture · Notes · Brain Training · Medical.
- **Timestamp Precision Phase 2/3** (`docs/WLJ_TIMESTAMP_PRECISION.md`; principle `03 §7`). Phase 2 = persist `observed_precision` per-domain, certification-gated (Health first — 8 noon-fabricating ingest sites). Phase 3 = presentation adopts. **Do NOT big-bang it.**
- **Conversation State migration inventory (audit only)** — retire the two non-prod runtimes' duplicate conversation systems; gated on runtime consolidation (all users → `model_interface`). Durable records stay put.
- **Other parallel owners (do not collide):** Rich Confirmation · Structured Import Orchestration · Meals Ingredient Intelligence · Configuration Governance.

## 🔮 Deferred / carried (open as its own step before implementing)
- **Journal polish that needs Danny's LIVE model + real mic to advance & validate** (already substantially built — do NOT blindly re-tune what you can't run/hear; that risks breaking working behavior): deeper **contextual reasoning** (relationship reasoning over today's truth), deep **voice polish** (speaking/thinking transitions, mic recovery, reconnect, endpointing feel), **conversation quality** ("feels like my Chief of Staff, not AI"). Voice Pause naming vs the durable draft is a minor polish (the transcript already persists every turn → Resume Talk It Through is durable).
- **Journal recent-context truth:** lightweight, request-path-safe "today" facts (meals/exercise/glucose/meds) to deepen questions — needs a cheap cached per-domain snapshot, not heavy builders.
- **Journal genuinely-new-truth:** "goals discussed in my journal", "people mentioned most in my journal" — require NEW deterministic truth, not exposure.
- **Timestamp Precision Phase 2/3** and remaining Health precision rollout · **Artifact perception adapters** (PDF/DOCX/OCR — extend *perception* only, not Conversation State) · **Faith refinements** (pickers, reminder UI, Collection model, Mirror theme analysis) · **WLJ Certification Platform** remaining types · **UTC-vs-user-local calendar-day attribution** · **WLJ Operations** operator-gated Phase II → OPS-8a.
- **Long-term product idea ONLY — tabled, NOT active:** Faith **Life Seasons / Life Chapters**. Do not open without Danny's explicit go.
- **CLOSED — do not reopen:** Renpho direct / Terra.

## ⏳ Waiting on Danny (operator — Claude has no prod access)
- **Validate in production:** the **Journal unified-draft lifecycle** (journal by talking, then typing, then talking across a day; confirm the draft follows you and nothing is lost; Finish & Review → Save Journal reads as one story from both channels), **Conversation State**, **Faith domain certification**, plus still-open Faith First Light + Health Sync validations.
- **Deploy topology:** the CoS runs in **`wlj-worker`**; `/_health/` reports only the web commit — verify the worker is on the tested commit before trusting a production CoS result.

## 🔀 Concurrency — coordinate, do not collide (Danny runs MANY parallel sessions on the SAME tree)
Commit **only your own files by explicit pathspec** (`git commit -m … -- <paths>`). The changelog and shared files (`apps/core/truth/domain.py`, `apps/ai/multimodal.py`, `apps/ai/cos_services/*`, this bootloader) are heavily contended: re-check the changelog top **immediately before each commit**, defer your line if a foreign entry appeared, isolate your hunk from foreign uncommitted work, verify the push is a fast-forward (never lose a foreign commit). A concurrent session may push the shared branch — including *your* commit — so "nothing to push" can be normal; re-fetch and confirm your SHA is on remote.
