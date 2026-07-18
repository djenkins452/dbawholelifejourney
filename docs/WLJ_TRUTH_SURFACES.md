# WLJ Truth Surfaces — Validated As-Built Catalog

**Status:** Reference documentation of an architectural fact **proven by production certification (2026-07-18)**. Read-only knowledge capture — it changes no runtime behavior, routing, or data. It records what the architecture already does.

> **Related (separate) doc:** `docs/DRAFT_THREE_TRUTH_SURFACES_AND_PTP.md` is a *design proposal* (Personal Truth Profile, NOT canonical). This document is the *validated as-built catalog* of the truth surfaces the Chief of Staff demonstrably reasons from today. Where the two framings differ, reconcile there — do not treat this as superseding the design work.

---

## Definition
A **Truth Surface** is *a deterministic source of truth that can legitimately supply facts to the Chief of Staff.*

The production certification run disproved an earlier assumption that the CoS receives deterministic truth **primarily** through `DomainTruth`. In production, the CoS correctly answered questions whose facts came from **several** deterministic surfaces — e.g. **Goals** answered from **Standing Context** (no `goals` DomainTruth exists), **Fitness** from a **Domain Entity Surface** (`health.describe("workout")`). Truth reaches the model through more than one door.

---

## The validated truth surfaces

Truth-type legend — a surface supplies one or more of: **summary · detailed · execution · contextual · historical**.

### 1. DomainTruth
- **Purpose:** the single canonical per-domain interface — `current()` / `history()` / `describe()` — for a domain's deterministic facts.
- **Ownership:** each domain's registered provider (`@register_domain_truth`), `apps/core/truth/domain.py`. Model-facing tools: `get_domain_state`, `get_history`, `get_entity`, `get_analysis`.
- **Appropriate use:** item-level and time-series facts about a specific domain (weight history, med adherence, workout sets).
- **Strengths:** read-live from canonical models (never stale), deterministic, provenance-bearing, catalog-discoverable, per-capability.
- **Limitations:** only exists for **registered** domains — many domains (goals, people, body-measurements, medical-labs, documents) have **no** provider yet.
- **Prefer when:** the question needs *detailed or historical* truth about one domain, or item-level confirmation.
- **Supplies:** detailed · historical · current.

### 2. Domain Entity Surfaces
- **Purpose:** record-level truth — `describe()` / `describe_one()` returning `CompleteEntity` objects (the Entity Completeness Law).
- **Ownership:** a facet of a domain's `DomainTruth` (`entity_types` + `describe`); model-facing tool `get_entity`. E.g. `health.describe("workout")`, `medicine.describe_one(name)`, `nutrition.describe("food")`.
- **Appropriate use:** "show / tell me about *this record*" — a medication, a workout and its sets, a logged food.
- **Strengths:** one deterministic retrieval fully answers the natural questions about a record; grounds the model in real user records, not generic knowledge.
- **Limitations:** only domains that register `entity_types`; date/window scoping depends on the provider (e.g. nutrition lacks a date filter today).
- **Prefer when:** the question is about a *specific record's* contents (exercises, sets, dose, food items).
- **Supplies:** detailed.

### 3. Standing Context
- **Purpose:** the always-present canonical **summary** block in every turn's system prompt — the executive read plus supporting headlines (`executive_read`, `priorities`/`user_priorities`, `cos_intelligence`, `medication_adherence`, `calendar_today`).
- **Ownership:** `apps/ai/cos_services/standing_context.py` (composes pre-warmed context; never live-computes on the request path).
- **Appropriate use:** orientation and summary facts the CoS can state without a tool call; the executive conclusion to lead with.
- **Strengths:** always present, zero-latency, cross-domain, canonical summary. **This is how Goals/priorities answered in production with no goals tool.**
- **Limitations:** **summary-level** (its own trust-framing: *"canonical SUMMARY state; confirm item-level claims via domain or decision tools"*, `standing_context.py:158`); pre-warmed, so it can be briefly stale relative to a live tool.
- **Prefer when:** the executive read, orientation, or a summary fact — and to decide *whether* an item-level tool call is even needed.
- **Supplies:** summary · contextual.

### 4. Personal Truth
- **Purpose:** a canonical cross-module **projection** of durable, explicitly-stored user facts (targets, conditions, medications, relationship, priorities) the CoS reasons *from* every turn.
- **Ownership:** `apps/ai/cos_services/personal_truth.py` — one composer feeding a standing block + the `get_user_truth` tool. Read-only, per-fact `module`+`source` provenance, conflict-surfacing.
- **Appropriate use:** stable "who the user is / what they've told us" facts; grounding reasoning in the person's durable reality.
- **Strengths:** deterministic, provenance-bearing, cross-domain, conflict-aware (canonical wins, never AI-resolved).
- **Limitations:** **explicit facts only** (derived facts deferred); it is a projection, **never a store, authority, or derivation**.
- **Prefer when:** the CoS needs durable personal facts to reason correctly (a target weight, a condition, a stated priority).
- **Supplies:** contextual · summary (durable facts).

