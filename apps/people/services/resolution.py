"""
The ONE deterministic Person resolution service.

Resolves a name/phrase to a canonical Person using, in order:
  exact canonical name → unique first name → @handle (compact) → derived
  relationship role (via registered feature resolvers) → confirmed custom/learned
  phrase.

Every match is deterministic and user-scoped. A step that matches exactly one active
person RESOLVES; a step that matches more than one is AMBIGUOUS (stop — never guess);
if nothing matches the reference is UNRESOLVED. This is the single answer to "how do I
resolve a Person?" and "how do I identify someone mentioned in a journal?".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from ..models import Person, RecognitionPhrase
from ..normalization import compact_name, normalize_name
from . import hooks

# Resolution status
RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
UNRESOLVED = "unresolved"

# source_type of a resolution (mirrors the structured mention source types)
EXACT_NAME = "exact_name"
RELATIONSHIP_ROLE = "relationship_role"
CONFIRMED_ALIAS = "confirmed_alias"


@dataclass
class Resolution:
    text: str
    status: str = UNRESOLVED
    person: Optional[Person] = None
    source_type: Optional[str] = None
    candidates: list = field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        return self.status == RESOLVED

    @property
    def is_ambiguous(self) -> bool:
        return self.status == AMBIGUOUS


def _finalize(text, persons, source_type):
    """Given the persons a step matched, decide resolved/ambiguous, or None to
    continue to the next step when nothing matched."""
    unique = {p.pk: p for p in persons}
    if not unique:
        return None
    if len(unique) == 1:
        return Resolution(text=text, status=RESOLVED,
                          person=next(iter(unique.values())), source_type=source_type)
    return Resolution(text=text, status=AMBIGUOUS, candidates=list(unique.values()),
                      source_type=source_type)


def resolve(user, text) -> Resolution:
    norm = normalize_name(text)
    if not norm:
        return Resolution(text=text, status=UNRESOLVED)
    compact = compact_name(text)

    persons = list(Person.objects.filter(user=user))  # active only (SoftDeleteManager)

    by_name = defaultdict(list)
    by_first = defaultdict(list)
    by_compact = defaultdict(list)
    for p in persons:
        for key in {normalize_name(p.display_name), normalize_name(p.full_name)}:
            if key:
                by_name[key].append(p)
        fn = normalize_name(p.first_name)
        if fn:
            by_first[fn].append(p)
        for key in {compact_name(p.display_name), compact_name(p.full_name)}:
            if key:
                by_compact[key].append(p)

    # 1. Exact canonical name (display or full name).
    result = _finalize(text, by_name.get(norm, []), EXACT_NAME)
    if result:
        return result

    # 2. Unique first name.
    result = _finalize(text, by_first.get(norm, []), EXACT_NAME)
    if result:
        return result

    # 3. @handle / compact form ("@HeatherJenkins" → "Heather Jenkins").
    result = _finalize(text, by_compact.get(compact, []), EXACT_NAME)
    if result:
        return result

    # 4. Derived relationship role ("wife", "my daughter") via registered feature
    #    resolvers. Deterministic + unique only; None if absent/ambiguous.
    role_person = hooks.resolve_role(user, norm)
    if role_person is not None:
        return Resolution(text=text, status=RESOLVED, person=role_person,
                          source_type=RELATIONSHIP_ROLE)

    # 5. Confirmed custom/learned recognition phrase.
    phrase_persons = [
        rp.person for rp in RecognitionPhrase.objects
        .filter(person__user=user, person__status="active", normalized=norm)
        .select_related("person")
    ]
    result = _finalize(text, phrase_persons, CONFIRMED_ALIAS)
    if result:
        return result

    return Resolution(text=text, status=UNRESOLVED)


# Aliases for call-site clarity.
def resolve_mention(user, text) -> Resolution:
    """Identify the canonical Person a mention refers to (same deterministic logic)."""
    return resolve(user, text)
