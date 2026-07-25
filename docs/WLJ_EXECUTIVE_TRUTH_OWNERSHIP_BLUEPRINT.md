# WLJ — Executive Truth Constitutional Ownership Blueprint

**Date:** 2026-07-24 · **Type:** definitive ownership map (no implementation, no redesign)
**HEAD assessed:** `b858e060`
**Status:** **BLUEPRINT — the stable ownership model future Executive Truth implementation follows**
**Measured against:** `02_WLJ_CONSTITUTION.md`, decided by Articles **I.3** (WLJ owns
deterministic calculations) and **I.4** (the model owns interpretation/judgment; WLJ emits
no verdicts).

**Series:** Truth Assessment → Frontier Review → Transition Review → Constitutional Audit →
**this blueprint**. This document consolidates the four into one durable map. Every row is
anchored to source read at HEAD; unproven claims are marked unproven.

---

## Section 1 — Executive Truth decomposition

Executive Truth is not one thing. The Constitution forces it into five layers, and
ownership changes at two of the four boundaries:

```
1. EXECUTIVE DETERMINISTIC TRUTH   ── WLJ (I.1, I.3)   facts, counts, scores, classifications, single-authority state
        │  ownership boundary (I.3 → I.4): facts become judgment
2. EXECUTIVE REASONING             ── OpenAI (I.2, I.4) verdicts, prioritization, patterns-as-meaning, narrative
        │  (no ownership change: reasoning renders into language)
3. EXECUTIVE PRESENTATION          ── OpenAI + client   how the reasoned answer is delivered
        │  ownership boundary (I.4 → I.7): a decision becomes a mutation
4. EXECUTIVE ACTIONS               ── WLJ (I.7)          the safe, audited, deterministic write path
   EXECUTIVE CONTEXT               ── WLJ (I.1/II)       the assembled envelope that feeds layer 2 (spans, owns nothing it didn't already)
```

**Why each exists and where ownership changes:**

- **Executive Deterministic Truth (WLJ):** the reproducible substrate — "1 task due today,
  3 overdue; sleep debt present; latest weight 280.4." I.3 keeps *scores and
  classifications* here (`workload=heavy`, `cognitive_load=high`) because they are
  auditable calculations, not opinions.
- **Executive Reasoning (OpenAI):** the moment a fact becomes a *verdict* — "your biggest
  risk today is sleep," "focus on X first." **This is the first ownership boundary (I.3 →
  I.4).** The Constitution assigns everything past it to the model.
- **Executive Presentation (OpenAI + client):** wording, ordering, tone. Still reasoning's
  side; no WLJ-owned truth here.
- **Executive Actions (WLJ):** if a reasoned recommendation becomes a data change, **the
  second ownership boundary (I.4 → I.7)** returns control to WLJ's safe action path.
- **Executive Context (WLJ):** the `build_standing_context` envelope — an *assembly* of
  layer-1 truth handed to layer 2. It owns nothing new; it carries owned truth across the
  boundary.

**The whole transition is about one line: I.3 → I.4.** Everything else is already settled.

---

## Section 2 — Executive artifact ownership map

| Artifact | Producer | Consumer | Inputs | Outputs | Current owner | **Constitutional owner** | Class |
|---|---|---|---|---|---|---|---|
| Decision Authority `current_action` | `execution/decision_authority.py` | envelope, surfaces | execution state | primary_action + reason | WLJ | **WLJ (III.2)** | **Deterministic Truth** |
| Executive Context Envelope `build_standing_context` | `model_interface/service.py` | Model Interface / OpenAI | owned interfaces | one assembled envelope | WLJ | **WLJ (I.1/II)** | **Context (assembly)** |
| Mission Link | `purpose/mission_link.py` | envelope | mission map | primary mission, weight, why | WLJ | **WLJ (III.3)** | **Deterministic Truth** |
| Task horizons (→ workload/cog-load) | `_task_horizons` via `TaskQueries` | `interpret()` | certified Task authority | counts, bins | WLJ | **WLJ (I.3)** | **Deterministic Truth** |
| `recovery_needed`, `health_read` (direction) | `_health_read` | `interpret()` | domain state | bool, trend direction | WLJ | **WLJ (I.3)** | **Deterministic Truth** |
| `build_executive_summary` (status) | `core/cos_briefing` | brief, ops | domain states | summary sections | WLJ | **WLJ (I.3)** | **Deterministic Truth** |
| **`ExecutiveSignals.biggest_risk`** | `interpret()` | Understanding, brief | facts + intelligence | verdict text | WLJ | **OpenAI (I.4)** | **Reasoning** |
| **`priority_action` / highest_leverage** | `interpret()` | Understanding, decision support | ranked candidates | prioritized pick | WLJ | **OpenAI (I.4)** | **Reasoning** |
| **`primary_challenge`** | `interpret()` | Understanding | facts | "the real limiter" | WLJ | **OpenAI (I.4)** | **Reasoning** |
| **`executive_picture` / headline / workload_summary** | `interpret()` | narrative | facts | composed prose | WLJ | **OpenAI (I.4)** | **Reasoning** |
| **`patterns` / `opportunity` / `wins` prose** | `active_intelligence` → `interpret()` | Understanding | Insight/Prediction rows | interpreted text | WLJ | **OpenAI (I.4)** | **Reasoning** |
| `Insight` / `Prediction` / `GuidanceItem` | `ai_insights` / `ai_predictions` engines | `active_intelligence` | raw data | stored findings | WLJ | **Mixed** — record=Truth, content=Reasoning | **Mixed** |
| Deterministic Understanding | `understanding.py` | envelope | `interpret()` + context | assessment envelope | WLJ | **Mixed** — forwards A and B | **Mixed** |
| Executive Actions | `action_interface` / intent path | write path | confirmed intent | audited mutation | WLJ | **WLJ (I.7)** | **Action** |
| Operations executive status | `ops_executive` | Ops Wall / banner | integrity snapshot | overall_status, score | WLJ | **WLJ (I.3)** | **Deterministic Truth** |

