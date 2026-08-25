# WLJ — Medication Instruction Truth: Investigation

**Status:** Part A **SHIPPED** (`3770cc41`) · Part B **APPROVED** · **M1 IMPLEMENTED** (see §B13, as-built)
**Date:** 2026-08-21 · **Origin:** the successful own-record-grounding smoke (`a4995dcd`)
**Governing:** `02_WLJ_CONSTITUTION.md` (I.1, I.2, I.4, IV.2, IV.4) · `docs/WLJ_RUNTIME_TRACE_DEBUGGING.md`

---

## 1. The defect

The smoke that proved own-record grounding also exposed a new trust defect. The CoS correctly retrieved Danny's
Mounjaro record and correctly resolved his next dose — then said:

> *"…it has a **60-minute grace period for a late dose**. … Generally, if you miss a dose, it's advised to take it
> **as soon as possible within the same day**, unless it is very close to your next scheduled dose."*

Two separate errors in one sentence pair:
1. a WLJ **adherence-bookkeeping** number was narrated as if it were **administration guidance**;
2. the drug-specific missed-dose rule was **improvised from general model knowledge** and is not the established
   guidance for this product (per Danny: a ~4-day / 96-hour window, then skip and resume).

**The class:** *personal regimen truth and medication-product instructions are different kinds of evidence.* The CoS
must not retrieve the schedule correctly and then fill the product-instruction gap from improvised knowledge.

---

## 2. PROVEN: what `grace_period_minutes` actually is

**It is adherence-status bookkeeping. It carries zero prescribing meaning.**

| Evidence | Finding |
|---|---|
| `apps/health/models.py:2497` | Declared under the comment `# Grace Period for Missed Doses`, `default=60`, help_text **"Minutes after scheduled time before marking as overdue"** |
| Consumers (only two, non-test) | `IntakeLog.was_taken_on_time` and `IntakeLog.mark_taken` — both do exactly one thing: classify a log as `STATUS_TAKEN` vs `STATUS_LATE` |
| `apps/health/models.py:6018` | **The identical field, identical `default=60`, identical semantics exists on the WORKOUT PLAN model** ("Minutes after preferred_time before marking late") — proving it is a platform-wide lateness-tolerance concept, not a clinical one |
| Clinical use | **None.** No consumer anywhere treats it as dosing guidance |

**The `60` is the untouched platform default** — nobody prescribed it, and it says nothing about Mounjaro.

### Why the model read it as guidance — the exposure defect
`MedicineQueries.describe_one` emits it as a **bare, unitless, unlabelled integer inside a block named `plan`**,
adjacent to `schedule`, `start_date` and `instructions`. Verified by dumping the real serialization
(transaction-rolled-back, dev DB untouched):

```json
"plan": {
  "schedule": ["7:00 AM"],
  "schedule_detail": [{"time": "7:00 AM", "days_of_week": "0", ...}],
  "grace_period_minutes": 60,          ← adherence bookkeeping, presented as part of the PLAN
  "start_date": "2026-01-01",
  "instructions": null,                ← no product instruction truth at all
  "monitoring": null
}
```

Nothing in that payload tells the model the number is bookkeeping. **Mea culpa:** the domain-semantics line added
yesterday (`apps/core/truth/semantics.py:109`) describes it as *"the grace period for a late dose"* — ambiguous
phrasing that made this more likely, not less.

---

## 3. PROVEN: what instruction truth exists today

**None that is authoritative for product administration.**

| Candidate | What it actually is | Verdict |
|---|---|---|
| `Intake.instructions` | Free text, help_text *"Special instructions (e.g., 'take with food', 'avoid grapefruit')"* — **user/prescription-entered regimen notes** | Personal regimen truth. Would never contain a manufacturer missed-dose window. **`null` in the verified serialization** |
| `Intake.monitoring_requirements` | Free-text monitoring notes | Not administration guidance |
| `apps/scan/services/medicine_lookup.py` | RxNav + openFDA **NDC directory** + OpenAI fallback → identity, strength, form, purpose, warnings | **Scan-time IDENTIFICATION only.** Consumed solely by `apps/scan/views.py` for barcode prefill; **not** in the truth catalog, **not** a CoS tool, persists nothing, request-path outbound HTTP |
| DailyMed / package insert / monograph / label endpoint | — | **Does not exist anywhere in the repo** |

