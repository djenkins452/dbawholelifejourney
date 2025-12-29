"""
Whole Life Journey - Dashboard Views

Project: Whole Life Journey
Path: apps/dashboard/views.py
Purpose: AI-powered dashboard displaying personalized insights and module summaries

Description:
    The DashboardView is the main view after login, providing a personalized
    command center with AI-driven insights, daily encouragement, module
    overviews, and wellness celebrations/nudges.

Key Views:
    - DashboardView: Main dashboard with AI insights and module tiles
    - RefreshAIInsightsView: HTMX endpoint for refreshing AI content
    - DashboardStatsView: API endpoint for dashboard statistics

AI Features:
    - Gathers comprehensive data from all modules (journal, health, faith, life)
    - Generates personalized insights based on patterns
    - Provides gentle accountability nudges
    - Celebrates achievements and streaks

Data Gathering:
    The _gather_comprehensive_data method collects:
    - Journal entries (recent, mood patterns, streaks)
    - Health metrics (weight, heart rate, glucose, workouts, medicine)
    - Faith data (prayers, scripture, fasting)
    - Life data (tasks, events, projects)
    - Purpose data (goals, directions)

Dependencies:
    - apps.ai.dashboard_ai for AI insight generation
    - All module models for data aggregation

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""
import json
import random
from datetime import timedelta
from django.db import models
from django.db.models import Count, Avg
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView, View
from django.http import HttpResponse, JsonResponse
from django.conf import settings

from .models import DailyEncouragement
from apps.help.mixins import HelpContextMixin


class DashboardView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    AI-Driven Dashboard - Your personalized command center.
    """
    template_name = "dashboard/home.html"
    help_context_id = "DASHBOARD_HOME"

    def get_context_data(self, **kwargs):
        import logging
        logger = logging.getLogger(__name__)

        try:
            context = super().get_context_data(**kwargs)
            user = self.request.user
            prefs = user.preferences

            # Basic info
            context["current_date"] = timezone.now()
            context["greeting"] = self._get_greeting()
            context["faith_enabled"] = prefs.faith_enabled

            # Get daily encouragement (fallback if AI unavailable)
            context["encouragement"] = self._get_daily_encouragement(prefs.faith_enabled)

            # Gather all user data for AI
            user_data = self._gather_comprehensive_data(user, prefs)
            context["user_data"] = user_data

            # AI Insights (if enabled)
            context["ai_enabled"] = prefs.ai_enabled
            if prefs.ai_enabled:
                context["ai_insights"] = self._get_ai_insights(user, prefs, user_data)
            else:
                context["ai_insights"] = None

            # Quick stats for the header
            context["quick_stats"] = self._get_quick_stats(user_data)

            # Module enabled flags for conditional display
            context["journal_enabled"] = prefs.journal_enabled
            context["health_enabled"] = prefs.health_enabled
            context["life_enabled"] = prefs.life_enabled
            context["purpose_enabled"] = prefs.purpose_enabled

            return context
        except Exception as e:
            logger.error(f"Dashboard error for user {self.request.user.email}: {e}", exc_info=True)
            raise
    
    def _get_greeting(self):
        """Get time-appropriate greeting in user's timezone."""
        import pytz
        user_tz = pytz.timezone(self.request.user.preferences.timezone)
        user_time = timezone.now().astimezone(user_tz)
        hour = user_time.hour
        if hour < 12:
            return "Good morning"
        elif hour < 17:
            return "Good afternoon"
        else:
            return "Good evening"
    
    def _get_daily_encouragement(self, faith_enabled):
        """Get daily encouragement message."""
        today = timezone.now()
        queryset = DailyEncouragement.objects.filter(is_active=True)
        
        if not faith_enabled:
            queryset = queryset.filter(is_faith_specific=False)
        
        # Try to match day of week or month
        targeted = queryset.filter(
            models.Q(day_of_week=today.weekday()) |
            models.Q(month=today.month)
        )
        
        if targeted.exists():
            return random.choice(list(targeted))
        
        if queryset.exists():
            return random.choice(list(queryset))
        
        return None
    
    def _gather_comprehensive_data(self, user, prefs):
        """Gather all user data for AI analysis."""
        from apps.core.utils import get_user_today, get_user_now

        now = get_user_now(user)
        today = get_user_today(user)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        data = {
            "today": today,
            "week_ago": week_ago,
        }

        # Journal data
        if prefs.journal_enabled:
            data.update(self._get_journal_data(user, today, week_ago, month_ago))

        # Faith data
        if prefs.faith_enabled:
            data.update(self._get_faith_data(user))

        # Health data
        if prefs.health_enabled:
            data.update(self._get_health_data(user, today, month_ago))

        # Life data
        if prefs.life_enabled:
            data.update(self._get_life_data(user, today))

        # Purpose data
        if prefs.purpose_enabled:
            data.update(self._get_purpose_data(user))

        # Scan data (if AI enabled - scan requires AI)
        if prefs.ai_enabled:
            data.update(self._get_scan_data(user, today, week_ago))

        return data
    
    def _get_journal_data(self, user, today, week_ago, month_ago):
        """Get journal-related data."""
        from apps.journal.models import JournalEntry
        
        entries = JournalEntry.objects.filter(user=user)
        entries_week = entries.filter(created_at__gte=week_ago)
        
        last_entry = entries.order_by('-entry_date').first()
        days_since_journal = None
        if last_entry:
            days_since_journal = (today - last_entry.entry_date).days
        
        # Calculate streak
        streak = self._calculate_journal_streak(user, today)
        
        # Get mood distribution this week
        moods = entries_week.exclude(mood='').values('mood').annotate(
            count=Count('mood')
        ).order_by('-count')
        top_mood = moods[0]['mood'] if moods else None
        
        # Recent entries for context
        recent_entries = list(entries.order_by('-entry_date')[:5].values(
            'title', 'entry_date', 'mood', 'body'
        ))
        
        return {
            "journal_total": entries.count(),
            "journal_this_week": entries_week.count(),
            "journal_this_month": entries.filter(created_at__gte=month_ago).count(),
            "last_journal_date": last_entry.entry_date if last_entry else None,
            "days_since_journal": days_since_journal,
            "journal_streak": streak,
            "top_mood_this_week": top_mood,
            "recent_entries": recent_entries,
        }
    
    def _calculate_journal_streak(self, user, today):
        """Calculate consecutive days of journaling."""
        from apps.journal.models import JournalEntry
        
        entries = JournalEntry.objects.filter(
            user=user
        ).order_by('-entry_date').values_list('entry_date', flat=True).distinct()[:60]
        
        if not entries:
            return 0
        
        streak = 0
        expected_date = today
        
        for entry_date in entries:
            if entry_date == expected_date:
                streak += 1
                expected_date -= timedelta(days=1)
            elif entry_date < expected_date:
                break
        
        return streak
    
    def _get_faith_data(self, user):
        """Get faith-related data."""
        from apps.faith.models import PrayerRequest, FaithMilestone
        
        prayers = PrayerRequest.objects.filter(user=user)
        active_prayers = prayers.filter(is_answered=False)
        answered_prayers = prayers.filter(is_answered=True)
        
        # Recent answered prayers
        recent_answered = answered_prayers.order_by('-answered_at').first()
        
        return {
            "active_prayers": active_prayers.count(),
            "answered_prayers": answered_prayers.count(),
            "total_milestones": FaithMilestone.objects.filter(user=user).count(),
            "recent_answered_prayer": recent_answered,
        }
    
    def _get_health_data(self, user, today, month_ago):
        """Get health-related data."""
        from apps.health.models import (
            WeightEntry, FastingWindow, GlucoseEntry,
            Medicine, MedicineLog, MedicineSchedule,
            WorkoutSession, PersonalRecord
        )
        from datetime import datetime, timedelta as dt_timedelta

        # Weight
        weights = WeightEntry.objects.filter(user=user)
        latest_weight = weights.order_by('-recorded_at').first()

        weight_change = None
        weight_trend = None
        if latest_weight and weights.count() >= 2:
            month_ago_weight = weights.filter(
                recorded_at__lte=timezone.now() - timedelta(days=25),
                recorded_at__gte=timezone.now() - timedelta(days=35)
            ).order_by('-recorded_at').first()
            if month_ago_weight:
                weight_change = round(latest_weight.value_in_lb - month_ago_weight.value_in_lb, 1)
                weight_trend = 'down' if weight_change < 0 else 'up' if weight_change > 0 else 'stable'

        # Fasting
        fasting = FastingWindow.objects.filter(user=user)
        active_fast = fasting.filter(ended_at__isnull=True).first()
        completed_fasts_month = fasting.filter(
            ended_at__isnull=False,
            started_at__gte=month_ago
        ).count()

        # Glucose
        glucose = GlucoseEntry.objects.filter(user=user)
        latest_glucose = glucose.order_by('-recorded_at').first()

        # =====================
        # Medicine Tracking
        # =====================
        active_medicines = Medicine.objects.filter(
            user=user,
            medicine_status=Medicine.STATUS_ACTIVE
        )

        # Today's medicine schedule
        today_weekday = today.weekday()
        todays_schedules = []
        for medicine in active_medicines.filter(is_prn=False):
            for schedule in medicine.schedules.filter(is_active=True):
                if schedule.applies_to_day(today_weekday):
                    # Check if this dose was taken today
                    log = MedicineLog.objects.filter(
                        medicine=medicine,
                        schedule=schedule,
                        scheduled_date=today
                    ).first()
                    todays_schedules.append({
                        'medicine': medicine,
                        'schedule': schedule,
                        'log': log,
                        'taken': log is not None and log.log_status in ['taken', 'late'],
                        'missed': log is not None and log.log_status == 'missed',
                        'skipped': log is not None and log.log_status == 'skipped',
                    })

        # Sort by scheduled time
        todays_schedules.sort(key=lambda x: x['schedule'].scheduled_time)

        # Medicine adherence for the week
        week_ago_date = today - timedelta(days=7)
        medicine_logs_week = MedicineLog.objects.filter(
            user=user,
            scheduled_date__gte=week_ago_date,
            scheduled_date__lte=today
        )
        taken_count = medicine_logs_week.filter(log_status__in=['taken', 'late']).count()
        missed_count = medicine_logs_week.filter(log_status='missed').count()
        total_scheduled = taken_count + missed_count
        adherence_rate = round((taken_count / total_scheduled) * 100) if total_scheduled > 0 else None

        # Medicines needing refill
        needs_refill = active_medicines.filter(
            current_supply__isnull=False,
            current_supply__lte=models.F('refill_threshold')
        )

        # =====================
        # Workout Tracking
        # =====================
        week_ago_date = today - timedelta(days=7)

        # Workouts this week
        workouts_week = WorkoutSession.objects.filter(
            user=user,
            date__gte=week_ago_date,
            date__lte=today
        )

        # Recent workouts (last 3)
        recent_workouts = WorkoutSession.objects.filter(
            user=user
        ).order_by('-date')[:3]

        # Recent PRs (last 30 days)
        recent_prs = PersonalRecord.objects.filter(
            user=user,
            achieved_date__gte=today - timedelta(days=30)
        ).order_by('-achieved_date')[:3]

        # Workout streak (consecutive days with workouts)
        workout_streak = self._calculate_workout_streak(user, today)

        # Last workout date
        last_workout = WorkoutSession.objects.filter(user=user).order_by('-date').first()
        days_since_workout = None
        if last_workout:
            days_since_workout = (today - last_workout.date).days

        return {
            "latest_weight": latest_weight,
            "weight_change": weight_change,
            "weight_trend": weight_trend,
            "weight_entries_month": weights.filter(recorded_at__gte=month_ago).count(),
            "active_fast": active_fast,
            "fasting_active": active_fast is not None,
            "completed_fasts_month": completed_fasts_month,
            "latest_glucose": latest_glucose,
            # Medicine data
            "active_medicines": active_medicines.count(),
            "todays_medicine_schedule": todays_schedules,
            "medicine_doses_today": len(todays_schedules),
            "medicine_doses_taken_today": sum(1 for s in todays_schedules if s['taken']),
            "medicine_adherence_rate": adherence_rate,
            "medicines_need_refill": list(needs_refill),
            "medicines_need_refill_count": needs_refill.count(),
            # Workout data
            "workouts_this_week": workouts_week.count(),
            "recent_workouts": list(recent_workouts),
            "recent_prs": list(recent_prs),
            "workout_streak": workout_streak,
            "days_since_workout": days_since_workout,
            "last_workout": last_workout,
        }

    def _calculate_workout_streak(self, user, today):
        """Calculate consecutive days with workouts."""
        from apps.health.models import WorkoutSession

        workout_dates = WorkoutSession.objects.filter(
            user=user
        ).order_by('-date').values_list('date', flat=True).distinct()[:60]

        if not workout_dates:
            return 0

        streak = 0
        expected_date = today

        for workout_date in workout_dates:
            if workout_date == expected_date:
                streak += 1
                expected_date -= timedelta(days=1)
            elif workout_date < expected_date:
                break

        return streak

    def _get_scan_data(self, user, today, week_ago):
        """Get scan/camera activity data."""
        from apps.scan.models import ScanLog

        # Scans this week
        scans_week = ScanLog.objects.filter(
            user=user,
            created_at__gte=week_ago,
            status=ScanLog.STATUS_SUCCESS
        )

        # Category breakdown
        category_counts = {}
        for scan in scans_week:
            if scan.category:
                category_counts[scan.category] = category_counts.get(scan.category, 0) + 1

        # Most scanned category
        top_category = None
        if category_counts:
            top_category = max(category_counts, key=category_counts.get)

        # Recent scans with actions taken
        recent_scans = ScanLog.objects.filter(
            user=user,
            status=ScanLog.STATUS_SUCCESS
        ).exclude(action_taken='').order_by('-created_at')[:5]

        # Items logged via scan (entries created via AI camera this week)
        from apps.core.models import UserOwnedModel
        from apps.journal.models import JournalEntry
        from apps.health.models import Medicine, WorkoutSession

        ai_camera_entries = JournalEntry.objects.filter(
            user=user,
            created_via='ai_camera',
            created_at__gte=week_ago
        ).count()

        ai_camera_medicines = Medicine.objects.filter(
            user=user,
            created_via='ai_camera',
            created_at__gte=week_ago
        ).count()

        ai_camera_workouts = WorkoutSession.objects.filter(
            user=user,
            created_via='ai_camera',
            created_at__gte=week_ago
        ).count()

        total_items_from_scan = ai_camera_entries + ai_camera_medicines + ai_camera_workouts

        return {
            "scans_this_week": scans_week.count(),
            "scan_category_counts": category_counts,
            "top_scan_category": top_category,
            "recent_scans_with_action": list(recent_scans),
            "items_from_scan_week": total_items_from_scan,
            "ai_camera_entries": ai_camera_entries,
            "ai_camera_medicines": ai_camera_medicines,
            "ai_camera_workouts": ai_camera_workouts,
        }

    def _get_life_data(self, user, today):
        """Get life-related data."""
        from apps.life.models import Project, Task, LifeEvent
        
        week_ahead = today + timedelta(days=7)
        
        # Projects
        projects = Project.objects.filter(user=user)
        active_projects = projects.filter(status='active')
        
        # Tasks
        tasks = Task.objects.filter(user=user, is_completed=False)
        overdue_tasks = tasks.filter(due_date__lt=today)
        due_soon = tasks.filter(due_date__gte=today, due_date__lte=week_ahead)
        
        # Tasks completed today
        completed_today = Task.objects.filter(
            user=user,
            is_completed=True,
            completed_at__date=today
        ).count()
        
        # Upcoming events
        upcoming_events = LifeEvent.objects.filter(
            user=user,
            start_date__gte=today,
            start_date__lte=week_ahead
        ).order_by('start_date')[:5]
        
        return {
            "active_projects": active_projects.count(),
            "incomplete_tasks": tasks.count(),
            "overdue_tasks": overdue_tasks.count(),
            "tasks_due_soon": due_soon.count(),
            "completed_tasks_today": completed_today,
            "upcoming_events": list(upcoming_events),
            "upcoming_events_count": upcoming_events.count(),
        }
    
    def _get_purpose_data(self, user):
        """Get purpose-related data."""
        from apps.purpose.models import AnnualDirection, LifeGoal, ChangeIntention

        current_year = timezone.now().year

        # Look for direction for current year or next year (if planning ahead)
        direction = AnnualDirection.objects.filter(
            user=user, year__in=[current_year, current_year + 1]
        ).order_by('-year').first()
        
        goals = LifeGoal.objects.filter(user=user)
        active_goals = goals.filter(status='active')
        
        intentions = ChangeIntention.objects.filter(user=user, status='active')
        
        return {
            "word_of_year": direction.word_of_year if direction else None,
            "annual_direction": direction,
            "active_goals": active_goals.count(),
            "completed_goals": goals.filter(status='completed').count(),
            "active_intentions": intentions.count(),
        }
    
    def _get_ai_insights(self, user, prefs, user_data):
        """Get AI-generated insights."""
        try:
            from apps.ai.dashboard_ai import DashboardAI
            
            dashboard_ai = DashboardAI(user)
            
            # Get or generate daily insight
            daily_insight = dashboard_ai.get_daily_insight()
            
            # Get weekly summary if it's been generated
            weekly_summary = dashboard_ai.get_weekly_summary()
            
            # Check for things to celebrate
            celebrations = self._check_for_celebrations(user_data)
            
            # Check for accountability nudges
            nudges = self._check_for_nudges(user_data, prefs)
            
            return {
                "daily_insight": daily_insight,
                "weekly_summary": weekly_summary,
                "celebrations": celebrations,
                "nudges": nudges,
            }
        except Exception as e:
            import logging
            logging.error(f"AI insights error: {e}")
            return None
    
    def _check_for_celebrations(self, user_data):
        """Check for things worth celebrating."""
        celebrations = []

        # Journal streak
        streak = user_data.get("journal_streak", 0)
        if streak >= 7:
            celebrations.append({
                "type": "streak",
                "title": f"🔥 {streak}-Day Journal Streak!",
                "detail": "You're building a powerful reflection habit."
            })
        elif streak >= 3:
            celebrations.append({
                "type": "streak",
                "title": f"📝 {streak} Days in a Row!",
                "detail": "Keep the momentum going."
            })

        # Tasks completed today
        completed = user_data.get("completed_tasks_today", 0)
        if completed >= 5:
            celebrations.append({
                "type": "tasks",
                "title": f"⚡ {completed} Tasks Done Today!",
                "detail": "You're crushing it."
            })
        elif completed >= 3:
            celebrations.append({
                "type": "tasks",
                "title": f"✓ {completed} Tasks Completed",
                "detail": "Solid progress today."
            })

        # Weight trend
        if user_data.get("weight_trend") == "down" and user_data.get("weight_change"):
            celebrations.append({
                "type": "health",
                "title": f"📉 Down {abs(user_data['weight_change'])} lbs",
                "detail": "Your consistency is paying off."
            })

        # Answered prayers
        if user_data.get("recent_answered_prayer"):
            celebrations.append({
                "type": "faith",
                "title": "🙏 Prayer Answered",
                "detail": "God is faithful."
            })

        # Medicine adherence - perfect adherence
        adherence = user_data.get("medicine_adherence_rate")
        if adherence is not None and adherence >= 95:
            celebrations.append({
                "type": "medicine",
                "title": "💊 Perfect Medicine Adherence!",
                "detail": f"{adherence}% adherence this week. Keep it up!"
            })
        elif adherence is not None and adherence >= 80:
            celebrations.append({
                "type": "medicine",
                "title": f"💊 {adherence}% Adherence",
                "detail": "Great job staying on track with your medicines."
            })

        # All medicines taken today
        doses_today = user_data.get("medicine_doses_today", 0)
        taken_today = user_data.get("medicine_doses_taken_today", 0)
        if doses_today > 0 and taken_today == doses_today:
            celebrations.append({
                "type": "medicine",
                "title": "✅ All Doses Taken Today!",
                "detail": "You've taken all your scheduled medicines."
            })

        # Workout streak
        workout_streak = user_data.get("workout_streak", 0)
        if workout_streak >= 5:
            celebrations.append({
                "type": "workout",
                "title": f"💪 {workout_streak}-Day Workout Streak!",
                "detail": "Your dedication is inspiring."
            })
        elif workout_streak >= 3:
            celebrations.append({
                "type": "workout",
                "title": f"🏋️ {workout_streak} Days of Workouts!",
                "detail": "Building strong habits."
            })

        # Recent PRs
        recent_prs = user_data.get("recent_prs", [])
        if recent_prs:
            pr = recent_prs[0]  # Most recent PR
            celebrations.append({
                "type": "workout",
                "title": f"🏆 New PR: {pr.exercise.name}!",
                "detail": f"{pr.weight}lbs x {pr.reps} reps"
            })

        # Workouts this week
        workouts_week = user_data.get("workouts_this_week", 0)
        if workouts_week >= 5:
            celebrations.append({
                "type": "workout",
                "title": f"🔥 {workouts_week} Workouts This Week!",
                "detail": "Outstanding fitness commitment."
            })
        elif workouts_week >= 3:
            celebrations.append({
                "type": "workout",
                "title": f"💪 {workouts_week} Workouts This Week",
                "detail": "Staying active and strong."
            })

        # AI Camera usage
        items_from_scan = user_data.get("items_from_scan_week", 0)
        if items_from_scan >= 5:
            celebrations.append({
                "type": "scan",
                "title": f"📷 {items_from_scan} Items Logged via Camera!",
                "detail": "Smart use of the AI camera feature."
            })

        return celebrations[:3]  # Max 3 celebrations
    
    def _check_for_nudges(self, user_data, prefs):
        """Check for gentle accountability nudges."""
        nudges = []

        # Journal gap
        days_since = user_data.get("days_since_journal")
        if days_since and days_since >= 3:
            nudges.append({
                "type": "journal",
                "days": days_since,
                "action_url": "/journal/new/",
                "action_text": "Write Now"
            })

        # Overdue tasks
        overdue = user_data.get("overdue_tasks", 0)
        if overdue > 0:
            nudges.append({
                "type": "tasks",
                "count": overdue,
                "action_url": "/life/tasks/",
                "action_text": "View Tasks"
            })

        # No active goals (if purpose enabled)
        if prefs.purpose_enabled and user_data.get("active_goals", 0) == 0:
            nudges.append({
                "type": "goals",
                "action_url": "/purpose/goals/new/",
                "action_text": "Set a Goal"
            })

        # Missed medicine doses today (high priority)
        doses_today = user_data.get("medicine_doses_today", 0)
        taken_today = user_data.get("medicine_doses_taken_today", 0)
        pending_doses = doses_today - taken_today
        if pending_doses > 0:
            nudges.append({
                "type": "medicine",
                "count": pending_doses,
                "action_url": "/health/medicine/",
                "action_text": "Open Tracker"
            })

        # Low medicine adherence this week
        adherence = user_data.get("medicine_adherence_rate")
        if adherence is not None and adherence < 70:
            nudges.append({
                "type": "medicine_adherence",
                "adherence": adherence,
                "action_url": "/health/medicine/",
                "action_text": "View Schedule"
            })

        # Medicines needing refill
        refill_count = user_data.get("medicines_need_refill_count", 0)
        if refill_count > 0:
            nudges.append({
                "type": "refill",
                "count": refill_count,
                "action_url": "/health/medicine/",
                "action_text": "Check Refills"
            })

        # Workout gap
        days_since_workout = user_data.get("days_since_workout")
        if days_since_workout and days_since_workout >= 5:
            nudges.append({
                "type": "workout",
                "days": days_since_workout,
                "action_url": "/health/workouts/",
                "action_text": "Log Workout"
            })

        return nudges[:2]  # Max 2 nudges
    
    def _get_quick_stats(self, user_data):
        """Get quick stats for the header."""
        return {
            "journal_streak": user_data.get("journal_streak", 0),
            "active_goals": user_data.get("active_goals", 0),
            "tasks_today": user_data.get("completed_tasks_today", 0),
            "active_prayers": user_data.get("active_prayers", 0),
            # Medicine stats
            "medicine_doses_today": user_data.get("medicine_doses_today", 0),
            "medicine_doses_taken": user_data.get("medicine_doses_taken_today", 0),
            "medicine_adherence": user_data.get("medicine_adherence_rate"),
            # Workout stats
            "workouts_week": user_data.get("workouts_this_week", 0),
            "workout_streak": user_data.get("workout_streak", 0),
        }


