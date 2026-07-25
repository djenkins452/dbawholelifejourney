# WLJ — Executive Layer Constitutional Audit

**Date:** 2026-07-24 · **Type:** constitutional audit (no implementation, no redesign)
**HEAD assessed:** `b18c2469`
**Measured against:** `02_WLJ_CONSTITUTION.md` (the authority)
**Series:** Truth Assessment → Frontier Review → Executive-Truth Transition Review → *this*

**Governing stance (from the brief):** the Constitution is correct. Every apparent
inconsistency is first tested for resolution **inside** the Constitution. No
constitutional change is proposed. The question is never "should this exist" — it is
**"who constitutionally owns this?"**

**Evidence rule:** every classification is anchored to source read at HEAD. Where a strict
claim cannot be proven, it is marked unproven rather than asserted.

---

## Section 1 — Executive inventory

| Artifact | Purpose | Producer | Consumers | Inputs | Outputs | Deterministic? |
|---|---|---|---|---|---|---|
| **`ExecutiveSignals`** (`interpret()`) | The single whole-life "executive judgment" object | `chatgpt_cos/executive_interpretation.py :: interpret()` | Deterministic Understanding, executive brief, decision support | task horizons, health read, exec summary, `active_intelligence`, user check-in evidence | workload, cognitive_load, recovery, health_read, biggest_risk, primary_challenge, priority_action, patterns, predictions, wins, opportunity, executive_picture | **Deterministic-heuristic** (reproducible; no model call) |
| **`active_intelligence`** | Surface persisted insights/predictions/patterns | `cos_intelligence.py` | `interpret()`, narrative | `Insight`, `Prediction`, `DomainCorrelation`, `GuidanceItem` rows | risks, wins, predictions, patterns, guidance | Deterministic read of persisted rows |
| **`Insight`** | Stored heuristic finding | `ai_insights` engines (background) | `active_intelligence` | raw domain data | insight records | Heuristic pipeline |
| **`Prediction`** | Stored forward-looking projection | `ai_predictions` engines (background) | `active_intelligence` | raw domain data | prediction records | Heuristic pipeline |
| **`GuidanceItem`** | Stored guidance | intelligence pipeline | `active_intelligence` | raw domain data | guidance records | Heuristic pipeline |
| **Deterministic Understanding** (`understanding.py`) | Cache-first whole-life assessment envelope for the Model Interface | `model_interface/understanding.py :: _compose/read` | Model Interface standing context | `interpret()`, standing context, day_continuity | executive assessments, priority, patterns, predictions, wins, opportunity, direction, continuity | Deterministic composition (cache-first) |
| **Executive Context / standing context** (`build_standing_context`) | Assemble owned interfaces for the model per turn | `model_interface/service.py` | Model Interface / OpenAI | AI Relationship, Understanding, Current Context, Conversation State, Personal Truth, Mission Link, Decision Authority | one assembled envelope | Deterministic **assembly** |
| **Executive Briefing** | Deterministic day briefing | `core/cos_briefing/*` | brief surfaces | exec summary, sections | briefing text/sections | Deterministic |
| **`build_executive_summary`** | Ops/exec status summary | `core/cos_briefing/executive_summary.py` | `interpret()`, ops | domain states | summary sections | Deterministic |
| **Executive Interpretation** | (= `interpret()`) | as above | as above | as above | as above | as above |
| **Decision Authority** | "What to do now" | `execution/decision_authority.py :: current_action` | standing context, surfaces | execution state | primary_action + reason | Deterministic, single producer (CI-gated) |
| **Operations executive output** | System-status executive summary | `ops_executive.build_executive_summary` | Ops Wall, CoS banner/dot | integrity snapshot | overall_status, score | Deterministic |

---

## Section 2 — Constitutional ownership audit

Classification per artifact: **A = Deterministic Truth** (WLJ; I.1/I.3), **B = Reasoning**
(the model; I.2/I.4), **C = Mixed**.

