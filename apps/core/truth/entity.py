"""
Platform capability: ENTITY COMPLETENESS.

THE LAW (permanent, business-first, implementation-independent):
    A canonical entity is complete when it can completely answer the natural business
    questions about itself from a single deterministic retrieval.

`CompleteEntity` is the CURRENT canonical IMPLEMENTATION of that law — not the law itself.
Today an entity answers its natural questions by describing itself across six dimensions
(identity / definition / status / plan / standing / performance), each carried with
freshness + confidence. The dimension set is OPEN: a domain may attach further dimensions
via `extensions` when a natural question isn't covered by the canonical six; a dimension
that proves universal is later promoted to a named field. Adding a dimension evolves THIS
implementation — it does not change the law. See docs/LAYER1_ENTITY_COMPLETENESS_CONTRACT.md.
"""
from dataclasses import dataclass, field
from typing import Any, Dict

from apps.core.truth.freshness import CURRENT
from apps.core.truth import confidence as _conf

# The current canonical dimensions (the present implementation of the law). This list can
# grow without changing the architecture — the law is about answering natural questions.
CANONICAL_DIMENSIONS = ("identity", "definition", "status", "plan", "standing", "performance")


@dataclass(frozen=True)
class CompleteEntity:
    kind: str                                   # entity type, e.g. "medication"
    identity: str                               # what it is (human name/title)
    definition: Dict[str, Any] = field(default_factory=dict)   # what specifies it
    status: str = ""                            # lifecycle state
    plan: Dict[str, Any] = field(default_factory=dict)         # what is SUPPOSED to happen
    standing: Dict[str, Any] = field(default_factory=dict)     # what's happening now vs plan
    performance: Dict[str, Any] = field(default_factory=dict)  # how it's gone over time
    # OPEN dimension set — domain-introduced dimensions not (yet) in the canonical six, so
    # new business questions can be answered without changing the architecture/law.
    extensions: Dict[str, Any] = field(default_factory=dict)
    freshness: str = CURRENT
    confidence: str = ""                        # derived from freshness (Layer 1 Law 2)

    def __post_init__(self):
        if not self.confidence:
            object.__setattr__(self, "confidence",
                               _conf.confidence_from_freshness(self.freshness))

    def to_dict(self):
        out = {
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
        if self.extensions:                     # only surface when a domain uses them
            out["extensions"] = dict(self.extensions)
        return out
