# ==============================================================================
# File: apps/core/ai_events/adapters/finance.py
# Project: Whole Life Journey
# Description: Finance/transaction event adapter
# Created: 2026-03-28
# ==============================================================================
"""Finance Event Adapter. Reads Transaction directly."""

import logging
from datetime import date
from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    from apps.finance.models import Transaction
    entries = Transaction.objects.filter(
        user=user, date__gte=start_date, date__lte=end_date,
    ).select_related('category').order_by('date')
    return [_to_event(e) for e in entries]


def get_latest(user, count=5):
    from apps.finance.models import Transaction
    return [_to_event(e) for e in Transaction.objects.filter(user=user).order_by('-date')[:count]]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def _to_event(entry):
    from django.utils import timezone as tz
    amount = float(entry.amount)
    is_income = amount > 0
    cat_name = entry.category.name if entry.category_id else ''
    desc = entry.description or ''

    label = f"{'Income' if is_income else 'Expense'} — ${abs(amount):.2f}"
    if desc:
        label += f" ({desc})"

    timestamp = tz.make_aware(
        tz.datetime.combine(entry.date, tz.datetime.min.time()),
        tz.get_default_timezone(),
    )

    return EventRecord(
        domain='finance', event_type='transaction', timestamp=timestamp,
        label=label, status='logged',
        detail={
            'amount': amount, 'description': desc,
            'category': cat_name,
            'is_income': is_income, 'date': str(entry.date),
        },
        source_model='Transaction', source_id=entry.pk,
    )


def _enforce_bounds(s, e):
    if e < s: raise ValueError("end_date must be >= start_date")
    if (e - s).days > MAX_LOOKBACK_DAYS: raise ValueError(f"Exceeds {MAX_LOOKBACK_DAYS} days")
