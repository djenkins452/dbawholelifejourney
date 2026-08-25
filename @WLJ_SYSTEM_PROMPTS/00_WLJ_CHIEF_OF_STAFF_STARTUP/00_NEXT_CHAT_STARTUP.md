# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent decision, principle, rule, and preference is already folded into them. **Do not summarize them back.** Read, absorb, act.
3. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02 §3`, default NO, Danny's explicit written approval).
4. Continue from the live sprint state below.

---

> ## 🏁 CoS DEVELOPMENT ARC CLOSED (2026-08-18) — WORK IS NOW PRODUCTION-FRICTION-DRIVEN
> **The Chief-of-Staff architecture / certification / navigation arc is COMPLETE and CLOSED.** The
> original product model is realized end-to-end and prod-validated: **WLJ knows → OpenAI reasons → the
> CoS proactively guides, follows up, acts, and navigates.** Shipped across this arc: whole-life
> Executive Truth + two-phase Synthesis · the full CoS Domain Certification program · Proactive Product
> Phase 2 (Daily Executive Brief · Durable Follow-Through · Missing-Data Intervention · Action
> Completeness) · Reveal Target + single-authority navigation + Object-Level Reveal · OpenAI cost
> governance.
>
> **NEW OPERATING POSTURE — do NOT resume capability/coverage expansion on spec.** From here, new CoS
> development is driven **primarily by REAL production friction Danny actually hits** — something the CoS
> **failed to notice, remember, follow up on, execute, navigate to, or reason about correctly** — or a
> genuine new user requirement. **Do NOT** start new features, additional Current Context / navigation
> coverage, or architectural cleanup **without a real product failure or new requirement.** When a real
> failure appears: reproduce it (runtime-trace, `docs/WLJ_RUNTIME_TRACE_DEBUGGING.md`), classify the
> failing layer (Truth → Reasoning → Action → Experience), fix the first that failed, and prefer
> eliminating the *class* over patching the symptom. Product-first: judge every change by *"would a
> paying customer trust this conversation?"*, not by architectural completeness.
>
> **Intentionally DEFERRED (remain deferred — NOT active work; pick up only on real need):** `health.intake`
> + `calendar.overview` + `life.tasks` page-summary providers (need shared request-path-safe builders);
> `get_absolute_url` on the remaining health objects + object-level reveal for update/complete actions +
> entity-resolved reveal ("open the workout from Tuesday"); read-after-write SAE snapshot staleness
> (Layer-1 read-freshness, pre-existing, affects all writes, not proven to block anything); legacy
> `PersonalAssistant`/ChatGPT-CoS runtime convergence onto `model_interface`; `health.body_temperature.current_context`;
> the durable-draft (`WorkspaceDraftSession`) generalization. See the changelog + the topic docs for each.
>
> **COST DISCIPLINE STILL BINDS:** Tier-1 deterministic testing by default; at most ONE real-model smoke
> per deploy; never repeated real-model runs on spec (CLAUDE.md + `03 §10a`). Cleanup complete: Object-Level
> Reveal cert artifacts removed (ai migration `0041`, soft-delete by proven identity).

---

> ## 💸 COST GOVERNANCE (2026-08-16) — READ BEFORE ANY MODEL TESTING
> **Incident:** Danny's OpenAI account auto-charged ~$16–17 repeatedly. Root cause = **Claude's own
> certification / `cos-run` real-model testing** (Aug 12–16) × the **Executive Synthesis Phase-2
> multiplier** (a broad turn = 3–9 billable requests). Forensic record: **`docs/WLJ_OPENAI_COST_AUDIT.md`**.
> **GOVERNANCE MILESTONE SHIPPED (§16 of that doc):** every billable provider request now writes ONE
> `owner_finance.LLMUsageEvent` via the single seam `apps/ai/llm_accounting.py :: record_llm_event`
> (tokens+cost+`source`+`traffic_class`); certification traffic is tagged `certification`, proactive as
> `proactive`; **generate-before-suppress waste eliminated** (midday/evening now gate + lock before the
> model call). See spend at `/owner/finance/` or `GET /admin-console/api/claude/cost-summary/?days=7`.
> **Testing discipline is now MANDATORY (CLAUDE.md + `03 §10a`): Tier 1 deterministic by default; ONE
> real-model smoke per deploy; never default to repeated real-model runs — answer the 4 questions first.**
> Model (`gpt-4o`), Executive Synthesis, schedules, retries UNCHANGED (cost is now visible, not optimized).
> All subsequent CoS work (the now-closed arc — see the ARC CLOSED banner up top) is prod-shipped; its
> proactive traffic is ledgered `traffic_class=proactive` and certification/`cos-run` as `certification`.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Live sprint state only — nothing constitutional, architectural, or duplicated.*

**Last regenerated:** 2026-08-18 — **CoS development / certification / navigation arc CLOSED.** The original model is realized (WLJ knows → OpenAI reasons → the CoS proactively guides, follows up, acts, navigates) and prod-validated; posture is now **production-friction-driven** (see the ARC CLOSED banner up top). Durable knowledge folded into `01 §5` (CoS arc-complete maturity), `03 §10a`/`§11` (testing + deploy discipline), `99 §B` (cost / proactive / cert-ledger docs). Foreign parallel tracks (Meal Intelligence · Journal Workspace · Travel · WLJ Operations) and Waiting-on-Danny are PRESERVED below.

---

## 🧭 PRIMARY FOCUS — 🏁 CoS DEVELOPMENT ARC CLOSED (2026-08-18); posture = production-friction-driven (see top banner)

> **🏁 THE CoS ARC IS COMPLETE AND CLOSED.** Certification program (139/140), whole-life Executive Truth + two-phase Synthesis, Proactive Product Phase 2 (Daily Executive Brief · Durable Follow-Through · Missing-Data · Action Completeness), Reveal Target + single-authority navigation + Object-Level Reveal, and OpenAI cost governance are ALL shipped + prod-validated. The recommended milestones from the earlier product investigation were all implemented. **Do NOT reopen CoS architecture, continue generic certification, or expand capability/coverage on spec.** Ledgers/records: `docs/WLJ_COS_CERTIFICATION_LEDGER.md`, `docs/WLJ_COS_PROACTIVE_PRODUCT_INVESTIGATION.md`, `docs/WLJ_COS_PLATFORM_EVOLUTION_INVESTIGATION.md`, `docs/WLJ_OPENAI_COST_AUDIT.md`.
>
> **➡️ NEXT WORK COMES FROM REAL USE, NOT A ROADMAP.** New CoS development is now driven **primarily by production friction Danny actually experiences** — something the CoS failed to notice, remember, follow up on, execute, navigate to, or reason about correctly — or a genuine new requirement. See the **CoS DEVELOPMENT ARC CLOSED** banner at the top for the operating posture and the list of items that remain **intentionally deferred** (pick up only on real need). No milestone is queued.
> ### ✅ CLOSED 2026-08-25 — Mounjaro / Medication Grounding production-friction arc
> One real question (*"I forgot my Mounjaro this morning — can I take it tonight?"*) exposed **six** stacked
> defects, each visible only once the previous was removed: a topic-keyed medical deflection · a grounding rule
> sitting too late in the prompt to affect tool selection · under-declared truth surfaces · adherence bookkeeping
> serialized as if it were dosing guidance · **no authoritative product labelling in WLJ at all** · and decisive
> evidence destroyed on the Phase-1→Phase-2 synthesis handoff. All fixed and **production verified end-to-end**:
> the CoS now retrieves personal regimen truth AND authoritative labelling, both survive synthesis, and the answer
> materially uses both. **Shipped:** `medication_reference` — WLJ's first **impersonal** truth domain (DailyMed
> labelling, RxNorm identity, brand-only, **fails closed**, reuses the existing `get_entity`; no new tool, no
> routing). **Durable lessons:** `03 §10b` (prompt POSITION is semantics) · `§10c` (evidence capture ≠ evidence
> delivery) · `§10d` (operational metadata must never read as domain guidance) · `01 §4` (personal vs reference
> truth). **No Constitutional Review occurred; the Amendment Log is untouched.** Full record + the *why each fix
> exposed the next* narrative: `docs/WLJ_MEDICATION_INSTRUCTION_TRUTH_INVESTIGATION.md §C`.
> **DO NOT REOPEN OR EXTEND THIS ARC** — a new product problem starts a new production-friction investigation.
> **Deferred, not lost:** medication-reference **M2** (generic/NDC identity) until production evidence requires it;
> Phase-2 evidence size is an **observability consideration only** — no speculative truncation (an unmeasured cap
> already destroyed the decisive fact once in this arc).

**⚠️ Pre-existing (NOT this milestone):** 7 `apps.dashboard_v3` test failures from the concurrent Journal-Workspace/Dashboard redesign (`eb7392ed`) — a spawned task tracks them; confirm they're fixed independently.

## 🎯 Parallel tracks (other sessions may own — reconcile which you're driving; the primary focus above wins)
- **CoS Domain Certification — ✅ PROGRAM COMPLETE (139/140 actionable; part of the closed CoS arc).** All 13 catalog domains mechanically certified + the actionable set natural-certified on Danny's real data; ratchet `RemainingDomainRatchetTests` locks them. Ledger `docs/WLJ_COS_CERTIFICATION_LEDGER.md`. Only deferred gap = `health.body_temperature.current_context`. **Do NOT reopen to keep a score going.**
- **Timestamp Precision Phase 2/3** (`docs/WLJ_TIMESTAMP_PRECISION.md`; principle `03 §7`). Phase 2 = persist `observed_precision` per-domain, certification-gated (Health first — 8 noon-fabricating ingest sites). Phase 3 = presentation adopts. **Do NOT big-bang it.**
- **Conversation State migration inventory (audit only)** — retire the two non-prod runtimes' duplicate conversation systems; gated on runtime consolidation (all users → `model_interface`). Durable records stay put.
- **WLJ Operations — Configuration Governance & Recovery.** Foundation COMPLETE this session: Configuration Governance **OPS-13** (report-only drift detection, deployed prod-verified `43e3c128`; architecture RATIFIED `4639a4f2`), the 2026-07-23 truth-path **investigation** (`e2980b40`→`b858e060`), and **Operations Recovery Stabilization** (`f871a511` — hysteresis + `RECOVERING` state + alignment-badge relabel; durable lessons folded to `03 §4a`/`§7a`). **NEXT = OPS-14 Configuration Visibility** — a pure read-only Ops Wall card rendering the existing `config_integrity` section's own status (decoupled from global status, no enforcement); **approval-gated, NOT started.** Then OPS-15 (config→operations state + CoS banner, medium blast) · OPS-16 (enforcement, high — report-only first) · OPS-17 (continuous). Milestone map: `docs/WLJ_CONFIGURATION_GOVERNANCE.md §10`. The latent two-authority *risk* (COAS vs Integrity) is documented, was **NOT** this incident's cause, and consolidation is deferred until evidence warrants — do NOT preemptively consolidate.
- **Other parallel owners (do not collide):** Rich Confirmation · Structured Import Orchestration · Configuration Governance. **(Meal Intelligence is now foundationally complete — see its own section below.)**

## 🍽️ Meal Intelligence — foundationally COMPLETE; continue by REFINEMENT, never redesign
**Status:** a mature standalone deterministic truth domain (Foundations 1–2 + Ingredient Intelligence shipped 2026-07-20). Durable knowledge + the strategic direction are now permanent in `01 §5`/`§6` — **read them there, don't restate.** In one line: **Meals owns food truth; the CoS will *consume* it (never own it); future meal/grocery/pantry/recipe/nutrition conversations flow through the CoS once the CoS platform stabilizes — do NOT redesign Meals around today's CoS.** Governing docs: `docs/WLJ_MEAL_INTELLIGENCE_ARCHITECTURE.md`, `WLJ_INGREDIENT_INTELLIGENCE.md`, `WLJ_MEAL_INTELLIGENCE_TRUTH_CERTIFICATION.md`, `WLJ_MEAL_INTELLIGENCE_ROADMAP.md`.

- **AWAITING Danny's real-world validation (all shipped this session):** Foundation 2 lifecycle (prep → deduction → leftovers → consumption → nutrition → waste), Pantry **Container Truth** + **Remaining Truth**, **Pantry Smart Search**, **Manual Pantry Entry**, **Ingredient Intelligence** (+ curated-aliases-no-runtime-learning refinement), the single **Pantry Availability authority**, and the three product-defect fixes (availability drift · blank substitution names · meal score of 0). *Implemented · deployed · certification passing — but NOT validated until Danny confirms in production.*
- **Remaining implementation (carry forward — product refinement + remaining capabilities, NOT redesign):** continued real-world product validation · UX improvements found in testing · Ingredient Intelligence refinement where needed · Pantry usability + matching improvements · Manual Pantry Entry refinements · Container Truth polish · **meal planning intelligence · grocery list generation · shopping workflows** · pantry optimization · **price intelligence · store intelligence** · future grocery-ordering integrations · analytics/reporting enhancements · any deferred product refinements from this session. (Roadmap M4+.)
- **Sequencing:** these continue after the CoS platform work reaches stability; they remain Meal Intelligence responsibilities and integrate as a platform *consumer* (`01 §6`).

## 🔮 Deferred / carried (open as its own step before implementing)
- **Journal Workspace (Focus Compose) — SHIPPED 2026-07-21 (`f9b93c81`), AWAITING Danny's prod validation; refinements carried.** The Journal editor is the writing-first Focus Compose workspace (editor owns the screen + sticky Compose Dock: always-visible mood/tags/categories chips → lightweight overlay pickers, live-update, zero layout shift; in-dock Save/Cancel). Presentation-only — POST/model/migration unchanged; verified real-page desktop+mobile in Chromium. Governing doc `docs/WLJ_JOURNAL_FORM_LAYOUT.md`; platform pattern `01 §6`; front-end invariants + interaction-redesign discipline `03 §6a`. **Carried refinements (visual polish, not architecture — do NOT reintroduce viewport math or a second scroll owner):** refine the Compose Dock visual design · slightly widen the editor on desktop · strengthen the dock's visual hierarchy · increase emphasis of the primary Save action · slightly strengthen the selected-metadata chips · **revisit the presentation of the three Journal modes** (Just Write / Write Together / Talk It Through) *after* the dock is complete · **generalize the Compose Dock into a reusable WLJ Workspace Dock** (Health/Travel/Faith metadata) only AFTER the Journal implementation is complete (platform-consumer pattern, `01 §6`). **Safari/WebKit validation is on Danny (below).**
- **Travel Intelligence — DESIGNED this session, NOT the next milestone.** Full design in `docs/WLJ_TRAVEL_INTELLIGENCE_ARCHITECTURE.md` (v0.1 DRAFT); governing pattern in `01 §6`. It is a **platform-consumer showcase**, built only *after* the reusable platform capabilities above exist. **One open decision blocks ratification (see Waiting on Danny): classify Travel `BEHAVIORAL` (recommended) vs the reserved `CONTEXT` (`descriptors.py:26`).** Do NOT begin Travel code; do NOT build a Travel AI/conversation/reasoning engine. Recommended MVP when it's time: truth spine + conversational planning (Phases 0–2); GPS/live mode is Phase 3 (greenfield — zero device location exists today). Carried sub-concepts: **Workspace ≠ Session**; **location truth = shared platform capability** (Travel = first consumer, not owner).
- **Journal polish that needs Danny's LIVE model + real mic to advance & validate** (already substantially built — do NOT blindly re-tune what you can't run/hear): deeper **contextual reasoning** (relationship reasoning over today's truth), deep **voice polish** (speaking/thinking transitions, mic recovery, reconnect, endpointing feel), **conversation quality** ("feels like my Chief of Staff, not AI"). Voice Pause naming vs the durable draft is minor polish (the transcript already persists every turn → Resume Talk It Through is durable).
- **Journal recent-context truth:** lightweight, request-path-safe "today" facts (meals/exercise/glucose/meds) to deepen questions — needs a cheap cached per-domain snapshot, not heavy builders.
- **Journal genuinely-new-truth:** "goals discussed in my journal", "people mentioned most in my journal" — require NEW deterministic truth, not exposure.
- **Timestamp Precision Phase 2/3** and remaining Health precision rollout · **Artifact perception adapters** (PDF/DOCX/OCR — extend *perception* only, not Conversation State) · **Faith refinements** (pickers, reminder UI, Collection model, Mirror theme analysis) · **WLJ Certification Platform** remaining types · **UTC-vs-user-local calendar-day attribution** · **WLJ Operations** controlled production enablement of the ship-dark recovery engine (Phase III, evidence-gated → OPS-8a) — distinct from the Configuration Governance / OPS-14 track above.
- **Long-term product idea ONLY — tabled, NOT active:** Faith **Life Seasons / Life Chapters**. Do not open without Danny's explicit go.
- **CLOSED — do not reopen:** Renpho direct / Terra.

## ⏳ Waiting on Danny (operator — Claude has no prod access)
- **Validate the shipped CoS product arc in real use (the closed arc awaits your app-validation):** the **Daily Executive Brief** opening your day; a **promised follow-up firing** ("ask me tonight whether I got my workout done" → it returns tonight); a **missing-data ask** when material; a **safe action executing** end-to-end (log/create/block time); and **Reveal Target / Object-Level Reveal** taking you to the right workspace/object ("show me my weight", "log my workout and open it"). If a queued/slow acceptance turn created a leftover test artifact after migration `0041`, remove it. This is real-world validation, not new engineering.
- **RATIFY Travel classification (one decision, unblocks the design):** classify Travel Intelligence `BEHAVIORAL` (recommended — a first-class life domain the CoS serves) vs the reserved `CONTEXT` placeholder. In-Constitution; product call, not a Constitutional Review.
- **Validate in production:** the **Journal unified-draft lifecycle** (M-D1…M-D4, shipped 2026-07-20, flag `features.journal.write_together`, owner-only — journal by talking then typing then talking across a day; confirm the draft follows you and nothing is lost; Finish & Review → Save Journal reads as one story from both channels), **Conversation State**, **Faith domain certification**, the **Measurement Session Capture confirmation experience** (hardening pass shipped 2026-07-20 — upload a body-measurement screenshot → the RESULTS-not-intentions confirmation lists recognized / skipped + why / counts, nothing dropped silently → confirm → the check-in appears in Body Intelligence and is answerable by the CoS; the *core* capability was already validated 2026-07-19, this validates the new confirmation + the deterministic "Import" persistence), plus still-open Faith First Light + Health Sync validations.
- **Validate the Journal Focus Compose workspace in Safari/WebKit (the iOS app + Safari) — the one surface not drivable locally.** Confirm on Create AND Edit: the page scrolls normally (one scrollbar), the editor never resizes/collapses when opening a metadata picker or selecting a mood/tag/category, chips always show current values and update live, nothing is clipped, Save/Cancel stay reachable, and it holds across desktop/mobile + browser zoom. Shipped `f9b93c81`; design is plain document flow + overlays + the shell's own scroll (the safest WebKit structure), but only on-device confirms it.
- **Validate in production: Operations Recovery Stabilization** (`f871a511`, deployed). During the next real degradation confirm the CoS banner / header dot / Ops Wall no longer flap 🟡→🟢→🟡: a `RECOVERING` amber state shows during the confirm window, "recovered" fires **once** only after sustained stability with no active P1/P2 incident, and the header badge reads **"Alignment"** (labelled — not "Status", not a bare green "100%") and renders **"—"** if alignment can't compute. (Hard to force locally — needs a real production dip.)
- **Deploy topology:** the CoS runs in **`wlj-worker`**; `/_health/` reports only the web commit — verify the worker is on the tested commit before trusting a production CoS result.

## 🔀 Concurrency — coordinate, do not collide (Danny runs MANY parallel sessions on the SAME tree)
Commit **only your own files by explicit pathspec** (`git commit -m … -- <paths>`). The changelog and shared files (`apps/core/truth/domain.py`, `apps/ai/multimodal.py`, `apps/ai/cos_services/*`, this bootloader) are heavily contended: re-check the changelog top **immediately before each commit**, defer your line if a foreign entry appeared, isolate your hunk from foreign uncommitted work, verify the push is a fast-forward (never lose a foreign commit). A concurrent session may push the shared branch — including *your* commit — so "nothing to push" can be normal; re-fetch and confirm your SHA is on remote.