**Conclusion: WLJ owns no authoritative drug-product administration instructions.** The model was structurally
forced to improvise. That is not a reasoning defect — there was nothing to reason from.

---

## 4. First failing layer

**Layer 1 (Truth) — two distinct defects.** Reasoning did its job: it retrieved, and it resolved the branch from
real truth. It then hit a hole and filled it.

- **Defect A — semantic mislabelling (no architecture needed).** An adherence-bookkeeping integer is exposed inside
  `plan` with no semantics, inviting the category error. *This is a defect regardless of what we decide about B.*
- **Defect B — missing authority (architecture decision required).** No deterministic source of product
  administration/missed-dose instructions exists.

---

## 5. Options for Defect B (NOT implemented — Danny's call)

| # | Option | Assessment |
|---|---|---|
| 1 | Instruct the model to attribute/hedge product instructions | Cheapest, but only makes wrong drug facts better-labelled. **Does not fix the defect.** |
| 2 | WLJ answers regimen truth; the CoS bounds the *specific* missed-dose rule back to the labelling/pharmacist | Honest and safe, needs no new authority — but partially re-opens the deflection class just closed. A **narrow, bounded** escalation, not the old blanket punt. |
| 3 | **Expose an authoritative product-label surface** (openFDA `/drug/label.json` → `dosage_and_administration`), cached + background-refreshed + attributed, read-only | The only option that actually fixes it. **But it is NOT "expose what exists":** `Intake` stores only a free-text `name` (no NDC, no rxcui), and the wired client calls the **NDC directory**, not the label endpoint. Needs name→product resolution, a new endpoint, and a **new KIND of truth: impersonal REFERENCE truth** (about a product, not a user) — every surface today is user-scoped. **Architecture decision.** |
| 4 | Let the model web-search | Non-deterministic and unattributed; conflicts with the constitution's authoritative-attribution requirement. Not recommended. |

**Constitutional read on Option 3:** WLJ would own *retrieval, caching, provenance and verbatim exposure* of an
authoritative external document; the model still interprets. That is consistent with I.1/I.2/I.4 — provided WLJ
**never paraphrases or summarizes** a label (that would be WLJ generating clinical content). Must be
background/cached — **never request-path outbound HTTP** (`docs/WLJ_REQUEST_PATH_SAFETY.md`).

---

## 6. Recommendation

1. **Fix Defect A now** (small, no decision needed): stop presenting adherence bookkeeping as plan/administration
   truth — move `grace_period_minutes` out of `plan` into the adherence/standing context where it belongs, label it
   for what it is, and correct the ambiguous semantics line. Add a contract test that WLJ never exposes an
   adherence-tolerance field as prescribing guidance.
2. **Decide Defect B.** Recommended sequence: **Option 2 as the immediate safety floor** (bounded, honest, ships
   today), then **Option 3** if Danny wants the CoS to genuinely own this class — opened as its own architecture
   review, since it introduces impersonal reference truth.

**STOPPED here per instruction. No code changed, no real-model call spent.**

---

## 7. Open item for Danny (one glance)

The verified serialization shows `instructions: null` for a blank record, and the smoke quoted no instruction text —
so Danny's Mounjaro record almost certainly has empty `instructions`. **Not proven:** the audit ledger stores
envelope metadata only (by design), so the stored value cannot be read from it. Confirm in the app if it matters —
though the class holds either way, since that field is regimen notes, not manufacturer labelling.

---

# PART B — Authoritative Medication Reference Truth: architecture recommendation

**Status:** DESIGN ONLY · **NOT IMPLEMENTED** · awaiting Danny's decision
**Date:** 2026-08-22 · Part A (the semantic-category fix) shipped separately in `3770cc41`.

## B1. The requirement, stated once

> The CoS sometimes needs **authoritative impersonal reference truth** in addition to the user's personal
> deterministic truth.

Scoped for this milestone to **medication product information only**. The design must not *prevent* later
generalization, but nothing here builds a universal reference-truth platform.

Three concepts stay explicitly separate, end to end:

| # | Kind | Owner | Scope | Example |
|---|---|---|---|---|
| 1 | **Personal medication truth** | `medicine` domain (exists, certified) | user-scoped | *Danny takes Mounjaro, weekly, 7:00 AM Sunday, last taken …* |
| 2 | **Authoritative reference truth** | **new** `medication_reference` domain | **impersonal** — about a PRODUCT | *"If a dose is missed, administer within N days …"* (verbatim, with provenance) |
| 3 | **Reasoning** | the conversational model | — | combines 1 + 2 to answer *"can I take it tonight?"* |