| Artifact | Class | Reasoning |
|---|---|---|
| Decision Authority (`current_action`) | **A** | "What to do now" is explicitly deterministic truth with one authority (III.2). Clean. |
| Executive Context / `build_standing_context` | **A** | It **assembles** owned interfaces; it produces no judgment of its own. Assembly is not reasoning. |
| Mission Link (in the envelope) | **A** | III.3 — deterministic relationship truth by Article. |
| `build_executive_summary` / Operations executive | **A (with a III.1 issue, §4)** | Deterministic status aggregation. |
| Insight / Prediction / GuidanceItem | **C** | The *record* is deterministic state (A); the *content* ("protein is low", "you'll miss this goal") is an interpretation/projection (B) computed by a heuristic engine. |
| `active_intelligence` | **C** | Deterministic **read** (A) of records whose **content** is reasoning-shaped (B). |
| **`ExecutiveSignals` / `interpret()`** | **C — the crux** | Split precisely below. |
| Deterministic Understanding | **C** | Deterministic composition (A) that forwards a mix of A and B fields from `interpret()`. |

### The precise split of `ExecutiveSignals` (the central artifact)

The Constitution itself supplies the dividing line: **I.3** grants WLJ "aggregates, scores,
momentum, timing"; **I.4** reserves "verdicts ('on track')… interpretation and judgment"
for the model.

| Field | Owner | Why |
|---|---|---|
| `workload` (light…overloaded) | **A — Truth (I.3)** | A deterministic **binning of a count** (`_task_horizons`). A score/classification. |
| `cognitive_load` (low/moderate/high) | **A — Truth (I.3)** | Deterministic function of active tasks + recovery. |
| `recovery_needed` (bool) | **A — Truth (I.3)** | Deterministic from sleep debt. |
| `health_read` (improving/stable/declining) | **A — Truth (I.3)** | A trend **direction** — a classification, not a verdict, *provided its input is canonical*. |
| task/horizon counts | **A — Truth (I.1)** | Raw canonical counts. |
| `biggest_risk` (free text) | **B — Reasoning (I.4)** | A **verdict** — "the main thing to watch." The code itself ranks it as "JUDGMENT." |
| `priority_action` / `highest_leverage` | **B — Reasoning (I.4)** | **Prioritization** — the code comment: *"Highest leverage is a JUDGMENT."* Prioritization is reasoning by the brief's own definition. |
| `primary_challenge` ("the real limiter") | **B — Reasoning (I.4)** | Judgment. |
| `patterns` / `opportunity` / `wins` prose | **B — Reasoning (I.4)** | Interpretation + narrative. |
| `executive_picture`, `headline`, `workload_summary` | **B — Reasoning (I.4)** | Composed narrative. |
| `intervention_required` (bool) | **B — Reasoning (I.4)** | A judgment ("should act"). |

**`ExecutiveSignals` is Mixed by construction** — and its own docstring says so: *"Produce
ExecutiveSignals — **ALL executive judgment** — from deterministic facts."* The deterministic
classifications are constitutionally WLJ's; the verdict/prioritization/narrative fields are
constitutionally the model's.

---

## Section 3 — Truth audit (do the A-classified outputs consume the certified authorities?)

Runtime producers, read at HEAD — **not** speculation:

| Deterministic executive input | Actual runtime producer | Certified authority? |
|---|---|---|
| Task horizons (`workload`, `cognitive_load` input) | `TaskQueries.due_today / overdue / due_within / no_due_date` | ✅ **Yes** — the certified Task authority (made user-local in `a6a15b38`) |
| `health_read` | `get_domain_state(user, ...)` → SAE snapshot | ◐ **Partial** — the SAE projection (a store), not the certified `get_history`/`metric_date` authorities |
| `_exec_summary` | `core/cos_briefing/executive_summary.build_executive_summary` | ◐ domain states |
| `risks / wins / predictions / patterns` | `active_intelligence` → `Insight` / `Prediction` rows | ❌ **No** — the older heuristic pipeline |

