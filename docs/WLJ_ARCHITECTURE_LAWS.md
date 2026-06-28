# WLJ Architecture Laws — The Platform Constitution

> **This is the highest-order, platform-wide governing document for Whole Life
> Journey.** It is not Beth-specific. Every subsystem that ingests data or answers a
> personal question — Chat/Beth, Health, Faith, Purpose, Relationships, Finance,
> Productivity, Dashboards, Physician Mode, Notifications, Action Center, the AI
> State/Signal/Event engines, Retrieval, Caching, and every future domain — is
> subordinate to these Laws. Where any other document
> (`BETH_ARCHITECTURAL_PRINCIPLES.md`, `MEDICATION_INTELLIGENCE_CANON.md`,
> `INTELLIGENCE_ARCHITECTURE.md`, a ticket, or a convenience) conflicts with a Law
> here, the Law wins. Changes require explicit owner approval.
>
> **Status:** Canonical. **Established:** 2026-06-28. **Amended:** 2026-06-28
> (added **Law 0 — Intent Before Retrieval** as the first Law).

---

## Preamble — The Ordering Principle

WLJ rests on one sentence: **WLJ owns truth; the LLM owns reasoning.** Production
revealed a deeper deficiency beneath several "isolated bugs":

- *"Did I workout today?"* answered about **sleep** — the wrong question.
- Sleep reported as **5.3h** then **6.9h** a minute later — stale, unstable truth.
- *"How many steps yesterday?"* → **"assistant unavailable"** — a deterministic
  lookup hiding behind an AI failure.
- *"List each medicine and what each is for"* forced through **one reasoning prompt**
  instead of a retrieve→enumerate→enrich→assemble workflow.

These are one root cause:

> **WLJ reasons *before* it validates intent, freshness, completeness, confidence,
> and orchestration strategy. That order is fundamentally incorrect.**

These Laws fix the order. **Validation precedes reasoning, and intent precedes
everything.** Reasoning/narration is the **last** step, never the first. Reasoning
over an unvalidated question, or unvalidated data, is the defect class; these Laws
make it structurally impossible.

### The Answer Precondition Pipeline (the unifying contract)

Every personal answer, in every subsystem, must pass through this order. No subsystem
may bypass it. Reasoning/narration is the **last** step.

```
Question
  0. INTENT      → what EXACTLY is being asked? (deterministic-first)   (Law 0)
  1. SCOPE       → retrieve ONLY the domains that question requires      (Law 0)
  2. FRESHNESS   → are those datasets current enough? (per-dataset as-of)(Law 1)
  3. COMPLETENESS→ is required data present, not partial/pending?        (Law 1,2)
  4. CONFIDENCE  → compose deterministic confidence (freshness +
                   completeness + source + sync + evidence)             (Law 2)
        └─ if insufficient → answer honestly about WHAT IS MISSING, STOP.
  5. STRATEGY    → retrieval | enumeration+enrichment | reasoning?       (Law 3)
  6. RETRIEVE    → deterministic answer first; retrieval failure is
                   reported as retrieval failure, never AI-unavailable   (Law 4)
  7. STABILITY   → identical question + unchanged source ⇒ identical
                   factual answer                                        (Law 5)
  8. REASON / NARRATE  ← only now, over the validated, stable, composed truth
```

**Questions determine retrieval. Retrieval never determines the answer.**

---

## Part I — The Foundational Invariants (restated; this is their canonical home)

These already governed WLJ implicitly. Recorded here so the platform has one
constitution. (F-series, to keep the numbered **Laws** below distinct.)

- **F1 — Truth/Reasoning Separation.** WLJ owns truth; the LLM owns reasoning. The
  LLM never invents personal facts, numbers, or status.
- **F2 — LLM-Last.** Raw data → deterministic signals/state → composed state → CoS →
  narration. The LLM touches only the last narration step (or a bounded, non-personal
  leaf such as general education).
- **F3 — Framework-First.** Capabilities are added by extending a small set of
  contracts, never by special-casing a question. The agentic tool loop is the demoted
  fallback, not the primary path.
