# Layer 1 Domain Certification Standard

**Status:** Permanent WLJ architecture. Part of the
[Layer 1 Domain Framework](LAYER1_DOMAIN_FRAMEWORK.md).

> The **gates** a canonical domain must pass before it may be called certified. A domain is
> **not certified until every gate passes.** Certification is a claim of trust to paying
> customers — treat it as one.

---

## Principle: trust before intelligence

The gates run in order and are **cumulative** — each assumes every gate below it is green. A
conversation built on wrong, stale, or unstable facts cannot be a good conversation, so the
factual gates (architecture → Deep) gate the conversational ones (Beth Production). You may not
score a higher gate while a lower one is red. This mirrors the platform's implementation order
(Law 0 → 4 → 1 → 2 → 3) and the Acceptance Center's enforcement that the Chief-of-Staff suite
cannot run until Deep is GREEN.

```
Gate 1  Architecture Review          ── design conforms before code is trusted
Gate 2  Technical Validation          ── it runs, it's scoped, it's regression-backed
Gate 3  Smoke Acceptance              ── the domain answers its headline questions at all
Gate 4  Full Acceptance               ── it answers the natural question set correctly
Gate 5  Deep Acceptance               ── factual-trust: intent, value, freshness, stability
Gate 6  Beth Production Acceptance    ── the live assistant handles it like a trusted CoS
Gate 7  Production Conversation       ── real conversations on the real stack confirm it
        Validation
              │
              ▼
        CERTIFIED & FROZEN  (manifest + tag + CI gate)
```

---

## Gate 1 — Architecture Review

**Question:** Is the domain *designed* to Layer 1 standard, before we trust its code?

Pass conditions (from the [Development Standard](LAYER1_DOMAIN_DEVELOPMENT_STANDARD.md)):

- Natural business-question list exists and is reviewed.
- The three-layer shape is present: `DomainTruth` facade → deterministic query layer →
  canonical models. Higher layers make one call.
- Each question maps to a `CompleteEntity` dimension (or a justified `extensions` dimension).
- Business vocabulary is defined, pinned to a single classifier, symmetric across categories.
- No precompute/SAE on the retrieval path; canonical calculations reused, not re-derived.

**Artifact:** a short domain inventory/design note (Medication's lineage:
`BETH_LAYER1_TRUTH_INVENTORY.md` + `MEDICATION_ADHERENCE_TRUST_CONTRACT.md`).

---

## Gate 2 — Technical Validation

**Question:** Does it run, is it correctly scoped, and is it protected?

- `python3 manage.py check` clean.
- `python3 manage.py makemigrations --check --dry-run` → **No changes detected** (or the
  migration is intentional, reviewed, and idempotent — e.g. a data re-tag migration).
- Scoped module tests green (never the full suite): the domain's own test module plus any
  directly-impacted modules.
- **SAE-disabled proof:** the domain answers with the snapshot layer patched to raise —
  proving live canonical retrieval (Law 4).
- **LLM-not-called proof** for deterministic questions — the LLM is asserted *not* invoked.
- Every historical production defect for the domain is a permanent regression.

---

## Gate 3 — Smoke Acceptance

**Question:** Does the domain answer its headline questions *at all*, on the real path?

- Runs the `depth="smoke"` questions through the real chat path (`acceptance_service.py`).
- The domain's headline questions (e.g. "what am I taking?", "did I take them today?") return
  a real answer — not empty, not an exception, not "assistant unavailable."
