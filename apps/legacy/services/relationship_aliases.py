"""
Relationship aliases — how Legacy gets smarter over time.

Words like "Dad", "Mom", "Coach", "Pastor", "Grandma" are NOT people; they are
ALIASES that stand in for a specific person. The first time Legacy meets one it
asks "Who is 'Dad' in this document?"; once the keeper answers, the mapping is
stored and every FUTURE import resolves the alias automatically — never asking
twice. This module is the persistent store + resolver behind that behaviour.

Local and deterministic — no OpenAI, no CoS.
"""

# Common relational terms that are aliases for a person rather than names.
COMMON_ALIASES = frozenset({
    "dad", "daddy", "father", "pa", "pop", "pops",
    "mom", "mommy", "mother", "ma", "mama",
    "grandma", "grandmother", "granny", "nana", "gran",
    "grandpa", "grandfather", "papa", "gramps", "pawpaw", "papaw",
    "sister", "sis", "brother", "bro",
    "aunt", "auntie", "uncle", "cousin",
    "husband", "wife", "son", "daughter",
    "coach", "pastor", "boss", "teacher", "professor", "doctor",
    "grandson", "granddaughter", "nephew", "niece", "godfather", "godmother",
})


def normalize(text):
    """Canonical key for an alias — lowercased, trimmed, possessive stripped."""
    t = (text or "").strip().lower()
    if t.endswith("'s") or t.endswith("’s"):
        t = t[:-2]
    return t.strip()


def is_alias_term(text):
    """True when a term is a relational alias (a stand-in for a person)."""
    return normalize(text) in COMMON_ALIASES


def resolve(user, text):
    """Return the Person this alias maps to for `user`, or None if unmapped."""
    from apps.legacy.models import RelationshipAlias
    key = normalize(text)
    if not key:
        return None
    row = (RelationshipAlias.objects.filter(user=user, alias=key)
           .exclude(person__isnull=True).select_related("person").first())
    return row.person if row else None


def record(user, label, person):
    """Persist (or update) the mapping alias(label) → person. Returns the row.
    Idempotent — teaching the same alias again just confirms it."""
    from apps.legacy.models import RelationshipAlias
    key = normalize(label)
    if not key:
        return None
    row, _created = RelationshipAlias.objects.get_or_create(
        user=user, alias=key, defaults={"label": (label or key)[:80], "person": person})
    if row.person_id != getattr(person, "pk", None) and person is not None:
        row.person = person
        row.label = (label or key)[:80]
        row.save(update_fields=["person", "label", "updated_at"])
    return row
