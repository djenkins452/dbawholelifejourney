# ==============================================================================
# File: apps/core/tests/test_user_local_temporal_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: CI guard — registered user-calendar services must not compute dates
#              independently of the canonical user-local temporal authority
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-23
# ==============================================================================
"""
User-local temporal contract — CI guard.

Deliberately an **allow-list / semantic registration** design, not a broad regex sweep.
A blanket ban on `timezone.now()` would be wrong: the audit classified 212 truth-layer
temporal sites and **79 are Category A (system instant)** and **27 Category E
(business schedule)**, where server/UTC time is CORRECT. Only Category B (user-local
calendar truth) and C (user-local rolling period) must use the user's calendar.

So a service earns its way onto `USER_CALENDAR_SERVICES` when it has been *classified*
as answering a user-calendar question. Inside those files, deriving a calendar date from
a server/UTC clock is a defect and fails here. Everything else is untouched.

Register a module when you certify it — that is the same "certification precedes
expansion" discipline the calendar-day milestone used.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[3]

# Modules CERTIFIED as answering user-calendar questions (Category B/C).
# Adding a module here asserts: every calendar date it derives is the USER's.
USER_CALENDAR_SERVICES = [
    "apps/life/services/task_queries.py",          # due today / overdue / due tomorrow
    "apps/ai/cos_services/history_search.py",      # rolling history windows
    "apps/ai/cos_services/metric_date.py",         # metric on a calendar date
    "apps/ai/cos_services/domain_history.py",      # date-scoped history retrieval
    "apps/core/truth/calendar_day.py",             # the authority itself
]

# Server/UTC clock reads that would silently produce a NON-user calendar date.
FORBIDDEN = re.compile(
    r"(timezone\.localdate\(\)"
    r"|timezone\.now\(\)\s*\.date\(\)"
    r"|datetime\.now\(\)\s*\.date\(\)"
    r"|(?<![\w.])date\.today\(\))"
)

# Intentional, documented exceptions — each must carry an inline justification.
# file -> reason
EXCEPTIONS = {
    # `_today(user=None)` keeps a server-date fallback for the no-user case, which the
    # search path never hits; the user-local branch is taken whenever a user is present
    # and is asserted by test_task_user_local_dates.HistorySearchWindowTests.
    "apps/ai/cos_services/history_search.py": 1,
}


def _forbidden_hits(path):
    """Forbidden clock reads in real CODE only.

    Comments and string literals are stripped first — otherwise a docstring that
    *explains* the defect (as these modules' do) would fail the very gate it documents.
    """
    import io
    import tokenize
    src = path.read_text()
    try:
        code_lines = {}
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            n = tok.start[0]
            code_lines[n] = code_lines.get(n, "") + tok.string
    except (tokenize.TokenError, IndentationError):   # pragma: no cover - defensive
        code_lines = dict(enumerate(src.split("\n"), 1))
    return [(n, line.strip()) for n, line in sorted(code_lines.items())
            if FORBIDDEN.search(line)]


class UserLocalTemporalContractTests(SimpleTestCase):

    def test_registered_services_derive_dates_from_the_user_calendar(self):
        offenders = []
        for rel in USER_CALENDAR_SERVICES:
            path = REPO / rel
            if not path.exists():
                offenders.append(f"{rel}: REGISTERED BUT MISSING")
                continue
            hits = _forbidden_hits(path)
            allowed = EXCEPTIONS.get(rel, 0)
            if len(hits) > allowed:
                for n, line in hits:
                    offenders.append(f"{rel}:{n}  {line[:90]}")
        self.assertEqual(
            offenders, [],
            "These CERTIFIED user-calendar services derive a date from the server/UTC "
            "clock. Use apps.core.truth.calendar_day (today/now/day_bounds/resolve) so "
            "the date is the USER's:\n  " + "\n  ".join(offenders))

    def test_registered_services_actually_reach_the_authority(self):
        """Registration is not a comment — the file must really consume the authority
        (directly, or via the user-local helpers it composes)."""
        uses = re.compile(r"calendar_day|get_user_today|get_user_now|_user_today"
                          r"|_get_user_tz|user_today")
        missing = [rel for rel in USER_CALENDAR_SERVICES
                   if (REPO / rel).exists() and not uses.search((REPO / rel).read_text())]
        self.assertEqual(missing, [],
                         f"registered but never consults the user-local authority: {missing}")

    def test_the_authority_owns_no_duplicate_date_math(self):
        """`calendar_day` must stay a façade — it composes, it does not re-implement.
        A second date engine is exactly what this program exists to prevent."""
        src = (REPO / "apps/core/truth/calendar_day.py").read_text()
        for delegated in ("get_user_today", "get_user_now", "_get_user_tz",
                          "resolve_period", "resolve_date_expression", "daypart"):
            self.assertIn(delegated, src,
                          f"calendar_day stopped delegating to {delegated}")
        # It must not grow its own weekday/period arithmetic.
        self.assertNotIn("weekday()", src)
        self.assertNotIn("isocalendar()", src)

    def test_exceptions_are_documented(self):
        """Every allowance must name the file it applies to and stay small."""
        for rel, count in EXCEPTIONS.items():
            self.assertIn(rel, USER_CALENDAR_SERVICES,
                          f"exception for unregistered file: {rel}")
            self.assertLessEqual(count, 2, f"exception budget too loose for {rel}")
