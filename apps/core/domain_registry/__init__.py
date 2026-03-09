# ==============================================================================
# File: apps/core/domain_registry/__init__.py
# Description: Domain Capability Registry — central registry for all WLJ domains
# ==============================================================================
"""
Domain Capability Registry

Every WLJ domain app registers its capabilities via a `capabilities.py` file.
The registry is auto-discovered at Django startup (like admin.autodiscover()).

Usage:
    from apps.core.domain_registry import registry

    # Get all registered domains
    domains = registry.get_all()

    # Get a specific domain
    health = registry.get('health')

    # Audit compliance
    from apps.core.domain_registry import audit_domains
    report = audit_domains()
"""

from .registry import registry, autodiscover  # noqa: F401