**WLJ must never precompute the medical judgment.** It supplies #1 and #2; the model does #3.

## B2. Source comparison — PROVEN against the live APIs (public data only; no user data transmitted)

| Source | Authoritative for | Not authoritative for | Evidence gathered |
|---|---|---|---|
| **RxNorm / RxNav** (NLM) | **Drug IDENTITY** — normalized concepts (RXCUI), ingredient/brand/clinical-drug relationships, NDC↔RXCUI | Label text. Any clinical instruction | `rxcui.json?name=Ozempic` → `1991307`. **Also returns `4419` for "fish oil"** — a successful RXCUI does **not** imply a drug label exists |
| **DailyMed** (NLM/NIH) | **LABEL CONTENT** — the official repository of FDA-approved SPL documents; `setid` + `spl_version` + `published_date` | Identity normalization | `spls.json?drug_name=Ozempic` → **7 SPLs**, incl. a repackager and the manufacturer of record; supports `rxcui=` |
| **openFDA `/drug/label.json`** | Convenient **JSON index over the same SPL data**; `openfda` block carries rxcui/NDC/brand/generic | Being the source of record; its own terms disclaim clinical decision-making | `brand_name:"Ozempic"` → **3 SPLs**, distinct `set_id`/`version`/`effective_time`; `dosage_and_administration` present and contains the exact fact class needed |

**Recommendation: use both, for different jobs.**
- **RxNorm/RxNav = the identity authority.**
- **DailyMed = the authoritative source of record for label text** (NLM's official SPL repository, versioned).
- **openFDA = a convenience index** for search/section extraction — never cited as the authority, and never the only
  source relied upon. Cite DailyMed `setid` + `spl_version` as provenance.

## B3. The identity chain — PROVEN NECESSARY, because name search attaches the WRONG label

The user's instruction was to prove this rather than assume it. **Name search is not merely imprecise — it is
actively dangerous:**

- **DailyMed's top name-match for "Ozempic" is an SPL titled `OZEMPIC (ORAL SEMAGLUTIDE) TABLET RYBELSUS (ORAL
  SEMAGLUTIDE) TABLET`** — an **oral tablet**, a different product and a different administration route from the
  Ozempic **injection**. A naive first-hit implementation would attach tablet instructions to an injectable.
- **One brand returns many SPLs** (openFDA 3, DailyMed 7), spanning **repackagers** (`A-S MEDICATION SOLUTIONS`) and
  the **manufacturer of record** (`NOVO NORDISK`), with different `spl_version` and `published_date`.
- **A multi-source generic is unresolvable by name: `openfda.generic_name:"IBUPROFEN"` → 1,185 distinct SPLs.**
- **A supplement has no drug label at all:** `fish oil` → openFDA `NOT_FOUND`, while RxNav still returns an RXCUI.

### Proposed chain (every step must succeed, or the whole thing fails closed)

```
Intake.name (free text)
  → RxNav approximate/exact match ────────────────► RXCUI            [identity gate]
  → RXCUI + dosage form/route ────────────────────► candidate SPLs   [DailyMed rxcui= / openFDA]
  → filter: labeler = manufacturer of record,
            route/dosage form consistent          ► ONE SPL lineage  [product gate]
  → newest spl_version for that setid ────────────► THE label        [version gate]
  → extract `dosage_and_administration` VERBATIM  ► reference fact   [content gate]