**`ExecutiveSignals` split (the one Mixed artifact that matters), by Article:**

- **WLJ / I.3 (keep):** `workload`, `cognitive_load`, `recovery_needed`, `health_read`
  direction, horizon counts — auditable classifications/scores.
- **OpenAI / I.4 (belongs to the model):** `biggest_risk`, `priority_action`,
  `primary_challenge`, `intervention_required`, `executive_picture`, `patterns`/
  `opportunity`/`wins` prose — verdicts, prioritization, narrative.

---

## Section 3 — Deterministic Executive Truth: grounding status (actual runtime producers)

| Deterministic executive truth | Grounding | Certified authority supplying it (runtime, HEAD) |
|---|---|---|
| Task horizons / workload / cognitive_load | ✅ **Grounded** | `TaskQueries.due_today / overdue / due_within / no_due_date` (the certified Task authority, user-local since `a6a15b38`) |
| Decision Authority action | ✅ **Grounded** | `decision_authority.current_action` (single producer, CI-gated) |
| Mission Link | ✅ **Grounded** | `mission_link.get_mission_map` / `enrich_action` |
| Current Context (in envelope) | ✅ **Grounded** | `get_current_context_baseline` (certified overview tier) |
| Conversation State (in envelope) | ✅ **Grounded** | `conversation_state.read` (subject anchoring, `140e6c3c`) |
| Personal Truth (in envelope) | ✅ **Grounded** | `personal_truth` composer (single source) |
| `recovery_needed` (sleep debt) | ◐ **Partially grounded** | `_health_read` → domain state (canonical store; not the certified `get_history` authority) |
| `health_read` direction | ◐ **Partially grounded** | same — SAE snapshot, not `metric_date`/`get_history` |
| `build_executive_summary` status | ◐ **Partially grounded** | domain states |

**Single-domain truth tools** the model can call directly (`metric_date`, `get_history`,
`get_entity`, `get_domain_state`, `get_foundational_health_facts`) are ✅ **grounded and
certified** — but they are *not consumed by the executive composition*; they are the
model's own retrieval path. The executive **composition's** deterministic scalars are
grounded via `TaskQueries`/Decision Authority/Mission Link (✅) and the SAE snapshot (◐).

**Nothing in the deterministic-truth column is fully ungrounded.** The ungrounded material
(Insight/Prediction content) is classified **Reasoning** (§4), not Truth — which is why the
grounding line and the I.3/I.4 line coincide.

---

## Section 4 — Executive Reasoning inventory

| Reasoning output | WLJ produces it today? | OpenAI produces it? | WLJ exposing evidence instead? | Ownership correct today? |
|---|---|---|---|---|
| `biggest_risk` (verdict) | **Yes** | No | Partial (the facts exist too) | ❌ should be OpenAI (I.4) |
| `priority_action` (prioritization) | **Yes** | No | Partial | ❌ should be OpenAI (I.4) |
| `primary_challenge` | **Yes** | No | Partial | ❌ should be OpenAI (I.4) |
| `executive_picture` / headline (narrative) | **Yes** | No | No | ❌ should be OpenAI (I.4) |
| `patterns` (meaning) | **Yes** (from Insight rows) | No | `basis` is carried | ❌ should be OpenAI (I.4) |
| `opportunity` / `wins` (interpretation) | **Yes** | No | Partial | ❌ should be OpenAI (I.4) |
| Final conversational answer | No | **Yes** | — | ✅ correct |
| Coaching / recommendation prose to the user | No | **Yes** (model narrates) | — | ✅ correct |

