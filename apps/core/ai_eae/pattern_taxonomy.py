# ==============================================================================
# File: apps/core/ai_eae/pattern_taxonomy.py
# Description: Phase 5 — Cross-Domain Pattern Taxonomy
#
# Defines the catalog of derived pattern signal types. Each pattern is computed
# from combinations of base signal types and stored as a SignalSnapshot with
# signal_class='derived_pattern'.
#
# Domain mappings live in SIGNAL_TYPE_DOMAIN (signal_aggregation.py) to preserve
# the single canonical taxonomy. This file holds pattern metadata only.
# ==============================================================================
"""
Phase 5 — Cross-Domain Pattern Taxonomy.

Pattern signal types are registered in SIGNAL_TYPE_DOMAIN alongside base signal
types. This file defines the pattern catalog metadata: descriptions, source
signals, and governance constants.

Pattern types MUST NOT collide with base signal taxonomy keys.
All names must fit within signal_type max_length (30 chars).
"""

# Confidence discount — derived patterns are inherently less certain than
# their source signals. All pattern confidences are multiplied by this factor.
PATTERN_CONFIDENCE_DISCOUNT = 0.85

# Pattern type catalog: pattern_type -> metadata
# Domain mappings are in SIGNAL_TYPE_DOMAIN, not here.
PATTERN_TYPE_CATALOG = {
    'recovery_risk': {
        'display_name': 'Recovery Risk',
        'description': (
            'High activity with poor biometrics (especially sleep) — '
            'overtraining without adequate recovery'
        ),
        'source_signals': ['health_activity', 'health_biometrics'],
    },
    'holistic_momentum': {
        'display_name': 'Holistic Momentum',
        'description': (
            '3+ signal types scoring well across 2+ domains — '
            'positive multi-area life momentum'
        ),
        'source_signals': ['*'],  # any 3+ above threshold
    },
    'domain_neglect': {
        'display_name': 'Domain Neglect',
        'description': (
            'A domain with 2+ signal types ALL declining over 7 days — '
            'systematic neglect of a life area'
        ),
        'source_signals': ['*'],  # any domain with 2+ declining
    },
    'compliance_drift': {
        'display_name': 'Compliance Drift',
        'description': (
            'Medication adherence declining alongside biometrics — '
            'medical compliance risk emerging'
        ),
        'source_signals': ['medication_adherence', 'health_biometrics'],
    },
    'wellbeing_convergence': {
        'display_name': 'Wellbeing Convergence',
        'description': (
            'Mental reflection, relational engagement, and faith practice '
            'all performing — emotional/spiritual wellbeing convergence'
        ),
        'source_signals': ['mental_reflection', 'relational_engagement', 'faith_practice'],
    },
}

# Flat set for quick membership checks
PATTERN_TYPES = set(PATTERN_TYPE_CATALOG.keys())

# Base signal types (Phase 4) — used to distinguish patterns from base signals
BASE_SIGNAL_TYPES = {
    'health_activity', 'health_biometrics', 'medication_adherence',
    'nutrition_compliance', 'faith_practice', 'mental_reflection',
    'cognitive_fitness', 'productivity_progress', 'financial_health',
    'relational_engagement',
    # Emotion-derived (deterministic from structured journal emotion selections)
    'emotional_stress', 'emotional_low_mood', 'emotional_positive',
}
