# The WLJ Chief of Staff Constitution

**Status:** RATIFIED — Constitutional. Protected.
**Constitution Version:** 1.0
**Established:** 2026-07-11 (WLJ Chief of Staff Architecture Milestone)
**Governs:** The permanent architecture of the WLJ Chief of Staff.
**Supersedes as apex authority:** all architecture docs — every other doc derives from this one; where any doc conflicts with this Constitution, this Constitution wins, and the conflicting doc is the thing that must change (through Constitutional Review, below).

---

## 0. What this document is

This Constitution records the architectural principles of the WLJ Chief of Staff that are now considered **permanent and intentionally protected**. They are the result of roughly 4–6 months of architecture, engineering, testing, simplification, and production validation.

This document does **not** claim the product is finished. It marks the point at which the **fundamental architecture is complete and locked**. Future development is expected to **improve the product, not redefine the architecture**.

Two rules frame everything below:

1. **Solve inside the Constitution first.** When you hit a problem, the default is to solve it within these principles — better truth, better truth delivery, a new truth or action tool, a corrected AI Relationship, a better product experience. Only when that is genuinely impossible do you propose changing the Constitution.
2. **Changing the Constitution requires explicit written approval from Danny** (see §3, Constitutional Review). The default answer to a constitutional change is **NO**.

---

## 1. Naming (constitutional)

- All engineering documentation, architecture, guides, contracts, tests, and code comments refer to the system as the **WLJ Chief of Staff** (or "the Chief of Staff").
- The **user-facing AI name is a per-user preference only** — e.g. *Clara, Beth, Jarvis, Friday,* or any name the user selects. It is stored as a user preference and rendered only in that user's experience.
- **Never hardcode a user-selected AI name** (Clara, Beth, or any other) into architecture, documentation, contracts, fixtures, release notes, help, or system identity. A provider name (OpenAI) and an assistant display name are **never** a WLJ system identity.

---

## 2. The Articles

Each Article is a permanent principle. The short form is the law; the gloss explains it.

### Article I — The Truth / Reasoning Division

**I.1 — WLJ owns deterministic truth.**
The canonical facts of a person's life — records, history, preferences, state, timing — live in WLJ and are produced deterministically. WLJ is the source of truth, not a cache of the model's beliefs.

**I.2 — The conversational model owns reasoning.**
Reasoning, conversation, and driving the turn belong to the conversational model (**currently OpenAI**, behind the single Model Interface seam — see I.8). WLJ does **not** contain a reasoning engine. A reasoning miss is fixed by giving the model better truth, context, tools, or relationship — never by building a mind inside WLJ.

**I.3 — WLJ owns deterministic calculations.**
Calculations that must be correct, reproducible, auditable, or policy-bound (adherence, streaks, momentum, timing, aggregates, scores) are computed deterministically in WLJ. The model never re-derives a calculation WLJ already owns.

**I.4 — The conversational model owns interpretation and judgment.**
WLJ exposes facts (numbers, dates, state). It does **not** emit verdicts ("on track," "you're doing great"). The model interprets. Truth is facts; judgment is reasoning.

**I.5 — The conversational model performs perception.**
Perception of uploaded images, PDFs, and unstructured input is the model's job (it perceives; WLJ has no OCR/parser engine). Perceived candidates then flow through WLJ's existing deterministic spine (validate → dedup → confirm → execute → audit + provenance).

**I.6 — WLJ validates deterministic truth.**
Before truth is presented or acted on, WLJ validates it deterministically (integrity: freshness, ordering, non-future timestamps, completeness, confidence). Validation is WLJ's, not the model's.

**I.7 — WLJ executes deterministic actions.**
Actions that change a user's data run through WLJ's safe, deterministic, audited action path — never as free-form model side effects. Every action is validated, optionally confirmed, executed, and audited with provenance.

**I.8 — Provider-agnostic behind one seam.**
The reasoning/perception provider is configuration behind a single Model Interface seam. It is **currently OpenAI**. No provider name and no assistant display name is ever a WLJ system identity. The Constitution is written so the provider can change without changing the architecture.

### Article II — Current Context Authority

**II.1 — Current Context is authoritative.**
Every page declares, deterministically, what the user is looking at. The server-resolved Current Context is canonical truth; scraped DOM is never trusted as truth.

