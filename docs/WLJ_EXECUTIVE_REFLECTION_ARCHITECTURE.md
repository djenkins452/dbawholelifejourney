# WLJ Executive Reflection & Continuous Improvement Architecture

**Status:** RATIFIED — governing architecture (2026-07-07). Implementation in progress (Phase 0A → 0B).
**Layer:** Phase 4 — sits *above* Phases 1–3; observes them, never replaces or bypasses them
**Owner decision authority:** Danny (architect). Beth *recognizes and communicates*; she never self-modifies Truth, Reasoning, or Execution.
**Companion investigation:** the capability inventory and wiring analysis that produced this design (see References).

> This document governs Phase 4 the way the Reasoning Architecture, Standing Context, and Tool Architecture documents govern their areas. It is the constitution for how Beth improves. If an implementation ever contradicts this document, the implementation is wrong.

---

## 0. Purpose

**Executive Reflection does not exist to make Beth smarter. It exists to make her progressively more *trustworthy*, more *valuable*, and more *effective* — so that every meaningful interaction gives the user more reason to rely on her — without ever compromising the deterministic truth on which that trust is built.**

Trust is necessary but not sufficient. A perfectly trustworthy assistant that never demonstrates initiative, insight, or proactive leadership is not an exceptional Chief of Staff. Reflection therefore cultivates trust as the ultimate *outcome* and, inseparably, the **value, effectiveness, and initiative** that earn deepening trust over time.

That is the whole charter. Beth becoming "smarter" in the sense of accumulating heuristics is not a goal and is, in most forms, a failure mode. Trust — earned through demonstrated reliability, proactive value, honesty about limits, and never quietly routing around the deterministic architecture — is the ultimate outcome Phase 4 optimizes; value, effectiveness, and initiative are how that trust is earned.

Today, when Beth makes a mistake, the correction lives and dies in one conversation turn. Nothing durable records what happened, nothing evaluates whether she succeeded, nothing classifies *why*, and nothing distinguishes "Beth should adapt" from "the platform has a defect Beth must not paper over." The improvement loop runs entirely through Danny → Claude → code. Executive Reflection closes that loop **correctly**: it evaluates both successes and failures, reinforces what earns trust, and surfaces — never hides — what only the platform can fix.

It does four things and only four things:

1. **Observe** what happened after a meaningful interaction, using evidence WLJ already produces.
2. **Assess** whether Beth succeeded, and what the interaction did to trust — *before* asking why.
3. **Classify** (only when needed) *where* something went wrong.
4. **Route to exactly one disposition** — and the overwhelmingly common dispositions are *reinforce* or *do nothing*.

It has no authority to change how Beth retrieves truth, reasons, or executes. The only path to a Phase 1–3 change remains Danny directing Claude.

---

## 1. Architectural principles

These are governing principles, not implementation notes. Every design and implementation decision defers to them.

**P1 — Trust is the ultimate KPI; value and effectiveness are how it is earned.**
Every reflection ultimately answers one question: *did this interaction increase, maintain, or decrease the user's trust?* But trust is not earned by caution alone — it is earned by demonstrated **value**: initiative, insight, proactive leadership, and effective execution. Truth accuracy, reasoning quality, communication, calibration, and **executive initiative** all exist to move that outcome. Trust is measured (§6, §12), never assumed, and it is the headline of Beth's performance (§12).

**P2 — Learning is default-deny.** *(Elevated to a governing principle.)*
The default conclusion of every reflection is **"this is NOT something Beth should learn."** Beth earns the right to learn only by *proving*, for a specific event, that **all five** hold:
   1. deterministic **truth** is not involved,
   2. **reasoning** is not involved,
   3. **execution** is not involved,
   4. **sufficient evidence** exists, and
   5. the learning is **bounded** to preference, communication, or trust-repair behavior.

If any one fails, Beth does not learn. Everything else preserves the deterministic architecture. Learning is rare by design; a Phase 4 that learns often is malfunctioning.

**P3 — Never learn around deterministic architecture.**
If a failure's locus is Truth, Reasoning, or Execution, learning is *forbidden* — not discouraged. Beth does not memorize the corrected answer; she raises an Executive Improvement Opportunity so the underlying phase can be fixed. Memorizing around a defect hides it and makes it permanent for every user. This is the single most important safety property in the system.

**P4 — Success is evaluated as deliberately as failure.**
Executive Reflection is a professional-development system, not a mistake detector. Recommendations that worked, predictions that proved accurate, coaching that resonated, prioritization that improved execution — these are reflected on and *reinforced* with the same rigor applied to failures. Reinforcement is a first-class disposition (§10).

