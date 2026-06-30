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

    # COMPLETE BUSINESS OBJECT (reusable Layer 1 pattern) ----------------------
    # Layer 1 exposes COMPLETE business objects; higher layers retrieve ONE object and
    # never assemble fragmented truth from many calls. A domain's `profile()` composes
    # all attributes a natural question about the entity needs (inventory + status +
    # execution + history) into one deterministic object. Every future canonical entity
    # (Goals, Calendar, Journal, Relationships, …) should implement this. The Medication
    # domain is the reference implementation.
    profile_entities = ()         # introspection: entities profile() supports

    def profile(self, entity=None):
        raise NotImplementedError(f"{self.domain} domain truth exposes no profile()")

    def supports(self):
        return {"current": tuple(self.current_metrics),
                "history": tuple(self.history_metrics),
                "profile": tuple(self.profile_entities)}
