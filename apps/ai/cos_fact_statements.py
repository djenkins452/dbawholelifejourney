"""
CoS Fact Statement Builders — System-owned truth.

These functions produce FINAL human-readable statements about today's
execution status. The LLM receives these statements and MUST use them
exactly. The LLM does NOT construct factual statements — the system does.

Architecture:
  Database → Execution Truth Engine → Fact Statement (string) → LLM prompt
  The LLM adds tone, flow, and coaching AROUND these statements.
  The LLM NEVER rewrites, reinterprets, or overrides them.

CRITICAL: This module uses ONLY the Execution Truth Engine for all
completion data. It does NOT query models directly. It does NOT call
faith/engagement.py or today_execution.py. One source of truth.
"""
import logging

logger = logging.getLogger(__name__)


def build_locked_facts(user) -> dict:
    """
    Build all locked fact statements for a user's current day.

    Uses the Execution Truth Engine as the SINGLE source of truth.
    Respects expected vs not-expected — domains not scheduled today
    are reported as "not scheduled" rather than "not yet completed."

    Returns:
        dict with keys:
            'faith_summary': str
            'routine_summary': str
            'task_summary': str
            'workout_summary': str
            'journal_summary': str
            'overall_summary': str
            '_raw': dict of booleans/ints for validator use
    """
    raw = {
        'prayer_done': False,
        'prayer_expected': False,
        'bible_done': False,
        'bible_expected': False,
        'workout_done': False,
        'workout_expected': False,
        'journal_done': False,
        'journal_expected': False,
        'routine_done': 0,
        'routine_total': 0,
        'tasks_done': 0,
    }

    pending_names = []

    # HARD CALL — no try/except. If this fails, the caller must know.
    # A silent failure here means Beth gets all-False data and lies.
    from apps.core.execution.execution_truth_engine import get_execution_truth
    truth = get_execution_truth(user)
    logger.info(
        "[CoS FACT BUILD] user=%s engine_call=SUCCESS date=%s",
        user.id, truth.get('date'),
    )

    # Faith — includes routine bridge (handled by engine)
    faith = truth['domains']['faith']
    raw['prayer_done'] = faith['prayer_completed']
    raw['prayer_expected'] = faith.get('prayer_expected', False)
    raw['bible_done'] = faith['bible_reading_completed']
    raw['bible_expected'] = faith.get('bible_expected', False)

    # Workout
    raw['workout_done'] = truth['domains']['workout']['completed']
    raw['workout_expected'] = truth['domains']['workout'].get('expected', False)

    # Journal
    raw['journal_done'] = truth['domains']['journal']['completed']
    raw['journal_expected'] = truth['domains']['journal'].get('expected', False)

    # Tasks
    raw['tasks_done'] = truth['tasks']['completed_today_all']

    # Routines
    raw['routine_total'] = truth['routines']['total']
    raw['routine_done'] = truth['routines']['completed']

    # Collect pending routine item names from raw items
    for _window, items in truth['routines'].get('_raw_items', {}).items():
        for item in items:
            if not item.get('is_completed'):
                pending_names.append(item.get('item_name', 'Unknown'))

    facts = {
        'faith_summary': _build_faith_summary(raw),
        'routine_summary': _build_routine_summary(
            raw['routine_done'], raw['routine_total'], pending_names,
        ),
        'task_summary': _build_task_summary(raw['tasks_done']),
        'workout_summary': _build_workout_summary(raw),
        'journal_summary': _build_journal_summary(raw),
        'overall_summary': _build_overall_summary(raw),
        'next_action': build_locked_next_action(user),
        '_raw': raw,
    }

    logger.info(
        "[CoS LOCKED FACTS] user=%s prayer=%s(exp=%s) bible=%s(exp=%s) "
        "workout=%s(exp=%s) journal=%s(exp=%s) routines=%d/%d tasks=%d",
        user.id,
        raw['prayer_done'], raw['prayer_expected'],
        raw['bible_done'], raw['bible_expected'],
        raw['workout_done'], raw['workout_expected'],
        raw['journal_done'], raw['journal_expected'],
        raw['routine_done'], raw['routine_total'], raw['tasks_done'],
    )

    return facts


