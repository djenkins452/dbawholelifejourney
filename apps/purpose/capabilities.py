from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability

registry.register(DomainCapability(
    name='purpose',
    display_name='Goals & Purpose',
    description='Goals, habits, intentions, and life purpose tracking',
    intent_types=['create_goal', 'update_goal_progress', 'set_intention', 'log_habit'],
    primary_models=['Goal', 'HabitEntry', 'Intention'],
    context_builders=['_build_plan_and_alignment', '_build_purpose_context'],
    proactive_signals=['goal_deadline_approaching', 'habit_streak_break', 'intention_unchecked'],
    related_domains=['life', 'journal', 'health'],
    feature_flag='features.purpose.enabled',
    url_namespace='purpose',
))
