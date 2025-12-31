# ==============================================================================
# File: dashboard_ai.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Dashboard AI Integration - Comprehensive user context gathering
#              for personalized AI insights including Word of Year, goals,
#              intentions, faith, health, projects, and nutrition data.
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-28
# Last Updated: 2025-12-31 (Enhanced AI context with comprehensive user data)
# ==============================================================================
"""
Dashboard AI Integration - With Coaching Style Support

This module provides AI-powered insights specifically for the dashboard.
It handles caching, data gathering, and insight generation.

Gathers comprehensive user data including:
- Annual Direction (Word of Year, Theme, Anchor Scripture)
- Life Goals with domain and importance
- Change Intentions (identity-based shifts)
- Tasks, Projects, and Events
- Faith data (prayers, memory verses, Scripture study)
- Health data (weight, fasting, nutrition, workouts, medicine)
- Journal activity and streaks
"""
import logging
from datetime import timedelta
from django.db import models
from django.utils import timezone
from django.db.models import Count, F

from .services import ai_service
from .models import AIInsight

logger = logging.getLogger(__name__)


class DashboardAI:
    """
    AI services specifically for dashboard insights.
    Uses the user's preferred coaching style.
    """
    
    def __init__(self, user):
        self.user = user
        self.prefs = user.preferences
        self.faith_enabled = self.prefs.faith_enabled
        self.coaching_style = getattr(self.prefs, 'ai_coaching_style', 'supportive')
        self.user_profile = getattr(self.prefs, 'ai_profile', '') or ''
    
    def get_daily_insight(self, force_refresh: bool = False) -> str:
        """
        Get or generate the daily AI insight for the dashboard.

        Returns cached insight if available and valid, otherwise generates new one.
        Cache is invalidated when coaching style changes.
        """
        # Check for cached valid insight with matching coaching style
        if not force_refresh:
            cached = AIInsight.objects.filter(
                user=self.user,
                insight_type='daily',
                coaching_style=self.coaching_style,  # Must match current style
                valid_until__gt=timezone.now()
            ).first()

            if cached:
                return cached.content

        # Generate new insight
        user_data = self._gather_user_data()
        content = ai_service.generate_daily_insight(
            user_data,
            self.faith_enabled,
            self.coaching_style,
            self.user_profile
        )

        if content:
            # Cache until end of day
            end_of_day = timezone.now().replace(hour=23, minute=59, second=59)
            AIInsight.objects.create(
                user=self.user,
                insight_type='daily',
                content=content,
                context_summary=str(user_data)[:500],
                coaching_style=self.coaching_style,  # Store the style used
                valid_until=end_of_day
            )

        return content or self._get_fallback_insight()
    
    def get_weekly_summary(self, force_refresh: bool = False) -> str:
        """
        Get or generate weekly journal summary.
        Cache is invalidated when coaching style changes.
        """
        # Check cache (valid for a day, must match coaching style)
        if not force_refresh:
            cached = AIInsight.objects.filter(
                user=self.user,
                insight_type='weekly_summary',
                coaching_style=self.coaching_style,  # Must match current style
                created_at__gte=timezone.now() - timedelta(days=1)
            ).first()

            if cached:
                return cached.content

        # Gather journal entries
        entries = self._get_journal_entries(days=7)

        if not entries:
            return None

        content = ai_service.generate_journal_summary(
            entries,
            'week',
            self.faith_enabled,
            self.coaching_style
        )

        if content:
            AIInsight.objects.create(
                user=self.user,
                insight_type='weekly_summary',
                content=content,
                coaching_style=self.coaching_style,  # Store the style used
                valid_until=timezone.now() + timedelta(days=1)
            )

        return content
    
    def get_nudge_message(self, nudge_type: str, context: dict) -> str:
        """
        Generate a coaching-style-appropriate nudge message.
        
        Args:
            nudge_type: 'journal', 'tasks', 'goals', etc.
            context: Dict with relevant info (days_since, count, etc.)
        """
        gap_data = {
            'gap_type': nudge_type,
            'days_since': context.get('days', 0),
            'item_name': context.get('item_name', ''),
        }
        
        return ai_service.generate_accountability_nudge(
            gap_data,
            self.faith_enabled,
            self.coaching_style
        )
    
    def get_celebration_message(self, achievement_type: str, details: str) -> str:
        """
        Generate a coaching-style-appropriate celebration message.
        """
        achievement_data = {
            'achievement_type': achievement_type,
            'details': details,
        }
        
        return ai_service.generate_celebration(
            achievement_data,
            self.faith_enabled,
            self.coaching_style
        )
    
    def get_reflection_prompt(self) -> str:
        """
        Get a personalized reflection prompt for journaling.
        """
        user_data = self._gather_reflection_data()
        return ai_service.generate_weekly_reflection_prompt(
            user_data, 
            self.faith_enabled,
            self.coaching_style
        )
    
    def _gather_user_data(self) -> dict:
        """Gather comprehensive user data for daily insight generation."""
        from apps.journal.models import JournalEntry
        from apps.core.utils import get_user_today, get_user_now

        now = get_user_now(self.user)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        today = get_user_today(self.user)
        current_year = today.year

        # Journal stats
        entries = JournalEntry.objects.filter(user=self.user)
        entries_this_week = entries.filter(created_at__gte=week_ago)
        last_entry = entries.order_by('-entry_date').first()

        data = {
            'today': today,
            'journal_count_week': entries_this_week.count(),
            'last_journal_date': last_entry.entry_date if last_entry else None,
        }

        # Calculate streak
        data['current_streak'] = self._calculate_journal_streak()

        # ===================
        # PURPOSE MODULE DATA
        # ===================
        if self.prefs.purpose_enabled:
            try:
                from apps.purpose.models import LifeGoal, AnnualDirection, ChangeIntention

                # Goals count
                active_goals = LifeGoal.objects.filter(user=self.user, status='active')
                data['active_goals'] = active_goals.count()

                # Get goal details for context (max 3 most important)
                goals_list = list(active_goals.order_by('sort_order')[:3].values(
                    'title', 'why_it_matters', 'domain__name'
                ))
                if goals_list:
                    data['goals_list'] = goals_list

                # Annual Direction - Word of Year and Theme
                direction = AnnualDirection.objects.filter(
                    user=self.user,
                    year=current_year
                ).first()
                if direction:
                    data['word_of_year'] = direction.word_of_year
                    if direction.theme:
                        data['annual_theme'] = direction.theme
                    if direction.anchor_text:
                        data['anchor_scripture'] = f"{direction.anchor_text[:100]}..." if len(direction.anchor_text) > 100 else direction.anchor_text
                        if direction.anchor_source:
                            data['anchor_scripture'] += f" ({direction.anchor_source})"

                # Active Change Intentions
                intentions = ChangeIntention.objects.filter(
                    user=self.user, status='active'
                )[:3]
                if intentions:
                    data['active_intentions'] = [i.intention for i in intentions]

            except Exception as e:
                logger.debug(f"Could not load purpose data for AI context: {e}")

        # ===================
        # LIFE MODULE DATA
        # ===================
        if self.prefs.life_enabled:
            try:
                from apps.life.models import Task, Project, LifeEvent

                # Tasks completed today
                data['completed_tasks_today'] = Task.objects.filter(
                    user=self.user,
                    is_completed=True,
                    completed_at__date=today
                ).count()

                # Overdue tasks
                data['overdue_tasks'] = Task.objects.filter(
                    user=self.user,
                    is_completed=False,
                    due_date__lt=today
                ).count()

                # Tasks due today (not overdue, but actionable)
                data['tasks_due_today'] = Task.objects.filter(
                    user=self.user,
                    is_completed=False,
                    due_date=today
                ).count()

                # Active projects with progress
                active_projects = Project.objects.filter(
                    user=self.user, status='active'
                )
                if active_projects.exists():
                    data['active_projects'] = active_projects.count()
                    # Get top priority projects
                    priority_projects = active_projects.filter(priority='now')[:2]
                    if priority_projects:
                        data['priority_projects'] = [
                            {'title': p.title, 'progress': p.progress_percentage}
                            for p in priority_projects
                        ]

                # Upcoming events today and tomorrow
                events_today = LifeEvent.objects.filter(
                    user=self.user,
                    start_date=today
                ).count()
                if events_today:
                    data['events_today'] = events_today

            except Exception as e:
                logger.debug(f"Could not load life module data for AI context: {e}")

        # ===================
        # FAITH MODULE DATA
        # ===================
        if self.faith_enabled:
            try:
                from apps.faith.models import PrayerRequest, SavedVerse, FaithMilestone

                # Active prayer count
                active_prayers = PrayerRequest.objects.filter(
                    user=self.user, is_answered=False
                )
                data['active_prayers'] = active_prayers.count()

                # Recently answered prayers (last 30 days) - shows God's faithfulness
                answered_recently = PrayerRequest.objects.filter(
                    user=self.user,
                    is_answered=True,
                    answered_at__gte=month_ago
                ).count()
                if answered_recently > 0:
                    data['answered_prayers_month'] = answered_recently

                # Memory verse (if user has one set)
                memory_verse = SavedVerse.objects.filter(
                    user=self.user,
                    is_memory_verse=True,
                    status='active'
                ).first()
                if memory_verse:
                    data['memory_verse'] = {
                        'reference': memory_verse.reference,
                        'text': memory_verse.text[:150] + '...' if len(memory_verse.text) > 150 else memory_verse.text
                    }

                # Recent saved verses (shows what user is studying)
                recent_verses = SavedVerse.objects.filter(
                    user=self.user,
                    status='active'
                ).order_by('-created_at')[:3]
                if recent_verses:
                    data['studying_scripture'] = [v.reference for v in recent_verses]

                # Faith milestones count (shows spiritual journey depth)
                milestones = FaithMilestone.objects.filter(user=self.user).count()
                if milestones > 0:
                    data['faith_milestones_count'] = milestones

            except Exception as e:
                logger.debug(f"Could not load faith data for AI context: {e}")

        # ===================
        # HEALTH MODULE DATA
        # ===================
        if self.prefs.health_enabled:
            try:
                from apps.health.models import WeightEntry, FastingWindow

                # Weight trend
                weights = WeightEntry.objects.filter(user=self.user).order_by('-recorded_at')[:5]
                if weights.count() >= 2:
                    recent = list(weights)
                    if recent[0].value_in_lb < recent[-1].value_in_lb:
                        data['weight_trend'] = 'down'
                    elif recent[0].value_in_lb > recent[-1].value_in_lb:
                        data['weight_trend'] = 'up'
                    else:
                        data['weight_trend'] = 'stable'

                    # Current weight for context
                    data['current_weight'] = round(recent[0].value_in_lb, 1)

                # Weight goal progress
                weight_progress = self.prefs.get_weight_progress()
                if weight_progress and weight_progress.get('current_weight'):
                    data['weight_goal'] = weight_progress.get('goal')
                    data['weight_remaining'] = weight_progress.get('remaining')
                    data['weight_direction'] = weight_progress.get('direction')
                    data['weight_progress_percent'] = weight_progress.get('progress_percent')

                # Active fast
                active_fast = FastingWindow.objects.filter(
                    user=self.user, ended_at__isnull=True
                ).first()
                if active_fast:
                    data['fasting_active'] = True
                    # Calculate how long they've been fasting
                    fasting_hours = (now - active_fast.started_at).total_seconds() / 3600
                    data['fasting_hours'] = round(fasting_hours, 1)
                else:
                    data['fasting_active'] = False

            except Exception as e:
                logger.debug(f"Could not load health data for AI context: {e}")

            # Health - Nutrition Tracking
            try:
                from apps.health.models import DailyNutritionSummary

                # Today's nutrition progress
                nutrition_progress = self.prefs.get_nutrition_progress(today)
                if nutrition_progress:
                    calories = nutrition_progress.get('calories', {})
                    if calories.get('current', 0) > 0:
                        data['calories_today'] = calories.get('current')
                        data['calorie_goal'] = calories.get('goal')
                        data['calories_remaining'] = calories.get('remaining')

            except Exception as e:
                logger.debug(f"Could not load nutrition data for AI context: {e}")

            # Health - Medicine Tracking
            try:
                from apps.health.models import Medicine, MedicineLog

                active_medicines = Medicine.objects.filter(
                    user=self.user,
                    medicine_status=Medicine.STATUS_ACTIVE
                )
                data['active_medicines_count'] = active_medicines.count()

                # Medicine adherence this week
                medicine_logs = MedicineLog.objects.filter(
                    user=self.user,
                    scheduled_date__gte=today - timedelta(days=7),
                    scheduled_date__lte=today
                )
                taken_count = medicine_logs.filter(log_status__in=['taken', 'late']).count()
                missed_count = medicine_logs.filter(log_status='missed').count()
                total = taken_count + missed_count
                if total > 0:
                    data['medicine_adherence_rate'] = round((taken_count / total) * 100)
                else:
                    data['medicine_adherence_rate'] = None

                # Medicines needing refill
                needs_refill = active_medicines.filter(
                    current_supply__isnull=False,
                    current_supply__lte=F('refill_threshold')
                ).count()
                data['medicines_need_refill'] = needs_refill

            except Exception as e:
                logger.debug(f"Could not load medicine data for AI context: {e}")

            # Health - Workout Tracking
            try:
                from apps.health.models import WorkoutSession, PersonalRecord

                # Workouts this week
                workouts_week = WorkoutSession.objects.filter(
                    user=self.user,
                    date__gte=today - timedelta(days=7),
                    date__lte=today
                ).count()
                data['workouts_this_week'] = workouts_week

                # Last workout
                last_workout = WorkoutSession.objects.filter(
                    user=self.user
                ).order_by('-date').first()
                if last_workout:
                    data['days_since_workout'] = (today - last_workout.date).days
                else:
                    data['days_since_workout'] = None

                # Recent PRs (last 30 days)
                recent_prs = PersonalRecord.objects.filter(
                    user=self.user,
                    achieved_date__gte=today - timedelta(days=30)
                ).count()
                data['recent_prs_count'] = recent_prs

            except Exception as e:
                logger.debug(f"Could not load workout data for AI context: {e}")

        # Scan Activity
        try:
            from apps.scan.models import ScanLog

            # Scans this week
            scans_week = ScanLog.objects.filter(
                user=self.user,
                created_at__gte=week_ago,
                status=ScanLog.STATUS_SUCCESS
            ).count()
            data['scans_this_week'] = scans_week

            # Items created via AI camera this week
            ai_camera_items = JournalEntry.objects.filter(
                user=self.user,
                created_via='ai_camera',
                created_at__gte=week_ago
            ).count()
            data['items_from_ai_camera'] = ai_camera_items

        except Exception as e:
            logger.debug(f"Could not load scan data for AI context: {e}")

        return data
    
    def _gather_reflection_data(self) -> dict:
        """Gather data for reflection prompt generation."""
        from apps.journal.models import JournalEntry
        
        week_ago = timezone.now() - timedelta(days=7)
        entries = JournalEntry.objects.filter(
            user=self.user,
            created_at__gte=week_ago
        )
        
        data = {}
        
        # Most common mood
        moods = entries.exclude(mood='').values('mood').annotate(
            count=Count('mood')
        ).order_by('-count')
        if moods:
            data['top_mood'] = moods[0]['mood']
        
        # Goals worked on
        if self.prefs.purpose_enabled:
            try:
                from apps.purpose.models import LifeGoal
                recent_goals = LifeGoal.objects.filter(
                    user=self.user,
                    status='active',
                    updated_at__gte=week_ago
                ).values_list('title', flat=True)[:3]
                data['goals_worked_on'] = list(recent_goals)
            except Exception as e:
                logger.debug(f"Could not load goals for reflection: {e}")
        
        return data
    
    def _get_journal_entries(self, days: int = 7) -> list:
        """Get journal entries for summary."""
        from apps.journal.models import JournalEntry
        
        since = timezone.now() - timedelta(days=days)
        entries = JournalEntry.objects.filter(
            user=self.user,
            created_at__gte=since
        ).order_by('-entry_date')[:10]
        
        return [
            {
                'title': e.title,
                'body': e.body[:500] if e.body else '',
                'mood': e.mood,
                'date': e.entry_date.strftime('%A, %b %d'),
            }
            for e in entries
        ]
    
    def _calculate_journal_streak(self) -> int:
        """Calculate current journal streak in days."""
        from apps.journal.models import JournalEntry
        
        entries = JournalEntry.objects.filter(
            user=self.user
        ).order_by('-entry_date').values_list('entry_date', flat=True).distinct()[:30]

        if not entries:
            return 0

        from apps.core.utils import get_user_today
        today = get_user_today(self.user)
        streak = 0
        expected_date = today
        
        for entry_date in entries:
            if entry_date == expected_date:
                streak += 1
                expected_date -= timedelta(days=1)
            elif entry_date < expected_date:
                break
        
        return streak
    
    def _get_fallback_insight(self) -> str:
        """Fallback insight when AI is unavailable."""
        fallbacks = {
            'gentle': [
                "Every small step is meaningful. Be gentle with yourself today.",
                "You're doing beautifully just by showing up. No pressure.",
                "Take a breath. You're exactly where you need to be.",
            ],
            'supportive': [
                "Every step forward is progress, no matter how small.",
                "Taking time to reflect shows you're committed to growth.",
                "You're doing the work that matters—be proud of that.",
            ],
            'direct': [
                "Today is yours to shape. Make it count.",
                "Progress beats perfection. Get moving.",
                "You've got what it takes. Now prove it.",
            ]
        }
        
        import random
        style_fallbacks = fallbacks.get(self.coaching_style, fallbacks['supportive'])
        return random.choice(style_fallbacks)


def get_dashboard_insight(user) -> dict:
    """
    Convenience function to get all AI insights for the dashboard.
    
    Returns dict with insight content and metadata.
    """
    if not ai_service.is_available:
        return {
            'available': False,
            'daily_insight': None,
            'weekly_summary': None,
        }
    
    dashboard_ai = DashboardAI(user)
    
    return {
        'available': True,
        'daily_insight': dashboard_ai.get_daily_insight(),
        'weekly_summary': dashboard_ai.get_weekly_summary(),
    }
