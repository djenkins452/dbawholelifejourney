"""
Platform capability: ENTITY COMPLETENESS CONTRACT.

A canonical entity COMPLETELY describes itself. Layer 1 exposes complete business objects;
higher layers retrieve one object and never assemble fragmented truth from many calls.

`CompleteEntity`'s fields ARE the contract's business dimensions, so the contract is
visible in the type — you cannot return a half-described entity without leaving a
dimension empty. Every canonical domain returns entities in THIS shape (Medication is the
reference implementation). See docs/LAYER1_ENTITY_COMPLETENESS_CONTRACT.md.
"""
from dataclasses import dataclass, field
from typing import Any, Dict

from apps.core.truth.freshness import CURRENT
from apps.core.truth import confidence as _conf


@dataclass(frozen=True)
class CompleteEntity:
    kind: str                                   # entity type, e.g. "medication"
    identity: str                               # what it is (human name/title)
    definition: Dict[str, Any] = field(default_factory=dict)   # what specifies it
    status: str = ""                            # lifecycle state
    plan: Dict[str, Any] = field(default_factory=dict)         # what is SUPPOSED to happen
    standing: Dict[str, Any] = field(default_factory=dict)     # what's happening now vs plan
    performance: Dict[str, Any] = field(default_factory=dict)  # how it's gone over time
    freshness: str = CURRENT
    confidence: str = ""                        # derived from freshness (Layer 1 Law 2)

    def __post_init__(self):
        if not self.confidence:
            object.__setattr__(self, "confidence",
                               _conf.confidence_from_freshness(self.freshness))

    def to_dict(self):
        return {
            "kind": self.kind,
            "identity": self.identity,
            "definition": dict(self.definition),
            "status": self.status,
            "plan": dict(self.plan),
            "standing": dict(self.standing),
            "performance": dict(self.performance),
            "freshness": self.freshness,
            "confidence": self.confidence,
        }
