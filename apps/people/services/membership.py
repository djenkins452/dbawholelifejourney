"""
People Membership — the deterministic People-vs-Legacy boundary.

A Person becomes a member of the everyday People experience when they become part
of the user's life. Membership is GRANTED (idempotently), never auto-revoked. A
person with no membership row (e.g. a GEDCOM-only ancestor never referenced) stays
in Legacy without cluttering People.
"""

from ..models import Person, PersonMembership
from .provenance import record_person_event


def grant_membership(person, via, *, note="", actor="system"):
    """Ensure `person` is a People member. Idempotent: returns the existing
    membership if present (never revokes, never downgrades the original grant)."""
    membership, created = PersonMembership.objects.get_or_create(
        person=person, defaults={"granted_via": via, "note": note}
    )
    if created and via == PersonMembership.Grant.PROMOTION:
        record_person_event(person, "promoted_to_people", actor=actor, via=via)
    return membership


def is_member(person) -> bool:
    return PersonMembership.objects.filter(person=person).exists()


def members(user):
    """The everyday People list: canonical people who became part of the user's
    life. Deceased members are included; genealogy-only people are not."""
    return Person.objects.filter(user=user, membership__isnull=False)
