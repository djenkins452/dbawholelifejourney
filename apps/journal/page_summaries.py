# ==============================================================================
# File: apps/journal/page_summaries.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context PAGE-SUMMARY providers for Journal overview pages.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deterministic page-summary providers for Journal overview pages.

Registered at app-ready (see JournalConfig.ready). Each provider is user-scoped and
request-path-safe, and returns the uniform {title, content, kind} the assistant consumes
as Current Context focus — the SAME deterministic truth the page renders (via
build_journal_home_summary). Facts only; the model decides what they mean.
"""

from django.utils.dateformat import format as _dj_date

from apps.core.current_context import register_page_summary
from apps.journal.services.journal_home_summary import build_journal_home_summary


def _d(d):
    return _dj_date(d, "M j, Y") if d else "—"


@register_page_summary("journal.home")
def journal_home_summary(user, params):
    """The Journal home overview. Deterministic facts only — no verdicts."""
    facts = build_journal_home_summary(user)
    if not facts.get("total"):
        return {"title": "Journal", "kind": "journal overview",
                "content": "Journal overview — no journal entries yet."}

    lines = [
        f"Total entries: {facts['total']}",
        f"Last 7 days: {facts['this_week']} entries",
        f"Last 30 days: {facts['this_month']} entries",
        f"Current writing streak: {facts['streak']} day(s)",
        f"Most recent entry: {_d(facts['latest_entry_date'])}",
    ]
    return {"title": "Journal", "kind": "journal overview",
            "content": "Journal overview\n" + "\n".join(lines)}
