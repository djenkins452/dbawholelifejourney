"""
Phase 5 — Tomorrow Protection Pass.

Scheduled check (7 PM user time) that:
1. Locks non-negotiable blocks in tomorrow's plan
2. Detects overload (capacity > 85%)
3. Auto-moves flexible items when overloaded
4. Generates a brief protection summary

This runs AFTER the nightly architecture pass has built tomorrow's plan.
It applies governance-aware adjustments on top.

Public API:
    - run_protection_pass(user) -> ProtectionResult
    - run_protection_pass_all_users() -> dict
"""

import datetime
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


class ProtectionResult:
    """Result of a tomorrow protection pass."""
    __slots__ = (
        'user_id', 'locked_count', 'moved_count',
        'capacity_before', 'capacity_after',
        'warnings', 'actions_taken',
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self):
        return {slot: getattr(self, slot, None) for slot in self.__slots__}


def run_protection_pass(user):
    """
    Run the tomorrow protection pass for a single user.

    Steps:
    1. Get tomorrow's plan
    2. Lock all non-negotiable blocks
    3. Compute capacity
    4. If overloaded, move flexible blocks
    5. Return summary

    Returns:
        ProtectionResult or None
    """
    try:
        from apps.core.blueprint.models import ArchitecturePlan
        from apps.core.ai_governance.models import GovernanceProfile

        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        plan = ArchitecturePlan.get_active_for_date(user, tomorrow)

        if not plan:
            return None

        blocks = list(plan.blocks.all().order_by('start_time'))
        if not blocks:
            return None

        # Get governance profiles
        profiles = {
            p.module_key: p
            for p in GovernanceProfile.objects.filter(
                user=user, is_active=True,
            )
        }

        locked_count = 0
        moved_count = 0
        warnings = []
        actions = []

        # Step 1: Lock non-negotiable blocks
        for block in blocks:
            module_key = _block_to_module_key(block)
            profile = profiles.get(module_key)

            if profile and profile.commitment_level == 'non_negotiable':
                if not block.is_locked:
                    block.is_locked = True
                    block.save(update_fields=['is_locked'])
                    locked_count += 1
                    actions.append(f"Locked: {block.title}")

            # Also lock tier-1 blocks
            elif block.tier == 1 and not block.is_locked:
                block.is_locked = True
                block.save(update_fields=['is_locked'])
                locked_count += 1
                actions.append(f"Locked (Tier 1): {block.title}")

        # Step 2: Compute capacity
        total_minutes = 0
        for b in blocks:
            if b.start_time and b.end_time:
                s = datetime.datetime.combine(tomorrow, b.start_time)
                e = datetime.datetime.combine(tomorrow, b.end_time)
                d = (e - s).total_seconds() / 60
                if d > 0:
                    total_minutes += d

        waking_minutes = 16 * 60
        capacity_before = min(100, round(total_minutes / waking_minutes * 100))

        # Step 3: If overloaded (>85%), move flexible blocks
        capacity_after = capacity_before
        if capacity_before > 85:
            warnings.append(
                f"Tomorrow at {capacity_before}% capacity — overloaded."
            )

            # Find flexible blocks to move (lowest tier, not locked)
            flexible_blocks = [
                b for b in blocks
                if not b.is_locked
                and b.tier >= 3
                and _block_to_module_key(b) not in {
                    k for k, p in profiles.items()
                    if p.commitment_level == 'non_negotiable'
                }
            ]

            # Sort by tier (highest first = least important)
            flexible_blocks.sort(key=lambda b: -b.tier)

            for block in flexible_blocks:
                if capacity_after <= 80:
                    break

                # Remove block duration from capacity
                if block.start_time and block.end_time:
                    s = datetime.datetime.combine(tomorrow, block.start_time)
                    e = datetime.datetime.combine(tomorrow, block.end_time)
                    d = (e - s).total_seconds() / 60
                    if d > 0:
                        total_minutes -= d
                        capacity_after = min(
                            100, round(total_minutes / waking_minutes * 100)
                        )

                # Mark as moved (set to flexible status)
                block.is_completed = False
                block.notes = (block.notes or '') + ' [Moved by protection pass]'
                block.save(update_fields=['notes', 'updated_at'])
                moved_count += 1
                actions.append(f"Deprioritized: {block.title} (Tier {block.tier})")

            if moved_count > 0:
                warnings.append(
                    f"Moved {moved_count} flexible items to protect commitments."
                )

        # Step 4: Check for at-risk non-negotiables without blocks
        from apps.core.blueprint.models import NonNegotiable
        nns = NonNegotiable.objects.filter(
            blueprint__user=user,
            is_active=True,
        )
        block_behaviors = {_block_to_module_key(b) for b in blocks}
        for nn in nns:
            if nn.is_applicable_today(tomorrow):
                if nn.module_key not in block_behaviors:
                    warnings.append(
                        f"No block scheduled for non-negotiable: {nn.display_name}"
                    )

        result = ProtectionResult(
            user_id=user.id,
            locked_count=locked_count,
            moved_count=moved_count,
            capacity_before=capacity_before,
            capacity_after=capacity_after,
            warnings=warnings,
            actions_taken=actions,
        )

        # Fire PIE event for tracking
        _fire_protection_event(user, result)

        return result

    except Exception as e:
        logger.error("Protection pass failed for user %s: %s", user.id, e)
        return None


