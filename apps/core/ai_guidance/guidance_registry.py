"""
PGE -- Guidance Rule Registry.

Collects guidance rules via @register_guidance decorator.
Rules are evaluated during generate_guidance() to produce candidates.
"""

_GUIDANCE_RULES = []


def register_guidance(cls):
    """Register a guidance rule class."""
    _GUIDANCE_RULES.append(cls())
    return cls


def get_guidance_rules():
    """Return all registered guidance rules."""
    return list(_GUIDANCE_RULES)
