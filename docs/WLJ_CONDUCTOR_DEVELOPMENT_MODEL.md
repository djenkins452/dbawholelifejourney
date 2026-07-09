# WLJ Development Model — Truth, Reasoning, Action, Experience

> **Reframed 2026-07-09.** This document previously described a four-layer model in
> which WLJ owned **orchestration (the Conductor)** and **reasoning (capabilities)**.
> That model is retired. A frontier conversational model now owns reasoning and
> conversation; WLJ owns deterministic truth, preferences, history, actions, and
> audit. The **product-first** and **eliminate-the-class** disciplines below are
> unchanged and remain governing. The layer taxonomy is updated to match the new
> architecture.
>
> **Governing philosophy:** `WLJ_PRODUCT_VISION.md` (the *why* — WLJ is a Personal Truth
> Platform; the model reasons, WLJ knows).
> **Governing contract:** `WLJ_LLM_TRUTH_ACTION_CONTRACT.md`.
> **Constitution:** `WLJ_ARCHITECTURE_LAWS.md` (Laws 0–5).

---

## The shift this document captures

We are not building the assistant's mind. **We are building the deterministic platform
the conversational model reasons over.**

**The retired reflex** — every production failure asked "what capability is missing?"
and grew another self-selecting lane/classifier until the pieces stopped behaving like
one assistant. Repeated changes to the orchestration layer were the smell that told us
the approach was thrashing.

**The discipline now** — every production failure is diagnosed **product-first**, then
placed at the **first layer that failed**, where the layers are:

> **Truth (WLJ) → Reasoning (the conversational model) → Action (WLJ) →
> Experience (the composed response).**

The middle layer is no longer WLJ's to build. When reasoning is wrong, the fix is
almost never "write a WLJ reasoning capability" — it is **give the model better truth,
better context, or a better tool**, or adjust the behavioral profile. Building
bespoke WLJ reasoning is the retired path.

---

## Product Review comes BEFORE the Architecture Review (the North Star)

The layers are the *engineering* diagnosis. They are **not** the success metric. The
only success metric is:

> **"If this were the only conversation a paying customer ever had with their
> assistant, would they immediately want to use it again tomorrow?"**

The customer never experiences layers — they experience **trust**. So every production
transcript is judged **product-first**, then architecture-second:

1. **Would a paying customer trust this conversation?**
2. **If not, why — in customer terms?** (It contradicted itself · forgot what we
   discussed · answered a different question · made me fact-check it.) The moment trust
   breaks, the customer stops listening and starts fact-checking — the assistant has
   already failed.
3. **Only then: which layer caused the loss of trust?** — and fix the first one that
   failed.

**Never architecture-first.** Trust-breakers are fixed one at a time, wherever they
live — most often **Layer 1 (truth)** or **Layer 4 (experience)**. As Chief Architect:
**call it out plainly when the engineering is improving but the product experience is
not.**

---

## The four layers (diagnose top-down; fix the first that failed)

Check the layers **in order**. A failure at a lower layer cannot be correctly diagnosed
until the layer above it is confirmed correct.

### Layer 1 — Truth (owned by WLJ)
**Did WLJ know, and return, the correct deterministic truth — with correct freshness
and confidence?** If not → fix WLJ: the data, the accessor, the calculation, or the
briefing envelope. No amount of model reasoning can fix a wrong or badly-composed fact.
This is where most fixes land. (See `WLJ_ARCHITECTURE_LAWS.md`; the Answer Precondition
Pipeline now runs inside the truth tools.)

### Layer 2 — Reasoning (owned by the conversational model)
**Given correct truth, did the model reason correctly?** WLJ does **not** fix this by
building a reasoning capability. The levers are:
- **Truth/context** — did the model receive the right composed truth and executive
  context? A reasoning miss is usually a Layer 1 delivery gap in disguise (the model
  was never given the fact, the priority ranking, or the day-continuity state).
- **Tools** — did the model have the right truth/action tool available and in scope?
- **Behavioral profile** — did the profile tell it the right relationship, directness,
  and truth contract?
