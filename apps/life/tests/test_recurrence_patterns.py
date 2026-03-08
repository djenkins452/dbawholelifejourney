"""
Comprehensive tests for the RecurrencePattern parser and RecurrenceService.

Tests cover:
- All original patterns (backward compatibility)
- New patterns: daily:<days>, every_N_unit:<spec>
- get_next_occurrence() correctness
- get_human_readable() output
- Task creation with complex patterns via RecurrenceService
"""

from datetime import date, timedelta
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from apps.life.services.recurrence import RecurrencePattern, RecurrenceService

User = get_user_model()


class TestRecurrencePatternParsing(TestCase):
    """Test that pattern strings are parsed into correct components."""

    # --- Backward compatibility: original 6 patterns ---

    def test_daily(self):
        p = RecurrencePattern('daily')
        self.assertEqual(p.pattern_type, 'daily')
        self.assertEqual(p.interval, 1)
        self.assertEqual(p.weekdays, [])

    def test_weekly(self):
        p = RecurrencePattern('weekly')
        self.assertEqual(p.pattern_type, 'weekly')
        self.assertEqual(p.interval, 1)
        self.assertEqual(p.weekdays, [])

    def test_biweekly(self):
        p = RecurrencePattern('biweekly')
        self.assertEqual(p.pattern_type, 'weekly')
        self.assertEqual(p.interval, 2)

    def test_monthly(self):
        p = RecurrencePattern('monthly')
        self.assertEqual(p.pattern_type, 'monthly')
        self.assertEqual(p.interval, 1)

    def test_yearly(self):
        p = RecurrencePattern('yearly')
        self.assertEqual(p.pattern_type, 'yearly')
        self.assertEqual(p.interval, 1)

    def test_annually(self):
        p = RecurrencePattern('annually')
        self.assertEqual(p.pattern_type, 'yearly')

    def test_every_weekday(self):
        p = RecurrencePattern('every_weekday')
        self.assertEqual(p.pattern_type, 'weekly')
        self.assertEqual(sorted(p.weekdays), [0, 1, 2, 3, 4])

    def test_weekdays_alias(self):
        p = RecurrencePattern('weekdays')
        self.assertEqual(p.pattern_type, 'weekly')
        self.assertEqual(sorted(p.weekdays), [0, 1, 2, 3, 4])

    # --- Existing advanced patterns (backend supported, now UI-exposed) ---

    def test_weekly_specific_days(self):
        p = RecurrencePattern('weekly:mon,wed,fri')
        self.assertEqual(p.pattern_type, 'weekly')
        self.assertEqual(sorted(p.weekdays), [0, 2, 4])

    def test_monthly_specific_day(self):
        p = RecurrencePattern('monthly:15')
        self.assertEqual(p.pattern_type, 'monthly')
        self.assertEqual(p.day_of_month, 15)

    def test_monthly_last_day(self):
        p = RecurrencePattern('monthly:last')
        self.assertEqual(p.pattern_type, 'monthly')
        self.assertEqual(p.day_of_month, 'last')

    def test_monthly_first_monday(self):
        p = RecurrencePattern('monthly:first_monday')
        self.assertEqual(p.pattern_type, 'monthly')
        self.assertEqual(p.week_of_month, 1)
        self.assertEqual(p.weekdays, [0])  # Monday = 0

    def test_monthly_last_friday(self):
        p = RecurrencePattern('monthly:last_friday')
        self.assertEqual(p.pattern_type, 'monthly')
        self.assertEqual(p.week_of_month, -1)
        self.assertEqual(p.weekdays, [4])  # Friday = 4

    def test_monthly_second_tuesday(self):
        p = RecurrencePattern('monthly:second_tuesday')
        self.assertEqual(p.pattern_type, 'monthly')
        self.assertEqual(p.week_of_month, 2)
        self.assertEqual(p.weekdays, [1])  # Tuesday = 1

    # --- New patterns ---

    def test_daily_specific_days(self):
        p = RecurrencePattern('daily:mon,wed,fri')
        self.assertEqual(p.pattern_type, 'daily')
        self.assertEqual(p.interval, 1)
        self.assertEqual(sorted(p.weekdays), [0, 2, 4])

    def test_daily_mon_through_sat(self):
        p = RecurrencePattern('daily:mon,tue,wed,thu,fri,sat')
        self.assertEqual(p.pattern_type, 'daily')
        self.assertEqual(sorted(p.weekdays), [0, 1, 2, 3, 4, 5])

    def test_every_3_days(self):
        p = RecurrencePattern('every_3_days')
        self.assertEqual(p.pattern_type, 'daily')
        self.assertEqual(p.interval, 3)

    def test_every_2_weeks(self):
        p = RecurrencePattern('every_2_weeks')
        self.assertEqual(p.pattern_type, 'weekly')
        self.assertEqual(p.interval, 2)

    def test_every_2_weeks_with_days(self):
        p = RecurrencePattern('every_2_weeks:mon,wed,fri')
        self.assertEqual(p.pattern_type, 'weekly')
        self.assertEqual(p.interval, 2)
        self.assertEqual(sorted(p.weekdays), [0, 2, 4])

    def test_every_3_months(self):
        p = RecurrencePattern('every_3_months')
        self.assertEqual(p.pattern_type, 'monthly')
        self.assertEqual(p.interval, 3)

    def test_every_2_months_day_15(self):
        p = RecurrencePattern('every_2_months:15')
        self.assertEqual(p.pattern_type, 'monthly')
        self.assertEqual(p.interval, 2)
        self.assertEqual(p.day_of_month, 15)

    def test_every_2_months_first_monday(self):
        p = RecurrencePattern('every_2_months:first_monday')
        self.assertEqual(p.pattern_type, 'monthly')
        self.assertEqual(p.interval, 2)
        self.assertEqual(p.week_of_month, 1)
        self.assertEqual(p.weekdays, [0])

    def test_every_2_months_last(self):
        p = RecurrencePattern('every_2_months:last')
        self.assertEqual(p.pattern_type, 'monthly')
        self.assertEqual(p.interval, 2)
        self.assertEqual(p.day_of_month, 'last')

    def test_every_2_years(self):
        p = RecurrencePattern('every_2_years')
        self.assertEqual(p.pattern_type, 'yearly')
        self.assertEqual(p.interval, 2)

    def test_invalid_pattern(self):
        p = RecurrencePattern('gibberish')
        self.assertIsNone(p.pattern_type)

    def test_case_insensitive(self):
        p = RecurrencePattern('Weekly:Mon,Wed,Fri')
        self.assertEqual(p.pattern_type, 'weekly')
        self.assertEqual(sorted(p.weekdays), [0, 2, 4])


