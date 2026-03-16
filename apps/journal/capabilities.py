from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability

registry.register(DomainCapability(
    name='journal',
    display_name='Journal',
    description='Personal journaling with mood tracking, emotions, and gratitude',
    intent_types=['create_journal_entry', 'add_gratitude'],
    primary_models=['JournalEntry', 'GratitudeEntry'],
    context_builders=['_build_people_and_mood'],
    proactive_signals=['journal_gap', 'concern_recurring', 'mood_declining'],
    expected_signal_types=['mental_reflection'],
    related_domains=['goals', 'faith', 'health'],
    feature_flag='features.journal.enabled',
    url_namespace='journal',
))
