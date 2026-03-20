"""
Today State — Deterministic Truth Layer.

Single source of truth for "what has actually happened today?"
Separates TRUTH (this file) from EXECUTION (today_execution.py) and
INTERPRETATION (cos_context.py).

ARCHITECTURAL RULES:
  1. Completion MUST come from deterministic DB records only.
     NEVER derive from streaks, trends, signals, or aggregates.
  2. Every domain reports a confidence level so the LLM can
     explain what data is missing and why it matters.
  3. Reuses existing services — never re-derives calculations.
  4. No new models or tables — pure computation layer.

CONSUMERS:
  - CoS context builder: reads today_state as the ONLY source of
    execution truth for the system prompt injection.
  - format_cos_system_injection(): renders today_state into the
    authoritative truth block.
"""

import logging
from datetime import date

from apps.core.utils import get_user_today

logger = logging.getLogger(__name__)


def build_today_state(user) -> dict:
    """
    Build the authoritative today-state snapshot.

    Returns a deterministic dict of what has actually been completed today,
    with confidence annotations per domain. This is the ONLY source CoS
    should use when stating what is done or not done.

    Returns:
        dict with 'date', 'domains', 'routines', 'tasks', 'medications',
        and 'data_confidence' keys.
    """
    user_today = get_user_today(user)

    state = {
        'date': user_today.isoformat(),
        'domains': {},
        'routines': {},
        'tasks': {},
        'medications': {},
        'data_confidence': {},
    }

    # ── Faith domain ──
    state['domains']['faith'] = _build_faith_state(user, user_today)

    # ── Health domain ──
    state['domains']['health'] = _build_health_state(user, user_today)

    # ── Journal domain ──
    state['domains']['journal'] = _build_journal_state(user, user_today)

    # ── Routines ──
    state['routines'] = _build_routine_state(user)

    # ── Tasks ──
    state['tasks'] = _build_task_state(user, user_today)

    # ── Medications ──
    state['medications'] = _build_medication_state(user, user_today)

    # ── Data confidence rollup ──
    state['data_confidence'] = _build_confidence_rollup(state)

    return state


# ── Domain Builders ─────────────────────────────────────────────


def _build_faith_state(user, user_today: date) -> dict:
    """Deterministic faith completion from DB records."""
    result = {
        'prayer_completed': False,
        'bible_reading_completed': False,
        'confidence': 'missing',
    }

    try:
        from apps.faith.engagement import get_faith_engagement_details
        faith = get_faith_engagement_details(user, user_today)
        result['bible_reading_completed'] = faith.get('reading_completed_today', False)
        result['prayer_completed'] = faith.get('faith_task_completed_today', False)
        result['confidence'] = 'high'
    except ImportError:
        result['confidence'] = 'missing'
    except Exception:
        logger.warning("today_state: faith state failed", exc_info=True)
        result['confidence'] = 'partial'

    return result


def _build_health_state(user, user_today: date) -> dict:
    """Deterministic health completion from DB records."""
    result = {
        'workout_completed': False,
        'medications_taken': False,
        'confidence': 'missing',
    }

    # Workout — direct DB check
    try:
        from apps.health.models import WorkoutSession
        result['workout_completed'] = WorkoutSession.objects.filter(
            user=user, date=user_today,
        ).exclude(status='deleted').exists()
    except ImportError:
        pass
    except Exception:
        logger.warning("today_state: workout check failed", exc_info=True)

    # Medications — reuse existing utility
    try:
        from apps.health.medicine_utils import calculate_medicine_adherence
        adherence = calculate_medicine_adherence(user, user_today, user_today)
        expected = adherence.get('expected_doses', 0)
        taken = adherence.get('taken_doses', 0)
        if expected == 0:
            result['medications_taken'] = True  # No meds scheduled = satisfied
        else:
            result['medications_taken'] = taken >= expected
        result['medications_detail'] = {
            'taken': taken,
            'expected': expected,
        }
    except ImportError:
        pass
    except Exception:
        logger.warning("today_state: medication check failed", exc_info=True)

    # Confidence based on what we could read
    result['confidence'] = 'high'
    return result


def _build_journal_state(user, user_today: date) -> dict:
    """Deterministic journal completion from DB records."""
    result = {
        'completed': False,
        'confidence': 'missing',
    }

    try:
        from apps.journal.models import JournalEntry
        result['completed'] = JournalEntry.objects.filter(
            user=user, entry_date=user_today,
        ).exists()
        result['confidence'] = 'high'
    except ImportError:
        result['confidence'] = 'missing'
    except Exception:
        logger.warning("today_state: journal check failed", exc_info=True)
        result['confidence'] = 'partial'

    return result