class TestGetNextOccurrence(TestCase):
    """Test get_next_occurrence() correctness for all pattern types."""

    def test_daily_next(self):
        p = RecurrencePattern('daily')
        result = p.get_next_occurrence(date(2026, 2, 27))
        self.assertEqual(result, date(2026, 2, 28))

    def test_daily_specific_days_skips_excluded(self):
        """daily:mon,wed,fri from a Wednesday should go to Friday."""
        p = RecurrencePattern('daily:mon,wed,fri')
        # 2026-02-25 is a Wednesday
        result = p.get_next_occurrence(date(2026, 2, 25))
        # Next matching day after Wed is Fri = Feb 27
        self.assertEqual(result, date(2026, 2, 27))

    def test_daily_specific_days_wraps_week(self):
        """daily:mon,wed from a Wednesday should go to next Monday."""
        p = RecurrencePattern('daily:mon,wed')
        # 2026-02-25 is Wednesday, next match is Mon 2026-03-02
        result = p.get_next_occurrence(date(2026, 2, 25))
        self.assertEqual(result, date(2026, 3, 2))

    def test_daily_mon_through_sat(self):
        """daily:mon,tue,wed,thu,fri,sat from Saturday should skip Sunday."""
        p = RecurrencePattern('daily:mon,tue,wed,thu,fri,sat')
        # 2026-02-28 is Saturday
        result = p.get_next_occurrence(date(2026, 2, 28))
        # Should skip Sunday (Mar 1) and go to Monday (Mar 2)
        self.assertEqual(result, date(2026, 3, 2))

    def test_weekly_no_days(self):
        p = RecurrencePattern('weekly')
        result = p.get_next_occurrence(date(2026, 2, 27))
        self.assertEqual(result, date(2026, 3, 6))

    def test_weekly_specific_days(self):
        """weekly:mon,fri from Wednesday should go to Friday."""
        p = RecurrencePattern('weekly:mon,fri')
        # 2026-02-25 is Wednesday
        result = p.get_next_occurrence(date(2026, 2, 25))
        self.assertEqual(result, date(2026, 2, 27))  # Friday

    def test_biweekly(self):
        p = RecurrencePattern('biweekly')
        result = p.get_next_occurrence(date(2026, 2, 27))
        self.assertEqual(result, date(2026, 3, 13))

    def test_every_2_weeks_with_days(self):
        """every_2_weeks:mon,fri from a Friday should find Monday in next-next week."""
        p = RecurrencePattern('every_2_weeks:mon,fri')
        # 2026-02-27 is Friday. Rest of this week: Sat, Sun (no match).
        # Jump 1 week forward to Mon Mar 9
        result = p.get_next_occurrence(date(2026, 2, 27))
        self.assertEqual(result, date(2026, 3, 9))

    def test_monthly_same_day(self):
        p = RecurrencePattern('monthly')
        result = p.get_next_occurrence(date(2026, 1, 15))
        self.assertEqual(result, date(2026, 2, 15))

    def test_monthly_specific_day(self):
        p = RecurrencePattern('monthly:15')
        result = p.get_next_occurrence(date(2026, 1, 20))
        self.assertEqual(result, date(2026, 2, 15))

    def test_monthly_last_day(self):
        p = RecurrencePattern('monthly:last')
        result = p.get_next_occurrence(date(2026, 1, 31))
        self.assertEqual(result, date(2026, 2, 28))

    def test_monthly_first_monday(self):
        p = RecurrencePattern('monthly:first_monday')
        # From Jan 15, next month first Monday is Feb 2
        result = p.get_next_occurrence(date(2026, 1, 15))
        self.assertEqual(result, date(2026, 2, 2))

    def test_monthly_last_friday(self):
        p = RecurrencePattern('monthly:last_friday')
        result = p.get_next_occurrence(date(2026, 1, 15))
        self.assertEqual(result, date(2026, 2, 27))

    def test_every_2_months_day_15(self):
        p = RecurrencePattern('every_2_months:15')
        result = p.get_next_occurrence(date(2026, 1, 15))
        self.assertEqual(result, date(2026, 3, 15))

    def test_every_3_months_last(self):
        p = RecurrencePattern('every_3_months:last')
        result = p.get_next_occurrence(date(2026, 1, 31))
        self.assertEqual(result, date(2026, 4, 30))

    def test_yearly(self):
        p = RecurrencePattern('yearly')
        result = p.get_next_occurrence(date(2026, 2, 27))
        self.assertEqual(result, date(2027, 2, 27))

    def test_every_2_years(self):
        p = RecurrencePattern('every_2_years')
        result = p.get_next_occurrence(date(2026, 2, 27))
        self.assertEqual(result, date(2028, 2, 27))

    def test_every_3_days(self):
        p = RecurrencePattern('every_3_days')
        result = p.get_next_occurrence(date(2026, 2, 27))
        self.assertEqual(result, date(2026, 3, 2))

    def test_invalid_pattern_returns_none(self):
        p = RecurrencePattern('invalid')
        self.assertIsNone(p.get_next_occurrence(date(2026, 2, 27)))

    def test_monthly_day_31_in_short_month(self):
        """monthly:31 in February should use last day of month."""
        p = RecurrencePattern('monthly:31')
        result = p.get_next_occurrence(date(2026, 1, 31))
        self.assertEqual(result, date(2026, 2, 28))

    def test_string_date_input(self):
        """get_next_occurrence should accept string dates."""
        p = RecurrencePattern('daily')
        result = p.get_next_occurrence('2026-02-27')
        self.assertEqual(result, date(2026, 2, 28))


