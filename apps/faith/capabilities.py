from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability

registry.register(DomainCapability(
    name='faith',
    display_name='Faith & Spiritual',
    description='Prayer tracking, Bible reading, verse saving, and faith milestones',
    intent_types=['log_prayer', 'mark_prayer_answered', 'save_verse', 'add_faith_milestone'],
    primary_models=['PrayerEntry', 'SavedVerse', 'FaithMilestone', 'ReadingPlan'],
    context_builders=['_build_faith_context'],
    proactive_signals=['reading_streak_break', 'prayer_rhythm_gap'],
    related_domains=['journal', 'goals'],
    feature_flag='features.faith.enabled',
    url_namespace='faith',
))
