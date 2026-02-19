"""
Phase 5 — Recalibration Loop.

Detects when a user repeatedly violates a non-negotiable commitment and
triggers a conversational reclassification. This is NOT punitive — it's
a check-in: "Has something changed, or do we recommit?"

Recalibration triggers when:
    - Miss rate >= 60% over 7 days for a non-negotiable
    - AND review interval has elapsed since last review

Public API:
    - check_recalibration_needed(user) -> list[RecalibrationTrigger]
    - build_recalibration_injection(user) -> str
    - record_recalibration_decision(user, module_key, decision, new_level) -> None
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Thresholds
RECALIBRATION_MISS_THRESHOLD = 0.6  # 60% miss rate triggers recalibration
MINIMUM_REVIEW_INTERVAL_DAYS = 7    # Don't ask more often than weekly


class RecalibrationTrigger:
    """A module that needs recalibration."""
    __slots__ = (
        'module_key', 'display_name', 'commitment_level',
        'miss_rate', 'drift_pressure', 'days_since_review',
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def check_recalibration_needed(user):
    """
    Check which governance profiles need recalibration.

    Returns:
        list of RecalibrationTrigger for modules that need reclassification.
    """
    try:
        from apps.core.ai_governance.models import GovernanceProfile
        from apps.core.ai_governance.consistency_evaluator import (
            compute_drift_pressure,
            get_miss_rate,
        )

        profiles = GovernanceProfile.objects.filter(
            user=user,
            is_active=True,
            commitment_level='non_negotiable',
        )

        triggers = []
        now = timezone.now()

        for profile in profiles:
            # Check review interval
            if profile.last_reviewed_at:
                days_since = (now - profile.last_reviewed_at).days
                if days_since < max(
                    MINIMUM_REVIEW_INTERVAL_DAYS,
                    profile.review_interval_days,
                ):
                    continue
            else:
                days_since = 999  # Never reviewed

            # Check miss rate
            miss_rate = get_miss_rate(user, profile.module_key, days=7)
            if miss_rate < RECALIBRATION_MISS_THRESHOLD:
                continue

            # Get drift pressure for context
            dp = compute_drift_pressure(user, profile.module_key)
            drift = dp.drift_pressure if dp else 0

            triggers.append(RecalibrationTrigger(
                module_key=profile.module_key,
                display_name=profile.display_name,
                commitment_level=profile.commitment_level,
                miss_rate=round(miss_rate, 2),
                drift_pressure=round(drift, 1),
                days_since_review=days_since,
            ))

        return triggers

    except Exception as e:
        logger.debug("Recalibration check failed: %s", e)
        return []


def build_recalibration_injection(user):
    """
    Build system prompt injection for recalibration conversations.

    Only returns content if there are modules needing recalibration.

    Returns:
        str — system prompt block, or empty string.
    """
    triggers = check_recalibration_needed(user)
    if not triggers:
        return ""

    lines = ["--- RECALIBRATION NEEDED ---"]
    lines.append("")
    lines.append(
        "The following commitments have been consistently missed. "
        "You need to have a direct, non-judgmental conversation about each one. "
        "Ask: 'Has something changed, or should we recommit?'"
    )
    lines.append("")

    for t in triggers[:3]:  # Max 3 at a time
        lines.append(
            f"- {t.display_name}: classified as non-negotiable, "
            f"but missed {t.miss_rate:.0%} of the time over 7 days."
        )

    lines.append("")
    lines.append(
        "RULES: "
        "1. Name the specific inconsistency with evidence. "
        "2. No guilt, no emotion — just facts. "
        "3. Offer three options: recommit, downgrade to 'important', or drop entirely. "
        "4. Accept their decision without argument. "
        "5. If they recommit, acknowledge it and move on. "
        "6. Address ONE item per conversation, not all at once."
    )
    lines.append("--- END RECALIBRATION ---")
    return '\n'.join(lines)


def record_recalibration_decision(user, module_key, decision, new_level=None):
    """
    Record the user's recalibration decision.

    Args:
        user: Django User instance.
        module_key: str — module being recalibrated.
        decision: str — 'recommit', 'downgrade', or 'drop'
        new_level: str — new commitment level if downgrading
            ('important' or 'flexible')
    """
    try:
        from apps.core.ai_governance.models import GovernanceProfile

        profile = GovernanceProfile.objects.filter(
            user=user, module_key=module_key, is_active=True,
        ).first()

        if not profile:
            return

        profile.last_reviewed_at = timezone.now()

        if decision == 'recommit':
            # Keep as non-negotiable, reset review timer
            profile.save(update_fields=['last_reviewed_at', 'updated_at'])
            logger.info(
                "User %s recommitted to %s as non-negotiable",
                user.id, module_key,
            )

        elif decision == 'downgrade':
            new = new_level or 'important'
            profile.commitment_level = new
            # Adjust importance weight
            weight_map = {
                'non_negotiable': 2.0,
                'important': 1.0,
                'flexible': 0.3,
            }
            profile.importance_weight = weight_map.get(new, 1.0)
            profile.save(update_fields=[
                'commitment_level', 'importance_weight',
                'last_reviewed_at', 'updated_at',
            ])
            logger.info(
                "User %s downgraded %s to %s",
                user.id, module_key, new,
            )

            # Deactivate NonNegotiable if it exists
            _deactivate_non_negotiable(user, module_key)

        elif decision == 'drop':
            profile.is_active = False
            profile.save(update_fields=['is_active', 'last_reviewed_at', 'updated_at'])
            logger.info("User %s dropped %s from governance", user.id, module_key)
            _deactivate_non_negotiable(user, module_key)

    except Exception as e:
        logger.error("Recalibration decision recording failed: %s", e)


def _deactivate_non_negotiable(user, module_key):
    """Deactivate NonNegotiable record when commitment is downgraded."""
    try:
        from apps.core.blueprint.models import NonNegotiable
        NonNegotiable.objects.filter(
            blueprint__user=user,
            module_key=module_key,
            is_active=True,
        ).update(is_active=False)
    except Exception:
        pass