class ConfigureDashboardView(LoginRequiredMixin, TemplateView):
    """
    Dashboard configuration view.
    
    Allows users to:
    - Show/hide tiles
    - Reorder tiles
    - Choose tile sizes (future)
    """
    template_name = "dashboard/configure.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        prefs = self.request.user.preferences
        context["current_config"] = prefs.dashboard_config or {}
        context["available_tiles"] = self.get_available_tiles()
        return context
    
    def get_available_tiles(self):
        """Get list of available tile types."""
        tiles = [
            {
                "type": "encouragement",
                "name": "Daily Encouragement",
                "description": "An uplifting message to start your day",
            },
            {
                "type": "journal_summary",
                "name": "Journal Summary",
                "description": "Recent journal activity and quick entry",
            },
            {
                "type": "quick_actions",
                "name": "Quick Actions",
                "description": "Fast access to common tasks",
            },
        ]
        
        # Add faith-specific tiles if enabled
        if self.request.user.preferences.faith_enabled:
            tiles.append({
                "type": "scripture",
                "name": "Daily Scripture",
                "description": "A verse to reflect on today",
            })
        
        return tiles
    
    def post(self, request, *args, **kwargs):
        """Save dashboard configuration."""
        try:
            config = json.loads(request.body)
            prefs = request.user.preferences
            prefs.dashboard_config = config
            prefs.save(update_fields=["dashboard_config", "updated_at"])
            return HttpResponse(status=200)
        except (json.JSONDecodeError, KeyError):
            return HttpResponse(status=400)


