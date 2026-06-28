# WLJ Architecture Laws — The Platform Constitution

> **This is the highest-order, platform-wide governing document for Whole Life
> Journey.** It is not Beth-specific. Every subsystem that ingests data or answers
> a personal question — CoS/Beth, dashboards, the Action Center, mobile/API,
> engines, exports — is subordinate to these Laws. Where any other document
> (`BETH_ARCHITECTURAL_PRINCIPLES.md`, `MEDICATION_INTELLIGENCE_CANON.md`,
> `INTELLIGENCE_ARCHITECTURE.md`, a ticket, or a convenience) conflicts with a Law
> here, the Law wins. Changes require explicit owner approval.
>
> **Status:** Canonical. **Established:** 2026-06-28 (promoted from production
> evidence in the Medication Intelligence and morning-briefing incidents).

---

## Preamble — The Ordering Principle

WLJ rests on one sentence: **WLJ owns truth; the LLM owns reasoning.** Production
revealed a deeper deficiency beneath several "isolated bugs" (sleep 5.3h then 6.9h a
minute later; stale data presented as current; "assistant unavailable" for a
deterministic step count; a retrieve→enrich→assemble question forced through one
reasoning prompt). They are one root cause:

> **WLJ reasons *before* it validates freshness, completeness, and orchestration
> strategy. That order is backwards.**

These Laws fix the order. **Validation precedes reasoning.** Before any reasoning
or narration begins, a subsystem must establish that its inputs are *fresh enough*,
*complete enough*, *retrieved deterministically*, and *orchestrated in the right
shape*. Reasoning over unvalidated truth is the defect class; these Laws make it
structurally impossible.

### The Answer Precondition Pipeline (the unifying contract)

Every personal answer, in every subsystem, must pass through this order. Reasoning/
narration is the **last** step, never the first.

```
Question
  1. SCOPE       → which datasets does this answer require?           (Law 1)
  2. FRESHNESS   → are they current enough? (per-dataset as-of)        (Law 1)
  3. COMPLETENESS→ is required data present, not partial/pending?      (Law 1,2)
  4. CONFIDENCE  → compose deterministic confidence (freshness +
                   completeness + source + sync + evidence)            (Law 2)
        └─ if insufficient → answer honestly about WHAT IS MISSING, STOP.
  5. STRATEGY    → retrieval | enumeration+enrichment | reasoning?     (Law 3)
  6. RETRIEVE    → deterministic answer first; retrieval failure is
                   reported as retrieval failure, never AI-unavailable (Law 4)
  7. STABILITY   → identical question + unchanged source ⇒ identical
                   factual answer                                       (Law 5)
  8. REASON/NARRATE  ← only now, over validated, stable, composed truth
```

---

## Part I — The Pre-Existing Foundational Laws (restated; this is their canonical home)

These already governed WLJ implicitly. They are recorded here so the platform has
one constitution.

- **L0 — Truth/Reasoning Separation.** WLJ owns truth; the LLM owns reasoning. The
  LLM never invents personal facts, numbers, or status.
- **L0.1 — LLM-Last.** Raw data → deterministic signals/state → composed state →
  CoS → narration. The LLM touches only the last, narration step (or a bounded,
  non-personal leaf such as general education).
- **L0.2 — Framework-First.** Capabilities are added by extending a small set of
  contracts, never by special-casing a question. The agentic tool loop is the
  demoted fallback, not the primary path.
- **L0.3 — Single Source of Truth (Domain Truth Contracts).** One canonical query
  per concept (`apps/{domain}/services/{domain}_queries.py`); UI, SAE, CoS, and
  engines read the same contract.
- **L0.4 — Never Compute on the Request Path.** Heavy analytics run in background
  workers; request paths read pre-computed snapshots, else return "pending."
- **L0.5 — No Silent Failures.** Critical paths log loudly and degrade honestly;
  never `except: pass` on intent/execution/safety.
- **L0.6 — Visual Truth Contract.** Only actual completion may visually resemble
  completion. (See `WLJ_VISUAL_TRUTH_CONTRACT.md`.)
- **L0.7 — Beth Consumes Briefings, Not Signals.** Intelligence produces composed,
  deterministic state objects (verdict already inside) for Beth to narrate over.

---

## Part II — The Five New Laws

### Law 1 — Data Freshness Before Reasoning

**Before answering any personal question, determine which datasets it requires and
whether they are current enough. If required data is stale or missing, do not answer
as though it were current — state exactly what is missing.**

- Every dataset that backs a personal answer must carry an **as-of timestamp** and a
  **freshness verdict** (`fresh | stale | pending | absent`) relative to the
  question's time window. Freshness is a deterministic property of the data, not a
  guess.
