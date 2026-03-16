from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability

registry.register(DomainCapability(
    name='relationships',
    display_name='People & Relationships',
    description='Track connections, interactions, and meaningful relationships',
    intent_types=[],
    primary_models=['Person', 'PersonGroup', 'RelationshipInteraction', 'Mention'],
    context_builders=['_build_people_and_mood'],
    proactive_signals=['relationship_gap', 'birthday_approaching'],
    expected_signal_types=['relational_engagement'],
    related_domains=['journal', 'life'],
    feature_flag='features.relationships.enabled',
    url_namespace='relationships',
))