**Finding:** the picture is *split*, not uniformly ungrounded (correcting the prior review's
broad framing). The **task-derived deterministic classifications already consume the
certified authority** (`TaskQueries`). The **health read consumes the SAE snapshot** (canonical
store, but not the certified retrieval authority). The **reasoning-shaped fields consume the
heuristic Insight/Prediction pipeline** and touch none of `metric_date` / `get_history` /
`calendar_day` / `authority_declarations` (grep at HEAD: zero references in `chatgpt_cos/`,
`cos_intelligence.py`, `understanding.py`).

So: the parts that are **most clearly Truth (I.3)** are the parts that are **already best
grounded**; the parts grounded in the heuristic pipeline are the parts that are **most
clearly Reasoning (I.4)**. That alignment is fortunate — it means grounding and the
truth/reasoning split are the *same* line.

---

## Section 4 — Parallel authority audit (proven cases only)

| Case | Status | Evidence |
|---|---|---|
| Task horizons | ✅ **No violation** | Single authority — `TaskQueries`. Reused, not re-derived (IV.3 honored). |
| Decision Authority | ✅ **No violation** | III.2 — one producer, CI-gated against a second selector. |
| **Executive deterministic inputs vs certified authorities** | ⚠️ **Grounding concern, strict double-producer NOT proven** | The heuristic pipeline (`Insight`/`Prediction`) computes domain assessments from raw data while the certified authorities (`get_history`/`metric_date`) compute the underlying facts. The two stacks share no code (proven). Whether they compute the *identical* fact twice (a strict III.1 double-producer) is **not proven at the field level** — the Insight content ("protein is low") is a coarser assessment than the certified aggregate (75 g). Reported honestly as a **grounding/parallel-source concern**, not a proven III.1 violation. |
| **Operations executive** | ⚠️ **Proven two-authority** (adjacent) | `WLJ_OPERATIONS_TRUTH_PATH_INVESTIGATION.md` proves COAS scores vs `executive.overall_status` diverge — a proven parallel authority for operational *status*, not for personal truth. |

**No proven parallel authority for a personal-truth domain inside the executive layer.** The
one proven parallel authority is in Operations status.

---

## Section 5 — Reasoning audit (does WLJ produce reasoning, or expose truth?)

The honest constitutional answer: **WLJ currently produces both**, and the architecture's
*own doctrine* already names the line it should hold.

- **`interpret()` produces reasoning-shaped outputs** — `biggest_risk`, `priority_action`,
  `primary_challenge`, `executive_picture`. By I.4 these are the model's. This is real, and
  the code labels itself "ALL executive judgment."
- **But Deterministic Understanding already filters toward truth.** Its docstring:
  *"EXPOSE-DON'T-INVENT… we deliberately expose only ASSESSMENTS (what things mean), NOT
  prescriptions/recommendations (disposition, 'batch them now', highest-leverage action
  verbs, composed prose) — those are Reasoning and belong to the model."* The
  constitutionally-governed runtime (the Model Interface) is where this doctrine is applied.
- **The doctrine is applied incompletely.** `understanding.py` still forwards `biggest_risk`,
  `priority.executive`, and `opportunity.text` — verdict/prioritization fields I.4 assigns to
  the model. It drops action verbs and prose; it does not yet drop verdicts.

**So the constitutional line already exists in the codebase; it is drawn in the right place
(the Model Interface boundary) and applied ~70% of the way.** WLJ producing the deterministic
*assessments* (workload=heavy, recovery_needed) is I.3-legitimate. WLJ producing the
*verdicts* (biggest_risk, the priority selection) is the residual I.4 tension.

This is **not** a criticism of heuristic behavior for existing (per the brief). It is a
statement of *which layer constitutionally owns each field* — and the answer is that a
minority of `ExecutiveSignals` fields are owned by the model but currently emitted by WLJ.

---

## Section 6 — Boundary audit (Truth → Executive Context → Reasoning)

