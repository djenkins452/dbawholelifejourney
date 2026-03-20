from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability, DomainClass

# The 'emotional' domain represents emotion-derived signal types produced
# deterministically from structured journal emotion selections (not NLP).
# These signals are created by the journal blending pipeline
# (_blend_journal_signals) rather than individual signal computers.
registry.register(DomainCapability(
    name='emotional',
    display_name='Emotional State',
    description='Emotion-derived signals from structured journal emotion selections',
    domain_class=DomainClass.BEHAVIORAL,
    intent_types=[],
    primary_models=[],
    context_builders=[],
    proactive_signals=['emotional_distress', 'mood_shift'],
    expected_signal_types=[
        'emotional_stress', 'emotional_low_mood', 'emotional_positive',
    ],
    related_domains=['journal', 'health'],
))
