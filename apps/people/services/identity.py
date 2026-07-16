"""
Canonical identity creation & the self-anchor.

`create_person` is the one place a canonical Person is minted with correct origin
provenance and a meaningful lifecycle event. `get_self_person` / `set_self_person`
own the self-anchor (the Person that IS the user), replacing Legacy's per-module
self-binding as the platform authority.
"""

from django.db import transaction

from ..models import Person, PersonEvent, PersonOrigin
from .provenance import record_person_event

# origin → the lifecycle event that explains how this identity was born.
_ORIGIN_EVENT = {
    PersonOrigin.MANUAL: PersonEvent.Type.CREATED_MANUAL,
    PersonOrigin.CONTACT_IMPORT: PersonEvent.Type.IMPORTED_CONTACTS,
    PersonOrigin.GEDCOM: PersonEvent.Type.IMPORTED_GEDCOM,
    PersonOrigin.PROMOTION: PersonEvent.Type.PROMOTED_TO_PEOPLE,
    PersonOrigin.MENTION: PersonEvent.Type.FIRST_MENTION,
    PersonOrigin.EXTRACTION: PersonEvent.Type.FIRST_MENTION,
    PersonOrigin.API: PersonEvent.Type.CREATED_MANUAL,
}


@transaction.atomic
def create_person(user, *, origin=PersonOrigin.MANUAL, actor="system", **fields):
    """Create a canonical Person and record its birth as a lifecycle event."""
    person = Person.objects.create(user=user, origin=origin, **fields)
    event_type = _ORIGIN_EVENT.get(origin, PersonEvent.Type.CREATED_MANUAL)
    record_person_event(person, event_type, actor=actor, origin=origin)
    return person


def get_self_person(user):
    """The Person that IS the user (the self-anchor), or None."""
    return Person.objects.filter(user=user, is_self=True).first()


@transaction.atomic
def set_self_person(person):
    """Mark `person` as the user's self-anchor, ensuring at most one per user."""
    Person.objects.filter(user=person.user, is_self=True).exclude(pk=person.pk).update(
        is_self=False
    )
    if not person.is_self:
        person.is_self = True
        person.save(update_fields=["is_self", "updated_at"])
    return person
