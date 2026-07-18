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
    def describe(self, entity_type: str = None, filters=None) -> List[CompleteEntity]:
        et = entity_type or "memory"
        if et == "memory":
            return self._describe_memories(filters or {})
        if et == "person":
            return self._describe_people()
        if et == "place":
            return self._describe_places()
        raise NotImplementedError(f"legacy domain truth cannot describe {entity_type!r}")

    # ── Name lookup (answers "tell me about Harold Keck / my grandfather") ──────
    def describe_one(self, name):
        """Best match by name → a person CompleteEntity (falls back to place, then
        memory title). None when nothing matches — never guesses."""
        from django.db.models import Q
        from apps.legacy.models import Memory, Person, Place

        q = (name or "").strip()
        if not q:
            return None
        p = (Person.objects.filter(user=self.user)
             .filter(Q(display_name__icontains=q) | Q(also_known_as__icontains=q)
                     | Q(relationship_label__icontains=q))
             .order_by("-significance", "display_name").first())
        if p:
            return self._person_entity(p)
        pl = (Place.objects.filter(user=self.user)
              .filter(Q(name__icontains=q) | Q(location_text__icontains=q))
              .order_by("-significance", "name").first())
        if pl:
            return self._place_entity(pl)
        m = (Memory.objects.filter(user=self.user)
             .filter(Q(title__icontains=q) | Q(body__icontains=q))
             .order_by("-created_at").first())
        return self._memory_entity(m) if m else None

    def _describe_memories(self, filters=None) -> List[CompleteEntity]:
        from apps.legacy.models import Memory
        filters = filters or {}
        qs = (Memory.objects.filter(user=self.user)
              .prefetch_related("people", "places", "media").order_by("-created_at"))
        # Deterministic scoping (truth, not model inference):
        #   involves — person name → memories that person appears in ("memories with X")
        #   occurred_from / occurred_to — year bounds ("childhood memories")
        if filters.get("involves"):
            qs = qs.filter(people__display_name__icontains=filters["involves"])
        if filters.get("occurred_from"):
            qs = qs.filter(occurred_on__year__gte=int(filters["occurred_from"]))
        if filters.get("occurred_to"):
            qs = qs.filter(occurred_on__year__lte=int(filters["occurred_to"]))
        return [self._memory_entity(m) for m in qs.distinct()]

    def _describe_people(self) -> List[CompleteEntity]:
        from apps.legacy.models import Person
        return [self._person_entity(p) for p in Person.objects.filter(user=self.user)]

    def _describe_places(self) -> List[CompleteEntity]:
        from apps.legacy.models import Place
        return [self._place_entity(pl) for pl in Place.objects.filter(user=self.user)]

    # ── per-record mappers (shared by describe + describe_one) ──────────
    def _memory_entity(self, m) -> CompleteEntity:
        return CompleteEntity(
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
                "provenance": {
                    "source_kind": m.source_kind,
                    "attributed_to": m.attributed_to.display_name if m.attributed_to else None,
                    "contributor": m.contributor.name if m.contributor else None,
                    "created_via": m.created_via,
                    "note": m.provenance_note,
                },
                "significance": m.significance,
            },
        )

    def _person_entity(self, p) -> CompleteEntity:
        mems = list(p.memories.all()[:25])
        return CompleteEntity(
            kind="person",
            identity=p.display_name,
            definition={
                "also_known_as": p.also_known_as,
                "relationship": p.relationship_label,
                "birth_year": p.birth_year,
                "death_year": p.death_year,
            },
            standing={"memory_count": p.memories.count(),
                      "memories": [m.title or "(untitled)" for m in mems]},
            extensions={"significance": p.significance},
        )

    def _place_entity(self, pl) -> CompleteEntity:
        return CompleteEntity(
            kind="place",
            identity=pl.name,
            definition={"location": pl.location_text},
            standing={"memory_count": pl.memories.count()},
            extensions={"significance": pl.significance},
        )
