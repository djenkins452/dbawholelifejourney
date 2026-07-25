# WLJ Truth Layer — Executive Architecture Assessment

**Date:** 2026-07-23 · **Type:** architecture review (no implementation)
**HEAD assessed:** `a6a15b38`
**Question:** *How close is WLJ to having a production-certified deterministic Truth Layer?*

**Evidence rule:** every claim below is drawn from runtime measurement at HEAD, a passing
certification gate, or a completed commit. Where something is unknown, it says so.

---

## Section 1 — Executive Summary

| | |
|---|---|
| **Overall maturity** | **65%** |
| **Confidence in this number** | **Medium-high** for the deterministic layer (measured); **low** for end-to-end customer truth (largely unvalidated in production) |
| **Architectural maturity** | **Mature and converged.** The hard architectural questions are answered and enforced by contracts, not convention. |
| **Classification** | **PRODUCTION-CAPABLE — not production-certified** |
| **Recommendation** | Two more foundational milestones, then shift focus. Do not shift yet. |

**Why "production-capable" and not "production-certified":**

Production-certified would require that the *customer-facing* path is proven, repeatably,
in production. Four measured facts prevent that claim:

1. **Certification is 58% of applicable capability cells** (61 certified / 106 applicable;
   live `capability_matrix()` at HEAD). 40 cells are *assessed* — the provider is believed
   capable, but no test has executed it.
2. **Owner-2 (live Customer Truth through the gateway) is not certified.** Per
   `WLJ_TRUTH_RETRIEVAL_COVERAGE.md`, no automated Deep run has executed on the deployed
   worker. Everything proven this week was proven by **hand-written probe scripts**, not a
   repeatable harness.
3. **Four declared shadow authorities are still serving** (F1–F5; F2 explicitly
   **BLOCKED by a clinical-safety finding**). They are *visible and contained* — which is
   a genuine achievement — but visible ≠ compliant.
4. **Almost everything shipped in the last seven days is AWAITING production validation.**
   Exactly one item has confirmed production validation: the weight questions Danny
   verified in this program (`280.4` / `281.5` / most-recent semantics).

**Why "mature" architecturally:** in five days, four distinct defect *classes* were found,
runtime-proven, eliminated, and locked shut with CI gates. That cadence is only possible on
an architecture whose seams are in the right places.

---

## Section 2 — Certified accomplishments

| Milestone | Status | Evidence | Remaining risk |
|---|---|---|---|
| **One deterministic authority per truth domain** | ✅ Architecturally enforced | `apps/core/truth/domain.py` — **20 registered domains**; `authority.py` metadata contract; **127 served keys, 127 declaring authority, zero anonymous** | F1–F5 declared shadows still serve |
| **Retrieval Authority Framework** | ✅ CERTIFIED (mechanical) | `WLJ_RETRIEVAL_PLATFORM_CERTIFICATION.md` — F0 closed (`1690a4f4`); 13 contract gates | Framework certified; **surfaces not all compliant** |
| **Date-scoped metric authority** | ✅ COMPLETE | `metric_date.py`; exact-date vs `latest_on_or_before` **named apart**; 21 gates (`140e6c3c`) | — |
| **Incomplete-key-set class** | ✅ COMPLETE | Key set **derived** from the capability index — symmetric by construction (`5b4bd722`) | — |
| **Natural date authority** | ✅ COMPLETE | WLJ resolves the year, not the model (`f7cad624`) | — |
| **Snapshot delegation** | ✅ COMPLETE | Nutrition snapshot delegates to `get_daily_totals`; *snapshot-is-not-a-producer* gate (`852e242c`) | Only proven for nutrition/tasks |
| **Calendar-bound truth** | ✅ COMPLETE | **31 of 31** day-claims stamped; 24 gates; 9 timezones, DST both hemispheres, leap day, year rollover (`49d9e0d1`) | — |
| **User-local temporal semantics** | ◐ **FIRST SLICE ONLY** | 212 sites classified (A79/B60/C42/D4/E27); Task authority migrated; 13 gates; CI guard (`a6a15b38`) | **101 of 102 B/C sites unmigrated** |
| **Current Context** | ✅ Certified tier | Dashboard, Health/Finance/Meals Home, journal.home; 5 gates (`e00f6c98`) | Glucose/calendar/goals/tasks overviews remain |
| **Production forensics** | ✅ COMPLETE | Per-turn `turn_id`, `conversation_id`, real values in `truth_digest` (`140e6c3c`) | **No operator read channel** |
| **Conversation State** | ◐ Shipped, partially certified | Subject anchoring from *every* truth retrieval (`140e6c3c`) | Entity-retrieval follow-ups unanchored |
| **Timestamp precision** | ◐ Phase 1 only | `truth/precision.py` | Phases 2–3 not started |
| **Multimodal truth** | ✅ Closed (prior program) | `0dcbeb93`, 169 tests | Not re-verified in this program |