def _build_faith_summary(raw):
    """Build locked faith fact statement with expectation awareness."""
    parts = []

    # Bible reading
    if raw['bible_done']:
        parts.append("Bible reading is complete.")
    elif raw['bible_expected']:
        parts.append("Bible reading is not yet completed.")
    else:
        parts.append("No Bible reading scheduled today.")

    # Prayer
    if raw['prayer_done']:
        parts.append("Prayer is complete.")
    elif raw['prayer_expected']:
        parts.append("Prayer is not yet completed.")
    else:
        parts.append("No prayer scheduled today.")

    return " ".join(parts)


def _build_routine_summary(done, total, pending_names):
    """Build locked routine fact statement."""
    if total == 0:
        return "No routine items scheduled today."

    if done >= total:
        return f"All {total} routine items completed."

    base = f"{done} of {total} routine items completed."
    if pending_names:
        shown = pending_names[:3]
        pending_text = ", ".join(shown)
        if len(pending_names) > 3:
            pending_text += f", and {len(pending_names) - 3} more"
        return f"{base} Still pending: {pending_text}."
    return base


def _build_task_summary(tasks_done):
    """Build locked task fact statement."""
    if tasks_done == 0:
        return "No tasks completed today."
    if tasks_done == 1:
        return "1 task completed today."
    return f"{tasks_done} tasks completed today."


def _build_workout_summary(raw):
    """Build locked workout fact statement with expectation awareness."""
    if raw['workout_done']:
        return "Workout is complete."
    elif raw['workout_expected']:
        return "Workout is not yet completed."
    else:
        return "No workout scheduled today."


def _build_journal_summary(raw):
    """Build locked journal fact statement with expectation awareness."""
    if raw['journal_done']:
        return "Journal entry logged today."
    elif raw['journal_expected']:
        return "Journal entry is not yet completed."
    else:
        return "No journal entry scheduled today."


def _build_overall_summary(raw):
    """Build locked overall day summary — only counts expected domains."""
    # Count only EXPECTED domains
    expected_domains = []
    done_domains = []

    if raw['prayer_expected'] or raw['prayer_done']:
        expected_domains.append('prayer')
        if raw['prayer_done']:
            done_domains.append('prayer')

    if raw['bible_expected'] or raw['bible_done']:
        expected_domains.append('Bible reading')
        if raw['bible_done']:
            done_domains.append('Bible reading')

    if raw['workout_expected'] or raw['workout_done']:
        expected_domains.append('workout')
        if raw['workout_done']:
            done_domains.append('workout')

    if raw['journal_expected'] or raw['journal_done']:
        expected_domains.append('journaling')
        if raw['journal_done']:
            done_domains.append('journaling')

    total_expected = len(expected_domains)
    total_done = len(done_domains)

    routine_text = ""
    if raw['routine_total'] > 0:
        routine_text = (
            f" Routine progress: {raw['routine_done']}"
            f" of {raw['routine_total']}."
        )

    task_text = f" {raw['tasks_done']} tasks completed."

    if total_expected == 0 and raw['routine_total'] == 0:
        return f"No items scheduled today.{task_text}"

    if (
        total_done == total_expected
        and total_expected > 0
        and raw['routine_done'] >= raw['routine_total']
    ):
        return "All daily items are complete."

    if total_done == 0 and raw['routine_done'] == 0:
        return (
            f"Nothing has been completed yet today.{routine_text}{task_text}"
        )

    done_text = ", ".join(done_domains) if done_domains else "Nothing"
    return f"{done_text} completed so far.{routine_text}{task_text}"


