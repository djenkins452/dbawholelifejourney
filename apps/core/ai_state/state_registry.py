"""
SAE — State Registry.

Manages the mapping between module names and their state builders.
Allows dynamic registration of new module builders.
"""

import logging

logger = logging.getLogger(__name__)

# Registry populated by state_builder.py MODULE_BUILDERS
# This module provides the registration API for future extensions.

_custom_builders = {}


def register_builder(module_name, builder_fn):
    """
    Register a custom state builder for a module.

    Args:
        module_name: Module key (e.g., "finance", "brain_training").
        builder_fn: Callable(user) → dict.
    """
    _custom_builders[module_name] = builder_fn
    logger.info(f"SAE: Registered custom builder for module '{module_name}'")


def get_custom_builders():
    """Get all custom-registered builders."""
    return dict(_custom_builders)