---

## Section 3 — Truth architecture scorecard

| # | Area | Score | Why / evidence | Remaining work |
|---|---|---:|---|---|
| 1 | **Truth Authority** | **80** | 20 domains under one `DomainTruth` contract; 127/127 keys declare authority | F1–F5 shadows |
| 2 | **Truth Retrieval** | **75** | Derived key set; one door for "metric on date D"; natural dates | F2 blocked, F4 deferred |
| 3 | **Truth Exposure** | **70** | 113 QuestionSpecs across 18 domains; entity/history/analysis surfaces | 5 declared gaps; nutrition exposes **0** `current` metrics |
| 4 | **Truth Consistency** | **72** | Full-surface agreement matrices certified for **nutrition** and **tasks** | 18 other domains unproven |
| 5 | **Temporal Semantics** | **55** | `calendar_day.py` authority; 24 gates; 9 zones/DST/leap/year | **101 of 102** B/C sites unmigrated |
| 6 | **Current Context** | **85** | Two-pattern contract; certified overview tier | Remaining overviews |
| 7 | **Conversation State** | **60** | Deterministic subject anchoring, references-only | Entity follow-ups; **self-consistency reasoning miss unresolved** |
| 8 | **Snapshot Architecture** | **85** | Cache-not-producer proven; day-stamp registry; rollover-before-write | Delegation proven for 2 of 8 registered modules |
| 9 | **Freshness** | **78** | Envelope + `ensure_fresh` + rollover + honest stale disclosure | Heavy modules background-only |
| 10 | **Confidence** | **70** | Shared `confidence_from_freshness/coverage` | Not uniform across all 127 keys |
| 11 | **Provenance** | **80** | `authority` + `source` in envelopes; 127/127 declared | F5 aggregates carry weak semantics |
| 12 | **Auditability** | **70** | Per-turn ids; **values** in digest | **No operator read channel — every incident still needs local reproduction** |
| 13 | **Tool Selection** | **60** | One door for date questions removed the biggest trap | Model invented `entity_type: nutrition_overview` → false absence (runtime-observed) |
| 14 | **Truth Envelopes** | **75** | `metric_date` envelope complete; `domain_state` discloses day freshness | Not uniform platform-wide |
| 15 | **Domain Completeness** | **50** | 20 registered — but depth varies enormously (health 33 history metrics; **finance 2 current / 0 history / 0 entities**) | Most domains are shallow |
| 16 | **Certification Coverage** | **58** | 61 certified / 106 applicable cells (live matrix) | 40 assessed cells |
| 17 | **Runtime Verification** | **65** | Extensive real-model, ToolCallLog-backed probes this week | **Ad-hoc scripts, not a repeatable harness**; Owner-2 not automated |
| 18 | **Developer Tooling** | **45** | Certification is script-driven | No operator endpoint; no one-command truth cert |
| 19 | **Operations Visibility** | **40** | Ops Wall exists | **`WLJ_OPERATIONS_TRUTH_PATH_INVESTIGATION.md` proves TWO operational authorities (COAS vs Executive) — unresolved** |
| 20 | **Customer Trust** | **60** | Weight validated in production | Four distinct trust failures found in five days; most fixes unvalidated |

**Weighted overall: 65%.**

---

## Section 4 — Remaining architectural gaps (ranked by customer trust)

1. **Safety behavior attached to the wrong layer.** The glucose future-timestamp guard
   lives in the SAE path in `health_facts.py`, **not** in the canonical accessor — so
   delegating `last_glucose_reading` *regresses clinical safety* (proven; F2 reverted).
   **This is the most serious gap in the review:** it means canonical accessors are not
   yet the safety boundary, and any future delegation can silently drop a protection.
2. **Two operational authorities.** COAS scores drive Clara's notifications while
   `executive.overall_status` drives the Wall/dot/banner. The same parallel-authority
   class already eliminated in domain truth, still live in Operations.
3. **Owner-2 has no automated certification.** Customer truth is proven by disposable
   scripts. Nothing prevents regression between sessions.
4. **No operator audit channel.** `ToolCallLog` is rich but unreachable in production;
   incidents are answered by local reproduction, which is slow and environment-divergent.
5. **Declared-but-serving shadows (F1–F5).** Contained and visible, not compliant.
6. **Temporal migration is 1% complete** (1 of 102 B/C sites). The authority exists;
   adoption does not.
