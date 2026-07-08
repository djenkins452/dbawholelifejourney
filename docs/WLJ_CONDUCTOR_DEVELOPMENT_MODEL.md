# WLJ Conductor Development Model — the Four-Layer Diagnostic

**Status:** Governing design principle (approved 2026-07-08).
**Scope:** Every production issue in any Beth / Chief-of-Staff surface, and every decision about whether to add a capability.
**Related:** `docs/WLJ_ARCHITECTURE_LAWS.md` (truth), the Conductor Contract + Return Contract (orchestration), `docs/WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md` (observers).

---

## The shift this document captures

We are no longer simply building Beth. **We are building the platform Beth runs on.** That distinction changes how we develop.

**Before The Conductor** — every production failure led to the same reflex:

> Production issue → "What capability is missing?" → build another lane / classifier / capability.

That reflex kept adding self-selecting lanes and grew the collision surface until the capabilities stopped behaving like one Chief of Staff.

**After The Conductor** — every production issue begins with one question instead:

> Production issue → **"Which architectural layer failed?"** → fix that layer → *only then* decide whether a new capability is actually required.

Adding a capability is now the **exception**, reached only after the layer diagnosis proves a genuine gap — never the default response to a failure.

---

## Product Review comes BEFORE the Architecture Review (the North Star)

The four layers are the *engineering* diagnosis. They are **not** the success metric. The only success metric is:

> **"If this were the only conversation a paying customer ever had with Beth, would they immediately want to use her again tomorrow?"**

The customer never experiences layers — they experience **trust**. So every production transcript is judged **product-first**, then architecture-second:

1. **Would a paying customer trust this conversation?** (Would they want to use her again tomorrow?)
2. **If not, why — in customer terms?** (She contradicted herself · forgot what we discussed · answered a different question · made me fact-check her.) The moment trust breaks, the customer stops listening and starts fact-checking — she has already failed as a Chief of Staff.
3. **Only then: which architectural layer caused that loss of trust?** — and fix it.

**Never architecture-first.** A passing Layer 2, an elegant handler selection, a correct routing decision mean nothing if the customer left less confident. The Conductor / Four-Layer Diagnostic / Return Contract are the **engineering methodology**; the **product is the North Star**. Trust-breakers are fixed one at a time, wherever they live — often Layer 1 (truth) or Layer 4 (experience), not orchestration — ranked by trust impact. Do **not** advance the Conductor roadmap because it is "next"; advance it only when it is the highest-trust-impact fix. And as Chief Architect: **call it out plainly when the engineering is improving but the product experience is not.**

## The four layers (diagnose top-down; fix the first that failed)

Check the layers **in order**. A failure at a lower layer cannot be correctly diagnosed until the layer above it is confirmed correct — a wrong answer built on wrong truth is a Layer 1 problem, not a reasoning problem.

### Layer 1 — Truth (owned by WLJ)
**Question:** Did WLJ know the correct deterministic truth?
**If not → fix WLJ.** The data, the accessor, the calculation. No amount of orchestration or reasoning can fix a wrong fact. (See `WLJ_ARCHITECTURE_LAWS.md`, the Answer Precondition Pipeline.)

### Layer 2 — The Conductor (owned by orchestration)
**Question:** Did the **correct capability own the turn**?
**If not → fix orchestration.** The wrong capability answered. This is an ownership/routing failure, and it is diagnosed with the Conductor's own instrumentation (`COS_CLASSIFY` / `COS_CLASSIFY_MATCH`: expected owner vs actual owner vs `agree`). Fixing it means the Classifier/dispatch, **not** a new capability.

### Layer 3 — Capability (owned by Beth's intelligence)
**Question:** The correct capability owned the turn — did it **reason correctly**?
**If not → improve the capability, or (only here) add a missing one.** This layer has two distinct sub-cases, and they must not be conflated:
- **3a — the correct capability reasoned incorrectly** → improve that capability. Not a new capability.
- **3b — no existing capability covers this situation at all** → *this is the only case that warrants building a new capability.*

### Layer 4 — Experience (owned by the composed response)
**Question:** The reasoning was correct — was the conversation **natural**? Was the recommendation **executive quality**? Did it feel **human**?
**If not → improve the user experience.** Voice, composition, filtering, tone (`naturalize`, `harmonize`, the composers). The right truth, the right owner, the right reasoning can still land as a robotic or low-value response — that is a Layer 4 fix, not a capability.

---

## Eliminate the class, don't detect the symptom (the default before any trust-fix)

