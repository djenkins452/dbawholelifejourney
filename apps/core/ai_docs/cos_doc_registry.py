"""
Whole Life Journey — CoS Documentation Registry

Project: Whole Life Journey
Path: apps/core/ai_docs/cos_doc_registry.py
Purpose: Structured metadata registry for CoS components, validated against code

Description:
    Defines every CoS component with references to the actual code that
    implements it. The registry is validated at generation time — if a
    referenced module, function, or model field does not exist, the
    generator raises an error instead of producing stale docs.

Public API:
    - get_cos_registry() -> list[dict]
    - validate_registry() -> tuple[bool, list[str]]

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import importlib
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# ENGINE DEPENDENCY MAP
# =============================================================================

ENGINE_DEPENDENCIES = {
    'blueprint_engine': {
        'module': 'apps.core.blueprint.engine',
        'functions': [
            'get_blueprint', 'update_blueprint', 'sync_flags',
            'explain_blueprint', 'is_behavior_reference_allowed',
            'get_enabled_drift_types', 'get_non_negotiables_for_date',
        ],
    },
    'priority_engine': {
        'module': 'apps.core.blueprint.priority_engine',
        'functions': [
            'resolve_conflict', 'compute_identity_cost',
            'get_tier_for_block', 'prioritize_blocks',
        ],
    },
    'architecture_engine': {
        'module': 'apps.core.blueprint.architecture_engine',
        'functions': [
            'run_architecture_pass', 'handle_curveball', 'get_todays_plan',
        ],
    },
    'drift_engine': {
        'module': 'apps.core.blueprint.drift_engine',
        'functions': [
            'record_drift_event', 'compute_daily_drift_score',
            'predict_drift_probability', 'get_drift_summary',
        ],
    },
    'intervention_engine': {
        'module': 'apps.core.blueprint.intervention_engine',
        'functions': [
            'determine_escalation_level', 'create_intervention',
            'create_friction_gate', 'get_pending_interventions',
            'record_intervention_response',
        ],
    },
    'assistant_triggers': {
        'module': 'apps.core.blueprint.assistant_triggers',
        'functions': [
            'check_triggers', 'execute_trigger', 'execute_all_triggers',
        ],
    },
    # Upstream intelligence engines referenced by CoS
    'ai_orchestrator': {
        'module': 'apps.core.ai_orchestrator.orchestrator',
        'functions': ['process_user_input'],
    },
    'ai_state': {
        'module': 'apps.core.ai_state.state_engine',
        'functions': ['get_user_state'],
    },
    'ai_insights': {
        'module': 'apps.core.ai_insights.insight_engine',
        'functions': ['run_insights'],
    },
    'ai_predictions': {
        'module': 'apps.core.ai_predictions.prediction_engine',
        'functions': ['generate_predictions'],
    },
    'ai_guidance': {
        'module': 'apps.core.ai_guidance.guidance_engine',
        'functions': ['generate_guidance'],
    },
    'ai_guidance_learning': {
        'module': 'apps.core.ai_guidance_learning.learning_engine',
        'functions': ['update_learning_profile'],
    },
    'ai_briefing': {
        'module': 'apps.core.ai_briefing.briefing_engine',
        'functions': ['generate_daily_briefing'],
    },
    'ai_scheduler': {
        'module': 'apps.core.ai_scheduler.scheduler_registry',
        'functions': ['get_registered_tasks'],
    },
    'ai_explain': {
        'module': 'apps.core.ai_explain.explain_engine',
        'functions': ['ensure_explain_record'],
    },
    'ai_delivery': {
        'module': 'apps.core.ai_delivery.delivery_engine',
        'functions': ['deliver_due_notifications'],
    },
    'persona_engine': {
        'module': 'apps.core.ai_persona.persona_engine',
        'functions': ['render_with_persona'],
    },
}


# =============================================================================
# MODEL FIELD REGISTRY
# =============================================================================

BLUEPRINT_MODEL_FIELDS = {
    'PersonalOperatingBlueprint': {
        'module': 'apps.core.blueprint.models',
        'expected_fields': [
            'operating_style', 'persona_id', 'interruption_tolerance',
            'auto_architect_enabled', 'tier1_protected_behaviors',
            'pillars_ranked', 'sleep_target_minutes', 'wake_time_policy',
            'preferred_architecture_time', 'override_policy',
            'module_flags_snapshot', 'sub_feature_flags_snapshot',
            'last_architecture_run_at', 'version',
        ],
    },
    'NonNegotiable': {
        'module': 'apps.core.blueprint.models',
        'expected_fields': [
            'behavior_key', 'display_name', 'pillar',
            'min_duration_minutes', 'preferred_time_window_start',
            'preferred_time_window_end', 'frequency', 'custom_days',
            'hard_deadline', 'module_key', 'feature_key',
            'is_active', 'sort_order',
        ],
    },
    'ArchitecturePlan': {
        'module': 'apps.core.blueprint.models',
        'expected_fields': [
            'date', 'status', 'recommended_wake_time',
            'recommended_sleep_time', 'risk_warnings',
            'identity_cost_summary', 'suggested_moves',
            'generation_trigger', 'curveball_description',
            'evidence_summary',
        ],
    },
    'ScheduledBlock': {
        'module': 'apps.core.blueprint.models',
        'expected_fields': [
            'start_time', 'end_time', 'title', 'description',
            'tier', 'source', 'source_id', 'is_locked',
            'rationale', 'behavior_key', 'is_completed', 'completed_at',
        ],
    },
    'DriftEvent': {
        'module': 'apps.core.blueprint.models',
        'expected_fields': [
            'drift_type', 'date', 'occurred_at', 'behavior_key',
            'tier', 'pillar', 'severity', 'description', 'evidence',
            'is_acknowledged', 'acknowledged_at', 'recovery_plan',
        ],
    },
    'DriftScore': {
        'module': 'apps.core.blueprint.models',
        'expected_fields': [
            'date', 'score', 'pillar_scores', 'event_count',
            'drift_probability_24h', 'drift_probability_72h',
            'prediction_factors',
        ],
    },
    'InterventionLog': {
        'module': 'apps.core.blueprint.models',
        'expected_fields': [
            'level', 'trigger_type', 'behavior_key', 'message',
            'evidence', 'user_response', 'responded_at', 'delivered_via',
        ],
    },
}


# =============================================================================
# COS COMPONENT REGISTRY
# =============================================================================

def get_cos_registry():
    """
    Return the structured metadata registry for all CoS components.

    Each entry describes a CoS subsystem with references to the actual
    code that implements it. These references are validated before
    documentation is generated.

    Returns:
        list[dict] — Component definitions with metadata.
    """
    return [
        {
            'key': 'personal_operating_blueprint',
            'name': 'Personal Operating Blueprint',
            'description': (
                'The foundational configuration layer that defines how the '
                'assistant operates for each user. Stores identity-protected '
                'behaviors, life pillar rankings, operating style preferences, '
                'and module integration flags.'
            ),
            'engines': ['blueprint_engine'],
            'models': ['PersonalOperatingBlueprint', 'NonNegotiable'],
            'tier_rules': {
                'source': 'priority_engine',
                'function': 'get_tier_for_block',
                'tiers': {
                    1: 'Identity Protected — behaviors central to who the user is',
                    2: 'Directional Commitment — important but movable behaviors',
                    3: 'Administrative — calendar events, tasks, logistics',
                    4: 'Optional — buffer time, flexible activities',
                },
            },
            'configuration_fields': [
                'operating_style', 'interruption_tolerance',
                'auto_architect_enabled', 'tier1_protected_behaviors',
                'pillars_ranked', 'sleep_target_minutes',
                'wake_time_policy', 'override_policy',
            ],
            'guardrails': [
                'Module flags snapshot prevents referencing disabled modules',
                'Behavior key validation via is_behavior_reference_allowed()',
                'Feature flag gating on non-negotiables',
            ],
        },
        {
            'key': 'tier_system',
            'name': 'Tier System & Priority Rules',
            'description': (
                'A four-tier priority hierarchy that governs how schedule '
                'conflicts are resolved. Tier 1 behaviors are identity-protected '
                'and are only displaced as an absolute last resort.'
            ),
            'engines': ['priority_engine', 'blueprint_engine'],
            'models': ['ScheduledBlock'],
            'tier_rules': {
                'conflict_resolution_order': 'Tier 4 → Tier 3 → Tier 2 → Tier 1',
                'rule_b': (
                    'Tier 1 is touched ONLY if all lower-tier blocks have been '
                    'exhausted. If Tier 1 is impacted, an identity cost is '
                    'computed and a recovery plan is attached.'
                ),
            },
            'identity_cost': {
                'source': 'priority_engine',
                'function': 'compute_identity_cost',
                'formula_description': (
                    'Weighted composite of pillar importance (40%), '
                    'recent frequency of violations (30%), and '
                    'current drift probability (30%). Yields a score from 0 to 100.'
                ),
            },
            'guardrails': [
                'Tier 1 blocks auto-locked by architecture engine',
                'Friction gate required before Tier 1 override',
                'Recovery plan generated for any Tier 1 displacement',
            ],
        },
        {
            'key': 'daily_architecture',
            'name': 'Daily Architecture Mode',
            'description': (
                'The nightly planning engine that builds tomorrow\'s schedule. '
                'Assembles sleep blocks, non-negotiables, calendar events, and '
                'tasks into a prioritized daily plan with risk warnings.'
            ),
            'engines': ['architecture_engine', 'priority_engine', 'blueprint_engine'],
            'models': ['ArchitecturePlan', 'ScheduledBlock'],
            'scheduling': {
                'source': 'ai_scheduler',
                'task_name': 'run_architecture_pass',
                'interval': '24 hours (nightly)',
            },
            'plan_lifecycle': [
                'Draft — newly generated',
                'Active — currently governing the day',
                'Superseded — replaced by a newer plan (curveball)',
                'Completed — day is finished',
            ],
            'risk_warnings': [
                'Schedule density exceeds 85% of waking hours',
                'No Tier 1 blocks scheduled for the day',
                'Sleep block missing or below target duration',
            ],
            'guardrails': [
                'Only runs if auto_architect_enabled is True in blueprint',
                'Tier 1 blocks are automatically locked',
                'Identity cost summary computed for Tier 1 and Tier 2 blocks',
            ],
        },
        {
            'key': 'curveball_protocol',
            'name': 'Curveball Protocol',
            'description': (
                'Real-time re-optimization when an unexpected event disrupts '
                'the daily plan. Inserts the new event and resolves conflicts '
                'using the tier hierarchy.'
            ),
            'engines': ['architecture_engine', 'priority_engine'],
            'models': ['ArchitecturePlan', 'ScheduledBlock'],
            'behavior': {
                'curveball_tier': 2,
                'curveball_locked': True,
                'resolution': (
                    'Conflict resolution follows Rule B: lower-tier blocks '
                    'are displaced first. If Tier 1 is impacted, full evidence '
                    'and recovery plan are generated.'
                ),
            },
            'guardrails': [
                'Completed blocks are preserved (cannot be displaced)',
                'Curveball block is locked to prevent displacement',
                'Previous plan is superseded (not deleted) for audit trail',
            ],
        },
        {
            'key': 'drift_detection',
            'name': 'Drift Detection & Scoring',
            'description': (
                'Monitors deviations from committed behaviors and computes '
                'a daily aggregate drift score. Each drift event is weighted '
                'by tier importance and pillar significance.'
            ),
            'engines': ['drift_engine', 'blueprint_engine'],
            'models': ['DriftEvent', 'DriftScore'],
            'drift_types': {
                'source': 'drift_engine',
                'types': [
                    'Broke fast early',
                    'Medication missed',
                    'Workout skipped',
                    'Nutrition off track',
                    'Faith block missed',
                    'Goal progress slip',
                    'Sleep deficit',
                    'Scheduled block missed',
                ],
            },
            'scoring': {
                'formula_description': (
                    'Each event contributes: severity × pillar weight × '
                    'tier multiplier × 10. Tier multipliers: Tier 1 = 3×, '
                    'Tier 2 = 2×, Tier 3 = 1.5×, Tier 4 = 1×. '
                    'Daily score aggregated per pillar, normalized to 0–100.'
                ),
            },
            'scheduling': {
                'source': 'ai_scheduler',
                'task_name': 'run_drift_scoring',
                'interval': '6 hours',
            },
            'guardrails': [
                'Drift types filtered by enabled modules — disabled module drifts are suppressed',
                'Tier 1 drift events trigger immediate PIE insight generation',
                'Module gating prevents mentioning disabled features',
            ],
        },
        {
            'key': 'predictive_modeling',
            'name': 'Predictive Drift Modeling',
            'description': (
                'Forecasts the probability of drift in the next 24 and 72 hours '
                'using a multi-factor heuristic model.'
            ),
            'engines': ['drift_engine'],
            'models': ['DriftScore'],
            'prediction_factors': {
                'recent_drift_trend': '35% weight — average drift score over past 7 days',
                'schedule_density': '25% weight — how packed the next day\'s schedule is',
                'streak_fatigue': '20% weight — risk increases after 14+ clean days',
                'weekend_effect': '20% weight — elevated risk on Friday through Sunday',
            },
            'thresholds': {
                'spike_trigger': 'Predicted 24-hour probability ≥ 70%',
                '72h_multiplier': '72-hour probability = 24-hour × 1.3',
            },
            'guardrails': [
                'Clean streak detection (score below 20) for fatigue modeling',
                'Predictions are advisory — they inform interventions but never execute actions',
            ],
        },
        {
            'key': 'intelligent_friction',
            'name': 'Intelligent Friction & Interventions',
            'description': (
                'A five-level escalation system that determines how the assistant '
                'communicates urgency. Respects the user\'s interruption tolerance '
                'and adapts escalation based on tier and severity.'
            ),
            'engines': ['intervention_engine', 'persona_engine'],
            'models': ['InterventionLog'],
            'escalation_levels': {
                0: 'Silent — logged but not displayed to user',
                1: 'Nudge — subtle panel line or badge',
                2: 'Ping — assistant opens conversation',
                3: 'Interrupt — in-app modal or push notification',
                4: 'Friction Gate — confirmation required with evidence',
            },
            'tolerance_adjustment': {
                'low': 'Reduces escalation by 1 level (except friction gates)',
                'medium': 'No adjustment (default)',
                'high': 'Increases escalation by 1 level (capped below friction gate)',
            },
            'friction_gate': {
                'trigger': 'Any attempt to override a Tier 1 behavior',
                'contents': [
                    'Description of what the user is about to do',
                    'Which identity-protected behavior is impacted',
                    'Projected adherence drop',
                    'Consequence description',
                    'Identity cost score (0–100)',
                ],
                'response_options': [
                    'Proceed anyway — override acknowledged',
                    'Accept suggestion — follow assistant recommendation',
                    'Adjust plan — modify the schedule instead',
                ],
            },
            'guardrails': [
                'Tier 1 forces friction gate minimum (level 4)',
                'Severity ≥ 80% escalates to Interrupt minimum',
                'Messages rendered through persona engine for tone',
                'Friction gate overrides logged for GLOE learning',
            ],
        },
        {
            'key': 'recovery_plan',
            'name': 'Recovery Plan System',
            'description': (
                'When a Tier 1 behavior is displaced or missed, the system '
                'generates a recovery plan with specific compensating actions.'
            ),
            'engines': ['priority_engine', 'intervention_engine'],
            'models': ['DriftEvent'],
            'behavior': {
                'trigger': 'Tier 1 displacement during conflict resolution or curveball',
                'output': (
                    'Behavior-specific recovery suggestion (e.g., reschedule workout, '
                    'take medication as soon as possible, adjust fasting window).'
                ),
            },
            'guardrails': [
                'Recovery plans are suggestions — never auto-executed',
                'Attached to E3 evidence for explainability',
                'Persona rendering applies to recovery plan text',
            ],
        },
        {
            'key': 'delivery_notification',
            'name': 'Delivery & Notification',
            'description': (
                'Routes CoS interventions through the Delivery & Notification '
                'Engine for multi-channel delivery. Respects quiet hours, '
                'consent settings, and throttling policies.'
            ),
            'engines': ['intervention_engine', 'ai_delivery', 'assistant_triggers'],
            'models': ['InterventionLog'],
            'trigger_conditions': [
                'Approaching non-negotiable deadline (within 1 hour)',
                'High drift probability spike (≥ 70%)',
                'Nightly architecture summary ready',
                'User idle during scheduled focus block (≥ 30 minutes)',
            ],
            'deduplication': {
                'window': '4 hours — identical trigger types are suppressed',
            },
            'scheduling': {
                'source': 'ai_scheduler',
                'task_name': 'run_assistant_triggers',
                'interval': '15 minutes',
            },
            'guardrails': [
                'Triggers only run if auto_architect_enabled',
                'DNE delivery only for escalation level ≥ 2 (Ping or higher)',
                'Deduplication prevents notification spam',
                'Quiet hours and consent enforced by DNE',
            ],
        },
        {
            'key': 'alignment_index',
            'name': 'Alignment Index',
            'description': (
                'A composite daily measure of how well the user\'s actual '
                'behavior aligns with their stated blueprint commitments. '
                'Derived from the inverse of the drift score.'
            ),
            'engines': ['drift_engine', 'blueprint_engine'],
            'models': ['DriftScore'],
            'calculation': {
                'formula_description': (
                    'Alignment = 100 − Drift Score. A drift score of 0 '
                    'means 100% alignment. Per-pillar alignment is also '
                    'available from pillar-level drift scores.'
                ),
            },
            'guardrails': [
                'Only considers enabled modules in calculation',
                'Missing data defaults to neutral (no penalty)',
            ],
        },
        {
            'key': 'observability',
            'name': 'Observability & Logging',
            'description': (
                'Every CoS decision is logged for transparency and review. '
                'Architecture plans, drift events, interventions, and trigger '
                'checks produce audit records viewable in the admin console.'
            ),
            'engines': [
                'architecture_engine', 'drift_engine',
                'intervention_engine', 'assistant_triggers', 'ai_explain',
            ],
            'models': [
                'ArchitecturePlan', 'DriftEvent', 'DriftScore', 'InterventionLog',
            ],
            'evidence': {
                'source': 'ai_explain',
                'description': (
                    'The Evidence & Explainability Engine (E3) attaches '
                    'evidence records to architecture plans and friction gates, '
                    'enabling full transparency into why decisions were made.'
                ),
            },
            'guardrails': [
                'Superseded plans are preserved for audit trail',
                'Intervention responses (accepted, dismissed, proceeded) are tracked',
                'E3 evidence linked to all Tier 1 impact decisions',
            ],
        },
    ]


# =============================================================================
# VALIDATION
# =============================================================================

def validate_registry():
    """
    Validate that all registry references exist in actual code.

    Checks:
        - All engine modules are importable
        - All registered functions exist
        - All model classes exist with expected fields

    Returns:
        tuple[bool, list[str]] — (is_valid, list of error messages)
    """
    errors = []

    # Validate engine dependencies
    for engine_key, engine_def in ENGINE_DEPENDENCIES.items():
        module_path = engine_def['module']
        try:
            mod = importlib.import_module(module_path)
            for func_name in engine_def['functions']:
                if not hasattr(mod, func_name):
                    errors.append(
                        f"Engine '{engine_key}': function '{func_name}' "
                        f"not found in {module_path}"
                    )
        except ImportError as e:
            errors.append(
                f"Engine '{engine_key}': cannot import {module_path} — {e}"
            )

    # Validate model fields
    for model_name, model_def in BLUEPRINT_MODEL_FIELDS.items():
        module_path = model_def['module']
        try:
            mod = importlib.import_module(module_path)
            model_class = getattr(mod, model_name, None)
            if model_class is None:
                errors.append(f"Model '{model_name}' not found in {module_path}")
                continue

            # Check fields exist on the model
            model_fields = {f.name for f in model_class._meta.get_fields()}
            for field_name in model_def['expected_fields']:
                if field_name not in model_fields:
                    errors.append(
                        f"Model '{model_name}': field '{field_name}' not found"
                    )
        except ImportError as e:
            errors.append(f"Model module '{module_path}': import failed — {e}")

    is_valid = len(errors) == 0
    if not is_valid:
        for err in errors:
            logger.error("CoS registry validation: %s", err)

    return is_valid, errors
