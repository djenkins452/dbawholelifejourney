# Beth Truth Gap Analysis

> **Where WLJ knows truth about Danny that Beth cannot access, reason over, or
> weave into briefings — and why.** Companion to `BETH_TRUTH_COVERAGE_AUDIT.md`.
> **Date:** 2026-06-26

## The central gap (one sentence)

**WLJ computes rich canonical state for ~18 domains and surfaces ~9 of them on the
dashboard/briefings, but Beth can *deliberately reason* over exactly one — health.**
Everything else is either read-only (tool loop / standing summaries) or invisible.

## Gap classes

### G1 — The reasoning-coverage gap (HIGHEST impact)
The reasoning lane (`apps/ai/chatgpt_cos/reasoning/`) has 4 intents, all health,
and `INTENT_TRUTH_SCOPE` is `HEALTH_TRUTH` only. The planner vocabulary lists
`fitness, nutrition, goals, faith, tasks, execution` in `ALLOWED_DOMAINS`, but **no
non-health intent is implemented**, so those domains are never retrieved or reasoned
over. Result: a question like *"how are my goals tracking?"* or *"am I overspending
this month?"* falls to the **demoted agentic tool loop** (P8) — the least reliable,
least curated path — rather than a curated reasoning lane.
- **Impact:** Beth answers health questions like a Chief of Staff and everything
  else like a search box. This is the biggest lever for "holistic truth."

### G2 — The foundational-facts gap
Only **12 fast-facts** exist, all health/nutrition/medicine (weight, glucose, BP,
sleep, calories, protein, meds). No deterministic fast-fact for: *net worth, budget
status, next bill, goal count/next deadline, prayer streak, current reading plan,
today's workout, journal streak, last lab result, relationship birthdays.* These are
all already in canonical SAE state — they just aren't wired as facts.

### G3 — Orphaned truth (WLJ knows it; Beth has ZERO access)
| Orphan | Stored | SAE? | Why orphaned |
|--------|--------|------|--------------|
| **Documents** | `life.Document`, `medical.MedicalDocument` | none | No SAE module, no domain-state, no tool, no search. Beth literally cannot see uploaded documents. |
| **Emotional state** | `journal.Emotion` (M2M on entries) | none (folded into journal mood) | No `emotional` SAE module; no domain-state registry entry; emotion only leaks out as `journal.mood_avg_7d`. |
| **`faith.journey`** | reading-journey progress | not a real domain | Registered name with no provider — dead reference. |
| **Life-misc** | `life`: Pet/PetRecord, InventoryItem, Recipe, ShoppingList, MaintenanceLog | only `life_events` | Pets, inventory, recipes, shopping, maintenance are invisible to Beth. |

### G4 — Dashboard-/briefing-only truth (user sees it; Beth can't reason over it)
Domains surfaced to the user (dashboard cards, proactive check-ins, executive
insights) but with **no reasoning capability**: **finance, relationships, journal,
nutrition, goals, faith, fitness.** Beth can *narrate composed insights* about them
(via the executive summary) and *fire scripted proactive check-ins*, but cannot
*answer a free-form judgment question* — the answer quality drops to the tool loop.
This is the "looks integrated, isn't reasoned" trap.

### G5 — Rich-but-under-surfaced canonical state (built, barely used)
The SAE builds **rich** state that Beth almost never sees:
- **Medical/labs** (`build_medical_state`: abnormal-results-90d, glycemic labs,
  metabolic intelligence) — Beth gets only "current medications." The single richest
  under-used truth source.
- **Fitness** (`build_fitness_state`: training-load, PRs, strength-trend) — tool-only.
- **Sports / brain-training / capture / scan** — built but tool-only, no briefing.

### G6 — Read-but-not-reasoned (tool-only) domains
`brain_training, meals, sports, capture, medical` are reachable via `get_domain_state`
(tool loop) but have **no standing-context weave, no foundational fact, no history
search (most), no reasoning**. Beth can fetch them only if the agentic loop chooses
to — non-deterministic and fragile.

## Duplicate / divergent truth systems (the good news)

The audit found **no problematic duplicate truth engines**:
- `DailyHealthSummary` / `DailyNutritionSummary` vs SAE → **layered consumer**
  relationship (SAE reads the nightly summary; falls back to live aggregation only
  when empty). Acceptable.
- Glucose multi-representation (latest / 7d / projected A1c) → **intentional** trust
  fix, not a duplicate.
- The one historical divergence — dashboard "next" (`build_rhythm_sections`,
  schedule) vs Beth "next" (`get_next_action`, urgency) — was **already fixed** by
  the canonical Rhythm API (P24). No open duplicate-truth defect remains.

## Privacy / "explicit architectural reason not to" candidates

Per the governing principle, these are the domains where an *explicit reason* may
justify limiting Beth (to be ratified, not assumed):
- **Finance** — Beth should know it for coaching, but raw account numbers / balances
  may warrant a sensitivity gate (summaries yes, full ledgers on explicit ask).
- **Medical/labs** — clinical caution: Beth narrates trends and adherence, never
  diagnoses (already the health-reasoning tone contract; extend to labs).
- **Documents** — content may be sensitive; access should be explicit-retrieval, not
  ambient.
Everything else defaults to **"Beth should know it."**

## Priority ranking of gaps (impact × readiness)

| Rank | Gap | Why first | Readiness (SAE already built?) |
|------|-----|-----------|-------------------------------|
| 1 | **G1 reasoning beyond health** (goals, tasks, finance, faith) | turns Beth from "health CoS + search box" into a whole-life CoS | ✅ canonical state already exists |
| 2 | **G5 medical/labs into briefing+reasoning** | richest under-used truth; high personal value | ✅ rich SAE built |
| 3 | **G2 foundational facts for non-health** | cheap, deterministic, high-frequency wins | ✅ all in SAE |
| 4 | **G3 documents + emotional** | true orphans; document access is a real CoS expectation | ❌ needs new SAE/access |
| 5 | **G4 finance/relationships/journal reasoning** | high value, needs privacy ratification | ✅ SAE built |
| 6 | **G6 sports/brain-training/meals/scan** | low stakes; opportunistic | ◑ thin SAE |

*Sequencing and phasing in `BETH_HOLISTIC_TRUTH_ROADMAP.md`.*