**II.2 — Detail pages expose focused objects.**
A detail page is about one canonical record and declares that object (`app.model:pk`) as its Current Context.

**II.3 — Overview pages expose deterministic summaries.**
An overview/dashboard page has no single object and declares a deterministic **page summary** (`summary:<key>`) via a user-scoped, request-path-safe, **facts-only** provider. The same one deterministic source feeds both the page render and the summary provider — never two independent derivations.

**II.4 — Related truth enriches Current Context but never replaces it.**
Related/adjacent truth may enrich what the Chief of Staff knows about the current screen, but it never overrides or substitutes for the authoritative Current Context of the page the user is actually on.

### Article III — Single Deterministic Authority

**III.1 — One deterministic authority per truth domain.**
Each truth domain has exactly one deterministic producer that every surface consumes. No surface re-derives or re-orders a domain's truth independently. (Precedent: one sleep accessor, one weight summary source, one mission-link producer.)

**III.2 — One Execution Decision Authority.**
"What to do now" has a single deterministic producer (`decision_authority.current_action(user)`). Every surface **consumes** it; none introduces a second selector or re-orders it. Enforced by CI contract.

**III.3 — Mission Link is deterministic truth.**
The connection between an action and the mission(s)/goal(s) it serves is deterministic truth (join action → signal type → goal signal source → goals), exposed as facts (primary mission, weight, why). It is truth, not reasoning, and not invented by the model.

### Article IV — Engineering Discipline

**IV.1 — Results, not intentions.**
Report and act on what actually happened — verified results — not on what was intended or attempted. A passing unit test is not proof of production behavior; prove the runtime path.

**IV.2 — Improve truth before adding intelligence.**
Before building any new capability, ask: *can the conversational model already do this well?* If yes, do not build it — improve the **truth** available to it. As frontier models improve, WLJ gets **simpler**, not more complex.

**IV.3 — Reuse before rebuilding.**
When a calculation, accessor, or utility already exists, use it. Inline re-derivation causes drift (log-based vs schedule-based adherence, etc.). Extend the single authority; do not fork it.

**IV.4 — Expose before inventing.**
A genuine gap is filled by exposing existing truth better, or by adding a **truth or action tool** — never by inventing a bespoke reasoning capability inside WLJ.

### Article V — Product Governance

**V.1 — Product experience governs future refinement.**
The only success metric is: *"If this were the only conversation a paying customer ever had with their Chief of Staff, would they immediately want to use it again tomorrow?"* Every production review is **Product first, then Architecture**: (1) would a paying customer trust this? (2) if not, why, in customer terms? (3) only then, which architectural layer caused it. The customer experiences **trust**, not layers.

**V.2 — Eliminate the class, don't detect the symptom.**
When a trust-breaking failure appears, ask what architectural **condition** made it possible and whether that condition can be **removed** (so the whole class becomes structurally impossible), rather than adding another detector/validator/recovery path. Bounded by blast radius: if removal needs a disproportionate rewrite, contain the class narrowly and **log the residual**.

**V.3 — The development model is layered and top-down.**
For any Chief-of-Staff production issue, classify the failing layer — **Truth (WLJ) → Reasoning (the model) → Action (WLJ) → Experience** — and fix the first layer that failed. Most fixes are Layer 1 (truth). Reflection sits **above** these layers and only observes them; learning is default-deny and never learns around a deterministic defect.

---

## 3. Constitutional Review Process (mandatory)

A **Constitutional Review** is required whenever a proposal would change, weaken, remove, or invert any Article in §2, the naming rule in §1, or the framing in §0. This includes — but is not limited to — proposals to:

- build any reasoning, judgment, classification, or "conductor" engine inside WLJ (violates I.2, IV.2, IV.4);
- have the model re-derive or own a deterministic calculation, or have WLJ emit interpretive verdicts (violates I.3, I.4);
- introduce a second producer/selector for a truth domain or for "what to do now" (violates III.1, III.2);
- let scraped DOM, related truth, or a non-authoritative source override Current Context (violates II.1, II.4);
- bypass the deterministic validation or safe action path (violates I.6, I.7);
- hardcode a provider name or a user-selected AI name as system identity (violates §1, I.8);
- add a bespoke capability where better truth or an existing tool would do (violates IV.2, IV.3, IV.4).

### The review procedure