| Producer | Effect on the boundary | Evidence |
|---|---|---|
| Decision Authority | **Strengthens** | Single deterministic producer the model consumes; textbook III.2. |
| Executive Context Envelope (`build_standing_context`) | **Strengthens** | Assembles owned facts and hands them to the model; it interprets nothing. |
| Mission Link | **Strengthens** | Deterministic facts (III.3). |
| Deterministic Understanding | **Preserves (imperfectly)** | Its expose-don't-invent doctrine actively defends the boundary; the residual verdict fields it forwards slightly blur it. |
| `interpret()` deterministic scalars | **Preserves** | I.3 calculations grounded in canonical inputs. |
| `interpret()` verdict/prioritization fields | **Blurs** | WLJ emitting `biggest_risk`/`priority_action` puts judgment on WLJ's side of the boundary (I.4). |
| `active_intelligence` / Insight / Prediction | **Blurs** | Reasoning-shaped content produced by a WLJ engine, not the model. |
| Operations two-authority | **Potentially violates (III.1, operational)** | Proven divergent producers for status. |

**Net:** the boundary is **structurally sound and actively defended** at the Model Interface,
with two localized blurs — the executive verdict fields and the heuristic-intelligence
content — both on the *reasoning* side of the line, both resolvable by adoption.

---

## Section 7 — Executive Truth grounding (current state, precisely)

| Executive deterministic output | Grounded on… | Constitutional status | Needs |
|---|---|---|---|
| Task horizons / workload / cognitive_load | **Certified authority** (`TaskQueries`) | ✅ Correct | nothing |
| Decision Authority action | Certified execution state | ✅ Correct | nothing |
| Mission Link | Deterministic mission truth | ✅ Correct | nothing |
| `health_read` | SAE snapshot (canonical store) | ◐ Acceptable, not best | **adoption** — move to the certified health authority |
| risks / patterns / predictions / wins | Heuristic `Insight`/`Prediction` pipeline | ◐ Reasoning-side, ungrounded from certified truth | **adoption + certification** |
| verdict fields (`biggest_risk`, `priority_action`, `executive_picture`) | Computed in WLJ | ◐ I.4 tension | **alignment** — expose facts, let the model render the verdict |

**Already constitutionally correct:** everything grounded on `TaskQueries` / Decision
Authority / Mission Link. **Requires only adoption:** `health_read` grounding; completing the
assessment-vs-verdict separation. **Requires certification:** proving the composed executive
answer against certified truth end-to-end (no Owner-2 harness exists).

---

## Section 8 — Constitutional compliance

**Does the Executive layer violate any Article?**

**No Article is violated in a way that requires a Constitutional Review — but there are two
compliance *gaps*, both resolvable entirely inside the existing Constitution.**

| Article | Status | Evidence | Resolvable within the Constitution? |
|---|---|---|---|
| **I.1 / I.3** (WLJ owns truth & calculations) | ✅ Honored | Deterministic scalars are legitimate I.3 scores/classifications; grounded on canonical inputs | — |
| **I.2** (no reasoning engine in WLJ) | ⚠️ **Tension, not clean violation** | `interpret()` computes judgment-shaped fields and calls itself "executive judgment." But it builds no *mind* — it is deterministic heuristics over facts, and the Model Interface doctrine already narrows what reaches the model. | ✅ Yes — I.4 separation (adoption) |
| **I.4** (WLJ emits no verdicts; model interprets) | ⚠️ **Partial gap** | WLJ emits `biggest_risk`, `priority_action`, `primary_challenge` — verdict/prioritization fields | ✅ Yes — complete the expose-don't-invent doctrine `understanding.py` already applies |
| **III.1** (one authority per domain) | ⚠️ **Grounding concern** (strict double-producer unproven, §4) | Executive reasoning-fields derive from the heuristic pipeline, not the certified authority | ✅ Yes — grounding adoption |
| **III.2 / III.3** (Decision Authority, Mission Link) | ✅ Honored | Single producers, consumed | — |
| **II** (Current Context) | ✅ Honored | Assembled, authoritative | — |
| **IV.2 / IV.3 / IV.4** (improve truth, reuse, expose) | ⚠️ **The method for the fix** | These Articles *prescribe the resolution*: ground on existing certified truth (IV.3 reuse), expose facts rather than invent verdicts (IV.4), improve truth before intelligence (IV.2) | ✅ Yes — by definition |

