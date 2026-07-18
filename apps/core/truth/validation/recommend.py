# ==============================================================================
# File: apps/core/truth/validation/recommend.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Smart-execution recommender — map changed code paths to the Truth
#   Validation scopes worth running. Pure function, designed so a future CI job can
#   call it. NOT wired to CI (per the architecture: design for it, don't build it yet).
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""suites_for_changed_paths(paths) -> recommended validation scopes.

A change to a domain's truth provider (or the model-facing read surfaces, or the truth
core) should be re-validated. This maps changed file paths to `domain:<name>` scopes using
(a) the domain tags already in the discovery suite and (b) app-directory heuristics. A
change to a shared truth/tool surface recommends the whole Truth Layer (`full`).
"""
import re
from typing import Iterable, List

# Paths that affect ALL domains -> recommend the full Truth Layer.
_GLOBAL_MARKERS = (
    "apps/core/truth/",                 # truth core + comparison engine
    "apps/ai/cos_services/",            # get_domain_entity/state/history/analysis
    "apps/ai/cos_gateway/",             # the production send path
    "apps/ai/model_interface/",         # the CoS runtime
)
# App-directory -> domain name (only domains the discovery suite covers).
_APP_DOMAIN = {
    "health": "health", "medical": "medical", "nutrition": "nutrition",
    "meals": "meals", "journal": "journal", "faith": "faith",
    "purpose": "goals", "life": "projects", "relationships": "relationships",
    "people": "relationships", "legacy": "legacy", "calendar_engine": "calendar",
    "capture": "capture", "notes": "notes", "brain_training": "brain_training",
}
_APP_RE = re.compile(r"apps/([a-z_]+)/")


def domains_from_discovery():
    """The set of domains the discovery suite actually validates."""
    try:
        from apps.core.truth.discovery_suite import prompts_by_domain
        return set(prompts_by_domain().keys())
    except Exception:
        return set()


def suites_for_changed_paths(paths: Iterable[str]) -> List[str]:
    """Return recommended scopes for a set of changed file paths.

    Returns `["full"]` when a shared truth surface changed; otherwise a sorted list of
    `domain:<name>` scopes for the domains whose providers changed. Empty when nothing
    truth-relevant changed.
    """
    paths = [str(p).replace("\\", "/") for p in (paths or [])]
    if not paths:
        return []
    covered = domains_from_discovery()

    for p in paths:
        if any(marker in p for marker in _GLOBAL_MARKERS):
            return ["full"]

    domains = set()
    for p in paths:
        m = _APP_RE.search(p)
        if not m:
            continue
        app = m.group(1)
        domain = _APP_DOMAIN.get(app)
        if domain and (not covered or domain in covered):
            domains.add(domain)
    return [f"domain:{d}" for d in sorted(domains)]