class TestGetOccurrences(TestCase):
    """Test get_occurrences() range generation."""

    def test_daily_range(self):
        p = RecurrencePattern('daily')
        occs = p.get_occurrences(date(2026, 2, 1), date(2026, 2, 5))
        self.assertEqual(len(occs), 5)
        self.assertEqual(occs[0], date(2026, 2, 1))
        self.assertEqual(occs[-1], date(2026, 2, 5))

    def test_weekly_range(self):
        p = RecurrencePattern('weekly')
        occs = p.get_occurrences(date(2026, 2, 1), date(2026, 3, 1))
        self.assertEqual(len(occs), 5)  # Feb 1, 8, 15, 22, Mar 1

    def test_daily_specific_days_range(self):
        """daily:mon,wed,fri should only include those days."""
        p = RecurrencePattern('daily:mon,wed,fri')
        occs = p.get_occurrences(date(2026, 2, 2), date(2026, 2, 15))
        # Feb 2 is Mon, should get Mon/Wed/Fri for 2 weeks
        for occ in occs:
            self.assertIn(occ.weekday(), [0, 2, 4])

    def test_max_count_limit(self):
        p = RecurrencePattern('daily')
        occs = p.get_occurrences(date(2026, 1, 1), date(2027, 12, 31), max_count=10)
        self.assertEqual(len(occs), 10)


