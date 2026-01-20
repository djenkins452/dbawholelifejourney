"""
Finance Module - Recurring Transaction Service

Handles processing and generation of recurring transactions.
Uses the Life module's RecurrencePattern for consistent pattern handling.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any

from django.db import transaction as db_transaction
from django.utils import timezone

from apps.core.utils import get_user_today
from apps.life.services.recurrence import RecurrencePattern


class RecurringTransactionService:
    """
    Service for managing recurring transactions.

    Provides methods for:
    - Processing due recurring transactions
    - Getting upcoming transactions
    - Skipping occurrences
    - Bulk operations
    """

    @staticmethod
    def get_due_recurring_transactions(user=None, as_of_date=None):
        """
        Get all recurring transactions that are due for processing.

        Args:
            user: Optional user filter
            as_of_date: Date to check against (defaults to today)

        Returns:
            QuerySet of RecurringTransaction objects due for processing
        """
        from apps.finance.models import RecurringTransaction

        if as_of_date is None:
            as_of_date = timezone.now().date()

        queryset = RecurringTransaction.objects.filter(
            is_active=True,
            is_auto_post=True,
            next_due_date__lte=as_of_date,
            status='active',  # From SoftDeleteModel
        )

        if user:
            queryset = queryset.filter(user=user)

        return queryset

    @staticmethod
    def process_due_transactions(user=None, as_of_date=None):
        """
        Process all due recurring transactions and generate actual transactions.

        Args:
            user: Optional user filter
            as_of_date: Date to check against

        Returns:
            dict with 'created' count and 'errors' list
        """
        due_recurring = RecurringTransactionService.get_due_recurring_transactions(
            user=user, as_of_date=as_of_date
        )

        results = {
            'created': 0,
            'errors': [],
        }

        for recurring in due_recurring:
            try:
                with db_transaction.atomic():
                    recurring.generate_transaction()
                    results['created'] += 1
            except Exception as e:
                results['errors'].append({
                    'recurring_id': recurring.id,
                    'name': recurring.name,
                    'error': str(e),
                })

        return results

    @staticmethod
    def get_upcoming_transactions(user, days_ahead=30, include_inactive=False):
        """
        Get all upcoming recurring transactions for a user.

        Args:
            user: The user
            days_ahead: Number of days to look ahead
            include_inactive: Include inactive recurring transactions

        Returns:
            List of dicts with recurring info and next dates
        """
        from apps.finance.models import RecurringTransaction

        today = get_user_today(user)
        end_date = today + timedelta(days=days_ahead)

        queryset = RecurringTransaction.objects.filter(
            user=user,
            next_due_date__lte=end_date,
            status='active',
        )

        if not include_inactive:
            queryset = queryset.filter(is_active=True)

        upcoming = []

        for recurring in queryset:
            upcoming.append({
                'recurring': recurring,
                'next_due_date': recurring.next_due_date,
                'amount': recurring.amount,
                'signed_amount': recurring.signed_amount,
                'is_expense': recurring.is_expense,
                'is_income': recurring.is_income,
                'days_until': (recurring.next_due_date - today).days,
                'is_overdue': recurring.next_due_date < today,
                'is_due_today': recurring.next_due_date == today,
            })

        # Sort by due date
        upcoming.sort(key=lambda x: x['next_due_date'])

        return upcoming

    @staticmethod
    def get_monthly_recurring_summary(user, month_date=None):
        """
        Get a summary of expected recurring transactions for a month.

        Args:
            user: The user
            month_date: Any date within the month (defaults to current month)

        Returns:
            dict with income, expenses, net, and list of transactions
        """
        from apps.finance.models import RecurringTransaction

        if month_date is None:
            month_date = get_user_today(user)

        # Get first and last day of month
        month_start = month_date.replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)

        # Get all active recurring transactions
        recurring_list = RecurringTransaction.objects.filter(
            user=user,
            is_active=True,
            status='active',
            start_date__lte=month_end,
        ).filter(
            # Either no end date or end date is in/after this month
            end_date__isnull=True
        ) | RecurringTransaction.objects.filter(
            user=user,
            is_active=True,
            status='active',
            start_date__lte=month_end,
            end_date__gte=month_start,
        )

        transactions = []
        total_income = Decimal('0.00')
        total_expenses = Decimal('0.00')

        for recurring in recurring_list.distinct():
            # Get occurrences within this month
            pattern = RecurrencePattern(recurring.recurrence_pattern)

            # Start from either next_due_date or month_start, whichever is later
            check_date = max(recurring.next_due_date, month_start)

            # Walk through occurrences in the month
            current = check_date
            month_occurrences = []

            while current <= month_end:
                if current >= month_start:
                    month_occurrences.append(current)

                next_date = pattern.get_next_occurrence(current)
                if not next_date or next_date <= current:
                    break
                current = next_date

            for occurrence_date in month_occurrences:
                amount = recurring.signed_amount

                transactions.append({
                    'recurring': recurring,
                    'date': occurrence_date,
                    'name': recurring.name,
                    'amount': recurring.amount,
                    'signed_amount': amount,
                    'is_expense': recurring.is_expense,
                    'is_income': recurring.is_income,
                    'category': recurring.category,
                    'account': recurring.account,
                })

                if recurring.is_income:
                    total_income += recurring.amount
                else:
                    total_expenses += recurring.amount

        # Sort by date
        transactions.sort(key=lambda x: x['date'])

        return {
            'month_start': month_start,
            'month_end': month_end,
            'total_income': total_income,
            'total_expenses': total_expenses,
            'net': total_income - total_expenses,
            'transactions': transactions,
            'count': len(transactions),
        }

    @staticmethod
    def skip_occurrence(recurring, skip_date=None):
        """
        Skip the next occurrence of a recurring transaction.

        Args:
            recurring: The RecurringTransaction instance
            skip_date: The date to skip (defaults to next_due_date)

        Returns:
            The new next_due_date after skipping
        """
        if skip_date is None:
            skip_date = recurring.next_due_date

        # Simply advance to the next occurrence without generating a transaction
        next_date = recurring.calculate_next_due_date(skip_date)

        if next_date:
            recurring.next_due_date = next_date
            recurring.save(update_fields=['next_due_date', 'updated_at'])
            return next_date
        else:
            # No more occurrences
            recurring.is_active = False
            recurring.save(update_fields=['is_active', 'updated_at'])
            return None

    @staticmethod
    def post_now(recurring):
        """
        Immediately post a recurring transaction (manual trigger).

        Args:
            recurring: The RecurringTransaction instance

        Returns:
            The created Transaction instance
        """
        today = get_user_today(recurring.user)
        return recurring.generate_transaction(transaction_date=today)

    @staticmethod
    def get_reminders_for_date(user, reminder_date=None):
        """
        Get recurring transactions that need reminders on a specific date.

        Args:
            user: The user
            reminder_date: The date to check (defaults to today)

        Returns:
            List of RecurringTransaction objects needing reminders
        """
        from apps.finance.models import RecurringTransaction

        if reminder_date is None:
            reminder_date = get_user_today(user)

        # Get all active recurring with reminders enabled
        recurring_list = RecurringTransaction.objects.filter(
            user=user,
            is_active=True,
            status='active',
            remind_days_before__gt=0,
        )

        reminders = []

        for recurring in recurring_list:
            # Calculate when reminder should be sent
            reminder_trigger_date = recurring.next_due_date - timedelta(
                days=recurring.remind_days_before
            )

            if reminder_trigger_date == reminder_date:
                reminders.append(recurring)

        return reminders


def process_recurring_transactions():
    """
    Process all due recurring transactions across all users.

    This function is designed to be called by a daily cron job or
    management command.

    Returns:
        dict with total created and errors
    """
    from apps.finance.models import RecurringTransaction

    today = timezone.now().date()

    # Get all due recurring transactions
    due_recurring = RecurringTransaction.objects.filter(
        is_active=True,
        is_auto_post=True,
        next_due_date__lte=today,
        status='active',
    )

    results = {
        'total_processed': 0,
        'created': 0,
        'errors': [],
    }

    for recurring in due_recurring:
        results['total_processed'] += 1
        try:
            with db_transaction.atomic():
                recurring.generate_transaction()
                results['created'] += 1
        except Exception as e:
            results['errors'].append({
                'recurring_id': recurring.id,
                'user_id': recurring.user_id,
                'name': recurring.name,
                'error': str(e),
            })

    return results