7. **Envelope non-uniformity.** Some keys carry full evidence; F5 aggregates do not.
8. **Domain shallowness.** Finance, artifacts, capture, notes have registered contracts
   with almost no depth — a certified *contract* over a thin domain reads as more mature
   than it is.

---

## Section 5 — Domain maturity

Certified / assessed / gap counts are live from `capability_matrix()` at HEAD.

| Domain | Truth surfaces (cur/hist/ent/anal) | Cert cells | Maturity | Known risk | Next milestone |
|---|---|---:|---|---|---|
| **Health** | 6 / 33 / 7 / 5 | 6c 1a 1g | **High** | F2 safety guard; analytics on server dates | Relocate the safety guard |
| **Nutrition** | 0 / 6 / 3 / 11 | 6c 0a 2g | **High** | **0 `current` metrics** — "today so far" has no current surface | Close the 2 gaps |
| **Weight** (in health) | — | certified | **High — prod-validated** | none known | — |
| **Tasks** | 2 / 1 / 1 / 0 | 3c 3a | **Medium-high** | Was UTC-dated until `a6a15b38` | Certify remaining cells |
| **Calendar** | 4 / 1 / 1 / 0 | 3c 3a | **Medium** | `today_events` day-stamped but not agreement-certified | Surface agreement |
| **Goals** | 5 / 2 / 3 / 2 | 4c 2a | **Medium** | `goal_queries.overdue` on server date | Temporal slice #1 |
| **Habits** | 1 / 1 / 1 / 1 | 3c 3a | **Medium** | thin | Certify |
| **Faith** | 4 / 1 / 8 / 13 | 2c 4a | **Medium** | close-out awaiting prod validation | Validate |
| **Journal** | 3 / 1 / 1 / 14 | 4c 2a | **Medium-high** | prod-complete per program record | — |
| **Meals** | 1 / 0 / 6 / 0 | 3c 1a | **Medium** | own governing architecture; day-attribution unmigrated | Meals temporal slice |
| **Medicine** | 17 / 1 / 4 / 0 | 5c 1a **2g** | **Medium-high** | adherence is calendar-bound | Close 2 gaps |
| **Medical** | 5 / 1 / 3 / 1 | 4c 2a | **Medium** | lab-value windows | Certify |
| **Relationships** | 4 / 0 / 1 / 0 | 3c 1a | **Low-medium** | no history surface | Person consolidation |
| **Finance** | 2 / 0 / 0 / 0 | **0c** 2a | **Low** | **no entity or history surface; zero certified cells** | Establish truth depth |
| **Legacy** | 4 / 0 / 3 / 0 | 2c 2a | **Low-medium** | preservation-first; no history | — |
| **Projects** | 1 / 0 / 1 / 0 | 3c 1a | **Low** | thin | — |
| **Brain training** | 3 / 2 / 1 / 0 | 3c 3a | **Low-medium** | thin | — |
| **Capture / Notes / Artifacts / Events** | 1–2 surfaces each | 0–3c | **Low** | artifacts **0 certified** | — |
| **Travel** | not registered | — | **Design only** | not built | Deliberately deferred |

---

## Section 6 — Certification coverage

**Measured at HEAD:** 160 matrix cells → **61 certified · 40 assessed · 5 gaps · 54 n/a**.

* **Certified share of applicable cells: 61 / 106 = 58%.**
* Certified share of *all* cells: 38%.

**Major blind spots:**

1. **Owner-2 / customer truth — 0% automated.** The layer the customer actually touches.
2. **Streaming (SSE) path — uncertified.** Shares `generate`, but the relay wrapper has no suite.
3. **Cross-domain and executive questions — uncertified.** All certification is single-domain.
4. **Finance (0 certified) and artifacts (0 certified).**
5. **The 40 "assessed" cells** — believed-capable, never executed.

**Highest-risk uncertified areas** (likelihood × trust damage): Owner-2 end-to-end ·
Medicine adherence gaps (safety-adjacent) · Finance · cross-domain reasoning inputs.

---

## Section 7 — Remaining defect classes

