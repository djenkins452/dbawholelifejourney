# =============================================================================
# File: apps/journal/services/journal_writes.py
# Purpose: THE canonical journal-entry recording mechanism. One place creates a
#   JournalEntry so every caller (the CoS create_journal_entry action, the execution
#   reconciliation workflow) records the same way — model save handles HTML sanitize /
#   plain-text shadow / word count / title default, and the JournalEntry post_save
#   signals fire the standard journal intelligence regardless of caller.
#
#   `entry_date` is the day the entry is ABOUT (WLJ records when something ACTUALLY
#   happened, not when it was entered) — defaults to today, never the future. This is
#   what makes a retroactive "I journaled yesterday" entry belong to yesterday, which in
#   turn (single source of truth: FaithQueries/JournalQueries.has_entry_on) reconciles
#   yesterday's journal execution — no second completion mechanism.
# =============================================================================
import logging
from datetime import date as _date

logger = logging.getLogger(__name__)


def _coerce_date(value):
    if value is None:
        return None
    if isinstance(value, _date):
        return value
    try:
        return _date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def create_entry(user, *, body, entry_date=None, title=None, mood="okay"):
    """Create ONE journal entry for `user`, dated to `entry_date` (default: the user's
    today; a future date is clamped to today). Returns the saved JournalEntry. The
    model's save() sanitizes the rich-text body, derives the plain shadow, sets the word
    count, and defaults the title; post_save signals fire journal intelligence."""
    from apps.journal.models import JournalEntry
    from apps.core.utils import get_user_today

    today = None
    try:
        today = get_user_today(user)
    except Exception:
        today = _date.today()

    when = _coerce_date(entry_date) or today
    if when > today:            # never record the future — reconciliation is about the past
        when = today

    return JournalEntry.objects.create(
        user=user, body=body or "", entry_date=when,
        title=(title or ""), mood=(mood or "okay"))
