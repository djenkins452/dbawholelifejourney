# WLJ Truth Retrieval Selection Investigation — the "protein yesterday" trust failure

**Status:** INVESTIGATION COMPLETE · architectural recommendation complete · **implementation intentionally deferred to the CoS-platform / Truth Retrieval Certification track** (this session did NOT implement).
**Date:** 2026-07-21
**Type:** Read-only runtime-trace investigation (no production code changed).
**Owns:** the runtime evidence + the architectural conclusion. **Does not own** the fix — see §7 Sequencing.

---

## 1. The customer-facing trust failure

The customer asked their Chief of Staff:

> "How much protein did I get yesterday?"

Observed conversation:
1. The CoS replied that **no protein was recorded**.
2. Challenged, it retrieved **every meal correctly** (breakfast/lunch/dinner).
3. Challenged again, it **still failed to answer the question** (it listed meals but produced no total).
4. Only after the customer **showed the Nutrition page** did it report **134 g** — and it did so by **accepting the customer's number, not by retrieving it.**

The deterministic truth existed the entire time. This is a trust failure, not a data failure.

---

## 2. Investigation 1 — architectural hypothesis (and where it was WRONG)

By tracing the code we established (correctly) that:
- The deterministic surface `get_history("nutrition","protein","yesterday")` has existed, deployed, since **2026-07-18** (`22c21ad6`); called directly it returns `total: 134.0, confidence: high`.
- The four deterministic capabilities exist as an abstraction: `get_domain_state` (current) · `get_history` (aggregate over a period) · `get_entity` (record detail) · `get_analysis` (analytical). Coverage across domains is uneven.
- Therefore this is **not** a missing-truth problem; it is a **truth-selection** problem.

What Investigation 1 got **wrong** (by inference, not evidence): it concluded the model was mis-routing between `get_domain_state` (a "today-vs-past trap") and `get_entity` (a "reconstruction trap"). **The runtime evidence disproved this.** The model never called `get_domain_state`. The real competitor was a *sixth* tool that the inference under-weighted. **Lesson: do not conclude an architectural cause from code inference — prove it at runtime.**

---

## 3. Investigation 2 — runtime proof

### 3.1 Method (and an audit-pillar gap discovered)
The authoritative source is the production `ToolCallLog` ledger for the customer's turn. **It has no operator read channel and no Django-admin registration** — so the literal production rows are not reachable without shipping a read endpoint (out of scope for a read-only session). *This is itself a finding: the append-only audit ledger designed for exactly this forensic question is not operator-queryable (see §8, Residual 1).*

Instead the turn was reproduced faithfully: the exact question run through the real `CoSGateway.respond(surface="chat")` → **`model_interface` runtime** (the production path; owner is flag-enabled) → **real gpt-4o** (`COS_MODEL=gpt-4o`, same as prod), against a user with 134 g of protein logged yesterday, reading back the `ToolCallLog` it wrote. **The failure reproduced 4/4** (three single-turn trials + one three-turn conversation). Routing is driven by tool descriptions + capability metadata, which are code-derived and byte-identical to production.

### 3.2 The reproduced chronological ledger (mirrors the real conversation beat-for-beat)

| Turn | Customer | Tool called (runtime evidence) | Result → CoS reply |
|------|----------|--------------------------------|--------------------|
| 1 | "How much protein yesterday?" | `get_foundational_health_facts(keys=['protein_today'])` → **`{"status":"unknown"}`** | "couldn't retrieve… daily protein wasn't included" = **"no protein recorded"** |
| 2 | "Check again" | `get_entity(nutrition, meal)` → per-meal detail ✓ | Listed 34 g + 55 g + 45 g **but never summed** = "retrieved every meal, still no answer" |
| 3 | "My page shows 134 g" | **no tool called** | "indeed 134 g" — **accepted the number, did not retrieve it** |

**`get_history` was never called — not in turn 1, not under challenge, not even when the number was named.**

### 3.3 The proven mechanism — a curated surface shadows the systematic authority
The model reaches first for `get_foundational_health_facts` — a **hand-curated key-value "canonical facts" list** whose description ("foundational, canonical health facts") makes it read as *the* authoritative one-stop lookup. Its 18-key set is **incomplete and asymmetric**:

| "…yesterday" question | key present? | result |
|---|---|---|
| calories | `calories_yesterday` ✓ | works (1550 kcal) |
| weight | `weight_yesterday` ✓ | works |
| glucose | `average_glucose_yesterday` ✓ | works |
| steps | `steps_yesterday` ✓ | works |
| **protein** | **`protein_yesterday` ✗ absent** | **false "not available"** |

