# The WLJ Chief of Staff Constitution

**Status:** RATIFIED — Stable and constitutionally protected.
**Constitution Version:** 1.0
**Established:** 2026-07-11 (WLJ Chief of Staff Architecture Milestone)
**Canonical location:** `@WLJ_SYSTEM_PROMPTS/00_WLJ_CHIEF_OF_STAFF_STARTUP/01_WLJ_CONSTITUTION.md` (this file). `docs/WLJ_CONSTITUTION.md` is a pointer to here.
**Responsibility of this document:** what must not change casually, the Constitutional Review process, and the protected architectural boundaries. It does not summarize the other startup documents.

---

## 0. What this document is

This Constitution records the architectural principles of the WLJ Chief of Staff that are considered **stable and constitutionally protected**. They are the result of roughly 4–6 months of architecture, engineering, testing, simplification, and production validation.

This document does **not** claim the product is finished, and it does **not** freeze the architecture forever. It marks the point at which the **fundamental architecture is considered stable**. The architecture is expected to **evolve slowly, through Constitutional Review** (below) — not through casual redesign. Future development is expected to **improve the product, and to change the architecture only deliberately.**

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

Each Article is a protected principle. The short form is the law; the gloss explains it.

### Article I — The Truth / Reasoning Division

**I.1 — WLJ owns deterministic truth.** The canonical facts of a person's life — records, history, preferences, state, timing — live in WLJ and are produced deterministically. WLJ is the source of truth, not a cache of the model's beliefs.

**I.2 — The conversational model owns reasoning.** Reasoning, conversation, and driving the turn belong to the conversational model (**currently OpenAI**, behind the single Model Interface seam — see I.8). WLJ does **not** contain a reasoning engine. A reasoning miss is fixed by giving the model better truth, context, tools, or relationship — never by building a mind inside WLJ.

**I.3 — WLJ owns deterministic calculations.** Calculations that must be correct, reproducible, auditable, or policy-bound (adherence, streaks, momentum, timing, aggregates, scores) are computed deterministically in WLJ. The model never re-derives a calculation WLJ already owns.

**I.4 — The conversational model owns interpretation and judgment.** WLJ exposes facts (numbers, dates, state). It does **not** emit verdicts ("on track"). The model interprets. Truth is facts; judgment is reasoning.

**I.5 — The conversational model performs perception.** Perception of uploaded images, PDFs, and unstructured input is the model's job (it perceives; WLJ has no OCR/parser engine). Perceived candidates then flow through WLJ's existing deterministic spine (validate → dedup → confirm → execute → audit + provenance).

**I.6 — WLJ validates deterministic truth.** Before truth is presented or acted on, WLJ validates it deterministically (integrity: freshness, ordering, non-future timestamps, completeness, confidence).

**I.7 — WLJ executes deterministic actions.** Actions that change a user's data run through WLJ's safe, deterministic, audited action path — never as free-form model side effects. Every action is validated, optionally confirmed, executed, and audited with provenance.

**I.8 — Provider-agnostic behind one seam.** The reasoning/perception provider is configuration behind a single Model Interface seam. It is **currently OpenAI**. No provider name and no assistant display name is ever a WLJ system identity.

### Article II — Current Context Authority

**II.1 — Current Context is authoritative.** Every page declares, deterministically, what the user is looking at. The server-resolved Current Context is canonical truth; scraped DOM is never trusted as truth.

**II.2 — Detail pages expose focused objects.** A detail page is about one canonical record and declares that object (`app.model:pk`) as its Current Context.

**II.3 — Overview pages expose deterministic summaries.** An overview/dashboard page declares a deterministic **page summary** (`summary:<key>`) via a user-scoped, request-path-safe, **facts-only** provider. The same one deterministic source feeds both the page render and the summary provider.

**II.4 — Related truth enriches Current Context but never replaces it.** Related/adjacent truth may enrich what the Chief of Staff knows about the current screen, but it never overrides or substitutes for the authoritative Current Context of the page the user is on.

### Article III — Single Deterministic Authority

**III.1 — One deterministic authority per truth domain.** Each truth domain has exactly one deterministic producer that every surface consumes. No surface re-derives or re-orders a domain's truth independently.

**III.2 — One Execution Decision Authority.** "What to do now" has a single deterministic producer (`decision_authority.current_action(user)`). Every surface **consumes** it. Enforced by CI contract.

**III.3 — Mission Link is deterministic truth.** The connection between an action and the mission(s)/goal(s) it serves is deterministic truth, exposed as facts (primary mission, weight, why). It is truth, not reasoning, and not invented by the model.

### Article IV — Engineering Discipline

**IV.1 — Results, not intentions.** Report and act on what actually happened — verified results — not on what was intended. A passing unit test is not proof of production behavior; prove the runtime path.

**IV.2 — Improve truth before adding intelligence.** Before building any new capability, ask: *can the conversational model already do this well?* If yes, do not build it — improve the **truth** available to it. As frontier models improve, WLJ gets **simpler**, not more complex.

**IV.3 — Reuse before rebuilding.** When a calculation, accessor, or utility already exists, use it. Inline re-derivation causes drift. Extend the single authority; do not fork it.

**IV.4 — Expose before inventing.** A genuine gap is filled by exposing existing truth better, or by adding a **truth or action tool** — never by inventing a bespoke reasoning capability inside WLJ.

### Article V — Product Governance

**V.1 — Product experience governs future refinement.** The only success metric is: *"If this were the only conversation a paying customer ever had with their Chief of Staff, would they immediately want to use it again tomorrow?"* Every production review is **Product first, then Architecture**. The customer experiences **trust**, not layers.

