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
- **Current Context** — every page declares what the user is looking at (detail→object; overview→deterministic summary), resolved server-side; the model answers from it before retrieving. Related truth may *enrich* it but never *replace* it.
- **Execution Truth / Execution Decision Authority** — one deterministic producer of execution truth. It owns the buckets **current action · completed today · overdue · due now · coming up · later**; every surface consumes it, none re-derives. Recurring execution is **occurrence-based**: "today's execution" (the occurrence due today) and "history" (what happened previously) are **separate deterministic truths** and are never blended.
- **Mission Link** — action→mission connection as deterministic relationship facts (WLJ computes it; the model reasons *from* it). Production-complete.
- **Multimodal** — perception is the model's; the deterministic spine is WLJ's. Pattern: **the model perceives → WLJ validates truth → WLJ executes the action → the model communicates the real results.** Production-complete (see maturity).
- **Model Interface + Executive Context Envelope** — the single seam and the structured per-turn context (AI Relationship + Current Context + deterministic understanding) handed to the model.
- **Conversation integrity** — the transcript stays a faithful record of what the user actually submitted; artifacts derived from an upload become deterministic truth with provenance, but the transcript still preserves the original submission.
- **Reflection** — sits *above* the four layers and only observes; learning is default-deny and never learns around a deterministic defect.
- **Truth Surfaces** — the CoS reasons from **several complementary deterministic truth surfaces**, not `DomainTruth` alone: **Current Context · Standing Context · Personal Truth · DomainTruth · Domain Entity Surfaces · Executive Briefings · Decision Authority.** Each supplies a truth type (summary/detailed/execution/contextual/historical); they are complementary views of one life, not rivals. **A missing `DomainTruth` provider does not make an answer impossible** — the fact may legitimately arrive via another surface (Goals answered from Standing Context; Fitness from a Domain Entity Surface). Validated by production certification, 2026-07-18. Full catalog: `docs/WLJ_TRUTH_SURFACES.md`.

Stack: Django 4.2.27 (note: CLAUDE.md says "5.x"; runtime is 4.2), PostgreSQL/Redis, Celery worker+beat, Gunicorn, Railway (Nixpacks), OpenAI. iOS SwiftUI wrapper. ~4,400 tests. Soft deletes, not hard deletes.

## 5. Current maturity (honest)

- **Phase:** WLJ has moved from **architecture discovery → product refinement.** Daily use of the Chief of Staff now drives the roadmap; architectural change is proposed only after investigation proves it necessary (see the engineering guide's investigation order).
- **Architecture:** considered **stable and constitutionally protected** (Milestone, 2026-07-11) — expected to evolve slowly through Constitutional Review, not frozen.
- **Layer 1 truth:** Medication is the **certified reference** domain; others follow `LAYER1_DOMAIN_FRAMEWORK.md` up the maturity ladder.
- **Current Context:** mechanism complete; **adoption early** (page-summary pattern live on ~1 page). Help coverage broad (135/135 ids).
- **Multimodal:** **first production capability complete** — image transport, artifact persistence, conversation integrity, provenance, validation, confirmation, idempotent duplicate prevention, deterministic execution, results-not-intentions.
- **WLJ Operations — the primary active initiative** (its own **Layer 1 truth domain**, `docs/WLJ_OPERATIONS_VISION.md`, architecture frozen 2026-07-11). It stays the primary initiative through the full Operations Vision (Phases II–IX) unless Danny redirects; Current Context and other WLJ work are secondary. **Phase I (Operations Visibility) is ✅ COMPLETE (2026-07-12)** — mission achieved: the critical infrastructure + execution surface is comprehensively observable (OPS-1…5,7; the residual is hardening/metadata/tech-debt, reclassified by category). **Phase II/II-B recovery is built + shipped dark** — three R1 handlers across two shapes (`OPS_RECOVERY_ENABLED=False` → zero behavior change); **Phase III (recovery-as-config) is evidence-gated** (needs real production experience). The **O1→O2 production pilot** is an operator-gated **Operational Rollout** (not engineering), and the next **engineering** milestone is **OPS-8a** (confirmation-queue + audit-lag, Operational Hardening). Governing principle: *"if it runs in production, it must be observable."*
- **Truth Validation Center — built (2026-07-19), complete enough to pause.** The deterministic **Owner-2 instrument** for CoS certification: sends discovery prompts through the production CoS (`CoSGateway`) and compares the answer against WLJ deterministic truth — no model grades a model. It classifies every failure by *layer* (Object Resolution · Provider · Routing · Tool Selection · Answer Grounding · Contamination), resolves each object by the app's own selection rules (with a visible resolution card), and runs in resolved or natural prompt modes. Governing doc: `docs/WLJ_TRUTH_VALIDATION_CENTER.md`; engineering loop: `03 §3c`. Its build **matured the Truth Layer and Object Resolution substantially and eliminated the entire by-name retrieval defect class** (every multi-entity provider's `describe_one` now covers all its entity types).
- **CoS status (honest, 2026-07-19):** Truth Layer + Object Resolution mature; **provider failures dramatically reduced.** Remaining engineering weight is expected in **conversational grounding, retrieval quality, capability completeness, and natural conversational behavior** — the gaps the next sprint is designed to find.
- **Product:** not finished. UX and daily usage drive the roadmap. See `docs/WLJ_KNOWN_LIMITATIONS.md`.

