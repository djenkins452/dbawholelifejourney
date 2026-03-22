"""
Today State — Deterministic Truth Layer.

Single source of truth for "what has actually happened today?"
Separates TRUTH (this file) from EXECUTION (today_execution.py) and
INTERPRETATION (cos_context.py).

ARCHITECTURAL RULES:
  1. All completion data comes from the Execution Truth Engine.
     This file does NOT query models directly for completion.
  2. Every domain reports a confidence level so the LLM can
     explain what data is missing and why it matters.
  3. No new models or tables — pure computation layer.

CONSUMERS:
  - CoS context builder: reads today_state as the ONLY source of
    execution truth for the system prompt injection.
  - format_cos_system_injection(): renders today_state into the
    authoritative truth block.
"""

import logging

logger = logging.getLogger(__name__)


def build_today_state(user) -> dict:
    """
    Build the authoritative today-state snapshot.

    Delegates ALL completion checks to the Execution Truth Engine.
    This ensures there is ONE source of truth across the entire system.

    Returns:
        dict with 'date', 'domains', 'routines', 'tasks', 'medications',
        and 'data_confidence' keys.
    """
    from apps.core.execution.execution_truth_engine import get_execution_truth

    truth = get_execution_truth(user)

    # Map engine output to today_state format (preserving the interface
    # that consumers like format_today_state_injection() expect)
    state = {
        'date': truth['date'],
        'domains': {
            'faith': {
                'prayer_completed': truth['domains']['faith']['prayer_completed'],
                'bible_reading_completed': truth['domains']['faith']['bible_reading_completed'],
                'confidence': 'high',
            },
            'health': {
                'workout_completed': truth['domains']['workout']['completed'],
                'medications_taken': truth['medications']['all_taken'],
                'medications_detail': {
                    'taken': truth['medications']['taken'],
                    'expected': truth['medications']['expected'],
                },
                'confidence': 'high',
            },
            'journal': {
                'completed': truth['domains']['journal']['completed'],
                'confidence': 'high',
            },
        },
        'routines': {
            'total': truth['routines']['total'],
            'completed': truth['routines']['completed'],
            'fully_complete': truth['routines']['fully_complete'],
            'items': truth['routines']['items'],
            '_raw_items': truth['routines'].get('_raw_items', {}),
        },
        'tasks': {
            'total': truth['tasks']['total'],
            'completed': truth['tasks']['completed'],
        },
        'medications': truth['medications'],
        'data_confidence': {},
    }

    # ── Data confidence rollup ──
    state['data_confidence'] = _build_confidence_rollup(state)

    return state


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
    has_activity = faith.get('prayer_completed') or faith.get('bible_reading_completed')
    rollup['faith'] = 'present' if has_activity else 'missing'

    # Health
    health = state.get('domains', {}).get('health', {})
    has_workout = health.get('workout_completed', False)
    has_meds = health.get('medications_taken', False)
    if has_workout or has_meds:
        rollup['health'] = 'present'
    else:
        rollup['health'] = 'missing'

    # Journal
    journal = state.get('domains', {}).get('journal', {})
    rollup['journal'] = 'present' if journal.get('completed') else 'missing'

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
