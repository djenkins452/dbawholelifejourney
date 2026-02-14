# ==============================================================================
# File: apps/dashboard/cache.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Smart caching layer for dashboard with signal-based invalidation
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-06
# ==============================================================================
"""
Dashboard Cache Service

Provides intelligent caching for dashboard data with automatic invalidation
when underlying data changes. Uses Django's cache framework with signal-based
invalidation to ensure data freshness while minimizing database queries.

Cache Strategy:
- Each data section (health, journal, faith, life, purpose) cached separately
- Cache keys include user ID and data type
- Signals invalidate only affected cache sections when data changes
- Version numbers allow bulk invalidation if needed

Usage:
    cache_service = DashboardCacheService(user)
    health_data = cache_service.get_health_data(today, month_ago)  # Uses cache

    # When medicine is logged (via signal):
    DashboardCacheService.invalidate_health(user)  # Clears only health cache
"""

import hashlib
import logging
from datetime import date, timedelta
from typing import Any, Dict, Optional

from django.core.cache import cache
from django.db.models import Count, F, Prefetch, Q

logger = logging.getLogger(__name__)

# Cache timeout in seconds (5 minutes - short enough to be fresh, long enough to help)
DASHBOARD_CACHE_TIMEOUT = 300

# Cache key prefix
CACHE_PREFIX = "dashboard_v1"


