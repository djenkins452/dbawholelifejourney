from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability, DomainClass

registry.register(DomainCapability(
    name='capture',
    display_name='Capture',
    description='Cross-domain ingestion system for quick voice and text capture',
    domain_class=DomainClass.INFLUENCE,
    intent_types=[],
    primary_models=['CaptureEntry'],
    context_builders=['_build_capture_context'],
    proactive_signals=['unprocessed_captures'],
    related_domains=['life', 'journal'],
    url_namespace='capture',
))
