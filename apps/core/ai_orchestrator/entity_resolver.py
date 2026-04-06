"""
Entity Resolver — resolve natural language entity references to database objects.

Pipeline position:
    Activity Reconciliation → **Entity Resolver** → CRUD Confirmation Gate

This is a data enrichment step ONLY. It never executes actions, never bypasses
safety, and never overrides existing IDs. When a match is found, it attaches:
    - The resolved database ID (e.g., task_id)
    - The resolved display name (e.g., resolved_name)

When no match or multiple ambiguous matches are found, parameters pass through
unchanged — the downstream handler or CRUD gate handles clarification.

Supported entity types:
    - Tasks (complete_task, skip_task, mutate_task, read_task)
    - Goals (update_goal_progress)
    - Habits (log_habit)
    - Intakes (take_medication)
"""

import logging
from typing import Optional

from django.db.models import Q

logger = logging.getLogger(__name__)


# ── Intent → Entity mapping ──────────────────────────────────────────

# Maps intent_type → (keyword_param, id_param, name_param, resolver_func_name)
ENTITY_INTENT_MAP = {
    # Tasks
    'complete_task': ('task_keyword', '_resolved_id', 'resolved_name', '_resolve_task'),
    'skip_task': ('task_keyword', '_resolved_id', 'resolved_name', '_resolve_task'),
    'mutate_task': ('task_query', '_resolved_id', 'resolved_name', '_resolve_task'),
    'read_task': ('task_keyword', '_resolved_id', 'resolved_name', '_resolve_task'),
    # Goals
    'update_goal_progress': ('goal_keyword', '_resolved_goal_id', 'resolved_name', '_resolve_goal'),
    # Habits
    'log_habit': ('habit_keyword', '_resolved_habit_id', 'resolved_name', '_resolve_habit'),
    # Intakes (Medications)
    'take_medication': ('medicine_name', '_resolved_intake_id', 'resolved_name', '_resolve_intake'),
}


def resolve_entities(user, enriched_action) -> None:
    """
    Resolve entity references in-place on enriched_action.parameters.

    This mutates enriched_action.parameters directly — adding resolved IDs
    and display names when a confident match is found.

    Args:
        user: Django user instance (for user-scoped queries)
        enriched_action: EnrichedAction with intent_type and parameters dict
    """
    intent_type = enriched_action.intent_type
    params = enriched_action.parameters

    mapping = ENTITY_INTENT_MAP.get(intent_type)
    if not mapping:
        return  # No entity resolution needed for this intent

    keyword_param, id_param, name_param, resolver_name = mapping

    # Never override an existing ID
    if params.get(id_param):
        return

    keyword = params.get(keyword_param)
    if not keyword or not keyword.strip():
        return

    # Dispatch to the appropriate resolver
    resolver = _RESOLVERS.get(resolver_name)
    if not resolver:
        return

    try:
        result = resolver(user, keyword.strip())
        if result:
            params[id_param] = result['id']
            params[name_param] = result['name']
            logger.info(
                "[ENTITY_RESOLVER] Resolved %s='%s' → id=%s name='%s' for user=%s",
                keyword_param, keyword, result['id'], result['name'], user.id,
            )
    except Exception as e:
        # Entity resolution failure must never block the pipeline.
        # Parameters pass through unchanged — handler does its own lookup.
        logger.warning(
            "[ENTITY_RESOLVER] Failed to resolve %s='%s' for user=%s: %s",
            keyword_param, keyword, user.id, e, exc_info=True,
        )


# ── Individual resolvers ─────────────────────────────────────────────