class DashboardDebugView(LoginRequiredMixin, View):
    """Temporary debug endpoint to diagnose dashboard errors."""

    def get(self, request, *args, **kwargs):
        import traceback
        errors = []
        data = {}

        user = request.user
        prefs = user.preferences
        data['user'] = user.email

        # Test the actual DashboardView methods
        dashboard_view = DashboardView()
        dashboard_view.request = request

        try:
            data['greeting'] = dashboard_view._get_greeting()
        except Exception as e:
            errors.append(f"_get_greeting error: {e}\n{traceback.format_exc()}")

        try:
            data['encouragement'] = str(dashboard_view._get_daily_encouragement(prefs.faith_enabled))
        except Exception as e:
            errors.append(f"_get_daily_encouragement error: {e}\n{traceback.format_exc()}")

        try:
            user_data = dashboard_view._gather_comprehensive_data(user, prefs)
            data['user_data_keys'] = list(user_data.keys())
            # Check specific keys that might cause template errors
            data['recent_workouts_count'] = len(user_data.get('recent_workouts', []))
            data['recent_prs_count'] = len(user_data.get('recent_prs', []))
            data['todays_medicine_count'] = len(user_data.get('todays_medicine_schedule', []))
        except Exception as e:
            errors.append(f"_gather_comprehensive_data error: {e}\n{traceback.format_exc()}")

        try:
            if prefs.ai_enabled:
                ai_insights = dashboard_view._get_ai_insights(user, prefs, user_data)
                data['ai_insights'] = 'generated' if ai_insights else 'none'
            else:
                data['ai_insights'] = 'disabled'
        except Exception as e:
            errors.append(f"_get_ai_insights error: {e}\n{traceback.format_exc()}")

        try:
            quick_stats = dashboard_view._get_quick_stats(user_data)
            data['quick_stats'] = quick_stats
        except Exception as e:
            errors.append(f"_get_quick_stats error: {e}\n{traceback.format_exc()}")

        # Try to render the template
        try:
            from django.template.loader import render_to_string
            context = {
                'user': user,
                'current_date': timezone.now(),
                'greeting': data.get('greeting', 'Hello'),
                'faith_enabled': prefs.faith_enabled,
                'encouragement': None,
                'user_data': user_data if 'user_data_keys' in data else {},
                'ai_enabled': prefs.ai_enabled,
                'ai_insights': None,
                'quick_stats': data.get('quick_stats', {}),
                'journal_enabled': prefs.journal_enabled,
                'health_enabled': prefs.health_enabled,
                'life_enabled': prefs.life_enabled,
                'purpose_enabled': prefs.purpose_enabled,
            }
            html = render_to_string('dashboard/home.html', context, request=request)
            data['template_rendered'] = True
            data['template_length'] = len(html)
        except Exception as e:
            errors.append(f"Template render error: {e}\n{traceback.format_exc()}")
            data['template_rendered'] = False

        data['errors'] = errors
        return JsonResponse(data)


