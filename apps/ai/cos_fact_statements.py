"""
CoS Fact Statement Builders — System-owned truth.

These functions produce FINAL human-readable statements about today's
execution status. The LLM receives these statements and MUST use them
exactly. The LLM does NOT construct factual statements — the system does.

Architecture:
  Database → Service Layer → Fact Statement (string) → LLM prompt
  The LLM adds tone, flow, and coaching AROUND these statements.
  The LLM NEVER rewrites, reinterprets, or overrides them.
"""
import logging

logger = logging.getLogger(__name__)


def build_locked_facts(user) -> dict:
    """
    Build all locked fact statements for a user's current day.

    Returns:
        dict with keys:
            'faith_summary': str
            'routine_summary': str
            'task_summary': str
            'workout_summary': str
            'journal_summary': str
            'overall_summary': str
            '_raw': dict of booleans for validator use
    """
    raw = {
        'prayer_done': False,
        'bible_done': False,
        'workout_done': False,
        'journal_done': False,
        'routine_done': 0,
        'routine_total': 0,
        'tasks_done': 0,
    }

    try:
        from apps.core.execution.today_execution import build_today_execution
        exec_data = build_today_execution(user)
        summaries = exec_data.get('summaries', {})
        domains = summaries.get('domains', {})

        raw['prayer_done'] = domains.get('prayer', False)
        raw['bible_done'] = domains.get('bible_reading', False)
        raw['workout_done'] = domains.get('workout', False)
        raw['journal_done'] = domains.get('journal', False)
        raw['tasks_done'] = summaries.get('tasks_completed_today', 0)

        for rid, rdata in summaries.get('routines', {}).items():
            raw['routine_total'] += rdata.get('total_count', 0)
            raw['routine_done'] += rdata.get('completed_count', 0)
    except Exception as e:
        logger.warning("cos_fact_statements: execution data unavailable: %s", e)

    # Build pending routine item names
    pending_names = []
    try:
        from apps.core.execution.today_execution import build_today_execution
        exec_data = build_today_execution(user)
        for item in exec_data.get('items', []):
            if (
                item.get('source_type') == 'routine_item'
                and item.get('completion_status') in ('pending', 'overdue')
            ):
                pending_names.append(item.get('title', 'Unknown'))
    except Exception:
        pass

    facts = {
        'faith_summary': _build_faith_summary(
            raw['bible_done'], raw['prayer_done'],
        ),
        'routine_summary': _build_routine_summary(
            raw['routine_done'], raw['routine_total'], pending_names,
        ),
        'task_summary': _build_task_summary(raw['tasks_done']),
        'workout_summary': _build_workout_summary(raw['workout_done']),
        'journal_summary': _build_journal_summary(raw['journal_done']),
        'overall_summary': _build_overall_summary(raw),
        '_raw': raw,
    }

    logger.info(
        "[CoS LOCKED FACTS] user=%s prayer=%s bible=%s workout=%s "
        "journal=%s routines=%d/%d tasks=%d",
        user.id, raw['prayer_done'], raw['bible_done'],
        raw['workout_done'], raw['journal_done'],
        raw['routine_done'], raw['routine_total'], raw['tasks_done'],
    )

    return facts


def _build_faith_summary(bible_done, prayer_done):
    """Build locked faith fact statement."""
    parts = []
    if bible_done:
        parts.append("Bible reading is complete.")
    else:
        parts.append("Bible reading is not yet completed.")

    if prayer_done:
        parts.append("Prayer is complete.")
    else:
        parts.append("Prayer is not yet completed.")

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


def _build_workout_summary(workout_done):
    """Build locked workout fact statement."""
    if workout_done:
        return "Workout is complete."
    return "Workout is not yet completed."


def _build_journal_summary(journal_done):
    """Build locked journal fact statement."""
    if journal_done:
        return "Journal entry logged today."
    return "No journal entry yet today."


def _build_overall_summary(raw):
    """Build locked overall day summary."""
    done_count = sum([
        raw['prayer_done'],
        raw['bible_done'],
        raw['workout_done'],
        raw['journal_done'],
    ])
    total_domains = 4
    routine_text = ""
    if raw['routine_total'] > 0:
        routine_text = (
            f" Routine progress: {raw['routine_done']}"
            f" of {raw['routine_total']}."
        )

    if done_count == 0 and raw['routine_done'] == 0:
        return (
            f"Nothing has been completed yet today.{routine_text}"
            f" {raw['tasks_done']} tasks completed."
        )
    elif done_count == total_domains and raw['routine_done'] >= raw['routine_total']:
        return "All daily items are complete."
    else:
        domains_done = []
        if raw['prayer_done']:
            domains_done.append("prayer")
        if raw['bible_done']:
            domains_done.append("Bible reading")
        if raw['workout_done']:
            domains_done.append("workout")
        if raw['journal_done']:
            domains_done.append("journaling")

        done_text = ", ".join(domains_done) if domains_done else "Nothing"
        return (
            f"{done_text} completed so far.{routine_text}"
            f" {raw['tasks_done']} tasks completed."
        )


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
        "RULES:",
        "- You MUST include these facts in your response.",
        "- You MUST NOT change their wording, meaning, or completion status.",
        "- You MUST NOT infer, assume, or override completion status.",
        "- You MUST NOT say something is complete if the fact says 'not yet'.",
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
        "=" * 60,
    ]
    return "\n".join(lines)
