# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent architectural decision, principle, engineering rule, and working preference has already been folded into them.
3. **Do not summarize them back.** Read, absorb, act.
4. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02_WLJ_CONSTITUTION.md §3`, default NO, Danny's explicit written approval).
5. Continue from the live session state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Carries only live sprint state — nothing constitutional, architectural, or duplicated.*

**Last regenerated:** 2026-07-17 (Personal Truth Slice 1 shipped; **development priority changed to bottom-up: Truth Retrieval Certification is the next CoS milestone — STOP optimizing higher-order reasoning until retrieval is certified**).

---

## ⭐ THE PRIORITY CHANGED — develop the CoS strictly BOTTOM-UP
**Do NOT begin the next session by improving reasoning, coaching, or executive synthesis.** This session's central conclusion: *we began optimizing executive reasoning before fully proving deterministic truth retrieval.* The architecture is correct and progressing well — the **implementation order** changes. The CoS cannot be an exceptional executive assistant until it first proves it reliably KNOWS the user's truth.

Governing principle: **WLJ owns deterministic truth; the model reasons FROM it. If deterministic truth retrieval is unreliable, higher-order reasoning is premature.**

### The next milestone is: **PHASE 1 — Truth Retrieval Certification**
Prove, domain by domain, that the CoS correctly answers plain deterministic factual questions. **No reasoning, no synthesis, no coaching — just prove the truth comes back.** Certification questions:
- What did I eat for lunch? · What have I eaten today? · What do I weigh? · What was my glucose this morning? · What medications am I taking? · What workout did I do today? · What did I journal yesterday? · What is my current waist measurement? · What mood did I log yesterday?

**For every failure, TRACE (do not guess, do not prompt-patch first):** Question → routing → tool selection → arguments → canonical source → returned records → final answer. Identify the layer that owns the defect and fix that layer. (This session proved the method: e.g. the meal-plan defect was Layer-E/C *evidence delivery*, not retrieval; the "what have I eaten" defect below is likely *routing*.)

### Then, and only then, work up the ladder
- **Phase 2 — Single-Domain Understanding:** summarize / compare / trend / analyze within ONE domain (nutrition, weight, journal, sleep, glucose, fitness, body measurements).
- **Phase 3 — Cross-Domain Understanding:** nutrition vs workouts, sleep vs glucose, recovery vs training, measurements vs weight.
- **Phase 4 — Executive Chief of Staff:** strategic coaching, blind spots, priorities, executive summaries, recommendations, 90-day planning.

### Ownership model — the guardrail for all of the above (do not blur)
`Personal Truth` = who the user IS · `Domain Truth` = what HAPPENED · `Current Context` = what they're looking at NOW · `Deterministic Understanding` = WLJ's deterministic ASSESSMENT · `the Model` = reasons FROM truth. (Full architecture: `01_…ARCHITECTURE`; deeper PTP doc is a concurrent effort — `docs/DRAFT_THREE_TRUTH_SURFACES_AND_PTP.md`.)

---

## Verified production architecture (current as of this session — reviewed, no divergence found)
- Model Interface **timeout fix** deployed (`model_interface` no longer inherits the 8s utility timeout → 45s; both loop rounds + plain fallback). Endpoint budgets 7 rounds / 3500 tokens; synthesis retry on empty forced-final.
- **Journal** entity surface · **Nutrition** food entity surface (episodic "what happened").
- **Personal Truth Slice 1** (explicit stored facts): one canonical composer (`apps/ai/cos_services/personal_truth.py`), injected into standing context, plus the `get_user_truth` tool; additive — does not replace Domain/entity surfaces. Now has a **high-salience profile lead** (`_profile_lead`) reframing stored targets/conditions as binding CONSTRAINTS (evidence-utilization fix).
- Executive Briefing derives from canonical execution truth · Health Sync separates sync-health from source activity · Dashboard Focus Mode shipped.

## ⛔ DEFERRED — do NOT start until Truth Retrieval Certification is complete
- **Derived Personal Truth / behavioral inference** — favorite foods, preferred protein shake, recurring breakfast, preferred exercises, inferred routines/adherence (the "later derived-fact slice" with provenance/confidence/freshness/invalidation).
- **More reasoning prompts · more executive synthesis · more CoS coaching refinements.**
- Rationale: adding more truth or reasoning before retrieval is certified only increases complexity. Fix evidence *utilization* and *retrieval* first.

## Open investigations / carried bugs (CoS thread)
- **Meals retrieval routing** — "What have I eaten over the last three days?" still answers "no access to detailed meal logs" though `get_entity(nutrition, food)` exists and is advertised. Likely *routing*: "over N days" pulls the model to history/state (no food items) instead of the food entity. **A Phase-1 certification failure — trace it first.**
- **2 pre-existing test failures** (unrelated to this session, proven pre-existing on base): `apps/ai/tests/test_health_facts.py::FoundationalHealthFactsTests` — `test_full_facts_payload_under_2000_chars` (payload drift) and `test_medications_from_canonical_state` (`[]` vs `['Metformin','Valsartan']`). Worth folding into Phase-1 (medications retrieval).
- **Worker-deploy caveat:** the CoS runs in the separate `wlj-worker` Railway service. `/_health/` reports only the **web** commit — several CoS fixes this session (timeout, entity surfaces, Personal Truth, profile lead) are live in the CoS only once **wlj-worker** redeploys onto the pushed commit. Verify the worker version before validating CoS behavior.

## 🔝 Architecture backlog (top item — its own product + truth-model decision, do NOT fold into feature work)
- **UTC-vs-user-local calendar-day attribution.** Health ingest attributes a sample to its **UTC** calendar date; summaries/analysis must agree with ingest or they rebuild a different day than records landed on. Whether UTC (vs the user's local day) is the right truth affects **ingestion, summaries, trends, scoring, and historical interpretation** — a deliberate decision, not a code fix. Kept visible at the top of the backlog.

## Coordination — the CoS is now ONE authoritative thread
Parallel CoS architecture development is ending; **CoS architecture stays in a single session until stabilized** (through Truth Retrieval Certification). Other sessions may continue in their own threads on: **Dashboard · Health Sync · Body Intelligence · Legacy · Operations**. Do not fork CoS work across sessions.

### Parallel track — Operations (separate session, operator-gated; preserved so it's not lost)
WLJ Operations Phase II recovery pilot is **live but operator-gated**: `OPS_RECOVERY_MODE=ACTIVE` with a single allowlisted Beat-retry handler (`recompute_all_health_briefings_task`). The open action is **operator-run** — Danny confirms **O2** (a real `MISSED_RUN` recovered + verified: `RECOVER_ATTEMPTED → VERIFIED/SUCCESS → CLOSED`), then the ledger/maturity/changelog update. Do NOT expand the allowlist until O2 proves out. Full state + runbook: `docs/WLJ_OPERATIONS_VISION.md`, `docs/WLJ_OPERATIONS_PHASE2_PLAN.md §11.1`, `docs/WLJ_OPS_WALL_COVERAGE.md §4.1` (OPS-11, expired-image cleanup, OPS-8b/9/6/10 backlog). This is NOT the CoS thread's priority.

## Waiting on Danny (operator — Claude has no prod access)
- **Validate Personal Truth Slice 1 + the evidence-utilization fix in production** (once `wlj-worker` is on the latest commit): the five acceptance questions, especially *"Build a meal plan using my WLJ profile"* — it must honor stored targets (≤ carb target, not double it) and be shaped by conditions (diabetes). Report the transcript.
- **Operations:** confirm O2 from the ACTIVE pilot (parallel track, above).
- **Doc classification (14 uncertain)** — CURRENT vs HISTORICAL (esp. the CLAUDE.md-linked `INTELLIGENCE_ARCHITECTURE`, `DOMAIN_INTELLIGENCE_ARCHITECTURE`, `ENGINE_COS_REFERENCE`, `ENGINE_INTEGRATION_GUIDE`). `docs/WLJ_DOCUMENTATION_INVENTORY.md §6`.
- **DB backup verification** — confirm the latest Railway Postgres snapshot; record its timestamp in `docs/WLJ_MILESTONE_COS_ARCHITECTURE.md`.

## Immediate next step
**Begin Truth Retrieval Certification — Phase 1.** Work domain by domain through the certification questions; for each failure, TRACE the layer and fix the owning layer. Start with the already-known Phase-1 failure (meals retrieval routing) and medications retrieval. Do not optimize reasoning until retrieval is certified.
