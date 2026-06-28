# The Medication Intelligence Canon

**The permanent philosophical reference for the Medication & Supplement Intelligence domain of Whole Life Journey.**

*Status: canonical. This is the constitution for the domain — principles, not implementation. It should remain correct as the code beneath it changes. Where it touches schema, it does so only to fix ownership, never to dictate design. Companion planning (Architecture, Gap Analysis, UX, Roadmap) lives in the `MEDICATION_SUPPLEMENT_INTELLIGENCE_V2_*` documents; this Canon outranks them in matters of principle and outlives them.*

*Last reviewed: 2026-06-27.*

---

## Preamble

This domain governs how Whole Life Journey understands what a person takes into their body to treat, manage, or improve their health — medications and supplements — and what that means for their life over time. It is subordinate to the **WLJ Architecture Laws** (`WLJ_ARCHITECTURE_LAWS.md` — the platform constitution) and the Visual Truth Contract; nothing here overrides them. Where this Canon and an implementation disagree, the implementation is wrong until this Canon is deliberately amended.

> **Amendment — 2026-06-28 (Architecture Laws promotion).** Platform Laws now
> explicitly govern this domain: **Law 0 (Intent Before Retrieval)** — a medication
> question is scoped to the medication/intake domain and answered as asked, never
> substituted with other loaded state; **Law 3 (Orchestration Before Reasoning)** —
> compound medication-education questions ("list each medicine and what each is for")
> are **retrieve → enumerate → enrich-each → assemble → narrate** via the
> Enumeration+Enrichment pattern, never a single reasoning prompt; and **Law 1/2
> (Freshness/Confidence Before Reasoning)** — adherence, refills, and observations
> declare data freshness and confidence before narration (e.g. "I don't have today's
> doses yet"), never presenting stale or pending state as current. See
> `WLJ_ARCHITECTURE_LAWS.md`.

---

## Section 1 — Domain Definition

**Medication Intelligence is the capability that turns a list of substances into an understood treatment.**

Its purpose is not to remind a person to take a pill. Its purpose is to help them understand *what* they take, *why*, whether they take it *consistently*, how their treatment *changes over time*, how it *interacts with the rest of their life*, and what is *worth discussing with their physician*.

It exists because the hardest part of managing one's health is not remembering the dose — it is making sense of treatment over months and years, across a body that also sleeps, eats, moves, and bleeds glucose. That understanding is exactly what isolated tools cannot provide, and exactly what WLJ — which already holds the rest of the person's health — uniquely can.

**The problems it solves:** fragmented memory of a treatment history; invisible cause-and-effect between medication and the rest of life; the anxiety and inefficiency of an unprepared physician visit; the quiet erosion of adherence; and the absence of anyone — human or system — whose job is to help the person *understand*, not just *comply*.

**How it differs:**
- **Medication reminder apps** optimize for the alarm. We optimize for understanding; the reminder is table stakes, not the product.
- **Pill trackers** record events. We record a *treatment story* — changes, reasons, outcomes — and read it against the whole person.
- **Pharmacy apps** serve the dispensing relationship. We serve the *person's* understanding of their own treatment, independent of any pharmacy.
- **Apple Health medication tracking** is a well-built ledger. We are a *companion* — a Chief of Staff who narrates meaning over that ledger and prepares the person for their doctor.

The one-sentence definition: *Medication Intelligence helps a person understand whether their treatment is working, and act on that understanding safely.*

---

## Section 2 — Relationship to Treatment Intelligence

A conclusion has matured across planning: **Medication Intelligence is the first and foundational instrument of a larger future capability — Treatment Intelligence.**

A medication is a *means*. A treatment is the *intent* behind it — a goal pursued through one or more therapies, measured against the body's real response. Today, medications are the richest, most structured, most consequential therapy WLJ can observe, so they are where treatment understanding must begin. But treatment is broader: it includes therapies that are not pills — a diet protocol, an exercise prescription, a sleep intervention, a CPAP, a physical-therapy regimen.

**Where Medication Intelligence stops:** at the boundary of *substances taken into the body* — their identity, dose, schedule, adherence, inventory, history, and the observations that surround them.

**Where Treatment Intelligence begins:** at the level of *clinical intent* — grouping therapies (medication and non-medication) under a goal and a condition, and reasoning about whether that *intent* is being achieved.

**Should Medication Intelligence remain a standalone first-class domain?** Yes. It is coherent, bounded, and independently valuable. It must not be dissolved into a vaguer abstraction.

**Should Treatment Intelligence become a higher-order layer?** Yes — *eventually*, and *above*, not *instead of*. Treatment Intelligence is a composition layer that sits over Medication Intelligence (and later over nutrition, exercise, and other therapeutic domains), borrowing their observations to answer goal-level questions. The `TreatmentPlan` concept is the seam where this future attaches.

**Design rule for today:** build Medication Intelligence as a complete first-class domain, but keep its contracts *treatment-shaped* — group-able by goal and condition, observation-bearing, domain-agnostic in naming — so that Treatment Intelligence can later compose over it without a rewrite. **Do not rename anything now.** Design additively for the future; promote when the future arrives.

---

## Section 3 — Canonical Concepts

Each concept is defined by what it **owns** and what it **does not own**. Ownership is exclusive.

- **Medication** — a substance taken to treat or manage a condition. *Owns:* its clinical identity, dose, route, and prescription context. *Does not own:* the schedule (it references one), the dose-events (logged separately), or any judgment of effectiveness.
- **Supplement** — a substance taken to support or optimize health, distinguished from medication by intent and regulatory class, not by mechanism. *Owns:* the same identity surface as a medication, plus its supplement classification. *Does not own:* any implied clinical claim.
- **Treatment** — the clinical intent (a goal for a condition) pursued through one or more medications/supplements/therapies. *Owns:* the grouping and the goal narrative. *Does not own:* the individual substances (it references them) or their adherence math.
- **Dose** — the amount of a substance taken at one time. *Owns:* the quantity-and-unit fact. *Does not own:* when it is scheduled or whether it was taken.
- **Schedule** — the plan of when doses should occur. *Owns:* timing and recurrence. *Does not own:* the substance, or the record of what actually happened.
- **Adherence** — the degree to which actual intake matched the schedule. *Owns:* a single, computed measure. *Does not own:* a value-judgment of the person; it is an observation, never a grade.
- **Inventory** — the estimated remaining supply. *Owns:* the supply estimate and refill horizon. *Does not own:* certainty; it is always an estimate, honestly labeled.
- **History** — the append-only record of how a treatment changed (started, dose changed, stopped, provider changed) and *why*. *Owns:* the immutable change story. *Does not own:* the current state (it is the cause of the current state, not a copy of it).
- **Evidence** — the traceable provenance behind any fact or conclusion (see Section 6). *Owns:* the link between a claim and its source. *Does not own:* the claim itself.
- **Observation** — a deterministic, evidence-backed pattern about the treatment, often cross-domain. *Owns:* a stated pattern with its confidence and its sources. *Does not own:* causation, diagnosis, or recommendation.
- **Signal** — a typed, computed indicator (adherence trend, refill risk, treatment momentum) that feeds intelligence. *Owns:* a measured state with trust classification. *Does not own:* narration; signals are composed into verdicts, not spoken raw.
- **Treatment Goal** — what the person and their physician are trying to achieve. *Owns:* the target. *Does not own:* the therapies used to pursue it (it references them).
- **Treatment Outcome** — the body's measured response (a lab, a weight, a glucose trend) relevant to a goal. *Owns:* the real-world result. *Does not own:* the interpretation of it as a clinical finding.
- **Learning Plan** — a structured, time-boxed, personal observation a person runs to learn what works for *their* body. *Owns:* the hypothesis, protocol, and deterministic finding. *Does not own:* any prescription; it observes, it does not direct.
- **Provider Discussion** — the set of evidence-backed questions and observations prepared for a physician visit. *Owns:* the talking points. *Does not own:* any clinical conclusion; it frames, it does not decide.

---

## Section 4 — The Canonical Medication Object

This describes the *conceptual* medication — the durable mental model that should guide any future schema, regardless of how the tables are drawn. A medication is understood through nine facets:

1. **Identity** — what it *is*: name, strength, form/route, classification, regulatory type (prescription/OTC/supplement), and external identifiers (e.g., NDC). Identity is factual and, ideally, externally verifiable.
2. **Treatment** — what it is *for*: purpose, the condition it addresses, the goal it serves, and its membership in a treatment plan. This is where a medication connects to *intent*.
3. **Schedule** — when it is *meant* to be taken: timing, recurrence, and the "as needed" exception. The schedule is a plan, never a record of fact.
4. **Inventory** — how much *remains*: supply estimate, refill horizon, expiration. Always an estimate, never asserted as certain.
5. **History** — how the treatment has *changed*: the append-only ledger of starts, dose changes, pauses, stops, and provider/pharmacy changes, each with a reason. History is immutable and forward-only — WLJ records change from the moment it begins observing and never fabricates a past it did not witness.
6. **Evidence** — *why we believe* each fact: the bottle photo, the OCR extraction, the user's confirmation, the prescription label. Identity and changes should be traceable.
7. **Relationships** — how it *connects*: to a prescriber, a pharmacy, a prescription, a drug class, other medications (same-class duplicates, interactions to flag for a pharmacist), and the conditions and allergies that contextualize it.
8. **Observations** — what *patterns surround it*: deterministic, evidence-backed, often cross-domain — adherence trends and the medication's relationship to glucose, weight, labs, sleep, nutrition, exercise.
9. **Intelligence** — what it *means*: the composed verdict (treatment momentum, things to monitor, questions to discuss) that the Chief of Staff narrates. Intelligence is always a composition of the facets above, never a free-floating opinion.

A future schema is healthy when each fact has exactly one home among these nine facets, and unhealthy when a fact is duplicated or homeless.

---

## Section 5 — Sources of Truth

Canonical ownership is exclusive and permanent. Nothing below may have a competing owner.

| Concept | Single Source of Truth | Never owned by |
|---------|------------------------|----------------|
| Medication/supplement **identity** | The canonical medication record (current state) | Any cache, draft, or extraction |
| **Dose & route** | The canonical medication record | The schedule or the logs |
| **Schedule** | The dosing-plan record | The medication record or the logs |
| **Dose events** (taken/missed) | The intake-log record | Any computed summary |
| **History / changes** | The append-only change ledger | The current medication record (which is the ledger's *projection*) |
| **Adherence** | One computation utility, used everywhere | Any view, dashboard, or signal that re-derives it inline |
| **Inventory estimate** | The supply fields + the one estimation rule | Any independent recomputation |
| **Provider / pharmacy** | The existing structured provider records (reused, not duplicated) | Free-text fields, which may persist only as fallbacks |
| **Treatment observations** | The deterministic signal/correlation engines | The language model |
| **Signals** | The signal-computation layer (typed, trust-classified, no-zero-fill) | Narration or UI |
| **Composed state / verdict** | The single medicine state contract | Multiple parallel "medicine brains" |
| **Beth's knowledge** | The composed state contract she is given | Raw logs, raw OCR, or raw meals |
| **Evidence** | The source records themselves, referenced by a shared envelope | A second, divergent copy of the source data |

**Two permanent ownership rules:**
- **Adherence has exactly one author.** Every surface that shows an adherence number reads it from the same computation. Divergent denominators are a defect, always.
- **Truth flows in one direction:** raw records → signals/state → composition → Chief of Staff → language. Nothing downstream may become a source of truth for anything upstream. The language model is the last consumer and never an author of fact.

---

## Section 6 — Evidence Philosophy

Evidence recurred throughout planning because it is genuinely central: **everything the Chief of Staff says should be traceable to something real.** The question is whether Evidence should be a first-class architectural *concept* or a shared *convention*.

**Verdict: Evidence is a first-class *philosophical* concept expressed through a shared *convention* — not, today, a single universal store.**

The principle is non-negotiable: no conclusion without provenance. But the *mechanism* must respect WLJ's laws. WLJ already carries provenance in many places — extraction methods, source enums, signal evidence, audit logs. What has been missing is not a place to put evidence; it is a *shared shape* for it and a consistent way to show it. So the canonical answer is a **convention**: a uniform way to express "here is the source," applied across every fact and conclusion, rendered to the user as a simple, honest "why this?" A dedicated universal evidence *store* is deferred until cross-domain demand or clinical-audit need earns it — promoting it earlier would violate modify-before-add and small-reversible-increments.

**What Evidence means here.** Evidence is the chain from a claim back to its origin. For a medication's *identity*, evidence is the bottle photo, the prescription label, the OCR extraction, and — decisively — the **user's confirmation**. For an *observation*, evidence is the underlying data: the weights, the glucose readings, the labs, the meals, the workouts, the journal entries, the capture, the signals it was computed from, and the timeline events it spans.

**How it works, conceptually:**
- **Confirmation is the strongest evidence.** OCR, vision, and inference produce *candidates*; only a person's confirmation makes a fact canonical. Extraction is never, by itself, evidence *of truth* — only evidence of *what a label appeared to say*.
- **Confidence travels with evidence.** Every piece of evidence carries how much it should be trusted; low-confidence evidence is surfaced as uncertain, never laundered into certainty.
- **Conclusions inherit their weakest link.** A verdict built on a low-confidence extraction is itself low-confidence, and says so.
- **Evidence is shown, not hidden.** Any conclusion the Chief of Staff presents can be unfolded to its sources. This is what makes the system trustworthy rather than merely confident.
- **Evidence lives inside the verdict.** It is part of the composed object the Chief of Staff narrates — never a separate pile of atoms she reasons over independently.

The test of this philosophy: a user (or their physician) can ask "why do you say that?" of *anything* the system claims, and receive a real, traceable answer — or an honest "I'm not certain, here's what I'm going on."

---

## Section 7 — Beth's Role

The Chief of Staff's role in this domain is permanent and bounded. *(In all user-facing copy the role is named "Chief of Staff"; "Beth" is an internal/configurable name.)*

**Beth shall:**
- **Observe** — surface real patterns from real data.
- **Organize** — keep the medication list, history, and inventory coherent and current.
- **Summarize** — turn months of data into a calm, honest picture.
- **Recognize patterns** — narrate deterministic, evidence-backed observations, including cross-domain ones.
- **Prepare physician discussions** — assemble evidence-backed questions and exports for real clinical conversations.
- **Support Learning Plans** — propose, run, and report personal observations, framed as learning.
- **Provide educational context** — explain, in general and clearly-labeled terms, what something is.

**Beth shall never:**
- **Diagnose** — name a condition the person has.
- **Prescribe** — tell a person to start, stop, or take a substance.
- **Recommend medication changes** — suggest a dose up, down, or switched.
- **Override physicians** — contradict or second-guess clinical direction.
- **Create false certainty** — present an estimate, a low-confidence extraction, or a correlation as fact.
- **Make unsupported conclusions** — say anything that cannot be traced to evidence.

These are not features to be toggled. They are the permanent shape of the role. When asked to cross a line, Beth declines warmly and redirects to the person's physician or pharmacist — and offers to *prepare* that conversation rather than substitute for it. Beth is enforced into these boundaries structurally (she has no authority to write medication facts without confirmation, and a safety check screens unsafe requests before she ever speaks), not merely asked to behave.

---

## Section 8 — Safety Philosophy

The permanent safety philosophy is a single sentence: **encourage understanding and learning, while keeping every clinical decision with the person and their physician.**

This resolves every hard case:

- **Medications & supplements:** WLJ tracks, organizes, and observes. It never advises starting, stopping, or changing. Possible duplicates or interactions are surfaced as *"worth checking with your pharmacist,"* never asserted.
- **Glucose, hypoglycemia, hyperglycemia:** WLJ surfaces *patterns* and flags them for physician discussion. It never interprets a reading as a diagnosis or advises a treatment. A dangerous-looking pattern is met with a calm safety note and a push toward a clinician — never a clinical instruction.
- **Exercise & nutrition in relation to treatment:** observed and learned about (especially through Learning Plans), never prescribed as therapy.
- **Potential treatment changes:** WLJ *records* a change the person or their physician made (with its reason) and *prepares* questions about whether a change might be warranted. It never *initiates* the suggestion of a change.
- **Learning Plans:** explicitly framed as personal observation — *"an observation about your body,"* closing with *keep testing* or *discuss with your physician*, never *you should do X*.
- **Physician conversations:** WLJ's highest safety expression is making the person a better-prepared, better-informed participant in their own care — amplifying the clinical relationship, never replacing it.

**The default under uncertainty is always: stage, ask, and defer to the human.** A missing fact costs a follow-up question; a wrong silent assertion costs trust and safety. The system always pays the former.

---

## Section 9 — Capability Maturity

A description of how the domain *evolves*, independent of any sprint plan. Each level is a stable plateau that is valuable on its own; the domain may rest at any level and still be worthwhile.

- **Level 1 — Inventory.** The system reliably knows *what* the person takes: a trustworthy, structured, current list of medications and supplements.
- **Level 2 — Capture, Timeline & Inventory.** Adding is effortless and trustworthy (confidence-reviewed capture); the treatment *history* accrues; supply and refills are managed. The person's treatment has a *record* and a *story*.
- **Level 3 — Awareness & Provider Exports.** The Chief of Staff *knows* the regimen and adherence and can speak to them; the person can produce a clinician-ready summary in one step. Tracking becomes *clinically useful*.
- **Level 4 — Cross-Domain Observation & Treatment Reviews.** The system relates medication to the rest of life — glucose, weight, labs, sleep, nutrition, exercise — and reviews treatment at the level of goals. The person begins to *understand* their treatment, not just record it.
- **Level 5 — Treatment Intelligence.** Medication observation composes upward into goal-level treatment reasoning across therapies; personal learning becomes continuous; the system helps the person and their physician optimize over time — always observing and preparing, never prescribing.

The arc from Level 1 to Level 5 is the arc from *a list* to *an understood, evolving treatment* — and the seam at Level 5 is where Treatment Intelligence (Section 2) is born.

---

## Section 10 — Success Definition

This domain is **not** measured by reminders sent or medications stored. Those are activity, not value.

It succeeds to the degree that:

- **The person understands their treatment better.** Could they explain what they take, why, how it's changed, and whether it's working — because WLJ helped them see it?
- **Physician visits are easier and better.** Does the person walk in prepared, with evidence-backed questions, and walk out having had a better conversation?
- **Manual work disappears.** Has capture, inventory, and history-keeping become effortless, replacing tedious data entry with a snapshot and a confirmation?
- **The Chief of Staff is trustworthy.** Does Beth say only what is true, traceable, and within her boundaries — such that the person *believes* her precisely because she never overreaches?
- **Observations are evidence-based.** Can every claim be traced to its source, with honest confidence?

**The north star:** the share of a person's regimen that is genuinely *understood* — each substance with a confirmed identity, a forward treatment story, and at least one evidence-backed observation the Chief of Staff can discuss. A flagship capability is one a person would miss if it vanished — and they would miss this because nothing else turns their bottles into understanding.

---

## Final Canon — The Domain in Brief

**What Medication Intelligence is:** the capability that turns the substances a person takes into an understood, evolving treatment — and prepares them to act on that understanding with their physician.

**What it is not:** a reminder app, a pill tracker, a pharmacy tool, or a passive ledger. It does not nag, and it does not practice medicine.

**What it owns:** the identity, dose, schedule, adherence, inventory, history, observations, and composed intelligence of medications and supplements — each fact with exactly one home, adherence with exactly one author, and truth flowing in exactly one direction.

**What Beth owns:** narration over composed, evidence-backed state — observing, organizing, summarizing, preparing physician discussions, supporting learning. Never diagnosing, prescribing, recommending changes, overriding physicians, or manufacturing certainty.

**What Evidence means:** the traceable chain from every claim back to a real source, with confirmation as its strongest form and confidence traveling alongside it — so that *anything* the system says can answer the question "why?"

**What Truth means:** a fact that has a single canonical owner and has been confirmed by a person; everything an algorithm extracts or infers is a *candidate* until then. The language model is truth's last reader, never its author.

**How it should evolve:** from a trustworthy list, to a captured history, to a knowledgeable companion, to a cross-domain observer, and finally to Treatment Intelligence — always additively, always within the same safety boundaries, always in service of the person's understanding of their own care.

*This Canon should remain correct after the implementation beneath it has been rewritten many times. Amend it deliberately and rarely. Planning for Medication Intelligence is, with this document, substantially complete; the work now is to build.*