```

### Is brand/generic identity sufficient, or is NDC/product-level required?
**Neither name level is sufficient on its own.** The true unit of "a label" is the **SPL `setid`**. Practically:

- **Brand-name, single-manufacturer products (e.g. Mounjaro): resolvable** — after filtering to the
  manufacturer-of-record SPL and the correct dosage form. **This covers the demonstrated failure case.**
- **Multi-source generics (e.g. metformin ER): NOT resolvable from a name.** 1,185 candidates cannot be verified to
  agree. These must **fail closed** until the user's actual product is known.
- The bridge for generics later is **NDC**, which the existing **scan/barcode path already reads** — a legitimate
  reuse, not new machinery.

### Identifiers to persist (on `Intake`, all nullable, never guessed)
`reference_rxcui` · `reference_spl_setid` · `reference_identity_confidence` (`exact` | `ambiguous` | `none`) ·
`reference_resolved_at`. Absent = unresolved, and unresolved **never** falls back to a name lookup at answer time.

## B4. Ownership boundary — one authority, no shadow

- **New domain `medication_reference`**, one entity `product_label`, with **exactly one** deterministic producer
  (Article III.1). Registered in the **existing** truth catalog.
- **Exposed through the EXISTING `get_entity` tool** — `get_entity(domain='medication_reference', name=…)`. **No new
  tool**, no parallel retrieval path, the **existing envelope** (`apps/core/truth/envelope.py`, freshness,
  confidence) — so the certified Retrieval Platform gains a domain, not a rival.
- **The `medicine` domain must NEVER serve label facts** and the reference domain must never serve personal facts.
  This is precisely why the reference block is a separate domain rather than a `reference` key bolted onto the
  medication entity — the latter would make `medicine` a second, informal label authority.
- **WLJ exposes label text VERBATIM.** No summarizing, paraphrasing, ranking, or "what this means for you." The
  moment WLJ condenses a label it is generating clinical content.

## B5. Storage, freshness, provenance

Canonical impersonal record — **no user FK** (the architectural novelty):

```
MedicationProductLabel
  spl_setid (unique)      rxcui[]            brand_name  generic_name
  dosage_form  route      labeler
  dosage_and_administration_text   (VERBATIM)
  spl_version   effective_time     published_date
  source ("dailymed")     source_url         retrieved_at
  content_hash            status (active | superseded | withdrawn)
