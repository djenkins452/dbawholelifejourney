# Retrieval Platform Adoption — Rollout Matrix (FINAL)

**Date:** 2026-07-23 · **Status:** ✅ **RETRIEVAL PLATFORM CERTIFIED — ADOPTION COMPLETE**
**Gate:** the certified metadata contract + tests (`apps/core/truth/tests/test_retrieval_authority_contract.py`)

> Adoption = **consume the existing platform**. No new architecture, no new authorities. Every served value declares `authority` + `semantics`. Keyed surfaces expose `authority_declarations()` + `served_keys()` and register in `_ADOPTED_SURFACES`; dynamic-key surfaces stamp at their fact factory; composed-envelope surfaces declare at the envelope root.

## Final rollout matrix

```
Surface → Authority Contract → Semantics → Projection Verified → Certified
```

| Surface | Shape | Adoption pattern | Classification | Certified |
|---|---|---|---|---|
| `get_foundational_health_facts` | keyed (~130) | per-key registry + stamp | projections (+2 declared missing_projection) | ✅ mechanical |
| `get_foundational_execution_facts` | keyed (9) | per-key registry + stamp | projections | ✅ mechanical |
| `personal_truth` / `get_user_truth` | dynamic-key | `_fact()` factory stamp | projection | ✅ |
| `get_domain_state` | composed | envelope-root | projection (SAE store) | ✅ |
| `decision_authority.current_action` | composed | envelope-root | **canonical_authority** | ✅ |
| `execution_state` (`execution_facts`) | composed | envelope-root | **canonical_authority** | ✅ |
| `standing_context` | composed | envelope-root (ready + pending) | projection of `cos_context` | ✅ |
| Executive briefing (`truth/briefing`) | composed | envelope-root | projection of DomainTruth | ✅ |
| Page summaries (15 providers) | keyed | generic choke-point stamp | projection | ✅ |

**Canonical retrieval tools** (`get_history`, `get_entity`, `get_analysis`) are the **authorities every projection above delegates to** — provenance-native (source / freshness / confidence in the truth envelope). They are the destinations of adoption, not adopters.

## Certification result
- **Zero anonymous served values** across every adopted surface.
- **Zero shadow authorities.** The ratchet holds **2 declared `missing_projection`s** — `weight_30_day_change`, `sleep_trend` — a *disclosed* gap, not a defect of adoption: `get_history` exposes series average/total but not a change/trend scalar, so the canonical projection is genuinely absent. Closing them is a future `get_history` enhancement (teach it to own change/trend), tracked by the ratchet.
- **Permanent gates:** `AdoptedSurfacesContractTests` (keyed, iterates the registry) + `ComposedSurfaceContractTests` (composed, asserts envelope-root declaration). A new retrieval surface certifies by adopting the **one platform convention** — `authority_declarations()` / `served_keys()` / `stamp()` (keyed) or an envelope-root stamp (composed) — no alternate mechanism.

## Platform standard (permanent convention)
Every future retrieval surface adopts the same pattern:
- **keyed:** `authority_declarations()` + `served_keys()`, stamp each served fact, register in `_ADOPTED_SURFACES`.
- **composed:** stamp `authority` + `semantics` at the envelope root.
- **canonical tool:** it IS the authority — carry provenance natively; others delegate to it.

**The Retrieval Platform is now permanent certified infrastructure. Future work consumes it; it is not modified without runtime evidence of a platform defect.**