## 6. Major lessons learned

- **Don't assemble sentences from independent fragments** — it manufactured contradictions. One author (the model), one composed truth. This lesson *caused the pivot*.
- **Eliminate the class, don't detect the symptom.** We didn't "fix" *"6:15 AM tonight"* — we removed the condition that let one sentence draw from two time sources.
- **Occurrence-scoped truth.** "Completed today" must mean *the occurrence due today is done*, not *a timestamp landed today* — a recurring prior occurrence completed after midnight is history, not today (the "Check on Von's House" incident).
- **Prove the runtime path before editing.** A passing unit test is not proof; trace Browser→…→Composer→DB and find ALL producers (persisted ≠ live).
- **Request-path safety.** Never compute heavy analytics or call the LLM inline on a request; read snapshots or return "pending." Live fallbacks caused production timeouts.
- **Improve truth before adding intelligence.** Most "make the assistant smarter" asks are really "give the model better truth."
- **Certification drives the roadmap, not intuition** (proven 2026-07-18). Two-owner model — Deterministic (Owner-1) → Customer Truth (Owner-2) → Executive Judgment — with per-question structured evidence and first-failing-layer attribution. Rank work by *measured* customer impact; untested = **NOT YET MEASURED**, never "low priority." The loop and instrument are in `03_ENGINEERING_OPERATING_GUIDE §3c`.
- **A missing provider is not a missing answer.** *"A missing provider changes which deterministic truth surface supplied the answer; it does not necessarily determine whether the answer is possible."* Trace which surface served an answer before concluding a gap exists (`docs/WLJ_TRUTH_SURFACES.md`).
- **Validate at the altitude you're certifying.** *(The defining lesson of the Truth Validation Center build, 2026-07-19.)* The Truth Validation Center certifies **implementation** — it separates Truth Layer · Object Resolution · Provider · Routing · Tool Selection · Answer Grounding, which is *invaluable for engineering* (it turns "the CoS got it wrong" into "which layer failed"). But that is the **wrong altitude for operator certification of the Chief of Staff.** Field- and layer-level validation proves the parts work; it does **not** prove the *conversational experience* is one a paying customer would trust. **Operator certification must validate natural conversation** — "does my Chief of Staff behave like a knowledgeable Chief of Staff?" — in the user's own language, never database or developer terms. Keep both instruments, and use each at its altitude: the layer-level Center for engineering diagnosis, natural-conversation testing for operator certification. (This is not a failure of the Center — it is the right tool at the wrong level for that job.)

## 7. Where the authoritative detail lives

This package is the **onboarding experience**; the detail is the **supporting library**. Full map: `99_REFERENCE_INDEX.md`. Highest-value detail docs:

- Vision & contract: `docs/WLJ_PRODUCT_VISION.md`, `docs/WLJ_LLM_TRUTH_ACTION_CONTRACT.md`
- Laws & development model: `docs/WLJ_ARCHITECTURE_LAWS.md`, `docs/WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md`
- Pillars: `docs/WLJ_CURRENT_CONTEXT_CONTRACT.md`, `docs/WLJ_VISUAL_TRUTH_CONTRACT.md`, `docs/WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md`
- Domains: `docs/LAYER1_DOMAIN_FRAMEWORK.md`, `docs/WLJ_LEGACY_DOMAIN_ARCHITECTURE.md`
- Certification: `docs/WLJ_TRUTH_VALIDATION_CENTER.md` (the deterministic CoS-vs-WLJ validator + failure-layer classification), `docs/WLJ_TRUTH_SURFACES.md`, `docs/WLJ_CERTIFICATION_BACKLOG.md`
- Security & authorization (RATIFIED 2026-07-18, architecture only): `docs/WLJ_SECURITY_AUTHORIZATION_FRAMEWORK.md` — Identity · **Space** · Capability · Ownership · Delegation · Trust; one deterministic PDP; Space is the canonical container; the Platform is not a Space; the CoS is a derived principal. Not yet implemented.
- Milestone record: `docs/WLJ_MILESTONE_COS_ARCHITECTURE.md` and its coverage docs.