class WeightChartDataView(LoginRequiredMixin, View):
    """API endpoint for weight chart data."""

    def get(self, request, *args, **kwargs):
        from apps.health.models import WeightEntry

        days = int(request.GET.get('days', 30))
        since = timezone.now() - timedelta(days=days)

        entries = WeightEntry.objects.filter(
            user=request.user,
            recorded_at__gte=since
        ).order_by('recorded_at')

        data = {
            'labels': [e.recorded_at.strftime('%b %d') for e in entries],
            'values': [float(e.value_in_lb) for e in entries],
        }

        return JsonResponse(data)


class JournalSummaryTileView(LoginRequiredMixin, TemplateView):
    """HTMX endpoint for journal summary tile."""
    template_name = "dashboard/tiles/journal_summary.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.journal.models import JournalEntry
        
        user = self.request.user
        entries = JournalEntry.objects.filter(user=user)
        
        context["recent_entries"] = entries.order_by("-entry_date")[:3]
        context["total_count"] = entries.count()
        
        return context


class EncouragementTileView(LoginRequiredMixin, TemplateView):
    """HTMX endpoint for encouragement tile."""
    template_name = "dashboard/tiles/encouragement.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        faith_enabled = self.request.user.preferences.faith_enabled
        
        queryset = DailyEncouragement.objects.filter(is_active=True)
        if not faith_enabled:
            queryset = queryset.filter(is_faith_specific=False)
        
        if queryset.exists():
            context["encouragement"] = random.choice(list(queryset))
        else:
            context["encouragement"] = {
                "message": "Take a moment to breathe. You're exactly where you need to be.",
            }
        
        return context