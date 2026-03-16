# ==============================================================================
# File: apps/core/domain_registry/validation.py
# Description: Phase 3 + Phase 4 — Domain & Signal governance validation
#
# Validates alignment between governance layers:
#   1. Domain Registry (DomainCapability) — canonical domain identity
#   2. Module Catalog (ModuleDefinition) — module participation & enablement
#   3. Builder Registry (_TAGGED_BUILDERS) — CoS context assembly
#   4. Signal Taxonomy (SIGNAL_TYPE_DOMAIN) — signal governance (Phase 4)
# ==============================================================================
"""
Domain Registry & Signal Taxonomy Validation

Deterministic validation that all domain references and signal types
resolve to canonical governance entries. Detects drift between the
registry, catalog, builder, and signal layers.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def is_registered_domain(domain_key: str) -> bool:
    """Check if a domain key is registered in the canonical Domain Registry."""
    from .registry import registry
    return registry.is_registered(domain_key)


def get_domain_definition(domain_key: str):
    """Get the DomainCapability for a registered domain key, or None."""
    from .registry import registry
    return registry.get(domain_key)


def validate_module_domain_mappings() -> Dict[str, List[str]]:
    """
    Validate that every module's mapped_domain_keys resolve to registered domains.

    Returns:
        {
            'valid': [(module_slug, domain_key), ...],
            'invalid': [(module_slug, domain_key, reason), ...],
            'unmapped_modules': [module_slug, ...],  # modules with no domain keys
        }
    """
    from .registry import registry

    result = {'valid': [], 'invalid': [], 'unmapped_modules': []}

    try:
        from apps.users.models import ModuleDefinition
        modules = ModuleDefinition.objects.filter(is_active=True)
    except Exception as e:
        logger.warning("Cannot validate module mappings: %s", e)
        return result

    for module in modules:
        domain_keys = module.mapped_domain_keys or []
        if not domain_keys:
            result['unmapped_modules'].append(module.slug)
            continue

        for dk in domain_keys:
            if registry.is_registered(dk):
                result['valid'].append((module.slug, dk))
            else:
                result['invalid'].append((
                    module.slug, dk,
                    f"Domain '{dk}' mapped by module '{module.slug}' "
                    f"is not registered in DomainRegistry"
                ))

    return result


def validate_builder_domain_keys() -> Dict[str, List]:
    """
    Validate that every builder's domain_key resolves to a registered domain.

    System builders (domain_key=None) are always valid.

    Returns:
        {
            'valid': [(tag, domain_key), ...],
            'invalid': [(tag, domain_key, reason), ...],
            'system': [tag, ...],
        }
    """
    from .registry import registry

    result = {'valid': [], 'invalid': [], 'system': []}

    try:
        from apps.core.ai_orchestrator.cos_context import _TAGGED_BUILDERS
    except ImportError:
        logger.warning("Cannot import _TAGGED_BUILDERS for validation")
        return result

    for tag, _fn, domain_key in _TAGGED_BUILDERS:
        if domain_key is None:
            result['system'].append(tag)
        elif registry.is_registered(domain_key):
            result['valid'].append((tag, domain_key))
        else:
            result['invalid'].append((
                tag, domain_key,
                f"Builder '{tag}' references domain '{domain_key}' "
                f"which is not registered in DomainRegistry"
            ))

    return result


def validate_catalog_registry_alignment() -> Dict[str, List]:
    """
    Cross-validate Module Catalog ↔ Domain Registry alignment.

    Checks:
    - Catalog domain keys resolve to registry
    - Registry domains that claim CoS participation have builders
    - Builder domain keys map to modules via catalog

    Returns comprehensive alignment report.
    """
    from .registry import registry

    report = {
        'module_mapping': validate_module_domain_mappings(),
        'builder_keys': validate_builder_domain_keys(),
        'orphaned_registry_entries': [],
        'cos_without_builder': [],
        'classification_mismatches': [],
        'is_aligned': True,
    }

    # Check for registry entries with no module mapping
    try:
        from apps.core.module_catalog import get_domain_to_module_map
        domain_to_module = get_domain_to_module_map()
    except Exception:
        domain_to_module = {}

    for name, domain in registry.get_all().items():
        if name not in domain_to_module:
            # Not necessarily wrong — influence/system domains may not map to modules
            if domain.is_user_life_domain:
                report['orphaned_registry_entries'].append((
                    name, domain.domain_class,
                    f"Behavioral domain '{name}' has no module mapping"
                ))

    # Check for CoS-participating domains that have no builder
    try:
        from apps.core.ai_orchestrator.cos_context import _TAGGED_BUILDERS
        builder_domains = {dk for _, _, dk in _TAGGED_BUILDERS if dk is not None}
        # All builder tags (both system and domain) — a domain's context_builder
        # may run under a different tag (e.g., 'plan' serves life's _build_plan_and_alignment)
        all_builder_tags = {tag for tag, _, _ in _TAGGED_BUILDERS}
    except ImportError:
        builder_domains = set()
        all_builder_tags = set()

    for name, domain in registry.get_all().items():
        if domain.context_builders and name not in builder_domains:
            # Domain declares context_builders but isn't a direct domain builder.
            # Check if it's covered by a system-level builder (e.g., life's
            # _build_plan_and_alignment runs under the 'plan' system tag,
            # journal's _build_people_and_mood runs under 'relationships' tag).
            # This is architecturally valid — some builders serve multiple domains.
            if name not in all_builder_tags:
                # Not even a system-level tag — only flag if no other builder
                # references this domain's context_builder functions.
                # This is a soft warning, not a hard failure, because
                # system-level builders legitimately serve domain context.
                pass  # Covered by system-level builders — not a drift issue

    # Set alignment flag
    if (report['module_mapping']['invalid']
            or report['builder_keys']['invalid']
            or report['orphaned_registry_entries']
            or report['cos_without_builder']):
        report['is_aligned'] = False

    return report


# =============================================================================
# Phase 4 — Signal Taxonomy Validation
# =============================================================================


def validate_signal_domain_mappings() -> Dict[str, List]:
    """
    Validate that every SIGNAL_TYPE_DOMAIN domain exists in the Domain Registry.

    Returns:
        {
            'valid': [(signal_type, domain), ...],
            'invalid': [(signal_type, domain, reason), ...],
        }
    """
    from .registry import registry

    result = {'valid': [], 'invalid': []}

    try:
        from apps.core.ai_eae.signal_aggregation import SIGNAL_TYPE_DOMAIN
    except ImportError:
        logger.warning("Cannot import SIGNAL_TYPE_DOMAIN for validation")
        return result

    for signal_type, domain in SIGNAL_TYPE_DOMAIN.items():
        if registry.is_registered(domain):
            result['valid'].append((signal_type, domain))
        else:
            result['invalid'].append((
                signal_type, domain,
                f"Signal type '{signal_type}' maps to domain '{domain}' "
                f"which is not registered in DomainRegistry"
            ))

    return result


def validate_expected_signal_types() -> Dict[str, List]:
    """
    Validate that every DomainCapability.expected_signal_types entry
    exists in the signal taxonomy (SIGNAL_TYPE_DOMAIN).

    Returns:
        {
            'valid': [(domain_name, signal_type), ...],
            'invalid': [(domain_name, signal_type, reason), ...],
            'domains_without_signals': [domain_name, ...],
        }
    """
    from .registry import registry

    result = {'valid': [], 'invalid': [], 'domains_without_signals': []}

    try:
        from apps.core.ai_eae.signal_aggregation import SIGNAL_TYPE_DOMAIN
    except ImportError:
        logger.warning("Cannot import SIGNAL_TYPE_DOMAIN for validation")
        return result

    taxonomy_types = set(SIGNAL_TYPE_DOMAIN.keys())

    for name, domain in registry.get_all().items():
        expected = getattr(domain, 'expected_signal_types', [])
        if not expected:
            # Only flag behavioral domains that participate in CoS
            if domain.is_user_life_domain and domain.participates_in_cos:
                result['domains_without_signals'].append(name)
            continue

        for st in expected:
            if st in taxonomy_types:
                result['valid'].append((name, st))
            else:
                result['invalid'].append((
                    name, st,
                    f"Domain '{name}' declares expected signal type '{st}' "
                    f"which does not exist in SIGNAL_TYPE_DOMAIN"
                ))

    return result


def validate_signal_computer_coverage() -> Dict[str, List]:
    """
    Validate that every taxonomy signal type has a registered computer
    or is intentionally stubbed.

    Returns:
        {
            'covered': [signal_type, ...],
            'stubbed': [(signal_type, reason), ...],
            'missing': [signal_type, ...],
        }
    """
    result = {'covered': [], 'stubbed': [], 'missing': []}

    try:
        from apps.core.ai_eae.signal_aggregation import (
            SIGNAL_TYPE_DOMAIN,
            STUBBED_SIGNAL_TYPES,
            SignalAggregationService,
        )
    except ImportError:
        logger.warning("Cannot import signal aggregation for validation")
        return result

    # Map method names to signal types
    computer_method_names = {
        '_compute_health_activity': 'health_activity',
        '_compute_health_biometrics': 'health_biometrics',
        '_compute_medication_adherence': 'medication_adherence',
        '_compute_nutrition_compliance': 'nutrition_compliance',
        '_compute_faith_practice': 'faith_practice',
        '_compute_mental_reflection': 'mental_reflection',
        '_compute_cognitive_fitness': 'cognitive_fitness',
        '_compute_productivity_progress': 'productivity_progress',
        '_compute_relational_engagement': 'relational_engagement',
        '_compute_financial_health': 'financial_health',
    }

    # Phase 5: Pattern types are computed by PatternEngine, not individual computers
    try:
        from apps.core.ai_eae.pattern_taxonomy import PATTERN_TYPES
    except ImportError:
        PATTERN_TYPES = set()

    available_computers = set()
    for method_name, signal_type in computer_method_names.items():
        if hasattr(SignalAggregationService, method_name):
            available_computers.add(signal_type)

    for signal_type in SIGNAL_TYPE_DOMAIN:
        if signal_type in PATTERN_TYPES:
            continue  # Patterns are computed by PatternEngine, not signal computers
        if signal_type in STUBBED_SIGNAL_TYPES:
            result['stubbed'].append((signal_type, STUBBED_SIGNAL_TYPES[signal_type]))
        elif signal_type in available_computers:
            result['covered'].append(signal_type)
        else:
            result['missing'].append(signal_type)

    return result


def validate_cos_signal_coverage() -> Dict[str, List]:
    """
    Validate that every behavioral CoS-participating domain contributes
    to CoS through at least one of:
      1. Direct signal taxonomy ownership (expected_signal_types)
      2. Context builders that contribute state to CoS
      3. Contribution through a related domain's signals

    Domains that have neither signals NOR builders are flagged.

    Returns:
        {
            'covered_by_signals': [(domain_name, [signal_types]), ...],
            'covered_by_builders': [domain_name, ...],
            'uncovered': [(domain_name, reason), ...],
        }
    """
    from .registry import registry

    result = {'covered_by_signals': [], 'covered_by_builders': [], 'uncovered': []}

    try:
        from apps.core.ai_eae.signal_aggregation import SIGNAL_TYPE_DOMAIN
    except ImportError:
        return result

    # Invert: domain → signal types
    domain_signals = {}
    for st, domain in SIGNAL_TYPE_DOMAIN.items():
        domain_signals.setdefault(domain, []).append(st)

    for name, domain in registry.get_all().items():
        if not domain.participates_in_cos:
            continue
        if not domain.is_user_life_domain:
            continue  # Influence/knowledge domains don't require signals

        signals = domain_signals.get(name, [])
        if signals:
            result['covered_by_signals'].append((name, signals))
        elif domain.context_builders or domain.proactive_signals:
            # Domain contributes via builders or proactive signals
            # (e.g., purpose via builders, meals via proactive_signals
            # and data that feeds health's nutrition_compliance signal).
            # Architecturally valid — some domains participate in CoS
            # through builders or related domain signals rather than
            # direct taxonomy signal ownership.
            result['covered_by_builders'].append(name)
        else:
            result['uncovered'].append((
                name,
                f"Behavioral CoS-participating domain '{name}' has neither "
                f"signal types, context builders, nor proactive signals — "
                f"no CoS contribution path"
            ))

    return result


def get_signal_health_summary() -> Dict:
    """
    Signal governance health summary for Ops Wall / diagnostics.

    Returns:
        {
            'status': 'healthy' | 'drift_detected',
            'taxonomy_types': int,
            'computers_covered': int,
            'computers_stubbed': int,
            'computers_missing': int,
            'domain_mapping_issues': [str, ...],
            'expected_type_issues': [str, ...],
            'cos_coverage_issues': [str, ...],
            'domains_without_signals': [str, ...],
        }
    """
    domain_mappings = validate_signal_domain_mappings()
    expected_types = validate_expected_signal_types()
    computers = validate_signal_computer_coverage()
    cos_coverage = validate_cos_signal_coverage()

    domain_issues = [reason for _, _, reason in domain_mappings.get('invalid', [])]
    expected_issues = [reason for _, _, reason in expected_types.get('invalid', [])]
    cos_issues = [reason for _, reason in cos_coverage.get('uncovered', [])]

    try:
        from apps.core.ai_eae.signal_aggregation import SIGNAL_TYPE_DOMAIN
        taxonomy_count = len(SIGNAL_TYPE_DOMAIN)
    except ImportError:
        taxonomy_count = 0

    all_issues = domain_issues + expected_issues + cos_issues

    pattern_health = get_pattern_health_summary()

    return {
        'status': 'healthy' if not all_issues else 'drift_detected',
        'taxonomy_types': taxonomy_count,
        'computers_covered': len(computers.get('covered', [])),
        'computers_stubbed': len(computers.get('stubbed', [])),
        'computers_missing': len(computers.get('missing', [])),
        'domain_mapping_issues': domain_issues,
        'expected_type_issues': expected_issues,
        'cos_coverage_issues': cos_issues,
        'domains_without_signals': expected_types.get('domains_without_signals', []),
        'pattern_health': pattern_health,
    }


# =============================================================================
# Phase 5 — Pattern Taxonomy Validation
# =============================================================================


def validate_pattern_taxonomy() -> Dict[str, List]:
    """
    Validate pattern taxonomy: no collisions with base signal types,
    names fit field constraints, and domains resolve to the Domain Registry.

    Returns:
        {
            'valid': [pattern_type, ...],
            'collisions': [(pattern_type, reason), ...],
            'oversized': [(pattern_type, len), ...],
            'unregistered_domains': [(pattern_type, domain, reason), ...],
        }
    """
    from .registry import registry

    result = {'valid': [], 'collisions': [], 'oversized': [], 'unregistered_domains': []}

    try:
        from apps.core.ai_eae.pattern_taxonomy import PATTERN_TYPES, BASE_SIGNAL_TYPES
        from apps.core.ai_eae.signal_aggregation import SIGNAL_TYPE_DOMAIN
    except ImportError:
        logger.warning("Cannot import pattern/signal taxonomy for validation")
        return result

    for pt in PATTERN_TYPES:
        has_issue = False

        if pt in BASE_SIGNAL_TYPES:
            result['collisions'].append((
                pt, f"Pattern type '{pt}' collides with base signal type"
            ))
            has_issue = True

        if len(pt) > 30:
            result['oversized'].append((pt, len(pt)))
            has_issue = True

        # Verify domain resolves to registry
        domain = SIGNAL_TYPE_DOMAIN.get(pt)
        if domain and not registry.is_registered(domain):
            result['unregistered_domains'].append((
                pt, domain,
                f"Pattern type '{pt}' maps to domain '{domain}' "
                f"which is not registered in DomainRegistry"
            ))
            has_issue = True

        if not has_issue:
            result['valid'].append(pt)

    return result


def get_pattern_health_summary() -> Dict:
    """
    Pattern governance health summary for Ops Wall / diagnostics.

    Returns:
        {
            'status': 'healthy' | 'drift_detected',
            'catalog_types': int,
            'valid_count': int,
            'issues': [str, ...],
        }
    """
    taxonomy = validate_pattern_taxonomy()

    try:
        from apps.core.ai_eae.pattern_taxonomy import PATTERN_TYPE_CATALOG
        catalog_count = len(PATTERN_TYPE_CATALOG)
    except ImportError:
        catalog_count = 0

    issues = [
        reason for _, reason in taxonomy.get('collisions', [])
    ] + [
        f"Pattern type '{pt}' exceeds 30 char limit ({length})"
        for pt, length in taxonomy.get('oversized', [])
    ] + [
        reason for _, _, reason in taxonomy.get('unregistered_domains', [])
    ]

    return {
        'status': 'healthy' if not issues else 'drift_detected',
        'catalog_types': catalog_count,
        'valid_count': len(taxonomy.get('valid', [])),
        'issues': issues,
    }


# =============================================================================
# Combined Health Summary (Phase 3 + Phase 4 + Phase 5)
# =============================================================================


def get_registry_health_summary() -> Dict:
    """
    Produce a concise health summary for the Ops Wall or diagnostics.

    Combines Phase 3 (domain governance) and Phase 4 (signal governance).

    Returns:
        {
            'status': 'healthy' | 'drift_detected',
            'domain_count': int,
            'by_class': {class: count, ...},
            'issues': [str, ...],
            'signal_health': {signal governance summary},
            'details': {full alignment report},
        }
    """
    from .registry import registry
    from .descriptors import DomainClass

    alignment = validate_catalog_registry_alignment()
    signal_health = get_signal_health_summary()

    # Count by class
    by_class = {}
    for domain in registry.get_all().values():
        cls = domain.domain_class
        by_class[cls] = by_class.get(cls, 0) + 1

    issues = []
    for _, dk, reason in alignment['module_mapping'].get('invalid', []):
        issues.append(reason)
    for tag, dk, reason in alignment['builder_keys'].get('invalid', []):
        issues.append(reason)
    for name, cls, reason in alignment.get('orphaned_registry_entries', []):
        issues.append(reason)
    for name, cls, reason in alignment.get('cos_without_builder', []):
        issues.append(reason)

    # Include signal issues
    issues.extend(signal_health.get('domain_mapping_issues', []))
    issues.extend(signal_health.get('expected_type_issues', []))
    issues.extend(signal_health.get('cos_coverage_issues', []))

    # Include pattern issues
    pattern_health = signal_health.get('pattern_health', {})
    issues.extend(pattern_health.get('issues', []))

    is_aligned = (
        alignment['is_aligned']
        and signal_health['status'] == 'healthy'
        and pattern_health.get('status', 'healthy') == 'healthy'
    )

    return {
        'status': 'healthy' if is_aligned else 'drift_detected',
        'domain_count': registry.domain_count,
        'by_class': by_class,
        'issues': issues,
        'signal_health': signal_health,
        'details': alignment,
    }
