# ==============================================================================
# File: apps/dashboard/services/daily_activity_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Unified daily activity aggregation
# Created: 2026-03-14 (Architecture Evolution Phase 2)
# ==============================================================================
"""
DailyActivityService — Unified Daily Activity

Aggregates all completed actions for a given date from domain completion records.
Returns a chronological list of everything that actually happened today.

Part of the WLJ Architecture Evolution — Layer 2 (Activity).
This is a read-time aggregation service — no new model required.
"""

import datetime as dt
import logging

from django.utils import timezone as tz_utils

logger = logging.getLogger(__name__)


class DailyActivityService:
    """
    Aggregates all completed actions for a user on a given date.

    Queries each domain's completion records:
    - Task completions
    - Medicine logs (taken)
    - Workout sessions
    - Habit completions
    - Bible reading progress
    - Journal entries
    - Health measurements (weight, glucose, blood pressure, sleep)
    - Brain training sessions

    Returns a chronological list of normalized activity dicts.
    """

    @staticmethod
    def get_daily_activity(user, date):
        """
        Returns chronological list of all completed actions for a date.

        Each item is a dict with:
            timestamp: datetime — when the action occurred
            title: str — description of the action
            domain: str — LifeDomain slug
            source_type: str — model source identifier
            source_id: str — PK of source record
            signal_class: str — verified_action or verified_measurement
        """
        activities = []

        # Collect from each domain — each collector is wrapped in try/except
        # so one domain's failure doesn't break the entire aggregation
        collectors = [
            DailyActivityService._collect_task_completions,
            DailyActivityService._collect_medicine_logs,
            DailyActivityService._collect_workout_sessions,
            DailyActivityService._collect_habit_completions,
            DailyActivityService._collect_faith_progress,
            DailyActivityService._collect_journal_entries,
            DailyActivityService._collect_weight_entries,
            DailyActivityService._collect_glucose_entries,
            DailyActivityService._collect_blood_pressure_entries,
            DailyActivityService._collect_sleep_entries,
            DailyActivityService._collect_brain_training,
        ]

        for collector in collectors:
            try:
                items = collector(user, date)
                activities.extend(items)
            except Exception as e:
                logger.warning(
                    "DailyActivityService collector %s failed: %s",
                    collector.__name__, e,
                )

        # Sort chronologically
        activities.sort(key=lambda x: x['timestamp'])

        return activities

    @staticmethod
    def get_activity_summary(user, date):
        """
        Returns a summary of today's activity by domain.

        Useful for CoS context assembly and signal generation.
        """
        activities = DailyActivityService.get_daily_activity(user, date)

        by_domain = {}
        by_signal_class = {
            'verified_action': 0,
            'verified_measurement': 0,
        }

        for item in activities:
            domain = item['domain']
            if domain not in by_domain:
                by_domain[domain] = {'count': 0, 'items': []}
            by_domain[domain]['count'] += 1
            by_domain[domain]['items'].append(item['title'])

            signal_class = item.get('signal_class', 'verified_action')
            if signal_class in by_signal_class:
                by_signal_class[signal_class] += 1

        return {
            'total_activities': len(activities),
            'by_domain': by_domain,
            'by_signal_class': by_signal_class,
        }

    # ──────────────────────────────────────────────────────────
    # Domain Collectors
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _collect_task_completions(user, date):
        """Tasks completed today."""
        from apps.life.models import Task

        tasks = Task.objects.filter(
            user=user,
            completed_at__date=date,
            completion_status='completed',
        ).only('pk', 'title', 'completed_at', 'module')

        return [
            {
                'timestamp': task.completed_at,
                'title': f"Completed: {task.title}",
                'domain': task.module or 'life',
                'source_type': 'task',
                'source_id': str(task.pk),
                'signal_class': 'verified_action',
            }
            for task in tasks
        ]

    @staticmethod
    def _collect_medicine_logs(user, date):
        """Medicine doses taken today."""
        from apps.health.models import MedicineLog

        logs = MedicineLog.objects.filter(
            user=user,
            scheduled_date=date,
            status='taken',
        ).select_related('medicine').only(
            'pk', 'taken_at', 'medicine__name',
        )

        return [
            {
                'timestamp': log.taken_at or tz_utils.make_aware(
                    dt.datetime.combine(date, dt.time(12, 0)),
                    tz_utils.get_current_timezone(),
                ),
                'title': f"Took {log.medicine.name}",
                'domain': 'health',
                'source_type': 'medicine_log',
                'source_id': str(log.pk),
                'signal_class': 'verified_action',
            }
            for log in logs
        ]

    @staticmethod
    def _collect_workout_sessions(user, date):
        """Workouts completed today."""
        from apps.health.models import WorkoutSession

        sessions = WorkoutSession.objects.filter(
            user=user,
            date=date,
        ).only('pk', 'name', 'workout_type', 'duration_minutes', 'created_at')

        return [
            {
                'timestamp': session.created_at,
                'title': f"Workout: {session.name or session.workout_type or 'Session'}",
                'domain': 'health',
                'source_type': 'workout_session',
                'source_id': str(session.pk),
                'signal_class': 'verified_action',
            }
            for session in sessions
        ]

    @staticmethod
    def _collect_habit_completions(user, date):
        """Habit entries completed today."""
        from apps.purpose.models import HabitEntry

        entries = HabitEntry.objects.filter(
            goal__user=user,
            date=date,
            completed=True,
        ).select_related('goal', 'goal__domain').only(
            'pk', 'date', 'goal__name', 'goal__domain__slug',
            'created_at',
        )

        return [
            {
                'timestamp': entry.created_at if hasattr(entry, 'created_at') and entry.created_at
                else tz_utils.make_aware(
                    dt.datetime.combine(date, dt.time(12, 0)),
                    tz_utils.get_current_timezone(),
                ),
                'title': f"Habit: {entry.goal.name}",
                'domain': entry.goal.domain.slug if entry.goal.domain else 'life',
                'source_type': 'habit_entry',
                'source_id': str(entry.pk),
                'signal_class': 'verified_action',
            }
            for entry in entries
        ]

    @staticmethod
    def _collect_faith_progress(user, date):
        """Bible reading completions today."""
        from apps.faith.models import UserReadingProgress

        readings = UserReadingProgress.objects.filter(
            user=user,
            is_completed=True,
            completed_at__date=date,
        ).select_related('user_plan__template', 'plan_day').only(
            'pk', 'completed_at', 'user_plan__template__name',
        )

        return [
            {
                'timestamp': reading.completed_at,
                'title': f"Bible Reading: {reading.user_plan.template.name}",
                'domain': 'faith',
                'source_type': 'reading_progress',
                'source_id': str(reading.pk),
                'signal_class': 'verified_action',
            }
            for reading in readings
        ]

    @staticmethod
    def _collect_journal_entries(user, date):
        """Journal entries created today."""
        from apps.journal.models import JournalEntry

        entries = JournalEntry.objects.filter(
            user=user,
            entry_date=date,
        ).only('pk', 'created_at')

        return [
            {
                'timestamp': entry.created_at,
                'title': "Journal entry",
                'domain': 'mind',
                'source_type': 'journal_entry',
                'source_id': str(entry.pk),
                'signal_class': 'verified_action',
            }
            for entry in entries
        ]

    @staticmethod
    def _collect_weight_entries(user, date):
        """Weight measurements today."""
        from apps.health.models import WeightEntry

        entries = WeightEntry.objects.filter(
            user=user,
            recorded_at__date=date,
        ).only('pk', 'recorded_at', 'value', 'unit')

        return [
            {
                'timestamp': entry.recorded_at,
                'title': f"Weight: {entry.value} {entry.unit}",
                'domain': 'health',
                'source_type': 'weight_entry',
                'source_id': str(entry.pk),
                'signal_class': 'verified_measurement',
            }
            for entry in entries
        ]

    @staticmethod
    def _collect_glucose_entries(user, date):
        """Blood glucose readings today."""
        from apps.health.models import GlucoseEntry

        entries = GlucoseEntry.objects.filter(
            user=user,
            recorded_at__date=date,
        ).only('pk', 'recorded_at', 'value', 'unit')

        return [
            {
                'timestamp': entry.recorded_at,
                'title': f"Glucose: {entry.value} {entry.unit}",
                'domain': 'health',
                'source_type': 'glucose_entry',
                'source_id': str(entry.pk),
                'signal_class': 'verified_measurement',
            }
            for entry in entries
        ]

    @staticmethod
    def _collect_blood_pressure_entries(user, date):
        """Blood pressure readings today."""
        from apps.health.models import BloodPressureEntry

        entries = BloodPressureEntry.objects.filter(
            user=user,
            recorded_at__date=date,
        ).only('pk', 'recorded_at', 'systolic', 'diastolic')

        return [
            {
                'timestamp': entry.recorded_at,
                'title': f"BP: {entry.systolic}/{entry.diastolic} mmHg",
                'domain': 'health',
                'source_type': 'blood_pressure_entry',
                'source_id': str(entry.pk),
                'signal_class': 'verified_measurement',
            }
            for entry in entries
        ]

    @staticmethod
    def _collect_sleep_entries(user, date):
        """Sleep records for today (sleep_date = last night's sleep)."""
        from apps.health.models import SleepEntry

        entries = SleepEntry.objects.filter(
            user=user,
            sleep_date=date,
        ).only('pk', 'recorded_at', 'total_minutes')

        return [
            {
                'timestamp': entry.recorded_at or tz_utils.make_aware(
                    dt.datetime.combine(date, dt.time(7, 0)),
                    tz_utils.get_current_timezone(),
                ),
                'title': f"Sleep: {entry.total_minutes // 60}h {entry.total_minutes % 60}m" if entry.total_minutes else "Sleep logged",
                'domain': 'health',
                'source_type': 'sleep_entry',
                'source_id': str(entry.pk),
                'signal_class': 'verified_measurement',
            }
            for entry in entries
        ]

    @staticmethod
    def _collect_brain_training(user, date):
        """Brain training sessions completed today."""
        from apps.brain_training.models import GameSession

        sessions = GameSession.objects.filter(
            user=user,
            completed_at__date=date,
            status='completed',
        ).only('pk', 'completed_at')

        return [
            {
                'timestamp': session.completed_at,
                'title': "Brain training session",
                'domain': 'mind',
                'source_type': 'brain_training',
                'source_id': str(session.pk),
                'signal_class': 'verified_action',
            }
            for session in sessions
        ]
