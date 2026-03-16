# ==============================================================================
# File: apps/core/domain_registry/registry.py
# Description: Central domain registry singleton with autodiscover
# ==============================================================================
"""
Domain Registry

Singleton registry that stores all DomainCapability instances.
Auto-discovered from each app's capabilities.py during Django startup.
"""

import importlib
import logging
from typing import Dict, List, Optional, Set

from django.apps import apps

from .descriptors import DomainCapability, DomainClass

logger = logging.getLogger(__name__)


class DomainRegistry:
    """
    Central registry for all WLJ domain capabilities.

    Thread-safe: populated once at startup, read-only after.
    """

    def __init__(self):
        self._domains = {}
        self._discovered = False

    def register(self, capability: DomainCapability):
        """Register a domain capability."""
        if not isinstance(capability, DomainCapability):
            raise TypeError(f"Expected DomainCapability, got {type(capability)}")

        if capability.name in self._domains:
            logger.warning(
                "Domain '%s' already registered — overwriting", capability.name,
            )

        self._domains[capability.name] = capability
        logger.debug("Registered domain: %s (%s)", capability.name, capability.display_name)

    def get(self, name: str) -> Optional[DomainCapability]:
        """Get a domain by name."""
        return self._domains.get(name)

    def get_all(self) -> Dict[str, DomainCapability]:
        """Get all registered domains."""
        return dict(self._domains)

    def get_names(self) -> List[str]:
        """Get sorted list of all domain names."""
        return sorted(self._domains.keys())

    def get_domains_with_signal(self, signal_type: str) -> List[DomainCapability]:
        """Get all domains that can generate a specific proactive signal."""
        return [
            d for d in self._domains.values()
            if signal_type in d.proactive_signals
        ]

    def get_related_domains(self, name: str) -> List[DomainCapability]:
        """Get domains related to the given domain."""
        domain = self._domains.get(name)
        if not domain:
            return []
        return [
            self._domains[r]
            for r in domain.related_domains
            if r in self._domains
        ]

    def get_all_intent_types(self) -> Set[str]:
        """Get the union of all registered intent types."""
        result = set()
        for d in self._domains.values():
            result.update(d.intent_types)
        return result

    def get_all_proactive_signals(self) -> Set[str]:
        """Get the union of all registered proactive signals."""
        result = set()
        for d in self._domains.values():
            result.update(d.proactive_signals)
        return result

    def get_coverage_summary(self) -> List[dict]:
        """Get coverage summary for all domains (for Command Center / Ops Wall)."""
        return [
            {
                'name': d.name,
                'display_name': d.display_name,
                'domain_class': d.domain_class,
                'intent_count': len(d.intent_types),
                'signal_count': len(d.proactive_signals),
                'has_context_builder': bool(d.context_builders),
                'model_count': len(d.primary_models),
                'coverage_score': d.coverage_score(),
                'is_user_life_domain': d.is_user_life_domain,
                'participates_in_cos': d.participates_in_cos,
            }
            for d in sorted(self._domains.values(), key=lambda x: x.name)
        ]

    def is_registered(self, name: str) -> bool:
        """Check if a domain key is registered."""
        return name in self._domains

    def get_by_class(self, domain_class: str) -> List[DomainCapability]:
        """Get all domains of a given class (behavioral, influence, etc.)."""
        return [
            d for d in self._domains.values()
            if d.domain_class == domain_class
        ]

    def get_user_life_domains(self) -> List[DomainCapability]:
        """Get all behavioral user-life domains."""
        return [d for d in self._domains.values() if d.is_user_life_domain]

    def get_cos_participating(self) -> List[DomainCapability]:
        """Get all domains that participate in CoS context."""
        return [d for d in self._domains.values() if d.participates_in_cos]

    @property
    def domain_count(self) -> int:
        return len(self._domains)


# Singleton instance
registry = DomainRegistry()


def autodiscover():
    """
    Auto-discover capabilities.py in all installed apps.

    Similar to django.contrib.admin.autodiscover().
    Called once during Django startup via AppConfig.ready().
    """
    if registry._discovered:
        return

    for app_config in apps.get_app_configs():
        module_name = f"{app_config.name}.capabilities"
        try:
            importlib.import_module(module_name)
        except ImportError:
            pass  # App has no capabilities.py — expected for many apps
        except Exception as e:
            logger.error(
                "Error loading capabilities for %s: %s",
                app_config.name, e, exc_info=True,
            )

    registry._discovered = True
    logger.info(
        "Domain registry: %d domains registered: %s",
        registry.domain_count,
        ', '.join(registry.get_names()),
    )