### 5. Current Context
- **Purpose:** what the user is **looking at right now** — the current screen as a focused object (`app.model:pk`) or page summary (`summary:<key>`).
- **Ownership:** `apps/ai/cos_services/current_context.py` + `get_current_context_baseline()`; the page declares `<meta name="wlj-context">`, resolved **server-side** (scraped DOM never trusted).
- **Appropriate use:** "this" / page-relative questions, answered *before* any retrieval.
- **Strengths:** deterministic, immediate, precisely scoped to the user's focus; first in the precedence hierarchy.
- **Limitations:** only the current screen — not general or historical.
- **Prefer when:** the question references the current page/object ("what's this?", "how am I doing on *this*?").
- **Supplies:** contextual.

### 6. Executive Briefings
- **Purpose:** the composed **executive read / daily agenda / wrap-up** — an interpreted summary of the user's day and state.
- **Ownership:** `apps/ai/chatgpt_cos/executive_brief.py` (`compose_executive_brief`), `apps/core/cos_briefing/daily_agenda.py` (`build_daily_agenda`), and `cos_intelligence` (surfaced via standing context).
- **Appropriate use:** "how am I doing", daily orientation, end-of-day wrap-up.
- **Strengths:** synthesizes cross-domain deterministic facts into one executive conclusion.
- **Limitations:** it is *interpreted* summary (a conclusion), not raw item-level truth; interpretation must remain grounded in the underlying facts (see Grounding Discipline).
- **Prefer when:** the user wants the executive conclusion / orientation rather than a specific record.
- **Supplies:** summary · contextual (interpreted).

### 7. Decision Authority
- **Purpose:** **the single producer of "what to do now."**
- **Ownership:** `apps/core/execution/decision_authority.py :: current_action(user)` — one selector; CI rejects a second. Surfaces *consume* it; they never re-derive.
- **Appropriate use:** "what should I do now / what's next / what's due."
- **Strengths:** one authoritative, occurrence-scoped answer for the current action; eliminates drift between surfaces.
- **Limitations:** execution / now-focused — not historical, not summary.
- **Prefer when:** the question is about the *current or next action*.
- **Supplies:** execution.

---

## They are complementary, not competing
These surfaces are **complementary deterministic views of one life**, not rival sources. The CoS reasons from **multiple** surfaces in a turn; it does **not** rely exclusively on `DomainTruth`. A rough precedence for *answering a question* (from the Current-Context precedence rule):

**Current Context → conversation → truth-in-context (Standing Context / Personal Truth) → tools (DomainTruth / Domain Entity / Decision Authority) → general knowledge.**

Standing Context and Personal Truth provide the *summary/contextual* floor every turn; DomainTruth and Domain Entity Surfaces provide *detailed/historical* depth on demand; Decision Authority owns *execution*; Executive Briefings synthesize; Current Context scopes to the user's focus. A well-formed answer uses summary surfaces to orient and detail surfaces to confirm item-level claims.

---

## Key architectural principle (elevated from production certification)

> **A missing provider changes *which deterministic truth surface* supplied the answer; it does not necessarily determine whether the answer is possible.**

Corollaries proven in production:
- **Absence of a `DomainTruth` provider is not absence of truth.** Goals answered from Standing Context; Fitness from a Domain Entity Surface. Do not declare a production answer impossible from the provider registry alone — **trace which surface served it.**
- **Certification must measure the surface the customer actually reaches** (Owner-2 / Customer Truth), not just the `DomainTruth` tool catalog (Owner-1). This is precisely why the production run answered questions the Owner-1 capability matrix marked "no provider."
- **A summary-surface answer can be a *partial*.** When a fact arrives via a summary surface (Standing Context) with no detailed surface behind it, item-level / historical depth is weak (Goals milestones were vague). The remedy is usually to **add the missing DETAILED surface (a DomainTruth provider)** for depth — not to distrust the summary.
- **Grounding discipline still applies.** A surface supplies deterministic facts; the model's *interpretation* (executive briefings, cross-domain synthesis) must stay grounded in those facts and must not blend generic external guidance into a "strictly WLJ" answer.

---

*This document preserves an architectural discovery. It authorizes no implementation. The certification-driven roadmap continues: implement only evidence-backed deterministic improvements, avoid the parallel Nutrition work, and proceed with the next measured slice (Glucose/BP trends or Body Measurements) once ownership is clarified.*