- **Infrastructure honesty:** the run reports empty-responses, OpenAI-failures, and whether it
  is trustworthy. A smoke failure that is really an infra outage is triaged as infra, not as a
  content defect (and vice versa — Run #62 was a *content* defect on a healthy path).

---

## Gate 4 — Full Acceptance

**Question:** Does it answer the full natural question set *correctly*?

- Runs `depth="full"`. Evaluated by the shared gold-standard rules
  (`acceptance_rules.py`): `required` / `required_any` / `forbidden` terms, plus the quality
  **gates** each question declares:
  - `gate_value` — a deterministic fact cites a VALUE or honestly says it's unavailable.
  - `gate_evidence` — the answer is backed by numbers/evidence, not vibes.
  - `gate_actionable` — where the contract expects a next step, one is present.
  - `gate_synthesis` — where a synthesis answer is expected, it spans enough dimensions.
- **Zero banned-phrase leakage:** no COACHING, SYSTEM, or DEFLECTION banned phrases (no
  "check your dashboard", no "source of truth", no "keep going").
- No wrong-domain answers (Law 0), no duplicate answers, no internal field/SAE leakage.

---

## Gate 5 — Deep Acceptance (factual-trust certification)

**Question:** Is the factual foundation trustworthy under adversarial, regression, and
stability pressure?

- Runs `depth="deep"` — the factual-trust categories operationalizing the Architecture Laws as
  release-blocking checks:
  - **Intent (Law 0):** answers the question actually asked; a wrong-domain answer is a
    *critical* failure.
  - **Truth (Law 1/2):** every deterministic fact cites a value or honest unavailability.
  - **Freshness (Law 1):** current / stale / pending / partial / missing each honored; stale is
    never presented as current.
  - **Deterministic Retrieval (Law 4):** never returns the OpenAI/"assistant unavailable"
    message for a deterministic question.
  - **Stability (Law 5):** identical question + unchanged data ⇒ identical numeric fact
    (`stability_violations()` / `unstable_fact`).
  - **Regression:** every historical production defect is frozen here permanently.
- Any factual-trust **critical** rule failing ⇒ the run grades **RED**. Deep must be **GREEN**.

---

## Gate 6 — Beth Production Acceptance (Chief-of-Staff quality)

**Question:** Does the live assistant handle the domain's conversations like a trusted Chief of
Staff — not just return correct facts?

- Gated: may only score once **Deep is GREEN** (enforced by `cos_acceptance_service.py`, which
  raises `CoSDeepNotGreen` otherwise). Trust precedes intelligence.
- A **weighted rubric** over seven dimensions — `trust` (hard-fail), `intent` (hard-fail),
  `truth_preservation`, `holistic`, `initiative`, `coaching`, `customer_confidence`. Any
  hard-fail ⇒ RED; ≥0.90 GREEN, ≥0.75 YELLOW.
- Run live in the Admin **Acceptance Center** (browser) against the real stack, on real user
  data. This is the automated form of the Playbook's Gate 3 ("Beth is the product").
- **Conversational threads** are validated, not just single questions — the anchor doesn't
  drift, comparisons return a comparison, follow-ups resolve (see the Conversation Object /
  Active Subject capabilities).

---

## Gate 7 — Production Conversation Validation

**Question:** Does it hold up in real conversations on the real stack?

- The domain is exercised through genuine production conversations (the operator, thinking like
  the customer — see the Playbook).
- **Production is the final authority.** A repository trace that says "this should work" is a
  hypothesis; the production conversation is the verdict. Certification is granted only when
  every acceptance test passes *and* production conversation confirms it.
- Any defect found here is root-caused from repository evidence, fixed at the root, frozen as a
  regression, and the affected gates are re-run.

---

## Certification (the manifest, the tag, the gate)

A domain is certified only when **all seven gates are green**. Certification is recorded, not
declared:

1. **Manifest** — record the domain's status in `apps/core/truth/certification.py` (status
   `certified`, `frozen`, capabilities, `test_modules`, acceptance results, commit + tag).
2. **CI gate** — `certify_layers` runs on every merge (`.github/workflows/test.yml`); no higher
   layer may bypass it. The domain's regression modules are wired in.
3. **Tag** — tag the certified commit (Layer 1's own tag: `layer1-canonical-truth-v1`).
4. **Constitution / snapshot** — record what the domain is/is not and its certification history
   (`LAYER1_CONSTITUTION.md` / `LAYER1_CERTIFICATION.md`).

**After certification the domain is frozen.** It changes only via formal change control:
evidence → justification → regression → Smoke/Full/Deep → production validation. Future work
builds upon it; it never silently redefines it.

---

## The two-consecutive-green rule (stable-tag)

A single green run is necessary but not sufficient for a **stable tag**. Stable-tag eligibility
requires:

- **Two consecutive GREEN Full runs** (a flaky green is not a green),
- **Zero banned-phrase leakage**,
- **Deep suite GREEN**,
- **Manual spot-check complete** (a human read a sample of real answers).

These are the operator's runtime gate — they cannot be claimed from local unit tests alone. A
local deterministic gate being green means the *fix* is proven; the stable tag means the
*product* is proven. Do not conflate them.

---

## Certification checklist (copy per domain)

- [ ] **Gate 1** Architecture review passed; design note exists.
- [ ] **Gate 2** `check` clean; migrations clean; scoped tests green; SAE-disabled + LLM-not-called proven; defects regressed.
- [ ] **Gate 3** Smoke GREEN; run trustworthy (infra honest).
- [ ] **Gate 4** Full GREEN; zero banned-phrase leakage; no wrong-domain/duplicate/leak.
- [ ] **Gate 5** Deep GREEN; no factual-trust critical failures; every defect frozen.
- [ ] **Gate 6** Beth Production (Chief-of-Staff) GREEN/acceptable; no hard-fail; threads hold.
- [ ] **Gate 7** Production conversation validated; production is the authority.
- [ ] **Recorded** manifest updated; CI gate wired; tag applied; constitution/snapshot written.
- [ ] **Stable-tag** two consecutive GREEN Full + zero banned + Deep GREEN + manual spot-check.

---

*Reference: Medication passed all seven and is the certified reference Layer 1 implementation
(2026-06-30). Layer 1 as a whole: commit `d6c187f7`, tag `layer1-canonical-truth-v1`.*