def _resolve_task(user, keyword: str) -> Optional[dict]:
    """
    Resolve a task keyword to a single Task.

    Priority: exact title > prefix > substring.
    Tie-break: earliest due_date, then most recently updated.
    Returns None if zero or multiple ambiguous matches.
    """
    from apps.life.models import Task

    base_qs = Task.objects.filter(
        user=user, status='active', completion_status='pending',
    )

    # Tier 1: Exact match
    exact = list(base_qs.filter(title__iexact=keyword))
    if len(exact) == 1:
        return {'id': exact[0].id, 'name': exact[0].title}

    # Tier 2: Prefix match
    prefix = list(base_qs.filter(title__istartswith=keyword))
    if len(prefix) == 1:
        return {'id': prefix[0].id, 'name': prefix[0].title}

    # Tier 3: Substring match
    substring = list(
        base_qs.filter(
            Q(title__icontains=keyword) | Q(notes__icontains=keyword)
        ).order_by(
            # Earliest due_date first (nulls last), then most recently updated
            'due_date', '-updated_at',
        )[:5]
    )
    if len(substring) == 1:
        return {'id': substring[0].id, 'name': substring[0].title}

    # Multiple matches at any tier — pick best if tiers above returned >1
    if exact:
        # Multiple exact matches (unlikely) — pick earliest due_date
        best = _pick_best_task(exact)
        return {'id': best.id, 'name': best.title}
    if prefix:
        best = _pick_best_task(prefix)
        return {'id': best.id, 'name': best.title}

    # Multiple substring matches — don't guess, let handler disambiguate
    if len(substring) > 1:
        return None

    return None


def _pick_best_task(tasks):
    """Pick the best task from a list: earliest due_date, then most recent update."""
    return sorted(
        tasks,
        key=lambda t: (
            t.due_date if t.due_date else _far_future(),
            -(t.updated_at.timestamp() if t.updated_at else 0),
        ),
    )[0]


def _far_future():
    """Return a far-future date for null due_date sorting."""
    from datetime import date
    return date(9999, 12, 31)


def _resolve_goal(user, keyword: str) -> Optional[dict]:
    """Resolve a goal keyword to a single LifeGoal."""
    from apps.purpose.models import LifeGoal

    base_qs = LifeGoal.objects.filter(user=user, status='active')

    exact = list(base_qs.filter(title__iexact=keyword))
    if len(exact) == 1:
        return {'id': exact[0].id, 'name': exact[0].title}

    substring = list(
        base_qs.filter(title__icontains=keyword).order_by('-updated_at')[:5]
    )
    if len(substring) == 1:
        return {'id': substring[0].id, 'name': substring[0].title}

    return None


def _resolve_habit(user, keyword: str) -> Optional[dict]:
    """Resolve a habit keyword to a single HabitGoal."""
    from apps.purpose.models import HabitGoal

    base_qs = HabitGoal.objects.filter(user=user, status='active')

    exact = list(base_qs.filter(name__iexact=keyword))
    if len(exact) == 1:
        return {'id': exact[0].id, 'name': exact[0].name}

    substring = list(
        base_qs.filter(name__icontains=keyword).order_by('-updated_at')[:5]
    )
    if len(substring) == 1:
        return {'id': substring[0].id, 'name': substring[0].name}

    return None


def _resolve_intake(user, keyword: str) -> Optional[dict]:
    """Resolve an intake keyword to a single Intake."""
    from apps.health.models import Intake

    base_qs = Intake.objects.filter(
        user=user, status='active', intake_status='active',
    )

    exact = list(base_qs.filter(name__iexact=keyword))
    if len(exact) == 1:
        return {'id': exact[0].id, 'name': exact[0].name}

    substring = list(
        base_qs.filter(
            Q(name__icontains=keyword) | Q(purpose__icontains=keyword)
        ).order_by('-updated_at')[:5]
    )
    if len(substring) == 1:
        return {'id': substring[0].id, 'name': substring[0].name}

    return None


# Resolver dispatch table
_RESOLVERS = {
    '_resolve_task': _resolve_task,
    '_resolve_goal': _resolve_goal,
    '_resolve_habit': _resolve_habit,
    '_resolve_intake': _resolve_intake,
}
