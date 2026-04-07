"""
Phase 1 — Domain gating helper.

Single source of truth for "is this domain enabled for this user?". Used by
signal collectors, CDCE detectors, PIE rules, and CoS context builders so the
enabled check lives in ONE place instead of being re-implemented (or forgotten)
at every consumer.

Behavior:
    - Reads ``UserPreferences`` parent-module flags (``health_enabled``,
      ``faith_enabled``, ``journal_enabled``, ``life_enabled``, ``purpose_enabled``).
    - Optional ``feature`` argument checks a sub-feature toggle inside the parent
      module via ``UserPreferences.is_feature_enabled``.
    - Fail-closed: any error resolving preferences treats the domain as disabled
      so a misconfigured user never causes signals to be fabricated.

This helper is intentionally minimal. The Trust Contract (Phase 3) will replace
ad-hoc gating with a richer surface_eligibility resolver, but Phase 1 only needs
a single place to ask the enabled question.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Map our internal domain keys to the UserPreferences flag attribute name.
# Aliases let callers use either the data-domain name (e.g. "fasting") or the
# parent-module name (e.g. "health"). When an alias points at a sub-feature
# under a parent module, we also record the sub-feature key.
_PARENT_FLAG = {
    'health': ('health_enabled', None),
    'faith': ('faith_enabled', None),
    'journal': ('journal_enabled', None),
    'life': ('life_enabled', None),
    'organize': ('life_enabled', None),
    'purpose': ('purpose_enabled', None),
    'goals': ('purpose_enabled', None),
    # Sub-domains under health
    'fitness': ('health_enabled', None),
    'workout': ('health_enabled', None),
    'workouts': ('health_enabled', None),
    'nutrition': ('health_enabled', None),
    'meals': ('health_enabled', None),
    'sleep': ('health_enabled', None),
    'fasting': ('health_enabled', 'fasting'),
    'medicine': ('health_enabled', 'medicine'),
    'medications': ('health_enabled', 'medicine'),
    'body_composition': ('health_enabled', None),
    # Sub-domains under organize/life
    'habits': ('life_enabled', None),
    'tasks': ('life_enabled', None),
    'routines': ('life_enabled', None),
    'transformation': ('health_enabled', None),
}


def is_domain_enabled(user, domain: str, feature: Optional[str] = None) -> bool:
    """
    Return True iff ``domain`` (and optional sub-``feature``) is enabled for the user.

    Fail-closed semantics: returns False on missing preferences or any
    resolution error. Callers must treat False as "do not produce signals".

    Args:
        user: Django User instance (or anything with a ``preferences`` attr).
        domain: Domain key (e.g. ``"health"``, ``"faith"``, ``"fasting"``).
            Unknown domains default to enabled (True) so newly-added domains
            are not silently suppressed before they have a flag.
        feature: Optional sub-feature key. If provided, the parent module must
            be enabled AND the sub-feature toggle must be on.

    Returns:
        bool — True if the user has the domain (and feature) enabled.
    """
    prefs = getattr(user, 'preferences', None)
    if prefs is None:
        return False

    parent_attr, sub_feature = _PARENT_FLAG.get(domain, (None, None))
    # If caller passed an explicit feature, prefer it over the table mapping.
    if feature is not None:
        sub_feature = feature

    # Unknown domain → assume enabled (safer than silently suppressing).
    if parent_attr is None:
        return True

    try:
        if not getattr(prefs, parent_attr, True):
            return False
    except Exception as exc:
        logger.warning(
            "domain_gating: failed to read %s for user %s: %s",
            parent_attr, getattr(user, 'pk', '?'), exc,
        )
        return False

    if sub_feature:
        try:
            # is_feature_enabled handles its own parent-module check internally
            # but we already short-circuited above; pass the parent module name
            # the way UserPreferences expects it.
            parent_module_for_features = {
                'health_enabled': 'health',
                'life_enabled': 'organize',
                'purpose_enabled': 'goals',
                'faith_enabled': 'faith',
                'journal_enabled': 'journal',
            }.get(parent_attr, 'health')
            return bool(prefs.is_feature_enabled(parent_module_for_features, sub_feature))
        except Exception as exc:
            logger.warning(
                "domain_gating: is_feature_enabled(%s, %s) failed for user %s: %s",
                parent_module_for_features, sub_feature,
                getattr(user, 'pk', '?'), exc,
            )
            return False

    return True
