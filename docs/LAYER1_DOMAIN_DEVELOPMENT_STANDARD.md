# Layer 1 Domain Development Standard

**Status:** Permanent WLJ architecture. Generalized from the Medication reference
implementation. Part of the [Layer 1 Domain Framework](LAYER1_DOMAIN_FRAMEWORK.md).

> How a canonical domain must be **designed**. Read before writing any code for a new Layer 1
> domain. Subordinate to [`WLJ_ARCHITECTURE_LAWS.md`](WLJ_ARCHITECTURE_LAWS.md) and
> [`LAYER1_ENTITY_COMPLETENESS_CONTRACT.md`](LAYER1_ENTITY_COMPLETENESS_CONTRACT.md).

---

## 0. The one rule everything else serves

**A Layer 1 domain exists to answer the natural business questions a customer would ask about
it — completely, deterministically, from a single retrieval, carrying its own trust.**

Everything below is how you get there. If a design decision does not move the domain toward
that sentence, it is scope, not Layer 1.

---

## 1. Business-first, always. Software second.

**Design the domain from questions, not from models.**

The wrong instinct is to look at the Django models you already have (`Intake`, `IntakeLog`,
`IntakeSchedule`) and expose queries over them. That produces a domain shaped like your
schema, which answers the questions your schema makes easy — not the questions a customer
actually asks.

The right instinct: **write down the natural business questions first**, in the customer's
words, before any code. For Medication that list was:

- What am I taking? / What prescriptions am I taking? / What supplements?
- What's my Metformin dose? / Am I taking fish oil?
- Did I take my meds today? / What do I still need to take today?
- How's my adherence? / How's my Metformin adherence specifically?
- When did I start Metformin? / When did my dose change? / What have I stopped?
- Which of my meds are for diabetes?

Only after that list exists do you choose the implementation that answers all of it. The
question list is the specification. The models are an implementation detail that must serve
it — and if the models can't, that's a gap to close, not a question to refuse.

> **Test of a business-first design:** a non-engineer reading your entity's fields can predict
> which questions it answers. If they can't, you designed from the schema.

---

## 2. Architecture before implementation

**Decide the shape before you write the retrieval.** A Layer 1 domain has a fixed shape,
proven by Medication. Design it in this order — each layer depends only on the one below it:

```
        Business questions            ← written first, in the customer's words
              │
   ┌──────────┴──────────┐
   │  DomainTruth facade  │           MedicineDomainTruth(DomainTruth)
   │  describe() / current() / describe_one() / history()
   └──────────┬──────────┘           one call per business question; composes aggregates INSIDE Layer 1
              │
   ┌──────────┴──────────┐
   │  Deterministic query │           MedicineQueries
   │  layer               │           reads canonical models LIVE; owns no precompute; no SAE
   └──────────┬──────────┘
              │
   ┌──────────┴──────────┐
   │  Canonical models    │           Intake / IntakeLog / IntakeSchedule / MedicationEvent
   └─────────────────────┘
```

Rules that fall out of the shape:

- **Higher layers make ONE call.** Beth, dashboards, reports, and engines all call the same
  `DomainTruth`. They never assemble truth from fragments, and they never each re-derive it.
- **The query layer reads canonical models on the retrieval path.** It owns no precompute and
  depends on no SAE snapshot (Law 4). This is why "I don't have any current medications" —
  the production failure that started Medication — cannot recur: there is nothing to be stale.
- **Aggregates are composed inside Layer 1.** "Overall adherence" is computed in the domain
  and returned as part of the object, so the caller still makes one call.

