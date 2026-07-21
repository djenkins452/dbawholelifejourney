# ==============================================================================
# File: apps/journal/services/journal_home_summary.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic facts for the Journal home overview — the SINGLE source
#              that feeds BOTH the page render and the Current Context page summary.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""One deterministic source for the Journal home overview.

Per the Current Context contract, an overview page and its `summary:<key>` provider must
read the SAME deterministic source — never derive the numbers independently (that is the
page-vs-assistant drift class the contract eliminates). `JournalHomeView` and the
`journal.home` page-summary provider both call `build_journal_home_summary`.

Request-path-safe: a handful of indexed COUNT queries + one small distinct-date scan for
the streak. No heavy compute, no LLM, user-scoped (the query IS the ownership boundary).
"""

from datetime import timedelta


def build_journal_home_summary(user):
    """Return deterministic facts for the Journal home page (facts only — no verdicts).

    Keys: total, this_week, this_month, streak, latest_entry_date.
    """
    from apps.journal.models import JournalEntry
    from apps.core.utils import get_user_today

    today = get_user_today(user)
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    entries = JournalEntry.objects.filter(user=user)

    latest = entries.order_by("-entry_date").values_list("entry_date", flat=True).first()

    return {
        "total": entries.count(),
        "this_week": entries.filter(entry_date__gte=week_ago).count(),
        "this_month": entries.filter(entry_date__gte=month_ago).count(),
        "streak": _current_streak(entries, today),
        "latest_entry_date": latest,
    }


def _current_streak(entries, today):
    """Consecutive-day writing streak ending today (facts only). Cheap: distinct dates,
    capped scan. Mirrors the historical JournalHomeView logic — now the single source."""
    dates = entries.order_by("-entry_date").values_list("entry_date", flat=True).distinct()[:60]
    streak = 0
    expected_date = today
    for entry_date in dates:
        if entry_date == expected_date:
            streak += 1
            expected_date -= timedelta(days=1)
        elif entry_date < expected_date:
            break
    return streak
