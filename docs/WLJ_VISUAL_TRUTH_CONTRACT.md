# WLJ Truth Presentation Contract
*(formerly, and still filed as, the Visual Truth Contract)*

**Status:** Permanent architecture invariant.
**Owner:** All customer-facing surfaces (UI templates, CSS, page summaries, sync/status messages, mobile app), enforced by tests, reviewed on every UI / template / async-workflow PR.
**Origin:** 2026-05-20 trust-breaking incident (visual completion) — expanded 2026-07-15 to cover lifecycle completion after the Health Sync investigation found "Sync Complete" was being shown for a *network upload*, not verified persistence.

---

## The umbrella rule

> **The customer must never be shown a state that claims more certainty than WLJ has actually established.**

This is the one governing rule. It has **two dimensions**, each a derivation of it:

| Dimension | Axis | Failure it prevents | Enforced by |
|---|---|---|---|
| **1 — Visual Truth** (spatial) | *how a state looks* | An incomplete item **looking** done (strike-through, ✓, completed colour) | `apps/core/tests/test_visual_truth_contract.py` |
| **2 — Lifecycle Truth** (temporal) | *what stage a state has reached* | An async workflow **claiming** completion for a stage it only *initiated* (e.g. "Sync Complete" = upload sent) | `apps/core/tests/test_truth_presentation_contract.py` |

Both dimensions protect the same thing: **trust**. If the product tells the customer something is done when it isn't — whether by a strike-through or by a premature "Sync Complete" — the customer loses the ability to trust the surface, and from that moment they're managing the *app*, not their life.

The rule is deliberately housed in ONE document (not fragmented into a separate "Async Truth" doctrine): Visual and Lifecycle are two faces of the same discipline. This is a **product-presentation** contract, not a Constitutional Article — it changes how WLJ *communicates* deterministic truth, not who *owns* it.

---

# Dimension 1 — Visual Truth (spatial)

## The Contract

> **Only actual user completion may visually resemble completion.**
>
> Homepage visual state must NEVER imply false completion.

This is the single non-negotiable rule of this dimension. Every other rule in this section is a derivation of it.

The rule exists because trust between the user and the system is the foundation everything else sits on. If the homepage tells the user "you finished this" and CoS tells the user "you haven't done this yet," the user loses the ability to trust either surface — and from that moment forward, they're managing the *app*, not their day.

---

## What "actual user completion" means

A state where the data layer can definitively answer **yes** to "did the user do this thing?"

Examples that qualify:
- `Task.completion_status == 'completed'`
- `WorkoutScheduleLog` exists for today with `is_completed = True`
- `IntakeDose.status == 'taken'`
- A routine item has been explicitly checked off
- A binary action (journal / workout / faith) has been logged for today

Examples that do **NOT** qualify (these must NEVER visually look completed):
- Past scheduled time but no user action (overdue)
- Past window cutoff but still recoverable today (`behind`)
- Past a HARD_EXPIRED grace (`missed` — the opportunity is gone but the user did NOT complete it)
- Recovery-mode de-emphasised (still actionable, just lower priority while anchors take focus)
- Skipped via an automatic system process (not a deliberate user "I'm done with this")

---

## Allowed visual treatments

For **anything that is not actually completed**, the only acceptable visual signals of state are:

| Treatment | What it communicates | When OK |
|---|---|---|
| **Badges** (small text label: `BEHIND`, `MISSED`, `PAST DUE`, `NOW`, `RESET`, `FOUNDATIONAL`) | Specific state, named in plain language | Any time the state is meaningful to the user |
| **Muted text colour** (grey title, e.g. `#888`) | Lower visual weight | Past-window, recovery-de-emphasised |
| **Subtle dimming** (opacity 0.70–0.90) | Lower priority but unambiguously present | Recovery-mode non-foundational overdue items |
| **Left-rail ring / border colour** (`ring-expired` grey, `ring-overdue` red, `ring-now` blue, `ring-foundational` yellow) | State at a glance via colour | Any state |
| **Warm tone for urgency** (`tone-warning` red, `tone-active` blue) | "Needs attention now" / "happening now" | Overdue in grace, in-window |
| **Foundational dot / border** | "This is an anchor" | Foundational items |

These signals can be combined. None of them, individually or together, may produce a treatment that reads as "done."

---

## Reserved EXCLUSIVELY for `item.completed == True`

The following visuals are **completion signals** and may **only** be applied when the data layer confirms the user actually completed the item:

| Treatment | Notes |
|---|---|
| **Strike-through** (`text-decoration: line-through` in any form) | The most powerful "this is done" signal in UI. Reserve absolutely. |
| **Heavy opacity reduction** below 0.7 | At ≤0.6 opacity an item reads as "handled / dismissed / archived" |
| **Filled checkmark** (✓ on a filled background) | The literal "done" glyph |
| **"Completed" colour** (green tick fill, completed-state background) | Direct semantic association with completion |
| **"Completed" badge text** ("done", "completed", "✓") | Literal text claim of completion |

