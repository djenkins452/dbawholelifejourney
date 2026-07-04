"""
Who is the current user? — the permanent binding between an authenticated WLJ
user and the canonical Person that IS them (the Family View's focal point).

Resolution order, each step self-healing (it persists the binding once found so it
never has to be searched for again):
  1. LegacyProfile.self_person — the explicit, permanent binding.
  2. Person.is_self — the older flag (kept in sync).
  3. A name match to the user's WLJ name — exact, or first + last name both present
     as words in the Person's name (so "Danny Jenkins" binds "Danny Ray Jenkins").

Local and deterministic — no Discovery, no CoS.
"""


def _user_names(user):
    getter = getattr(user, "get_full_name", None)
    full = (getter() or "").strip().lower() if callable(getter) else ""
    first = (getattr(user, "first_name", "") or "").strip().lower()
    last = (getattr(user, "last_name", "") or "").strip().lower()
    return full, first, last


def _name_match(user, people):
    full, first, last = _user_names(user)
    if full:
        for p in people:
            if p.display_name.strip().lower() == full:
                return p
    if first and last:
        for p in people:
            toks = p.display_name.lower().split()
            if first in toks and last in toks:
                return p
    return None


def bind_self(user, person):
    """Permanently bind `person` as the keeper. Keeps Person.is_self in sync."""
    from apps.legacy.models import LegacyProfile, Person
    LegacyProfile.objects.update_or_create(user=user, defaults={"self_person": person})
    Person.objects.filter(user=user, is_self=True).exclude(pk=person.pk).update(is_self=False)
    Person.objects.filter(pk=person.pk).update(is_self=True)
    return person


def get_self_person(user):
    """The Person that IS this user (or None). Binds it the first time it's found."""
    from apps.legacy.models import LegacyProfile, Person
    prof = LegacyProfile.objects.filter(user=user).select_related("self_person").first()
    if prof and prof.self_person_id:
        return prof.self_person

    people = list(Person.objects.filter(user=user).only("pk", "display_name", "is_self"))
    if not people:
        return None
    p = next((x for x in people if x.is_self), None) or _name_match(user, people)
    if p is not None:
        bind_self(user, p)
    return p
