"""
Whole Life Journey - Blueprint Engine

Project: Whole Life Journey
Path: apps/core/blueprint/engine.py
Purpose: Core service for reading/updating the Personal Operating Blueprint

Description:
    Provides the central API that all intelligence engines use to consult the
    blueprint. Handles blueprint creation, updates, module flag syncing, and
    the "explain" transparency view.

Public API:
    - get_blueprint(user) -> PersonalOperatingBlueprint
    - update_blueprint(user, data) -> PersonalOperatingBlueprint
    - sync_flags(user) -> None
    - explain_blueprint(user) -> dict
    - is_behavior_reference_allowed(user, behavior_key) -> bool

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

from .models import PersonalOperatingBlueprint, NonNegotiable

logger = logging.getLogger(__name__)


# =============================================================================
# PUBLIC API
# =============================================================================


def get_blueprint(user):
    """
    Get the blueprint for a user, creating one if it doesn't exist.
    This is the primary entry point for all engines.
    """
    return PersonalOperatingBlueprint.get_or_create_for_user(user)


def update_blueprint(user, data):
    """
    Update the blueprint with provided data dict.
    Only updates fields that are present in the data.

    Args:
        user: The user
        data: Dict of fields to update. Supported keys:
            - operating_style
            - persona_id
            - interruption_tolerance
            - auto_architect_enabled
            - tier1_protected_behaviors
            - pillars_ranked
            - sleep_target_minutes
            - wake_time_policy
            - preferred_architecture_time
            - override_policy

    Returns:
        Updated PersonalOperatingBlueprint
    """
    blueprint = get_blueprint(user)

    updatable_fields = [
        'operating_style', 'persona_id', 'interruption_tolerance',
        'auto_architect_enabled', 'tier1_protected_behaviors', 'pillars_ranked',
        'sleep_target_minutes', 'wake_time_policy', 'preferred_architecture_time',
        'override_policy',
    ]

    changed_fields = []
    for field in updatable_fields:
        if field in data:
            setattr(blueprint, field, data[field])
            changed_fields.append(field)

    if changed_fields:
        blueprint.version += 1
        changed_fields.append('version')
        changed_fields.append('updated_at')
        blueprint.save(update_fields=changed_fields)
        logger.info(
            "Blueprint updated for %s: fields=%s, version=%d",
            user.email, changed_fields, blueprint.version,
        )

    return blueprint


def sync_flags(user):
    """
    Sync the blueprint's module/feature flag snapshots from user preferences.
    Should be called when preferences change.
    """
    blueprint = get_blueprint(user)
    blueprint.sync_module_flags()
    blueprint.save(update_fields=[
        'module_flags_snapshot', 'sub_feature_flags_snapshot', 'updated_at',
    ])
    logger.info("Blueprint flags synced for %s", user.email)


def explain_blueprint(user):
    """
    Generate a transparency explanation of what's driving the user's guidance.
    Returns a dict suitable for rendering to the user.
    """
    blueprint = get_blueprint(user)
    non_negotiables = list(
        blueprint.non_negotiables.filter(is_active=True)
        .values('behavior_key', 'display_name', 'pillar', 'frequency', 'min_duration_minutes')
    )

    # Build tier map
    tier_map = {}
    for nn in non_negotiables:
        bk = nn['behavior_key']
        tier = blueprint.get_tier_for_behavior(bk)
        tier_map[bk] = tier

    # Build pillar weights
    pillar_weights = {}
    for pillar in (blueprint.pillars_ranked or []):
        pillar_weights[pillar] = blueprint.get_pillar_weight(pillar)

    # Enabled modules
    enabled_modules = {
        k: v for k, v in (blueprint.module_flags_snapshot or {}).items() if v
    }

    return {
        'operating_style': blueprint.get_operating_style_display(),
        'interruption_tolerance': blueprint.get_interruption_tolerance_display(),
        'auto_architect_enabled': blueprint.auto_architect_enabled,
        'wake_time_policy': blueprint.get_wake_time_policy_display(),
        'override_policy': blueprint.get_override_policy_display(),
        'sleep_target_hours': round(blueprint.sleep_target_minutes / 60, 1),
        'pillars_ranked': blueprint.pillars_ranked or [],
        'pillar_weights': pillar_weights,
        'tier1_protected': blueprint.tier1_protected_behaviors or [],
        'non_negotiables': non_negotiables,
        'tier_assignments': tier_map,
        'enabled_modules': enabled_modules,
        'version': blueprint.version,
        'last_architecture_run': blueprint.last_architecture_run_at,
    }


def is_behavior_reference_allowed(user, behavior_key):
    """
    Check if the assistant is allowed to reference a behavior.
    Behaviors tied to disabled modules/features must not be referenced.

    This is the guardrail that prevents the assistant from mentioning
    disabled modules.
    """
    blueprint = get_blueprint(user)

    # Map behavior keys to module/feature requirements
    behavior_module_map = {
        'FAITH_BLOCK': ('faith', None),
        'SCRIPTURE_READING': ('faith', 'faith.scripture'),
        'PRAYER': ('faith', 'faith.prayers'),
        'MEDS_ADHERENCE': ('health', None),
        'WORKOUT': ('health', 'health.fitness'),
        'NUTRITION': ('health', None),
        'FASTING': ('health', 'health.fasting'),
        'WEIGHT_LOG': ('health', 'health.weight'),
        'SLEEP': ('health', None),
        'GOAL_EXECUTION': ('purpose', None),
        'HABIT_TRACKING': ('purpose', 'purpose.habits'),
        'JOURNAL_REFLECTION': ('journal', None),
        'TASK_COMPLETION': ('life', 'life.tasks'),
        'FINANCE_REVIEW': ('finance', None),
    }

    module_feature = behavior_module_map.get(behavior_key)
    if module_feature is None:
        return True  # Unknown behaviors are allowed by default

    module_key, feature_key = module_feature
    if module_key and not blueprint.is_module_enabled(module_key):
        return False
    if feature_key and not blueprint.is_feature_enabled(feature_key):
        return False

    return True


def get_enabled_drift_types(user):
    """
    Return only drift event types that correspond to enabled modules/features.
    The assistant must never reference drift for disabled modules.
    """
    from .models import DriftEvent

    blueprint = get_blueprint(user)
    all_drift_types = dict(DriftEvent.DRIFT_TYPE_CHOICES)

    drift_module_map = {
        DriftEvent.DRIFT_FAST_BREAK_EARLY: ('health', 'health.fasting'),
        DriftEvent.DRIFT_MED_MISSED: ('health', None),
        DriftEvent.DRIFT_WORKOUT_SKIPPED: ('health', 'health.fitness'),
        DriftEvent.DRIFT_NUTRITION_OFF_TRACK: ('health', None),
        DriftEvent.DRIFT_FAITH_BLOCK_MISSED: ('faith', None),
        DriftEvent.DRIFT_GOAL_SLIP: ('purpose', None),
        DriftEvent.DRIFT_SLEEP_DEFICIT: ('health', None),
        DriftEvent.DRIFT_BLOCK_MISSED: (None, None),  # Always enabled
    }

    enabled = {}
    for drift_type, (module_key, feature_key) in drift_module_map.items():
        if module_key and not blueprint.is_module_enabled(module_key):
            continue
        if feature_key and not blueprint.is_feature_enabled(feature_key):
            continue
        enabled[drift_type] = all_drift_types[drift_type]

    return enabled


def get_non_negotiables_for_date(user, date=None):
    """
    Get active non-negotiables that apply to a given date,
    filtered by enabled modules.
    """
    blueprint = get_blueprint(user)
    non_negotiables = blueprint.non_negotiables.filter(is_active=True)

    result = []
    for nn in non_negotiables:
        if not nn.is_applicable_today(date):
            continue
        if not nn.is_feature_enabled(blueprint):
            continue
        result.append(nn)

    return result