Once the Product Review and the layer diagnosis have located a trust-breaking failure, one question comes **before** writing the fix:

> **"Can the architectural condition that makes this class of failure possible be removed entirely?"**

The goal is never to prevent *this one bug*. It is to make the *entire class* structurally impossible. So, in order:

1. **Does this failure represent an entire class?** ("6:15 AM tonight" is not one bug — it's the class "a sentence assembled from two independent time sources.")
2. **What architectural condition allows that class to exist?** (Composition glued an item's own time to a frame from a *different* clock; nothing read the sentence back.)
3. **Can we REMOVE that condition** instead of detecting its symptoms? (Yes — one sentence, one time source. The class is now impossible, not merely caught.)

**Removing the condition is almost always preferred** over adding a detector, validator, recovery path, or new capability. A customer does not care that a validator caught an error — they care that the error *never occurs*. The product becomes trustworthy not because it recovers from mistakes well, but because whole categories of mistakes become impossible.

- **Right:** make contradictory time composition structurally impossible.
  **Wrong:** add a check that flags "AM … tonight".
- **Right:** remove the condition that lets multiple greeting authors contribute to one conversation.
  **Wrong:** detect and suppress repeated greetings.
- **Right:** remove the condition that lets one capability answer a question owned by another (the Conductor's ownership model).
  **Wrong:** detect wrong-question answers after the fact.

**Bound by blast radius (the escape valve).** Prefer elimination, but this is *not* a mandate to redesign Beth on every bug. When removing the condition would require a disproportionate rewrite or would destabilize working paths, **contain the class as narrowly as possible and LOG the residual** — then eliminate it later, product-first, one step at a time. Only when elimination is genuinely impractical do we fall back to a localized detector/capability. Elimination is the default; judgment sets the size.

## The governing rule for new capabilities

> Do not create a new capability because production exposed a problem. First let The Conductor prove **which** of these is true:
> 1. the **wrong** capability answered (Layer 2 → fix orchestration),
> 2. the **correct** capability answered **incorrectly** (Layer 3a → improve the capability),
> 3. a **genuine** capability is **missing** (Layer 3b → build it).
>
> **Only case 3 results in a new capability.**

The Conductor's instrumentation is what makes this determinable rather than a guess. A turn is routed to its expected owner; the owner declares its own return outcome (see the Return Contract). Whether the owner was "good enough" is answered by the handler's return state — never by orchestration deciding it.

---

## The Architectural Stability Principle

**The Conductor is one of the least-frequently-modified components in WLJ.** It is the operating system beneath Beth. Future improvement should land, overwhelmingly, in:

- **deterministic truth** (WLJ / Layer 1),
- **capabilities** (Layer 3),
- **observers** (Executive Reflection, Continuous Learning — consumers of the commit stream, never turn-owners),
- **experience** (Layer 4).

If we repeatedly need to modify The Conductor itself, treat that as an **architectural smell** and investigate why — a capability is probably violating the advertisement model, or a responsibility is being pushed into orchestration that belongs in a layer around it. **Closed core, open space.**

---

## Worked example — the Executive-Accountability turn

Input: *"I noticed you let me slide on Bike Ride/Pickleball, Empty Dishwasher, and Journal."* → Beth answered *"None of your active goals appear to be slipping…"*

- **Layer 1 (Truth):** the rhythm/execution truth exists (`get_remaining_rhythm_items`). ✅ Not a truth failure.
- **Layer 2 (Conductor):** `COS_CLASSIFY` = `meta`, expected owner = `repair`, high confidence; actual owner = `personal_reasoning` → `goal_concerns`; `agree=False`. ❌ **The wrong capability owned the turn.** → Fix orchestration first (Step 2b routes `meta` → `repair`).
- **Layer 3 (Capability):** *not yet answerable* — the correct owner has never received the turn. Once Step 2b delivers it to `repair`, `repair` declares its own outcome (ANSWERED / UNABLE / ESCALATED). Only then do we learn whether it's 3a (improve repair) or 3b (a genuine Accountability capability is missing).
- **Layer 4 (Experience):** downstream of the above.

This is the discipline in one example: **the failure was Layer 2 before it could ever be considered a missing-capability (Layer 3b) problem.** Without the Conductor we would have built an "Executive Accountability" capability immediately — and still had the orchestration bug.

---

*Last updated: 2026-07-08 (initial — captures the four-layer diagnostic + Architectural Stability Principle as a governing development model).*