- "Today's sleep" before HealthKit has synced is **pending**, not 0 and not
  yesterday's value. The honest answer is *"I don't have today's sleep yet — Apple
  Health hasn't synced."* — never a confident stale number.
- Applies platform-wide: Apple Health, Dexcom/CGM, workouts, journal processing,
  finance/payroll, capture, labs. Each names its own freshness source.

*Evidence: Examples 1 & 2 — stale sleep presented as current.*

### Law 2 — Confidence Before Conversation

**Every personal answer carries deterministic confidence — composed from freshness,
completeness, source, synchronization, and evidence. If confidence is insufficient,
say so. Never replace uncertainty with confidence.**

- Confidence is **composed deterministically** (per L0.7), not narrated by the LLM.
  It is part of the state object Beth (or any surface) consumes.
- Insufficient confidence is a first-class, honest answer ("I have partial data…"),
  not a fabricated certainty and not silence.
- This extends the existing freshness verdict into a single composed confidence
  envelope that travels with every truth claim.

*Evidence: Examples 1 & 2 — confident delivery of low-confidence data.*

### Law 3 — Orchestration Before Reasoning

**Questions that are naturally workflows must be orchestrated, not collapsed into a
single reasoning prompt. Enumeration + Enrichment is a first-class, platform-wide
orchestration pattern.**

- The canonical shape: **`(WLJ deterministic set) × (bounded per-item enrichment) →
  deterministic assembly → narrate`.** "List each medicine and what each is for" is
  retrieve → enrich-each → assemble, not one large tool-loop invocation.
- Per-item enrichment that is **non-personal** (general education) is cached
  globally and reused; this is memoization of general knowledge, **not** a curated
  reference database.
- Generalize beyond medication: labs ("what each marker measures"), conditions,
  supplements, goals — any "enumerate a personal set, enrich each item" question.
- The agentic single-call tool loop remains the *fallback*, never the chosen
  strategy for a workflow-shaped question (reinforces L0.2).

*Evidence: Example 4 — a retrieve/enrich/assemble question forced through one
reasoning pipeline; the prompt-size / tool-loop / planner fragility chased across
multiple incidents.*

### Law 4 — Deterministic Retrieval Never Falls Back to AI Failure

**If a deterministic answer exists, return it. If retrieval fails, report the
retrieval failure. Never answer a deterministic question with "assistant
unavailable."**

- "How many steps yesterday?" is a deterministic lookup. Its failure modes are
  *retrieved value*, *retrieval error* (named), or *not-yet-synced* (Law 1) — never
  the LLM-outage message.
- The LLM-unavailable / "I couldn't pull that together" path is reserved for genuine
  LLM-dependent work (general education, narration), and may **never** be reached
  for a question a deterministic contract can answer.
- Deterministic fast paths must not route through, or share a failure mode with, the
  LLM path.

*Evidence: Example 3 — deterministic step count returned "assistant unavailable."*

### Law 5 — Stable Truth

**A repeated identical question, with no change in the underlying source data, must
produce an identical factual answer.**

- The same user must never receive 5.3h then 6.9h of sleep a minute apart unless new
  source data actually arrived. Aggregation must be **deterministic**; caches must
  be **keyed on a source-data version/as-of** and invalidated **only** on real data
  change — never time-varying, race-prone, or source-ambiguous.
- If two sources disagree, the contract picks one deterministically and records the
  choice; it does not flip between them.
- Stability is verifiable: same inputs ⇒ same output, provable by test.

*Evidence: Example 1 — the same morning question produced two different sleep values
one minute apart.*

---

## Part III — Affected Subsystems

The Laws are platform-wide. Subsystems that must comply (and what changes):

| Subsystem | Path(s) | Obligation introduced |
|---|---|---|
| **Data ingestion / sync** | `apps/health` (HealthKit), `apps/mobile` (ingest API), Dexcom/glucose, `apps/finance`, `apps/journal`, `apps/capture` | Each dataset emits an **as-of timestamp + freshness verdict** (Law 1). |
| **Domain Truth Contracts** | `apps/{domain}/services/{domain}_queries.py` | Expose freshness/completeness alongside the value; deterministic aggregation (Laws 1,5). |
| **State Assembly Engine (SAE)** | `apps/core/ai_state/` | Carry a **confidence envelope** (freshness+completeness+source+sync+evidence) per fact/domain (Law 2). |
| **Foundational Facts (deterministic fast path)** | `apps/ai/chatgpt_cos/foundational_facts.py`, `apps/ai/cos_services/health_facts.py` | Check freshness before answering; never share the LLM-failure path (Laws 1,4). |
| **CoS lanes / reasoning / tool loop** | `apps/ai/chatgpt_cos/` | Run the Answer Precondition Pipeline before reasoning; add **Enumeration+Enrichment** as a first-class lane; tool loop demoted (Law 3). |
| **General-knowledge enrichment + cache** | new, non-personal cache | Global per-entity education cache, lazy + background-warmed (Laws 3, L0.4). |
| **The 14 engines** | `apps/core/ai_*`, `apps/core/blueprint/` | Respect freshness; produce confidence-tagged composed state (Laws 1,2,L0.7). |
| **Caching layer** | `wlj:*` cache keys | Keys derived from source-data version/as-of; invalidate only on real change (Law 5). |
| **Answer surfaces** | dashboards, Action Center, exports, Physician Mode | Render freshness/confidence; honor Visual Truth (Laws 1,2,L0.6). |

