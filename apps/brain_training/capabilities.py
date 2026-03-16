from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability

registry.register(DomainCapability(
    name='brain_training',
    display_name='Brain Training',
    description='Cognitive exercises and mental fitness tracking',
    intent_types=[],
    primary_models=['TrainingSession', 'TrainingScore'],
    context_builders=['_build_brain_training_context'],
    proactive_signals=['training_streak_break'],
    expected_signal_types=['cognitive_fitness'],
    related_domains=['health'],
    url_namespace='brain_training',
))
