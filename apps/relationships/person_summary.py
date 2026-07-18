"""Relationships' contribution to the shared canonical-Person hover card.

Registered as a people `person_summary` provider (see AppConfig.ready). Given a canonical
``people.Person``, it returns lightweight, display-only facts the People domain can't know
on its own: the relationship label ("Spouse") and the rich Relationships person-page URL.

Core never imports this — the dependency flows Relationships → People (core) via the hook
seam. Cheap by contract: two indexed lookups, no analytics.
"""
from django.urls import reverse


def relationship_person_summary(user, person):
    """`{"relationship": "Spouse", "url": "/relationships/5/"}` for a canonical Person that
    maps to a relationships contact; `{}` otherwise."""
    from apps.people.models import PersonSourceLink
    from .models import Person as RelationshipsPerson

    link = (PersonSourceLink.objects
            .filter(person=person, source_domain=PersonSourceLink.Source.RELATIONSHIPS)
            .first())
    if link is None:
        return {}
    rel = RelationshipsPerson.objects.filter(pk=link.source_pk, owner=user).first()
    if rel is None:
        return {}

    data = {"url": reverse("relationships:person_detail", args=[rel.pk])}
    rtype = (rel.relationship_type or "").strip()
    if rtype and rtype.lower() != "other":
        data["relationship"] = rel.get_relationship_type_display()
    return data
