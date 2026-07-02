"""
Legacy Domain Truth — the single canonical interface to Legacy's truth.

Conforms to the Layer-1 contract (apps/core/truth/domain.py): every consumer —
dashboards, reports, exports, and (eventually) the assistant — asks this one
object the same way. "Expose, don't rebuild."

Phase 1 exposes:
  * describe("memory" | "person" | "place") → list[CompleteEntity]
  * current("total_memories" | "total_people" | "total_places" | "total_media")
History is not yet meaningful for a preservation domain and is left unimplemented.
"""

from typing import List

from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.entity import CompleteEntity


@register_domain_truth
class LegacyDomainTruth(DomainTruth):
    domain = "legacy"
    current_metrics = ("total_memories", "total_people", "total_places", "total_media")
    history_metrics = ()
    entity_types = ("memory", "person", "place")

    # ── Current Truth ──────────────────────────────────────────────────
    def current(self, metric: str) -> CurrentTruth:
        from apps.legacy.models import Media, Memory, Person, Place

        counters = {
            "total_memories": lambda: Memory.objects.filter(user=self.user).count(),
            "total_people": lambda: Person.objects.filter(user=self.user).count(),
            "total_places": lambda: Place.objects.filter(user=self.user).count(),
            "total_media": lambda: Media.objects.filter(user=self.user).count(),
        }
        if metric not in counters:
            raise KeyError(f"legacy domain truth has no metric {metric!r}")
        return CurrentTruth.found(
            domain=self.domain,
            metric=metric,
            value=counters[metric](),
            freshness="current",
            source="legacy",
        )

    # ── Canonical entities (the Entity Completeness contract) ──────────
    def describe(self, entity_type: str = None) -> List[CompleteEntity]:
        et = entity_type or "memory"
        if et == "memory":
            return self._describe_memories()
        if et == "person":
            return self._describe_people()
        if et == "place":
            return self._describe_places()
        raise NotImplementedError(f"legacy domain truth cannot describe {entity_type!r}")

    def _describe_memories(self) -> List[CompleteEntity]:
        from apps.legacy.models import Memory

        out = []
        qs = (
            Memory.objects.filter(user=self.user)
            .prefetch_related("people", "places", "media")
            .order_by("-created_at")
        )
        for m in qs:
            out.append(CompleteEntity(
                kind="memory",
                identity=m.title or "(untitled memory)",
                definition={
                    "entry_type": m.entry_type,
                    "occurred_on": m.occurred_on.isoformat() if m.occurred_on else None,
                    "occurred_precision": m.occurred_precision,
                },
                status=m.entry_state,
                standing={
                    "people": [p.display_name for p in m.people.all()],
                    "places": [p.name for p in m.places.all()],
                    "media_count": m.media.count(),
                    "has_audio": m.has_audio,
                },
                extensions={
                    # Preservation-shaped dimensions (architecture §13.3).
                    "provenance": {
                        "source_kind": m.source_kind,
                        "attributed_to": m.attributed_to.display_name if m.attributed_to else None,
                        "contributor": m.contributor.name if m.contributor else None,
                        "created_via": m.created_via,
                        "note": m.provenance_note,
                    },
                    "significance": m.significance,
                },
            ))
        return out

    def _describe_people(self) -> List[CompleteEntity]:
        from apps.legacy.models import Person

        out = []
        for p in Person.objects.filter(user=self.user):
            out.append(CompleteEntity(
                kind="person",
                identity=p.display_name,
                definition={
                    "also_known_as": p.also_known_as,
                    "relationship": p.relationship_label,
                    "birth_year": p.birth_year,
                    "death_year": p.death_year,
                },
                standing={"memory_count": p.memories.count()},
                extensions={"significance": p.significance},
            ))
        return out

    def _describe_places(self) -> List[CompleteEntity]:
        from apps.legacy.models import Place

        out = []
        for pl in Place.objects.filter(user=self.user):
            out.append(CompleteEntity(
                kind="place",
                identity=pl.name,
                definition={"location": pl.location_text},
                standing={"memory_count": pl.memories.count()},
                extensions={"significance": pl.significance},
            ))
        return out
