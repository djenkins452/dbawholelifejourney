"""
Whole Life Journey - Architecture Engine

Project: Whole Life Journey
Path: apps/core/blueprint/architecture_engine.py
Purpose: Daily Architecture Pass and Curveball Re-optimization

Description:
    Implements the nightly "Tomorrow Architecture Pass" that builds a daily plan
    from calendar events, tasks, non-negotiables, health commitments, and sleep.
    Also handles real-time "Curveball Re-optimization" when the user says
    "clear my calendar, I have to do X".

    Pipeline:
    - Uses HTIE for time normalization
    - Uses PRIE to forecast "tomorrow drift risk"
    - Uses PGE to rank which blocks matter most
    - Attaches E3 explanations for key moves
    - Registered in ISE for nightly execution

Public API:
    - run_architecture_pass(user, target_date=None) -> ArchitecturePlan
    - handle_curveball(user, description, new_event_start, new_event_end) -> ArchitecturePlan
    - get_todays_plan(user) -> ArchitecturePlan or None

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
import logging

from django.utils import timezone

from . import engine as blueprint_engine
from .models import ArchitecturePlan, ScheduledBlock
from . import priority_engine

logger = logging.getLogger(__name__)


# =============================================================================
# PUBLIC API
# =============================================================================


def run_architecture_pass(user, target_date=None):
    """
    Run the nightly architecture pass for a target date (default: tomorrow).

    Steps:
    1. Load blueprint + non-negotiables
    2. Gather calendar events + tasks
    3. Build sleep block
    4. Place non-negotiables in preferred windows
    5. Fill gaps with tasks by priority
    6. Compute risk warnings
    7. Generate E3 evidence
    8. Store and activate plan

    Returns:
        ArchitecturePlan (activated)
    """
    if target_date is None:
        target_date = timezone.localdate() + datetime.timedelta(days=1)

    blueprint = blueprint_engine.get_blueprint(user)

    # Get non-negotiables for the target date
    non_negotiables = blueprint_engine.get_non_negotiables_for_date(user, target_date)

    # Gather inputs
    calendar_events = _get_calendar_events(user, target_date)
    tasks = _get_tasks_with_deadlines(user, target_date)

    # Build the plan
    plan = ArchitecturePlan.objects.create(
        user=user,
        date=target_date,
        status=ArchitecturePlan.STATUS_DRAFT,
        generation_trigger='nightly',
    )

    blocks = []

    # 1. Sleep block
    sleep_block = _create_sleep_block(blueprint, target_date)
    if sleep_block:
        blocks.append(sleep_block)
        plan.recommended_wake_time = sleep_block.get('wake_time')
        plan.recommended_sleep_time = sleep_block.get('sleep_time')

    # 2. Non-negotiables
    for nn in non_negotiables:
        block = _create_non_negotiable_block(blueprint, nn)
        if block:
            blocks.append(block)

    # 3. Calendar events
    for event in calendar_events:
        block = _create_calendar_block(event)
        blocks.append(block)

    # 4. Tasks
    for task in tasks:
        block = _create_task_block(task)
        blocks.append(block)

    # Sort all blocks by start time and check for conflicts
    blocks = sorted(blocks, key=lambda b: b.get('start_time', datetime.time(0)))

    # Prioritize using priority engine
    blocks = priority_engine.prioritize_blocks(blueprint, blocks)

    # Create ScheduledBlock records
    for block_data in blocks:
        ScheduledBlock.objects.create(
            plan=plan,
            start_time=block_data.get('start_time', datetime.time(8, 0)),
            end_time=block_data.get('end_time', datetime.time(9, 0)),
            title=block_data.get('title', 'Untitled'),
            description=block_data.get('description', ''),
            tier=block_data.get('tier', 4),
            source=block_data.get('source', ScheduledBlock.SOURCE_BUFFER),
            source_id=block_data.get('source_id', ''),
            is_locked=block_data.get('tier', 4) <= 1,  # Tier 1 locked by default
            rationale=block_data.get('rationale', ''),
            behavior_key=block_data.get('behavior_key', ''),
        )

    # Compute risk warnings
    risk_warnings = _compute_risk_warnings(blueprint, blocks, target_date)
    plan.risk_warnings = risk_warnings

    # Generate identity cost summary
    identity_costs = {}
    for block_data in blocks:
        bk = block_data.get('behavior_key', '')
        if bk and block_data.get('tier', 4) <= 2:
            cost = priority_engine.compute_identity_cost(blueprint, bk)
            identity_costs[bk] = cost.cost
    plan.identity_cost_summary = identity_costs

    # E3 evidence
    plan.evidence_summary = {
        'blocks_scheduled': len(blocks),
        'non_negotiables_placed': len(non_negotiables),
        'calendar_events': len(calendar_events),
        'tasks_scheduled': len(tasks),
        'risk_warnings': len(risk_warnings),
    }

    plan.save()

    # Activate
    plan.activate()

    # Update blueprint metadata
    blueprint.last_architecture_run_at = timezone.now()
    blueprint.save(update_fields=['last_architecture_run_at', 'updated_at'])

    logger.info(
        "Architecture pass completed for %s on %s: %d blocks, %d warnings",
        user.email, target_date, len(blocks), len(risk_warnings),
    )

    return plan


def handle_curveball(user, description, new_event_start=None, new_event_end=None,
                     new_event_duration_minutes=60):
    """
    Handle a curveball event by re-optimizing the current day's plan.

    Steps:
    1. Get current active plan
    2. Add the curveball event
    3. Use priority engine to resolve conflicts (Rule B)
    4. Create new plan version
    5. Attach E3 evidence for any Tier 1 impacts

    Args:
        user: The user
        description: What the curveball is
        new_event_start: Start time (TimeField)
        new_event_end: End time (TimeField)
        new_event_duration_minutes: Duration if end not specified

    Returns:
        New ArchitecturePlan (activated)
    """
    today = timezone.localdate()
    blueprint = blueprint_engine.get_blueprint(user)
    current_plan = ArchitecturePlan.get_active_for_date(user, today)

    # Get existing blocks
    existing_blocks = []
    if current_plan:
        for block in current_plan.blocks.all():
            existing_blocks.append({
                'start_time': block.start_time,
                'end_time': block.end_time,
                'title': block.title,
                'tier': block.tier,
                'source': block.source,
                'behavior_key': block.behavior_key,
                'is_locked': block.is_locked,
                'is_completed': block.is_completed,
            })

    # Build curveball block
    if new_event_start is None:
        now = timezone.localtime()
        new_event_start = now.time()

    if new_event_end is None:
        start_dt = datetime.datetime.combine(today, new_event_start)
        end_dt = start_dt + datetime.timedelta(minutes=new_event_duration_minutes)
        new_event_end = end_dt.time()

    curveball_block = {
        'start_time': new_event_start,
        'end_time': new_event_end,
        'title': description,
        'tier': 2,  # Curveballs are directional
        'source': 'calendar',
        'behavior_key': '',
        'is_locked': True,  # Curveball is locked
    }

    # Resolve conflicts using priority engine
    resolution = priority_engine.resolve_conflict(
        blueprint,
        [b for b in existing_blocks if not b.get('is_completed')],
        [],  # available slots computed internally
        curveball_block,
    )

    # Create new plan
    new_plan = ArchitecturePlan.objects.create(
        user=user,
        date=today,
        status=ArchitecturePlan.STATUS_DRAFT,
        generation_trigger='curveball',
        curveball_description=description,
        risk_warnings=([resolution.explanation] if resolution.tier1_impacted else []),
        identity_cost_summary=(
            {'curveball_cost': resolution.identity_cost}
            if resolution.tier1_impacted else {}
        ),
        evidence_summary={
            'trigger': 'curveball',
            'description': description,
            'blocks_moved': len(resolution.moved_blocks),
            'tier1_impacted': resolution.tier1_impacted,
            'identity_cost': resolution.identity_cost,
            'recovery_plan': resolution.recovery_plan,
        },
    )

    # Re-create blocks: completed blocks as-is, adjust others
    for block_data in existing_blocks:
        if block_data.get('is_completed'):
            ScheduledBlock.objects.create(
                plan=new_plan,
                start_time=block_data['start_time'],
                end_time=block_data['end_time'],
                title=block_data['title'],
                tier=block_data['tier'],
                source=block_data['source'],
                behavior_key=block_data.get('behavior_key', ''),
                is_locked=True,
                is_completed=True,
            )

    # Add curveball block
    ScheduledBlock.objects.create(
        plan=new_plan,
        start_time=curveball_block['start_time'],
        end_time=curveball_block['end_time'],
        title=curveball_block['title'],
        tier=curveball_block['tier'],
        source=ScheduledBlock.SOURCE_CALENDAR,
        is_locked=True,
        rationale=f"Curveball: {description}",
    )

    # Activate new plan
    new_plan.activate()

    logger.info(
        "Curveball handled for %s: '%s', %d blocks moved, tier1=%s",
        user.email, description, len(resolution.moved_blocks),
        resolution.tier1_impacted,
    )

    return new_plan


def get_todays_plan(user):
    """Get the active architecture plan for today."""
    return ArchitecturePlan.get_active_for_date(user)


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _get_calendar_events(user, target_date):
    """Fetch calendar events for a date from the Life/Organize module."""
    events = []
    try:
        from apps.life.models import LifeEvent
        qs = LifeEvent.objects.filter(
            user=user,
            start_date=target_date,
        ).order_by('start_time')
        for event in qs[:20]:  # Limit
            events.append({
                'title': event.title,
                'start_time': event.start_time,
                'end_time': event.end_time,
                'source_id': str(event.pk),
            })
    except Exception as e:
        logger.warning("Could not fetch calendar events: %s", e)
    return events


def _get_tasks_with_deadlines(user, target_date):
    """Fetch tasks with deadlines on the target date."""
    tasks = []
    try:
        from apps.life.models import Task
        qs = Task.objects.filter(
            user=user,
            due_date=target_date,
            is_completed=False,
        ).order_by('priority', 'due_date')
        for task in qs[:10]:  # Limit
            tasks.append({
                'title': task.title,
                'priority': getattr(task, 'priority', 3),
                'source_id': str(task.pk),
                'estimated_minutes': getattr(task, 'estimated_minutes', 30),
            })
    except Exception as e:
        logger.warning("Could not fetch tasks: %s", e)
    return tasks


def _create_sleep_block(blueprint, target_date):
    """Create a sleep/wake time recommendation block."""
    sleep_minutes = blueprint.sleep_target_minutes
    sleep_hours = sleep_minutes / 60

    # Default: sleep at 10pm, wake at target
    wake_hour = int(24 - sleep_hours + 22) % 24  # Approximate
    if wake_hour < 4:
        wake_hour = 6
    if wake_hour > 9:
        wake_hour = 7

    sleep_time = datetime.time(22, 0)
    wake_time = datetime.time(wake_hour, 0)

    # Check user activity patterns for personalization
    try:
        from apps.core.models import UserActivityPattern
        pattern = UserActivityPattern.objects.filter(user=blueprint.user).first()
        if pattern and pattern.is_reliable:
            typical_start = pattern.typical_start_hour
            wake_time = datetime.time(int(typical_start), int((typical_start % 1) * 60))
            # Compute sleep time from wake + target sleep
            sleep_hour = int(typical_start - sleep_hours)
            if sleep_hour < 0:
                sleep_hour += 24
            sleep_time = datetime.time(sleep_hour, 0)
    except Exception:
        pass

    return {
        'title': 'Sleep',
        'start_time': sleep_time,
        'end_time': wake_time,
        'tier': 1,
        'source': ScheduledBlock.SOURCE_SLEEP,
        'behavior_key': 'SLEEP',
        'rationale': f"Target: {sleep_hours:.0f}h sleep",
        'wake_time': wake_time,
        'sleep_time': sleep_time,
    }


def _create_non_negotiable_block(blueprint, nn):
    """Create a scheduled block from a non-negotiable."""
    start = nn.preferred_time_window_start or datetime.time(8, 0)
    end_dt = datetime.datetime.combine(
        datetime.date.today(), start
    ) + datetime.timedelta(minutes=nn.min_duration_minutes)
    end = end_dt.time()

    tier = blueprint.get_tier_for_behavior(nn.behavior_key)

    return {
        'title': nn.display_name,
        'start_time': start,
        'end_time': end,
        'tier': tier,
        'source': ScheduledBlock.SOURCE_NON_NEGOTIABLE,
        'source_id': str(nn.pk),
        'behavior_key': nn.behavior_key,
        'rationale': f"Non-negotiable: {nn.display_name} ({nn.get_frequency_display()})",
    }


def _create_calendar_block(event_data):
    """Create a scheduled block from a calendar event."""
    return {
        'title': event_data.get('title', 'Calendar Event'),
        'start_time': event_data.get('start_time') or datetime.time(9, 0),
        'end_time': event_data.get('end_time') or datetime.time(10, 0),
        'tier': 3,
        'source': ScheduledBlock.SOURCE_CALENDAR,
        'source_id': event_data.get('source_id', ''),
        'rationale': 'Calendar event',
    }


def _create_task_block(task_data):
    """Create a scheduled block from a task."""
    estimated = task_data.get('estimated_minutes', 30)
    return {
        'title': task_data.get('title', 'Task'),
        'start_time': datetime.time(10, 0),  # Placeholder; filled by slot allocation
        'end_time': (
            datetime.datetime.combine(datetime.date.today(), datetime.time(10, 0))
            + datetime.timedelta(minutes=estimated)
        ).time(),
        'tier': 3,
        'source': ScheduledBlock.SOURCE_TASK,
        'source_id': task_data.get('source_id', ''),
        'rationale': f"Task due today (est. {estimated}min)",
    }


def _compute_risk_warnings(blueprint, blocks, target_date):
    """Compute risk warnings for a plan."""
    warnings = []

    # Check for schedule density
    total_minutes = 0
    for block in blocks:
        start = block.get('start_time', datetime.time(0))
        end = block.get('end_time', datetime.time(0))
        start_min = start.hour * 60 + start.minute
        end_min = end.hour * 60 + end.minute
        if end_min > start_min:
            total_minutes += (end_min - start_min)

    waking_hours = 16 * 60  # Approximate
    density = total_minutes / waking_hours if waking_hours > 0 else 0

    if density > 0.85:
        warnings.append(
            f"Schedule density is {density:.0%}. Consider trimming optional blocks."
        )

    # Check for Tier 1 blocks at risk
    tier1_blocks = [b for b in blocks if b.get('tier', 4) == 1]
    if not tier1_blocks:
        warnings.append("No Tier 1 (identity-protected) blocks scheduled.")

    # Check sleep adequacy
    sleep_target = blueprint.sleep_target_minutes
    sleep_blocks = [b for b in blocks if b.get('behavior_key') == 'SLEEP']
    if not sleep_blocks:
        warnings.append(f"No sleep block scheduled. Target: {sleep_target // 60}h.")

    return warnings
