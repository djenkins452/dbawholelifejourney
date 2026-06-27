"""
Observation Engine (Sprint 5) — the deterministic orchestrator.

Runs every observation rule, enforces the evidence requirement, passes everything
through the deterministic safety classifier, drops suppressed/duplicate
observations, and returns ONLY the approved observations Beth may narrate.
"""

from apps.health.observations.core import approve


def build_observations(user):
    """Return the approved deterministic Observation objects for a user."""
    from apps.health.observations.rules import (
        cross_domain_observations,
        medication_observations,
    )
    raw = medication_observations(user) + cross_domain_observations(user)
    return approve(raw)


def build_observation_dicts(user):
    """Approved observations as JSON-safe dicts for canonical state / Beth."""
    return [o.to_dict() for o in build_observations(user)]
