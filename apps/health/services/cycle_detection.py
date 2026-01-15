"""
Cycle Detection Service

Automatically detects period start/end from daily logs and manages Cycle records.
This service is triggered when daily logs are created or updated, analyzing
flow patterns to determine cycle boundaries.

Key Features:
- Detects period start when flow changes from none to any level
- Detects period end after 2+ consecutive days of no flow
- Creates new Cycle records when periods start
- Updates period_end_date when periods end
- Handles spotting intelligently (doesn't count as new period)
- Closes previous cycles when new ones begin

Usage:
    from apps.health.services.cycle_detection import CycleDetectionService

    # After saving a daily log
    service = CycleDetectionService(user)
    service.process_daily_log(daily_log)
"""

from datetime import date, timedelta
from typing import Optional, Tuple

from django.db.models import Q

from ..models import Cycle, CycleDailyLog


class CycleDetectionService:
    """
    Service for detecting menstrual cycle boundaries from daily logs.

    The service analyzes flow level patterns to automatically create
    and manage Cycle records.
    """

    # Flow levels that indicate period has started
    PERIOD_FLOW_LEVELS = ["light", "medium", "heavy"]

    # Spotting is tracked but doesn't count as period start/end
    SPOTTING_LEVEL = "spotting"

    # No flow level
    NO_FLOW_LEVEL = "none"

    # Number of consecutive no-flow days to consider period ended
    DAYS_TO_END_PERIOD = 2

    def __init__(self, user):
        """
        Initialize the service for a specific user.

        Args:
            user: The User instance to process cycles for
        """
        self.user = user

    def process_daily_log(self, daily_log: CycleDailyLog) -> dict:
        """
        Process a daily log and update cycles accordingly.

        This is the main entry point called after a daily log is saved.

        Args:
            daily_log: The CycleDailyLog instance that was just saved

        Returns:
            dict with action taken and any cycle changes
        """
        result = {
            "action": None,
            "cycle_created": None,
            "cycle_updated": None,
            "period_detected": False,
            "period_ended": False,
        }

        flow_level = daily_log.flow_level
        log_date = daily_log.log_date

        # Check if this is a period day (actual flow, not just spotting)
        is_period_day = flow_level in self.PERIOD_FLOW_LEVELS

        if is_period_day:
            # Check if this might be the start of a period
            period_start_result = self._check_period_start(log_date)
            if period_start_result["is_new_period"]:
                cycle = self._create_new_cycle(log_date)
                result["action"] = "period_started"
                result["cycle_created"] = cycle.id
                result["period_detected"] = True
        elif flow_level == self.NO_FLOW_LEVEL:
            # Check if this might be the end of a period
            period_end_result = self._check_period_end(log_date)
            if period_end_result["period_ended"]:
                cycle = self._update_period_end(period_end_result["period_end_date"])
                if cycle:
                    result["action"] = "period_ended"
                    result["cycle_updated"] = cycle.id
                    result["period_ended"] = True

        return result

    def _check_period_start(self, log_date: date) -> dict:
        """
        Check if the given date represents the start of a new period.

        A period is considered to start when:
        1. There's flow on this day (light/medium/heavy)
        2. The previous day had no flow or spotting
        3. Not currently in an active period (or last period ended)

        Args:
            log_date: The date to check

        Returns:
            dict with is_new_period bool and related info
        """
        result = {
            "is_new_period": False,
            "reason": None,
        }

        # Get the previous day's log
        prev_date = log_date - timedelta(days=1)
        prev_log = CycleDailyLog.objects.filter(
            user=self.user,
            log_date=prev_date
        ).first()

        # If there's no previous log, or previous was no flow/spotting
        prev_was_no_flow = (
            prev_log is None or
            prev_log.flow_level in [self.NO_FLOW_LEVEL, self.SPOTTING_LEVEL]
        )

        if not prev_was_no_flow:
            result["reason"] = "previous_day_had_flow"
            return result

        # Check if there's already an ongoing cycle that hasn't ended
        ongoing_cycle = Cycle.objects.filter(
            user=self.user,
            end_date__isnull=True
        ).first()

        if ongoing_cycle:
            # Check if the current cycle's period has ended
            # (2+ days since last flow)
            last_flow_date = self._get_last_flow_date(ongoing_cycle.start_date)
            if last_flow_date:
                days_since_flow = (log_date - last_flow_date).days
                if days_since_flow < self.DAYS_TO_END_PERIOD:
                    # Still in current period, not a new one
                    result["reason"] = "still_in_current_period"
                    return result

        # This is a new period!
        result["is_new_period"] = True
        result["reason"] = "flow_started_after_break"
        return result

    def _check_period_end(self, log_date: date) -> dict:
        """
        Check if the period has ended based on consecutive no-flow days.

        A period is considered ended when there are 2+ consecutive days
        of no flow after the last day with flow.

        Args:
            log_date: The date to check (should be a no-flow day)

        Returns:
            dict with period_ended bool and period_end_date
        """
        result = {
            "period_ended": False,
            "period_end_date": None,
            "reason": None,
        }

        # Get the current ongoing cycle
        ongoing_cycle = Cycle.objects.filter(
            user=self.user,
            end_date__isnull=True
        ).first()

        if not ongoing_cycle:
            result["reason"] = "no_ongoing_cycle"
            return result

        # Check if period_end_date is already set
        if ongoing_cycle.period_end_date:
            result["reason"] = "period_already_ended"
            return result

        # Find the last day with actual flow (not spotting)
        last_flow_log = CycleDailyLog.objects.filter(
            user=self.user,
            log_date__gte=ongoing_cycle.start_date,
            log_date__lte=log_date,
            flow_level__in=self.PERIOD_FLOW_LEVELS
        ).order_by("-log_date").first()

        if not last_flow_log:
            result["reason"] = "no_flow_in_cycle"
            return result

        # Count consecutive no-flow days after last flow
        days_since_flow = (log_date - last_flow_log.log_date).days

        if days_since_flow >= self.DAYS_TO_END_PERIOD:
            result["period_ended"] = True
            result["period_end_date"] = last_flow_log.log_date
            result["reason"] = f"{days_since_flow}_days_no_flow"

        return result

    def _create_new_cycle(self, start_date: date) -> Cycle:
        """
        Create a new Cycle record and close any previous ongoing cycle.

        Args:
            start_date: The first day of the new period

        Returns:
            The newly created Cycle instance
        """
        # Close any existing ongoing cycle
        previous_cycle = Cycle.objects.filter(
            user=self.user,
            end_date__isnull=True
        ).first()

        if previous_cycle:
            # End the previous cycle (day before new cycle starts)
            previous_cycle.end_date = start_date - timedelta(days=1)

            # If period_end_date wasn't set, estimate it
            if not previous_cycle.period_end_date:
                last_flow = self._get_last_flow_date(
                    previous_cycle.start_date,
                    start_date - timedelta(days=1)
                )
                if last_flow:
                    previous_cycle.period_end_date = last_flow

            previous_cycle.save()

        # Create the new cycle
        new_cycle = Cycle.objects.create(
            user=self.user,
            start_date=start_date,
        )

        return new_cycle

    def _update_period_end(self, period_end_date: date) -> Optional[Cycle]:
        """
        Update the current cycle's period_end_date.

        Args:
            period_end_date: The last day of the period

        Returns:
            The updated Cycle instance or None if no ongoing cycle
        """
        ongoing_cycle = Cycle.objects.filter(
            user=self.user,
            end_date__isnull=True
        ).first()

        if not ongoing_cycle:
            return None

        ongoing_cycle.period_end_date = period_end_date
        ongoing_cycle.save()

        return ongoing_cycle

    def _get_last_flow_date(
        self,
        start_date: date,
        end_date: Optional[date] = None
    ) -> Optional[date]:
        """
        Get the last date with actual flow within a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range (optional, defaults to today)

        Returns:
            The date of last flow or None
        """
        if end_date is None:
            end_date = date.today()

        last_flow_log = CycleDailyLog.objects.filter(
            user=self.user,
            log_date__gte=start_date,
            log_date__lte=end_date,
            flow_level__in=self.PERIOD_FLOW_LEVELS
        ).order_by("-log_date").first()

        return last_flow_log.log_date if last_flow_log else None

    def recalculate_cycles(self) -> dict:
        """
        Recalculate all cycles from scratch based on daily logs.

        This is useful for fixing inconsistencies or after importing data.
        WARNING: This will delete and recreate all cycle records!

        Returns:
            dict with counts of cycles created
        """
        # Get all daily logs ordered by date
        daily_logs = CycleDailyLog.objects.filter(
            user=self.user
        ).order_by("log_date")

        if not daily_logs.exists():
            return {"cycles_created": 0, "message": "No daily logs found"}

        # Delete existing cycles (soft delete)
        existing_cycles = Cycle.objects.filter(user=self.user)
        for cycle in existing_cycles:
            cycle.soft_delete()

        # Process each log to detect periods
        cycles_created = 0
        current_cycle = None
        in_period = False
        consecutive_no_flow = 0

        for log in daily_logs:
            flow = log.flow_level
            is_flow = flow in self.PERIOD_FLOW_LEVELS

            if is_flow:
                consecutive_no_flow = 0
                if not in_period:
                    # Start new cycle
                    current_cycle = Cycle.objects.create(
                        user=self.user,
                        start_date=log.log_date,
                    )
                    cycles_created += 1
                    in_period = True
            elif flow == self.NO_FLOW_LEVEL:
                if in_period:
                    consecutive_no_flow += 1
                    if consecutive_no_flow >= self.DAYS_TO_END_PERIOD:
                        # Period ended
                        if current_cycle:
                            last_flow = self._get_last_flow_date(
                                current_cycle.start_date,
                                log.log_date
                            )
                            current_cycle.period_end_date = last_flow
                            current_cycle.save()
                        in_period = False
                        consecutive_no_flow = 0

        return {
            "cycles_created": cycles_created,
            "message": f"Recalculated {cycles_created} cycles from daily logs",
        }


def process_daily_log_signal(sender, instance, created, **kwargs):
    """
    Signal handler for CycleDailyLog post_save.

    Automatically processes the daily log to detect cycle boundaries.

    Args:
        sender: The model class (CycleDailyLog)
        instance: The actual CycleDailyLog instance
        created: Boolean indicating if this is a new record
        **kwargs: Additional signal arguments
    """
    # Only process if the user has cycle tracking enabled
    from ..models import CycleSettings
    try:
        settings = CycleSettings.objects.get(user=instance.user)
        if not settings.is_enabled:
            return
    except CycleSettings.DoesNotExist:
        return

    service = CycleDetectionService(instance.user)
    service.process_daily_log(instance)