- **The model itself** — prompt/context assembly, or (rarely) the provider/model tier.

Only after truth, context, tools, and profile are confirmed correct is a reasoning miss
genuinely the model's. **Building a WLJ reasoning engine is not a Layer 2 fix — it is
the retired approach.**

### Layer 3 — Action (owned by WLJ)
**Did the requested action execute safely and truthfully?** Writes go through the
deterministic action path with confirmation and audit; results are narrated from real
execution output. A wrong write, a missing confirmation, or a narrated-but-unexecuted
action is a Layer 3 fix.

### Layer 4 — Experience (owned by the composed response)
**Right truth, right reasoning, right action — did it land naturally and at executive
quality?** Voice, filtering (what was worth surfacing), formatting, tone. With the model
authoring, most old Layer-4 machinery (post-hoc rewriting) is retired; what remains is
**what WLJ feeds** (the filtered executive briefing) and the behavioral profile.

---

## Eliminate the class, don't detect the symptom (the default before any trust-fix)

Once the Product Review and the layer diagnosis have located a trust-breaking failure,
one question comes **before** writing the fix:

> **"Can the architectural condition that makes this class of failure possible be
> removed entirely?"**

The goal is never to prevent *this one bug*. It is to make the *entire class*
structurally impossible.

1. **Does this failure represent an entire class?** ("6:15 AM tonight" is not one bug —
   it is the class "a sentence assembled from two independent time sources.")
2. **What architectural condition allows that class?** (Composition glued an item's own
   time to a frame from a different clock; nothing read the sentence back.)
3. **Can we REMOVE that condition** instead of detecting its symptoms?

**Removing the condition is almost always preferred** over adding a detector, validator,
recovery path, or capability. Note the deepest example of this principle in action: the
**retirement of the WLJ reasoning/composition layer itself.** The whole *class* of
"WLJ assembles a sentence from fragments and contradicts itself" is eliminated by
letting the model author coherently over composed truth, rather than by adding
coherence detectors. That is condition-removal at the architectural scale.

**Bound by blast radius (the escape valve).** Prefer elimination, but when removing the
condition would require a disproportionate rewrite or destabilize working paths,
**contain the class as narrowly as possible and LOG the residual** — then eliminate it
later, product-first, one step at a time.

---

## The governing rule for new work

> A production failure does **not** justify building WLJ reasoning. First place it at
> the first failing layer:
> 1. **Truth wrong or badly composed** (Layer 1 → fix WLJ truth/briefing). *Most fixes.*
> 2. **Truth right, model reasoned poorly** (Layer 2 → better truth delivery, context,
>    tool, or profile — **not** a WLJ reasoning engine).
> 3. **Action unsafe/untruthful** (Layer 3 → fix the deterministic action path).
> 4. **All correct but the response was poor** (Layer 4 → what WLJ feeds + profile).

Building a bespoke WLJ reasoning capability is no longer an outcome of this process. If
a genuine truth or action *gap* exists, WLJ fills it as **truth or an action tool** —
never as a mind.

---

## The Architectural Stability Principle

**The truth and action layers are the stable core; the reasoning layer is the model's.**
Future improvement should land, overwhelmingly, in:

- **deterministic truth** (Layer 1 — accessors, briefings, freshness/confidence),
- **truth/action tools and the executive-context envelope** (what the model receives),
- **the behavioral/preference profile** (how the model is asked to behave),
- **audit and observers** (Executive Reflection — consumers of the tool-call/turn
  stream, never turn-owners).

If we find ourselves wanting to build reasoning *inside* WLJ, treat that as an
**architectural smell** and stop: the fix almost certainly belongs in truth delivery,
context, a tool, or the profile. **Closed core, open space.**

---

*Last updated: 2026-07-09 (reframed from the retired Conductor four-layer model to
Truth → Reasoning (the model) → Action → Experience; product-first and
eliminate-the-class disciplines retained; anchored on
`WLJ_LLM_TRUTH_ACTION_CONTRACT.md`).*