def _build_routine_state(user) -> dict:
    """Deterministic routine completion from today's routine items."""
    result = {
        'items': {},
        'total': 0,
        'completed': 0,
        'fully_complete': False,
    }

    try:
        from apps.life.services._routine_internal import get_todays_routine_items
        routine_data = get_todays_routine_items(user)
        routine_completion = routine_data.get('routine_completion', {})

        total = 0
        completed = 0

        for routine_name, completion in routine_completion.items():
            r_total = completion.get('total', 0)
            r_done = completion.get('completed', 0)
            total += r_total
            completed += r_done
            result['items'][routine_name] = {
                'total': r_total,
                'completed': r_done,
                'fully_complete': r_done >= r_total and r_total > 0,
            }

        result['total'] = total
        result['completed'] = completed
        result['fully_complete'] = completed >= total and total > 0

    except ImportError:
        pass
    except Exception:
        logger.warning("today_state: routine check failed", exc_info=True)

    return result


def _build_task_state(user, user_today: date) -> dict:
    """Deterministic task completion from DB records."""
    result = {
        'completed': 0,
        'total': 0,
    }

    try:
        from apps.life.models import Task
        today_tasks = Task.objects.filter(
            user=user,
            is_routine=False,
            due_date=user_today,
        ).exclude(status='deleted')

        result['total'] = today_tasks.count()
        result['completed'] = today_tasks.filter(
            completion_status='completed',
        ).count()
    except ImportError:
        pass
    except Exception:
        logger.warning("today_state: task check failed", exc_info=True)

    return result


def _build_medication_state(user, user_today: date) -> dict:
    """Deterministic medication state from DB records."""
    result = {
        'taken': 0,
        'expected': 0,
        'all_taken': False,
    }

    try:
        from apps.health.medicine_utils import calculate_medicine_adherence
        adherence = calculate_medicine_adherence(user, user_today, user_today)
        result['expected'] = adherence.get('expected_doses', 0)
        result['taken'] = adherence.get('taken_doses', 0)
        result['all_taken'] = (
            result['taken'] >= result['expected']
            if result['expected'] > 0
            else True
        )
    except ImportError:
        pass
    except Exception:
        logger.warning("today_state: medication state failed", exc_info=True)

    return result


# ── Confidence Rollup ───────────────────────────────────────────


def _build_confidence_rollup(state: dict) -> dict:
    """
    Build per-domain data confidence assessment.

    Values:
      - 'present': Deterministic records found, high confidence.
      - 'partial': Some data available but incomplete.
      - 'missing': No records found — could mean not tracked or not done.
    """
    rollup = {}

    # Faith
    faith = state.get('domains', {}).get('faith', {})
    faith_conf = faith.get('confidence', 'missing')
    if faith_conf == 'high':
        has_activity = faith.get('prayer_completed') or faith.get('bible_reading_completed')
        rollup['faith'] = 'present' if has_activity else 'missing'
    else:
        rollup['faith'] = faith_conf

    # Health
    health = state.get('domains', {}).get('health', {})
    health_conf = health.get('confidence', 'missing')
    if health_conf == 'high':
        has_workout = health.get('workout_completed', False)
        has_meds = health.get('medications_taken', False)
        if has_workout or has_meds:
            rollup['health'] = 'present'
        else:
            rollup['health'] = 'missing'
    else:
        rollup['health'] = health_conf

    # Journal
    journal = state.get('domains', {}).get('journal', {})
    journal_conf = journal.get('confidence', 'missing')
    if journal_conf == 'high':
        rollup['journal'] = 'present' if journal.get('completed') else 'missing'
    else:
        rollup['journal'] = journal_conf

    # Routines
    routines = state.get('routines', {})
    if routines.get('total', 0) > 0:
        if routines.get('completed', 0) > 0:
            rollup['routines'] = 'present' if routines.get('fully_complete') else 'partial'
        else:
            rollup['routines'] = 'missing'
    else:
        rollup['routines'] = 'missing'

    # Tasks
    tasks = state.get('tasks', {})
    if tasks.get('total', 0) > 0:
        if tasks.get('completed', 0) > 0:
            rollup['tasks'] = 'present' if tasks['completed'] >= tasks['total'] else 'partial'
        else:
            rollup['tasks'] = 'missing'
    else:
        rollup['tasks'] = 'missing'

    return rollup


