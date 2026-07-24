# Retrieval Platform Adoption — Rollout Matrix

**Date:** 2026-07-23 · **Initiative:** Platform Adoption (implementation, not architecture)
**Gate:** the certified metadata contract + generic multi-surface test (`apps/core/truth/tests/test_retrieval_authority_contract.py :: AdoptedSurfacesContractTests`)

> Adoption = **consume the existing platform**. No new architecture, no new authorities. A surface adopts by declaring `authority` + `semantics` on every served value; keyed surfaces expose `authority_declarations()` + `served_keys()` and register in `_ADOPTED_SURFACES`; composed-envelope surfaces declare at the envelope root.

## Rollout matrix

```
Surface → Authority Contract → Semantics → Projection Verified → Certified
```

| Surface | Shape | Authority | Semantics | Projection verified | Certified |
|---|---|---|---|---|---|
| `get_foundational_health_facts` | keyed (127) | ✅ per-key | ✅ | ✅ 102 derived delegate; residuals pinned | ✅ **(mechanical)** |
| `get_foundational_execution_facts` | keyed (9) | ✅ per-key | ✅ `current`/`latest_observation` | ✅ all delegate (Journal/Workout/Medicine/Nutrition/calendar) | ✅ **(mechanical, this session)** |
| `personal_truth` / `get_user_truth` | dynamic-key | ✅ per-fact (`_fact` factory) | ✅ `current` | ✅ projection of module facts; already provenance-bearing | ✅ **(this session)** |
| `get_domain_state` | composed envelope | ✅ envelope root (`SAE.<domain>`) | ✅ `projection` | ✅ SAE store, not an authority; freshness disclosed (`49d9e0d1`) | ✅ **(this session)** |
| `standing_context` | composed | projects `cos_context`/`executive`; carries status | ⬜ semantics not yet declared | — | ◐ **pending (envelope-root touch)** |
| Page summaries (15 providers) | keyed `summary:<key>` | one shared builder per page (CC contract) | ⬜ | — | ◐ **pending** |
| Executive briefings | composed | carries source/freshness | ⬜ | — | ◐ **pending** |
| Decision authority (`current_action`) | composed | ✅ `source_type` | ⬜ semantics not declared | — | ◐ **pending (multi return point)** |
| Execution truth (`execution_state`) | composed | built from `execution_facts` (adopted) + `decision_authority` | inherits | — | ◐ **pending (verify)** |

**Certified this session: 3 surfaces adopted** (execution_facts, personal_truth, domain_state) on top of health_facts, plus the **generic multi-surface gate** so future surfaces certify by adding one registry line — no per-surface test authoring.

## What remains (bounded implementation, no architecture)

**Phase 1 tail — 4 composed surfaces:** declare `semantics` at the envelope root for `standing_context`, `decision_authority` (stamp each of its ~4 return points), executive briefings, and verify `execution_state` inherits. Page summaries: declare per provider. All are the same envelope-root touch already proven on `get_domain_state`.

**Phase 2 — Health cleanup (measured blast radius, cross-runtime):**
- `average_glucose_yesterday` → `average_glucose_7d`, `steps_recent` → `steps_avg_7d`. These keys live in BOTH runtimes — health_facts *and* the legacy `chatgpt_cos` (`foundational_facts.py` classifier + `_UNKNOWN_SENTENCE` + 2 `format_fact_sentence` branches, `conversation_memory._AVERAGE_FACT_KEYS`, `conversation_object` supporting tuples). A rename is 5 files across 2 runtimes; to become **compliant** (not just honestly-named) they must also delegate to `get_history(..., last_7_days).average` instead of reading SAE.
- F5 aggregates (`average_sleep_7d`, `sleep_trend`, `weight_30_day_change`): delegate to `get_history` windows; remove pins on runtime verification.

## Verdict
**Platform Adoption is NOT complete** — 4 of ~9 surfaces certified. The **framework and the mechanical gate are proven across multiple surfaces**; the remaining work is uniform envelope-root declarations (Phase 1 tail) plus the cross-runtime Health renames (Phase 2). None requires architecture. **The Retrieval Platform initiative stays OPEN until the tail lands.**