If you want to add a new visual treatment to the codebase and it could reasonably be read as "done," it goes in this list and is gated on a real completion signal from the data layer — no exceptions.

---

## How the contract is enforced

1. **Test** `apps/core/tests/test_visual_truth_contract.py` — parses `static/css/dashboard_v2.css` after every change and asserts:
   - No selector declares `text-decoration: line-through` unless it is in an explicit allowlist of completion-gated selectors.
   - `.v2-ac-item-expired` (the 2026-05-20 incident site) specifically never re-introduces strike-through.
   - `.v2-ac-recovery-dim` opacity stays in 0.70–0.95 (visible de-emphasis, not "dismissed").
   - To add a new completion-gated selector to the allowlist, the test requires a comment proving the template only applies the class on a real completion signal.

2. **Code review.** Any CSS or template change that touches the Action Center must be reviewed against this document.

3. **Scope.** The test guards the **homepage Action Center stylesheet** (`dashboard_v2.css`) directly. Other domain stylesheets (life, health, assistant-panel) were audited at the time of the 2026-05-20 incident and found to be correctly gated on `.completed` / `.skipped` / `{% if checked %}`. If those audits drift, sibling tests should be added — the existing test does NOT pretend to cover them.

---

## Architectural pipeline that this protects

```
raw data
  ↓
signals / state / execution truth
  ↓
CoS + UI  (BOTH derived from the same truth)
```

CoS and Homepage must **derive from the same execution truth**. The 2026-05-20 incident did not break this pipeline at the data layer — the pipeline was intact, CoS read it correctly. The break happened at the presentation layer where a single CSS rule re-interpreted "past window" as "completed." Restoring trust required removing one CSS declaration; this contract exists so a similar re-interpretation cannot silently land again.

---

## When you find yourself wanting to break this rule

If you find yourself reaching for a strike-through (or any completion visual) to "soften" or "de-emphasise" a non-completed item: **stop**. Use a badge plus muted text plus subtle dimming. Three independent non-completion signals beat one ambiguous completion signal every time.

If you find yourself thinking "the badge says 'BEHIND' so the strike-through can't be confusing": **stop**. Visual semantics override text semantics. A user's eye registers the strike-through before they read the badge. They process it as "done." The badge becomes noise.

If a user can ever look at the homepage and ask "did I do this?" the contract has been broken. The visual must answer that question unambiguously every time, in favour of the data layer's truth.

---

# Dimension 2 — Lifecycle Truth (temporal)

## The Contract

> **A customer-facing status must represent the highest VERIFIED deterministic stage WLJ has established — never the furthest stage it initiated, enqueued, or expects to reach.**

Where Visual Truth governs *how a state looks*, Lifecycle Truth governs *what stage a state has actually reached* in an asynchronous workflow. The failure it kills is the whole class of "we told the customer it was done because we finished our part of it":