---

## Part IV — Migration Strategy

Additive and phased; the platform stays answerable throughout.

1. **Freshness primitive (foundation).** Define a small, shared `Freshness`/`AsOf`
   value object and a `confidence envelope` shape. Domains populate them where the
   data already exists (no schema change for most — sync timestamps already exist).
2. **Domain Truth Contracts expose freshness.** Extend each canonical query to
   return `(value, as_of, freshness, completeness)`. Backward-compatible: callers
   that ignore the new fields keep working.
3. **SAE carries the envelope.** State builders attach the composed confidence to
   each fact/domain (read-only addition).
4. **Precondition pipeline at the answer boundary.** Foundational Facts and the CoS
   lanes consult freshness/confidence before answering; insufficient → honest
   "what's missing" answer. Deterministic paths decoupled from the LLM failure path
   (Law 4).
5. **Enumeration+Enrichment lane.** Introduce the orchestration pattern + non-personal
   enrichment cache; route medication-education-class questions to it; generalize to
   labs/conditions/goals.
6. **Stability hardening.** Make aggregations deterministic and re-key caches on
   source-data version; add stability tests (same input ⇒ same output).
7. **Per-domain rollout.** Health first (the evidence), then finance, journal,
   capture, labs — same contracts, no rewrite.

Each phase ships behind the existing test gates and is independently revertible.

---

## Part V — Breaking vs Non-Breaking Classification

**Non-breaking (additive — the majority):**
- Freshness/confidence value objects and envelope (new optional fields).
- Truth Contracts returning extra metadata (existing callers unaffected).
- SAE attaching confidence (read-only).
- New Enumeration+Enrichment lane + enrichment cache (new path; tool loop remains).
- Stability tests, freshness telemetry.

**Behaviour-changing (intended, user-visible — "breaking" by design):**
- Stale/pending data now yields an honest "not yet synced" answer instead of a
  confident stale number (Law 1) — *correct* change, but it changes outputs; gate
  with Beth Golden Behaviors + production validation.
- Deterministic questions no longer surface "assistant unavailable" (Law 4) — changes
  failure-mode text.
- Medication-education-class questions answered via orchestration, not the tool loop
  (Law 3) — changes the execution path (output should be equal or better).

**Genuinely breaking (none required):** no schema migration is mandated by the Laws
themselves; freshness sources largely already exist. Any later schema addition is a
normal additive migration.

---

## Part VI — Recommended Implementation Order

1. **Law 5 (Stable Truth)** + **Law 4 (Deterministic Retrieval)** — *first.* Highest
   trust impact, smallest surface, mostly bug-class fixes (deterministic aggregation,
   stable cache keys, decouple deterministic paths from the LLM failure path). Fixes
   Examples 1 & 3 directly.
2. **Law 1 (Freshness)** — the freshness primitive + Health domain (sleep/steps/
   glucose). Fixes Example 2.
3. **Law 2 (Confidence)** — compose the envelope on top of freshness; surface it.
4. **Law 3 (Orchestration)** — the Enumeration+Enrichment lane + non-personal cache;
   medication education first, then generalize. Fixes Example 4 as a *class*.

Rationale: stabilize and de-fragment the deterministic core first (Laws 4,5), then
add the freshness/confidence envelope (Laws 1,2), then the orchestration pattern
(Law 3) that the envelope makes safe.

---

## Part VII — Governance & Cross-References

- **Subordinate documents updated to defer here:** `BETH_ARCHITECTURAL_PRINCIPLES.md`
  (CoS constitution), `MEDICATION_INTELLIGENCE_CANON.md` (domain canon),
  `INTELLIGENCE_ARCHITECTURE.md` / `BETH_DOMAIN_REASONING_FRAMEWORK.md` (reasoning).
- **Enforcement:** new code touching answer paths must satisfy the Answer Precondition
  Pipeline; reviews check freshness/confidence/orchestration before reasoning.
- **These Laws are platform rules, not Beth behavior** — every future subsystem
  answers using fresh, deterministic, appropriately-orchestrated truth before any
  reasoning or narration begins.

*Last updated: 2026-06-28 (established).*
