"""
Legacy domain capability registration.

Registered with the WLJ Domain Registry at startup via autodiscover().
Legacy is a PRESERVATION-class domain: append-only / testimonial / conflict-
preserving / multi-contributor / designed to outlive its owner.

Phase 1 is standalone and non-Beth, so this descriptor declares NO
context_builders / proactive_signals / expected_signal_types yet — those are
added when the assistant becomes a Legacy consumer in a later phase.
"""

from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability, DomainClass

registry.register(DomainCapability(
    name='legacy',
    display_name='Legacy',
    description='Personal Legacy Operating System — preserve people, stories, '
                'places, and media so future generations can truly know someone.',
    domain_class=DomainClass.PRESERVATION,
    intent_types=[],          # No CoS actions in Phase 1 (standalone / non-Beth)
    primary_models=[
        'Memory', 'Person', 'Place', 'Media',
        'Relationship', 'Contributor', 'Output',
    ],
    context_builders=[],      # Assistant seam — added when Beth consumes Legacy
    proactive_signals=[],     # Assistant seam
    expected_signal_types=[],  # Preservation domain emits standing state, not daily signals
    related_domains=['relationships', 'journal', 'faith', 'capture'],
    feature_flag='features.legacy.enabled',
    url_namespace='legacy',
))
