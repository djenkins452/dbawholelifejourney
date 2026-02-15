"""
PRIE — Prediction Rule Registry.

Pluggable registry for prediction rules, following same pattern
as the PIE insight rule registry.
"""

PREDICTION_RULES = []


def register_prediction(rule_cls):
    """Decorator to register a prediction rule."""
    PREDICTION_RULES.append(rule_cls())
    return rule_cls


def get_prediction_rules():
    """Get all registered prediction rules."""
    return PREDICTION_RULES


def get_prediction_rules_for_module(module: str):
    """Get prediction rules that apply to a specific module."""
    return [r for r in PREDICTION_RULES if r.module == module]
