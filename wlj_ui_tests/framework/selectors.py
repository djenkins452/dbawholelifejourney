"""WLJ UI Test Framework — Selector Resolution Engine.

Resolves YAML selector definitions to Playwright-compatible locator strings.
Supports 5 strategies with priority-based resolution per Section 4/Phase 4.

Priority Order:
  1. data-testid  →  [data-testid="value"]   (preferred, most stable)
  2. id           →  #value                   (stable if unique)
  3. name         →  [name="value"]           (form elements)
  4. role         →  role=value               (accessibility)
  5. text_contains → text=value               (fragile, last resort)
"""


class SelectorError(Exception):
    """Raised when selector resolution fails."""


# --- Strategy Registry ---

# Each strategy maps to a function that produces a Playwright locator string.
# Order defines priority (highest first) for compound resolution.
STRATEGY_PRIORITY = [
    "data-testid",
    "id",
    "name",
    "role",
    "text_contains",
]

STRATEGY_RESOLVERS = {
    "data-testid": lambda v: f'[data-testid="{v}"]',
    "id": lambda v: f"#{v}",
    "name": lambda v: f'[name="{v}"]',
    "role": lambda v: f"role={v}",
    "text_contains": lambda v: f"text={v}",
}


class SelectorResolver:
    """Resolves YAML selector dicts to Playwright locator strings.

    Supports single-strategy selectors (one strategy + value) and
    compound selectors (multiple strategies resolved by priority).
    """

    def resolve(self, selector):
        """Resolve a selector definition to a Playwright locator string.

        Args:
            selector: One of:
              - str: returned as-is (raw CSS/Playwright selector)
              - dict with 'strategy' + 'value': single-strategy resolution
              - dict with multiple strategy keys: compound resolution

        Returns:
            Playwright-compatible locator string.

        Raises:
            SelectorError: If the selector is invalid or strategy unknown.
        """
        if isinstance(selector, str):
            return selector

        if not isinstance(selector, dict):
            raise SelectorError(
                f"Selector must be a string or dict, got {type(selector).__name__}"
            )

        # Single-strategy format: {"strategy": "data-testid", "value": "btn"}
        if "strategy" in selector and "value" in selector:
            return self._resolve_single(selector["strategy"], selector["value"])

        # Compound format: {"data-testid": "btn", "name": "submit"}
        # Resolve by priority — use highest-priority strategy present
        return self._resolve_compound(selector)

    def _resolve_single(self, strategy, value):
        """Resolve a single strategy + value pair."""
        resolver = STRATEGY_RESOLVERS.get(strategy)
        if not resolver:
            raise SelectorError(
                f"Unknown selector strategy: '{strategy}'. "
                f"Valid strategies: {', '.join(STRATEGY_PRIORITY)}"
            )
        return resolver(value)

    def _resolve_compound(self, selector):
        """Resolve a compound selector using priority order.

        When multiple strategies are present, the highest-priority
        strategy is used. This allows YAML authors to provide fallbacks
        while the framework always picks the most stable selector.
        """
        for strategy in STRATEGY_PRIORITY:
            if strategy in selector:
                return self._resolve_single(strategy, selector[strategy])

        raise SelectorError(
            f"No valid strategy found in selector: {selector}. "
            f"Valid strategies: {', '.join(STRATEGY_PRIORITY)}"
        )

    @staticmethod
    def get_strategy_info(selector):
        """Extract strategy metadata from a selector dict.

        Returns:
            dict with 'strategy', 'value', and 'resolved' keys.
            Useful for reporting and prompt generation.
        """
        if isinstance(selector, str):
            return {
                "strategy": "raw",
                "value": selector,
                "resolved": selector,
            }

        if isinstance(selector, dict) and "strategy" in selector:
            strategy = selector["strategy"]
            value = selector.get("value", "")
            resolver = STRATEGY_RESOLVERS.get(strategy)
            return {
                "strategy": strategy,
                "value": value,
                "resolved": resolver(value) if resolver else f"UNKNOWN({value})",
            }

        return {
            "strategy": "unknown",
            "value": str(selector),
            "resolved": str(selector),
        }


# --- Module-level convenience function ---

_default_resolver = SelectorResolver()


def resolve_selector(selector):
    """Resolve a selector using the default SelectorResolver instance.

    This is the primary entry point for other framework modules.
    Replaces the basic resolve_selector from executor.py.

    Args:
        selector: str, or dict with strategy/value.

    Returns:
        Playwright-compatible locator string.
    """
    return _default_resolver.resolve(selector)