Two-layer defect for protein specifically:
- `protein_yesterday` — **absent** from the enum entirely (no macro-yesterday keys exist).
- `protein_today` — **present but broken**: returns `{"status":"unknown","reason":"SAE nutrition state did not include daily_protein_g"}`.

So the *same question shape* succeeds for calories/weight/glucose/steps and fails for protein/macros — determined solely by which keys a human curator added. Because the tool answers with a plausible **absence** instead of deferring, the model trusts it and **never falls through** to `get_history`, which holds the exact number.

---

## 4. The class of failure (evidence-based)

> **A hand-curated key-value "facts" surface (`get_foundational_health_facts`) shadows the systematic per-metric aggregate authority (`get_history`) for the same "what was my ⟨metric⟩ on ⟨day⟩" question. The curated list is incomplete/asymmetric and answers with a false absence rather than deferring — so any metric×period the curator did not hand-add returns "not available" even though the systematic authority holds it.**

This is a direct violation of the platform law **one deterministic authority per truth domain**: there are two authorities for the same fact, and they have drifted.

---

## 5. Durable architectural lessons (folded into `01 §6`)

1. **Runtime evidence must precede architectural conclusions.** Investigation 1's inferred cause (`get_domain_state`/`get_entity` traps) was wrong; the runtime trace named the true cause (`get_foundational_health_facts`).
2. **Tool-selection failures ≠ truth-surface failures.** The truth existed and was correct; the model selected the wrong tool. These are different layers and must be diagnosed separately.
3. **"Routing" is overloaded — split the term.** *Deterministic Routing* (WLJ decides which provider/surface serves a request) is distinct from *Truth Retrieval Selection* (the model reasons about which tool to call). This failure was Truth Retrieval Selection, not Deterministic Routing.
4. **Truth Production and Truth Retrieval are separate architectural responsibilities.** A domain can *produce* a fact correctly (`macro_series` → 134 g) yet the *retrieval* surface the model reaches can fail to expose it.
5. **Parallel deterministic authorities are an architectural smell — investigate before patching.** Two surfaces answering the same question is the condition to remove, not a symptom to detect.

---

## 6. Recommendation — smallest constitutional change (eliminate the class)

The enabling **condition** is the parallel curated surface. Remove the overlap so there is exactly one producer:

- **Primary (smallest):** retire the metric-on-a-day keys (`*_today`/`*_yesterday`) from `get_foundational_health_facts`; let `get_history` own every "value of a metric for a day/period" question (it already accepts `today`/`yesterday`). One door; asymmetry becomes structurally impossible.
- **Alternative (keep the convenience tool):** make its metric keys **delegate to `get_history`** and **auto-derive the key set from `history_metrics × periods`**, so it can never again be incomplete or drift — a pure projection, not a second authority.
- **Certification gate:** add a **single-authority summary-retrieval** gate to the CoS Domain Certification Standard — a contract test enumerates `metric × {today, yesterday, this week}` and asserts (1) the systematic authority returns the page-agreeing number **and** (2) no other advertised tool answers the same question with a conflicting or absent result. This makes a shadow authority detectable before any domain ships.

Consistency: one authority per domain ✓ · WLJ owns truth, model reasons ✓ · improve truth before intelligence ✓ (this *deletes* a drifting surface, adds no capability) · product trust over elegance ✓.

---

## 7. Sequencing decision (why this session did NOT implement)

Implementation responsibility belongs to the **CoS-platform / Truth Retrieval Certification** track (the current PRIMARY FOCUS). This investigation deliberately stops at the architectural decision to avoid creating overlapping implementation work. The remaining work is to **evaluate the broader Truth Retrieval Architecture during platform implementation** — treat `get_foundational_health_facts` as one instance of the shadow-authority class, not a one-off patch — rather than continuing isolated investigation here.

---

## 8. Residuals (flagged, not fixed)

1. **The `ToolCallLog` audit ledger has no operator read channel** (no endpoint, no admin). The next trust incident should be answerable from the customer's real audit rows, not a reproduction — a small read-only operator endpoint would close this.
2. **`protein_today` returns "unknown" because the SAE nutrition snapshot omits `daily_protein_g`** — a second, smaller defect. It is a *symptom* of the shadow-authority class; the §6 primary fix dissolves it. Fold it into the platform fix rather than patching standalone.
