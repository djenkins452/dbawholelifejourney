# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent decision, principle, rule, and preference is already folded into them. **Do not summarize them back.** Read, absorb, act.
3. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02 §3`, default NO, Danny's explicit written approval).
4. Continue from the live sprint state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Live sprint state only — nothing constitutional, architectural, or duplicated.*

**Last regenerated:** 2026-07-21 (**Travel Intelligence designed as the first platform-consumer domain — governing pattern folded into `01 §6`; design doc `docs/WLJ_TRAVEL_INTELLIGENCE_ARCHITECTURE.md` DRAFT. Primary focus unchanged: evolve the CoS into a platform capability, Journal = reference implementation.**)

---

## 🧭 PRIMARY FOCUS — evolve the CoS from a page capability into a PLATFORM capability
**The governing mental model + the new domain-development pattern are in `01 §6` ("One Chief of Staff, many workspaces" and "a new domain is a platform *consumer*, never a parallel architecture") — read them there, don't restate.** In one line: **one Chief of Staff across every domain**; the relationship never changes, only the **workspace** changes; **Current Context** is a *defining* product capability; **navigation is a CoS decision**. **Journal is the first fully-realized workspace and the reference implementation.**

**START WITH INVESTIGATION — no code until these are answered with runtime evidence (trace, don't speculate; reuse-first):**
1. Which existing CoS components are **already reusable across domains**? (Model Interface seam, Executive Context Envelope, Current Context, Conversation State, `confirmation.py`, truth surfaces, action/audit path.)
2. Which Journal pieces are **truly Journal-specific** (`JournalConversation`/`written_body`, `journal_conversation.py`, the Playbook/Memory prompts, generate/review/Save)?
3. Which pieces should become **generic CoS capabilities** (the durable draft-session shape, autosave-to-draft, Finish&Review→review→Save, workspace-scoped conversation)?
4. How does **Current Context currently flow** into the CoS today (server-side `<meta wlj-context>` → baseline → Executive Context Envelope)?
5. How should **workspace navigation** integrate with the existing Current Context architecture (CoS-decided navigate vs answer-in-place)?
6. Which services **already support** this (Model Interface, `CoSGateway`, Current Context providers, `TeachingDestination`/Action router for navigation targets)?
7. What can be **generalized without breaking any existing Journal behavior**?

**As you investigate, name Travel's future consumption (per this session's direction):** for each reusable capability you confirm (Current Context · conversation continuity · workspace navigation · discovery · draft/workflow · confirmation · multimodal intake · truth extraction · shared action execution), note how **Travel Intelligence** will consume it — so the platform is shaped with a *second* real consumer in mind, not just Journal. Design only; do not build Travel.

**Guardrails (from Danny, verbatim intent):** do NOT redesign the Journal or the CoS architecture without evidence; do NOT create multiple assistants, duplicate conversation systems, or domain-specific AI engines; improve through **composition, not duplication**. Preserve everything already built — recognize it as CoS capabilities.

## 🎯 Parallel tracks (other sessions may own — reconcile which you're driving; the primary focus above wins)
- **CoS Domain Certification** (RATIFIED 5-step, `03 §3d`). Nutrition ✅ Journal ✅ prod-complete; Faith close-out (round 2) shipped, AWAITING prod validation. **Next domain: Fitness**, then Medications · Goals · Habits · People · Legacy · Calendar · Tasks · Projects · Capture · Notes · Brain Training · Medical.
- **Timestamp Precision Phase 2/3** (`docs/WLJ_TIMESTAMP_PRECISION.md`; principle `03 §7`). Phase 2 = persist `observed_precision` per-domain, certification-gated (Health first — 8 noon-fabricating ingest sites). Phase 3 = presentation adopts. **Do NOT big-bang it.**
- **Conversation State migration inventory (audit only)** — retire the two non-prod runtimes' duplicate conversation systems; gated on runtime consolidation (all users → `model_interface`). Durable records stay put.
- **Other parallel owners (do not collide):** Rich Confirmation · Structured Import Orchestration · Meals Ingredient Intelligence · Configuration Governance.

## 🔮 Deferred / carried (open as its own step before implementing)
- **Travel Intelligence — DESIGNED this session, NOT the next milestone.** Full design in `docs/WLJ_TRAVEL_INTELLIGENCE_ARCHITECTURE.md` (v0.1 DRAFT); governing pattern in `01 §6`. It is a **platform-consumer showcase**, built only *after* the reusable platform capabilities above exist. **One open decision blocks ratification (see Waiting on Danny): classify Travel `BEHAVIORAL` (recommended) vs the reserved `CONTEXT` (`descriptors.py:26`).** Do NOT begin Travel code; do NOT build a Travel AI/conversation/reasoning engine. Recommended MVP when it's time: truth spine + conversational planning (Phases 0–2); GPS/live mode is Phase 3 (greenfield — zero device location exists today). Carried sub-concepts: **Workspace ≠ Session**; **location truth = shared platform capability** (Travel = first consumer, not owner).
- **Journal polish that needs Danny's LIVE model + real mic to advance & validate** (already substantially built — do NOT blindly re-tune what you can't run/hear): deeper **contextual reasoning** (relationship reasoning over today's truth), deep **voice polish** (speaking/thinking transitions, mic recovery, reconnect, endpointing feel), **conversation quality** ("feels like my Chief of Staff, not AI"). Voice Pause naming vs the durable draft is minor polish (the transcript already persists every turn → Resume Talk It Through is durable).
- **Journal recent-context truth:** lightweight, request-path-safe "today" facts (meals/exercise/glucose/meds) to deepen questions — needs a cheap cached per-domain snapshot, not heavy builders.
- **Journal genuinely-new-truth:** "goals discussed in my journal", "people mentioned most in my journal" — require NEW deterministic truth, not exposure.
- **Timestamp Precision Phase 2/3** and remaining Health precision rollout · **Artifact perception adapters** (PDF/DOCX/OCR — extend *perception* only, not Conversation State) · **Faith refinements** (pickers, reminder UI, Collection model, Mirror theme analysis) · **WLJ Certification Platform** remaining types · **UTC-vs-user-local calendar-day attribution** · **WLJ Operations** operator-gated Phase II → OPS-8a.
- **Long-term product idea ONLY — tabled, NOT active:** Faith **Life Seasons / Life Chapters**. Do not open without Danny's explicit go.
- **CLOSED — do not reopen:** Renpho direct / Terra.

## ⏳ Waiting on Danny (operator — Claude has no prod access)
- **RATIFY Travel classification (one decision, unblocks the design):** classify Travel Intelligence `BEHAVIORAL` (recommended — a first-class life domain the CoS serves) vs the reserved `CONTEXT` placeholder. In-Constitution; product call, not a Constitutional Review.
- **Validate in production:** the **Journal unified-draft lifecycle** (M-D1…M-D4, shipped 2026-07-20, flag `features.journal.write_together`, owner-only — journal by talking then typing then talking across a day; confirm the draft follows you and nothing is lost; Finish & Review → Save Journal reads as one story from both channels), **Conversation State**, **Faith domain certification**, plus still-open Faith First Light + Health Sync validations.
- **Deploy topology:** the CoS runs in **`wlj-worker`**; `/_health/` reports only the web commit — verify the worker is on the tested commit before trusting a production CoS result.

## 🔀 Concurrency — coordinate, do not collide (Danny runs MANY parallel sessions on the SAME tree)
Commit **only your own files by explicit pathspec** (`git commit -m … -- <paths>`). The changelog and shared files (`apps/core/truth/domain.py`, `apps/ai/multimodal.py`, `apps/ai/cos_services/*`, this bootloader) are heavily contended: re-check the changelog top **immediately before each commit**, defer your line if a foreign entry appeared, isolate your hunk from foreign uncommitted work, verify the push is a fast-forward (never lose a foreign commit). A concurrent session may push the shared branch — including *your* commit — so "nothing to push" can be normal; re-fetch and confirm your SHA is on remote.