class TestGetHumanReadable(TestCase):
    """Test human-readable summary strings."""

    def test_daily(self):
        self.assertEqual(RecurrencePattern('daily').get_human_readable(), 'Daily')

    def test_weekly(self):
        self.assertEqual(RecurrencePattern('weekly').get_human_readable(), 'Weekly')

    def test_monthly(self):
        self.assertEqual(RecurrencePattern('monthly').get_human_readable(), 'Monthly')

    def test_yearly(self):
        self.assertEqual(RecurrencePattern('yearly').get_human_readable(), 'Yearly')

    def test_every_weekday(self):
        result = RecurrencePattern('every_weekday').get_human_readable()
        self.assertIn('weekday', result.lower())

    def test_weekly_specific_days(self):
        result = RecurrencePattern('weekly:mon,wed,fri').get_human_readable()
        self.assertIn('Mon', result)
        self.assertIn('Wed', result)
        self.assertIn('Fri', result)

    def test_every_2_weeks(self):
        result = RecurrencePattern('every_2_weeks').get_human_readable()
        self.assertIn('2 weeks', result)

    def test_every_3_months_day_15(self):
        result = RecurrencePattern('every_3_months:15').get_human_readable()
        self.assertIn('3 months', result)
        self.assertIn('15', result)

    def test_monthly_first_monday(self):
        result = RecurrencePattern('monthly:first_monday').get_human_readable()
        self.assertIn('first', result)
        self.assertIn('Mon', result)

    def test_monthly_last(self):
        result = RecurrencePattern('monthly:last').get_human_readable()
        self.assertIn('last day', result)

    def test_daily_specific_days(self):
        result = RecurrencePattern('daily:mon,wed,fri').get_human_readable()
        self.assertIn('Mon', result)
        self.assertIn('Fri', result)

    def test_every_2_years(self):
        result = RecurrencePattern('every_2_years').get_human_readable()
        self.assertIn('2 years', result)

    def test_invalid_returns_original(self):
        self.assertEqual(RecurrencePattern('gibberish').get_human_readable(), 'gibberish')


class TestRecurrenceServiceIntegration(TestCase):
    """Test RecurrenceService with complex patterns."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
        )

    def test_complete_daily_specific_days_creates_next(self):
        """Completing a daily:mon,wed,fri task creates next occurrence on correct day."""
        from apps.life.models import Task
        # 2026-02-25 is Wednesday
        task = Task.objects.create(
            user=self.user,
            title='Test daily specific',
            is_recurring=True,
            recurrence_pattern='daily:mon,wed,fri',
            start_date=date(2026, 2, 23),
            due_date=date(2026, 2, 25),
        )
        task.mark_complete()

        next_task = Task.objects.filter(
            user=self.user, title='Test daily specific',
            completion_status='pending'
        ).first()
        self.assertIsNotNone(next_task)
        # Next occurrence after Wed should be Fri Feb 27
        self.assertEqual(next_task.due_date, date(2026, 2, 27))
        self.assertEqual(next_task.recurrence_pattern, 'daily:mon,wed,fri')

    def test_complete_every_2_weeks_creates_next(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Biweekly task',
            is_recurring=True,
            recurrence_pattern='every_2_weeks',
            start_date=date(2026, 2, 27),
            due_date=date(2026, 2, 27),
        )
        task.mark_complete()

        next_task = Task.objects.filter(
            user=self.user, title='Biweekly task',
            completion_status='pending'
        ).first()
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task.due_date, date(2026, 3, 13))

    def test_complete_monthly_first_monday_creates_next(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='First Monday task',
            is_recurring=True,
            recurrence_pattern='monthly:first_monday',
            start_date=date(2026, 2, 2),
            due_date=date(2026, 2, 2),
        )
        task.mark_complete()

        next_task = Task.objects.filter(
            user=self.user, title='First Monday task',
            completion_status='pending'
        ).first()
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task.due_date, date(2026, 3, 2))

    def test_end_date_stops_recurrence(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Ending task',
            is_recurring=True,
            recurrence_pattern='weekly',
            start_date=date(2026, 2, 20),
            end_date=date(2026, 2, 25),
            due_date=date(2026, 2, 20),
        )
        task.mark_complete()

        next_task = Task.objects.filter(
            user=self.user, title='Ending task',
            completion_status='pending'
        ).first()
        # Next would be Feb 27, which is past end_date Feb 25
        self.assertIsNone(next_task)

    def test_duplicate_prevention(self):
        """Toggling complete/incomplete shouldn't create duplicates."""
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Toggle test',
            is_recurring=True,
            recurrence_pattern='daily',
            start_date=date(2026, 2, 27),
            due_date=date(2026, 2, 27),
        )
        task.mark_complete()
        task.mark_incomplete()
        task.mark_complete()

        next_tasks = Task.objects.filter(
            user=self.user, title='Toggle test',
            completion_status='pending'
        )
        self.assertEqual(next_tasks.count(), 1)
