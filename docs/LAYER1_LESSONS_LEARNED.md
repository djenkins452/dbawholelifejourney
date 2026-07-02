# Layer 1 Lessons Learned

**Status:** Permanent WLJ architecture. Part of the
[Layer 1 Domain Framework](LAYER1_DOMAIN_FRAMEWORK.md).

> Everything Medication taught us, so no future domain relearns it the hard way. Each lesson is
> stated as a principle, then grounded in the concrete moment that taught it.

---

## 1. Business contracts come before software

**Principle:** Define the truth as a business contract first; choose the implementation it
implies second. Never expose queries shaped like your schema.

**How we learned it:** `profile(entity)` was a software verb returning a per-domain dict — it
worked, but the business concept ("a canonical entity completely describes itself") was
invisible, and every domain invented its own shape. Replacing it with
`describe() → CompleteEntity` — a dataclass whose *fields are the business dimensions* — made
the contract visible in the type, identical across domains, and self-policing. The lesson: the
business concept must be expressed in code, not implied by it.

---

## 2. A canonical entity must completely answer its natural questions from one retrieval

**Principle:** Completeness is a business capability, not a field list. If a customer can
naturally ask it, one deterministic retrieval must answer it.

**How we learned it:** we declared Medication "complete" with four canonical entities and
dose-level execution — and the break attempt immediately found four holes: single-entity
retrieval ("what's my Metformin dose?"), symmetric categories ("what's my supplement
adherence?"), the combined view ("what am I taking?"), and execution slices ("what's left
today?"). The entities *were* complete; the retrieval surface around them was not. Complete
entities ≠ a complete domain.

---

## 3. Complete entities and a complete retrieval surface are different things

**Principle:** Building the entity object is half the work. The other half is every path by
which a customer reaches it — by name, by category, combined, by execution status, by history.

**How we learned it:** see Lesson 2. This is important enough to state on its own, because it
is the single most repeated near-miss: teams build a beautiful entity and forget that "beautiful
entity, unreachable by the customer's phrasing" answers nothing.

---

## 4. A word must mean exactly one thing, enforced in code

**Principle:** Business vocabulary is a trust contract. Pin each word to one meaning, put the
classification in one function every surface calls, and make the classifier the final authority
per object.

**How we learned it:** "Medication adherence" was silently including supplements and vitamins
across the dashboard, the action email, and Beth — three surfaces each computing a mixed number
and labeling it "Medicine." And a mis-tagged supplement (`category='prescription'`) appeared in
the prescription inventory. The fix was one classifier (`medicine_classification.py`), a
name-based safety net so a mis-tag can never leak, and a data migration to repair the rows —
plus the rule "Medicine = prescription only." Ambiguous vocabulary is a wrong answer waiting to
happen.

---

## 5. Read canonical truth live; never answer from a snapshot

**Principle:** Deterministic answers read the canonical models on the retrieval path. The SAE
and caches may consume the truth for precompute, but they are never the source of record on the
answer path (Law 4).

**How we learned it:** Medication truth was reconstructed ad-hoc inside the SAE precompute, and
Beth read the snapshot — so when the snapshot was missing or stale, Beth said "I don't have any
current medications." The customer *had* medications. There was simply nothing canonical to
read. Building `MedicineQueries` to read `Intake`/`IntakeLog`/`IntakeSchedule` live made
"I don't have any" impossible.

---

## 6. Reuse the canonical calculation — never re-derive inline

**Principle:** If a metric exists in a `*_utils` module, call it. Inline re-derivation drifts.

**How we learned it:** adherence existed in three forms (dashboard, email, Beth) that could
disagree, and a chart consumed a different calculation than the canonical one. Two numbers for
"the same" thing is an instant trust loss. One calculation, everyone calls it.

---

## 7. "Present but zero" is a trustworthy answer; "unknown" is a bug

**Principle:** A real `0` (nothing logged today) is an answer. "Unknown" because a snapshot is
missing is a failure. Carry freshness + confidence so the two are never confused.

**How we learned it:** calorie facts that coerced "no food logged" to "unknown" left no number
and failed the value gate; medication inventory that returned the snapshot-missing "unknown"
instead of a real "0" broke trust. Facts must always carry a value or an *honest* statement of
what's missing — never a silent gap.

---

## 8. Every production defect becomes a permanent regression

**Principle:** The moment a real conversation fails, freeze the exact case in the suite forever.

**How we learned it:** every Medication fix — supplement mis-tag, short-name resolution, the
Run #62 actionable-fallback, dose-level execution — shipped with a named regression test that
encodes the failing case. This is why the suite now matches reality and why no fixed defect can
silently return. A fix without a regression is a fix that will be undone.

---

## 9. Acceptance validates the product, not the code

**Principle:** Assert the rendered answer a customer reads, against the real evaluator — not an
internal dict, not a substring you invented.

**How we learned it:** Run #62 failed `gate_actionable` because the fallback said "an earlier
wind-down" (hyphen) where the real action cue was "wind down" (space). A test that asserted our
own made-up substring would have passed while the customer-facing gate failed. The regression
now asserts against the *real* `is_actionable` rule. Test what the customer experiences, judged
by the gate that judges the product.

---

## 10. Production conversations are the final authority

**Principle:** Repository evidence is the hypothesis; the live production conversation is the
verdict. "It should work" is not "it works."

**How we learned it:** more than once a repository trace said a path was fine and production
disproved it — the glucose average dropped on re-point; "Why?" returned "Assistant Unavailable"
because the cue set omitted the bare one-word form. Certification is granted only when every
acceptance test passes *and* production conversation confirms it.

---

## 11. Capability maturity matters more than fixing individual tests

**Principle:** Advance the domain up the maturity ladder; don't chase symptoms. Advancing one
stage retires whole classes of failures.

**How we learned it:** the stream of "it answered the wrong thing" reports didn't stop until
Medication reached entity completeness — not because each was fixed, but because the capability
that generated them finally existed. See the
[Capability Maturity Model](LAYER1_CAPABILITY_MATURITY_MODEL.md).

---

## 12. Trust before intelligence — the gates are ordered for a reason

**Principle:** A conversation built on wrong, stale, or unstable facts cannot be a good
conversation. Certify the factual foundation (Deep) before scoring the conversational quality
(Beth Production).

**How we learned it:** the Acceptance Center enforces that the Chief-of-Staff suite cannot even
*run* until Deep is GREEN (`CoSDeepNotGreen`). The platform implementation order (Law 0 → 4 →
1 → 2 → 3) is the same principle: right question → honest deterministic answers → fresh →
confidence-aware → orchestrated. Intelligence layered on untrustworthy truth is a confident lie.

---

## 13. Root-cause the class, don't patch the phrasing

**Principle:** When a question fails, identify *where* (truth / retrieval / routing / response
shape / vocabulary) and fix the class of defect. A one-question wording patch leaves the class
alive.

**How we learned it:** Run #62 was explicitly *not* treated as a sleep-question wording patch —
it was root-caused to the fallback *response shape* (concern-only, no evidence/why, passive
action), and the fix enriched every health-risk answer and improved the live path too. Fix the
defect class; the one phrasing is just where it surfaced.

---

## 14. The dimensions are the implementation; the law is the capability

**Principle:** Conform to Entity Completeness by *answering the natural questions*, not by
matching a fixed field list forever. Keep the dimension set open.

**How we learned it:** we elevated Entity Completeness so the LAW is "answer the natural
questions from one retrieval" and the six dimensions are its *current* implementation, with an
`extensions` map for domain-introduced dimensions. This keeps the architecture additive: a
future domain can answer a new kind of question without changing the law.

---

## 15. Routing order is a silent correctness feature

**Principle:** Order the classifier so specific beats generic; a shared cue must not swallow a
distinct intent.

**How we learned it:** "when did my dose *change*?" was captured by the present-time "dose" cue
until history ran first; "what supplements am I taking" had to route before the bare
"medication" keyword; a detailed "profile" request had to precede the "adherence" keyword.
Wrong order = confidently wrong answer, with no error to alert you.

---

## 16. Symmetry is completeness

**Principle:** If one category of an entity supports inventory / execution / adherence /
profile, every category must. Asymmetry is an incomplete domain.

**How we learned it:** supplements originally returned only a *list* while prescriptions
supported the full surface. "What's my supplement adherence?" is exactly as natural as the
prescription version; answering it with a list is a wrong answer. Parametrize the domain truth
by classification so every category is first-class.

---

## 17. Deferred means phased, with a trigger — never "maybe"

**Principle:** A cut capability gets a phase number and an explicit promotion trigger. The v1
architecture stays additive-compatible with the full roadmap.

**How we learned it:** this is a WLJ-wide planning rule reinforced throughout Layer 1 — every
"not in v1" carried a phase and a trigger, and the contracts stayed domain-agnostic
(registry-by-key, generalized patterns) so promotion is additive. "Maybe someday" hides scope
and breaks the additive guarantee.

---

## The meta-lesson

Medication was slow to certify not because the code was hard, but because we started by fixing
symptoms and only later understood the domain had to be *architected as a complete,
deterministic, self-describing business object, validated as a product*. Every future domain
inherits that understanding through this framework — so it can start at the top of the ladder
instead of the bottom. **That is the entire point of making Medication the reference
implementation.**

---

*Sources: the Medication changelog arc (2026-06-27 → 2026-07-01) and the Layer 1 certification
lineage. Concrete commits and tests for each lesson are in `docs/wlj_claude_changelog.md`.*