# ── Prompt Formatting ───────────────────────────────────────────


def format_today_state_injection(today_state: dict) -> str:
    """
    Format today_state as an authoritative prompt injection block.

    This replaces the inline DailyProgressService rendering in
    format_cos_system_injection(). The output is deterministic and
    includes confidence annotations for missing data.

    Returns:
        str — formatted injection block for the system prompt.
    """
    lines = []
    lines.append("")
    lines.append("========== TODAY'S TRUTH STATE (AUTHORITATIVE — SINGLE SOURCE) ==========")
    lines.append("These are the EXACT completion states for today from database records.")
    lines.append("Use ONLY these when stating what is done or not done today.")
    lines.append("NEVER infer completion from streaks, trends, signals, or past behavior.")
    lines.append("")

    date_str = today_state.get('date', 'unknown')
    lines.append(f"Date: {date_str}")
    lines.append("")

    # ── Domains ──
    domains = today_state.get('domains', {})

    # Faith
    faith = domains.get('faith', {})
    prayer = faith.get('prayer_completed', False)
    bible = faith.get('bible_reading_completed', False)
    faith_done = prayer or bible
    lines.append(f"  Faith: {'DONE' if faith_done else 'NOT DONE'}")
    if faith_done:
        parts = []
        if prayer:
            parts.append("prayer")
        if bible:
            parts.append("Bible reading")
        lines.append(f"    Completed: {', '.join(parts)}")
    elif faith.get('confidence') == 'missing':
        lines.append("    [No faith activity logged today]")

    # Health — Workout
    health = domains.get('health', {})
    workout = health.get('workout_completed', False)
    lines.append(f"  Workout: {'DONE' if workout else 'NOT DONE'}")

    # Journal
    journal = domains.get('journal', {})
    journal_done = journal.get('completed', False)
    lines.append(f"  Journaling: {'DONE' if journal_done else 'NOT DONE'}")

    # ── Medications ──
    meds = today_state.get('medications', {})
    med_expected = meds.get('expected', 0)
    med_taken = meds.get('taken', 0)
    if med_expected > 0:
        all_taken = meds.get('all_taken', False)
        lines.append(
            f"  Medicine: {med_taken}/{med_expected} taken"
            + (" — ALL DONE" if all_taken else " — NOT ALL DONE")
        )
    else:
        lines.append("  Medicine: none scheduled today")

    # ── Routines ──
    routines = today_state.get('routines', {})
    r_total = routines.get('total', 0)
    r_completed = routines.get('completed', 0)
    if r_total > 0:
        lines.append(
            f"  Routines: {r_completed}/{r_total} completed"
            + (" — ALL DONE" if routines.get('fully_complete') else " — NOT ALL DONE")
        )
        # Per-routine breakdown
        for name, data in routines.get('items', {}).items():
            status = "DONE" if data.get('fully_complete') else f"{data.get('completed', 0)}/{data.get('total', 0)}"
            lines.append(f"    {name}: {status}")
    else:
        lines.append("  Routines: none scheduled today")

    # ── Tasks ──
    tasks = today_state.get('tasks', {})
    t_total = tasks.get('total', 0)
    t_completed = tasks.get('completed', 0)
    if t_total > 0:
        lines.append(
            f"  Tasks: {t_completed}/{t_total} completed"
            + (" — ALL DONE" if t_completed >= t_total else " — NOT ALL DONE")
        )
    else:
        lines.append("  Tasks: none due today")

    # ── Domain State Classification ──
    lines.append("")
    lines.append("DOMAIN STATE CLASSIFICATION:")
    domain_states = _classify_domain_states(today_state)
    for domain_name, domain_state in domain_states.items():
        lines.append(f"  {domain_name}: {domain_state}")

    has_actionable = any(v == 'ACTIONABLE' for v in domain_states.values())
    lines.append("")
    if has_actionable:
        lines.append("RESPONSE MODE: ACTION")
        lines.append("  Primary recommendations MUST come from ACTIONABLE domains.")
        lines.append("  SATISFIED domains may receive reinforcement (not action) if a signal justifies it.")
    else:
        lines.append("RESPONSE MODE: REINFORCEMENT")
        lines.append("  All domains satisfied. No new actions to recommend.")
        lines.append("  Focus on meaning, encouragement, or reflection.")

    # ── Truth Enforcement ──
    lines.append("")
    lines.append("TRUTH ENFORCEMENT:")
    lines.append("- If a domain shows NOT DONE, you MUST NOT say it is done.")
    lines.append("- If a domain shows DONE, you MUST NOT recommend it as an action.")
    lines.append("  DONE means SATISFIED — do not re-prescribe.")
    lines.append("- 7-day aggregates and streaks do NOT override today's status.")

    # ── Missing Data Guidance ──
    confidence = today_state.get('data_confidence', {})
    missing_domains = [k for k, v in confidence.items() if v == 'missing']
    partial_domains = [k for k, v in confidence.items() if v == 'partial']

    if missing_domains or partial_domains:
        lines.append("")
        lines.append("MISSING DATA HANDLING (REQUIRED):")
        lines.append("When data is missing, you MUST NOT say 'I don't have enough data.'")
        lines.append("Instead, follow this pattern:")
        lines.append("  1. State WHAT is missing (specific domain/activity)")
        lines.append("  2. Explain WHY it matters (connect to their goals)")
        lines.append("  3. Suggest HOW to improve tracking (with app link)")
        lines.append("")

        _MISSING_DATA_GUIDANCE = {
            'faith': (
                "No faith activity logged today.",
                "Tracking prayer and Bible reading helps me assess spiritual consistency "
                "and connect faith patterns with your overall well-being.",
                "[Faith](/faith/)",
            ),
            'health': (
                "No workout logged today.",
                "Logging workouts helps me track your fitness momentum, recovery "
                "patterns, and how exercise impacts your sleep and energy.",
                "[Health](/health/fitness/)",
            ),
            'journal': (
                "No journal entry for today.",
                "Even a short reflection helps me track your emotional patterns, "
                "stress levels, and overall sentiment trajectory.",
                "[Journal](/journal/)",
            ),
            'routines': (
                "No routine items completed today.",
                "Routine completion drives your daily consistency score and helps me "
                "identify when your day is on or off track.",
                "[Routines](/life/routines/)",
            ),
            'tasks': (
                "No tasks completed today.",
                "Task completion feeds your productivity signals and helps me suggest "
                "the right priorities at the right time.",
                "[Tasks](/life/tasks/)",
            ),
        }

        for domain in missing_domains:
            guidance = _MISSING_DATA_GUIDANCE.get(domain)
            if guidance:
                what, why, link = guidance
                lines.append(f"  {domain.upper()} — {what}")
                lines.append(f"    Why it matters: {why}")
                lines.append(f"    Track it: {link}")

        if partial_domains:
            for domain in partial_domains:
                lines.append(f"  {domain.upper()} — Partial data available. Some items tracked, others missing.")

    lines.append("")
    lines.append("========== END TODAY'S TRUTH STATE ==========")

    return '\n'.join(lines)