**P5 — Reflection understands before it classifies; assesses before it explains.**
Reflection first reconstructs what happened, then assesses *whether* it succeeded, and only then — if warranted — classifies *why/where*. The label is always derived from evidence, never assumed from the trigger.

**P6 — Confidence is composed, not narrated.**
Whether a failure is architectural or learnable, and whether trust moved, is decided by deterministic checks (re-reading the source of truth, thresholds, outcome comparison) — never by the LLM narrating a conclusion into existence (WLJ Law 2). The LLM may help *describe* an event; it never *decides* the disposition.

**P7 — Human-in-the-loop by construction.**
An Executive Improvement Opportunity is surfaced to Danny. It is never auto-converted into a development task and never auto-implemented. Beth's job ends at "here is what I could not do, and my evidence for why." Danny remains the architect; Claude remains the implementation engineer.

**P8 — Modify Before Adding.**
Reflection is a thin consumer and router over evidence and metrics WLJ already computes. It is not a parallel intelligence engine. Its net-new surface is deliberately minimal (§19).

**P9 — Fail-open and off-path.**
Reflection runs in a background worker, never on the request path (WLJ F5). If reflection fails entirely, the user never notices and Phases 1–3 are unaffected (WLJ Rule 6).

**P10 — An Executive Chief of Staff is not defined by never making mistakes.**
She is defined by continuously becoming *more valuable* — recognizing mistakes, reinforcing successes, and improving in ways that preserve trust. Reflection measures and cultivates that trajectory; it does not chase an unattainable zero-defect ideal, and it never sacrifices trust or determinism in pursuit of one. The mark of the exceptional Chief of Staff is the slope of improvement, not the absence of error.

---

## 2. Relationship to Phases 1–3

```
   Phase 1 — Deterministic Truth  ┐
   Phase 2 — Reasoning & Synthesis │  the foundation — unchanged, authoritative
   Phase 3 — Execution (UAIO)     ┘
                 │
                 │  produces a durable record of what it concluded and did
                 ▼
   Phase 4 — Executive Reflection & Continuous Improvement
                 │
                 ├─▶ (common)  REINFORCE        → strengthen what earned trust
                 ├─▶ (rare)    LEARN            → preference / communication / trust-repair only
                 ├─▶ (as needed) EXECUTIVE IMPROVEMENT OPPORTUNITY → surfaced to Danny
                 └─▶ (default) OBSERVE / INSUFFICIENT EVIDENCE → no change
                 │
                 └─▶ every reflection contributes to the EXECUTIVE SCORECARD (§12)
```

Phase 4 has **exactly two behavior-affecting write targets** and no others:

| Write target | May contain | Hard limit |
|---|---|---|
| **Learning stores** (existing `BehaviorDirective` / preference records) | tone, framing, prioritization, personalization, trust-repair notes | **Never a truth value.** Never a fact that belongs in Phase 1. |
| **Executive Improvement Opportunity ledger** | a classified, evidence-backed description of a capability or architectural limitation | **Never auto-actioned.** Read-only to the running system; actionable only by Danny. |

It additionally writes two **observational** (non-behavior-affecting) records: the reflection log (§ lifecycle) and the Executive Scorecard snapshot (§12). Phase 4 reads from Phases 1–3; it has **zero** authority over their behavior. This is what makes it additive rather than a redesign.

---

## 3. Executive Reflection lifecycle

Your corrected sequence, with the Assessment stage added:

```
  Conversation / Interaction
            │
            ▼
  ①  TRIGGER              a reflection-worthy event is emitted (off-path, lightweight)
            │
            ▼
  ②  EVIDENCE COLLECTION  gather deterministic evidence of what happened (§5)
            │
            ▼
  ③  RECONSTRUCTION       reconstruct the actual sequence: what Beth concluded,
            │             what the source of truth said, what the user did, how it turned out
            ▼
  ④  ASSESSMENT           "Was I successful — and what did this do to trust?"  (§6)
            │             outputs an OUTCOME VERDICT + a TRUST DELTA, before asking why
            │
      ┌─────┴───────────────────────────────┐
      │ clean success                        │ failure / partial / notable
      ▼                                       ▼
  (skip deep classification)          ⑤  CLASSIFICATION  "Why / where?"  (§7)
      │                                       │           derive the failure LOCUS
      ▼                                       ▼
  ⑥  DECISION / DISPOSITION  ── route to exactly one terminal state ──
            │
   ┌────────┼───────────────┬───────────────────────┬──────────────────┐
   ▼        ▼               ▼                       ▼                  ▼
 REINFORCE  LEARN         EXECUTIVE IMPROVEMENT     OBSERVE /          (every path)
 (success;  (rare;        OPPORTUNITY               INSUFFICIENT       feeds the
  P4)       bounded; P2)  (locus = Phase 1–3        EVIDENCE           SCORECARD (§12)
                          faculty; → Danny; P3/P7)  (default; §11)
```

