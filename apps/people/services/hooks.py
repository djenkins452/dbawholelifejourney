"""
Extension points for the canonical Person domain (dependency inversion).

The Core Person domain must never import a feature module (Relationships, Legacy,
Journal, …) — the dependency direction flows Core → features, never the reverse.
But some canonical operations need feature truth:

* Derived RECOGNITION PHRASES for relationship roles ("wife", "my daughter")
  depend on relationship truth owned by the Relationships / Legacy modules.
* A canonical MERGE must also re-point feature-owned relations (relationship edges,
  memories, mentions) when two identities collapse.

Core defines the interfaces here; feature modules REGISTER their implementations at
startup (in their own AppConfig.ready()). Core calls the registered callables
without importing the feature app. In Phase 0b nothing is registered yet — the
architecture is complete and the seams are ready; consumers are wired in later
phases. Registration is idempotent and order-independent.
"""

from __future__ import annotations

from typing import Callable, Optional

# ── Role resolvers ──────────────────────────────────────────────────────────
# fn(user, normalized_role) -> Person | None
# Return a Person ONLY when the user's deterministic relationship truth identifies
# exactly one valid person for that role phrase; None if absent or ambiguous.
_role_resolvers: list[Callable] = []

# ── Merge participants ──────────────────────────────────────────────────────
# fn(user, loser, winner) -> None
# Re-point this module's feature-owned relations from loser to winner. Must be
# idempotent and preservation-safe.
_merge_participants: list[Callable] = []

# ── Person summary providers ────────────────────────────────────────────────
# fn(user, person) -> dict  (e.g. {"relationship": "Spouse", "url": "/relationships/5/"})
# A feature contributes lightweight, DISPLAY-ONLY facts about a canonical Person for
# shared surfaces (the Person hover card). Providers MUST be cheap — a couple of indexed
# lookups, never heavy analytics — because they run on a hover-triggered request.
_person_summary_providers: list[Callable] = []

# ── Relationship-derived recognition ────────────────────────────────────────
# Deterministic first-person role phrases ("my wife") projected from a feature's
# relationship graph. NOT stored RecognitionPhrases — computed, read-only.
#   person_roles:     fn(user, person) -> [str]   (the phrases that resolve to this person)
#   role phrases:     fn(user)         -> [str]   (all currently-resolving role phrases)
_person_roles_providers: list[Callable] = []
_role_phrases_providers: list[Callable] = []


def _dedup(seq):
    seen, out = set(), []
    for item in seq:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def register_role_resolver(fn: Callable) -> Callable:
    if fn not in _role_resolvers:
        _role_resolvers.append(fn)
    return fn


def register_merge_participant(fn: Callable) -> Callable:
    if fn not in _merge_participants:
        _merge_participants.append(fn)
    return fn


def resolve_role(user, normalized_role: str) -> Optional[object]:
    """Ask registered feature resolvers for the unique Person a role phrase maps to.

    Deterministic: a role resolves only if exactly one registered resolver returns a
    person AND no other resolver returns a *different* person (a cross-module conflict
    is treated as ambiguous → None)."""
    found = None
    for fn in _role_resolvers:
        try:
            person = fn(user, normalized_role)
        except Exception:
            # A feature resolver must never break canonical resolution.
            continue
        if person is None:
            continue
        if found is not None and getattr(person, "pk", None) != getattr(found, "pk", None):
            return None  # conflicting resolvers → ambiguous
        found = person
    return found


def run_merge_participants(user, loser, winner) -> None:
    for fn in _merge_participants:
        fn(user, loser, winner)


def register_person_summary_provider(fn: Callable) -> Callable:
    if fn not in _person_summary_providers:
        _person_summary_providers.append(fn)
    return fn


def person_summary(user, person) -> dict:
    """Merge lightweight, display-only facts about a canonical Person from registered
    feature providers (for the shared hover card). First provider to supply a key wins;
    a failing provider is skipped so a feature can never break the card."""
    out: dict = {}
    for fn in _person_summary_providers:
        try:
            data = fn(user, person) or {}
        except Exception:
            continue
        for key, value in data.items():
            if key not in out and value:
                out[key] = value
    return out


def register_person_roles_provider(fn: Callable) -> Callable:
    if fn not in _person_roles_providers:
        _person_roles_providers.append(fn)
    return fn


def register_role_phrases_provider(fn: Callable) -> Callable:
    if fn not in _role_phrases_providers:
        _role_phrases_providers.append(fn)
    return fn


def person_roles(user, person) -> list:
    """Deterministic first-person role phrases that resolve to this canonical Person
    ("my wife", "my daughter") — read-only projections, for the Person page + hover card."""
    out: list = []
    for fn in _person_roles_providers:
        try:
            out.extend(fn(user, person) or [])
        except Exception:
            continue
    return _dedup(out)


def all_role_phrases(user) -> list:
    """Every first-person role phrase that currently resolves for the user — candidate
    surfaces for passive prose recognition."""
    out: list = []
    for fn in _role_phrases_providers:
        try:
            out.extend(fn(user) or [])
        except Exception:
            continue
    return _dedup(out)


def _reset_for_tests() -> None:
    _role_resolvers.clear()
    _merge_participants.clear()
    _person_summary_providers.clear()
    _person_roles_providers.clear()
    _role_phrases_providers.clear()