class DashboardCacheService:
    """
    Intelligent dashboard caching with signal-based invalidation.

    Caches dashboard data sections separately so changes to one section
    don't invalidate everything.
    """

    def __init__(self, user):
        self.user = user
        self.user_id = user.id

    def _cache_key(self, section: str) -> str:
        """Generate cache key for a dashboard section."""
        return f"{CACHE_PREFIX}:{self.user_id}:{section}"

    def _get_cached(self, section: str) -> Optional[Dict]:
        """Get cached data for a section."""
        key = self._cache_key(section)
        data = cache.get(key)
        if data is not None:
            logger.debug(f"Dashboard cache HIT: {section} for user {self.user_id}")
        return data

    def _set_cached(self, section: str, data: Dict, timeout: int = DASHBOARD_CACHE_TIMEOUT):
        """Cache data for a section."""
        key = self._cache_key(section)
        cache.set(key, data, timeout)
        logger.debug(f"Dashboard cache SET: {section} for user {self.user_id}")

    # =========================================================================
    # CACHE INVALIDATION (called by signals)
    # =========================================================================

    @classmethod
    def invalidate_health(cls, user):
        """Invalidate health-related dashboard cache."""
        key = f"{CACHE_PREFIX}:{user.id}:health"
        cache.delete(key)
        logger.debug(f"Dashboard cache INVALIDATED: health for user {user.id}")

    @classmethod
    def invalidate_journal(cls, user):
        """Invalidate journal-related dashboard cache."""
        key = f"{CACHE_PREFIX}:{user.id}:journal"
        cache.delete(key)
        logger.debug(f"Dashboard cache INVALIDATED: journal for user {user.id}")

    @classmethod
    def invalidate_faith(cls, user):
        """Invalidate faith-related dashboard cache."""
        key = f"{CACHE_PREFIX}:{user.id}:faith"
        cache.delete(key)
        logger.debug(f"Dashboard cache INVALIDATED: faith for user {user.id}")

    @classmethod
    def invalidate_life(cls, user):
        """Invalidate life-related dashboard cache."""
        key = f"{CACHE_PREFIX}:{user.id}:life"
        cache.delete(key)
        logger.debug(f"Dashboard cache INVALIDATED: life for user {user.id}")

    @classmethod
    def invalidate_purpose(cls, user):
        """Invalidate purpose-related dashboard cache."""
        key = f"{CACHE_PREFIX}:{user.id}:purpose"
        cache.delete(key)
        logger.debug(f"Dashboard cache INVALIDATED: purpose for user {user.id}")

    @classmethod
    def invalidate_all(cls, user):
        """Invalidate all dashboard cache for a user."""
        sections = ['health', 'journal', 'faith', 'life', 'purpose', 'scan', 'capture']
        for section in sections:
            key = f"{CACHE_PREFIX}:{user.id}:{section}"
            cache.delete(key)
        logger.debug(f"Dashboard cache INVALIDATED: ALL for user {user.id}")

    # =========================================================================
    # OPTIMIZED DATA FETCHING
    # =========================================================================

    def get_health_data(self, today: date, month_ago) -> Dict[str, Any]:
        """
        Get health data with optimized queries.

        Fixes the N+1 query problem by:
        1. Using prefetch_related for medicine schedules
        2. Batch fetching all MedicineLogs for today in one query
        3. Using aggregation instead of multiple COUNT queries

        NOTE: We don't cache model instances because they don't serialize
        properly. Instead, we just run optimized queries each time but
        use the cache invalidation to know when data might have changed.
        The cache stores a simple 'version' marker that gets invalidated
        when data changes, triggering a re-fetch.
        """
        from apps.health.models import (
            WeightEntry, HeartRateEntry, GlucoseEntry,
            Medicine, MedicineLog, MedicineSchedule,
            WorkoutSession, PersonalRecord
        )

        user = self.user
        week_ago_date = today - timedelta(days=7)

        # =====================
        # Weight & Vitals (simple queries - no N+1)
        # =====================
        latest_weight = WeightEntry.objects.filter(user=user).order_by('-recorded_at').first()
        latest_heart_rate = HeartRateEntry.objects.filter(user=user).order_by('-recorded_at').first()
        latest_glucose = GlucoseEntry.objects.filter(user=user).order_by('-recorded_at').first()

        # =====================
        # Medicine Tracking (OPTIMIZED - was N+1)
        # =====================
        # Step 1: Get active medicines with schedules prefetched (ONE query with JOIN)
        active_medicines = list(Medicine.objects.filter(
            user=user,
            medicine_status=Medicine.STATUS_ACTIVE
        ).prefetch_related(
            Prefetch(
                'schedules',
                queryset=MedicineSchedule.objects.filter(is_active=True),
                to_attr='active_schedules'
            )
        ))

        # Step 2: Get ALL medicine logs for today in ONE query
        today_logs = MedicineLog.objects.filter(
            user=user,
            scheduled_date=today
        ).select_related('medicine', 'schedule')

        # Build lookup dict: (medicine_id, schedule_id) -> log
        log_lookup = {
            (log.medicine_id, log.schedule_id): log
            for log in today_logs
        }

        # Step 3: Build schedule list using prefetched data (NO additional queries)
        today_weekday = today.weekday()
        todays_schedules = []

        for medicine in active_medicines:
            if medicine.is_prn:
                continue
            for schedule in getattr(medicine, 'active_schedules', []):
                if schedule.applies_to_day(today_weekday):
                    log = log_lookup.get((medicine.id, schedule.id))
                    todays_schedules.append({
                        'medicine': medicine,
                        'schedule': schedule,
                        'log': log,
                        'taken': log is not None and log.log_status in ['taken', 'late'],
                        'missed': log is not None and log.log_status == 'missed',
                        'skipped': log is not None and log.log_status == 'skipped',
                    })

        todays_schedules.sort(key=lambda x: x['schedule'].scheduled_time)

        # Step 4: Medicine adherence - correct calculation against expected doses
        from apps.health.medicine_utils import calculate_medicine_adherence
        adherence_result = calculate_medicine_adherence(user, week_ago_date, today)
        adherence_rate = adherence_result['adherence_rate']
        taken_count = adherence_result['taken_doses']
        missed_count = adherence_result['missed_doses']

        # Refill queries - filter the already-fetched list instead of new queries
        needs_refill = [
            m for m in active_medicines
            if m.current_supply is not None
            and m.refill_threshold is not None
            and m.current_supply <= m.refill_threshold
            and not m.refill_requested
        ]
        refill_requested = [m for m in active_medicines if m.refill_requested]

        # =====================
        # Workout Tracking (simple queries)
        # =====================
        workouts_week = list(WorkoutSession.objects.filter(
            user=user,
            date__gte=week_ago_date,
            date__lte=today
        ))

        recent_workouts = list(WorkoutSession.objects.filter(
            user=user
        ).order_by('-date')[:3])

        recent_prs = list(PersonalRecord.objects.filter(
            user=user,
            achieved_date__gte=today - timedelta(days=30)
        ).order_by('-achieved_date')[:3])

        last_workout = recent_workouts[0] if recent_workouts else None
        days_since_workout = (today - last_workout.date).days if last_workout else None

        # Weight and Nutrition Progress
        from apps.health.models import HealthProfile
        health_profile = HealthProfile.get_for_user(user)
        weight_progress = health_profile.get_weight_progress()
        nutrition_progress = user.preferences.get_nutrition_progress(today)

        return {
            'latest_weight': latest_weight,
            'latest_heart_rate': latest_heart_rate,
            'latest_glucose': latest_glucose,
            'active_medicines': active_medicines,
            'todays_schedules': todays_schedules,
            'medicine_adherence_rate': adherence_rate,
            'taken_count': taken_count,
            'missed_count': missed_count,
            'needs_refill': needs_refill,
            'refill_requested': refill_requested,
            'workouts_week': workouts_week,
            'workouts_count_week': len(workouts_week),
            'recent_workouts': recent_workouts,
            'recent_prs': recent_prs,
            'days_since_workout': days_since_workout,
            'weight_progress': weight_progress,
            'nutrition_progress': nutrition_progress,
        }

    def get_journal_data(self, today: date, week_ago, month_ago) -> Dict[str, Any]:
        """Get journal data with caching."""
        cached = self._get_cached('journal')
        if cached is not None:
            return cached

        from apps.journal.models import JournalEntry

        entries = JournalEntry.objects.filter(user=self.user)
        entries_week = entries.filter(created_at__gte=week_ago)

        last_entry = entries.order_by('-entry_date').first()
        days_since_journal = (today - last_entry.entry_date).days if last_entry else None

        # Mood distribution (single aggregation query)
        moods = entries_week.exclude(mood='').values('mood').annotate(
            count=Count('id')
        ).order_by('-count')

        data = {
            'last_entry': last_entry,
            'days_since_journal': days_since_journal,
            'entries_week_count': entries_week.count(),
            'mood_distribution': list(moods),
        }

        self._set_cached('journal', data)
        return data

    def get_life_data(self, today: date) -> Dict[str, Any]:
        """Get life data with caching (excludes Google Calendar sync)."""
        cached = self._get_cached('life')
        if cached is not None:
            return cached

        from apps.life.models import Task, LifeEvent, Project

        # Tasks
        tasks = Task.objects.filter(
            user=self.user,
            status__in=['pending', 'in_progress']
        ).select_related('project').order_by('due_date')[:10]

        overdue_tasks = Task.objects.filter(
            user=self.user,
            status__in=['pending', 'in_progress'],
            due_date__lt=today
        ).count()

        # Events
        tomorrow = today + timedelta(days=1)
        week_from_now = today + timedelta(days=7)

        upcoming_events = LifeEvent.objects.filter(
            user=self.user,
            start_date__gte=today,
            start_date__lte=week_from_now
        ).order_by('start_date')[:5]

        todays_events = LifeEvent.objects.filter(
            user=self.user,
            start_date__date=today
        ).order_by('start_date')

        # Projects
        active_projects = Project.objects.filter(
            user=self.user,
            status='active'
        )[:5]

        data = {
            'pending_tasks': list(tasks),
            'overdue_tasks_count': overdue_tasks,
            'upcoming_events': list(upcoming_events),
            'todays_events': list(todays_events),
            'active_projects': list(active_projects),
        }

        self._set_cached('life', data)
        return data

    def get_faith_data(self) -> Dict[str, Any]:
        """Get faith data with caching."""
        cached = self._get_cached('faith')
        if cached is not None:
            return cached

        from apps.faith.models import Prayer, SavedVerse, FastingEntry
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        week_ago = today - timedelta(days=7)

        # Prayers
        active_prayers = Prayer.objects.filter(
            user=self.user,
            status='active'
        ).count()

        answered_prayers = Prayer.objects.filter(
            user=self.user,
            status='answered',
            answered_date__gte=week_ago
        ).count()

        # Saved verses
        recent_verses = SavedVerse.objects.filter(
            user=self.user
        ).order_by('-created_at')[:3]

        # Fasting
        current_fast = FastingEntry.objects.filter(
            user=self.user,
            start_time__date=today,
            end_time__isnull=True
        ).first()

        data = {
            'active_prayers_count': active_prayers,
            'answered_prayers_week': answered_prayers,
            'recent_verses': list(recent_verses),
            'current_fast': current_fast,
        }

        self._set_cached('faith', data)
        return data

    def get_purpose_data(self) -> Dict[str, Any]:
        """Get purpose data with caching."""
        cached = self._get_cached('purpose')
        if cached is not None:
            return cached

        from apps.purpose.models import LifeGoal

        # Goals with progress - use select_related for domain
        active_goals = LifeGoal.objects.filter(
            user=self.user,
            status='active'
        ).select_related('domain').prefetch_related('milestones')[:5]

        data = {
            'active_goals': list(active_goals),
            'active_goals_count': len(active_goals),
        }

        self._set_cached('purpose', data)
        return data