Steps ①–② touch the request path only as far as *emitting an event and a snapshot*. Steps ③–⑥ run entirely in a background worker (WLJ F5). Assessment (④) is deliberately placed **before** Classification (⑤): a clean success needs no failure-locus analysis, so the common case exits cheaply, and successes are evaluated on equal footing with failures rather than as an afterthought.

---

## 4. Reflection triggers — what deserves reflection

Reflection is triggered by *meaningful interactions*, not just corrections. The emit is cheap; most triggers terminate at Reinforce or Observe.

| Trigger | Signal it may carry | Typical disposition |
|---|---|---|
| **Recommendation followed** | Beth read the situation well | **Reinforce** |
| **Prediction later proven correct** | calibration confirmed | **Reinforce** |
| **Coaching style resonated** (positive feedback, thanks) | communication working | **Reinforce** |
| **Prioritization improved execution** | executive judgment sound | **Reinforce** |
| **User corrects a fact/recommendation** | Beth was wrong somewhere | classify → Learn / EIO |
| **User reconciles state** ("already did that") | executive-state miss vs. genuine data gap | Observe / EIO |
| **Recommendation ignored** (repeatedly) | wrong content, wrong timing, or wrong preference | classify → Learn / EIO / Observe |
| **Prediction later proven incorrect** | reasoning or calibration issue | classify → EIO / calibrate |
| **Advice explicitly rejected** | preference & trust signal | Learn / Observe |
| **Trust decreased** (frustration, "that's not helpful") | *symptom* — locus unknown | classify; often → EIO or Insufficient Evidence |
| **High-confidence answer later wrong** | miscalibration | EIO / calibrate |
| **Low-confidence answer later right** | under-calibration | Observe / calibrate |
| **Validator/guardrail fired** (truth validator, narration contract, contradiction telemetry) | a faculty nearly said something untrue | strong EIO signal |

**Design rule for triggers:** *trust changes are always a symptom, never a locus.* A trust move is decomposed by reflection into its underlying cause (a truth failure, a reasoning failure, a communication win). Beth never "learns" from a trust move directly — she reinforces or escalates from what *caused* it. Trust is the outcome the whole system serves (P1), which is exactly why it is never itself a thing to learn.

---

## 5. Evidence collection

Reflection reconstructs events from evidence WLJ already produces. It does not re-run reasoning; it reads the record.

| Evidence | Source (all existing) | Answers |
|---|---|---|
| **What Beth concluded** | executive read / `ExecutiveSignals`, chat snapshot | "What did she actually say and believe?" |
| **What the source of truth said** | re-read `day_truth`, `canonical_item_truth`, SAE state | "Was the correct answer available at the time?" |
| **What the user did** | correction lane, reconciliation, `CorrectionRecord`, intervention response log (surfaced/complied/ignored/overrode) | "How did the user respond?" |
| **How it turned out over time** | `PredictionOutcome`, `InterventionEffectivenessProfile`, drift scores | "Was the recommendation/prediction validated by reality?" |
| **Confidence Beth stated** | response confidence, `ValidatorMetric` | "Did she claim more certainty than warranted?" |
| **Trust trajectory** | correction frequency (ops telemetry), thumbs feedback, reconciliation tone | "Is the relationship strengthening or fraying?" |

**The decisive reconstruction step — the deterministic agreement check.**
For any *factual* correction, reflection re-reads the source of truth and compares it to the user's correction. This single check does most of the classification work deterministically (P6):

- Source, re-read, **now agrees** with the user ⇒ the truth *was available* and Beth didn't use it ⇒ **Reasoning/Retrieval** locus. Beth must **not** store the fact (it already exists); she escalates.
- Source, re-read, **still disagrees** (and the user is right) ⇒ the **truth layer itself** is wrong/stale/missing ⇒ **Truth Retrieval** locus, architectural. Beth must **not** learn the corrected value. She escalates.
- **No source exists** for the claim ⇒ **capability gap**, architectural ⇒ escalate.
- The correction is about *how she said it*, not *what was true* ⇒ **Communication/Preference** locus ⇒ eligible to learn.

**Evidence-substrate dependency (record, not implement):** the executive read (`ExecutiveSignals`) is currently transient — it leaves no trace of what Beth concluded at answer-time. Reliable reconstruction of "what Beth believed" requires that conclusion to be *recoverable* (the chat snapshot partially captures it). This is a design precondition for high-quality reflection, called out here so implementation planning accounts for it.

---

## 6. Assessment — "Was I successful?" (before "why?")

Assessment is the stage that makes Phase 4 a professional-development system rather than a mistake log. Before any locus analysis, it answers two questions from the reconstruction:

