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


def _reset_for_tests() -> None:
    _role_resolvers.clear()
    _merge_participants.clear()
