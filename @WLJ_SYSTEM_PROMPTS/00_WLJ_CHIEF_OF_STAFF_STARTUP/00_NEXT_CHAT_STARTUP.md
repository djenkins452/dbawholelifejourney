# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth** — every permanent architectural decision, principle, engineering rule, and preference is already folded into them. **Do not summarize them back.** Read, absorb, act.
3. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02 §3`, default NO, Danny's explicit written approval).
4. Continue from the live session state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Live sprint state only — nothing constitutional, architectural, or duplicated.*

**Last regenerated:** 2026-07-18 (**CoS Truth Certification milestone COMPLETE** — two-owner certification built, first production Customer Truth run measured, roadmap now certification-driven).

---

## ✅ What this session established (now PERMANENT — folded, do not re-derive)
- **Certification drives the CoS roadmap** (the loop + two-owner model): `03_ENGINEERING_OPERATING_GUIDE §3c`.
- **Truth Surfaces** — the CoS reasons from 7 complementary deterministic surfaces; a missing provider ≠ a missing answer: `01 §4/§6` + `docs/WLJ_TRUTH_SURFACES.md`.
- **The instrument is built:** Owner-1 deterministic (`apps/core/truth/question_specs.py`, `capability_matrix()`, `apps/core/tests/test_truth_retrieval_slice.py`) + Owner-2 live via the **Beth Acceptance Center through `CoSGateway`**, capturing per-question structured evidence + first-failing-layer (`AcceptanceResult` columns; run-detail UI panel).

## 🎯 The live roadmap — continue the certification loop on MEASURED evidence
First production Customer Truth run (Danny's real data) scored these. **Rank by measured impact; untested = NOT YET MEASURED, never "low."** Full scorecard + trace plan: `docs/WLJ_CUSTOMER_TRUTH_CERT_PROD1.md`; backlog: `docs/WLJ_CERTIFICATION_BACKLOG.md`.

**Measured PASS:** Weight, Medication, glucose/BP *current*, Fitness (via `health.describe("workout")`), Goals *summary* (via Standing Context).
**Measured weaknesses (the backlog, provisional until the production trace is read):**
1. **Nutrition date-scoped retrieval** — HIGH, but **COORDINATE**: a parallel thread owns it (see Concurrency). Do NOT duplicate.
2. **Glucose/BP trends** — HIGH, **proven** gap (`health.history_metrics` excludes glucose+BP). Small, low-risk, clear of parallel work. **Best next non-colliding slice.**
3. **Body Measurements provider** — MED-HIGH, **proven** (model exists, no `DomainTruth`). Small, low-risk.
4. **Journal source separation** — HIGH (trust): production blended mobility/audio-exposure into "journal". **TRACE FIRST** (which tool served it) before any fix.
5. **Relationships/People retrieval** — MED, missing person entity surface (announced retrieval, empty final).
6. **Goals item-level** (milestones) — summary works via Standing Context; needs a goals provider for detail.
7. Fitness squat-load precision (grounding) · 8. Cross-domain grounding discipline (generic advice leaked into a "strictly WLJ" answer).

## 🔀 Concurrency — coordinate, do not collide (Danny runs parallel sessions on the SAME tree)
- **Meal Intelligence thread** is actively shipping **canonical nutrition truth** (`docs/WLJ_MEAL_INTELLIGENCE_*`, "Meal Intelligence Foundation" commits). It **owns backlog #1 (nutrition)** — coordinate there, do not duplicate.
- **Person / rich-text thread** shipped canonical `people.Person` + `@`-mention journal recognition (`apps/people`, tiptap). Relates to backlog #5 (People retrieval).
- Rule: commit only your own files **by explicit path**; the changelog is contended — re-check its top immediately before each commit; defer your line if a foreign entry appeared.

## ⏳ Waiting on Danny (operator — Claude has no prod access)
- **Run the production Acceptance Center trace** for the partial/failing production results — the `AcceptanceResult` evidence columns (`selected_tool`, `retrieved_records`, `first_failing_layer`) finalize the backlog order (esp. Nutrition data-vs-retrieval, Journal blend source, Relationships stop-reason).
- **Deploy topology:** a Deep "Truth Certification" run executes in **`wlj-worker`**; `/_health/` reports only web. Verify the worker is on the tested commit before trusting a production CoS result.

## 🔮 Deferred initiative — DO NOT implement
- **WLJ Certification Platform** — unify all certification/testing/release-readiness/coverage/maturity into one platform (Production Test Plans = orchestration; subsystems = providers). Open as its OWN initiative only AFTER CoS Truth is production-validated. Recorded: `docs/WLJ_CERTIFICATION_PLATFORM_FUTURE.md`.

## 🔝 Architecture backlog (carried — its own decision, do NOT fold into feature work)
- **UTC-vs-user-local calendar-day attribution.** Health ingest attributes a sample to its UTC calendar date; summaries/analysis must agree with ingest. A deliberate truth-model decision affecting ingestion/summaries/trends/scoring/history — not a code fix.

## Parallel track — Operations (separate session, operator-gated; preserved so it's not lost)
WLJ Operations Phase II recovery is **live but operator-gated** (`OPS_RECOVERY_MODE=ACTIVE`, single allowlisted handler). Open action is operator-run: confirm **O2** (a real `MISSED_RUN` recovered + verified), then update ledger/maturity. Do NOT expand the allowlist until O2 proves out. Not the CoS thread's priority. State: `docs/WLJ_OPERATIONS_VISION.md`.

## Immediate next step
Continue the certification-driven loop. **Recommended next slice: Glucose/BP trends (#2)** or **Body Measurements provider (#3)** — both proven, small, low-risk, and clear of the parallel Meal Intelligence work. Avoid nutrition (#1, parallel thread). Journal (#4) needs a production trace first. Follow the loop in `03 §3c`: Owner-1 fixtures + certify → Customer Truth → attribute the first failing layer → smallest deterministic fix → re-certify.
