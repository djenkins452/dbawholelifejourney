"""
Canonical Person merge — collapse a duplicate into the surviving person.

"Marvin Jenkins" and "Marvin Lynn Jenkins" are the same individual. Merging moves
EVERYTHING off the duplicate onto the survivor — stories, photos, media, places
and milestones (which travel with the stories), relationships, aliases,
relationship aliases, discovery links, contributor links, outputs — then deletes
the obsolete record so no duplicate and no broken reference remains. The
duplicate's name is kept as an alias on the survivor so it stays searchable.

All in one transaction. Local and deterministic — no Discovery, no CoS.
"""

from django.db import transaction
from django.db.models import Q


@transaction.atomic
def merge_people(user, loser, winner):
    """Merge `loser` into `winner` (both this user's People). Returns the winner.
    Raises ValueError on a nonsensical merge."""
    from apps.legacy.models import (
        Contributor, Memory, MemoryDiscovery, MemoryPerson, Output,
        Relationship, RelationshipAlias,
    )
    if loser.pk == winner.pk:
        raise ValueError("Cannot merge a person into themselves.")
    if loser.user_id != user.id or winner.user_id != user.id:
        raise ValueError("Both people must belong to this user.")

    # 1. Stories (Memory.people via MemoryPerson) — re-point, dedupe per memory.
    for mp in MemoryPerson.objects.filter(person=loser):
        if MemoryPerson.objects.filter(memory_id=mp.memory_id, person=winner).exists():
            mp.delete()
        else:
            mp.person = winner
            mp.save(update_fields=["person"])

    # 2. Attribution ("whose memory this is") — covers archived/deleted too.
    Memory.all_objects.filter(attributed_to=loser).update(attributed_to=winner)

    # 3. Discovery graph links.
    MemoryDiscovery.objects.filter(linked_person=loser).update(linked_person=winner)

    # 4. Relationships — re-point both ends, then drop self-loops and duplicates.
    Relationship.objects.filter(from_person=loser).update(from_person=winner)
    Relationship.objects.filter(to_person=loser).update(to_person=winner)
    seen = set()
    for r in (Relationship.objects.filter(Q(from_person=winner) | Q(to_person=winner))
              .order_by("pk")):
        if r.from_person_id == r.to_person_id:
            r.delete()
            continue
        key = (r.from_person_id, r.to_person_id, (r.relationship_type or "").lower())
        if key in seen:
            r.delete()
        else:
            seen.add(key)

    # 5. Outputs scoped to the person.
    Output.objects.filter(scope_person=loser).update(scope_person=winner)

    # 6. Contributor ↔ Person link.
    Contributor.objects.filter(person=loser).update(person=winner)

    # 7. Relationship aliases ("Dad" → …). Alias is unique per (user, alias), so
    #    the loser and winner can never share one — re-pointing never conflicts.
    RelationshipAlias.objects.filter(person=loser).update(person=winner)

    # 8. Fill the survivor's blank facts from the duplicate (never overwrite).
    fields = []
    for f in ("birth_year", "death_year", "relationship_label", "bio"):
        if not getattr(winner, f) and getattr(loser, f):
            setattr(winner, f, getattr(loser, f))
            fields.append(f)
    if not winner.primary_photo_id and loser.primary_photo_id:
        winner.primary_photo_id = loser.primary_photo_id
        fields.append("primary_photo")

    # 9. Keep the duplicate's name searchable as an alias on the survivor.
    akas, seen_aka, merged = [], set(), []
    for x in (winner.also_known_as, loser.display_name, loser.also_known_as):
        for part in (x or "").split(","):
            part = part.strip()
            if part:
                akas.append(part)
    for x in akas:
        low = x.lower()
        if low == winner.display_name.lower() or low in seen_aka:
            continue
        seen_aka.add(low)
        merged.append(x)
    new_aka = ", ".join(merged)[:200]
    if new_aka != (winner.also_known_as or ""):
        winner.also_known_as = new_aka
        fields.append("also_known_as")

    if fields:
        winner.save(update_fields=list(set(fields)) + ["updated_at"])

    # 10. The obsolete record disappears (hard delete — everything already moved).
    loser.delete()
    return winner
