# ==============================================================================
# File: apps/core/truth/authority.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Retrieval Authority Metadata Contract (platform capability, F0)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-23
# ==============================================================================
"""
Retrieval Authority Metadata Contract — the platform capability that makes
Retrieval Authority Certification MECHANICAL.

    "A retrieval surface is not considered certified until every served value
     explicitly declares its authority and semantics."

WHY (runtime-proven, 2026-07-23): the certification pass could not mechanically
classify 9 of 111 served keys, because they declared no authority. A classifier
could not distinguish `current_medications` — a COMPLIANT projection delegating to
the canonical live `MedicineQueries` — from `average_glucose_yesterday`, a SHADOW
reading `SAE.health.glucose_avg_7d`. Both presented identically as
`authority: absent`. (The certification probe itself mis-classified
`current_medications`, which is the proof that the ambiguity was real and not
theoretical.) Ownership was only discoverable by reading source code.

WHAT THIS IS: a platform-level DECLARATION registry + vocabulary + validators.
It is NOT a retrieval surface, owns NO truth, and performs no reasoning. It records
what each served key's ownership IS — including, honestly, when that ownership is a
defect. Declaring a shadow as a shadow is the point: it converts an invisible
architectural violation into a mechanically countable one.

THE RATCHET: the contract test pins the CURRENT set of known shadow/missing keys.
A newly added key that omits metadata fails the build; a NEW shadow fails the build.
Closing a known shadow is a deliberate edit to the pinned set. Certification becomes
a test, not a review.
"""

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Vocabulary — deliberately small. Expand ONLY when runtime evidence proves a
# new concept is actually served (the standing rule: do not invent categories).
# ---------------------------------------------------------------------------

# How the value relates to the question's time scope.
EXACT_DATE = "exact_date"                    # observed ON the requested date
LATEST_ON_OR_BEFORE = "latest_on_or_before"  # carry-forward, WITH observed_on + age
LATEST_OBSERVATION = "latest_observation"    # most recent record, no date scope
ROLLING_AVERAGE = "rolling_average"          # mean over a trailing window
AGGREGATE = "aggregate"                      # count/total/change over a period
CURRENT = "current"                          # a "now" state scalar
PROJECTION = "projection"                    # a re-exposure of another surface
DERIVED_ZERO = "derived_zero"                # a structural zero, not a missing value

# LATEST_OBSERVATION and DERIVED_ZERO are included on runtime evidence: they are
# already emitted today (`health_facts._sleep_fact`, and the derived-zero path added
# with Derived Day-Key Coverage). They are not speculative additions.
SEMANTICS = frozenset({
    EXACT_DATE, LATEST_ON_OR_BEFORE, LATEST_OBSERVATION, ROLLING_AVERAGE,
    AGGREGATE, CURRENT, PROJECTION, DERIVED_ZERO,
})

# What KIND of truth the key serves.
CATEGORY_METRIC = "metric"        # a measured scalar over time
CATEGORY_RECORD = "record"        # an individual canonical record
CATEGORY_INVENTORY = "inventory"  # a set the user holds/takes
CATEGORY_STATUS = "status"        # a did-I / is-it boolean or state
CATEGORY_SUMMARY = "summary"      # a composed multi-value summary
TRUTH_CATEGORIES = frozenset({
    CATEGORY_METRIC, CATEGORY_RECORD, CATEGORY_INVENTORY, CATEGORY_STATUS,
    CATEGORY_SUMMARY,
})

# The five architectural conditions (the Retrieval Authority Audit's classification).
CANONICAL_AUTHORITY = "canonical_authority"
PROJECTION_OF = "projection"
SHADOW_AUTHORITY = "shadow_authority"
MISSING_PROJECTION = "missing_projection"
MISSING_AUTHORITY = "missing_authority"
CLASSIFICATIONS = frozenset({
    CANONICAL_AUTHORITY, PROJECTION_OF, SHADOW_AUTHORITY, MISSING_PROJECTION,
    MISSING_AUTHORITY,
})

# Classifications that represent an architectural DEFECT (tracked by the ratchet).
DEFECT_CLASSIFICATIONS = frozenset({
    SHADOW_AUTHORITY, MISSING_PROJECTION, MISSING_AUTHORITY,
})


