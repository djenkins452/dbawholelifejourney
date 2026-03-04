"""
Baseline Policy — determines when a user has enough data for scoring.

Requires >= 14 DailyHealthSummary rows with sufficient core signals
(at least sleep OR activity, plus at least one of weight/glucose/nutrition).

Usage:
    from apps.health.services.baseline_policy import BaselinePolicy
    if BaselinePolicy.baseline_ready(user, date.today()):
        # compute health score
"""

import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

# Minimum days of data required for scoring
BASELINE_DAYS_REQUIRED = 14

# Core signal groups: at least one signal from each group required
CORE_SIGNAL_GROUPS = {
    "activity_or_sleep": ["sleep", "steps"],
    "outcome_signal": ["weight", "glucose", "nutrition"],
}


class BaselinePolicy:
    """Static methods for baseline readiness checks."""

    @staticmethod
    def baseline_ready(user, as_of_date):
        """
        Return True if user has >= BASELINE_DAYS_REQUIRED summary rows
        with sufficient core signals before as_of_date.
        """
        from apps.health.models import DailyHealthSummary

        # Count rows with at least some core signals
        qualifying_days = 0
        summaries = (
            DailyHealthSummary.objects
            .filter(
                user=user,
                summary_date__lt=as_of_date,
            )
            .order_by("-summary_date")
            .values_list("signals_present", flat=True)[:90]  # check up to 90 days back
        )

        for signals in summaries:
            if BaselinePolicy._has_core_signals(signals or []):
                qualifying_days += 1
                if qualifying_days >= BASELINE_DAYS_REQUIRED:
                    return True

        return False

    @staticmethod
    def baseline_days_available(user, as_of_date=None):
        """Return count of qualifying summary days for the user."""
        from apps.health.models import DailyHealthSummary

        if as_of_date is None:
            from django.utils import timezone
            as_of_date = timezone.now().date()

        summaries = (
            DailyHealthSummary.objects
            .filter(user=user, summary_date__lte=as_of_date)
            .values_list("signals_present", flat=True)
        )

        return sum(
            1 for signals in summaries
            if BaselinePolicy._has_core_signals(signals or [])
        )

    @staticmethod
    def days_until_baseline(user, as_of_date=None):
        """Return estimated days until baseline is ready (0 if already ready)."""
        available = BaselinePolicy.baseline_days_available(user, as_of_date)
        remaining = max(0, BASELINE_DAYS_REQUIRED - available)
        return remaining

    @staticmethod
    def baseline_message(user, as_of_date=None):
        """Return a user-facing message about baseline status."""
        days_left = BaselinePolicy.days_until_baseline(user, as_of_date)
        if days_left == 0:
            return None  # Baseline ready, no message needed
        return (
            f"Collecting baseline data — {days_left} more "
            f"{'day' if days_left == 1 else 'days'} of tracking needed "
            f"for your health score."
        )

    @staticmethod
    def _has_core_signals(signals):
        """
        Check if a day's signals list satisfies core signal requirements.
        Need at least one from each group.
        """
        for group_name, required_signals in CORE_SIGNAL_GROUPS.items():
            if not any(s in signals for s in required_signals):
                return False
        return True