**Critical point:** the Constitution does not merely *permit* the resolution — **it prescribes
it.** I.4 says WLJ exposes facts and the model interprets; IV.3 says reuse the existing
authority; IV.4 says expose before inventing. Bringing the executive layer into full
compliance is *executing the Articles as written*, not amending them.

**No enforcement gap is hidden:** `test_constitution_contract.py` does not currently assert
the I.4 boundary on the executive layer (it checks documents, naming, fabrication). The I.4
line is held by doctrine (`understanding.py`), not by an executable gate — a certification
opportunity, not a violation.

---

## Section 9 — Executive Truth readiness (by constitutional ownership)

The remaining work, classified by what the Constitution says it is:

| Category | Share | What |
|---|---|---|
| **Architecture** | **~0%** | None required. No Article changes; no new subsystem. The prior reviews' "no new architecture" holds here too. |
| **Truth adoption** | **~40%** | Ground `health_read` and the executive assessments on the certified authorities (IV.3 reuse); ground the reasoning-fields' inputs on certified truth. |
| **Executive Truth grounding** | *(subset of adoption)* | Same line — the deterministic scalars are already grounded; the rest is adoption. |
| **Alignment (I.4 separation)** | **~20%** | Complete the assessment-vs-verdict split `understanding.py` began, so WLJ exposes facts and the model renders verdicts. |
| **Certification** | **~40%** | Owner-2 harness for composed executive answers; an executable I.4 gate; cross-domain tuples. |
| **Reasoning quality / Experience / new domains** | **0% (deferred)** | Not constitutional-compliance work; deferred per the prior review. |

**The remaining work is adoption + alignment + certification — none of it architectural, none
of it requiring a Constitutional Review.**

---

## Section 10 — Final opinion

1. **Is the Executive layer constitutionally sound? — Substantially yes.** Its backbone —
   Decision Authority, Executive Context assembly, Mission Link, task-grounded scalars — is
   textbook-compliant (III.2, III.3, I.3). It has two compliance *gaps* (I.4 verdict emission;
   grounding some inputs on the heuristic pipeline), neither of which is a clean Article
   violation and both of which the Constitution itself prescribes the fix for.

2. **Is Executive deterministic truth clearly separated from OpenAI reasoning? — Partially,
   and the line is drawn in the right place.** The `understanding.py` expose-don't-invent
   doctrine is the constitutional boundary made real; it is applied ~70% (it drops prose and
   action verbs, still forwards verdict fields). The separation exists but is incomplete and
   not executably enforced.

3. **Are any Executive artifacts owned by the wrong constitutional layer? — Yes, a minority.**
   The verdict/prioritization/narrative fields of `ExecutiveSignals` (`biggest_risk`,
   `priority_action`, `primary_challenge`, `executive_picture`) are constitutionally the
   model's (I.4) but are produced in WLJ. The deterministic scalars are correctly WLJ's.

4. **Is the remaining work architectural, adoption, or certification? — Adoption + alignment +
   certification. Zero architectural.** No Article changes; no new subsystem; no Constitutional
   Review. This confirms and sharpens the prior review's thesis at the constitutional level.

5. **Can the Executive Truth transition be completed entirely inside the existing Constitution?
   — Yes, unambiguously.** Every gap resolves by *executing the Articles as written*: I.3 keeps
   the scalars in WLJ, I.4 moves the verdicts to the model, III.1/IV.3 grounds the inputs on
   the one certified authority, IV.4 exposes facts instead of inventing verdicts. **The
   Constitution is not in tension with the transition — it is the specification for it.**

**Unknowns, on the record:** whether the heuristic Insight/Prediction content is *incorrect*
is unknown (only that it is reasoning-shaped and ungrounded from certified truth); whether any
individual executive field is computed twice by two producers (strict III.1) is **not proven**
and is reported as a grounding concern, not a violation; and the I.4 boundary is currently
held by doctrine, not by an executable gate — which is itself the clearest certification
opportunity the audit surfaced.
