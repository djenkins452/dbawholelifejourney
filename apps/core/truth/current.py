"""
Platform capability: CURRENT TRUTH OBJECTS.

The single authoritative value object for "what is the user's current X". A
`CurrentTruth` composes the two lower platform capabilities — a value (from a
domain's deterministic contract / Per-Day Truth) and a `freshness` verdict (from
apps.core.truth.freshness) — into one object Beth retrieves. History is separate:
Current Truth answers "what is it now", History answers "what was it on <date>".

Every domain exposes Current Truth via a small provider that returns these objects
(CurrentHealth, CurrentFinance, …). Implement the object once here; each domain is a
consumer, not a re-implementer. Engines and Beth both read the same object.

`to_fact_dict()` serializes to the flat dict the foundational-fact phrasing layer
already consumes, so Current Truth slots under the existing narration without churn.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from apps.core.truth.freshness import MISSING


@dataclass(frozen=True)
class CurrentTruth:
    domain: str
    metric: str
    present: bool
    value: Any = None
    unit: Optional[str] = None
    as_of: Optional[str] = None          # ISO date/datetime the value belongs to
    freshness: str = MISSING
    source: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    # -- constructors ---------------------------------------------------------
    @classmethod
    def found(cls, domain, metric, value, freshness, *, unit=None, as_of=None,
              source="", detail=None):
        return cls(domain=domain, metric=metric, present=True, value=value,
                   unit=unit, as_of=as_of, freshness=freshness, source=source,
                   detail=dict(detail or {}))

    @classmethod
    def absent(cls, domain, metric, freshness=MISSING, *, source="", reason=""):
        return cls(domain=domain, metric=metric, present=False, freshness=freshness,
                   source=source, reason=reason)

    # -- serialization --------------------------------------------------------
    def to_fact_dict(self):
        """Flat dict for the foundational-fact phrasing layer. Mirrors the existing
        fact shape: present → {value, source, freshness, **detail}; absent →
        {status: unknown, freshness, reason}."""
        if not self.present:
            out = {"status": "unknown", "freshness": self.freshness}
            if self.reason:                 # observability only; omit when empty
                out["reason"] = self.reason
            return out
        out = {"value": self.value, "source": self.source,
               "freshness": self.freshness}
        if self.unit:
            out["unit"] = self.unit
        out.update(self.detail)
        return out
