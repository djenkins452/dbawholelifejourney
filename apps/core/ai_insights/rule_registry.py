"""
Rule Registry — Pluggable registry for insight rules.

Add new rules without changing the engine:
    @register
    class MyRule(BaseInsightRule):
        ...
"""

RULES = []


def register(rule_cls):
    """Decorator to register an insight rule."""
    RULES.append(rule_cls())
    return rule_cls


def get_rules():
    """Get all registered insight rules."""
    return RULES


def get_rules_for_module(module):
    """Get rules that apply to a specific module."""
    return [r for r in RULES if r.module == module]