| # | Class | What creates it | Customer impact | Difficulty | Order |
|---|---|---|---|---|---|
| 1 | **Safety logic outside the canonical accessor** | Guards added at the consuming surface, not the authority | A delegation silently drops a clinical protection | Medium | **1st** |
| 2 | **Parallel operational authority** | Two producers of "system status" | Contradictory notifications vs dashboard | Medium | **2nd** |
| 3 | **Unmigrated user-calendar calculations** | 102 B/C sites; only 1 migrated | Wrong day near midnight — invisible to UTC developers | Low each, high volume | **3rd** |
| 4 | **Declared-but-serving shadows (F1–F5)** | Curated keys that snapshot independently | Two answers to one question | Low–medium | 4th |
| 5 | **Unverifiable production incidents** | No operator audit channel | Every incident costs a reproduction cycle | Low | 5th |
| 6 | **Uncertified customer path** | No automated Owner-2 harness | Regressions land silently | Medium–high | 6th |
| 7 | **Model-layer reasoning misses** | Free-associated `entity_type`; unanchored follow-ups; self-contradiction not owned | False absence; "which two numbers?" | Hard — **not a truth defect** | Last |
| 8 | **Envelope non-uniformity** | Legacy aggregates without full evidence | Model can't judge usability | Low | Opportunistic |

---

## Section 8 — What should NOT be worked on

1. **Do not migrate all 102 temporal sites.** 79 A + 27 E sites are legitimately UTC; a
   sweep would break correct code. Slice by proven risk.
2. **Do not start Travel Intelligence.** Designed, deliberately deferred; it is a platform
   *consumer* and would consume foundational attention.
3. **Do not build bidirectional Current Context / Desired Context / Reveal Target.** The
   gate for it is satisfied, but retrieval certification is not finished.
4. **Do not add reasoning capabilities to fix reasoning misses.** The self-consistency miss
   and the invented `entity_type` are model-layer; a WLJ-side detector is precisely the
   symptom-detection the guide forbids.
5. **Do not deepen shallow domains (Finance, Projects, Notes) yet.** Depth before the
   certification harness exists produces uncertified surface area.
6. **Do not redesign Current Context, Meals, or Multimodal.** All are closed programs.
7. **Do not chase F5.** Lowest-risk residual; it claims no date scope and cannot contradict
   an exact-date answer.

---

## Section 9 — Recommended roadmap (next 10 milestones)

Each eliminates a class, raises trust, and adds no features.

1. **Relocate clinical safety guards into canonical accessors** → unblocks F2 + F4; makes
   the authority the safety boundary. *(Class 1)*
2. **Collapse Operations to one authority** — notifications derive from
   `executive.overall_status`. *(Class 2)*
3. **Operator audit endpoint (read-only) for `ToolCallLog`** — answer the next incident
   from real rows. Small, compounding. *(Class 5)*
4. **Automated Owner-2 harness** — the golden-transcript suite through
   `CoSGateway.respond`, runnable on the worker. Converts this week's disposable scripts
   into a permanent gate. *(Class 6)*
5. **Temporal slice #1 — overdue / on-time** (`goal_queries`, `execution/timing`). *(Class 3)*
6. **Temporal slice #2 — meal-day attribution + health analytic windows.** *(Class 3)*
7. **Close F1/F3/F4 renames + delegation** once #1 lands. *(Class 4)*
8. **Nutrition `current` surface** — 0 current metrics today; "today so far" has no
   canonical current answer.
9. **Cross-domain certification tier** — first multi-domain question specs.
10. **Finance truth depth** — the weakest registered domain; only after #4 exists.

---

## Section 10 — Executive opinion

**Can we trust the Truth Layer?**

**Partially, and with a clear boundary.** Trust what is *certified*: date-scoped metrics,
calendar-day claims, snapshot delegation, nutrition and weight retrieval, the authority
metadata contract. That set is genuinely strong — enforced by CI gates, not convention, and
weight is the one piece validated in production.

Do **not** yet trust: anything calendar-sensitive outside the migrated slice, Operations
status, and — most importantly — **the assumption that a fix stays fixed**, because the
customer-facing path has no automated certification.

**Can we shift focus to higher-level Chief of Staff behavior?**

**Not yet — but the remaining work is small and well-defined.** The evidence against
shifting is concrete: four distinct trust-breaking classes were discovered in five days,
each by a real conversation rather than by a test. That rate says the surface is still
under-certified. Two facts in particular argue for finishing:

* **The F2 safety finding.** A canonical accessor that is not the safety boundary is a
  latent clinical-safety defect, not a tidiness issue.
* **No automated Owner-2 harness.** Every improvement this week is protected only by the
  memory of the session that made it.

**My recommendation as Chief Architect:** complete roadmap items **1–4** — safety guard
relocation, Operations authority collapse, the operator audit endpoint, and the automated
customer-truth harness. That is a bounded body of work with no new features, and it
converts "production-capable" into "production-certified." **After item 4, shift.** The
truth foundation will then be defended by gates rather than by attention, which is the
actual precondition for working on higher-level Chief of Staff behavior.

**One honest caveat:** this assessment measures the deterministic layer well and the
experiential layer poorly. Until item 4 exists, any statement about end-to-end customer
truth — including this one — rests on spot checks.
