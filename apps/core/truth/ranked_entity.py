"""
Platform capability: RANKED ENTITY RETRIEVAL (order canonical entities by a deterministic
measure).

The retrieval shape for "which X had the most/least Y" — "which meals contributed the most
carbs", "which workouts burned the most calories", "which expenses were largest". It does
NOT compute Y: the measure is an ALREADY-AUTHORITATIVE value the owning domain produced on
each entity. This capability only ORDERS the canonical entities by that value and returns
the top-N with their canonical references, so follow-ups ("tell me about the top one") flow
straight back into the existing entity-retrieval path.

REGISTRY-CONTROLLED, NOT a query engine. The model may only pick a REGISTERED ranking
subject (domain + entity_type + measure + canonical producer, declared in
`apps.ai.cos_services.domain_ranked_entity`). It can never send an arbitrary
model/table/field/order-by — there is no shadow database surface.

FACTS, NOT A VERDICT: WLJ returns the ranked values (and each entity's share of the total);
it never labels a meal "worst"/"unhealthy" or a workout "best". OpenAI judges.

MISSING ≠ ZERO: an entity with no measure value is EXCLUDED from the ranking (and counted),
never coerced to 0. A real 0 is a legitimate value and ranks normally. Ties break
deterministically on the canonical reference, never on database row order. The result is
bounded (a default and a hard maximum) so a large population never floods model context.
Pure: same items → same ranking.
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional

DEFAULT_LIMIT = 10
MAX_LIMIT = 50


@dataclass(frozen=True)
class RankItem:
    ref: str                     # canonical entity reference (stable identity)
    name: str                    # display name/title
    value: Optional[float]       # the deterministic measure (None = missing, excluded)
    occurred_on: Optional[str] = None    # ISO date/occurrence where relevant
    meta: dict = field(default_factory=dict)   # domain-owned extras (already authoritative)


def build_ranking(items: List[RankItem], *, measure: str, unit: Optional[str],
                  domain: str = "", entity_type: str = "", subject: str = "",
                  order: str = "desc", limit: int = DEFAULT_LIMIT) -> dict:
    """Rank `items` by their `value` and return the bounded top-N + population totals.

    - order: "desc" (most first, default) or "asc" (least first).
    - limit: clamped to [1, MAX_LIMIT]; DEFAULT_LIMIT when not given.
    - missing value (None) → EXCLUDED and counted (never zero-filled); real 0 kept.
    - ties break on the canonical `ref` (ascending) — deterministic, never row order.
    """
    order = "asc" if str(order).lower() == "asc" else "desc"
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))

    present = [it for it in items if it.value is not None]
    missing_excluded = len(items) - len(present)

    if order == "desc":
        present.sort(key=lambda it: (-float(it.value), str(it.ref)))
    else:
        present.sort(key=lambda it: (float(it.value), str(it.ref)))

    total = round(sum(float(it.value) for it in present), 2) if present else 0.0
    ranked = present[:limit]
    results = []
    for i, it in enumerate(ranked, start=1):
        v = round(float(it.value), 2)
        results.append({
            "rank": i,
            "ref": it.ref,
            "name": it.name,
            "value": v,
            "unit": unit,
            "contribution_pct": (round(v / total * 100, 1)
                                 if total not in (0, 0.0) else None),
            "occurred_on": it.occurred_on,
            **({"meta": it.meta} if it.meta else {}),
        })
    return {
        "domain": domain,
        "entity_type": entity_type,
        "subject": subject,
        "measure": measure,
        "unit": unit,
        "order": order,
        "limit": limit,
        "entities_ranked": len(present),
        "entities_returned": len(results),
        "missing_excluded": missing_excluded,      # measure absent — NOT counted as 0
        "total": total,                            # sum of the measure across ALL present
        "present": bool(results),
        "results": results,
    }
