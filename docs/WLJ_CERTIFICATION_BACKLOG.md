# WLJ Chief of Staff — Certification-Driven Backlog & Operating Model

**Status:** governing operating model as of 2026-07-18. Certification — not intuition — drives the roadmap.

---

## The operating model (do not skip steps)
For every truth domain, in order:

1. Deterministic fixtures → 2. Owner-1 certification (provider returns the right value, no OpenAI) → 3. Customer Truth certification (real question → gateway → ModelInterface → live model → grounded answer) → 4. Evidence capture → 5. Failure-layer attribution → 6. Root-cause → 7. **Smallest correction to the FIRST failing layer only** → 8. Re-certify. Repeat.

**Two environments, complementary (neither replaces the other):**
- **LOCAL** — deterministic truth on controlled fixtures.
- **PRODUCTION** — the real customer experience on real data + the deployed worker.

**Failure discipline:** never patch prompts, special-case routing, hardcode questions, or "improve AI." Identify the first failing layer; fix only that; re-certify.

**The roadmap question is now:** *"What did certification PROVE needs to be built next?"* — never "what seems important."

---

## Evidence discipline — three tiers (do NOT conflate)
- **① MEASURED** — a Customer Truth run produced pass/fail + a first-failing-layer. *Only Weight/Medication/Nutrition, LOCAL only, so far.*
- **② DETERMINISTIC-ASSESSED** — `capability_matrix()` shows the provider SURFACE exists (◐) or is missing (✗). This measures *surface availability*, **not customer impact.**
- **③ UNASSESSED** — no certification of any kind.

> **Absence of evidence is not evidence of low priority.** Untested domains are ranked "impact UNMEASURED," never "low."

---

## The certification backlog (sorted: MEASURED impact first, then surface gaps, then unassessed)

### Tier ① — MEASURED (from the LOCAL Customer Truth slice-1, 2026-07-18)
| # | Domain | Capability | Customer impact | First failing layer | Cert status | Blocking dependency |
|---|---|---|---|---|---|---|
| 1 | Weight (health) | Current fact / Latest / Comparison | **HIGH (measured)** — "what do I weigh" is a core daily question; failed live | Evidence delivery — **stale SAE `current_weight`** (test-env; proven NOT a builder bug) | ❌ LOCAL fail — **cause pending PROD confirm** | **PROD re-cert** (fresh worker) to confirm test-env vs real |
| 2 | Nutrition | Latest / Existence-by-date | **MEDIUM (measured)** — failed live; but `get_entity` answers the same needs and passed | Model **tool-selection** (chose date-only fact / erroring `search_history` over `get_entity`) | ❌ LOCAL fail (model layer) | Not a deterministic fix — do NOT patch; candidate truth-shape improvements below |
| 3 | Nutrition | (infra) `search_history` | **MEDIUM (measured)** — tool errored on nutrition, caused a live failure | Evidence retrieval — `search_history` returns error/`freshness: missing` | ❌ deterministic bug (secondary) | none — self-contained fix once prioritized |
| 4 | Medication | "when did I last TAKE X" | **LOW–MEDIUM (measured)** — weak pass; answered today's dose status, not last-taken date | Truth gap — no last-taken surface | ✅ **FIXED + re-certified** (2026-07-18) — `MedicineQueries._last_taken` → `performance.last_taken`; `med.last_taken` spec green; medicine `latest` ◐→✓ | none |
| 5 | Nutrition | Current/Historical (date-scoped) | **MEDIUM (measured indirectly)** — model worked around the missing date filter via `get_entity` reasoning (passed today/yesterday), so lower urgency than the audit assumed | Canonical provider — `describe(food)` has no date filter | ◐ works via model reasoning | none |

**PASSED live (no action) — proof the pipeline works:** weight-yesterday, highest-this-month, med list/active/dosage/history, meals today/yesterday, have-eaten-pizza (10/15).

### Tier ② — DETERMINISTIC surface gaps (from `capability_matrix()` — impact UNMEASURED)
| Domain | Capability | Surface status | Customer impact | Cert status |
|---|---|---|---|---|
| Goals / Missions | all | **✗ no DomainTruth at all** | **UNMEASURED** | not certified — no provider |
| People (canonical identity) | all | **✗ not in truth registry** | **UNMEASURED** | not certified — no provider |
| Medical (labs/vitals) | entity/history | **✗ no DomainTruth** (SAE blob only) | **UNMEASURED** | not certified |
| Body Measurements | current/comparison | **✗ model exists, no surface** | **UNMEASURED** | not certified |
| Documents | all | **✗ no domain** | **UNMEASURED** | not certified |
| Health (weight) | Count | ✗ no windowed-count surface | UNMEASURED | assessed gap |
| Medicine | Comparison / Count | ✗ | UNMEASURED | assessed gap |
| calendar/faith/tasks/finance/legacy/journal/relationships | history/timeline/entity (various ◐) | ◐ assessed, no spec run | UNMEASURED | not Customer-Truth-tested |

*These are surface facts, not impact rankings. To rank any of them, run a certification slice that MEASURES it.*

---

## Recommended NEXT certification slice (evidence-based)

**Recommendation: CLOSE the Weight/Medication/Nutrition loop before opening any new domain.** The evidence points here, not at a new domain — and the new standard *requires* both LOCAL and PRODUCTION certification, which slice-1 has not completed.

- **Domain:** Weight · Medication · Nutrition (the already-measured slice).
- **Capabilities to certify:** the same 15 questions, now in **PRODUCTION** (deployed worker, fresh SAE) — plus re-certify after each fix.
- **Estimated customer impact:** **HIGH and MEASURED.** #1 (current weight) is a core daily question that *failed live*; resolving test-env-vs-real is the single highest-value open question we have actual evidence for.
- **Why it is the highest-value next investment:** (a) it is the only work backed by *measured* evidence; (b) the local-vs-production standard makes slice-1 *incomplete* until it runs in production; (c) it resolves whether #1/#3/#5 are environmental or real — you cannot correctly prioritize a fix until that is known; (d) it honors "do not jump ahead to a new domain."
- **Prerequisites:** deploy the current commit to **`wlj-worker`** + **web**; run a Deep "Truth Certification" acceptance from the Acceptance Center against a seeded fixture user (or the owner). *This step needs production access — it is Danny's to run; the harness + evidence capture + panel are already in place.*

**Sequenced next steps (all evidence-gated):**
1. **PROD re-cert of slice-1** → reclassify #1/#3/#5 (test-env vs real). *(Danny)*
2. If PROD confirms a real current-weight defect → fix the FIRST failing layer only (serve current-weight from the live `weight_on` source, or guarantee SAE freshness), then re-certify.
3. Fix the two self-contained deterministic bugs surfaced with evidence: `search_history` nutrition error (#3), medicine last-taken surface (#4).
4. **Only after slice-1's loop is closed** do we open a new domain. Its selection **cannot be impact-ranked today** (no evidence). The evidence-generating move is to run cheap **Owner-1** certifications across candidates (Goals, People, Body Measurements) — each is a hard ✗ surface gap — then a small Customer Truth probe to MEASURE impact before committing. Do not pre-rank them.

---

## What this document deliberately does NOT do
- It does **not** rank Goals/People/Body-Measurements/Finance/Legacy by customer impact — there is no measurement for them yet.
- It does **not** recommend a new domain as "next" — the evidence says finish slice-1 first.
- It does **not** authorize any prompt-patch, routing special-case, or "AI improvement" — every fix must target a first failing layer and re-certify.

*Implementation is gated on this prioritization being accepted. The next concrete action (PROD re-cert of slice-1) requires production access.*
