# Beth Health Reasoning Intent Contracts

> **Authoritative behavioral contract for the four Phase-1 health reasoning
> intents.** Implemented by the reasoning lane
> (`apps/ai/chatgpt_cos/reasoning/{plan,stages,engine}.py`) and enforced by
> `apps/ai/tests/test_reasoning_lane.py`. Governed by
> `BETH_ARCHITECTURAL_PRINCIPLES.md` (P2, P3, P5, P6, P9–P11, P13).
> **Last updated:** 2026-06-25

The four intents must produce **materially different** answers — not variations of
the same response.

## Purpose

| Intent | Purpose |
|--------|---------|
| `biggest_health_risk` | The **single** highest-priority issue requiring attention |
| `health_focus_today` | The **best actionable step for today** (time-aware) |
| `health_concerns` | **Ranked list** of current concerns, each with explanation |
| `overall_progress` | **Executive summary** of overall status & trajectory |

## Full contract

| Intent | Question examples | Retrieval (all `HEALTH_TRUTH`-scoped) | Output structure | Differentiator |
|--------|-------------------|----------------------------------------|------------------|----------------|
| **biggest_health_risk** | "biggest health risk right now?" · "what's most wrong?" · "what should I worry about most?" | ranked concerns → **rank[0]** | One concern: concern + why + one action | Cardinality 1; diagnostic; current standing |
| **health_concerns** | "what are my health concerns?" · "list what's off" · "what health issues do I have?" | ranked concerns → **top N (≤4)** | Ranked list, each concern + 1-line explanation | Cardinality N (≥2 when available); survey |
| **health_focus_today** | "what should I focus on health-wise today?" · "one thing to do today?" | ranked concerns ∩ **today-actionable** + time-of-day context | (1) today's focus, (2) why it matters today, (3) one concrete 24h action | Action/imperative; **today + time-of-day** |
| **overall_progress** | "how am I doing overall?" · "am I on track?" · "health summary" | **status composite** (weight/glucose/sleep/pace) | Multi-domain status summary | Status/trajectory; not a problem list or action |

## Differentiation matrix

| Dimension | biggest_health_risk | health_concerns | health_focus_today | overall_progress |
|-----------|---------------------|-----------------|--------------------|------------------|
| Cardinality | 1 | N | 1 (action) | multi-domain summary |
| Framing | diagnostic | enumeration | imperative action | status/trajectory |
| Time horizon | current | current | **today + time-of-day** | trend |
| Primary data | rank[0] | rank[0..N] | rank ∩ today-actionable | status composite |
| Leads with | "Your biggest risk is…" | "Here's what's on the radar…" | "Today, focus on…" | "Overall, you're…" |

## Disambiguation (planner rules + `_HEALTH_INTENT_SIGNALS`, checked most-specific first)
1. **today / action** → `health_focus_today`
2. **plural concerns / issues / what's off** → `health_concerns`
3. **superlative single risk** ("biggest", "most", "worst", "what's wrong") → `biggest_health_risk`
4. **progress / status** ("how am I doing", "on track", "overall", "progress") → `overall_progress`

## Invariants (enforced by tests)
- **INV-1:** `health_concerns` returns ≥2 items when ≥2 ranked concerns exist; `biggest_health_risk` returns exactly 1.
- **INV-2:** `health_focus_today` contains an imperative action **and** time context, and is **not text-identical** to `biggest_health_risk`.
- **INV-3:** `overall_progress` is a multi-domain status summary with **no** single-risk framing.
- **INV-4 (pairwise distinctness):** against one fixture, the four answers are structurally distinct (different lead + cardinality).
- **INV-5 (Actionability):** `health_focus_today` must ALWAYS end with a concrete action completable within 24 hours, and ALWAYS contain (1) today's focus, (2) why it matters today, (3) one specific action.
  - **Valid:** "Eat 30g of protein at breakfast." · "Take a 20-minute walk after dinner." · "Protect a 10:30 PM bedtime tonight."
  - **Invalid (vague):** "Continue improving sleep." · "Work on nutrition." · "Try to stay active."

**Shared-underlying-concern edge:** when the same concern drives multiple intents, the
answers still differ **structurally** (single risk vs action-for-today vs ranked list
vs status summary). Identical presentation is a contract violation (INV-4).
