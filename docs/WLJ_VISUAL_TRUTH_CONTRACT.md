# WLJ Visual Truth Contract

**Status:** Permanent architecture invariant.
**Owner:** All UI surfaces, enforced by tests, reviewed on every CSS / template PR.
**Origin:** 2026-05-20 trust-breaking incident — the homepage Action Center applied strike-through to items that were past their window but not completed; CoS correctly reported them as incomplete; the two surfaces visually disagreed about what the user had done. See `docs/wlj_claude_changelog.md` 2026-05-20 entry for the full incident.

---

## The Contract

> **Only actual user completion may visually resemble completion.**
>
> Homepage visual state must NEVER imply false completion.

This is the single non-negotiable rule. Every other rule in this document is a derivation of it.

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
