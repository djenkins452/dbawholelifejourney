# ==============================================================================
# File: apps/finance/services/finance_history.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: FinanceHistory — deterministic monthly cash-flow trend truth (spending,
#              income, net cash flow) composed from Transactions in ONE grouped query.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""FinanceHistory — the Point-in-Time History capability for Finance.

Composes the deterministic MONTHLY cash-flow series a Chief of Staff reviews before
answering "how are my finances?" — spending, income, and net cash flow over time —
straight from `Transaction` rows (the canonical record), in ONE grouped query. No new
authority: it is the History half of `FinanceDomainTruth`, the peer of `HealthHistory`.

Truth rules honored:
* MONTHLY granularity — finance's natural horizon is the month, not the day (each domain's
  History picks its own granularity, exactly as Health is daily). Buckets are calendar
  months intersecting the requested window.
* AMOUNT CONVENTION (from the model): positive = income, negative = expense. Opening-balance
  entries and transfers are EXCLUDED (they are not spending or income).
* EMPTY ≠ ZERO — only months that actually HAVE transactions become data points; a month
  with no records is UNKNOWN, never a fabricated 0. So the trend can never invent a decline.
* Values are absolute dollars for spending (a positive magnitude the model reads as
  "you spent $X"); income is the positive inflow; net is income minus spending.
"""

import logging
from datetime import date
from decimal import Decimal

from django.db.models import Case, DecimalField, Sum, When
from django.db.models.functions import TruncMonth

from apps.core.truth.history import HistoryPoint, HistorySeries
from apps.core.truth.periods import resolve_period

logger = logging.getLogger(__name__)

_ZERO = Decimal("0.00")
# metric -> (which monthly aggregate to plot). All three read the SAME grouped query.
METRICS = ("spending", "income", "net_cashflow")


def _resolve(user, period, start, end):
    """Resolve to a concrete Period — a custom (start, end) or a named window — via the ONE
    shared temporal authority (never date math here)."""
    from apps.core.utils import get_user_today
    today = get_user_today(user) or date.today()
    if start and end:
        return resolve_period("custom", today, start=start, end=end)
    return resolve_period(period or "this_year", today)


def _monthly_rows(user, p):
    """ONE grouped query: per calendar month in the window, the income (positive) and expense
    (negative) sums, transfers + opening balances excluded. Only months WITH transactions
    appear (empty≠zero)."""
    # ONE population authority — Budget, metrics, the dashboard, and DomainTruth read the
    # same definition, so they can no longer disagree about transfers or opening balances
    # (F4 convergence; Article III.1).
    from apps.finance.services.attribution_population import financial_activity
    qs = financial_activity(user, start=p.start, end=p.end)
    rows = (qs.annotate(mo=TruncMonth("date"))
              .values("mo")
              .annotate(
                  income=Sum(Case(When(amount__gt=0, then="amount"),
                                  default=_ZERO, output_field=DecimalField())),
                  expense=Sum(Case(When(amount__lt=0, then="amount"),
                                   default=_ZERO, output_field=DecimalField())))
              .order_by("mo"))
    return rows


def _series(user, metric, period="this_year", start=None, end=None):
    p = _resolve(user, period, start, end)
    points = []
    for r in _monthly_rows(user, p):
        mo = r["mo"]
        mo_date = mo.date() if hasattr(mo, "date") else mo
        income = r["income"] or _ZERO
        expense = r["expense"] or _ZERO          # negative
        if metric == "spending":
            value = -expense                     # positive magnitude spent
        elif metric == "income":
            value = income
        else:                                    # net_cashflow
            value = income + expense
        points.append(HistoryPoint(date=mo_date, value=value))
    return HistorySeries(domain="finance", metric=metric, period=p,
                         points=tuple(points), unit="USD")


class FinanceHistory:
    """Monthly cash-flow trend series. Each classmethod returns a HistorySeries the History
    surface (get_history / get_analysis overview) consumes unchanged."""

    @staticmethod
    def spending(user, period="this_year", start=None, end=None):
        return _series(user, "spending", period, start, end)

    @staticmethod
    def income(user, period="this_year", start=None, end=None):
        return _series(user, "income", period, start, end)

    @staticmethod
    def net_cashflow(user, period="this_year", start=None, end=None):
        return _series(user, "net_cashflow", period, start, end)