When any such proposal arises, **STOP** and do not implement it. Instead, produce a Constitutional Review notice that states, plainly and prominently:

> ⚠️ **CONSTITUTIONAL CHANGE PROPOSED**
> This proposal changes the constitutional architecture of the WLJ Chief of Staff, established through months of architecture, engineering, and production validation.
> - **Article(s) affected:** _(list them)_
> - **What the proposal changes:** _(plain description)_
> - **Why the problem cannot be solved inside the Constitution:** _(required — show the in-Constitution options were genuinely exhausted)_
> - **Blast radius / what this would destabilize:** _(honest assessment)_
>
> **Do you intentionally wish to change the Constitution?**
> The default expectation is **NO.** Constitutional changes require **Danny's explicit written approval.** Absent that approval, the proposal is not implemented and the problem is solved inside the Constitution instead.

### Rules of the process

1. **Solve inside the Constitution first.** The reviewer must show that the in-Constitution options (better truth, better delivery, a truth/action tool, a corrected AI Relationship, a product-experience fix) were genuinely considered and are insufficient. "It would be cleaner" or "it would be smarter" is **not** sufficient grounds.
2. **Explicit written approval from Danny is required** to proceed. Silence, inference, or a general "move forward" on unrelated work is **not** approval for a constitutional change.
3. **Default NO.** If there is any doubt about whether a change is constitutional, treat it as constitutional and open the review.
4. **Record the outcome.** Every review (approved or declined) is recorded in the Amendment Log below, with date, Article(s), decision, and rationale. Engineering history is never deleted.

Ordinary work — new features, new domains, new truth, new tools, better prompts, better UX, bug fixes — does **not** require a Constitutional Review, as long as it stays inside the Articles. The Constitution constrains *architecture*, not *progress*.

---

## 4. Enforcement (the Constitution is executable, not just aspirational)

Several Articles are machine-enforced in CI. These contracts are the constitutional backstop; weakening one is itself a constitutional change.

| Article | Enforced by |
|---|---|
| I.2 / IV.2 (no reasoning/inline-LLM on the request path; no heavy compute on request path) | `apps/core/tests/test_request_path_safety_contract.py` |
| III.2 (one Execution Decision Authority) | `apps/core/tests/test_execution_decision_authority_contract.py` |
| V.1 / Visual truth (only real completion may look complete) | `apps/core/tests/test_visual_truth_contract.py` |
| Intent registration integrity (schema ↔ handler ↔ dispatcher parity) | `apps/ai/tests/test_intent_registration.py` |
| Constitutional contracts (this document's Articles have live tests) | `apps/core/tests/test_constitution_contract.py` |

The permanent acceptance baseline (see `docs/WLJ_ACCEPTANCE_BASELINE.md`) runs these together as the milestone regression suite.

---

## 5. Amendment Log

| Date | Version | Article(s) | Decision | Rationale |
|---|---|---|---|---|
| 2026-07-11 | 1.0 | — | **Ratified** | WLJ Chief of Staff Architecture Milestone. Initial constitution established and locked. |

*No amendments. The Constitution stands at Version 1.0.*

---

## 6. Related governing documents (derive from this Constitution)

- `docs/WLJ_PRODUCT_VISION.md` — the governing "why" (Personal Truth Platform).
- `docs/WLJ_LLM_TRUTH_ACTION_CONTRACT.md` — the truth/action/preference boundaries (Article I in detail).
- `docs/WLJ_ARCHITECTURE_LAWS.md` — the Answer Precondition Pipeline (Laws 0–5).
- `docs/WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md` — the layered development model (Article V.3).
- `docs/WLJ_CURRENT_CONTEXT_CONTRACT.md` — Current Context two-pattern standard (Article II).
- `docs/WLJ_VISUAL_TRUTH_CONTRACT.md` — only real completion may look complete (Article V.1).
- `docs/WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md` — reflection observes, never overrides (Article V.3).
- `docs/LAYER1_DOMAIN_FRAMEWORK.md` — how a new canonical truth domain is built (Article III.1).
- `docs/WLJ_MILESTONE_COS_ARCHITECTURE.md` — the milestone report this Constitution anchors.

---

*This Constitution establishes the permanent architectural foundation of the WLJ Chief of Staff. Future work should improve the product while remaining inside these boundaries, unless an explicit Constitutional Review is approved by Danny.*
