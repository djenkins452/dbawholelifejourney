from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability

registry.register(DomainCapability(
    name='health',
    display_name='Health & Vitals',
    description='Track vital signs, body measurements, food, sleep, water, and steps',
    intent_types=[
        'log_heart_rate', 'log_blood_pressure', 'log_weight', 'log_glucose',
        'log_blood_oxygen', 'log_food', 'log_sleep', 'log_water', 'log_steps',
        'log_body_measurement',
    ],
    primary_models=[
        'HeartRateEntry', 'BloodPressureEntry', 'WeightEntry', 'GlucoseEntry',
        'BloodOxygenEntry', 'FoodEntry', 'SleepEntry', 'WaterEntry', 'StepsEntry',
        'BodyMeasurement',
    ],
    context_builders=['_build_health_and_vitals'],
    proactive_signals=[
        'vitals_anomaly', 'weight_trend_change', 'sleep_deficit',
        'hydration_low', 'glucose_spike',
    ],
    related_domains=['fitness', 'meals', 'medical', 'goals'],
    feature_flag='features.health.enabled',
    url_namespace='health',
))