Design this on paper (or in the domain's inventory doc) before implementing. See
[`DOMAIN_TRUTH_CONTRACTS.md`](DOMAIN_TRUTH_CONTRACTS.md) for the `DomainTruth` base contract.

---

## 3. Entity completeness (the law you must satisfy)

Read [`LAYER1_ENTITY_COMPLETENESS_CONTRACT.md`](LAYER1_ENTITY_COMPLETENESS_CONTRACT.md). The
law, verbatim:

> **A canonical entity is complete when it can completely answer the natural business questions
> about itself from a single deterministic retrieval.**

The current implementation of the law is `CompleteEntity` (`apps/core/truth/entity.py`) — six
business dimensions, each carrying **freshness + confidence**, with an open `extensions` map:

| Dimension | The natural question it answers | Medication | Goal (illustrative) |
|---|---|---|---|
| **Identity** | What is it? | name | title |
| **Definition** | What specifies it? | dose, category, purpose | target, metric, why |
| **Status** | What lifecycle state? | active / discontinued | active / achieved / abandoned |
| **Plan** | What is *supposed* to happen? | schedule | deadline + target |
| **Standing** | What's happening *now* vs plan? | taken today (per dose) | progress to date |
| **Performance** | How has it gone over time? | 7/30/90-day adherence | pace, % to target, trend |

How to apply this when designing a new domain:

1. For each business question from §1, decide **which dimension** answers it. If a question
   fits none of the six, it is a candidate for an `extensions` dimension — add it there, and
   if it proves universal across domains, propose promoting it to a named dimension.
2. **A missing dimension must be visibly empty, never fabricated.** `CompleteEntity` is a
   dataclass whose fields *are* the dimensions — you cannot return a half-described entity
   without it being obvious.
3. Implement `describe(entity_type) -> list[CompleteEntity]` (the whole inventory) **and**
   `describe_one(name) -> CompleteEntity | None` (single-entity retrieval by name). Medication
   proved that single-entity retrieval is not optional: "What's my Metformin dose?" is as
   natural as "What am I taking?", and the second without the first is an incomplete domain.

> **The dimensions are the current implementation, not the law.** Conform by answering the
> natural questions — not by matching a fixed field list forever.

---

## 4. Canonical Truth (one source, read live)

- **One source of record.** The domain's `DomainTruth` is *the* answer. If two surfaces can
  disagree about a fact, the domain is not canonical. (Medication had adherence computed three
  different ways across dashboard, email, and Beth — the fix was one classifier and one
  calculation everyone calls.)
- **Read live from canonical models; never from a snapshot on the answer path** (Law 4). The
  SAE / caches may *consume* the domain truth for precompute, but they are never the *source*.
- **Reuse the canonical calculation.** If adherence/streak/pace already exists in a `*_utils`
  module, call it — never re-derive inline. Inline re-derivation is how a "schedule-based" and
  a "log-based" number drift apart and the customer loses trust.
- **Carry trust on every answer** (Laws 1 & 2). Freshness and confidence travel with the
  entity. "Present but zero" (a real `0`) is a trustworthy answer; "unknown because the
  snapshot is missing" is a bug.

---

## 5. Business vocabulary (a word means exactly one thing)

Ambiguous vocabulary is a trust defect, not a phrasing nuance. Medication's central vocabulary
decision:

> **"Medicine" / "Medication" = PRESCRIPTION only.** Supplements, OTC, and Wellness are
> separate first-class categories and are **never** counted as medicine.

This one rule drove: a four-way canonical classifier (`medicine_classification.py`) that is the
single source of truth for what an item *is*; a name-based safety net so a mis-tagged supplement
can never leak into the prescription number; and adherence metrics scoped so "Medication
adherence" can never silently include a vitamin.

For a new domain, **define the vocabulary explicitly and make it enforceable in code**:

1. List the domain's category words and pin each to exactly one meaning.
2. Put the classification in **one** function that every surface calls (never re-classify
   ad hoc).
3. Make the classifier the **final authority per object**, applied after any DB filter — a
   mis-tagged row must not be able to change what a word means.
4. Every category should be **symmetric**: if prescriptions support inventory / execution /
   adherence / profile, so must supplements, OTC, and wellness. Asymmetry ("supplements only
   return a list") is an incomplete domain.

Record the vocabulary in a domain contract doc (Medication's is
[`MEDICATION_ADHERENCE_TRUST_CONTRACT.md`](MEDICATION_ADHERENCE_TRUST_CONTRACT.md)).

---

## 6. Deterministic retrieval

- **Deterministic questions get deterministic answers** (Law 4). The domain answers from the
  models; the LLM is not in the retrieval path and is asserted *not called* in acceptance.
- **A retrieval failure is reported as a retrieval failure** — never "assistant unavailable"
  and never a fabricated value.
- **Name resolution must be forgiving but not promiscuous.** Medication stores "Metformin HCL
  ER" but the customer asks "Metformin"; `describe_one` resolves a short name by a distinctive
  name **token** (≥4 chars, minus generic stopwords like "daily"/"tablet"), most-specific match
  wins — so "Metformin" resolves the full name while "daily routine" does not false-match.
- **Order the classifier so specific beats generic.** Route "what supplements am I taking" to
  supplements *before* the bare "medication" keyword; route a detailed "profile" request before
  the "adherence" keyword; run history ("when did my dose change") before the present-time
  "dose" cue. Ambiguous routing is a silent wrong-answer generator.
- **Stability** (Law 5): identical question + unchanged data ⇒ identical answer. Because
  retrieval is deterministic and reads live, this is free — but it is *tested*, not assumed.

---

## 7. Acceptance philosophy (build it to be broken)

Full method is in the [Business Acceptance Playbook](LAYER1_BUSINESS_ACCEPTANCE_PLAYBOOK.md);
the design-time obligations:

- **Declare completion only after a break attempt, not before.** Medication's biggest maturity
  jump came from "becoming Danny" and running a large natural-question set *before* declaring
  done — which exposed that the entities were complete but the *retrieval surface* around them
  was not (single-entity, symmetric categories, combined view, "what's left").
- **Every production defect becomes a permanent regression.** No exceptions. The regression is
  the frozen record that the defect can never return.
- **Acceptance validates the product, not the code.** A green unit test that asserts the old
  wrong behavior is worse than no test. Assert against the real evaluator (the acceptance
  `gates`), and assert the *rendered answer a customer would read*, not an internal dict.
- **SAE-disabled acceptance.** Prove the domain answers with the snapshot layer patched to raise
  — that is the proof it reads canonical truth live and needs no precompute.

---

## 8. Definition of a well-developed domain (design checklist)

Before implementation is considered done (certification is separate — see the
[Certification Standard](LAYER1_DOMAIN_CERTIFICATION_STANDARD.md)):

- [ ] The natural business-question list is written, in the customer's words, and reviewed.
- [ ] Each question maps to a dimension of `CompleteEntity` (or a justified `extensions` one).
- [ ] `DomainTruth.describe()`, `describe_one()`, and `current()` implemented; one call per
      question; aggregates composed inside Layer 1.
- [ ] The query layer reads canonical models live; owns no precompute; reads no SAE.
- [ ] Business vocabulary defined, pinned to one classifier, applied as final per-object
      authority; all categories symmetric.
- [ ] Freshness + confidence carried on every entity; "present-but-zero" distinguished from
      "unknown."
- [ ] The canonical calculation is reused (no inline re-derivation).
- [ ] A break-attempt question set exists and passes SAE-disabled, LLM-asserted-not-called.
- [ ] Every known production defect for the domain has a permanent regression.

---

*Reference implementation: `apps/health/services/medicine_queries.py`,
`apps/health/services/medicine_domain_truth.py`, `apps/health/tests/test_medicine_domain_truth.py`.*
