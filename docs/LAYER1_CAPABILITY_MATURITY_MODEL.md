# Layer 1 Capability Maturity Model

**Status:** Permanent WLJ architecture. Part of the
[Layer 1 Domain Framework](LAYER1_DOMAIN_FRAMEWORK.md).

> The **progression** every canonical domain moves through. Future work advances a domain along
> this path — it does **not** fix isolated bugs and hope the domain matures by accident.

---

## The progression

```
   SYMPTOMS
      │        "supplements show as prescriptions" · "I don't have any current medications"
      │        · "when did I start Metformin errored" — a stream of individual reports
      ▼
   CAPABILITY
      │        name the missing business capability behind the symptoms
      │        ("retrieve a single medication by name", "answer per-category adherence")
      ▼
   ARCHITECTURE
      │        decide the shape that delivers the capability
      │        (DomainTruth facade → deterministic query layer → canonical models; one call)
      ▼
   BUSINESS CONTRACT
      │        define the truth in business terms, in code, visible in the type
      │        (describe()/CompleteEntity, vocabulary pinned to one classifier)
      ▼
   ENTITY COMPLETENESS
      │        the entity answers ALL its natural questions from one retrieval
      │        (six dimensions + open extensions; single-entity + symmetric + combined)
      ▼
   ACCEPTANCE
      │        become the customer, try to break it, freeze every defect as regression
      │        (Smoke → Full → Deep → Beth Production; SAE-disabled; production conversation)
      ▼
   CERTIFICATION
               all gates green → manifest + tag + CI gate → FROZEN foundation
```

Each stage is a different *kind* of work and produces a different artifact. Skipping a stage
doesn't speed things up — it sends you back to SYMPTOMS with a longer report queue.

---

## The stages in detail

### 1. Symptoms

Individual production reports: a wrong answer, a missing answer, a category leak, an error.
Each looks like its own bug. **The trap:** fixing each one where it surfaces. Medication spent
real effort here — three separate adherence calculations, an "I don't have any current
medications" snapshot-staleness failure, supplements appearing as prescriptions — each fixable
in isolation, none of them converging, because they were all symptoms of the same missing
architecture.

**What to do:** collect the symptoms, but resist patching them one at a time. Ask what
*capability's absence* would produce all of them.

### 2. Capability

Name the business capability the symptoms reveal is missing. "Supplements show as
prescriptions" + "medication adherence includes vitamins" + "OTC routes to prescription" are
not three bugs — they are one missing capability: **a canonical business vocabulary with a
single classification authority.** "What's my Metformin dose?" returning `None` +
"How's my Metformin adherence?" returning the overall number are one missing capability:
**single-entity retrieval.**

**What to do:** restate the symptom cluster as a capability sentence. If you can't, you haven't
understood the symptoms yet.

### 3. Architecture

Decide the shape that delivers the capability — before implementing. The Layer 1 shape is
fixed (facade → query layer → canonical models; higher layers make one call; no precompute on
the answer path). Architecture is where you decide *how this capability lives in that shape*,
and where you refuse shortcuts (a snapshot read on the answer path, a second copy of the
adherence math, a category re-classified ad hoc).

**What to do:** design on paper. The [Development Standard](LAYER1_DOMAIN_DEVELOPMENT_STANDARD.md)
§2 is this stage.

### 4. Business Contract

Express the truth as a business contract that is **visible in the type**, not a per-domain dict
of whatever fields were convenient. Medication's pivotal refactor: `profile()` (a software verb
returning an ad-hoc dict) → `describe()` returning `CompleteEntity` (a dataclass whose fields
*are* the business dimensions). The contract became self-policing — you cannot return a
half-described entity without the gap being visible — and identical across every domain, so
there is one shape to learn.

**What to do:** implement `describe()`/`describe_one()` returning `CompleteEntity`; pin the
vocabulary to one classifier; carry freshness + confidence.

### 5. Entity Completeness

Satisfy the law: **the entity answers all its natural questions from one deterministic
retrieval.** This is where single-entity retrieval, symmetric categories, the combined view,
and the execution slices ("what's left today?") get built — because the break attempt showed
that complete *entities* are not the same as a complete *retrieval surface* around them.

**What to do:** map every natural question to a dimension; build the retrieval surface until
none are unanswered. [Entity Completeness Contract](LAYER1_ENTITY_COMPLETENESS_CONTRACT.md) is
the law; Development Standard §3 is the method.

### 6. Acceptance

Validate the product, not the code: the five lenses, the break attempt, SAE-disabled proof, the
conversational threads, and — critically — **freezing every production defect as a permanent
regression.** Stop only when you struggle to find another reasonable business question.

**What to do:** run the [Business Acceptance Playbook](LAYER1_BUSINESS_ACCEPTANCE_PLAYBOOK.md).

### 7. Certification

All gates green → recorded in the manifest, tagged, wired into the CI gate → the domain is
frozen and becomes permanent foundation. Future work builds on it via change control; it never
silently redefines it.

**What to do:** run the [Certification Standard](LAYER1_DOMAIN_CERTIFICATION_STANDARD.md).

---

## The central insight: maturity > passing tests

> **A domain matures by advancing through these stages, not by turning individual tests green.**

Fixing a failing test at the SYMPTOMS stage moves a domain nowhere — the next symptom is
already queued. Advancing the domain one stage retires *entire classes* of symptoms at once.
When Medication reached ENTITY COMPLETENESS, the stream of "it answered the wrong thing"
reports stopped — not because each was fixed, but because the capability that generated them
now existed.

This is why the maturity model is the planning tool, and the bug tracker is not. When a report
arrives, the question is not "how do I make this pass?" but **"what stage is this domain
actually at, and what does advancing it require?"**

---

## Using the model to plan

1. **Locate the domain on the ladder.** Where does the current evidence say it is? (A stream of
   wrong-answer reports = SYMPTOMS/CAPABILITY. Complete entities but missing single-entity
   retrieval = between BUSINESS CONTRACT and ENTITY COMPLETENESS.)
2. **Advance one stage, deliberately.** Produce that stage's artifact (a capability sentence, a
   design note, a `describe()` implementation, a passing acceptance suite).
3. **Never skip.** A domain cannot be certified without entity completeness; it cannot be
   complete without a business contract; the contract cannot be right without the architecture.
4. **Deferred means phased, not maybe.** If a capability is cut from a stage, it gets a phase
   number and an explicit promotion trigger — the architecture stays additive-compatible with
   the full progression. "Maybe someday" is forbidden.

---

*Origin: the Medication journey, where fixing symptoms one at a time never converged, and each
deliberate advance up this ladder retired a whole class of failures — culminating in
certification as the reference Layer 1 implementation.*