```

Every fact leaves WLJ inside the standard envelope carrying **source · source_url · spl_version · effective_time ·
retrieved_at · freshness**. A label older than its refresh window is returned **with its date stated**, never as
"current".

**Refresh without touching the request path** (`docs/WLJ_REQUEST_PATH_SAFETY.md`):
- A **Celery Beat crontab** job (crontab, **not** a long interval — Railway's ephemeral filesystem resets
  `PersistentScheduler` on restart and starves long-interval tasks).
- Refresh scope = only products at least one user actually takes. Never the whole catalog.
- **The truth tool performs no outbound HTTP, ever.** It reads the local row. Cache miss → return `not_available`
  and `safe_enqueue` a background resolve.

## B6. Retrieval + discovery flow

1. User asks a question whose answer depends on product instructions.
2. The model's **second internal question** (`c937ee34`) fires: *does part of this depend on a fact WLJ may hold?*
3. It retrieves **personal** truth: `get_entity(domain='medicine', name=…)`.
4. That entity's advertisement (Part A) currently states *"WLJ holds no manufacturer or product labelling."*
   **On implementation this line changes** to point at the reference domain — that is the discovery mechanism, and
   it reuses the capability-index pattern already proven to work.
5. It retrieves **reference** truth: `get_entity(domain='medication_reference', …)`.
6. The **model** combines 1 + 2 and answers, attributing the label.

## B7. Failure behaviour — fail closed, always

| Condition | Returned | CoS behaviour |
|---|---|---|
| Identity ambiguous (generic, multiple labelers disagreeing) | `status: identity_ambiguous` + why | Say the specific product is needed; offer to scan/confirm it. **Never** attach a candidate label |
| No label exists (supplement, foreign product) | `status: no_label_available` | Say WLJ has no labelling for it |
| Not yet fetched | `status: pending` + background fetch enqueued | Answer from personal truth; say product instructions aren't loaded yet |
| Stale beyond window | returned **with** `effective_time` + staleness | Attribute and date it |

In every failure the CoS falls back to the **bounded** deferral (personal truth + "the specific product instruction
is what I don't have") — never the blanket punt eliminated in `e360a8e6`.

## B8. Licensing, retention, update

- SPL/DailyMed/openFDA/RxNorm are **US Government public-domain** data — storing excerpts is permissible.
- **openFDA's own terms disclaim clinical decision-making** → cite **DailyMed** as the source of record.
- The real risk is **staleness**, not licensing: labels change. Mitigated by `spl_version` + `effective_time` +
  scoped refresh + never presenting an undated label as current.
- Rate limits are modest; an API key and scoped refresh are sufficient.

## B9. Reuse of the existing scan machinery

`apps/scan/services/medicine_lookup.py` should **remain an identification consumer** and is **not** promoted to a
truth authority. Its RxNav name→RXCUI call is worth extracting into a shared **background-only** client. Two things
must **not** be inherited: its **request-path outbound HTTP**, and its **OpenAI fallback** — a model guess is the
exact opposite of authoritative and would reintroduce this defect at the source. Its **NDC barcode reading** is the
natural future bridge for generic identity (B3).

## B10. Constitutional assessment — NO Review required (one item for Danny to note)

Evaluated explicitly, not assumed:

| Article | Assessment |
|---|---|
| **I.1** WLJ owns deterministic truth | ✅ A fetched, versioned, provenance-bearing document is deterministic truth — not a cache of the model's beliefs. **Note below.** |
| **I.2** model owns reasoning | ✅ Strengthened. WLJ never interprets the label; it removes the improvisation that caused this defect |
| **I.3** WLJ owns calculations | n/a |
| **I.4** model owns interpretation/judgment | ✅ **conditional on verbatim exposure.** WLJ must never summarize a label or derive "so you may take it" |
| **I.6** WLJ validates truth | ✅ version/effective-date/completeness validated; fail-closed |
| **I.8** provider-agnostic | n/a |
| **III.1** one authority per domain | ✅ one producer; and `medicine` is explicitly barred from serving label facts (B4) |
| **III.2** one execution decision authority | n/a |

**No Article is changed, weakened, or inverted → no Constitutional Review is required**, consistent with Danny's
hypothesis.

**The one thing worth his explicit note:** Article I.1's gloss reads *"the canonical facts of **a person's life**."*
Reference truth is impersonal — about a product, not a person. That is a **scope extension, not a contradiction**,
and it makes `medication_reference` the **first impersonal truth domain** in WLJ. Nothing is weakened, so this is an
**ADR + Danny's explicit go**, not a Review — but he may reasonably want it recorded in the Amendment Log as a
clarification of I.1's scope.

## B11. Smallest milestone that solves the demonstrated class

**M1 — one domain, one entity, ONE fact, brand-resolvable products only.**
1. `MedicationProductLabel` model + the `medication_reference` domain truth object (one producer, catalog-registered).
2. Identity resolver (RxNav → DailyMed by RXCUI → manufacturer-of-record + dosage-form filter → newest version),
   **fail-closed**, background-only. Persist the four `reference_*` identifiers on `Intake`.
3. **Only `dosage_and_administration`, verbatim, with provenance.** No other section.
4. Celery **crontab** refresh scoped to products users take.
5. Expose via the **existing** `get_entity`; update the `medicine` advertisement to point at it.
6. Contract tests: fail-closed on ambiguity; never a name-only match; verbatim (no summarization); no request-path
   HTTP; `medicine` never serves label facts.

**Explicitly NOT in M1:** other label sections, interaction checking, generics via NDC, any UI, any generalization
to non-medication reference truth. **M1 covers the demonstrated case** (Mounjaro is brand-resolvable) and correctly
fails closed on Danny's generic metformin.

## B12. Risks and open decisions for Danny

1. **Coverage is partial by design.** M1 answers for brand products and fails closed on multi-source generics. Is a
   *partially* capable CoS acceptable here, or should generics-via-NDC be in scope from the start?
2. **First impersonal truth domain** (B10) — confirm ADR-and-go rather than an Amendment Log entry.
3. **Verbatim-only is a product constraint.** Label text is long and clinical. The **model** may quote/condense it in
   its answer; **WLJ** may not. Confirm that boundary.
4. **Third-party dependency + staleness.** NLM/FDA availability and label churn become a (background, non-blocking)
   dependency.
5. **Repackager vs manufacturer selection** needs a deterministic, defensible rule — this is where a wrong label
   would most plausibly slip in.
6. **Scope discipline.** Nothing here should drift toward a general drug-knowledge base or interaction checking.

**STOPPED per instruction. Nothing in Part B implemented. No real-model call spent on Part B.**


---

# B13. M1 AS-BUILT (implemented)

Approved scope: **brand-resolvable products only; fail closed otherwise.** Generic/NDC identity is M2 and was
deliberately not built. Recorded here as the durable architectural decision — **not** a Constitutional amendment.

**Governing interpretation (approved):** *WLJ may own deterministic reference truth that materially supports
reasoning over a person's life even when the referenced fact itself is impersonal. The model still owns
interpretation and judgment.* Implementation held to this without weakening any Article — no Review required.

## Authority model as built

| Concern | Where it lives |
|---|---|
| Personal regimen truth | `medicine` domain — `health.Intake` (unchanged) |
| **Authoritative product truth** | **`medication_reference` domain — `medical.MedicationProductLabel`** (no user FK) |
| Identity bridge | four `reference_*` fields on `health.Intake` (a pointer, never label content) |
| Reasoning | the conversational model, over both |

`medical.MedicationProductLabel` is impersonal by construction — a contract test asserts no `user`/`owner`/`intake`
field exists. The two domains are separate **precisely so `medicine` can never become a second, informal label
authority** (III.1); contract tests assert leakage in **both** directions.

## Identity chain as built (`apps/medical/services/medication_reference.py`)

```
name → RxNav rxcui  ─ >1 concept → AMBIGUOUS ─ TTY ∉ {BN} → UNSUPPORTED (generic)
     → DailyMed spls.json?rxcui=…   ─ none → NO_LABEL
     → highest spl_version           ─ 2 labelers tied → AMBIGUOUS
     → openFDA text for THAT set_id  ─ none/empty → NO_LABEL
     → persist verbatim + provenance
