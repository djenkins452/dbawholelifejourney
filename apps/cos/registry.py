"""
CoS v2 Action Registry — Central lookup for module action contracts.

Usage:
    from apps.cos.registry import cos_registry

    # Register (typically in AppConfig.ready or module init)
    cos_registry.register("calendar", CalendarCosActions)

    # Lookup & use
    actions = cos_registry.get("calendar", user=request.user)
    result = actions.create(title="Meeting", start_dt=..., end_dt=...)
"""

import logging
from typing import Dict, List, Optional, Type

from apps.cos.contracts import CosActionContract

logger = logging.getLogger(__name__)


class CosActionRegistry:
    """
    Singleton registry mapping module names to their CosActionContract classes.

    Thread-safe because Django processes are single-threaded per request
    and registration happens at import/ready time.
    """

    def __init__(self):
        self._contracts: Dict[str, Type[CosActionContract]] = {}

    def register(
        self,
        module_name: str,
        contract_class: Type[CosActionContract],
    ) -> None:
        """
        Register a module's action contract class.

        Args:
            module_name: Unique identifier (e.g. 'calendar', 'journal').
            contract_class: A CosActionContract subclass (NOT an instance).

        Raises:
            TypeError: If contract_class is not a CosActionContract subclass.
            ValueError: If module_name is already registered.
        """
        if not (
            isinstance(contract_class, type)
            and issubclass(contract_class, CosActionContract)
        ):
            raise TypeError(
                f"contract_class must be a CosActionContract subclass, "
                f"got {type(contract_class)}"
            )
        if module_name in self._contracts:
            raise ValueError(
                f"Module '{module_name}' is already registered. "
                f"Use unregister() first if replacing."
            )
        self._contracts[module_name] = contract_class
        logger.debug("CoS registry: registered '%s'", module_name)

    def unregister(self, module_name: str) -> None:
        """Remove a module from the registry."""
        self._contracts.pop(module_name, None)

    def get(self, module_name: str, user) -> Optional[CosActionContract]:
        """
        Get an instantiated action contract for the given module and user.

        Returns None if the module is not registered.
        """
        contract_class = self._contracts.get(module_name)
        if contract_class is None:
            return None
        return contract_class(user=user)

    def get_or_raise(self, module_name: str, user) -> CosActionContract:
        """
        Like get(), but raises KeyError if not registered.
        """
        contract = self.get(module_name, user)
        if contract is None:
            raise KeyError(
                f"No CoS action contract registered for module '{module_name}'. "
                f"Registered modules: {self.list_modules()}"
            )
        return contract

    def list_modules(self) -> List[str]:
        """Return sorted list of registered module names."""
        return sorted(self._contracts.keys())

    def is_registered(self, module_name: str) -> bool:
        """Check if a module is registered."""
        return module_name in self._contracts

    def clear(self) -> None:
        """Remove all registrations. Used in tests."""
        self._contracts.clear()


# Module-level singleton
cos_registry = CosActionRegistry()