**(a) Outcome verdict:**

| Verdict | Meaning |
|---|---|
| **Success** | Beth's answer/action was correct and served the user well |
| **Partial** | correct in part; something fell short |
| **Failure** | Beth was wrong, unhelpful, or an action didn't land |
| **Neutral / Indeterminate** | no clear outcome signal (routes toward Insufficient Evidence) |

**(b) Trust delta — the ultimate KPI (P1):**

| Trust delta | Signal |
|---|---|
| **Increased** | user relied on Beth and it paid off; expressed confidence/gratitude |
| **Maintained** | competent, unremarkable interaction; no erosion |
| **Decreased** | correction, frustration, ignored advice, visible mistake |

Assessment is computed on **every** reflection, regardless of outcome, and both outputs feed the Executive Scorecard (§12). Its routing role:

- **Clean Success + trust Increased/Maintained** → skip deep classification → **Reinforce** (record what worked so it can be strengthened).
- **Failure / Partial**, or **trust Decreased** → proceed to Classification (§7) to establish locus.
- **Neutral / Indeterminate** → **Insufficient Evidence** (§11).

Placing Assessment before Classification means success is never treated as "nothing to see here," and the expensive locus work only runs when something actually went wrong.

---

## 7. Failure taxonomy (classification / locus)

Classification runs only when Assessment flags a failure, a shortfall, or a trust decrease. It answers *where* — the **functional locus**, i.e. which of Beth's faculties is implicated. Locus determines who owns the fix and whether learning is even permitted.

| Class | Meaning | Owning phase / faculty | Learnable by Beth? | Default disposition |
|---|---|---|---|---|
| **Truth Retrieval** | The right data was stale, missing, or not fetched | Phase 1 | **No** | Executive Improvement Opportunity |
| **Reasoning** | Data was correct; the inference was wrong | Phase 2 | **No** | Executive Improvement Opportunity |
| **Execution** | An action failed, mis-routed, or wasn't performed | Phase 3 (UAIO) | **No** | Executive Improvement Opportunity |
| **Communication** | Truth & reasoning right; delivery poor (tone, clarity, framing, length) | Narration | **Yes** | Learn |
| **Preference** | Beth applied a default the user wants different | Personalization | **Yes** | Learn |
| **Confidence Calibration** | Stated confidence ≠ actual correctness | Confidence composition | **Conditional** | EIO if composition broken; calibrate if user-specific |
| **Trust** | *Not a locus — a symptom.* Decompose into the cause above | — | **No (decompose)** | route to underlying class |
| **None / Positive** | Beth was correct; the outcome confirms it | — | — | Reinforce |
| **Indeterminate** | Reflection cannot establish what happened | — | **No** | Insufficient Evidence |

**The load-bearing column** is "Learnable?" The three deterministic faculties — Truth, Reasoning, Execution — are a **hard No**, operationalizing P2 and P3. Everything Beth may learn concerns *how she serves*, never *what is true*.

---

## 8. Learning decision model

Learning is **default-deny** (P2). A reflection produces a `Learn` disposition only when **all five** conditions hold:

1. **Truth not involved** — the deterministic agreement check (§5) confirms the source of truth was correct.
2. **Reasoning not involved** — the miss was in delivery/personalization, not inference.
3. **Execution not involved** — no action failure is implicated.
4. **Evidence sufficient** — the reconstruction cleared the confidence threshold (§11).
5. **Bounded unit** — the learned thing adjusts tone, framing, prioritization, personalization, or trust-repair; it is expressible as a reversible `BehaviorDirective`-style directive with an evidence trail, and it **never encodes a truth value.**