**V.2 — Eliminate the class, don't detect the symptom.** When a trust-breaking failure appears, ask what architectural **condition** made it possible and whether that condition can be **removed** (so the whole class becomes structurally impossible), rather than adding another detector. Bounded by blast radius: if removal needs a disproportionate rewrite, contain the class narrowly and **log the residual**.

**V.3 — The development model is layered and top-down.** For any Chief-of-Staff production issue, classify the failing layer — **Truth (WLJ) → Reasoning (the model) → Action (WLJ) → Experience** — and fix the first layer that failed. Most fixes are Layer 1 (truth). Reflection sits **above** these layers and only observes them; learning is default-deny and never learns around a deterministic defect.

---

## 3. Constitutional Review Process (mandatory)

A **Constitutional Review** is required whenever a proposal would change, weaken, remove, or invert any Article in §2, the naming rule in §1, or the framing in §0. This includes proposals to: build a reasoning/conductor/classifier engine inside WLJ (I.2, IV.2, IV.4); have the model own a deterministic calculation or WLJ emit verdicts (I.3, I.4); introduce a second producer for a truth domain or for "what to do now" (III.1, III.2); let scraped DOM or related truth override Current Context (II.1, II.4); bypass deterministic validation or the safe action path (I.6, I.7); hardcode a provider or user AI name as identity (§1, I.8); or add a bespoke capability where better truth or an existing tool would do (IV.2–IV.4).

### The review procedure

When any such proposal arises, **STOP** and do not implement it. Produce a Constitutional Review notice stating, prominently:

> ⚠️ **CONSTITUTIONAL CHANGE PROPOSED**
> This proposal changes the constitutional architecture of the WLJ Chief of Staff, established through months of architecture, engineering, and production validation.
> - **Article(s) affected:** _(list)_
> - **What the proposal changes:** _(plain description)_
> - **Why the problem cannot be solved inside the Constitution:** _(required — show the in-Constitution options were exhausted)_
> - **Blast radius / what this would destabilize:** _(honest assessment)_
>
> **Do you intentionally wish to change the Constitution?**
> The default expectation is **NO.** Constitutional changes require **Danny's explicit written approval.** Absent that approval, the problem is solved inside the Constitution instead.

### Rules of the process

1. **Solve inside the Constitution first.** Show the in-Constitution options were genuinely considered and are insufficient. "Cleaner" or "smarter" is **not** sufficient grounds.
2. **Explicit written approval from Danny is required** to proceed. A general "move forward" on unrelated work is **not** approval for a constitutional change.
3. **Default NO.** If in doubt whether a change is constitutional, treat it as constitutional and open the review.
4. **Record the outcome.** Every review (approved or declined) is recorded in the Amendment Log below. Engineering history is never deleted.

Ordinary work — new features, new domains, new truth, new tools, better prompts, better UX, bug fixes — does **not** require a Constitutional Review, as long as it stays inside the Articles. The Constitution constrains *architecture*, not *progress*.

---

## 4. Enforcement (executable, not just aspirational)

| Article | Enforced by |
|---|---|
| I.2 / IV.2 (no reasoning/inline-LLM/heavy compute on request path) | `apps/core/tests/test_request_path_safety_contract.py` |
| III.2 (one Execution Decision Authority) | `apps/core/tests/test_execution_decision_authority_contract.py` |
| V.1 / Visual truth | `apps/core/tests/test_visual_truth_contract.py` |
| Intent registration integrity | `apps/ai/tests/test_intent_registration.py` |
| This Constitution (Articles, enforcement refs, naming, no-fabrication) | `apps/core/tests/test_constitution_contract.py` |

The permanent acceptance baseline (`docs/WLJ_ACCEPTANCE_BASELINE.md`) runs these together.

---

## 5. Amendment Log

| Date | Version | Article(s) | Decision | Rationale |
|---|---|---|---|---|
| 2026-07-11 | 1.0 | — | **Ratified** | WLJ Chief of Staff Architecture Milestone. Initial constitution established. |

*No amendments. The Constitution stands at Version 1.0.*

---

## 6. Related documents

- Sibling startup docs: `00_READ_FIRST_WLJ_CHIEF_OF_STAFF_ARCHITECTURE.md` (what/why), `02_ENGINEERING_OPERATING_GUIDE.md` (how to evolve safely), `03_DANNY_WORKING_PREFERENCES.md` (how to work with Danny), `98_SESSION_TRANSITION_PROTOCOL.md` (how to close a chat), `99_REFERENCE_INDEX.md` (master TOC). The transient bootloader `99_NEXT_CHAT_STARTUP.md` lives at the `@WLJ_SYSTEM_PROMPTS/` root, not in this evergreen package.
- Authoritative detail (supporting library): `docs/WLJ_PRODUCT_VISION.md`, `docs/WLJ_LLM_TRUTH_ACTION_CONTRACT.md`, `docs/WLJ_ARCHITECTURE_LAWS.md`, `docs/WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md`, `docs/WLJ_CURRENT_CONTEXT_CONTRACT.md`, `docs/WLJ_VISUAL_TRUTH_CONTRACT.md`, `docs/WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md`, `docs/LAYER1_DOMAIN_FRAMEWORK.md`.

---

*This Constitution establishes the foundational, constitutionally protected architecture of the WLJ Chief of Staff. Future work should improve the product while remaining inside these boundaries, and should change the architecture only through a Constitutional Review explicitly approved by Danny.*