- **F4 — Single Source of Truth (Domain Truth Contracts).** One canonical query per
  concept (`apps/{domain}/services/{domain}_queries.py`); UI, SAE, CoS, engines read
  the same contract.
- **F5 — Never Compute on the Request Path.** Heavy analytics run in background
  workers; request paths read pre-computed snapshots, else return "pending."
- **F6 — No Silent Failures.** Critical paths log loudly and degrade honestly; never
  `except: pass` on intent/execution/safety.
- **F7 — Visual Truth Contract.** Only actual completion may visually resemble
  completion. (See `WLJ_VISUAL_TRUTH_CONTRACT.md`.)
- **F8 — Beth Consumes Briefings, Not Signals.** Intelligence produces composed,
  deterministic state objects (verdict already inside) for Beth to narrate over.

---

## Part II — The Operational Laws

### Law 0 — Intent Before Retrieval  *(the first Law)*

**Before any retrieval, reasoning, or narration, determine exactly what the user is
asking. Retrieve only the domains required to answer that question. Never answer a
different question simply because other data is available.**

- Intent classification runs **first** and is **deterministic-first** (the FACT lane
  / intent registry), before any data fetch. Ambiguity is clarified, not guessed.
- Scope is derived from intent: *"Did I workout today?"* → required domain
  **Workout**, not Sleep, Weight, Glucose, or Calendar.
- The anti-pattern this forbids: **available-data-drives-the-answer** — answering
  about whatever state happens to be loaded (e.g. the standing context) instead of
  what was asked. Questions determine retrieval; retrieval never determines the
  answer.
- A correctly-scoped answer that lacks data defers to Law 1 (say what's missing for
  *that* domain) — it does not substitute a different domain's data.

*Evidence: Example 1 — "Did I workout today?" answered about sleep.*

### Law 1 — Data Freshness Before Reasoning

**Before answering any personal question, determine which datasets it requires and
whether they are current enough. If required data is stale or missing, do not answer
as though it were current — state exactly what is missing.**

- Every dataset that backs a personal answer carries an **as-of timestamp** and a
  **freshness verdict** (`fresh | stale | pending | absent`) relative to the
  question's time window. Freshness is a deterministic property of the data.
- "Today's sleep" before HealthKit has synced is **pending** — not 0, not yesterday's
  value. The honest answer: *"I don't have today's sleep yet — Apple Health hasn't
  synced."*
- Platform-wide freshness sources: Apple Health, Dexcom/CGM, workouts, journal
  processing, finance/payroll, capture, labs.

*Evidence: Example 2 — stale sleep presented as current.*

### Law 2 — Confidence Before Conversation

**Every personal answer carries deterministic confidence — composed from freshness,
completeness, source quality, synchronization, and evidence. If confidence is
insufficient, say so. Never replace uncertainty with confidence.**

- Confidence is **composed deterministically** (per F8), part of the state object the
  surface consumes — never narrated into existence by the LLM.
- Insufficient confidence is a first-class, honest answer ("I have partial data…"),
  not fabricated certainty and not silence.

*Evidence: Example 2 — confident delivery of low-confidence data.*

### Law 3 — Orchestration Before Reasoning

**Questions that naturally decompose into workflows must be orchestrated, not
collapsed into a single reasoning prompt. Retrieve → Enumerate → General-Knowledge
Enrichment → Assemble → Narrate is a first-class, platform-wide orchestration
pattern.**

- Canonical shape: **`(WLJ deterministic set) × (bounded, cached, non-personal
  per-item enrichment) → deterministic assembly → narrate`.**
- Non-personal enrichment is cached globally and reused — memoization of general
  knowledge, **not** a curated reference database.
- Generalize beyond medication: **supplements, labs, conditions, goals, financial
  accounts, projects, documents** — any "enumerate a personal set, enrich each item"
  question.
- The single-call agentic tool loop remains the *fallback*, never the chosen strategy
  for a workflow-shaped question (reinforces F3).

*Evidence: Example 4 — a retrieve/enumerate/enrich/assemble question forced through
one reasoning prompt.*

