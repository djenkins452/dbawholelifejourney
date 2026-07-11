# 00 · READ FIRST — WLJ Chief of Staff Architecture

**`00_NEXT_CHAT_STARTUP.md` is read before this file (it's the bootloader with current priorities). Read this next for the architecture, then `02_WLJ_CONSTITUTION.md`, `03_ENGINEERING_OPERATING_GUIDE.md`, `04_DANNY_WORKING_PREFERENCES.md`, `98_SESSION_TRANSITION_PROTOCOL.md`, and `99_REFERENCE_INDEX.md`. All seven files are in this one folder.**
**Responsibility of this document:** what WLJ is, why it exists, how the architecture got here, where it stands today, and where to find the authoritative detail. It does **not** restate the Constitution, the engineering rules, or Danny's preferences — those are their own documents.

---

## 1. What WLJ is

**Whole Life Journey (WLJ)** is a Django personal operating system — a **Personal Truth Platform** — with an **AI Chief of Staff** as its primary surface. It holds the deterministic truth of a person's whole life across domains: health, medical, meals, faith, journal, capture/notes, relationships, purpose/goals, finance, life/tasks/calendar, brain training, and more.

The user chooses a **default relationship** with their AI (Chief of Staff, Best Friend, Coach…) and a **display name** for it (Clara, Beth, Jarvis, Friday…). Those are preferences. The system is always the **WLJ Chief of Staff**.

## 2. Why it exists (product vision)

`docs/WLJ_PRODUCT_VISION.md` is the highest-level "why." In one line:

> **WLJ owns the deterministic truth of a person's life; the conversational model reasons over it.** "The model reasons. WLJ knows."

The point of the product is **trust**. The only success metric is: *if this were the only conversation a paying customer ever had with their Chief of Staff, would they immediately want to use it again tomorrow?* Elegant architecture is never the product — the customer experiences trust, not layers.

A core engineering consequence: **simplicity**. Before building anything, ask "can the conversational model already do this well?" If yes, don't build it — improve the *truth* available instead. As frontier models improve, **WLJ gets simpler, not more complex.**

## 3. Why the OpenAI pivot happened (the defining decision)

WLJ originally tried to build **reasoning inside WLJ** — a "Conductor" with conversation lanes, a classifier, composition passes, and an in-process assistant (historically nicknamed "Beth"). That approach produced a specific, repeating failure: WLJ assembling a sentence from independent fragments contradicted itself (the canonical example: *"6:15 AM tonight,"* stitched from two independent time sources). The contradiction was **structural**, not a bug to patch.

On **2026-07-09** the architecture pivoted: **WLJ stopped reasoning.** A provider-agnostic conversational model (**currently OpenAI**, behind one Model Interface seam) now **drives the turn and owns all reasoning**; WLJ owns deterministic truth, calculations, validation, actions, and audit, and hands the model **composed briefings** (facts with a freshness/confidence/source envelope), never raw signals and never a reasoning engine to imitate.

This is why the governing rule is: **do NOT build a reasoning engine inside WLJ.** A reasoning miss is fixed with better truth delivery, better context, a truth/action tool, or a corrected AI Relationship — never a bespoke WLJ "mind." The retired reasoning-engine docs are preserved and bannered HISTORICAL (see the documentation inventory).

## 4. Current architecture (the shape today)

Four layers, diagnosed **top-down**; fix the first that failed:

1. **Truth (WLJ)** — deterministic facts, calculations, history, preferences. One authority per domain. Most fixes live here.
2. **Reasoning (the model)** — OpenAI drives the turn, reasons over the briefings and tools WLJ provides.
3. **Action (WLJ)** — the safe deterministic path: validate → confirm → execute → audit + provenance.
4. **Experience** — the pages, Current Context, and conversation the customer actually feels.

Load-bearing pillars:
- **Current Context** — every page declares what the user is looking at (detail→object; overview→deterministic summary), resolved server-side; the model answers from it before retrieving.
- **Execution Decision Authority** — one deterministic producer of "what to do now"; every surface consumes it.
- **Mission Link** — action→mission connection as deterministic facts.
- **Model Interface + Executive Context Envelope** — the single seam and the structured per-turn context (AI Relationship + Current Context + deterministic understanding) handed to the model.
- **Reflection** — sits *above* the four layers and only observes; learning is default-deny and never learns around a deterministic defect.

Stack: Django 4.2.27 (note: CLAUDE.md says "5.x"; runtime is 4.2), PostgreSQL/Redis, Celery worker+beat, Gunicorn, Railway (Nixpacks), OpenAI. iOS SwiftUI wrapper. ~4,400 tests. Soft deletes, not hard deletes.

## 5. Current maturity (honest)

- **Architecture:** considered **stable and constitutionally protected** (Milestone, 2026-07-11) — expected to evolve slowly through Constitutional Review, not frozen.
- **Layer 1 truth:** Medication is the **certified reference** domain; others follow `LAYER1_DOMAIN_FRAMEWORK.md` up the maturity ladder.
- **Current Context:** mechanism complete; **adoption early** (page-summary pattern live on ~1 page). Help coverage broad (135/135 ids).
- **Observability (Ops Wall):** strong for engines/signals; **gaps** in non-engine Beat tasks, storage/volumes, OpenAI upstream, chat-queue backlog (OPS-1…10 backlog).
- **Product:** not finished. UX and daily usage drive the roadmap. See `docs/WLJ_KNOWN_LIMITATIONS.md`.

## 6. Major lessons learned

- **Don't assemble sentences from independent fragments** — it manufactured contradictions. One author (the model), one composed truth. This lesson *caused the pivot*.
- **Eliminate the class, don't detect the symptom.** We didn't "fix" *"6:15 AM tonight"* — we removed the condition that let one sentence draw from two time sources.
- **Occurrence-scoped truth.** "Completed today" must mean *the occurrence due today is done*, not *a timestamp landed today* — a recurring prior occurrence completed after midnight is history, not today (the "Check on Von's House" incident).
- **Prove the runtime path before editing.** A passing unit test is not proof; trace Browser→…→Composer→DB and find ALL producers (persisted ≠ live).
- **Request-path safety.** Never compute heavy analytics or call the LLM inline on a request; read snapshots or return "pending." Live fallbacks caused production timeouts.
- **Improve truth before adding intelligence.** Most "make the assistant smarter" asks are really "give the model better truth."

## 7. Where the authoritative detail lives

This package is the **onboarding experience**; the detail is the **supporting library**. Full map: `99_REFERENCE_INDEX.md`. Highest-value detail docs:

- Vision & contract: `docs/WLJ_PRODUCT_VISION.md`, `docs/WLJ_LLM_TRUTH_ACTION_CONTRACT.md`
- Laws & development model: `docs/WLJ_ARCHITECTURE_LAWS.md`, `docs/WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md`
- Pillars: `docs/WLJ_CURRENT_CONTEXT_CONTRACT.md`, `docs/WLJ_VISUAL_TRUTH_CONTRACT.md`, `docs/WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md`
- Domains: `docs/LAYER1_DOMAIN_FRAMEWORK.md`, `docs/WLJ_LEGACY_DOMAIN_ARCHITECTURE.md`
- Milestone record: `docs/WLJ_MILESTONE_COS_ARCHITECTURE.md` and its coverage docs.