**Finding:** the *final answer* to the user is correctly OpenAI's. The **intermediate
executive judgments** (`biggest_risk`, `priority_action`, patterns-as-meaning) are
constitutionally OpenAI's (I.4) but currently minted in WLJ and passed *pre-decided* to the
model. The model then narrates a verdict it did not form — the precise inversion of I.4.

**Mitigant (already present):** `understanding.py`'s expose-don't-invent doctrine drops the
sharpest reasoning (action verbs, disposition, prose) before the envelope. It is applied
~70% — it still forwards `biggest_risk`, `priority.executive`, `opportunity.text`. So the
boundary exists and is partially enforced by doctrine, not by a gate.

---

## Section 5 — Executive Context Envelope completeness

Does the envelope already contain everything OpenAI needs to *perform* the executive
reasoning WLJ currently pre-decides? **Assembled at `service.py :: build_standing_context`:**

| Envelope element | Present? | Runtime evidence |
|---|---|---|
| Current Context | ✅ | `ctx["current_context"] = get_current_context_baseline(...)` |
| Mission Link | ✅ | `ctx["missions"]`, `ctx["current_action"].primary_action` enriched |
| Conversation State | ✅ | `ctx["conversation_state"]` |
| Decision Authority | ✅ | `ctx["current_action"]` (reason + primary_action) |
| Deterministic Understanding | ✅ | `ctx["deterministic_understanding"]` (cache-first) |
| Personal Truth | ✅ | `ctx["personal_truth"]` |
| Execution state | ✅ | `ctx["execution_state"]` |
| Freshness | ◐ **Partial** | Understanding carries `status` (ok/pending); single-domain tool results carry `freshness`; the executive *assessments* carry `confidence` but not per-field freshness |
| Confidence | ◐ **Partial** | `understanding.confidence` + per-risk confidence present; not uniform across every assessment |
| Provenance / authority metadata | ◐ **Partial** | Single-domain tool envelopes declare `authority` (127/127); the executive assessments do **not** declare a certified authority (they derive from the heuristic pipeline) |

**Verdict:** the envelope **already contains the deterministic substrate** OpenAI needs —
Current Context, Mission Link, Conversation State, Decision Authority, Personal Truth,
execution state, and the deterministic scalars. What it is **missing is not deterministic
truth and not a new structure** — it is:

- **missing exposure/grounding:** the executive assessments lack certified-authority
  provenance because they are composed from the heuristic pipeline rather than the certified
  authorities;
- **not missing reasoning:** the reasoning the envelope would let OpenAI perform is exactly
  the reasoning WLJ currently pre-decides (§4).

So the envelope is **structurally complete**; the gap is *what feeds it* (grounding) and
*what it still pre-decides* (the I.4 fields), not the envelope itself.

---

## Section 6 — Executive Truth grounding map (as it exists today)

Each node: **[owner] — current implementation — certification — runtime evidence.**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ CERTIFIED DETERMINISTIC TRUTH AUTHORITIES                                     │
│ [WLJ · I.1/I.3]                                                               │
│ TaskQueries ✓cert · Decision Authority ✓cert(CI) · Mission Link ✓ ·          │
│ metric_date ✓cert · get_history ✓cert · calendar_day ✓cert(24 gates) ·       │
│ Current Context ✓cert · Conversation State ✓ · Personal Truth ✓ ·            │
│ authority metadata ✓ (127/127 declared)                                      │
│ evidence: WLJ_RETRIEVAL_PLATFORM_CERTIFICATION, WLJ_CALENDAR_BOUND_TRUTH      │
└───────────────┬──────────────────────────────────────┬──────────────────────┘
                │ (certified path)                      │ (heuristic path — NOT certified)
                ▼                                       ▼
┌──────────────────────────────┐        ┌──────────────────────────────────────┐
│ EXECUTIVE DETERMINISTIC TRUTH│        │ HEURISTIC INTELLIGENCE PIPELINE       │
│ [WLJ · I.3]                  │        │ [WLJ — content is Reasoning · I.4]    │
│ workload, cognitive_load,    │        │ Insight / Prediction / GuidanceItem   │
│ recovery_needed, horizons    │        │ → active_intelligence                 │
│ impl: interpret() scalars    │        │ impl: ai_insights/ai_predictions      │
│ cert: ◐ (behaviorally tested)│        │ cert: ✗ (ungrounded, uncertified)     │
│ evid: _task_horizons→        │        │ evid: cos_intelligence.py reads rows; │
│   TaskQueries ✓              │        │   ZERO refs to certified authorities  │
└───────────────┬──────────────┘        └──────────────────┬───────────────────┘
                │                                           │
                └─────────────────┬─────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ EXECUTIVE CONTEXT ENVELOPE  [WLJ · I.1/II — assembly, owns nothing new]       │