```

**Never a name query for the document, and never a title match** — a contract test spies the URLs and asserts every
SPL call carries `rxcui=` and none carries `drug_name=`. This is the gate that prevents the proven wrong-product
failure (DailyMed's top *name* match for "Ozempic" is an **oral tablet** SPL). Identity success and label existence
are separately gated (proven: "fish oil" → RXCUI 4419, no label).

## Provenance as built
`source=dailymed` (identity/version authority) · `source_url` · `spl_setid` · `spl_version` · `effective_time` ·
`published_date` · `labeler` · **`content_source`** (where the parsed text came from — deliberately a separate field
so the identity authority and the text retrieval are never conflated) · `retrieved_at` · `content_hash`.

## Verbatim, never interpreted
`dosage_and_administration` is stored and exposed byte-identical to the source (contract-tested), flagged
`verbatim: true`, and accompanied by *"WLJ does not interpret, summarize or condense it — apply it to the person's
situation yourself, and attribute it."* A contract test greps the producer for authored clinical phrasing.

## Failure behaviour
A refusal returns an **entity**, not nothing — status `unavailable` with the reason (`unsupported` / `ambiguous` /
`no_label`) and the instruction *"do NOT supply the product's instructions from general knowledge and present them
as authoritative."* Returning an explicit refusal rather than silence is what stops the model quietly substituting
its own knowledge.

## Request-path safety
The truth surface performs **one indexed DB read** and no outbound HTTP — asserted by a test that patches
`urllib.request.urlopen` to raise while calling `get_entity`. Resolution/refresh runs in
`medical.refresh_medication_reference_labels`, scheduled by **crontab** (05:00 UTC — an interval would be starved by
Railway's ephemeral filesystem resetting `PersistentScheduler`), scoped to medications users actually take, capped
per run, and re-resolving no more often than every 30 days.

## Exposure and discovery
**No new tool.** The domain registers in the existing truth catalog, so the existing `get_entity` tool's `domain`
enum picks it up automatically (contract-tested, including that no `get_medication_reference`-style tool exists).
`domain_semantics` advertises the domain, its verbatim/impersonal nature, its partial coverage and honest refusal;
and the `medicine` advertisement now names `medication_reference` and says **"retrieve BOTH and reason over them
together."** No phrase routing, no drug-specific routing, no `tool_choice`, no evidence planning — the
earliest-decision grounding anchor (`c937ee34`) is untouched and does the work.

## Constitutional assessment (re-confirmed against the built code)
I.1 ✅ deterministic, provenance-bearing, not a cache of model belief · I.2 ✅ WLJ never reasons over the label ·
I.4 ✅ verbatim only, contract-enforced · I.6 ✅ fail-closed validation with recorded reasons · III.1 ✅ one producer,
bidirectional leakage tests. **No Article changed or weakened; no Constitutional Review; no Amendment Log entry**
(per Danny's governance instruction).

## Explicitly NOT built (M2+)
Generic/NDC-level identity · other label sections · interaction checking · any UI · any generalization beyond
medication reference truth.
