"""
Deterministic Provider Registry (Layer 1 — the last platform capability).

Routes a foundational-fact key to the domain provider that owns it. Replaces the
hardcoded GOAL / EXECUTION / HEALTH branches in `answer_foundational_fact`: a new
domain registers a provider (`predicate -> (user, keys) -> {key: fact}`) instead of
editing the dispatch. Ordered; exactly one provider may be the default (fallback).

This is the seam that turns the uniform truth layer (Current Truth, History, Domain
Truth Objects) into Beth-answerable facts by REGISTRATION, not per-domain plumbing.
"""
import logging

logger = logging.getLogger(__name__)

_PROVIDERS = []   # [{predicate, provider, source, default}]


def register_fact_provider(predicate, provider, source, *, default=False):
    """Register a provider. `predicate(key)->bool` selects keys it owns (ignored for
    the default). `provider(user, [key])->{key: fact_dict}`. `source` is the label
    recorded in tools_called. Idempotent per source (re-registration replaces)."""
    global _PROVIDERS
    _PROVIDERS = [p for p in _PROVIDERS if p["source"] != source]
    _PROVIDERS.append({"predicate": predicate, "provider": provider,
                       "source": source, "default": bool(default)})


def resolve(user, key):
    """Return (fact_dict, source) for `key`; falls back to the default provider; or
    ({}, None) if nothing matches."""
    default = None
    for p in _PROVIDERS:
        if p["default"]:
            default = p
            continue
        try:
            if p["predicate"](key):
                return _extract(p["provider"](user, [key]), key), p["source"]
        except Exception:
            logger.warning("fact_registry: provider %s failed key=%s",
                           p["source"], key, exc_info=True)
    if default is not None:
        try:
            return _extract(default["provider"](user, [key]), key), default["source"]
        except Exception:
            logger.warning("fact_registry: default provider failed key=%s",
                           key, exc_info=True)
    return {}, None


def _extract(facts, key):
    return facts.get(key, {}) if isinstance(facts, dict) else {}


def registered_sources():
    return [p["source"] for p in _PROVIDERS]