def run_protection_pass_all_users():
    """
    Run tomorrow protection pass for all active AI users.

    Returns:
        dict — {processed: int, protected: int, errors: int}
    """
    try:
        from apps.core.ai_scheduler.scheduler_runner import _get_active_ai_users
        users = _get_active_ai_users()
    except ImportError:
        return {"processed": 0, "protected": 0, "errors": 0}

    processed = 0
    protected = 0
    errors = 0

    for user in users:
        try:
            result = run_protection_pass(user)
            processed += 1
            if result and (result.locked_count > 0 or result.moved_count > 0):
                protected += 1
        except Exception as e:
            logger.error("Protection pass error for user %s: %s", user.id, e)
            errors += 1

    logger.info(
        "Tomorrow protection pass: %d processed, %d protected, %d errors",
        processed, protected, errors,
    )
    return {"processed": processed, "protected": protected, "errors": errors}


# =============================================================================
# HELPERS
# =============================================================================


def _block_to_module_key(block):
    """Extract module_key from a ScheduledBlock."""
    # Try behavior_key first, then fall back to title-based mapping
    if hasattr(block, 'behavior_key') and block.behavior_key:
        return block.behavior_key.replace('_', '.')
    # Simple title-based fallback
    title_lower = (block.title or '').lower()
    if any(w in title_lower for w in ('prayer', 'devotion', 'bible', 'scripture')):
        return 'faith'
    if any(w in title_lower for w in ('workout', 'exercise', 'gym', 'run')):
        return 'health.exercise'
    if any(w in title_lower for w in ('journal', 'reflect')):
        return 'journal'
    if any(w in title_lower for w in ('sleep', 'bed')):
        return 'health.sleep'
    if any(w in title_lower for w in ('meal', 'eat', 'nutrition', 'cook')):
        return 'health.nutrition'
    return ''


def _fire_protection_event(user, result):
    """Fire a PIE event for the protection pass."""
    try:
        from apps.core.ai_insights.insight_engine import run_insights
        run_insights(user, {
            'event_type': 'scheduled_check',
            'module': 'governance',
            'action': 'protection_pass',
            'context': {
                'locked': result.locked_count,
                'moved': result.moved_count,
                'capacity_before': result.capacity_before,
                'capacity_after': result.capacity_after,
                'warnings': result.warnings,
            },
            'timestamp_utc': timezone.now().isoformat(),
        })
    except Exception:
        pass  # PIE events must never break protection pass