If any condition fails, learning does not happen. Depending on which failed, the disposition becomes **Executive Improvement Opportunity** (locus is a deterministic faculty) or **Insufficient Evidence** (couldn't establish what happened).

Because the only things Beth can accumulate are bounded, evidence-backed, reversible directives about *service style* — and only when the truth layer is provably not at fault — she cannot devolve into a heuristic sprawl or learn around a defect.

---

## 9. Reinforcement — the success model

Reinforcement is the positive counterpart of learning and a first-class disposition (P4). When Assessment returns Success with trust Increased/Maintained, reflection records *what worked* and, where a matching directive or profile exists, **strengthens** it:

- A coaching phrasing that resonated → reinforce the corresponding communication directive.
- A prioritization that improved execution → reinforce the prioritization pattern.
- A prediction proven accurate → strengthen the relevant confidence profile (reusing existing `PredictionAccuracyProfile`).

Constraints mirror learning: reinforcement **never** creates truth, never fabricates a directive from a single positive event, and only adjusts weight on patterns that already exist. Its purpose is deliberate professional development — Beth should get measurably better at what earns trust, not merely avoid mistakes.

---

## 10. Executive Improvement Opportunity (EIO)

**Name:** *Executive Improvement Opportunity (EIO)* — frames the output as *an opportunity to make the Chief of Staff more capable*, not a passive bug ticket.

**What an EIO is:** a classified, evidence-backed, human-surfaced record that says *"here is something I could not do correctly, here is my reconstruction of why, and here is the faculty I believe is implicated."*

### 10.1 Two-lens classification

An EIO is classified along **two independent axes**. Keeping them separate is what prevents "Architecture" from swallowing every EIO.

- **Functional locus** (from §7) — *which of Beth's faculties failed*: Truth Retrieval, Reasoning, Execution, Confidence Calibration, or Capability gap. This is the *symptom* Beth experienced.
- **Engineering category** — *what kind of work fixes it*. This is the *remedy* Danny/Claude would apply. Architecture is **one** category among several:

| EIO engineering category | What it means |
|---|---|
| **Architecture** | a structural or law-level limitation; needs a design decision |
| **Retrieval** | data exists but isn't being fetched / query gap |
| **State** | state awareness stale, missing, or not propagated (SAE-adjacent) |
| **Serialization** | data-contract / schema / key-mismatch defect between producer and consumer |
| **Pipeline** | orchestration, ordering, or phase-wiring defect |
| **Telemetry** | the failure couldn't even be measured; observability gap |
| **UI** | presentation/template surface issue |
| **Dead Code** | disconnected, orphaned, or never-wired capability |
| **Other** | genuine capability gap not covered above |

A single EIO carries both — e.g. *locus: Truth Retrieval × category: Serialization* ("the schedule was right in the DB but a key mismatch dropped it before Beth saw it"). The locus tells Beth what she experienced; the category tells Danny where to look. Neither is a verdict — both are hypotheses backed by preserved evidence.

### 10.2 Conceptual contents (not a schema)
- **Functional locus** and **engineering category** (§10.1).
- **Trigger event**, **evidence bundle** (immutable references, preserved for later verification), **reconstruction narrative**, **hypothesized root cause** (a hypothesis, never a verdict), **confidence** (deterministically composed), **status** (open → acknowledged → in_progress → resolved / dismissed), **recurrence count**.

### 10.3 Hard constraints (P3, P7)
- Never auto-converted to a development task; never auto-implemented.
- Beth never attempts a workaround for the limitation an EIO describes — recognizing and communicating *is* the job.
- Truth/reasoning/execution are never modified by an EIO's existence. Only Danny, reading it, may direct a change.

### 10.4 Home — extend `ImprovementTaskModel` (justification in §11)

---

## 11. Home for EIO — `ImprovementTaskModel` vs `OpsAnomaly`

Recommendation: **extend the existing `assistant/ImprovementTaskModel`** rather than reuse `OpsAnomaly` or build a third ledger. The comparison, and why it's architecturally correct:

| Dimension | `OpsAnomaly` | `ImprovementTaskModel` |
|---|---|---|
| **Semantic domain** | runtime-operational health (missed runs, error spikes, validator crashes) | **capability gaps — "Beth couldn't do X"** |
| **Lifecycle** | `is_active` / `resolved_at`; **auto-clears when the condition clears** | full human workflow: new → pending_approval → approved → in_progress → testing → resolved / dismissed / rolled_back |
| **Human-in-the-loop** | none — autonomous monitoring signal | **built-in approval flow (tokens); a human decides** |
| **Producer** | written only by SAME (autonomous monitor) | capability-gap detector; multi-source by design |
| **Persistence semantics** | transient — a symptom that disappears when the runtime recovers | **durable — persists until a human acts** |
| **Beth-awareness loop** | none | **already re-read into Beth's prompt as "known limitations"** (`system_gap_awareness`) |
| **Change-tracking** | none | git-commit / rollback fields — designed around a change being made |

**Why this is the correct choice, not just the convenient one:**

1. **Semantic match.** An EIO *is* a capability/limitation record — the same concept `ImprovementTaskModel` already represents. `OpsAnomaly` represents "something in the running system is currently misbehaving." An EIO is not a runtime alarm.
2. **Persistence semantics are decisive.** `OpsAnomaly` **auto-resolves when its condition clears**. A truth-retrieval defect does not "clear itself" — it waits for Danny. Housing EIOs in `OpsAnomaly` would make them *vanish when the immediate symptom passes*, destroying the very opportunity Phase 4 exists to preserve. `ImprovementTaskModel` persists until a human closes it — exactly right.
3. **Human-in-the-loop is native (P7).** `ImprovementTaskModel`'s approval-token workflow *is* "Danny decides." `OpsAnomaly` has no approval concept; using it would require bolting a human workflow onto a monitoring signal.
4. **The Beth-awareness loop already exists — a free win.** `system_gap_awareness` already injects unresolved `ImprovementTaskModel` rows into Beth's prompt as "KNOWN SYSTEM LIMITATIONS." Reuse means an open EIO *automatically* makes Beth honest about her own limits ("I can't reliably do X yet — it's a known opportunity"), with **zero new wiring**. This directly serves the trust charter (P1): a Chief of Staff who knows and states her limitations is more trustworthy than one who doesn't.
5. **Producer semantics stay clean.** `OpsAnomaly` is owned by SAME. Writing EIOs there conflates two producers with different meanings in one ledger. `ImprovementTaskModel` is *already* the capability-gap ledger; an EIO is a sibling category of the same idea.

**The required extension (conceptual, not implementation):** add the reflection-sourced two-lens taxonomy (§10.1) to the model's category set, and explicitly **do not** enable its dormant autonomous-execution half (that would violate P7). This is additive and law-compliant.

---

## 12. Executive Scorecard

**Verdict: it belongs.** Individual reflections are events; the Scorecard is what turns them into a *performance trajectory* — the difference between a mistake log and professional development (P4). It is also the only place Trust (P1) becomes a measured, trend-able outcome.

**What it is:** Beth's internal, admin-facing professional performance review. **Not user-facing** (it is dev/operator-facing, so internal naming is fine). It answers the one question the whole system exists to answer: *"Is Beth becoming a more trustworthy — and more valuable — Chief of Staff over time?"*

**Structure — Trust is the headline; Executive Initiative is the leading *value* signal; every other dimension is a diagnostic sub-score that explains the trust-and-value trajectory:**

| Dimension | Fed from (mostly existing) | Reads as |
|---|---|---|
| **User Trust** *(headline)* | aggregate trust delta across reflections; correction frequency; feedback | the north-star trend |
| **Executive Initiative** *(value)* | proactive items surfaced before being asked (PGE guidance acted-on); cross-domain connections (`DomainCorrelation`); preventive/anticipatory coaching; proactive check-in engagement | is she *leading*, not just responding? |
| **Truth Accuracy** | rate of Truth-Retrieval EIOs vs. factual claims | is the truth layer serving her? |
| **Reasoning Accuracy** | rate of Reasoning EIOs vs. reasoning events | is her inference sound? |
| **Execution Effectiveness** | execution EIOs; `InterventionEffectivenessProfile` | do her actions land? |
| **Prediction Accuracy** | existing `PredictionAccuracyProfile` (reused) | are her forecasts calibrated? |
| **Communication Quality** | communication learn/reinforce events; positive feedback | does her delivery resonate? |
| **Confidence Calibration** | stated-confidence vs. correctness; existing `ai_feedback` confidence adjustment | does her certainty match reality? |
| **Learning Events** | count/rate of `Learn` dispositions | is learning staying *rare* (P2 health check)? |
| **Executive Improvement Opportunities** | EIO counts by category, open/resolved, recurrence | where is the platform limiting her? |

Two of these dimensions are also **guardrail metrics on Phase 4 itself**: a rising *Learning Events* rate is a warning that Beth may be learning too much (P2 breach); a rising *EIO* count concentrated in one category tells Danny where the platform most constrains trust.

**How it complies (this is why it's cheap and safe):**
- **Composition, not new measurement (P8).** Most dimensions already have data sources — `PredictionAccuracyProfile`, `InterventionEffectivenessProfile`, `ValidatorMetric`, correction telemetry — plus the reflection log's assessment/classification outputs. The Scorecard *composes*; it does not instrument anything new.
- **Background, snapshot-read (P9 / WLJ F5).** Computed on a schedule in a background worker and read from a snapshot, following the existing `IntelligenceMetricsSnapshot` / `SystemMaturitySnapshot` pattern. It is a lagging, directional trend, never a real-time request-path computation.
- **Deterministic (P6).** Every dimension is a composed metric, not an LLM judgment.

The Scorecard reuses an existing pattern rather than inventing a bespoke system; conceptually it is one more composed snapshot alongside the maturity/intelligence snapshots WLJ already produces.

---

## 13. Confidence / Insufficient Evidence path

**It belongs, and it is the honest default — not a rare third branch.** Given P2, the highest-frequency terminal states are **Reinforce** (clear successes) and **Observe / Insufficient Evidence** (something happened but reflection cannot establish *what*). Treating "I don't know what went wrong" as first-class is what stops Beth from guessing — and guessing is how a reflection system would begin learning around problems it doesn't understand.

**Chosen when:** the reconstruction is contradictory or stale (WLJ Law 1), the agreement check is inconclusive, or confidence is below the composed threshold.

**What happens:** no learning, no EIO, no behavior change — the event is recorded in the reflection log with its evidence, and it still contributes a trust delta to the Scorecard. **Recurrence promotion:** if materially similar Insufficient-Evidence events recur past a threshold, the *pattern* is promoted to an EIO ("something keeps happening here I cannot classify — worth a human look"). This is how the ambiguous tail reaches Danny without Beth ever pretending to understand it. It is the structural embodiment of "confidence before conversation" (WLJ Law 2).

---

## 14. Architectural compliance with WLJ Architecture Laws

| Law / Invariant | How Phase 4 complies |
|---|---|
| **Law 0 — Intent before retrieval** | Reflection observations never steer future answers; they inform Danny (EIO) or become bounded service-directives. |
| **Law 1 — Freshness before reasoning** | Stale evidence forces Insufficient Evidence; reflection never treats old state as current. |
| **Law 2 — Confidence before conversation** | Assessment (trust delta, outcome), locus, and disposition are composed by deterministic checks, never narrated by the LLM. |
| **Law 4 — Deterministic paths never fall to AI failure** | Reflection is off-path and observe-only; it cannot degrade a deterministic answer. |
| **Law 5 — Stable truth** | Learning is bounded to preference/tone/prioritization; truth is never mutated ⇒ identical question + unchanged source ⇒ identical answer. |
| **F1 — Truth/Reasoning separation** | Reflection never invents or stores a personal fact; the learnable set excludes truth. |
| **F5 — Never compute on the request path** | Triggers emit lightweight; reconstruction, assessment, classification, and the Scorecard run in background workers. |
| **F8 — Beth consumes briefings, not signals** | EIOs, directives, and Scorecard entries are composed, verdict-bearing records — not raw signals injected into Beth's prompt. |
| **Rule 17 — Phase integrity** | Phase 4 observes only; it executes nothing. |
| **Rule 6 — Fail-open** | If reflection errors, user flow and Phases 1–3 are unaffected. |
| **Modify Before Adding** | Reflection reuses existing evidence, metrics, ledger, and snapshot patterns; net-new surface is minimal (§19). |

Phase 4 requires no exception to any law. The laws define its safe shape — off-path, observe-only, composed-output, preference-not-truth, human-in-the-loop.

---

## 15. Examples

**A. Strength-vs-cardio — source now agrees.** Beth recommends strength; user says cardio. Assessment: Failure, trust Decreased. Agreement check: schedule says *cardio* — truth was available. Locus: **Reasoning**. Disposition: **EIO** (locus Reasoning × category likely Pipeline/State). Beth does **not** store "cardio today."

**B. Strength-vs-cardio — source still says strength, user is right.** Truth layer is stale/wrong. Locus: **Truth Retrieval** × category **Serialization** or **Retrieval**. Disposition: **EIO**. Beth must **not** learn "cardio" — that hides a defect that misfires for every user.

**C. "Stop calling me 'champ.'"** Assessment: Partial, trust Decreased. Truth/reasoning fine; delivery grates. Locus: **Communication**. All five learn-conditions pass. Disposition: **Learn** a reversible directive.

**D. Prediction proven accurate.** Assessment: Success, trust Increased/Maintained. Disposition: **Reinforce** — strengthen the confidence profile (reusing `PredictionAccuracyProfile`). Contributes positively to Prediction Accuracy and Trust on the Scorecard.

**E. Prioritization improved execution.** User completed more after Beth reordered the day. Assessment: Success. Disposition: **Reinforce** the prioritization pattern (P4).

**F. Meditation nudge ignored three times.** Reflection distinguishes preference ("doesn't want meditation" → **Learn**, deprioritize) from timing ("right idea, wrong hour" → **EIO**, guidance-timing) via evidence. Beth doesn't just stop without establishing which.

**G. "That wasn't helpful," no specifics.** Assessment: Failure, trust Decreased; but no locatable fact or preference. Disposition: **Insufficient Evidence**; recorded. Recurs on the same answer type → promoted to **EIO**.

---

## 16. Future evolution

Each stage carries a promotion trigger; nothing is "someday."

- **Phase 4.0 (this document).** Lifecycle with Assessment; deterministic classifier; default-deny learning; reinforcement; two-lens EIO ledger (extending `ImprovementTaskModel`), surfaced to Danny; Insufficient-Evidence as honest default; Executive Scorecard as a composed background snapshot. All human-in-the-loop.
  *Trigger → 4.1:* 4.0 in production producing accurate classifications over a review period.
- **Phase 4.1 — Recurrence & reflection quality.** Recurrence-driven promotion; metrics on whether classifications held up when Danny investigated (reflection accuracy on the Scorecard).
  *Trigger → 4.2:* enough EIO volume that clustering helps.
- **Phase 4.2 — EIO clustering.** Group EIOs into architectural themes so Danny sees systemic patterns, not incidents.
  *Trigger → 4.3:* a demonstrated class of low-risk, high-confidence EIOs.
- **Phase 4.3 — Semi-autonomous routing (deferred, gated).** *Only* for a narrow, proven-safe EIO class, draft into the existing `assistant/` gap→task pipeline — still with mandatory human approval before any code change. Truth/reasoning/execution changes remain human-authored indefinitely. Requires a separate design review.

---

## 17. Design challenge — is this the smallest compliant architecture?

Per the instruction to challenge the design, here is the attempt to simplify or remove pieces, and the conclusion.

**Can existing architecture replace any piece?**
- *The reflection log* — could `chat_snapshot` replace it? No. `chat_snapshot` is a flag-gated, file-based, request-scoped *input* to reflection; it captures what the system computed, not the *conclusion* reflection reached (assessment, locus, disposition, trust delta). The Scorecard and recurrence both need those conclusions durably. But the log stays *thin* — it records outcomes, not a re-derivation.
- *The EIO ledger* — replaced by extending `ImprovementTaskModel` (§11). **Not a new model.**
- *The Scorecard* — replaced-in-pattern by the existing `IntelligenceMetricsSnapshot` / `SystemMaturitySnapshot` mechanism, and fed largely by existing profiles (`PredictionAccuracyProfile`, `InterventionEffectivenessProfile`, `ValidatorMetric`). **Composition, not new measurement infra.**
- *The learn target* — the existing `BehaviorDirective` / preference stores. **Not a new model.**
- *The classifier* — reuses `day_truth` / `canonical_item_truth` for the agreement check. The locus/category logic is genuinely new but thin and deterministic.

**Can pieces be removed?** Each remaining piece maps to a distinct, non-overlapping requirement; removing any breaks a named goal:
- Remove the **reflection log** → no Scorecard input, no recurrence promotion, no audit.
- Remove the **EIO ledger extension** → failures have nowhere to go but learning, violating P3.
- Remove the **Scorecard** → no trust KPI, no professional-development trajectory (fails P1/P4).
- Remove the **Assessment stage** → successes become an afterthought and trust is never measured (fails P1/P4).
- Remove the **classifier** → cannot distinguish learn from escalate — the entire point.
- Remove the **learn target** → no improvement at all.

**What was deliberately *not* built** (the simplification, made explicit): no new engine; no new dashboard (reuse the improvement dashboard); no new measurement infrastructure (Scorecard composes existing metrics); no LLM verdict (deterministic-first classifier); Assessment and Classification are two logic stages in one background worker, not two engines.

**Net-new surface, in full:** (1) one thin append-only reflection log; (2) a taxonomy/category extension on `ImprovementTaskModel`; (3) a composed Scorecard snapshot following an existing pattern; (4) one deterministic classifier + one background worker. Everything else is reuse.

**Conclusion:** After challenge, this is the smallest architecture that accomplishes the objective — make Beth measurably more *trustworthy, more valuable, and more effective* after every meaningful interaction, reinforcing success and initiative and escalating (never hiding) platform limits — while fully complying with the WLJ Architecture Laws and Modify Before Adding. It adds no engine and no parallel intelligence. If, during implementation, any part begins to resemble a standalone intelligence engine, that is the signal it has drifted from this document — and the document wins.

---

## References

- Companion investigation (capability inventory, overlap analysis, wiring breaks) — this session's Phase 4 investigation.
- `docs/WLJ_ARCHITECTURE_LAWS.md` — Laws 0–5, invariants F1/F5/F8, Rules 6/17.
- `docs/INTELLIGENCE_ARCHITECTURE.md` — the three-phase engine pipeline (Interpretation → Execution → Post-Execution).
- `docs/ENGINE_COS_REFERENCE.md` — engine inventory and CoS context pipeline.
- Existing reuse surfaces: `apps/core/ai_memory/` (`BehaviorDirective`, `CorrectionRecord` via `apps/ai/correction_service.py`), `apps/core/ai_feedback/` (`PredictionAccuracyProfile`, `InterventionEffectivenessProfile`), `assistant/` (`ImprovementTaskModel` + dashboard + `system_gap_awareness` prompt injection), `apps/core/ai_observability/` (`OpsAnomaly`, `IntelligenceMetricsSnapshot`, `SystemMaturitySnapshot`, `ValidatorMetric`).

*Last updated: 2026-07-07 — RATIFIED. Revision 3 (Trust + Value + Effectiveness charter, Executive Initiative scorecard dimension, P10 "not defined by never making mistakes"; governing document for Phase 4.0).*