### Law 4 — Deterministic Retrieval Never Falls Back to AI Failure

**If a deterministic answer exists, return it. If retrieval fails, report the
retrieval failure. Never answer a deterministic question with "assistant
unavailable."**

- "How many steps yesterday?" is a deterministic lookup; its outcomes are *retrieved
  value*, *named retrieval error*, or *not-yet-synced* (Law 1) — never the LLM-outage
  message.
- The LLM-unavailable / "I couldn't pull that together" path is reserved for genuine
  LLM-dependent work (general education, narration) and may **never** be reached for a
  question a deterministic contract can answer.
- Deterministic fast paths must not route through, or share a failure mode with, the
  LLM path.

*Evidence: Example 3 — deterministic step count returned "assistant unavailable."*

### Law 5 — Stable Truth

**A repeated identical question, with no change in the underlying source data, must
produce an identical factual answer. Truth changes only when evidence changes.**

- The same user never receives 5.3h then 6.9h of sleep a minute apart unless new
  source data actually arrived. Aggregation is **deterministic**; caches are **keyed
  on a source-data version/as-of** and invalidated **only** on real data change.
- If two sources disagree, the contract picks one deterministically and records the
  choice; it does not flip between them.
- Stability is verifiable: same inputs ⇒ same output, provable by test.

*Evidence: Example 2 — the same morning question produced two different sleep values
one minute apart.*

---

## Part III — Affected Subsystems

Platform-wide. Every subsystem that ingests data or answers a personal question must
eventually comply:

| Subsystem | Path(s) | Obligation introduced |
|---|---|---|
| **Chat / CoS (Beth)** | `apps/ai/chatgpt_cos/` | Run the full Answer Precondition Pipeline; intent-first scoping (Law 0); Enumeration+Enrichment lane (Law 3). |
| **Health** | `apps/health`, `apps/medical` | Freshness sources (sleep/steps/glucose/labs); deterministic aggregation (Laws 1,5). |
| **Faith / Purpose / Relationships / Productivity** | `apps/faith`, `apps/purpose`, `apps/life`, tasks | Intent scoping + freshness/confidence per domain (Laws 0,1,2). |
| **Finance** | `apps/finance`, `apps/billing` | Freshness ("payroll not refreshed"); enumeration of accounts (Laws 1,3). |
| **Dashboards / Action Center / Physician Mode / Exports** | templates, `apps/core` | Render freshness/confidence; honor Visual Truth (Laws 1,2,F7). |
| **Notifications / proactive** | `apps/ai/proactive_*`, `apps/sms` | Never push stale-as-current; confidence-gated (Laws 1,2,5). |
| **AI State Engine (SAE)** | `apps/core/ai_state/` | Carry a **confidence envelope** (freshness+completeness+source+sync+evidence) per fact/domain (Law 2). |
| **Signal Engine / Event Engine** | `apps/core/ai_*`, PIE/PRIE/CDCE | Tag composed state with freshness/confidence; no stale signals (Laws 1,2,F8). |
| **Domain Truth Contracts** | `apps/{domain}/services/{domain}_queries.py` | Expose freshness/completeness + deterministic aggregation (Laws 0,1,5). |
| **Foundational Facts / deterministic fast path** | `apps/ai/chatgpt_cos/foundational_facts.py`, `apps/ai/cos_services/health_facts.py` | Intent-scoped retrieval; freshness check; never share the LLM-failure path (Laws 0,1,4). |
| **Retrieval** | reasoning `retrieve_truth`, tool dispatch | Scope to intent's domains only (Law 0); deterministic failure reporting (Law 4). |
| **Caching** | `wlj:*` keys | Keys derived from source-data version/as-of; invalidate only on real change (Law 5). |
| **General-knowledge enrichment cache** | new, non-personal | Global per-entity education cache, lazy + background-warmed (Laws 3, F5). |
| **Future domains** | — | Configured within these Laws, never architected around them. |

---

## Part IV — Migration Strategy

Additive and phased; the platform stays answerable throughout.

