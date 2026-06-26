# Beth Domain Maturity Matrix

> **Per-domain maturity of Beth's truth coverage, scored across the truth pipeline.**
> Companion to `BETH_TRUTH_COVERAGE_AUDIT.md`. **Date:** 2026-06-26

## Scoring

Each domain is scored across the seven pipeline stages a fully-mature domain reaches
(✅ = present, ◑ = partial/summary-only, ❌ = absent):

| Stage | Meaning |
|-------|---------|
| **SAE** | canonical computed state (`build_*_state`) |
| **Dash** | surfaced on the dashboard |
| **Fact** | deterministic foundational fast-fact |
| **Brief** | woven into executive briefing / standing context |
| **Proact** | has a proactive check-in |
| **Reason** | deliberate reasoning lane (curated, with fallback) |
| **Read** | Beth can read it on demand (tool/state/history) |

**Maturity tiers:**
- **T4 — Holistic** (Beth knows, reasons, briefs, and reads): the target.
- **T3 — Surfaced** (canonical + dashboard + briefing + proactive, **no reasoning/facts**).
- **T2 — Readable** (canonical state, Beth reads via tool only; no briefing/reasoning).
- **T1 — Thin/partial** (minimal canonical state, weak/no Beth integration).
- **T0 — Orphaned** (WLJ knows it; Beth has no access).

## Matrix

| Domain | SAE | Dash | Fact | Brief | Proact | Reason | Read | **Tier** | Coverage |
|--------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **Health (vitals/weight/glucose/sleep)** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **T4** | ~100% |
| **Medication / supplements** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | **T3** | ~85% |
| **Tasks / execution / routines / calendar** | ✅ | ✅ | ❌ | ✅ | ✅ | ◑ | ✅ | **T3** | ~80% |
| **Faith** | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ | **T3** | ~75% |
| **Goals / Purpose** | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ | **T3** | ~75% |
| **Nutrition** | ✅ | ✅ | ✅ | ◑ | ◑ | ❌ | ✅ | **T3** | ~70% |
| **Habits** | ✅ | ✅ | ❌ | ◑ | ✅ | ❌ | ✅ | **T3** | ~70% |
| **Relationships / people** | ✅ | ◑ | ❌ | ◑ | ✅ | ❌ | ✅ | **T3** | ~65% |
| **Finance** | ✅ | ◑ | ❌ | ◑ | ✅ | ❌ | ✅ | **T3*** | ~60% |
| **Journal** | ✅ | ◑ | ❌ | ◑ | ✅ | ❌ | ✅ | **T3** | ~60% |
| **Fitness / workouts / PRs** | ✅ | ◑ | ❌ | ◑ | ✅ | ❌ | ✅ | **T2** | ~55% |
| **Medical / labs** | ✅ | ◑ | ❌ | ◑ | ❌ | ❌ | ◑ | **T2*** | ~40% |
| **Capture (inbox)** | ◑ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | **T2** | ~30% |
| **Sports (teams/games)** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ◑ | **T2** | ~25% |
| **Brain training** | ◑ | ❌ | ❌ | ❌ | ❌ | ❌ | ◑ | **T1** | ~20% |
| **Meals / pantry** | ◑ | ❌ | ❌ | ❌ | ❌ | ❌ | ◑ | **T1** | ~20% |
| **Life events (significant/birthdays)** | ◑ | ❌ | ❌ | ◑ | ✅ | ❌ | ◑ | **T1** | ~30% |
| **Scan / camera analyses** | ◑ | ❌ | ❌ | ❌ | ❌ | ❌ | ◑ | **T1** | ~15% |
| **Emotional state** | ❌ | ❌ | ❌ | ◑ | ❌ | ❌ | ◑ | **T0** | ~10% |
| **Documents (life + medical)** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **T0** | 0% |
| **Life misc (pets, inventory, recipes, shopping)** | ❌ | ❌ | ❌ | ❌ | ◑ | ❌ | ◑ | **T0** | ~5% |
| **`faith.journey`** (dead reference) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **T0** | 0% |

\* sensitivity-gated domains (finance, medical) — coverage is capped intentionally
pending the privacy ratification in the roadmap.

## What the tiers tell us

- **Exactly one T4 domain (Health).** Every other domain — even the well-surfaced
  ones — lacks the *reasoning* (and usually the *fact*) layer. That single column
  (`Reason`) is the dominant maturity gap.
- **A large, healthy T3 band (8 domains)** is the opportunity: these already have
  canonical state + dashboard + briefing + proactive — they need only the reasoning
  + facts layer to reach T4. **Cheapest path to holistic coverage.**
- **T2 hides the richest waste:** medical/labs has rich canonical state but ~40%
  coverage — high value, currently tool-only.
- **T0 = true debt:** documents (0%) and emotional (~10%) are the genuine orphans;
  `faith.journey` is a dead registry reference to clean up.

## Maturity → roadmap mapping

| Tier band | Domains | Roadmap action |
|-----------|---------|----------------|
| T4 | Health | maintain; the reference implementation for curators |
| T3 → T4 | medication, tasks, faith, goals, nutrition, habits, relationships, finance*, journal | **Roadmap Phase 1–2** (facts + reasoning curators) — highest ROI |
| T2 → T3/T4 | fitness, medical/labs*, capture, sports | **Phase 3 + 5** (labs first — richest) |
| T1 | brain-training, meals, life-events, scan | **Phase 5** opportunistic |
| T0 | documents, emotional, life-misc, faith.journey | **Phase 4** (reclaim orphans) + delete the dead reference |

## Single-number summary

- **Domains WLJ tracks (truth exists):** ~22 user-truth domains.
- **Domains Beth can *read*:** ~16 (◑ or better on `Read`).
- **Domains Beth can *reason* over:** **1** (health; tasks partial via execution).
- **Domains fully orphaned from Beth:** 3–4 (documents, emotional, life-misc, dead faith.journey).
- **Overall Beth holistic-truth coverage (weighted):** ≈ **45%** — high *read*
  breadth, low *reasoning* depth. The roadmap targets ~85%+ by lifting the T3 band to
  T4 (reasoning + facts) without building any new truth.
