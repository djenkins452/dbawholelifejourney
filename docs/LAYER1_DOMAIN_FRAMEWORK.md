# Layer 1 Canonical Truth — Domain Framework (Entry Point)

**Status:** Permanent WLJ architecture. Extracted from the Medication domain — the first
domain to pass Smoke, Full, Deep, and Beth Production acceptance and be designated the
**reference implementation for Layer 1 Canonical Truth**.

> Medication is not merely the first completed domain. It is the **template** every future
> canonical domain follows. This framework is that template, generalized. No new Layer 1
> domain begins until it can state how it will satisfy every document below.

---

## Why this exists

Layer 1 is the frozen foundation of WLJ: **WLJ owns truth; the LLM owns reasoning.** A
"domain" is a slice of that truth (Medication, Goals, Calendar, Relationships, Journal,
Finance, …). Before Medication we fixed truth defects one production report at a time.
Medication taught us that the reports were symptoms of a single deficiency — the domain
was not architected as a **complete, deterministic, self-describing business object** — and
that fixing symptoms never converges. This framework encodes the process that does.

Read [`LAYER1_LESSONS_LEARNED.md`](LAYER1_LESSONS_LEARNED.md) first if you want the "why."
Read the rest in order when you build a domain.

---

## The five documents

| # | Document | Answers |
|---|----------|---------|
| 1 | [Layer 1 Domain Development Standard](LAYER1_DOMAIN_DEVELOPMENT_STANDARD.md) | How is a canonical domain **designed**? (business-first, entity completeness, deterministic retrieval, business vocabulary) |
| 2 | [Layer 1 Domain Certification Standard](LAYER1_DOMAIN_CERTIFICATION_STANDARD.md) | Which **gates** must pass before a domain is certified? (architecture → technical → Smoke → Full → Deep → Beth Production → production conversation) |
| 3 | [Layer 1 Business Acceptance Playbook](LAYER1_BUSINESS_ACCEPTANCE_PLAYBOOK.md) | How should a developer **think** when validating a domain? (the philosophy, not the test cases) |
| 4 | [Layer 1 Capability Maturity Model](LAYER1_CAPABILITY_MATURITY_MODEL.md) | The **progression** every domain moves through: symptoms → capability → architecture → business contract → entity completeness → acceptance → certification |
| 5 | [Layer 1 Lessons Learned](LAYER1_LESSONS_LEARNED.md) | Everything Medication **taught us**, so no future domain relearns it the hard way |

## Governing documents these build on (do not restate — defer)

- [`WLJ_ARCHITECTURE_LAWS.md`](WLJ_ARCHITECTURE_LAWS.md) — the platform constitution (Laws 0–5 + the Answer Precondition Pipeline). Every Layer 1 domain is subordinate to it.
- [`LAYER1_ENTITY_COMPLETENESS_CONTRACT.md`](LAYER1_ENTITY_COMPLETENESS_CONTRACT.md) — the Entity Completeness **law** and its current six-dimension implementation.
- [`LAYER1_CONSTITUTION.md`](LAYER1_CONSTITUTION.md) / [`LAYER1_CERTIFICATION.md`](LAYER1_CERTIFICATION.md) — what Layer 1 is/is not, and the certification manifest mechanism (`apps/core/truth/certification.py`, `certify_layers`, CI gate, tags).

---

## The one-paragraph version

Design a domain from the **business questions a customer would naturally ask about it**, not
from the models you happen to have. Make each entity a **CompleteEntity** that answers those
questions from **one deterministic retrieval** (`DomainTruth.describe()` / `describe_one()`),
reading canonical models live — never a precomputed snapshot. Fix the **business vocabulary**
so a word means exactly one thing ("Medicine" = prescription only). Then try to **break it as
the customer would** until you struggle to find another reasonable question. Turn every
production defect into a **permanent regression**. Pass every certification gate. Only then is
the domain part of the frozen foundation — and only then do you start the next one.

---

*Reference implementation: Medication (`apps/health/services/medicine_queries.py`,
`apps/health/services/medicine_domain_truth.py`). Certified 2026-06-30.*
