from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability

registry.register(DomainCapability(
    name='capture',
    display_name='Capture',
    description='Quick capture of thoughts, ideas, and items for later processing',
    intent_types=[],
    primary_models=['CaptureEntry'],
    context_builders=['_build_capture_context'],
    proactive_signals=['unprocessed_captures'],
    related_domains=['life', 'journal'],
    url_namespace='capture',
))