**Breaking changes (intended, user-visible — gate with Beth Golden Behaviors +
production validation):**
- Wrong-domain answers stop: an out-of-scope question is answered about the asked
  domain or honestly deferred — never substituted with available data (Law 0).
- Stale/pending data yields an honest "not yet synced" answer instead of a confident
  stale number (Law 1).
- Deterministic questions no longer surface "assistant unavailable" (Law 4).
- Medication-education-class questions answered via orchestration, not the tool loop
  (Law 3). Output equal or better.

**Non-breaking changes (additive — the majority):**
- Intent→scope contract, freshness/confidence value objects and envelope (new optional
  fields). Truth Contracts returning extra metadata (existing callers unaffected). SAE
  attaching confidence (read-only). New Enumeration+Enrichment lane + enrichment cache
  (new path; tool loop remains). Stability tests, freshness telemetry.
- **No schema migration is mandated** by the Laws; freshness sources largely already
  exist. Any later schema addition is a normal additive migration.

**Rollout phases:**
1. Intent→scope contract at the answer boundary (deterministic intent precedes any
   fetch).
2. Freshness primitive (`AsOf`/`Freshness` value object) + confidence envelope shape.
3. Domain Truth Contracts expose `(value, as_of, freshness, completeness)`.
4. SAE carries the envelope; surfaces render it.
5. Decouple deterministic paths from the LLM failure path (Law 4); stability hardening
   (deterministic aggregation + source-versioned cache keys, Law 5).
6. Enumeration+Enrichment lane + non-personal cache; generalize across domains.
7. Per-domain rollout: Health first (the evidence), then Finance, Faith, Purpose,
   Relationships, Productivity — same contracts, no rewrite.

---

## Part V — Recommended Implementation Order

**Trust is established before intelligence:**

1. **Law 0 — Intent Before Retrieval** — *first.* If Beth answers the wrong question,
   nothing downstream matters. Deterministic intent→scope at the answer boundary.
   Fixes Example 1.
2. **Law 4 — Deterministic Retrieval ≠ AI Failure** — decouple deterministic paths
   from the LLM failure path; smallest surface, high trust. Fixes Example 3.
3. **Law 1 — Data Freshness** — freshness primitive + Health domain. Fixes Example 2
   (no more stale-as-current).
4. **Law 2 — Confidence** — compose the envelope on top of freshness; surface it.
5. **Law 3 — Orchestration** — Enumeration+Enrichment lane + non-personal cache;
   medication education first, then generalize. Fixes Example 4 as a *class*.

(Law 5 — Stable Truth — is delivered alongside Laws 1/4 as the deterministic
aggregation + source-versioned caching that those phases install.)

Rationale: **right question (0) → honest deterministic answers (4) → fresh (1) →
confidence-aware (2) → orchestrated intelligence (3).** Trust before intelligence.

---

## Part VI — Success Criteria

After adoption, verifiably:
- Beth never answers the wrong question (Law 0).
- Beth never silently uses stale personal data (Law 1).
- Beth always knows when she does not know (Law 2).
- Deterministic retrieval never hides behind an AI failure (Law 4).
- Enumeration-style questions are deterministic orchestration workflows (Law 3).
- Identical questions over unchanged data return identical facts (Law 5).
- Every future subsystem — not just Beth — follows the same Answer Precondition
  Pipeline before any reasoning or narration.

---

## Part VII — Governance & Cross-References

- **Subordinate documents that defer here:** `BETH_ARCHITECTURAL_PRINCIPLES.md` (CoS
  Constitution), `MEDICATION_INTELLIGENCE_CANON.md` (domain Canon),
  `INTELLIGENCE_ARCHITECTURE.md` / `BETH_DOMAIN_REASONING_FRAMEWORK.md` (reasoning),
  `CLAUDE.md` (engineering rules).
- **Enforcement:** new code on any answer path must satisfy the Answer Precondition
  Pipeline; reviews check intent→scope, freshness, confidence, and orchestration
  *before* reasoning.
- **These are platform rules, not Beth behavior** — the constitutional foundation for
  every future WLJ capability.

*Last updated: 2026-06-28 (added Law 0 — Intent Before Retrieval).*
