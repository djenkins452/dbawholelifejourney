from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability

registry.register(DomainCapability(
    name='meals',
    display_name='Meals & Nutrition',
    description='Meal planning, recipes, pantry management, and nutrition tracking',
    intent_types=[],
    primary_models=['MealEntry', 'Recipe', 'PantryItem'],
    context_builders=[],
    proactive_signals=['nutrition_gap', 'meal_plan_deviation'],
    related_domains=['health', 'goals'],
    url_namespace='meals',
))
