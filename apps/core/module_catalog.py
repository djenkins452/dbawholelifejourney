# ==============================================================================
# File: apps/core/module_catalog.py
# Description: Canonical Module Catalog — deterministic enablement and query API
# ==============================================================================
"""
Single source of truth for module enablement and catalog queries.

This module provides the canonical `is_module_enabled()` function that ALL code
should use to determine whether a module is available for a given user.

Enablement logic (evaluated in order):
    1. is_active=False → always disabled (admin kill switch)
    2. always_available=True → always enabled (system layers, Life)
    3. status='coming_soon' → always disabled (not yet available)
    4. UserModulePreference.is_enabled → user's choice
    5. default_enabled → catalog default for new users

Usage:
    from apps.core.module_catalog import is_module_enabled, get_module_catalog

    if is_module_enabled(user, 'health'):
        ...

    catalog = get_module_catalog()  # cached dict of slug → ModuleDefinition
"""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache key and TTL for the module catalog
_CATALOG_CACHE_KEY = 'wlj:module_catalog:all'
_CATALOG_CACHE_TTL = 300  # 5 minutes


def get_module_catalog(force_refresh=False):
    """
    Return the full module catalog as {slug: ModuleDefinition}.

    Cached for 5 minutes. The catalog is a small table (≤15 rows).
    """
    if not force_refresh:
        cached = cache.get(_CATALOG_CACHE_KEY)
        if cached is not None:
            return cached

    try:
        from apps.users.models import ModuleDefinition
        catalog = {m.slug: m for m in ModuleDefinition.objects.all()}
        cache.set(_CATALOG_CACHE_KEY, catalog, _CATALOG_CACHE_TTL)
        return catalog
    except Exception:
        logger.warning("module_catalog: Failed to load catalog from DB", exc_info=True)
        return {}


def invalidate_catalog_cache():
    """Invalidate the module catalog cache. Call after admin changes."""
    cache.delete(_CATALOG_CACHE_KEY)


def get_module(slug):
    """
    Get a single ModuleDefinition by slug.

    Returns None if not found.
    """
    catalog = get_module_catalog()
    return catalog.get(slug)


def is_module_enabled(user, module_slug):
    """
    Canonical enablement check — THE source of truth for module availability.

    Args:
        user: Django User instance
        module_slug: Module slug (e.g., 'health', 'journal', 'capture')

    Returns:
        bool: Whether the module is enabled for this user
    """
    module_def = get_module(module_slug)
    if module_def is None:
        # Unknown module — fail closed
        logger.warning("is_module_enabled: unknown module slug '%s'", module_slug)
        return False

    # Step 1: Admin kill switch
    if not module_def.is_active:
        return False

    # Step 2: Always-available system layers and core modules
    if module_def.always_available:
        return True

    # Step 3: Coming soon — not available yet
    if module_def.status == 'coming_soon':
        return False

    # Step 4: Check user preference
    try:
        from apps.users.models import UserModulePreference
        user_pref = UserModulePreference.objects.filter(
            user=user, module=module_def
        ).only('is_enabled').first()
        if user_pref is not None:
            return user_pref.is_enabled
    except Exception:
        logger.debug("is_module_enabled: could not read UserModulePreference", exc_info=True)

    # Step 5: Fall back to catalog default
    return module_def.default_enabled


def get_enabled_modules(user):
    """
    Return list of ModuleDefinition objects that are enabled for this user.

    Useful for building navigation, CoS context, etc.
    """
    catalog = get_module_catalog()
    if not catalog:
        return []

    enabled = []
    for slug, module_def in catalog.items():
        if not module_def.is_active:
            continue
        if module_def.always_available:
            enabled.append(module_def)
        elif module_def.status == 'coming_soon':
            continue
        elif is_module_enabled(user, slug):
            enabled.append(module_def)

    return sorted(enabled, key=lambda m: m.default_order)


def get_module_permissions(user):
    """
    Build the module_permissions dict for CoS context injection.

    Returns dict of {slug: bool} for all modules that participate in CoS.
    System layers with cos_participation=True are always True.
    """
    catalog = get_module_catalog()
    permissions = {}

    for slug, module_def in catalog.items():
        if not module_def.is_active:
            continue
        if module_def.catalog_type == 'internal':
            continue  # Internal modules don't appear in permissions
        if not module_def.cos_participation:
            continue  # Module doesn't participate in CoS
        permissions[slug] = is_module_enabled(user, slug)

    return permissions


def get_domain_to_module_map():
    """
    Build a mapping of domain_key → module_slug.

    Used for architecture validation and signal routing.
    Every domain should be owned by exactly one module.
    """
    catalog = get_module_catalog()
    domain_map = {}
    for slug, module_def in catalog.items():
        for domain_key in (module_def.mapped_domain_keys or []):
            if domain_key in domain_map:
                logger.warning(
                    "Domain '%s' is claimed by both '%s' and '%s'",
                    domain_key, domain_map[domain_key], slug
                )
            domain_map[domain_key] = slug
    return domain_map