│ build_standing_context: current_context, missions, current_action,           │
│ conversation_state, personal_truth, execution_state, deterministic_           │
│ understanding   │ cert: structure sound; carries partial freshness/           │
│ confidence; executive assessments lack certified provenance                  │
│ evidence: service.py:132-200; understanding.read (cache-first)               │
│ ⚠ ALSO carries I.4 verdict fields (biggest_risk, priority.executive) it      │
│   should not pre-decide — the one blur (§4)                                   │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ OPENAI EXECUTIVE REASONING  [OpenAI · I.2/I.4]                                │
│ interprets the envelope → verdict, prioritization, narrative                 │
│ cert: ✗ (no automated Owner-2 harness for composed executive answers)        │
│ evidence: model_interface runtime; prior probes were disposable scripts      │
│ ⚠ currently narrates verdicts WLJ pre-decided rather than forming them        │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  ▼
                     CONVERSATION  [OpenAI · the product]
                     cert: ✗ automated; ✓ one prod-validated slice (weight)
```

**Reading the map:** the top authority tier is certified. Two paths descend — a **certified
path** (TaskQueries/Decision Authority/Mission Link → deterministic scalars) and a
**heuristic path** (Insight/Prediction → reasoning-shaped content). Both merge in the
envelope. The envelope is structurally sound but carries two irregularities: it lacks
certified provenance on the assessments, and it pre-decides I.4 verdicts. OpenAI reasoning
and the final conversation are **uncertified end-to-end** (no Owner-2 harness).

---

## Section 7 — Constitutional compliance per producer

| Producer | Boundary effect | Article | Evidence | Issue type |
|---|---|---|---|---|
| Decision Authority | **Strengthens** | III.2 | Single producer, CI-gated | — |
| Executive Context Envelope | **Strengthens** | I.1/II | Assembles, interprets nothing | — |
| Mission Link | **Strengthens** | III.3 | Deterministic facts | — |
| `interpret()` deterministic scalars | **Preserves** | I.3 | Auditable classifications, grounded on `TaskQueries` | — |
| Deterministic Understanding | **Preserves (imperfectly)** | I.4 | Expose-don't-invent doctrine defends the line; forwards residual verdicts | **adoption** (complete the filter) |
| `interpret()` verdict fields | **Blurs** | I.4 | WLJ emits `biggest_risk`/`priority_action` | **adoption** (move to model) |
| `active_intelligence` / Insight / Prediction | **Blurs** | I.4 + III.1 grounding | Reasoning-shaped content, ungrounded from certified truth | **grounding + adoption** |
| `_health_read` via SAE snapshot | **Preserves (weakly)** | III.1 | Canonical store, not the certified retrieval authority | **grounding** (adoption) |
| Operations executive status | **Latent risk, not an active violation** | III.1 (operational) | ⚠️ **Correction:** `b858e060` FALSIFIED the two-authority *incident* — 0 COAS notifications, 4 warning-only unnotified alerts; the observed contradiction was **one integrity authority flapping across the 70 boundary + a mislabeled always-green badge**, not two authorities. The two-authority *architectural risk* remains real but was **not** the proven cause. | **implementation** (badge label) + latent architecture risk |

**No producer is a clean Article violation.** Every concern is **adoption, grounding, or
implementation** — never architecture, never requiring a Constitutional Review.

---

## Section 8 — Executive Truth implementation readiness

**Are the ownership questions resolved enough to begin? — Yes.** Concretely:

| Question | Resolved? | Answer |
|---|---|---|
| What does WLJ own? | ✅ | Deterministic scalars (workload, cognitive_load, recovery, health direction, horizons), Decision Authority, Mission Link, Current Context, envelope assembly, actions (I.1/I.3/I.7/II/III) |
| What does OpenAI own? | ✅ | Verdicts, prioritization, patterns-as-meaning, narrative, the conversation (I.2/I.4) |
| What remains deterministic? | ✅ | The §2 A-rows; already mostly grounded (§3) |
| What remains reasoning? | ✅ | The §4 rows; currently mis-located in WLJ |
| What requires grounding? | ✅ | `health_read` → certified authority; the assessments' inputs |
| What requires certification? | ✅ | Owner-2 harness for composed executive answers; an executable I.4 gate; cross-domain tuples |

**Remaining unknowns (named, not architectural):**
1. Whether any *single* executive field is computed twice by two producers (strict III.1) is
   **not proven** at the field level — reported as a grounding concern, not a violation.
2. Whether the heuristic pipeline's assessments are *substantively correct* is **unknown** —
   only that they are ungrounded and uncertified.
3. The I.4 boundary is held by **doctrine, not an executable gate** — a certification gap.

None of these is an *architectural* unknown. Each is an adoption/grounding/certification
question with a defined answer path inside the Constitution.

---

## Section 9 — Risks

**Risks of implementing before this ownership model is complete** (it is now complete — but
had implementation begun without it):

| # | Risk | Severity | Likelihood | Why |
|---|---|---|---|---|
| 1 | Re-grounding without the ownership line → moving reasoning into WLJ | High | High (was) | Without the I.3/I.4 split, a "grounding" refactor could deepen the I.4 blur |
| 2 | Certifying the wrong layer | High | Medium | Certifying WLJ-emitted verdicts would *lock in* the I.4 inversion |
| 3 | Building the Owner-2 harness against pre-decided verdicts | Medium | Medium | Would test that WLJ's verdict reaches the user, not that the model formed it |

**This blueprint removes risks 1–3** by fixing ownership *before* a line of implementation.

**Risks of delaying implementation now that ownership is understood:**

| # | Risk | Severity | Likelihood | Evidence |
|---|---|---|---|---|
| 1 | The flagship daily surface stays uncertified | High | High | Owner-2 at 0% automation; every fix "protected by memory" |
| 2 | Diminishing returns on further single-domain Truth | Medium | High | 58% cells certified; next increments low-traffic (Finance 0, artifacts 0); F5 flagged customer-irrelevant |
| 3 | Product thesis delayed | Medium | Medium | Vision: "the conversation IS the product" — the uncertified surface is the product |

**Net:** the ownership model being complete, the balance now tips toward *proceeding* —
delay costs more than the (now-removed) risk of premature implementation.

---

## Section 10 — Final architectural opinion

1. **Is the constitutional ownership of Executive Truth now understood? — Yes, completely.**
   Every artifact is classified by Article (§2), the deterministic substrate's grounding is
   mapped to actual runtime producers (§3), the reasoning is inventoried (§4), and the
   envelope's completeness is established (§5). The I.3 → I.4 line is drawn field by field.

2. **Is there any remaining architectural uncertainty? — No.** No Article needs changing; no
   subsystem needs inventing; the Executive Context Envelope already exists and is
   structurally complete (§5); the certified authorities already exist (§6 top tier). The
   three named unknowns (§8) are grounding/certification questions, not architecture.

3. **Is the remaining work almost entirely implementation, grounding, and certification? —
   Yes.** Zero architecture (§7: every concern is adoption/grounding/implementation). The
   work is: ground `health_read` and the assessments on the certified authorities; complete
   the expose-don't-invent filter so WLJ stops emitting I.4 verdicts; build the Owner-2
   harness and an executable I.4 gate.

4. **Can Executive Truth implementation proceed entirely inside the current Constitution? —
   Yes.** The Constitution is the specification: I.3 keeps the scalars, I.4 relocates the
   verdicts, III.1/IV.3 grounds the inputs on the one authority, IV.4 exposes facts instead
   of inventing verdicts, I.7 owns the resulting actions. Not one Article obstructs the
   transition; every one of them defines a piece of it.

5. **Does this document establish the stable ownership model future implementation should
   follow? — Yes.** §2 is the authoritative artifact-to-Article map; §3 the grounding
   ledger; §6 the as-built dependency map. Future Executive Truth work has one job: **make
   the running system match this map** — WLJ owning §2's A-rows (grounded per §3), OpenAI
   owning §2's B-rows, the envelope (§5) carrying certified provenance, and the whole path
   certified end-to-end (§8).

**One honest correction recorded this session:** the "two operational authorities" finding
carried since the Transition Review was **partially falsified** by row-level evidence
(`b858e060`) — the observed Operations contradiction was a single flapping authority plus a
mislabeled badge, not two authorities messaging. The two-authority *architectural risk*
remains real and latent; it was simply not the cause of the one incident it was blamed for.
Corrected here so the blueprint carries only what the evidence supports.

> **The constitutional ownership of Executive Truth is fully resolved. What remains is not
> architecture but fidelity — making the running system match this map — and every step of
> that fidelity is specified by the Constitution itself.**
