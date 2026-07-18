"""
Recognition Phrases — one unified capability on the canonical Person.

Three sources, ONE system:
  * derived  — computed from deterministic truth (names here; relationship roles via
               registered feature resolvers). Never stored; auto-updates with truth.
  * custom   — user-managed durable phrases (Honey, Sweetie).
  * learned  — durable phrases created ONLY on explicit user confirmation.

Authority chain (enforced by making these the only durable-write paths): AI proposes
→ WLJ validates → USER confirms → WLJ stores. No AI code path writes a durable phrase.
"""

from ..models import PersonEvent, RecognitionPhrase
from ..normalization import compact_name, normalize_name
from .provenance import record_person_event


def derived_phrases(person) -> list[str]:
    """Name-derived phrases for a person (normalized, deduped) — the internal MATCHING
    surfaces, including lowercase and compact ("heatherjenkins") forms. For display, use
    ``derived_display_names`` instead. Relationship-role derived phrases ("wife") are
    resolved dynamically via registered feature resolvers — see resolution.resolve — and
    are not enumerated here."""
    candidates = {
        normalize_name(person.display_name),
        normalize_name(person.full_name),
        normalize_name(person.first_name),
        compact_name(person.display_name),
        compact_name(person.full_name),
    }
    return sorted(c for c in candidates if c)


def derived_display_names(person) -> list[str]:
    """Human-readable auto-recognized names (ORIGINAL case), deduped: first name and
    full/display name. Excludes the lowercase-normalized and compact matching forms
    ("heatherjenkins") — those are internal artifacts, not shown to users."""
    out: list[str] = []
    for s in (person.first_name, person.last_name and person.full_name, person.display_name):
        s = (s or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _store(person, phrase, source, *, learned_from="", actor="user"):
    """The single durable-write path for a recognition phrase. Idempotent per
    (person, normalized). Only ever called from an explicit user-confirmed flow."""
    normalized = normalize_name(phrase)
    if not normalized:
        raise ValueError("Cannot store an empty recognition phrase.")
    obj, created = RecognitionPhrase.objects.get_or_create(
        person=person, normalized=normalized,
        defaults={"phrase": phrase.strip(), "source": source, "learned_from": learned_from},
    )
    if created:
        record_person_event(
            person, PersonEvent.Type.PHRASE_CONFIRMED, actor=actor,
            phrase=obj.phrase, source=source, learned_from=learned_from,
        )
    return obj


def add_custom_phrase(person, phrase, *, actor="user"):
    """User adds a custom phrase on the Person page."""
    return _store(person, phrase, RecognitionPhrase.Source.CUSTOM, actor=actor)


def confirm_learned_phrase(person, phrase, *, learned_from="", actor="user"):
    """The teaching moment: the user confirmed, during Save/Review, that a phrase
    means this person. Persist it durably so future entries resolve automatically."""
    return _store(
        person, phrase, RecognitionPhrase.Source.LEARNED,
        learned_from=learned_from, actor=actor,
    )


def remove_phrase(person, phrase, *, actor="user"):
    """Remove a custom/learned phrase (derived phrases can't be removed — they are
    deterministic truth). Records a PHRASE_REMOVED lifecycle event."""
    normalized = normalize_name(phrase)
    qs = RecognitionPhrase.objects.filter(person=person, normalized=normalized)
    existed = qs.exists()
    if existed:
        qs.delete()
        record_person_event(
            person, PersonEvent.Type.PHRASE_REMOVED, actor=actor, phrase=phrase
        )
    return existed
