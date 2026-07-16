"""
Meaningful Person lifecycle provenance — NOT a generic CRUD audit log.

Record ONLY events that explain how the canonical Person and its identity truth
evolved (created, imported, promoted, first mention, phrase confirmed/removed,
duplicate detected, merge completed, relationship added/removed, archived,
restored, source added). This history exists for debugging, explainability, merge
confidence, preservation, and user trust — and is deliberately bounded. Do not
call this for every field edit.
"""

from ..models import PersonEvent


def record_person_event(person, event_type, *, actor="system", **detail):
    """Append one meaningful lifecycle event. `detail` holds small deterministic
    facts only (ids, labels, counts) — never large blobs or full record copies."""
    return PersonEvent.objects.create(
        person=person,
        event_type=event_type,
        actor=actor,
        detail=detail or {},
    )
