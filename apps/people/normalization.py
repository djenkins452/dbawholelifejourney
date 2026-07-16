"""
Deterministic name/phrase normalization for the canonical Person domain.

Pure stdlib — NO app imports (the Core Person domain must not depend on any
feature module; see apps/people/tests/test_architecture_boundary.py). Every
resolver and recognition-phrase comparison normalizes through here so matching
is identical everywhere ("one resolution service, one recognition system").
"""

import re
import unicodedata

_STRIP_PUNCT = re.compile(r"[^\w\s'\-]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_name(value: str) -> str:
    """Canonical comparison form of a name or phrase.

    Lowercases, strips a leading ``@``, folds accents, drops punctuation (keeping
    apostrophes and hyphens inside words), and collapses whitespace. Deterministic
    and idempotent: ``normalize_name(normalize_name(x)) == normalize_name(x)``.
    """
    if not value:
        return ""
    v = unicodedata.normalize("NFKD", str(value))
    v = "".join(c for c in v if not unicodedata.combining(c))
    v = v.strip().lower().lstrip("@")
    v = _STRIP_PUNCT.sub(" ", v)
    v = _WHITESPACE.sub(" ", v).strip()
    return v


def compact_name(value: str) -> str:
    """Whitespace-free normalized form, so ``@HeatherJenkins`` matches
    ``Heather Jenkins``. Derived from :func:`normalize_name`."""
    return normalize_name(value).replace(" ", "")