def _classify_domain_states(today_state: dict) -> dict:
    """Classify each domain as ACTIONABLE / SATISFIED / IRRELEVANT."""
    states = {}
    domains = today_state.get('domains', {})

    # Faith
    faith = domains.get('faith', {})
    faith_done = faith.get('prayer_completed') or faith.get('bible_reading_completed')
    states['faith'] = 'SATISFIED' if faith_done else 'ACTIONABLE'

    # Workout
    health = domains.get('health', {})
    states['workout'] = 'SATISFIED' if health.get('workout_completed') else 'ACTIONABLE'

    # Journal
    journal = domains.get('journal', {})
    states['journaling'] = 'SATISFIED' if journal.get('completed') else 'ACTIONABLE'

    # Medications
    meds = today_state.get('medications', {})
    if meds.get('expected', 0) > 0:
        states['medicine'] = 'SATISFIED' if meds.get('all_taken') else 'ACTIONABLE'
    else:
        states['medicine'] = 'IRRELEVANT'

    # Routines
    routines = today_state.get('routines', {})
    if routines.get('total', 0) > 0:
        states['routines'] = 'SATISFIED' if routines.get('fully_complete') else 'ACTIONABLE'
    else:
        states['routines'] = 'IRRELEVANT'

    # Tasks
    tasks = today_state.get('tasks', {})
    if tasks.get('total', 0) > 0:
        states['tasks'] = (
            'SATISFIED' if tasks.get('completed', 0) >= tasks['total']
            else 'ACTIONABLE'
        )
    else:
        states['tasks'] = 'IRRELEVANT'

    return states