@dataclass(frozen=True)
class AuthorityDeclaration:
    """What ONE served retrieval key declares about its ownership.

    `authority` is the identifier of the producer that actually answers this key
    (e.g. "get_domain_history:health.weight", "SAE.health.glucose_avg_7d",
    "MedicineQueries"). `delegates_to` is REQUIRED for a projection — it names the
    canonical authority the projection defers to, so "projection" can never be an
    unbacked claim.
    """
    authority: str
    semantics: str
    truth_category: str
    classification: str
    delegates_to: str = ""
    note: str = ""

    def is_defect(self):
        return self.classification in DEFECT_CLASSIFICATIONS


def validate(key, decl):
    """Return a list of contract violations for one declaration (empty = valid)."""
    errs = []
    if not isinstance(decl, AuthorityDeclaration):
        return [f"{key}: not an AuthorityDeclaration"]
    if not decl.authority:
        errs.append(f"{key}: empty authority — a served key may never be anonymous")
    if decl.semantics not in SEMANTICS:
        errs.append(f"{key}: unknown semantics {decl.semantics!r} "
                    f"(allowed: {sorted(SEMANTICS)})")
    if decl.truth_category not in TRUTH_CATEGORIES:
        errs.append(f"{key}: unknown truth_category {decl.truth_category!r}")
    if decl.classification not in CLASSIFICATIONS:
        errs.append(f"{key}: unknown classification {decl.classification!r}")
    # A projection must NAME the canonical authority it defers to.
    if decl.classification == PROJECTION_OF and not decl.delegates_to:
        errs.append(f"{key}: classified 'projection' but declares no delegates_to — "
                    f"a projection must reference a canonical authority")
    # A canonical authority may not simultaneously claim to delegate.
    if decl.classification == CANONICAL_AUTHORITY and decl.delegates_to:
        errs.append(f"{key}: classified 'canonical_authority' but declares "
                    f"delegates_to={decl.delegates_to!r} — it cannot both own and defer")
    return errs


def validate_surface(declarations, *, served_keys=None):
    """Validate a whole surface's declarations.

    Args:
        declarations: {key: AuthorityDeclaration}
        served_keys: every key the surface can actually serve. Any served key with
            no declaration is an ANONYMOUS key — the exact condition F0 removes.

    Returns: list of violation strings (empty = the surface satisfies the contract).
    """
    errs = []
    for key, decl in sorted((declarations or {}).items()):
        errs.extend(validate(key, decl))
    for key in sorted(set(served_keys or ()) - set(declarations or {})):
        errs.append(f"{key}: served but UNDECLARED (architecturally anonymous) — "
                    f"every served key must declare authority + semantics")
    return errs


def defects(declarations):
    """{key: classification} for every declared architectural defect. The ratchet
    pins this set; a new entry means a new shadow/missing path was introduced."""
    return {k: d.classification for k, d in (declarations or {}).items()
            if d.is_defect()}


def duplicate_answers(declarations):
    """Keys that claim to answer the SAME deterministic question — the same
    (authority, semantics) pair. More than one key per pair means two names for one
    answer, which is how a caller ends up with a choice it should not have.

    Returns {(authority, semantics): [keys]} for pairs claimed more than once.
    """
    seen = {}
    for key, decl in (declarations or {}).items():
        # Defects are reported separately; only well-formed owners are compared.
        if decl.is_defect():
            continue
        seen.setdefault((decl.authority, decl.semantics), []).append(key)
    return {pair: sorted(keys) for pair, keys in seen.items() if len(keys) > 1}


def stamp(fact, decl):
    """Attach declared metadata to a served fact, NEVER overwriting what the
    producer already supplied.

    A delegated fact already carries the authority/semantics its canonical producer
    stamped (e.g. `metric_date._fact`); that value is more specific than the static
    declaration and always wins. This only fills the gap for keys whose producer
    does not stamp — which is precisely the anonymity F0 removes.
    """
    if not isinstance(fact, dict) or not isinstance(decl, AuthorityDeclaration):
        return fact
    fact.setdefault("authority", decl.authority)
    fact.setdefault("semantics", decl.semantics)
    fact.setdefault("truth_category", decl.truth_category)
    fact.setdefault("classification", decl.classification)
    if decl.delegates_to:
        fact.setdefault("delegates_to", decl.delegates_to)
    return fact
