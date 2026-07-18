"""Relationship-derived recognition — first-person role phrases as deterministic
projections of the relationship graph.

"my wife", "my daughter", "my father" are NOT stored RecognitionPhrases — they are
computed from ``relationships.Person.relationship_type`` and resolve to the canonical
Person. Read-only, never edited, never duplicated. Registered as people hooks
(``resolve_role`` / ``person_roles`` / ``all_role_phrases``) so Core never imports this
feature app; every consumer (Journal passive recognition, the resolver, the lookup,
the hover card) benefits automatically.

Determinism (no guessing): a role resolves ONLY when the user has exactly one person of
that relationship type. Two daughters → "my daughter" is ambiguous → it does not resolve.
Only FIRST-PERSON phrases are supported this milestone; "his wife" / "Mike's wife" belong
to a future contextual engine and are intentionally out of scope.
"""
from .canonical_bridge import ensure_canonical

# relationship_type → first-person role phrases (normalized form: lowercase, "my …").
# The relationship TYPE is the presentation label (as it already is for Mother/Father/
# Son/Daughter/…), so each type derives ONLY the phrase appropriate to it — never
# contradictory phrases. A spouse is presented as Wife, Husband, Partner or the neutral
# Spouse, and each derives just its own phrase. No biological-gender attribute is modelled.
ROLE_PHRASES = {
    "spouse":        ["my spouse"],
    "wife":          ["my wife"],
    "husband":       ["my husband"],
    "partner":       ["my partner"],
    "mother":        ["my mom", "my mother"],
    "father":        ["my dad", "my father"],
    "son":           ["my son"],
    "daughter":      ["my daughter"],
    "brother":       ["my brother"],
    "sister":        ["my sister"],
    "grandmother":   ["my grandma", "my grandmother"],
    "grandfather":   ["my grandpa", "my grandfather"],
    "grandson":      ["my grandson"],
    "granddaughter": ["my granddaughter"],
    "aunt":          ["my aunt"],
    "uncle":         ["my uncle"],
    "cousin":        ["my cousin"],
    "niece":         ["my niece"],
    "nephew":        ["my nephew"],
}

# phrase → relationship_type (reverse index).
PHRASE_TO_TYPE = {p: rtype for rtype, phrases in ROLE_PHRASES.items() for p in phrases}


def _rel_model():
    from .models import Person as RelationshipsPerson
    return RelationshipsPerson


def _unique_active(user, relationship_type):
    """The single active contact of a relationship type, or None if absent/ambiguous."""
    RelPerson = _rel_model()
    rels = list(RelPerson.objects.filter(
        owner=user, status="active", relationship_type=relationship_type))
    return rels[0] if len(rels) == 1 else None


def resolve_relationship_role(user, normalized_role):
    """Role resolver hook: "my wife" → the canonical spouse (or None). Ensures the
    canonical mirror so resolution works even for a contact never opened before."""
    rtype = PHRASE_TO_TYPE.get(normalized_role)
    if not rtype:
        return None
    rel = _unique_active(user, rtype)
    if rel is None:
        return None
    return ensure_canonical(user, rel)


def person_role_phrases(user, canonical_person):
    """`person_roles` hook: the first-person role phrases that resolve to this canonical
    person (for the Person page + hover card). Only a UNIQUELY-held role is included."""
    from apps.people.models import PersonSourceLink
    RelPerson = _rel_model()
    link = (PersonSourceLink.objects
            .filter(person=canonical_person,
                    source_domain=PersonSourceLink.Source.RELATIONSHIPS)
            .first())
    if link is None:
        return []
    rel = RelPerson.objects.filter(pk=link.source_pk, owner=user, status="active").first()
    if rel is None or rel.relationship_type not in ROLE_PHRASES:
        return []
    if _unique_active(user, rel.relationship_type) is None:   # ambiguous → nothing derived
        return []
    return list(ROLE_PHRASES[rel.relationship_type])


def all_role_phrases(user):
    """`all_role_phrases` hook: every first-person role phrase that currently resolves for
    the user (candidate surfaces for passive prose recognition). Unique roles only."""
    from collections import Counter
    RelPerson = _rel_model()
    counts = Counter(
        RelPerson.objects.filter(owner=user, status="active")
        .exclude(relationship_type="")
        .values_list("relationship_type", flat=True))
    out = []
    for rtype, n in counts.items():
        if n == 1:
            out.extend(ROLE_PHRASES.get(rtype, []))
    return out
