"""
Preservation-safe canonical Person merge — collapse a duplicate identity into the
survivor. THE single merge service ("how do I merge duplicate people?").

Re-points every Core-owned relation (membership, recognition phrases, photos,
events, source links, identity truths) from loser to winner, then runs registered
feature merge-participants (Relationships / Legacy re-point their own relations
without Core importing them), records a MERGE_COMPLETED lifecycle event, and
SOFT-DELETES the loser (reversible, preservation-safe — never a hard delete).

Conservative by contract: callers must only merge identities that are
deterministically the same human. Uncertain matches are routed to review, never
auto-merged (see reconciliation.py).
"""

from django.db import transaction

from ..models import (
    Person, PersonEvent, PersonMembership, PersonPhoto, PersonSourceLink,
    RecognitionPhrase,
)
from . import hooks, phrases
from .provenance import record_person_event


@transaction.atomic
def merge_persons(user, loser, winner, *, actor="user"):
    """Merge `loser` into `winner` (both this user's canonical people). Returns
    the winner. Raises ValueError on a nonsensical merge."""
    if loser.pk == winner.pk:
        raise ValueError("Cannot merge a person into themselves.")
    if loser.user_id != user.id or winner.user_id != user.id:
        raise ValueError("Both people must belong to this user.")

    # 1. Membership — grant follows the survivor; never lose membership.
    loser_membership = PersonMembership.objects.filter(person=loser).first()
    if loser_membership:
        if PersonMembership.objects.filter(person=winner).exists():
            loser_membership.delete()          # winner already a member
        else:
            loser_membership.person = winner    # move the grant + its provenance
            loser_membership.save(update_fields=["person"])

    # 2. Recognition phrases — re-point, dropping duplicates by (person, normalized).
    for rp in RecognitionPhrase.objects.filter(person=loser):
        if RecognitionPhrase.objects.filter(person=winner, normalized=rp.normalized).exists():
            rp.delete()
        else:
            rp.person = winner
            rp.save(update_fields=["person"])

    # 3. Photos — move; keep a single primary.
    winner_has_primary = PersonPhoto.objects.filter(person=winner, is_primary=True).exists()
    for photo in PersonPhoto.objects.filter(person=loser):
        photo.person = winner
        if winner_has_primary and photo.is_primary:
            photo.is_primary = False
        photo.save(update_fields=["person", "is_primary"])

    # 4. Lifecycle events — preserve the loser's history on the survivor.
    PersonEvent.objects.filter(person=loser).update(person=winner)

    # 5. Source links (migration bridges) — re-point; (domain, pk) is globally unique.
    PersonSourceLink.objects.filter(person=loser).update(person=winner)

    # 6. Identity truths — fill survivor blanks; deceased/self are OR-merged.
    fields = []
    for f in ("first_name", "last_name", "email", "phone", "notes"):
        if not getattr(winner, f) and getattr(loser, f):
            setattr(winner, f, getattr(loser, f))
            fields.append(f)
    if loser.is_deceased and not winner.is_deceased:
        winner.is_deceased = True
        fields.append("is_deceased")
    if loser.is_self and not winner.is_self:
        winner.is_self = True
        fields.append("is_self")
    if fields:
        winner.save(update_fields=list(set(fields)) + ["updated_at"])

    # 7. Keep the duplicate's name resolvable on the survivor (searchability), unless
    #    it already resolves. The merge is an explicit user action → durable is allowed.
    if loser.display_name and loser.display_name.lower() != winner.display_name.lower():
        phrases.confirm_learned_phrase(
            winner, loser.display_name, learned_from=f"merge:{loser.pk}", actor=actor
        )

    # 8. Feature modules re-point their own relations (edges, memories, mentions).
    hooks.run_merge_participants(user, loser, winner)

    # 9. Provenance + preservation-safe removal of the duplicate.
    record_person_event(
        winner, PersonEvent.Type.MERGE_COMPLETED, actor=actor,
        merged_from=loser.pk, merged_from_name=loser.display_name,
    )
    loser.soft_delete()
    return winner
