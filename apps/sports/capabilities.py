"""Sports Domain — Domain registry descriptor."""
from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability, DomainClass

registry.register(DomainCapability(
    name='sports',
    display_name='Sports',
    description='Track followed teams, game events, and generate contextual signals',
    domain_class=DomainClass.CONTEXT,
    intent_types=[],  # Read-only context domain — no AI intents
    primary_models=['Sport', 'League', 'Team', 'GameEvent', 'UserTeamFollow'],
    context_builders=['_build_sports_context'],
    proactive_signals=['game_starting_soon', 'game_completed'],
    expected_signal_types=['sports_event'],
    related_domains=['life', 'relationships'],
    feature_flag='features.sports.enabled',
    url_namespace='sports',
))