def build_locked_next_action(user) -> str:
    """
    Build the system-determined next action recommendation.

    Uses the Execution Truth Engine → today_execution → action prioritizer
    pipeline. The LLM does NOT decide what to recommend — the system does.

    Returns a locked statement like:
        "Start with Shower."
        "Start with Spay Weeds. Then move to Shower."
        "All items are complete — nothing pending."
    """
    try:
        from apps.core.execution.execution_truth_engine import get_execution_truth
        from apps.core.execution.today_execution import build_today_execution
        from apps.core.decision_engine.action_prioritizer import (
            prioritize_execution_items,
        )
        from apps.core.utils import get_user_now

        now = get_user_now(user)
        current_time = now.time()

        # Build execution contract for prioritizer
        exec_contract = build_today_execution(user)
        items = exec_contract.get('items', [])
        summaries = exec_contract.get('summaries', {})

        # Get prioritized actions (completed items already filtered out)
        priorities = prioritize_execution_items(
            items, current_time, summaries=summaries,
        )

        if not priorities:
            return "All items are complete — nothing pending."

        top = priorities[0]['title']
        result = f"Start with {top}."

        if len(priorities) >= 2:
            second = priorities[1]['title']
            result += f" Then move to {second}."

        logger.info(
            "[CoS LOCKED NEXT ACTION] user=%s top=%s total_pending=%d",
            user.id, top, len(priorities),
        )
        return result

    except Exception:
        logger.warning(
            "[CoS LOCKED NEXT ACTION] FAILED user=%s",
            user.id, exc_info=True,
        )
        return "Unable to determine next action — check your routine and task list."


def format_locked_facts_block(facts) -> str:
    """
    Format locked facts into the prompt block the LLM receives.

    This is the ONLY source of factual statements about today's status.
    The LLM must use these statements exactly.
    """
    lines = [
        "=" * 60,
        "LOCKED FACT STATEMENTS (SYSTEM-GENERATED — DO NOT CHANGE)",
        "=" * 60,
        "",
        f"  Faith: {facts['faith_summary']}",
        f"  Routines: {facts['routine_summary']}",
        f"  Tasks: {facts['task_summary']}",
        f"  Workout: {facts['workout_summary']}",
        f"  Journal: {facts['journal_summary']}",
        f"  Overall: {facts['overall_summary']}",
        "",
        f"  NEXT ACTION: {facts.get('next_action', 'Unable to determine.')}",
        "",
        "RULES:",
        "- You MUST include these facts in your response.",
        "- You MUST NOT change their wording, meaning, or completion status.",
        "- You MUST NOT infer, assume, or override completion status.",
        "- You MUST NOT say something is complete if the fact says 'not yet'.",
        "- You MUST NOT say something is pending if the fact says "
        "'not scheduled'.",
        "- You MUST NOT say 'great start' or 'productive' if Overall says "
        "'Nothing has been completed'.",
        "- You MAY add coaching, encouragement, or next-step suggestions "
        "AFTER presenting these facts.",
        "- You MAY paraphrase lightly for conversational flow, but the "
        "meaning and completion status MUST remain identical.",
        "- Example of acceptable paraphrasing:",
        "  Locked: 'Bible reading is not yet completed.'",
        "  OK: 'Bible reading hasn't been done yet.'",
        "  NOT OK: 'Bible reading is complete.'",
        "  NOT OK: 'You've finished your reading.'",
        "  Locked: 'No workout scheduled today.'",
        "  OK: 'No workout on the schedule today.'",
        "  NOT OK: 'Workout is not yet completed.'",
        "",
        "NEXT ACTION RULE (MANDATORY):",
        "- When the user asks 'what should I do next' or 'what to focus on',",
        "  your recommendation MUST match the NEXT ACTION above.",
        "- You MUST NOT recommend goals, prayer requests, or items not in",
        "  the execution list.",
        "- You MUST NOT invent actions from contextual data (goals, habits,",
        "  signals, patterns).",
        "- The NEXT ACTION is computed by the system from execution priority.",
        "  You do NOT decide priority — you only communicate it.",
        "=" * 60,
    ]
    return "\n".join(lines)