- "Sync Complete" shown when the network upload finished (but the server hasn't confirmed persistence).
- "Analysis ready" shown when an image finished uploading (but OCR/vision hasn't run).
- Body Intelligence trends shown as current when a newer sync hasn't been folded into the derived summaries yet.

In every case an **implementation event** (a transmission, an enqueue, a request accepted) was presented to the customer as a **truth** (the work is done). **The customer must never be the reconciler** — they should never have to wonder whether WLJ is waiting, working, or finished.

## The canonical lifecycle vocabulary

Customer-oriented, ordered from least to most established truth. Defined once in `apps/core/truth/lifecycle.py` and shared across every async workflow. The vocabulary is **conceptual** — each domain keeps its own persisted status enum (`HealthIngestionRun.status`, `CaptureEntry.status`, …) and *maps onto* these stages when it speaks to the customer. Domains may add domain-specific stages; they must not redefine these.

| Stage | Meaning (customer-oriented) |
|---|---|
| **Initiated** | The user's action was accepted; work is beginning. |
| **Received** | WLJ has custody of the input **server-side** — not merely "in transit." |
| **Persisted** | Canonical records are written to the system of record. Durable. This is the earliest point at which **"Saved"** is honest. |
| **Derived** | Downstream computed layers (summaries, scores, intelligence) have been rebuilt from the persisted truth. |
| **Current** | The derived truth is readable **and** up to date on the customer's surfaces. This is the only stage at which **"up to date / complete"** is earned. |

Three **qualifiers** modify a stage (they are not points on the line): **partial** (reached for some items, not all), **failed** (could not complete; reason known), **stale** (a later stage is readable but reflects an *older* persisted truth). Any qualifier of `partial`, `failed`, or `stale` **forbids a completion claim.**

`Current` is defined to compose with the existing freshness capability (`apps/core/truth/freshness.py`): it is exactly the point at which the derived layer's freshness verdict is `CURRENT`.

## Product rules

Every customer-facing async workflow must obey these:

1. **Completion is earned.** A surface may present "done / up to date / complete" **only** at `Current` with no blocking qualifier. Never at `Initiated`, `Received`, `Persisted`, or `Derived`. (`lifecycle.may_claim_complete`.)
2. **"Saved" is the honest floor.** Once data is `Persisted`, the customer may be told it's **saved** even while derived layers catch up — but "saved" ≠ "up to date." (`lifecycle.may_claim_saved`.)
3. **Partial success stays partial.** If some items failed, say so; never round a partial run up to success.
4. **Processing reflects real work.** "Working / updating" is shown only while a stage is genuinely in flight or a derived layer is genuinely rebuilding — never as decoration, never left on forever.
5. **Stale derived data is identified.** When newer truth has been persisted than a derived surface reflects, the surface says "updating" (or "as of &lt;when&gt;"), never presents the stale figures as current.
6. **The customer is never the reconciler.** One deterministic source maps the workflow to its claim; two surfaces of the same workflow never disagree about its stage.

Surfaces route through `lifecycle.claim_key(stage, qualifier=…)`, which returns the single honest claim key (`up_to_date` / `saved` / `updating` / `partial` / `failed` / `received` / `working`) — it can never emit a claim more optimistic than the verified stage allows. The surface (or the model) turns that key into words; the **facts** come from WLJ.

## As-built adoption (2026-07-15)

| Surface | Before | After |
|---|---|---|
| **Body Intelligence** (`services/body_intelligence.py`, `body_intelligence.html`, `page_summaries.py`) | Trends/scores presented as current even when a newer sync hadn't been folded into `DailyHealthSummary`. | `build_body_intelligence` emits a `freshness` fact (`derived_state(persisted_at, derived_at)`); the page shows a calm, non-completion **"still being folded in — a few figures may update shortly"** banner and the page summary states it as a fact. Stale derived data is never shown as current. |
| **Health Sync status** (`services/health_sync_status.py`) | Called an undefined `_sync_lifecycle_fact(run)` — a latent runtime error, and a half-built inline lifecycle. | Inline attempt removed; lifecycle interpretation now lives once in `apps/core/truth/lifecycle.py` (`sync_lifecycle(...)`), consuming ingestion-run counts WLJ already computes. |

## How Dimension 2 is enforced

1. **Contract test** `apps/core/tests/test_truth_presentation_contract.py` pins the product rule: completion cannot be claimed below `Current`; blocking qualifiers forbid completion even at `Current`; a clean just-finished sync with unknown derived freshness caps at **Saved** (never "up to date"); partial stays partial; stale reports **updating**; a never-built derived layer reports **pending**.
2. **The rule is code, not convention.** `apps/core/truth/lifecycle.py` is the ONE place the stage→claim mapping lives. A new async surface consumes it — it must not re-derive "is this done?" locally (that reintroduces the drift class).
3. **Review checklist.** Any PR that adds or changes a customer-facing async workflow (sync, upload, OCR, generation, rebuild, recovery) answers: *what is the highest verified stage this surface can prove, and does its wording claim no more than that?*

## Migration roadmap (ranked by customer-trust impact)

Adopt the standard where completion is currently assumed. Already done: **Health Sync / Body Intelligence** (highest impact — it's the customer's health data). Next candidates, in priority order, each to be converted from "event = done" to "highest verified stage," or explicitly recorded as compliant:

1. **Image / multimodal upload → analysis** — "uploaded" must not read as "analyzed."
2. **OCR / document & medication scan** — "scanned" must not read as "extracted & saved."
3. **Executive summary / reflection generation** — "generating" vs a stale prior artifact shown as current.
4. **Operations recovery** — distinguish "recovery initiated" from "recovered."
5. **Current Context regeneration** — stale context must not present as current.

Workflows already compliant (they surface real stage, not optimistic completion) are left alone. Where compliance would require a disproportionate redesign, it is recorded as technical debt with rationale rather than forced.

---

## Relationship to the rest of the architecture

- **WLJ owns deterministic truth.** Lifecycle Truth doesn't invent a new source — it *interprets* truth WLJ already owns (ingestion-run counts, summary build times, freshness verdicts). It is not a parallel state machine and stores no state.
- **Current Context.** Overview page summaries (`PageSummaryMixin`) now carry lifecycle/freshness as *facts* so the model never narrates stale derived data as current.
- **Request-path safety.** Lifecycle reads are cheap, indexed, pre-computed reads (e.g. one `HealthIngestionRun` lookup) — no heavy compute on the request path.
- **Product-first engineering.** This is a presentation-discipline standard: it changes what the customer is told, ranked by trust impact — not the ownership of truth, which is why it is a contract, not a Constitutional Article.
