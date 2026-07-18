"""
Platform capability: DOMAIN TRUTH OBJECTS.

The single canonical interface to a domain's truth. Every consumer — Beth,
dashboards, reports, exports, APIs, notifications, domain engines, cross-domain
engines, future interfaces — asks the same object the same way:

    truth = get_domain_truth(user, "health")
    truth.current("sleep_last_night")          # -> CurrentTruth   (now)
    truth.history("steps", "last_week")        # -> HistorySeries  (back then)
    truth.state()                              # -> SAE snapshot dict (composed current state)

A `DomainTruth` is a THIN FACADE: it composes the lower platform capabilities
(Current Truth, Point-in-Time History, Freshness, the SAE snapshot) and owns NO new
retrieval logic. Capabilities are the components; the Domain Truth Object is the
interface. This is the per-domain registration unit the Deterministic Provider
Registry will route over.
"""
from importlib import import_module

# Domain provider modules that self-register on import (lazy-loaded on first miss).
_KNOWN_PROVIDER_MODULES = (
    "apps.health.services.health_domain_truth",
    "apps.health.services.medicine_domain_truth",   # Medication Canonical Truth
    "apps.finance.services.finance_domain_truth",
    "apps.purpose.services.goal_domain_truth",       # Goals / Missions Canonical Truth
    "apps.life.services.project_domain_truth",        # Projects Canonical Truth
    "apps.life.services.event_domain_truth",          # Significant Events Canonical Truth
    "apps.meals.services.meals_domain_truth",         # Meal Intelligence Canonical Truth
    "apps.medical.services.medical_domain_truth",     # Medical / Lab Canonical Truth
    "apps.purpose.services.habit_domain_truth",       # Habits Canonical Truth
    "apps.notes.notes_domain_truth",                  # Notes Canonical Truth
    "apps.capture.services.capture_domain_truth",     # Capture Canonical Truth
    "apps.brain_training.services.brain_training_domain_truth",  # Brain Training Canonical Truth
    "apps.core.truth.domain_rollout",   # journal, calendar, tasks, faith, relationships
)

_REGISTRY = {}


def register_domain_truth(cls):
    """Class decorator — register a DomainTruth subclass under its `domain`."""
    if not getattr(cls, "domain", None):
        raise ValueError("DomainTruth subclass must set `domain`")
    _REGISTRY[cls.domain] = cls
    return cls


def get_domain_truth(user, domain):
    """Return the registered DomainTruth for `domain`, bound to `user`."""
    if domain not in _REGISTRY:
        for mod in _KNOWN_PROVIDER_MODULES:        # trigger self-registration
            try:
                import_module(mod)
            except Exception:
                pass
    cls = _REGISTRY.get(domain)
    if cls is None:
        raise KeyError(f"no DomainTruth registered for {domain!r}; "
                       f"have {sorted(_REGISTRY)}")
    return cls(user)


def registered_domains():
    for mod in _KNOWN_PROVIDER_MODULES:
        try:
            import_module(mod)
        except Exception:
            pass
    return sorted(_REGISTRY)


class DomainTruth:
    """Base facade. Subclasses implement `current()` / `history()` by delegating to
    the domain's Current Truth + History providers. `state()` is shared — it reads the
    pre-computed SAE module snapshot (never live-computes on the request path)."""

    domain = None
    current_metrics = ()          # introspection: metrics current() supports
    history_metrics = ()          # introspection: metrics history() supports

    def __init__(self, user):
        self.user = user

    def current(self, metric):
        raise NotImplementedError

    def history(self, metric, period="last_7_days", **kwargs):
        raise NotImplementedError

    def state(self):
        from apps.core.ai_state.state_engine import get_module_state
        return get_module_state(self.user, self.domain, allow_rebuild=False) or {}

    # ENTITY COMPLETENESS LAW (reusable Layer 1 pattern) ----------------------
    # THE LAW: a canonical entity is complete when it can completely answer the natural
    # business questions about itself from a SINGLE deterministic retrieval. Higher layers
    # retrieve that one complete object; they never assemble fragmented truth from many
    # calls. `describe(entity_type)` is that single retrieval — it returns the domain's
    # canonical entities, each a `CompleteEntity` (the current canonical implementation of
    # the law; the dimension set is open). Medication is the reference impl. See
    # apps/core/truth/entity.py + docs/LAYER1_ENTITY_COMPLETENESS_CONTRACT.md.
    entity_types = ()             # introspection: entity types describe() supports

    def describe(self, entity_type=None):
        """Single deterministic retrieval of the domain's canonical entities, each a
        `CompleteEntity` that can answer the natural questions about itself."""
        raise NotImplementedError(f"{self.domain} domain truth exposes no describe()")

    # ANALYSIS COMPLETENESS LAW (the investigate-before-concluding guarantee) --------
    # THE LAW: when the user's intent is ANALYSIS of a subject, the Chief of Staff must
    # investigate the deterministic truth WLJ holds before it may conclude "insufficient".
    # A prompt can only REQUEST that; it cannot GUARANTEE it. So WLJ performs the
    # investigation DETERMINISTICALLY: the Analysis surface composes EVERY relevant
    # retrieval for a subject (history across trailing windows + record detail + all-time
    # span/count) into ONE bundle carrying a deterministic completeness verdict
    # (holds_data / evidence). Composition, not reasoning — the model still reasons over
    # the bundle. Because one call returns the whole evidence set, the model can neither
    # under-gather nor truthfully claim "insufficient" while WLJ still holds the truth.
    # A domain declares its analyzable subjects here; the generic composer
    # (apps/ai/cos_services/domain_analysis.py) reuses history()/describe() — no new
    # retrieval logic. `subject -> {history_metric, entity_type, windows}`.
    analysis_subjects = {}        # introspection: subjects the Analysis surface can compose

    def supports(self):
        return {"current": tuple(self.current_metrics),
                "history": tuple(self.history_metrics),
                "entities": tuple(self.entity_types),
                "analysis": tuple(self.analysis_subjects)}
