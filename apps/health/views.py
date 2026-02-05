"""
Health Views - Physical wellness tracking.
"""

import json
import pytz
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Max, Min, Sum, F
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from django.http import JsonResponse
from django.template.loader import render_to_string

from apps.core.utils import get_user_today, user_log_id
from apps.core.views import SaveAddAnotherMixin, UndoDeleteMixin
from apps.help.mixins import HelpContextMixin

from django.shortcuts import render

from .forms import (
    BloodOxygenEntryForm,
    BloodPressureEntryForm,
    CustomFoodForm,
    FastingWindowForm,
    FoodEntryForm,
    GlucoseEntryForm,
    HeartRateEntryForm,
    MedicineForm,
    MedicineLogEditForm,
    MedicineScheduleForm,
    PRNDoseForm,
    QuickSleepForm,
    QuickWeightForm,
    SleepEntryForm,
    StepsEntryForm,
    UpdateSupplyForm,
    WeightEntryForm,
)
from .models import (
    BloodOxygenEntry,
    BloodPressureEntry,
    BodyTemperatureEntry,
    CardioDetails,
    ClassDetails,
    CustomFood,
    Exercise,
    ExerciseSet,
    FastingWindow,
    FoodEntry,
    GlucoseEntry,
    HeartRateEntry,
    Medicine,
    MedicineLog,
    MedicineSchedule,
    NutritionGoals,
    PersonalRecord,
    SleepEntry,
    StepsEntry,
    TemplateExercise,
    TemplateExerciseSet,
    WaterEntry,
    WeightEntry,
    WorkoutExercise,
    WorkoutSession,
    WorkoutTemplate,
)


class HealthLandingView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Health landing page - choose between Physical Health and Cognitive Health.
    """

    template_name = "health/landing.html"
    help_context_id = "HEALTH_LANDING"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [
            {"title": "Health", "url": None},
        ]
        return context


class HealthHomeView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Physical Health home - overview of all physical health metrics.
    """

    template_name = "health/home.html"
    help_context_id = "HEALTH_PHYSICAL_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        # Weight summary
        weight_entries = WeightEntry.objects.filter(user=user)
        if weight_entries.exists():
            latest_weight = weight_entries.first()
            context["latest_weight"] = latest_weight
            context["weight_count"] = weight_entries.count()
            
            # Weight change in last 30 days
            month_weights = weight_entries.filter(recorded_at__gte=month_ago)
            if month_weights.count() >= 2:
                oldest = month_weights.last()
                newest = month_weights.first()
                change = float(newest.value_in_lb) - float(oldest.value_in_lb)
                context["weight_change_30d"] = round(change, 1)
        
        # Active fasting window
        context["active_fast"] = FastingWindow.objects.filter(
            user=user,
            ended_at__isnull=True,
        ).first()
        
        # Recent fasting stats
        recent_fasts = FastingWindow.objects.filter(
            user=user,
            ended_at__isnull=False,
            started_at__gte=month_ago,
        )
        if recent_fasts.exists():
            context["fasts_this_month"] = recent_fasts.count()
            avg_duration = sum(f.duration_hours for f in recent_fasts) / recent_fasts.count()
            context["avg_fast_duration"] = round(avg_duration, 1)
        
        # Heart rate summary
        hr_entries = HeartRateEntry.objects.filter(user=user)
        if hr_entries.exists():
            context["latest_heart_rate"] = hr_entries.first()
            resting_hr = hr_entries.filter(context__in=["resting", "morning"])
            if resting_hr.exists():
                avg = resting_hr.aggregate(avg=Avg("bpm"))["avg"]
                context["avg_resting_hr"] = round(avg)

        # Steps summary
        steps_entries = StepsEntry.objects.filter(user=user)
        if steps_entries.exists():
            context["latest_steps"] = steps_entries.first()
            # 7-day average
            week_ago = now - timedelta(days=7)
            week_steps = steps_entries.filter(logged_date__gte=week_ago.date())
            if week_steps.exists():
                avg = week_steps.aggregate(avg=Avg("count"))["avg"]
                context["avg_steps"] = round(avg) if avg else None

        # Sleep summary
        sleep_entries = SleepEntry.objects.filter(user=user)
        if sleep_entries.exists():
            context["latest_sleep"] = sleep_entries.first()
            context["sleep_count"] = sleep_entries.count()
            # 7-day average
            week_sleep = sleep_entries.filter(sleep_date__gte=week_ago.date())
            if week_sleep.exists():
                total_minutes = sum(e.total_duration_minutes or 0 for e in week_sleep)
                avg_hours = total_minutes / week_sleep.count() / 60
                context["avg_sleep_hours"] = round(avg_hours, 1)

                # Average sleep quality (for entries that have it)
                quality_map = {'excellent': 5, 'good': 4, 'fair': 3, 'poor': 2, 'terrible': 1}
                entries_with_quality = [e for e in week_sleep if e.quality_rating]
                if entries_with_quality:
                    avg_score = sum(quality_map.get(e.quality_rating, 3) for e in entries_with_quality) / len(entries_with_quality)
                    # Map back to label
                    if avg_score >= 4.5:
                        context["avg_sleep_quality"] = "Excellent"
                    elif avg_score >= 3.5:
                        context["avg_sleep_quality"] = "Good"
                    elif avg_score >= 2.5:
                        context["avg_sleep_quality"] = "Fair"
                    elif avg_score >= 1.5:
                        context["avg_sleep_quality"] = "Poor"
                    else:
                        context["avg_sleep_quality"] = "Terrible"

        # Water/Hydration summary
        today = get_user_today(user)
        water_progress = WaterEntry.get_daily_goal_progress(user, today)
        context["water_today_oz"] = water_progress["total_oz"]
        context["water_goal_oz"] = water_progress["goal_oz"]
        context["water_today_percentage"] = water_progress["percentage"]
        context["water_goal_met"] = water_progress["goal_met"]

        water_entries = WaterEntry.objects.filter(user=user)
        if water_entries.exists():
            context["water_entry_count"] = water_entries.count()
            # 7-day average
            week_ago = now - timedelta(days=7)
            week_water = water_entries.filter(logged_date__gte=week_ago.date())
            if week_water.exists():
                # Calculate daily totals, then average
                daily_totals = {}
                for entry in week_water:
                    day = entry.logged_date
                    if day not in daily_totals:
                        daily_totals[day] = 0
                    daily_totals[day] += entry.amount_oz
                if daily_totals:
                    context["avg_water_oz"] = round(sum(daily_totals.values()) / len(daily_totals), 1)

        # Glucose summary
        glucose_entries = GlucoseEntry.objects.filter(user=user)
        if glucose_entries.exists():
            context["latest_glucose"] = glucose_entries.first()
            fasting_glucose = glucose_entries.filter(context="fasting")
            if fasting_glucose.exists():
                avg = fasting_glucose.aggregate(avg=Avg("value"))["avg"]
                context["avg_fasting_glucose"] = round(avg, 1)

        # Blood Pressure summary
        bp_entries = BloodPressureEntry.objects.filter(user=user)
        if bp_entries.exists():
            context["latest_blood_pressure"] = bp_entries.first()
            stats = bp_entries.aggregate(
                avg_systolic=Avg("systolic"),
                avg_diastolic=Avg("diastolic"),
            )
            if stats["avg_systolic"]:
                context["avg_systolic"] = round(stats["avg_systolic"])
            if stats["avg_diastolic"]:
                context["avg_diastolic"] = round(stats["avg_diastolic"])

        # Blood Oxygen summary
        bo_entries = BloodOxygenEntry.objects.filter(user=user)
        if bo_entries.exists():
            context["latest_blood_oxygen"] = bo_entries.first()
            avg_spo2 = bo_entries.aggregate(avg=Avg("spo2"))["avg"]
            if avg_spo2:
                context["avg_spo2"] = round(avg_spo2)

        # Body Temperature summary
        temp_entries = BodyTemperatureEntry.objects.filter(user=user)
        if temp_entries.exists():
            context["latest_body_temperature"] = temp_entries.first()
            context["has_body_temperature"] = True

        # Advanced metrics (derived from sleep data)
        # These show dashboard links when user has data
        sleep_with_hrv = SleepEntry.objects.filter(user=user, hrv_value__isnull=False)
        if sleep_with_hrv.exists():
            context["has_hrv_data"] = True
            latest_hrv = sleep_with_hrv.first()
            context["latest_hrv"] = latest_hrv.hrv_value

        sleep_with_vo2 = SleepEntry.objects.filter(user=user, vo2_max__isnull=False)
        if sleep_with_vo2.exists():
            context["has_vo2_max_data"] = True
            latest_vo2 = sleep_with_vo2.first()
            context["latest_vo2_max"] = latest_vo2.vo2_max

        sleep_with_rr = SleepEntry.objects.filter(user=user, respiratory_rate__isnull=False)
        if sleep_with_rr.exists():
            context["has_respiratory_rate_data"] = True
            latest_rr = sleep_with_rr.first()
            context["latest_respiratory_rate"] = latest_rr.respiratory_rate

        sleep_with_caffeine = SleepEntry.objects.filter(user=user, caffeine_mg__isnull=False)
        if sleep_with_caffeine.exists():
            context["has_caffeine_data"] = True

        sleep_with_mindful = SleepEntry.objects.filter(user=user, mindful_minutes__isnull=False)
        if sleep_with_mindful.exists():
            context["has_mindful_minutes_data"] = True

        # Medicine summary
        today = get_user_today(user)
        active_medicines = Medicine.objects.filter(
            user=user,
            medicine_status=Medicine.STATUS_ACTIVE,
        )
        context["medicine_count"] = active_medicines.count()

        if active_medicines.exists():
            # Count today's scheduled doses
            total_scheduled = 0
            taken_count = 0
            overdue_count = 0

            for medicine in active_medicines.filter(is_prn=False):
                for schedule in medicine.schedules.filter(is_active=True):
                    if schedule.applies_to_day(today.weekday()):
                        total_scheduled += 1
                        log = MedicineLog.objects.filter(
                            medicine=medicine,
                            schedule=schedule,
                            scheduled_date=today,
                        ).first()

                        if log and log.log_status in [
                            MedicineLog.STATUS_TAKEN,
                            MedicineLog.STATUS_LATE,
                        ]:
                            taken_count += 1
                        elif not log or log.log_status not in [
                            MedicineLog.STATUS_TAKEN,
                            MedicineLog.STATUS_LATE,
                            MedicineLog.STATUS_SKIPPED,
                        ]:
                            # Check if overdue using user's timezone
                            from datetime import datetime, timedelta as td

                            # Get user's timezone (use timezone_iana for legacy format support)
                            try:
                                user_tz = pytz.timezone(user.preferences.timezone_iana)
                            except (AttributeError, pytz.UnknownTimeZoneError):
                                user_tz = pytz.UTC

                            # Convert current time to user's local time
                            now_local = now.astimezone(user_tz)

                            # Create deadline from user's local date and scheduled time
                            scheduled_dt = datetime.combine(today, schedule.scheduled_time)
                            grace_minutes = medicine.grace_period_minutes
                            deadline = scheduled_dt + td(minutes=grace_minutes)

                            # Compare in user's local time (both naive)
                            now_local_naive = now_local.replace(tzinfo=None)
                            if now_local_naive > deadline:
                                overdue_count += 1

            context["medicine_scheduled_today"] = total_scheduled
            context["medicine_taken_today"] = taken_count
            context["medicine_overdue"] = overdue_count

            # Check for low supply
            low_supply = [m for m in active_medicines if m.needs_refill]
            context["medicine_low_supply"] = len(low_supply)

        # Nutrition summary for today
        from django.db.models import Sum
        today_entries = FoodEntry.objects.filter(
            user=user,
            logged_date=today,
        )
        if today_entries.exists():
            totals = today_entries.aggregate(calories=Sum('total_calories'))
            context["nutrition_today_calories"] = totals['calories'] or 0
            context["nutrition_today_entries"] = today_entries.count()

        # Medical Providers summary
        from .models import MedicalProvider
        providers = MedicalProvider.objects.filter(user=user)
        context["provider_count"] = providers.count()
        context["primary_provider"] = providers.filter(is_primary=True).first()

        # Fitness/Workout summary
        workouts = WorkoutSession.objects.filter(user=user)
        if workouts.exists():
            context["latest_workout"] = workouts.first()
            context["total_workouts"] = workouts.count()

            # Workouts this week
            week_start = today - timedelta(days=today.weekday())  # Monday
            week_workouts = workouts.filter(date__gte=week_start)
            context["workouts_this_week"] = week_workouts.count()

            # Total duration this week
            week_duration = week_workouts.filter(
                duration_minutes__isnull=False
            ).aggregate(total=Sum('duration_minutes'))['total'] or 0
            context["fitness_duration_this_week"] = week_duration

            # Workouts this month
            month_start = today.replace(day=1)
            month_workouts = workouts.filter(date__gte=month_start)
            context["workouts_this_month"] = month_workouts.count()

        # Cycle Tracking summary (only if opted in)
        try:
            from .models import CycleSettings, CycleDailyLog, Cycle

            cycle_settings = CycleSettings.objects.filter(
                user=user, status='active', cycle_tracking_enabled=True
            ).first()

            if cycle_settings:
                context['cycle_tracking_enabled'] = True

                # Get current phase info (wrapped separately to isolate errors)
                try:
                    from .services.cycle_phase import get_current_phase
                    phase_info = get_current_phase(user)
                    if phase_info:
                        context['cycle_current_phase'] = phase_info
                except Exception:
                    pass

                # Get days until next period from prediction
                try:
                    from .services.cycle_prediction import CyclePredictionService
                    prediction_service = CyclePredictionService(user)
                    latest_prediction = prediction_service.get_latest_prediction()
                    if latest_prediction and latest_prediction.predicted_period_start:
                        days_until = (latest_prediction.predicted_period_start - today).days
                        context['cycle_days_until_period'] = days_until
                        # Also pass absolute value for "days late" display
                        context['cycle_days_late'] = abs(days_until) if days_until < 0 else 0
                except Exception:
                    pass

                # Get daily log count
                try:
                    log_count = CycleDailyLog.objects.filter(user=user).count()
                    context['cycle_day_count'] = log_count
                except Exception:
                    pass

                # Get average cycle length if we have enough data
                try:
                    completed_cycles = Cycle.objects.filter(
                        user=user, end_date__isnull=False
                    )
                    if completed_cycles.count() >= 2:
                        # Calculate average manually since cycle_length is a property
                        cycle_lengths = [c.cycle_length for c in completed_cycles if c.cycle_length]
                        if cycle_lengths:
                            context['cycle_avg_length'] = round(sum(cycle_lengths) / len(cycle_lengths))
                except Exception:
                    pass
        except Exception:
            pass

        # Generate AI insight if user has AI enabled and consented
        context['ai_insight'] = None
        context['ai_enabled'] = False
        try:
            prefs = user.preferences
            if prefs.ai_enabled and prefs.ai_data_consent:
                context['ai_enabled'] = True
                from apps.ai.services import ai_service
                health_data = {
                    'weight_count': context.get('weight_count', 0),
                    'weight_change_30d': context.get('weight_change_30d'),
                    'fasts_this_month': context.get('fasts_this_month', 0),
                    'avg_fast_duration': context.get('avg_fast_duration'),
                    'avg_resting_hr': context.get('avg_resting_hr'),
                    'avg_fasting_glucose': context.get('avg_fasting_glucose'),
                    'avg_blood_pressure': f"{context.get('avg_systolic')}/{context.get('avg_diastolic')}" if context.get('avg_systolic') else None,
                    'has_heart_rate': 'latest_heart_rate' in context,
                    'has_glucose': 'latest_glucose' in context,
                    'has_blood_pressure': 'latest_blood_pressure' in context,
                    'sleep_count': context.get('sleep_count', 0),
                    'avg_sleep_hours': context.get('avg_sleep_hours'),
                    'avg_sleep_quality': context.get('avg_sleep_quality'),
                }
                context['ai_insight'] = ai_service.generate_health_home_insight(
                    health_data,
                    faith_enabled=prefs.faith_enabled,
                    coaching_style=prefs.ai_coaching_style
                )
        except Exception:
            pass

        # Breadcrumbs for Physical Health
        context["breadcrumbs"] = [
            {"title": "Health", "url": reverse("health:landing")},
            {"title": "Physical Health", "url": None},
        ]

        return context


# Weight Views

class WeightListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """
    List weight entries with stats.
    """

    model = WeightEntry
    template_name = "health/weight_list.html"
    context_object_name = "entries"
    paginate_by = 30
    help_context_id = "HEALTH_WEIGHT"

    def get_queryset(self):
        return WeightEntry.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = self.get_queryset()

        if entries.exists():
            context["latest"] = entries.first()
            context["total_count"] = entries.count()

            # Stats for last 30 entries
            values = [e.value_in_lb for e in entries[:30]]
            if values:
                context["min_weight"] = min(values)
                context["max_weight"] = max(values)
                context["avg_weight"] = round(sum(values) / len(values), 1)

            # Total weight loss calculation (first entry to last entry)
            first_entry = entries.last()  # Oldest entry (queryset ordered by -recorded_at)
            latest_entry = entries.first()  # Most recent entry
            if first_entry and latest_entry and first_entry != latest_entry:
                first_weight = float(first_entry.value_in_lb)
                latest_weight = float(latest_entry.value_in_lb)
                weight_change = latest_weight - first_weight
                context["weight_change"] = round(weight_change, 1)
                context["first_entry"] = first_entry
                context["first_weight"] = round(first_weight, 1)
                context["latest_weight_lb"] = round(latest_weight, 1)

            # Chart data - all entries for the graph (up to 100 for performance)
            chart_entries = list(entries[:100])
            chart_entries.reverse()  # Show oldest to newest for chart
            chart_data = []
            for entry in chart_entries:
                chart_data.append({
                    "date": entry.recorded_at.strftime("%b %d, %Y"),
                    "weight": float(entry.value_in_lb),
                    "recorded_at": entry.recorded_at.isoformat(),
                })
            context["chart_data"] = chart_data

        return context


class WeightCreateView(HelpContextMixin, SaveAddAnotherMixin, LoginRequiredMixin, CreateView):
    """
    Log a new weight entry.
    """

    model = WeightEntry
    form_class = WeightEntryForm
    template_name = "health/weight_form.html"
    success_url = reverse_lazy("health:weight_list")
    save_add_another_message = "Weight logged. Add another!"
    help_context_id = "HEALTH_WEIGHT"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        if 'save_add_another' not in self.request.POST:
            messages.success(self.request, "Weight logged.")
        return super().form_valid(form)


class WeightUpdateView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """
    Edit a weight entry.
    """

    model = WeightEntry
    form_class = WeightEntryForm
    template_name = "health/weight_form.html"
    success_url = reverse_lazy("health:weight_list")
    help_context_id = "HEALTH_WEIGHT"

    def get_queryset(self):
        return WeightEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class WeightDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a weight entry.
    Supports undo via toast notification for AJAX requests.
    """

    model = WeightEntry
    item_type = 'health.weightentry'
    item_name = 'weight entry'
    success_url = 'health:weight_list'

    def get_object(self):
        return get_object_or_404(
            WeightEntry.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


# Fasting Views

class FastingListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """
    List fasting windows.
    """

    model = FastingWindow
    template_name = "health/fasting_list.html"
    context_object_name = "fasts"
    paginate_by = 20
    help_context_id = "HEALTH_FASTING"

    def get_queryset(self):
        return FastingWindow.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_fast"] = FastingWindow.objects.filter(
            user=self.request.user,
            ended_at__isnull=True,
        ).first()
        # Get user's timezone for template display (use timezone_iana for legacy format support)
        try:
            tz_name = self.request.user.preferences.timezone_iana
            context["user_timezone"] = pytz.timezone(tz_name)
        except Exception:
            context["user_timezone"] = pytz.UTC
        return context


class StartFastView(LoginRequiredMixin, CreateView):
    """
    Start a new fasting window.
    """

    model = FastingWindow
    form_class = FastingWindowForm
    template_name = "health/fasting_form.html"
    success_url = reverse_lazy("health:fasting_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        """Pre-select user's default fasting type from preferences."""
        initial = super().get_initial()
        if hasattr(self.request.user, 'preferences'):
            initial['fasting_type'] = self.request.user.preferences.default_fasting_type
        return initial

    def get_context_data(self, **kwargs):
        """Add fasting type descriptions to template context."""
        context = super().get_context_data(**kwargs)
        from apps.users.models import UserPreferences
        context['fasting_descriptions'] = UserPreferences.FASTING_TYPE_DESCRIPTIONS
        return context

    def form_valid(self, form):
        # Check for existing active fast
        active = FastingWindow.objects.filter(
            user=self.request.user,
            ended_at__isnull=True,
        ).exists()
        
        if active:
            messages.warning(
                self.request,
                "You already have an active fast. End it first."
            )
            return redirect("health:fasting_list")
        
        form.instance.user = self.request.user
        
        # Set target hours based on fasting type
        fasting_type = form.cleaned_data.get("fasting_type")
        targets = {
            "16:8": 16,
            "18:6": 18,
            "20:4": 20,
            "OMAD": 23,
            "24h": 24,
            "36h": 36,
        }
        form.instance.target_hours = targets.get(fasting_type)
        
        messages.success(self.request, "Fast started. Stay strong!")
        return super().form_valid(form)


class EndFastView(LoginRequiredMixin, View):
    """
    End an active fasting window.
    """

    def post(self, request, pk):
        fast = get_object_or_404(
            FastingWindow.objects.filter(user=request.user, ended_at__isnull=True),
            pk=pk
        )
        fast.end_fast()
        
        duration = fast.duration_hours
        messages.success(
            request,
            f"Fast completed! You fasted for {duration:.1f} hours."
        )
        return redirect("health:fasting_list")


class FastingUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edit a fasting window.
    """

    model = FastingWindow
    form_class = FastingWindowForm
    template_name = "health/fasting_form.html"
    success_url = reverse_lazy("health:fasting_list")

    def get_queryset(self):
        return FastingWindow.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class FastingDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a fasting window.
    Supports undo via toast notification for AJAX requests.
    """

    model = FastingWindow
    item_type = 'health.fastingwindow'
    item_name = 'fasting window'
    success_url = 'health:fasting_list'

    def get_object(self):
        return get_object_or_404(
            FastingWindow.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


# Heart Rate Views

class HeartRateListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """
    List heart rate entries.
    """

    model = HeartRateEntry
    template_name = "health/heartrate_list.html"
    context_object_name = "entries"
    paginate_by = 30
    help_context_id = "HEALTH_HEART_RATE"

    def get_queryset(self):
        return HeartRateEntry.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = self.get_queryset()
        
        if entries.exists():
            context["latest"] = entries.first()
            
            # Resting HR stats
            resting = entries.filter(context__in=["resting", "morning"])
            if resting.exists():
                stats = resting.aggregate(
                    avg=Avg("bpm"),
                    min=Min("bpm"),
                    max=Max("bpm"),
                )
                context["resting_avg"] = round(stats["avg"])
                context["resting_min"] = stats["min"]
                context["resting_max"] = stats["max"]
        
        return context


class HeartRateCreateView(HelpContextMixin, SaveAddAnotherMixin, LoginRequiredMixin, CreateView):
    """
    Log a new heart rate entry.
    """

    model = HeartRateEntry
    form_class = HeartRateEntryForm
    template_name = "health/heartrate_form.html"
    success_url = reverse_lazy("health:heartrate_list")
    save_add_another_message = "Heart rate logged. Add another!"
    help_context_id = "HEALTH_HEART_RATE"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        if 'save_add_another' not in self.request.POST:
            messages.success(self.request, "Heart rate logged.")
        return super().form_valid(form)


class HeartRateUpdateView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """
    Edit a heart rate entry.
    """

    model = HeartRateEntry
    form_class = HeartRateEntryForm
    template_name = "health/heartrate_form.html"
    success_url = reverse_lazy("health:heartrate_list")
    help_context_id = "HEALTH_HEART_RATE"

    def get_queryset(self):
        return HeartRateEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class HeartRateDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a heart rate entry.
    Supports undo via toast notification for AJAX requests.
    """

    model = HeartRateEntry
    item_type = 'health.heartrateentry'
    item_name = 'heart rate entry'
    success_url = 'health:heartrate_list'

    def get_object(self):
        return get_object_or_404(
            HeartRateEntry.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


# =============================================================================
# STEPS VIEWS
# =============================================================================


class StepsListView(LoginRequiredMixin, ListView):
    """
    List steps entries.
    """

    model = StepsEntry
    template_name = "health/steps_list.html"
    context_object_name = "entries"
    paginate_by = 30

    def get_queryset(self):
        return StepsEntry.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = self.get_queryset()

        if entries.exists():
            context["latest"] = entries.first()
            context["total_count"] = entries.count()

            # Stats for past 7 days
            week_ago = timezone.now() - timedelta(days=7)
            week_entries = entries.filter(logged_date__gte=week_ago.date())
            if week_entries.exists():
                stats = week_entries.aggregate(
                    avg=Avg("count"),
                    total=Sum("count"),
                    max=Max("count"),
                )
                context["week_avg"] = round(stats["avg"]) if stats["avg"] else 0
                context["week_total"] = stats["total"] or 0
                context["week_max"] = stats["max"] or 0
                context["week_count"] = week_entries.count()

            # Goals met count
            goals_met = entries.filter(
                goal__isnull=False,
                count__gte=F("goal")
            ).count()
            context["goals_met"] = goals_met

            # Chart data for last 14 days
            two_weeks_ago = timezone.now() - timedelta(days=14)
            chart_entries = entries.filter(
                logged_date__gte=two_weeks_ago.date()
            ).order_by("logged_date")
            if chart_entries.exists():
                context["chart_labels"] = json.dumps([
                    e.logged_date.strftime("%m/%d") for e in chart_entries
                ])
                context["chart_data"] = json.dumps([
                    e.count for e in chart_entries
                ])
                # Include goals if available
                context["chart_goals"] = json.dumps([
                    e.goal if e.goal else None for e in chart_entries
                ])

        return context


class StepsCreateView(SaveAddAnotherMixin, LoginRequiredMixin, CreateView):
    """
    Log a new steps entry.
    """

    model = StepsEntry
    form_class = StepsEntryForm
    template_name = "health/steps_form.html"
    success_url = reverse_lazy("health:steps_list")
    save_add_another_message = "Steps logged. Add another!"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        if 'save_add_another' not in self.request.POST:
            messages.success(self.request, "Steps logged.")
        return super().form_valid(form)


class StepsUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edit a steps entry.
    """

    model = StepsEntry
    form_class = StepsEntryForm
    template_name = "health/steps_form.html"
    success_url = reverse_lazy("health:steps_list")

    def get_queryset(self):
        return StepsEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class StepsDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a steps entry.
    Supports undo via toast notification for AJAX requests.
    """

    model = StepsEntry
    item_type = 'health.stepsentry'
    item_name = 'steps entry'
    success_url = 'health:steps_list'

    def get_object(self):
        return get_object_or_404(
            StepsEntry.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


class BulkDeleteStepsView(LoginRequiredMixin, View):
    """
    Bulk delete steps entries.
    """

    def post(self, request):
        ids = request.POST.getlist("ids[]")
        if ids:
            deleted_count = StepsEntry.objects.filter(
                user=request.user,
                pk__in=ids
            ).delete()[0]
            messages.success(request, f"Deleted {deleted_count} steps entries.")
        return redirect("health:steps_list")


# =============================================================================
# Water / Hydration Views
# =============================================================================


class WaterListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """
    List water/hydration entries.
    """

    model = WaterEntry
    template_name = "health/water_list.html"
    context_object_name = "entries"
    paginate_by = 30
    help_context_id = "HEALTH_WATER"

    def get_queryset(self):
        return WaterEntry.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)
        entries = self.get_queryset()

        # Today's progress
        today_progress = WaterEntry.get_daily_goal_progress(user, today)
        context["today_total"] = today_progress["total_oz"]
        context["today_goal"] = today_progress["goal_oz"]
        context["today_percentage"] = today_progress["percentage"]
        context["today_goal_met"] = today_progress["goal_met"]

        if entries.exists():
            context["latest"] = entries.first()
            context["total_count"] = entries.count()

            # Stats for past 7 days
            week_ago = timezone.now() - timedelta(days=7)
            week_entries = entries.filter(logged_date__gte=week_ago.date())
            if week_entries.exists():
                # Calculate daily totals for the week
                daily_totals = {}
                for entry in week_entries:
                    day = entry.logged_date
                    if day not in daily_totals:
                        daily_totals[day] = 0
                    daily_totals[day] += entry.amount_oz

                if daily_totals:
                    totals = list(daily_totals.values())
                    context["week_avg"] = round(sum(totals) / len(totals), 1)
                    context["week_total"] = round(sum(totals), 1)
                    context["week_max"] = round(max(totals), 1)
                    context["week_days"] = len(totals)

            # Chart data for last 14 days
            two_weeks_ago = timezone.now() - timedelta(days=14)
            chart_entries = entries.filter(
                logged_date__gte=two_weeks_ago.date()
            )
            if chart_entries.exists():
                # Aggregate by day
                daily_data = {}
                for entry in chart_entries:
                    day = entry.logged_date
                    if day not in daily_data:
                        daily_data[day] = 0
                    daily_data[day] += entry.amount_oz

                # Sort by date
                sorted_days = sorted(daily_data.keys())
                context["chart_labels"] = json.dumps([
                    d.strftime("%m/%d") for d in sorted_days
                ])
                context["chart_data"] = json.dumps([
                    round(daily_data[d], 1) for d in sorted_days
                ])

        return context


class WaterCreateView(SaveAddAnotherMixin, LoginRequiredMixin, CreateView):
    """
    Log a new water entry.
    """

    model = WaterEntry
    fields = ["amount", "unit", "container", "logged_date", "notes"]
    template_name = "health/water_form.html"
    success_url = reverse_lazy("health:water_list")
    save_add_another_message = "Water logged. Add another!"

    def get_initial(self):
        initial = super().get_initial()
        initial["logged_date"] = get_user_today(self.request.user)
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        if 'save_add_another' not in self.request.POST:
            messages.success(self.request, "Water logged.")
        return super().form_valid(form)


class WaterUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edit a water entry.
    """

    model = WaterEntry
    fields = ["amount", "unit", "container", "logged_date", "notes"]
    template_name = "health/water_form.html"
    success_url = reverse_lazy("health:water_list")

    def get_queryset(self):
        return WaterEntry.objects.filter(user=self.request.user)


class WaterDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a water entry.
    Supports undo via toast notification for AJAX requests.
    """

    model = WaterEntry
    item_type = 'health.waterentry'
    item_name = 'water entry'
    success_url = 'health:water_list'

    def get_object(self):
        return get_object_or_404(
            WaterEntry.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


class QuickWaterLogView(LoginRequiredMixin, View):
    """
    Quick log water from dashboard or widget.
    Accepts preset amounts for fast logging.
    """

    def post(self, request):
        preset = request.POST.get("preset", "8")  # Default to 8oz glass
        try:
            amount = float(preset)
        except ValueError:
            amount = 8.0

        WaterEntry.objects.create(
            user=request.user,
            amount=amount,
            unit="oz",
            container="glass" if amount <= 12 else "bottle",
            logged_date=get_user_today(request.user),
        )

        messages.success(request, f"Logged {amount}oz of water!")

        # Handle AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            today_progress = WaterEntry.get_daily_goal_progress(
                request.user,
                get_user_today(request.user)
            )
            return JsonResponse({
                "success": True,
                "total_oz": today_progress["total_oz"],
                "percentage": today_progress["percentage"],
                "goal_met": today_progress["goal_met"],
            })

        return redirect(request.POST.get("next", "health:water_list"))


# NOTE: Glucose views moved to end of file with Dexcom integration views


class QuickLogView(LoginRequiredMixin, TemplateView):
    """
    Quick log modal/widget for dashboard.
    """

    template_name = "health/quick_log.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["weight_form"] = QuickWeightForm()
        return context

    def post(self, request, *args, **kwargs):
        log_type = request.POST.get("type")

        if log_type == "weight":
            form = QuickWeightForm(request.POST)
            if form.is_valid():
                entry = form.save(commit=False)
                entry.user = request.user
                entry.save()
                messages.success(request, "Weight logged!")

        return redirect("dashboard:home")


# =============================================================================
# Fitness Views
# =============================================================================


class FitnessHomeView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Fitness module home - overview of workouts and progress.
    """

    template_name = "health/fitness/home.html"
    help_context_id = "HEALTH_FITNESS"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)
        week_ago = today - timedelta(days=7)

        # Recent workouts
        context["recent_workouts"] = WorkoutSession.objects.filter(
            user=user
        ).select_related("user")[:5]

        # This week's workout count
        context["workouts_this_week"] = WorkoutSession.objects.filter(
            user=user,
            date__gte=week_ago,
        ).count()

        # User's templates
        context["templates"] = WorkoutTemplate.objects.filter(user=user)[:5]

        # Recent PRs
        context["recent_prs"] = PersonalRecord.objects.filter(
            user=user
        ).select_related("exercise")[:5]

        # Exercises for quick add
        context["exercises"] = Exercise.objects.filter(is_active=True)

        return context


class WorkoutListView(LoginRequiredMixin, ListView):
    """
    List all workout sessions.
    """

    model = WorkoutSession
    template_name = "health/fitness/workout_list.html"
    context_object_name = "workouts"
    paginate_by = 20

    def get_queryset(self):
        return WorkoutSession.objects.filter(user=self.request.user)


class WorkoutDetailView(LoginRequiredMixin, TemplateView):
    """
    View a completed workout session.
    """

    template_name = "health/fitness/workout_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        workout = get_object_or_404(
            WorkoutSession.objects.filter(user=self.request.user),
            pk=self.kwargs["pk"],
        )
        context["workout"] = workout
        context["workout_exercises"] = workout.workout_exercises.select_related(
            "exercise"
        ).prefetch_related("sets", "cardio_details")
        return context


class WorkoutCreateView(LoginRequiredMixin, TemplateView):
    """
    Create a new workout session.
    """

    template_name = "health/fitness/workout_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)

        # Pre-populate date with today
        context["date"] = today

        # Get exercises grouped by category
        context["resistance_exercises"] = Exercise.objects.filter(
            category="resistance", is_active=True
        ).order_by("muscle_group", "name")
        context["cardio_exercises"] = Exercise.objects.filter(
            category="cardio", is_active=True
        ).order_by("name")
        context["class_exercises"] = Exercise.objects.filter(
            category="class", is_active=True
        ).order_by("name")

        # User's templates for quick start
        context["templates"] = WorkoutTemplate.objects.filter(user=user)

        # Check if starting from a template
        template_id = self.request.GET.get("template")
        if template_id:
            try:
                import json
                template = WorkoutTemplate.objects.get(pk=template_id, user=user)
                context["from_template"] = template
                # Build template exercise defaults for pre-populating form
                template_defaults = {}
                for te in template.template_exercises.select_related("exercise").prefetch_related("set_defaults"):
                    exercise_id = te.exercise_id
                    template_defaults[exercise_id] = {
                        "default_sets": te.default_sets,
                        "sets": {},
                    }
                    for ds in te.set_defaults.all():
                        template_defaults[exercise_id]["sets"][ds.set_number] = {
                            "weight": float(ds.weight) if ds.weight else None,
                            "reps": ds.reps,
                        }

                # Fallback: if no set_defaults exist, look at the latest workout using this template
                if not any(d["sets"] for d in template_defaults.values()):
                    # Get template exercise IDs
                    template_exercise_ids = list(template_defaults.keys())
                    # Find latest completed workout with these exercises
                    latest_workout = (
                        WorkoutSession.objects.filter(
                            user=user,
                            completed_at__isnull=False,
                            workout_exercises__exercise_id__in=template_exercise_ids,
                        )
                        .order_by("-completed_at")
                        .first()
                    )
                    if latest_workout:
                        for we in latest_workout.workout_exercises.filter(
                            exercise_id__in=template_exercise_ids
                        ):
                            exercise_id = we.exercise_id
                            if exercise_id in template_defaults:
                                for s in we.sets.all():
                                    template_defaults[exercise_id]["sets"][s.set_number] = {
                                        "weight": float(s.weight) if s.weight else None,
                                        "reps": s.reps,
                                    }

                context["template_defaults_json"] = json.dumps(template_defaults)
            except WorkoutTemplate.DoesNotExist:
                pass

        # Check if copying a previous workout
        copy_id = self.request.GET.get("copy")
        if copy_id:
            try:
                copy_from = WorkoutSession.objects.get(pk=copy_id, user=user)
                context["copy_from"] = copy_from
            except WorkoutSession.DoesNotExist:
                pass

        return context

    def post(self, request, *args, **kwargs):
        user = request.user
        today = get_user_today(user)

        # Determine creation source
        source = request.GET.get('source')
        created_via = 'manual'
        if source == 'ai_camera':
            from apps.core.models import UserOwnedModel
            created_via = UserOwnedModel.CREATED_VIA_AI_CAMERA

        # Check if creating from template
        from_template = None
        template_id = request.POST.get("template_id") or request.GET.get("template")
        if template_id:
            try:
                from_template = WorkoutTemplate.objects.get(pk=template_id, user=user)
            except WorkoutTemplate.DoesNotExist:
                pass

        # Create workout session
        workout = WorkoutSession.objects.create(
            user=user,
            date=request.POST.get("date") or today,
            name=request.POST.get("name", ""),
            notes=request.POST.get("notes", ""),
            created_via=created_via,
            from_template=from_template,
        )

        # Process exercises
        exercise_ids = request.POST.getlist("exercise_id")
        for idx, exercise_id in enumerate(exercise_ids):
            try:
                exercise = Exercise.objects.get(pk=exercise_id)
                workout_exercise = WorkoutExercise.objects.create(
                    session=workout,
                    exercise=exercise,
                    order=idx,
                )

                if exercise.category == "resistance":
                    # Process sets for this exercise
                    set_idx = 1
                    while True:
                        weight_key = f"exercise_{exercise_id}_set_{set_idx}_weight"
                        reps_key = f"exercise_{exercise_id}_set_{set_idx}_reps"

                        if weight_key not in request.POST:
                            break

                        weight = request.POST.get(weight_key)
                        reps = request.POST.get(reps_key)

                        if weight or reps:
                            ExerciseSet.objects.create(
                                workout_exercise=workout_exercise,
                                set_number=set_idx,
                                weight=Decimal(weight) if weight else None,
                                reps=int(reps) if reps else None,
                            )
                        set_idx += 1

                elif exercise.category == "cardio":
                    # Process cardio details
                    duration = request.POST.get(f"exercise_{exercise_id}_duration")
                    distance = request.POST.get(f"exercise_{exercise_id}_distance")
                    intensity = request.POST.get(
                        f"exercise_{exercise_id}_intensity", "medium"
                    )

                    CardioDetails.objects.create(
                        workout_exercise=workout_exercise,
                        duration_minutes=int(duration) if duration else None,
                        distance=Decimal(distance) if distance else None,
                        intensity=intensity,
                    )

                elif exercise.category == "class":
                    # Process class details (no sets/reps, just duration + intensity)
                    duration = request.POST.get(f"exercise_{exercise_id}_duration")
                    intensity = request.POST.get(
                        f"exercise_{exercise_id}_intensity", "medium"
                    )

                    ClassDetails.objects.create(
                        workout_exercise=workout_exercise,
                        duration_minutes=int(duration) if duration else None,
                        intensity=intensity,
                    )

            except Exercise.DoesNotExist:
                continue

        messages.success(request, "Workout logged!")
        return redirect("health:workout_detail", pk=workout.pk)


class WorkoutUpdateView(LoginRequiredMixin, TemplateView):
    """
    Edit an existing workout session.
    """

    template_name = "health/fitness/workout_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        workout = get_object_or_404(
            WorkoutSession.objects.filter(user=user),
            pk=self.kwargs["pk"],
        )
        context["workout"] = workout
        context["workout_exercises"] = workout.workout_exercises.select_related(
            "exercise"
        ).prefetch_related("sets", "cardio_details", "class_details")
        context["date"] = workout.date
        context["editing"] = True

        # Get exercises grouped by category
        context["resistance_exercises"] = Exercise.objects.filter(
            category="resistance", is_active=True
        ).order_by("muscle_group", "name")
        context["cardio_exercises"] = Exercise.objects.filter(
            category="cardio", is_active=True
        ).order_by("name")
        context["class_exercises"] = Exercise.objects.filter(
            category="class", is_active=True
        ).order_by("name")

        return context

    def post(self, request, *args, **kwargs):
        user = request.user

        workout = get_object_or_404(
            WorkoutSession.objects.filter(user=user),
            pk=self.kwargs["pk"],
        )

        # Update basic info
        workout.date = request.POST.get("date") or workout.date
        workout.name = request.POST.get("name", "")
        workout.notes = request.POST.get("notes", "")
        workout.save()

        # Clear existing exercises and recreate
        workout.workout_exercises.all().delete()

        # Process exercises (same as create)
        exercise_ids = request.POST.getlist("exercise_id")
        for idx, exercise_id in enumerate(exercise_ids):
            try:
                exercise = Exercise.objects.get(pk=exercise_id)
                workout_exercise = WorkoutExercise.objects.create(
                    session=workout,
                    exercise=exercise,
                    order=idx,
                )

                if exercise.category == "resistance":
                    set_idx = 1
                    while True:
                        weight_key = f"exercise_{exercise_id}_set_{set_idx}_weight"
                        reps_key = f"exercise_{exercise_id}_set_{set_idx}_reps"

                        if weight_key not in request.POST:
                            break

                        weight = request.POST.get(weight_key)
                        reps = request.POST.get(reps_key)

                        if weight or reps:
                            ExerciseSet.objects.create(
                                workout_exercise=workout_exercise,
                                set_number=set_idx,
                                weight=Decimal(weight) if weight else None,
                                reps=int(reps) if reps else None,
                            )
                        set_idx += 1

                elif exercise.category == "cardio":
                    duration = request.POST.get(f"exercise_{exercise_id}_duration")
                    distance = request.POST.get(f"exercise_{exercise_id}_distance")
                    intensity = request.POST.get(
                        f"exercise_{exercise_id}_intensity", "medium"
                    )

                    CardioDetails.objects.create(
                        workout_exercise=workout_exercise,
                        duration_minutes=int(duration) if duration else None,
                        distance=Decimal(distance) if distance else None,
                        intensity=intensity,
                    )

                elif exercise.category == "class":
                    duration = request.POST.get(f"exercise_{exercise_id}_duration")
                    intensity = request.POST.get(
                        f"exercise_{exercise_id}_intensity", "medium"
                    )

                    ClassDetails.objects.create(
                        workout_exercise=workout_exercise,
                        duration_minutes=int(duration) if duration else None,
                        intensity=intensity,
                    )

            except Exercise.DoesNotExist:
                continue

        messages.success(request, "Workout updated!")
        return redirect("health:workout_detail", pk=workout.pk)


class WorkoutDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a workout session.
    Supports undo via toast notification for AJAX requests.
    """

    model = WorkoutSession
    item_type = 'health.workoutsession'
    item_name = 'workout'
    success_url = 'health:fitness_home'

    def get_object(self):
        return get_object_or_404(
            WorkoutSession.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


class WorkoutCopyView(LoginRequiredMixin, View):
    """
    Copy a previous workout as a new session.
    """

    def get(self, request, pk):
        return redirect(f"{reverse_lazy('health:workout_create')}?copy={pk}")


# Workout Templates


class TemplateListView(LoginRequiredMixin, ListView):
    """
    List workout templates.
    """

    model = WorkoutTemplate
    template_name = "health/fitness/template_list.html"
    context_object_name = "templates"

    def get_queryset(self):
        return WorkoutTemplate.objects.filter(user=self.request.user)


class TemplateCreateView(LoginRequiredMixin, TemplateView):
    """
    Create a new workout template.
    """

    template_name = "health/fitness/template_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["resistance_exercises"] = Exercise.objects.filter(
            category="resistance", is_active=True
        ).order_by("muscle_group", "name")
        context["cardio_exercises"] = Exercise.objects.filter(
            category="cardio", is_active=True
        ).order_by("name")

        return context

    def post(self, request, *args, **kwargs):
        user = request.user

        template = WorkoutTemplate.objects.create(
            user=user,
            name=request.POST.get("name", ""),
            description=request.POST.get("description", ""),
        )

        # Process exercises
        exercise_ids = request.POST.getlist("exercise_id")
        for idx, exercise_id in enumerate(exercise_ids):
            try:
                exercise = Exercise.objects.get(pk=exercise_id)
                default_sets = request.POST.get(
                    f"exercise_{exercise_id}_default_sets", 3
                )
                default_sets = int(default_sets) if default_sets else 3

                template_exercise = TemplateExercise.objects.create(
                    template=template,
                    exercise=exercise,
                    order=idx,
                    default_sets=default_sets,
                )

                # Save set defaults (weight/reps per set)
                for set_num in range(1, default_sets + 1):
                    weight = request.POST.get(
                        f"exercise_{exercise_id}_set_{set_num}_weight"
                    )
                    reps = request.POST.get(
                        f"exercise_{exercise_id}_set_{set_num}_reps"
                    )
                    # Only create if at least one value is provided
                    if weight or reps:
                        from decimal import Decimal, InvalidOperation
                        try:
                            weight_val = Decimal(weight) if weight else None
                        except (InvalidOperation, TypeError):
                            weight_val = None
                        try:
                            reps_val = int(reps) if reps else None
                        except (ValueError, TypeError):
                            reps_val = None

                        if weight_val is not None or reps_val is not None:
                            TemplateExerciseSet.objects.create(
                                template_exercise=template_exercise,
                                set_number=set_num,
                                weight=weight_val,
                                reps=reps_val,
                            )
            except Exercise.DoesNotExist:
                continue

        messages.success(request, f"Template '{template.name}' created!")
        return redirect("health:template_list")


class TemplateDetailView(LoginRequiredMixin, TemplateView):
    """
    View a workout template.
    """

    template_name = "health/fitness/template_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        template = get_object_or_404(
            WorkoutTemplate.objects.filter(user=self.request.user),
            pk=self.kwargs["pk"],
        )
        context["template"] = template
        context["template_exercises"] = template.template_exercises.select_related(
            "exercise"
        ).prefetch_related("set_defaults")
        return context


class TemplateUpdateView(LoginRequiredMixin, TemplateView):
    """
    Edit a workout template.
    """

    template_name = "health/fitness/template_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        template = get_object_or_404(
            WorkoutTemplate.objects.filter(user=self.request.user),
            pk=self.kwargs["pk"],
        )
        context["template"] = template
        context["template_exercises"] = template.template_exercises.select_related(
            "exercise"
        ).prefetch_related("set_defaults")
        context["editing"] = True

        context["resistance_exercises"] = Exercise.objects.filter(
            category="resistance", is_active=True
        ).order_by("muscle_group", "name")
        context["cardio_exercises"] = Exercise.objects.filter(
            category="cardio", is_active=True
        ).order_by("name")

        return context

    def post(self, request, *args, **kwargs):
        user = request.user

        template = get_object_or_404(
            WorkoutTemplate.objects.filter(user=user),
            pk=self.kwargs["pk"],
        )

        template.name = request.POST.get("name", "")
        template.description = request.POST.get("description", "")
        template.save()

        # Clear and recreate exercises (this also cascades to delete set_defaults)
        template.template_exercises.all().delete()

        exercise_ids = request.POST.getlist("exercise_id")
        for idx, exercise_id in enumerate(exercise_ids):
            try:
                exercise = Exercise.objects.get(pk=exercise_id)
                default_sets = request.POST.get(
                    f"exercise_{exercise_id}_default_sets", 3
                )
                default_sets = int(default_sets) if default_sets else 3

                template_exercise = TemplateExercise.objects.create(
                    template=template,
                    exercise=exercise,
                    order=idx,
                    default_sets=default_sets,
                )

                # Save set defaults (weight/reps per set)
                for set_num in range(1, default_sets + 1):
                    weight = request.POST.get(
                        f"exercise_{exercise_id}_set_{set_num}_weight"
                    )
                    reps = request.POST.get(
                        f"exercise_{exercise_id}_set_{set_num}_reps"
                    )
                    # Only create if at least one value is provided
                    if weight or reps:
                        from decimal import Decimal, InvalidOperation
                        try:
                            weight_val = Decimal(weight) if weight else None
                        except (InvalidOperation, TypeError):
                            weight_val = None
                        try:
                            reps_val = int(reps) if reps else None
                        except (ValueError, TypeError):
                            reps_val = None

                        if weight_val is not None or reps_val is not None:
                            TemplateExerciseSet.objects.create(
                                template_exercise=template_exercise,
                                set_number=set_num,
                                weight=weight_val,
                                reps=reps_val,
                            )
            except Exercise.DoesNotExist:
                continue

        messages.success(request, f"Template '{template.name}' updated!")
        return redirect("health:template_detail", pk=template.pk)


class TemplateDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a workout template.
    Supports undo via toast notification for AJAX requests.
    """

    model = WorkoutTemplate
    item_type = 'health.workouttemplate'
    item_name = 'template'
    success_url = 'health:template_list'

    def get_object(self):
        return get_object_or_404(
            WorkoutTemplate.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


class UseTemplateView(LoginRequiredMixin, View):
    """
    Start a new workout from a template.
    """

    def get(self, request, pk):
        return redirect(f"{reverse_lazy('health:workout_create')}?template={pk}")


# Personal Records


class PersonalRecordsView(LoginRequiredMixin, TemplateView):
    """
    View personal records.
    """

    template_name = "health/fitness/personal_records.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Get PRs grouped by exercise
        prs = PersonalRecord.objects.filter(user=user).select_related("exercise")

        # Group by exercise
        pr_by_exercise = {}
        for pr in prs:
            if pr.exercise.name not in pr_by_exercise:
                pr_by_exercise[pr.exercise.name] = pr
            elif pr.estimated_1rm > pr_by_exercise[pr.exercise.name].estimated_1rm:
                pr_by_exercise[pr.exercise.name] = pr

        context["prs"] = sorted(
            pr_by_exercise.values(), key=lambda x: x.exercise.name
        )
        return context


# Progress Tracking


class ProgressView(LoginRequiredMixin, TemplateView):
    """
    View workout progress and statistics.
    """

    template_name = "health/fitness/progress.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)

        # Workout frequency
        last_30_days = today - timedelta(days=30)
        context["workouts_30d"] = WorkoutSession.objects.filter(
            user=user,
            date__gte=last_30_days,
        ).count()

        # Total volume last 30 days
        workouts = WorkoutSession.objects.filter(
            user=user,
            date__gte=last_30_days,
        )
        total_volume = sum(w.total_volume for w in workouts)
        context["total_volume_30d"] = round(total_volume)

        # Get unique exercises the user has done
        exercise_ids = (
            WorkoutExercise.objects.filter(session__user=user)
            .values_list("exercise_id", flat=True)
            .distinct()
        )
        context["exercises_done"] = Exercise.objects.filter(
            pk__in=exercise_ids, category="resistance"
        ).order_by("name")

        # Selected exercise progress
        exercise_id = self.request.GET.get("exercise")
        if exercise_id:
            try:
                exercise = Exercise.objects.get(pk=exercise_id)
                context["selected_exercise"] = exercise

                # Get all sets for this exercise
                workout_exercises = WorkoutExercise.objects.filter(
                    session__user=user,
                    exercise=exercise,
                ).select_related("session")

                progress_data = []
                for we in workout_exercises:
                    for s in we.sets.all():
                        if s.weight and s.reps:
                            progress_data.append(
                                {
                                    "date": we.session.date.isoformat(),
                                    "weight": float(s.weight),
                                    "reps": s.reps,
                                    "volume": s.volume,
                                }
                            )

                context["progress_data"] = progress_data

            except Exercise.DoesNotExist:
                pass

        return context


# HTMX Endpoints


def exercise_list_json(request):
    """
    Return exercises as JSON for autocomplete.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"exercises": []})

    category = request.GET.get("category", "")
    exercises = Exercise.objects.filter(is_active=True)

    if category:
        exercises = exercises.filter(category=category)

    data = [
        {
            "id": e.id,
            "name": e.name,
            "category": e.category,
            "muscle_group": e.muscle_group,
        }
        for e in exercises
    ]

    return JsonResponse({"exercises": data})


def add_exercise_htmx(request, workout_pk=None):
    """
    HTMX endpoint to add an exercise row to workout form.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    exercise_id = request.POST.get("exercise_id")
    if not exercise_id:
        return JsonResponse({"error": "No exercise selected"}, status=400)

    try:
        exercise = Exercise.objects.get(pk=exercise_id)
    except Exercise.DoesNotExist:
        return JsonResponse({"error": "Exercise not found"}, status=404)

    html = render_to_string(
        "health/fitness/partials/exercise_row.html",
        {"exercise": exercise, "set_count": 3},
        request=request,
    )

    return JsonResponse({"html": html})


def add_set_htmx(request, exercise_id):
    """
    HTMX endpoint to add a set row to an exercise.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    set_number = int(request.POST.get("set_number", 1))

    html = render_to_string(
        "health/fitness/partials/set_row.html",
        {"exercise_id": exercise_id, "set_number": set_number},
        request=request,
    )

    return JsonResponse({"html": html})


# =============================================================================
# Live Workout AJAX Endpoints
# =============================================================================


def start_workout_ajax(request):
    """
    Create a new in-progress workout session.
    Returns the workout ID for subsequent set saves.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    import json
    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        data = {}

    user = request.user
    today = get_user_today(user)

    # Check for existing in-progress workout today
    existing = WorkoutSession.objects.filter(
        user=user,
        date=today,
        completed_at__isnull=True,
        started_at__isnull=False,
    ).first()

    if existing:
        return JsonResponse({
            "workout_id": existing.pk,
            "message": "Resumed existing workout",
            "is_resumed": True,
        })

    # Create new workout session
    template_id = data.get("template_id")
    template_name = ""
    from_template = None
    if template_id:
        try:
            from_template = WorkoutTemplate.objects.get(pk=template_id, user=user)
            template_name = from_template.name
        except WorkoutTemplate.DoesNotExist:
            pass

    workout = WorkoutSession.objects.create(
        user=user,
        date=data.get("date") or today,
        name=data.get("name") or template_name,
        started_at=timezone.now(),
        from_template=from_template,
    )

    return JsonResponse({
        "workout_id": workout.pk,
        "message": "Workout started",
        "is_resumed": False,
    })


def save_set_ajax(request):
    """
    Save a single set for an exercise in an in-progress workout.
    Creates the WorkoutExercise if it doesn't exist.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    user = request.user
    workout_id = data.get("workout_id")
    exercise_id = data.get("exercise_id")
    set_number = data.get("set_number")
    weight = data.get("weight")
    reps = data.get("reps")

    if not all([workout_id, exercise_id, set_number]):
        return JsonResponse({"error": "Missing required fields"}, status=400)

    # Validate workout belongs to user
    try:
        workout = WorkoutSession.objects.get(pk=workout_id, user=user)
    except WorkoutSession.DoesNotExist:
        return JsonResponse({"error": "Workout not found"}, status=404)

    # Get or create the WorkoutExercise
    try:
        exercise = Exercise.objects.get(pk=exercise_id)
    except Exercise.DoesNotExist:
        return JsonResponse({"error": "Exercise not found"}, status=404)

    workout_exercise, created = WorkoutExercise.objects.get_or_create(
        session=workout,
        exercise=exercise,
        defaults={"order": workout.workout_exercises.count()},
    )

    # Create or update the set
    exercise_set, set_created = ExerciseSet.objects.update_or_create(
        workout_exercise=workout_exercise,
        set_number=set_number,
        defaults={
            "weight": Decimal(str(weight)) if weight else None,
            "reps": int(reps) if reps else None,
        },
    )

    return JsonResponse({
        "success": True,
        "set_id": exercise_set.pk,
        "workout_exercise_id": workout_exercise.pk,
        "created": set_created,
        "message": f"Set {set_number} saved",
    })


def save_cardio_ajax(request):
    """
    Save cardio details for an exercise in an in-progress workout.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    user = request.user
    workout_id = data.get("workout_id")
    exercise_id = data.get("exercise_id")
    duration = data.get("duration")
    distance = data.get("distance")
    intensity = data.get("intensity", "medium")

    if not all([workout_id, exercise_id]):
        return JsonResponse({"error": "Missing required fields"}, status=400)

    # Validate workout belongs to user
    try:
        workout = WorkoutSession.objects.get(pk=workout_id, user=user)
    except WorkoutSession.DoesNotExist:
        return JsonResponse({"error": "Workout not found"}, status=404)

    # Get or create the WorkoutExercise
    try:
        exercise = Exercise.objects.get(pk=exercise_id)
    except Exercise.DoesNotExist:
        return JsonResponse({"error": "Exercise not found"}, status=404)

    workout_exercise, _ = WorkoutExercise.objects.get_or_create(
        session=workout,
        exercise=exercise,
        defaults={"order": workout.workout_exercises.count()},
    )

    # Create or update cardio details
    cardio, created = CardioDetails.objects.update_or_create(
        workout_exercise=workout_exercise,
        defaults={
            "duration_minutes": int(duration) if duration else None,
            "distance": Decimal(str(distance)) if distance else None,
            "intensity": intensity,
        },
    )

    return JsonResponse({
        "success": True,
        "cardio_id": cardio.pk,
        "workout_exercise_id": workout_exercise.pk,
        "message": "Cardio saved",
    })


def save_class_ajax(request):
    """
    Save class details for a fitness class exercise in an in-progress workout.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    user = request.user
    workout_id = data.get("workout_id")
    exercise_id = data.get("exercise_id")
    duration = data.get("duration")
    intensity = data.get("intensity", "medium")

    if not all([workout_id, exercise_id]):
        return JsonResponse({"error": "Missing required fields"}, status=400)

    # Validate workout belongs to user
    try:
        workout = WorkoutSession.objects.get(pk=workout_id, user=user)
    except WorkoutSession.DoesNotExist:
        return JsonResponse({"error": "Workout not found"}, status=404)

    # Get or create the WorkoutExercise
    try:
        exercise = Exercise.objects.get(pk=exercise_id)
    except Exercise.DoesNotExist:
        return JsonResponse({"error": "Exercise not found"}, status=404)

    workout_exercise, _ = WorkoutExercise.objects.get_or_create(
        session=workout,
        exercise=exercise,
        defaults={"order": workout.workout_exercises.count()},
    )

    # Create or update class details
    class_details, created = ClassDetails.objects.update_or_create(
        workout_exercise=workout_exercise,
        defaults={
            "duration_minutes": int(duration) if duration else None,
            "intensity": intensity,
        },
    )

    return JsonResponse({
        "success": True,
        "class_id": class_details.pk,
        "workout_exercise_id": workout_exercise.pk,
        "message": "Class saved",
    })


def complete_workout_ajax(request):
    """
    Mark a workout as completed.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    user = request.user
    workout_id = data.get("workout_id")
    notes = data.get("notes", "")
    name = data.get("name", "")

    if not workout_id:
        return JsonResponse({"error": "workout_id required"}, status=400)

    try:
        workout = WorkoutSession.objects.get(pk=workout_id, user=user)
    except WorkoutSession.DoesNotExist:
        return JsonResponse({"error": "Workout not found"}, status=404)

    workout.completed_at = timezone.now()
    if notes:
        workout.notes = notes
    if name:
        workout.name = name

    # Calculate duration if started_at exists
    if workout.started_at:
        duration = workout.completed_at - workout.started_at
        workout.duration_minutes = int(duration.total_seconds() / 60)

    workout.save()

    # Sync workout data back to template if this workout was created from one
    if workout.from_template:
        _sync_workout_to_template(workout)

    return JsonResponse({
        "success": True,
        "message": "Workout completed!",
        "redirect_url": f"/health/fitness/workout/{workout.pk}/",
    })


def _sync_workout_to_template(workout):
    """
    Sync completed workout exercise data back to the template.

    Updates the template's default sets with the actual weights/reps used.
    """
    template = workout.from_template

    for workout_exercise in workout.workout_exercises.select_related("exercise"):
        # Find matching template exercise
        try:
            template_exercise = TemplateExercise.objects.get(
                template=template,
                exercise=workout_exercise.exercise,
            )
        except TemplateExercise.DoesNotExist:
            continue

        # Update template exercise default sets with actual workout data
        for exercise_set in workout_exercise.sets.all():
            TemplateExerciseSet.objects.update_or_create(
                template_exercise=template_exercise,
                set_number=exercise_set.set_number,
                defaults={
                    "weight": exercise_set.weight,
                    "reps": exercise_set.reps,
                },
            )

        # Update the default_sets count if more sets were performed
        max_set = workout_exercise.sets.count()
        if max_set > template_exercise.default_sets:
            template_exercise.default_sets = max_set
            template_exercise.save(update_fields=["default_sets"])


def get_workout_state_ajax(request, workout_id):
    """
    Get current state of a workout (for resuming).
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    user = request.user

    try:
        workout = WorkoutSession.objects.get(pk=workout_id, user=user)
    except WorkoutSession.DoesNotExist:
        return JsonResponse({"error": "Workout not found"}, status=404)

    exercises_data = []
    for we in workout.workout_exercises.select_related("exercise").prefetch_related("sets"):
        exercise_info = {
            "exercise_id": we.exercise.pk,
            "exercise_name": we.exercise.name,
            "category": we.exercise.category,
            "sets": [],
        }
        for s in we.sets.all():
            exercise_info["sets"].append({
                "set_number": s.set_number,
                "weight": float(s.weight) if s.weight else None,
                "reps": s.reps,
            })
        if hasattr(we, "cardio_details") and we.cardio_details:
            exercise_info["cardio"] = {
                "duration": we.cardio_details.duration_minutes,
                "distance": float(we.cardio_details.distance) if we.cardio_details.distance else None,
                "intensity": we.cardio_details.intensity,
            }
        exercises_data.append(exercise_info)

    return JsonResponse({
        "workout_id": workout.pk,
        "name": workout.name,
        "date": str(workout.date),
        "started_at": workout.started_at.isoformat() if workout.started_at else None,
        "exercises": exercises_data,
    })


# =============================================================================
# Medicine Views
# =============================================================================


class MedicineHomeView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Medicine module home - daily tracker and overview.
    """

    template_name = "health/medicine/home.html"
    help_context_id = "HEALTH_MEDICINE_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)
        now = timezone.now()

        # Get active medicines
        active_medicines = Medicine.objects.filter(
            user=user,
            medicine_status=Medicine.STATUS_ACTIVE,
        )
        context["active_medicines"] = active_medicines
        context["active_count"] = active_medicines.count()

        # Get today's scheduled doses
        today_schedules = []
        for medicine in active_medicines.filter(is_prn=False):
            for schedule in medicine.schedules.filter(is_active=True):
                if schedule.applies_to_day(today.weekday()):
                    # Check if there's already a log for this dose today
                    log = MedicineLog.objects.filter(
                        medicine=medicine,
                        schedule=schedule,
                        scheduled_date=today,
                    ).first()

                    today_schedules.append({
                        "medicine": medicine,
                        "schedule": schedule,
                        "log": log,
                        "is_taken": log and log.log_status in [
                            MedicineLog.STATUS_TAKEN,
                            MedicineLog.STATUS_LATE,
                        ],
                        "is_overdue": self._is_overdue(schedule, log, now, today, medicine),
                    })

        # Sort by time_of_day order, then by scheduled_time
        today_schedules.sort(key=lambda x: (
            x["schedule"].time_of_day_order,
            x["schedule"].scheduled_time
        ))
        context["today_schedules"] = today_schedules

        # Group schedules by time_of_day for bulk actions
        from collections import OrderedDict
        grouped_schedules = OrderedDict()
        for item in today_schedules:
            tod = item["schedule"].time_of_day or "unassigned"
            tod_display = item["schedule"].time_of_day_display or "Other"
            if tod not in grouped_schedules:
                grouped_schedules[tod] = {
                    "time_of_day": tod,
                    "display_name": tod_display,
                    "schedules": [],
                    "all_taken": True,
                    "all_skipped": True,
                    "has_pending": False,
                }
            grouped_schedules[tod]["schedules"].append(item)
            # Track group status
            if not item["is_taken"]:
                grouped_schedules[tod]["all_taken"] = False
            if not (item["log"] and item["log"].log_status == "skipped"):
                grouped_schedules[tod]["all_skipped"] = False
            if not item["is_taken"] and not (item["log"] and item["log"].log_status == "skipped"):
                grouped_schedules[tod]["has_pending"] = True

        context["grouped_schedules"] = list(grouped_schedules.values())

        # Calculate today's stats
        total_scheduled = len(today_schedules)
        taken_count = sum(1 for s in today_schedules if s["is_taken"])
        context["total_scheduled_today"] = total_scheduled
        context["taken_today"] = taken_count
        context["pending_today"] = total_scheduled - taken_count

        # Check for overdue
        overdue = [s for s in today_schedules if s["is_overdue"]]
        context["overdue_doses"] = overdue
        context["has_overdue"] = len(overdue) > 0

        # Check for low supply medicines (needs refill but not yet requested)
        low_supply = [m for m in active_medicines if m.needs_refill]
        context["low_supply_medicines"] = low_supply
        context["has_low_supply"] = len(low_supply) > 0

        # Check for medicines with refill already requested
        refill_requested = [m for m in active_medicines if m.refill_requested]
        context["refill_requested_medicines"] = refill_requested
        context["has_refill_requested"] = len(refill_requested) > 0

        # PRN medicines taken today
        prn_today = MedicineLog.objects.filter(
            user=user,
            scheduled_date=today,
            is_prn_dose=True,
            log_status__in=[MedicineLog.STATUS_TAKEN, MedicineLog.STATUS_LATE],
        ).select_related("medicine")
        context["prn_doses_today"] = prn_today

        return context

    def _is_overdue(self, schedule, log, now, today, medicine):
        """Check if a scheduled dose is overdue."""
        if log and log.log_status in [
            MedicineLog.STATUS_TAKEN,
            MedicineLog.STATUS_LATE,
            MedicineLog.STATUS_SKIPPED,
        ]:
            return False

        from datetime import datetime, timedelta
        import pytz

        # Get user's timezone (use timezone_iana for legacy format support)
        user = self.request.user
        try:
            user_tz = pytz.timezone(user.preferences.timezone_iana)
        except (AttributeError, pytz.UnknownTimeZoneError):
            user_tz = pytz.UTC

        # Convert current time to user's local time
        now_local = now.astimezone(user_tz)

        # Create local datetime for the scheduled time
        scheduled_dt = datetime.combine(today, schedule.scheduled_time)
        grace_minutes = medicine.grace_period_minutes
        deadline = scheduled_dt + timedelta(minutes=grace_minutes)

        # Compare local times (both naive, both in user's local time)
        now_local_naive = now_local.replace(tzinfo=None)
        return now_local_naive > deadline


class MedicineListView(LoginRequiredMixin, ListView):
    """
    List all medicines.
    """

    model = Medicine
    template_name = "health/medicine/medicine_list.html"
    context_object_name = "medicines"
    paginate_by = 20

    def get_queryset(self):
        queryset = Medicine.objects.filter(user=self.request.user)

        # Filter by status if specified
        status = self.request.GET.get("status", "active")
        if status == "active":
            queryset = queryset.filter(medicine_status=Medicine.STATUS_ACTIVE)
        elif status == "paused":
            queryset = queryset.filter(medicine_status=Medicine.STATUS_PAUSED)
        elif status == "completed":
            queryset = queryset.filter(medicine_status=Medicine.STATUS_COMPLETED)
        # "all" shows everything

        return queryset.prefetch_related("schedules")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_status"] = self.request.GET.get("status", "active")

        # Counts for each status
        all_medicines = Medicine.objects.filter(user=self.request.user)
        context["active_count"] = all_medicines.filter(
            medicine_status=Medicine.STATUS_ACTIVE
        ).count()
        context["paused_count"] = all_medicines.filter(
            medicine_status=Medicine.STATUS_PAUSED
        ).count()
        context["completed_count"] = all_medicines.filter(
            medicine_status=Medicine.STATUS_COMPLETED
        ).count()

        return context


class MedicineDetailView(LoginRequiredMixin, TemplateView):
    """
    View medicine details and history.
    """

    template_name = "health/medicine/medicine_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        medicine = get_object_or_404(
            Medicine.objects.filter(user=self.request.user),
            pk=self.kwargs["pk"],
        )
        context["medicine"] = medicine
        context["schedules"] = medicine.schedules.all()

        # Recent logs
        context["recent_logs"] = MedicineLog.objects.filter(
            medicine=medicine
        ).order_by("-scheduled_date", "-scheduled_time")[:30]

        # Adherence stats for last 7 days
        today = get_user_today(self.request.user)
        week_ago = today - timedelta(days=7)
        week_logs = MedicineLog.objects.filter(
            medicine=medicine,
            scheduled_date__gte=week_ago,
            scheduled_date__lte=today,
        )
        taken = week_logs.filter(
            log_status__in=[MedicineLog.STATUS_TAKEN, MedicineLog.STATUS_LATE]
        ).count()
        total = week_logs.count()
        context["week_taken"] = taken
        context["week_total"] = total
        context["week_adherence"] = round(taken / total * 100) if total > 0 else 0

        return context


class MedicineCreateView(LoginRequiredMixin, CreateView):
    """
    Add a new medicine.
    """

    model = Medicine
    form_class = MedicineForm
    template_name = "health/medicine/medicine_form.html"

    def get_initial(self):
        """Pre-populate form from query parameters (for AI Camera scan and barcode scan)."""
        initial = super().get_initial()
        # Support prefill from Camera Scan and Barcode Scan features
        if self.request.GET.get('name'):
            initial['name'] = self.request.GET.get('name')
        if self.request.GET.get('dose'):
            initial['dose'] = self.request.GET.get('dose')
        if self.request.GET.get('purpose'):
            initial['purpose'] = self.request.GET.get('purpose')
        if self.request.GET.get('directions'):
            # Directions can go into notes or be displayed separately
            initial['notes'] = self.request.GET.get('directions')
        if self.request.GET.get('notes'):
            # Also support notes directly from barcode scan
            existing_notes = initial.get('notes', '')
            new_notes = self.request.GET.get('notes')
            if existing_notes:
                initial['notes'] = f"{existing_notes}\n{new_notes}"
            else:
                initial['notes'] = new_notes
        if self.request.GET.get('quantity'):
            # Try to extract supply count from quantity like "30 tablets"
            quantity = self.request.GET.get('quantity', '')
            if quantity:
                import re
                match = re.match(r'^(\d+)', quantity)
                if match:
                    initial['current_supply'] = int(match.group(1))
        return initial

    def get_context_data(self, **kwargs):
        """Add barcode scan context to template."""
        context = super().get_context_data(**kwargs)
        # Check if user has AI consent for barcode scanning
        has_ai_consent = (
            hasattr(self.request.user, 'preferences') and
            self.request.user.preferences.ai_enabled and
            self.request.user.preferences.ai_data_consent
        )
        context['has_ai_consent'] = has_ai_consent
        context['barcode_from_scan'] = self.request.GET.get('barcode', '')
        context['source'] = self.request.GET.get('source', '')
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user

        # Track if created via AI Camera scan or barcode scan
        source = self.request.GET.get('source')
        if source == 'ai_camera':
            from apps.core.models import UserOwnedModel
            form.instance.created_via = UserOwnedModel.CREATED_VIA_AI_CAMERA
        elif source == 'barcode_scan':
            from apps.core.models import UserOwnedModel
            form.instance.created_via = UserOwnedModel.CREATED_VIA_AI_CAMERA  # Reuse same constant

        messages.success(self.request, f"Added {form.instance.name} to your medicines.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("health:medicine_schedules", kwargs={"pk": self.object.pk})


class MedicineUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edit a medicine.
    """

    model = Medicine
    form_class = MedicineForm
    template_name = "health/medicine/medicine_form.html"

    def get_queryset(self):
        return Medicine.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"Updated {form.instance.name}.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("health:medicine_detail", kwargs={"pk": self.object.pk})


class MedicineDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a medicine.
    Supports undo via toast notification for AJAX requests.
    """

    model = Medicine
    item_type = 'health.medicine'
    item_name = 'medicine'
    success_url = 'health:medicine_list'

    def get_object(self):
        return get_object_or_404(
            Medicine.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


class MedicinePauseView(LoginRequiredMixin, View):
    """
    Pause a medicine temporarily.
    """

    def post(self, request, pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk,
        )
        reason = request.POST.get("reason", "")
        medicine.pause(reason)
        messages.success(
            request,
            f"Paused {medicine.name}. You can resume it anytime."
        )
        return redirect("health:medicine_detail", pk=pk)


class MedicineResumeView(LoginRequiredMixin, View):
    """
    Resume a paused medicine.
    """

    def post(self, request, pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk,
        )
        medicine.resume()
        messages.success(request, f"Resumed {medicine.name}.")
        return redirect("health:medicine_detail", pk=pk)


class MedicineCompleteView(LoginRequiredMixin, View):
    """
    Mark a medicine course as completed.
    """

    def post(self, request, pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk,
        )
        medicine.complete()
        messages.success(
            request,
            f"Marked {medicine.name} as completed. Great job!"
        )
        return redirect("health:medicine_list")


class MedicineSchedulesView(LoginRequiredMixin, TemplateView):
    """
    Manage schedules for a medicine.
    """

    template_name = "health/medicine/medicine_schedules.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        medicine = get_object_or_404(
            Medicine.objects.filter(user=self.request.user),
            pk=self.kwargs["pk"],
        )
        context["medicine"] = medicine
        context["schedules"] = medicine.schedules.all()
        context["form"] = MedicineScheduleForm()
        return context

    def post(self, request, pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk,
        )
        form = MedicineScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.medicine = medicine
            schedule.save()
            messages.success(request, "Added schedule.")
        else:
            messages.error(request, "Please fix the errors below.")
        return redirect("health:medicine_schedules", pk=pk)


class MedicineScheduleDeleteView(LoginRequiredMixin, View):
    """
    Delete a medicine schedule.
    """

    def post(self, request, medicine_pk, schedule_pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=medicine_pk,
        )
        schedule = get_object_or_404(
            medicine.schedules.all(),
            pk=schedule_pk,
        )
        schedule.delete()
        messages.success(request, "Removed schedule.")
        return redirect("health:medicine_schedules", pk=medicine_pk)


class MedicineScheduleActivateView(LoginRequiredMixin, View):
    """
    Activate an inactive schedule.
    """

    def post(self, request, medicine_pk, schedule_pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=medicine_pk,
        )
        schedule = get_object_or_404(
            medicine.schedules.all(),
            pk=schedule_pk,
        )
        schedule.is_active = True
        schedule.save()
        messages.success(request, "Schedule activated.")
        return redirect("health:medicine_schedules", pk=medicine_pk)


class MedicineTakeView(LoginRequiredMixin, View):
    """
    Mark a scheduled dose as taken.
    """

    def post(self, request, pk, schedule_pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk,
        )
        schedule = get_object_or_404(
            medicine.schedules.all(),
            pk=schedule_pk,
        )
        today = get_user_today(request.user)

        # Get or create the log entry
        log, created = MedicineLog.objects.get_or_create(
            user=request.user,
            medicine=medicine,
            schedule=schedule,
            scheduled_date=today,
            defaults={
                "scheduled_time": schedule.scheduled_time,
                "is_prn_dose": False,
            }
        )

        # Determine taken_at time
        taken_at = None
        if request.POST.get("taken_at_scheduled"):
            # User clicked "Taken at [scheduled time]" - use the scheduled time
            from datetime import datetime
            import pytz

            user_tz = pytz.timezone(request.user.preferences.timezone_iana)
            scheduled_dt = datetime.combine(today, schedule.scheduled_time)
            taken_at = user_tz.localize(scheduled_dt)

        # Mark as taken (with scheduled time or current time)
        log.mark_taken(taken_at=taken_at)

        # Decrease supply if tracked
        if medicine.current_supply is not None and medicine.current_supply > 0:
            medicine.current_supply -= 1
            medicine.save(update_fields=["current_supply", "updated_at"])

        messages.success(request, f"Marked {medicine.name} as taken.")

        # Return to referring page or home
        next_url = request.POST.get("next", reverse_lazy("health:medicine_home"))
        return redirect(next_url)


class MedicineSkipView(LoginRequiredMixin, View):
    """
    Mark a scheduled dose as skipped.
    """

    def post(self, request, pk, schedule_pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk,
        )
        schedule = get_object_or_404(
            medicine.schedules.all(),
            pk=schedule_pk,
        )
        today = get_user_today(request.user)
        reason = request.POST.get("reason", "")

        # Get or create the log entry
        log, created = MedicineLog.objects.get_or_create(
            user=request.user,
            medicine=medicine,
            schedule=schedule,
            scheduled_date=today,
            defaults={
                "scheduled_time": schedule.scheduled_time,
                "is_prn_dose": False,
            }
        )

        # Mark as skipped
        log.mark_skipped(reason)

        messages.info(request, f"Skipped {medicine.name} for today.")
        next_url = request.POST.get("next", reverse_lazy("health:medicine_home"))
        return redirect(next_url)


class MedicineUndoView(LoginRequiredMixin, View):
    """
    Undo a taken/skipped dose (set back to pending).
    """

    def post(self, request, pk, schedule_pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk,
        )
        schedule = get_object_or_404(
            medicine.schedules.all(),
            pk=schedule_pk,
        )
        today = get_user_today(request.user)

        log = get_object_or_404(
            MedicineLog.objects.filter(
                medicine=medicine,
                schedule=schedule,
                scheduled_date=today,
            )
        )

        # If it was taken, restore supply
        if log.log_status in [MedicineLog.STATUS_TAKEN, MedicineLog.STATUS_LATE]:
            if medicine.current_supply is not None:
                medicine.current_supply += 1
                medicine.save(update_fields=["current_supply", "updated_at"])

        # Delete the log entry to reset
        log.delete()

        messages.info(request, f"Undid {medicine.name} for today.")
        next_url = request.POST.get("next", reverse_lazy("health:medicine_home"))
        return redirect(next_url)


class MedicineBulkTakeView(LoginRequiredMixin, View):
    """
    Mark all pending doses in a time_of_day group as taken.
    """

    def post(self, request, time_of_day):
        from datetime import datetime
        import pytz

        user = request.user
        today = get_user_today(user)

        # Get all active medicines with schedules in this time_of_day
        active_medicines = Medicine.objects.filter(
            user=user,
            medicine_status=Medicine.STATUS_ACTIVE,
            is_prn=False,
        )

        taken_count = 0
        taken_at = None

        # Check if user wants to use scheduled time or current time
        use_scheduled_time = request.POST.get("taken_at_scheduled") == "1"

        for medicine in active_medicines:
            for schedule in medicine.schedules.filter(
                is_active=True,
                time_of_day=time_of_day,
            ):
                if not schedule.applies_to_day(today.weekday()):
                    continue

                # Check if already logged
                existing_log = MedicineLog.objects.filter(
                    medicine=medicine,
                    schedule=schedule,
                    scheduled_date=today,
                ).first()

                if existing_log and existing_log.log_status in [
                    MedicineLog.STATUS_TAKEN,
                    MedicineLog.STATUS_LATE,
                    MedicineLog.STATUS_SKIPPED,
                ]:
                    continue  # Already handled

                # Create or update log
                log, created = MedicineLog.objects.get_or_create(
                    user=user,
                    medicine=medicine,
                    schedule=schedule,
                    scheduled_date=today,
                    defaults={
                        "scheduled_time": schedule.scheduled_time,
                        "is_prn_dose": False,
                    }
                )

                # Determine taken_at time
                if use_scheduled_time:
                    user_tz = pytz.timezone(user.preferences.timezone_iana)
                    scheduled_dt = datetime.combine(today, schedule.scheduled_time)
                    taken_at = user_tz.localize(scheduled_dt)
                else:
                    taken_at = None  # mark_taken will use current time

                log.mark_taken(taken_at=taken_at)
                taken_count += 1

                # Decrease supply if tracked
                if medicine.current_supply is not None and medicine.current_supply > 0:
                    medicine.current_supply -= 1
                    medicine.save(update_fields=["current_supply", "updated_at"])

        time_display = dict(MedicineSchedule.TIME_OF_DAY_CHOICES).get(time_of_day, time_of_day)
        messages.success(request, f"Marked {taken_count} {time_display} dose{'s' if taken_count != 1 else ''} as taken.")

        next_url = request.POST.get("next", reverse_lazy("health:medicine_home"))
        return redirect(next_url)


class MedicineBulkSkipView(LoginRequiredMixin, View):
    """
    Mark all pending doses in a time_of_day group as skipped.
    """

    def post(self, request, time_of_day):
        user = request.user
        today = get_user_today(user)

        # Get all active medicines with schedules in this time_of_day
        active_medicines = Medicine.objects.filter(
            user=user,
            medicine_status=Medicine.STATUS_ACTIVE,
            is_prn=False,
        )

        skipped_count = 0
        reason = request.POST.get("reason", "")

        for medicine in active_medicines:
            for schedule in medicine.schedules.filter(
                is_active=True,
                time_of_day=time_of_day,
            ):
                if not schedule.applies_to_day(today.weekday()):
                    continue

                # Check if already logged
                existing_log = MedicineLog.objects.filter(
                    medicine=medicine,
                    schedule=schedule,
                    scheduled_date=today,
                ).first()

                if existing_log and existing_log.log_status in [
                    MedicineLog.STATUS_TAKEN,
                    MedicineLog.STATUS_LATE,
                    MedicineLog.STATUS_SKIPPED,
                ]:
                    continue  # Already handled

                # Create or update log
                log, created = MedicineLog.objects.get_or_create(
                    user=user,
                    medicine=medicine,
                    schedule=schedule,
                    scheduled_date=today,
                    defaults={
                        "scheduled_time": schedule.scheduled_time,
                        "is_prn_dose": False,
                    }
                )

                log.mark_skipped(reason)
                skipped_count += 1

        time_display = dict(MedicineSchedule.TIME_OF_DAY_CHOICES).get(time_of_day, time_of_day)
        messages.info(request, f"Skipped {skipped_count} {time_display} dose{'s' if skipped_count != 1 else ''}.")

        next_url = request.POST.get("next", reverse_lazy("health:medicine_home"))
        return redirect(next_url)


class PRNLogView(LoginRequiredMixin, TemplateView):
    """
    Log a PRN (as-needed) dose.
    """

    template_name = "health/medicine/prn_log.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = PRNDoseForm(user=self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        form = PRNDoseForm(request.POST, user=request.user)
        if form.is_valid():
            medicine = form.cleaned_data["medicine"]
            today = get_user_today(request.user)

            # Create the log
            MedicineLog.objects.create(
                user=request.user,
                medicine=medicine,
                scheduled_date=today,
                taken_at=timezone.now(),
                log_status=MedicineLog.STATUS_TAKEN,
                is_prn_dose=True,
                prn_reason=form.cleaned_data.get("reason", ""),
                notes=form.cleaned_data.get("notes", ""),
            )

            # Decrease supply if tracked
            if medicine.current_supply is not None and medicine.current_supply > 0:
                medicine.current_supply -= 1
                medicine.save(update_fields=["current_supply", "updated_at"])

            messages.success(request, f"Logged PRN dose of {medicine.name}.")
            return redirect("health:medicine_home")

        context = self.get_context_data()
        context["form"] = form
        return self.render_to_response(context)


class MedicineHistoryView(LoginRequiredMixin, TemplateView):
    """
    View medicine history including all scheduled doses (logged and unlogged).

    Shows complete history of scheduled doses with ability to retroactively
    mark missed doses as taken or skipped.
    """

    template_name = "health/medicine/history.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)

        # Get filter parameters
        medicine_id = self.request.GET.get("medicine")
        start_date_str = self.request.GET.get("start")
        end_date_str = self.request.GET.get("end")

        # Parse dates with defaults
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            except ValueError:
                start_date = today - timedelta(days=30)
        else:
            # Default to last 30 days
            start_date = today - timedelta(days=30)

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            except ValueError:
                end_date = today
        else:
            end_date = today

        # Build list of all expected doses in date range
        all_doses = self._get_all_doses_for_range(user, start_date, end_date, medicine_id)

        # Group doses by date (most recent first)
        from collections import OrderedDict
        doses_by_date = OrderedDict()
        for dose in all_doses:
            date = dose["scheduled_date"]
            if date not in doses_by_date:
                doses_by_date[date] = []
            doses_by_date[date].append(dose)

        context["doses_by_date"] = doses_by_date
        context["medicines"] = Medicine.objects.filter(user=user)
        context["selected_medicine"] = medicine_id
        context["start_date"] = start_date
        context["end_date"] = end_date

        # Add user timezone for template display
        try:
            context["user_timezone"] = user.preferences.timezone_iana
        except AttributeError:
            context["user_timezone"] = "UTC"

        return context

    def _get_all_doses_for_range(self, user, start_date, end_date, medicine_id=None):
        """
        Generate list of all expected doses in date range, combining:
        - Actual logged doses (from MedicineLog)
        - Expected but unlogged doses (from MedicineSchedule)
        """
        from datetime import timedelta

        # Get medicines to process
        medicines_qs = Medicine.objects.filter(user=user)
        if medicine_id:
            medicines_qs = medicines_qs.filter(pk=medicine_id)

        # Get all logs in range
        logs_qs = MedicineLog.objects.filter(
            user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
        ).select_related("medicine", "schedule")

        if medicine_id:
            logs_qs = logs_qs.filter(medicine_id=medicine_id)

        # Index logs by (medicine_id, schedule_id, date) for quick lookup
        logged_doses = {}
        for log in logs_qs:
            key = (log.medicine_id, log.schedule_id, log.scheduled_date)
            logged_doses[key] = log

        all_doses = []

        # Iterate through each day in range
        current_date = end_date
        while current_date >= start_date:
            day_of_week = current_date.weekday()

            # Check each medicine's schedules
            for medicine in medicines_qs.prefetch_related("schedules"):
                # Skip PRN-only medicines
                if medicine.is_prn:
                    continue

                # Check if medicine was active on this date
                if medicine.start_date and current_date < medicine.start_date:
                    continue
                if medicine.end_date and current_date > medicine.end_date:
                    continue

                for schedule in medicine.schedules.filter(is_active=True):
                    # Check if schedule applies to this day of week
                    if not schedule.applies_to_day(day_of_week):
                        continue

                    key = (medicine.pk, schedule.pk, current_date)
                    log = logged_doses.get(key)

                    dose_info = {
                        "scheduled_date": current_date,
                        "scheduled_time": schedule.scheduled_time,
                        "medicine": medicine,
                        "schedule": schedule,
                        "log": log,
                        "log_status": log.log_status if log else "pending",
                        "taken_at": log.taken_at if log else None,
                        "is_prn_dose": False,
                        "notes": log.notes if log else "",
                    }
                    all_doses.append(dose_info)

            # Also include PRN doses for this date (they have logs)
            for log in logs_qs.filter(scheduled_date=current_date, is_prn_dose=True):
                dose_info = {
                    "scheduled_date": current_date,
                    "scheduled_time": log.scheduled_time,
                    "medicine": log.medicine,
                    "schedule": log.schedule,
                    "log": log,
                    "log_status": log.log_status,
                    "taken_at": log.taken_at,
                    "is_prn_dose": True,
                    "prn_reason": log.prn_reason,
                    "notes": log.notes,
                }
                all_doses.append(dose_info)

            current_date -= timedelta(days=1)

        # Sort by date desc, then time
        all_doses.sort(key=lambda x: (
            -x["scheduled_date"].toordinal(),
            x["scheduled_time"] or datetime.min.time()
        ))

        return all_doses


class MedicineLogEditView(LoginRequiredMixin, UpdateView):
    """
    Edit the taken_at time of a medicine log entry.

    Allows users to correct the time when they actually took a dose,
    which is important when they took the medicine on time but forgot
    to log it immediately.
    """

    model = MedicineLog
    form_class = MedicineLogEditForm
    template_name = "health/medicine/log_edit.html"

    def get_queryset(self):
        """Only allow editing the user's own logs."""
        return MedicineLog.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["log"] = self.object
        context["medicine"] = self.object.medicine
        return context

    def get_success_url(self):
        """Return to the referring page or medicine history."""
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url:
            return next_url
        return reverse_lazy("health:medicine_history")

    def form_valid(self, form):
        messages.success(
            self.request,
            f"Updated taken time for {self.object.medicine.name}."
        )
        return super().form_valid(form)


class MedicineHistoryTakeView(LoginRequiredMixin, View):
    """
    Mark a past scheduled dose as taken from the history page.

    Allows retroactive logging of doses that were taken but not recorded.
    """

    def post(self, request, pk, schedule_pk):
        import pytz

        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk,
        )
        schedule = get_object_or_404(
            medicine.schedules.all(),
            pk=schedule_pk,
        )

        # Get the date from POST (required for history)
        date_str = request.POST.get("date")
        if not date_str:
            messages.error(request, "Date is required.")
            return redirect(request.POST.get("next", reverse_lazy("health:medicine_history")))

        try:
            dose_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect(request.POST.get("next", reverse_lazy("health:medicine_history")))

        # Get or create the log entry for this specific date
        log, created = MedicineLog.objects.get_or_create(
            user=request.user,
            medicine=medicine,
            schedule=schedule,
            scheduled_date=dose_date,
            defaults={
                "scheduled_time": schedule.scheduled_time,
                "is_prn_dose": False,
            }
        )

        # Determine taken_at time
        taken_at = None
        if request.POST.get("taken_at_scheduled"):
            # Use the scheduled time on that date
            user_tz = pytz.timezone(request.user.preferences.timezone_iana)
            scheduled_dt = datetime.combine(dose_date, schedule.scheduled_time)
            taken_at = user_tz.localize(scheduled_dt)
        elif request.POST.get("taken_at_time"):
            # Use specific time provided
            time_str = request.POST.get("taken_at_time")
            try:
                taken_time = datetime.strptime(time_str, "%H:%M").time()
                user_tz = pytz.timezone(request.user.preferences.timezone_iana)
                taken_dt = datetime.combine(dose_date, taken_time)
                taken_at = user_tz.localize(taken_dt)
            except ValueError:
                pass  # Fall back to current time

        # Mark as taken
        log.mark_taken(taken_at=taken_at)

        # Decrease supply if tracked (only if newly created)
        if created and medicine.current_supply is not None and medicine.current_supply > 0:
            medicine.current_supply -= 1
            medicine.save(update_fields=["current_supply", "updated_at"])

        messages.success(request, f"Marked {medicine.name} as taken for {dose_date.strftime('%b %d')}.")

        next_url = request.POST.get("next", reverse_lazy("health:medicine_history"))
        return redirect(next_url)


class MedicineHistorySkipView(LoginRequiredMixin, View):
    """
    Mark a past scheduled dose as skipped from the history page.

    Allows retroactive marking of doses that were intentionally skipped.
    """

    def post(self, request, pk, schedule_pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk,
        )
        schedule = get_object_or_404(
            medicine.schedules.all(),
            pk=schedule_pk,
        )

        # Get the date from POST (required for history)
        date_str = request.POST.get("date")
        if not date_str:
            messages.error(request, "Date is required.")
            return redirect(request.POST.get("next", reverse_lazy("health:medicine_history")))

        try:
            dose_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect(request.POST.get("next", reverse_lazy("health:medicine_history")))

        reason = request.POST.get("reason", "")

        # Get or create the log entry for this specific date
        log, created = MedicineLog.objects.get_or_create(
            user=request.user,
            medicine=medicine,
            schedule=schedule,
            scheduled_date=dose_date,
            defaults={
                "scheduled_time": schedule.scheduled_time,
                "is_prn_dose": False,
            }
        )

        # Mark as skipped
        log.mark_skipped(reason)

        messages.info(request, f"Marked {medicine.name} as skipped for {dose_date.strftime('%b %d')}.")

        next_url = request.POST.get("next", reverse_lazy("health:medicine_history"))
        return redirect(next_url)


class MedicineAdherenceView(LoginRequiredMixin, TemplateView):
    """
    View adherence statistics and trends.
    """

    template_name = "health/medicine/adherence.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)

        # Date range
        period = self.request.GET.get("period", "week")
        if period == "week":
            start_date = today - timedelta(days=7)
        elif period == "month":
            start_date = today - timedelta(days=30)
        else:
            start_date = today - timedelta(days=7)

        context["period"] = period
        context["start_date"] = start_date
        context["end_date"] = today

        # Get all logs in the period
        logs = MedicineLog.objects.filter(
            user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=today,
            is_prn_dose=False,  # Only count scheduled doses
        )

        total = logs.count()
        taken = logs.filter(
            log_status__in=[MedicineLog.STATUS_TAKEN, MedicineLog.STATUS_LATE]
        ).count()
        missed = logs.filter(log_status=MedicineLog.STATUS_MISSED).count()
        skipped = logs.filter(log_status=MedicineLog.STATUS_SKIPPED).count()
        late = logs.filter(log_status=MedicineLog.STATUS_LATE).count()

        context["total_scheduled"] = total
        context["taken_count"] = taken
        context["missed_count"] = missed
        context["skipped_count"] = skipped
        context["late_count"] = late
        context["adherence_rate"] = round(taken / total * 100) if total > 0 else 0

        # Per-medicine breakdown
        medicines = Medicine.objects.filter(user=user)
        medicine_stats = []
        for medicine in medicines:
            med_logs = logs.filter(medicine=medicine)
            med_total = med_logs.count()
            med_taken = med_logs.filter(
                log_status__in=[MedicineLog.STATUS_TAKEN, MedicineLog.STATUS_LATE]
            ).count()
            if med_total > 0:
                medicine_stats.append({
                    "medicine": medicine,
                    "total": med_total,
                    "taken": med_taken,
                    "rate": round(med_taken / med_total * 100),
                })
        context["medicine_stats"] = sorted(
            medicine_stats, key=lambda x: x["rate"]
        )

        # Daily breakdown for chart
        daily_data = []
        current = start_date
        while current <= today:
            day_logs = logs.filter(scheduled_date=current)
            day_total = day_logs.count()
            day_taken = day_logs.filter(
                log_status__in=[MedicineLog.STATUS_TAKEN, MedicineLog.STATUS_LATE]
            ).count()
            daily_data.append({
                "date": current.isoformat(),
                "total": day_total,
                "taken": day_taken,
                "rate": round(day_taken / day_total * 100) if day_total > 0 else 100,
            })
            current += timedelta(days=1)
        context["daily_data"] = daily_data

        return context


class MedicineUpdateSupplyView(LoginRequiredMixin, View):
    """
    Quick update of medicine supply count.
    """

    def post(self, request, pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk,
        )
        form = UpdateSupplyForm(request.POST)
        if form.is_valid():
            medicine.current_supply = form.cleaned_data["current_supply"]
            medicine.save(update_fields=["current_supply", "updated_at"])
            messages.success(request, f"Updated supply for {medicine.name}.")
        return redirect("health:medicine_detail", pk=pk)


class MedicineQuickLookView(LoginRequiredMixin, TemplateView):
    """
    Quick look view - condensed medicine summary for screenshots/sharing.
    """

    template_name = "health/medicine/quick_look.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Get active medicines only
        medicines = Medicine.objects.filter(
            user=user,
            medicine_status=Medicine.STATUS_ACTIVE,
        ).prefetch_related("schedules")

        context["medicines"] = medicines
        context["generated_at"] = timezone.now()
        return context


# =============================================================================
# Nutrition / Food Tracking Views
# =============================================================================


class NutritionHomeView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Nutrition module home - daily food tracker dashboard.
    """

    template_name = "health/nutrition/home.html"
    help_context_id = "NUTRITION_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)

        # Today's food entries
        today_entries = FoodEntry.objects.filter(
            user=user,
            logged_date=today,
        ).order_by('logged_time', 'created_at')

        context["today"] = today
        context["today_entries"] = today_entries

        # Group entries by meal type
        breakfast_entries = today_entries.filter(meal_type=FoodEntry.MEAL_BREAKFAST)
        lunch_entries = today_entries.filter(meal_type=FoodEntry.MEAL_LUNCH)
        dinner_entries = today_entries.filter(meal_type=FoodEntry.MEAL_DINNER)
        snack_entries = today_entries.filter(meal_type=FoodEntry.MEAL_SNACK)

        context["breakfast_entries"] = breakfast_entries
        context["lunch_entries"] = lunch_entries
        context["dinner_entries"] = dinner_entries
        context["snack_entries"] = snack_entries

        # Calculate subtotals for each meal type
        from django.db.models import Sum

        def get_meal_subtotals(entries):
            totals = entries.aggregate(
                calories=Sum('total_calories'),
                protein=Sum('total_protein_g'),
                carbs=Sum('total_carbohydrates_g'),
                fat=Sum('total_fat_g'),
            )
            return {
                'calories': totals['calories'] or 0,
                'protein': totals['protein'] or 0,
                'carbs': totals['carbs'] or 0,
                'fat': totals['fat'] or 0,
            }

        context["breakfast_totals"] = get_meal_subtotals(breakfast_entries)
        context["lunch_totals"] = get_meal_subtotals(lunch_entries)
        context["dinner_totals"] = get_meal_subtotals(dinner_entries)
        context["snack_totals"] = get_meal_subtotals(snack_entries)

        # Calculate today's totals
        totals = today_entries.aggregate(
            calories=Sum('total_calories'),
            protein=Sum('total_protein_g'),
            carbs=Sum('total_carbohydrates_g'),
            fat=Sum('total_fat_g'),
            fiber=Sum('total_fiber_g'),
            sugar=Sum('total_sugar_g'),
        )

        context["total_calories"] = totals['calories'] or 0
        context["total_protein"] = totals['protein'] or 0
        context["total_carbs"] = totals['carbs'] or 0
        context["total_fat"] = totals['fat'] or 0
        context["total_fiber"] = totals['fiber'] or 0
        context["total_sugar"] = totals['sugar'] or 0

        # Get user's nutrition goals
        goals = NutritionGoals.objects.filter(
            user=user,
            effective_until__isnull=True,
        ).first()
        context["goals"] = goals

        # Calculate progress percentages if goals exist
        if goals and goals.daily_calorie_target:
            context["calorie_progress"] = min(100, int(
                float(context["total_calories"]) / goals.daily_calorie_target * 100
            ))
        if goals and goals.daily_protein_target_g:
            context["protein_progress"] = min(100, int(
                float(context["total_protein"]) / goals.daily_protein_target_g * 100
            ))
        if goals and goals.daily_carb_target_g:
            context["carb_progress"] = min(100, int(
                float(context["total_carbs"]) / goals.daily_carb_target_g * 100
            ))
        if goals and goals.daily_fat_target_g:
            context["fat_progress"] = min(100, int(
                float(context["total_fat"]) / goals.daily_fat_target_g * 100
            ))

        # Recent custom foods for quick access
        context["recent_foods"] = CustomFood.objects.filter(
            user=user,
        ).order_by('-updated_at')[:5]

        return context


class FoodEntryCreateView(HelpContextMixin, SaveAddAnotherMixin, LoginRequiredMixin, CreateView):
    """
    Log a new food entry.
    """

    model = FoodEntry
    form_class = FoodEntryForm
    template_name = "health/nutrition/food_entry_form.html"
    success_url = reverse_lazy("health:nutrition_home")
    help_context_id = "NUTRITION_ENTRY_CREATE"
    save_add_another_message = "Food logged. Add another!"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        GET = self.request.GET

        # Pre-fill meal type from query param
        meal_type = GET.get('meal')
        if meal_type in dict(FoodEntry.MEAL_CHOICES):
            initial['meal_type'] = meal_type

        # Pre-fill from camera scan (food recognition)
        if GET.get('food_name'):
            initial['food_name'] = GET.get('food_name')
        if GET.get('food_brand'):
            initial['food_brand'] = GET.get('food_brand')
        if GET.get('total_calories'):
            initial['total_calories'] = GET.get('total_calories')
        if GET.get('total_protein_g'):
            initial['total_protein_g'] = GET.get('total_protein_g')
        if GET.get('total_carbohydrates_g'):
            initial['total_carbohydrates_g'] = GET.get('total_carbohydrates_g')
        if GET.get('total_fat_g'):
            initial['total_fat_g'] = GET.get('total_fat_g')
        if GET.get('total_fiber_g'):
            initial['total_fiber_g'] = GET.get('total_fiber_g')
        if GET.get('total_sugar_g'):
            initial['total_sugar_g'] = GET.get('total_sugar_g')
        if GET.get('total_saturated_fat_g'):
            initial['total_saturated_fat_g'] = GET.get('total_saturated_fat_g')
        if GET.get('serving_size'):
            initial['serving_size'] = GET.get('serving_size')
        if GET.get('serving_unit'):
            initial['serving_unit'] = GET.get('serving_unit')
        if GET.get('notes'):
            initial['notes'] = GET.get('notes')

        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Track if this is from camera scan or barcode scan for display purposes
        context['from_camera'] = self.request.GET.get('source') == 'ai_camera'
        context['from_barcode'] = self.request.GET.get('entry_source') == 'barcode'
        context['scanned_barcode'] = self.request.GET.get('barcode', '')
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        # Set entry source based on how user got here
        entry_source = self.request.GET.get('entry_source', 'manual')
        if entry_source == 'camera':
            form.instance.entry_source = FoodEntry.SOURCE_CAMERA
        elif entry_source == 'barcode':
            form.instance.entry_source = FoodEntry.SOURCE_BARCODE
        else:
            form.instance.entry_source = FoodEntry.SOURCE_MANUAL

        # Handle different submit buttons
        if 'save_and_scan' in self.request.POST:
            # Save the form first
            super().form_valid(form)
            messages.success(self.request, "Food logged. Scan another!")
            # Redirect to scan page with barcode mode
            scan_url = reverse('scan:home') + '?mode=barcode'
            # Preserve meal type if present
            meal_type = form.cleaned_data.get('meal_type')
            if meal_type:
                scan_url += f'&meal={meal_type}'
            return redirect(scan_url)
        elif 'save_add_another' not in self.request.POST:
            messages.success(self.request, "Food logged.")
        return super().form_valid(form)


class FoodEntryUpdateView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """
    Edit a food entry.
    """

    model = FoodEntry
    form_class = FoodEntryForm
    template_name = "health/nutrition/food_entry_form.html"
    success_url = reverse_lazy("health:nutrition_home")
    help_context_id = "NUTRITION_ENTRY_EDIT"

    def get_queryset(self):
        return FoodEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Food entry updated.")
        return super().form_valid(form)


class FoodEntryDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a food entry.
    Supports undo via toast notification for AJAX requests.
    """

    model = FoodEntry
    item_type = 'health.foodentry'
    item_name = 'food entry'
    success_url = 'health:nutrition_home'

    def get_object(self):
        return get_object_or_404(
            FoodEntry.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )

    def get_success_url(self):
        # Redirect back to referring page or nutrition home
        next_url = self.request.POST.get('next', self.request.META.get('HTTP_REFERER'))
        if next_url:
            return next_url
        from django.urls import reverse
        return reverse('health:nutrition_home')


class FoodEntryDetailView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    View details of a food entry.
    """

    template_name = "health/nutrition/food_entry_detail.html"
    help_context_id = "NUTRITION_ENTRY_DETAIL"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["entry"] = get_object_or_404(
            FoodEntry.objects.filter(user=self.request.user),
            pk=self.kwargs['pk'],
        )
        return context


class QuickAddFoodView(HelpContextMixin, LoginRequiredMixin, View):
    """
    Quick calorie-only food logging.
    """

    template_name = "health/nutrition/quick_add.html"
    help_context_id = "NUTRITION_QUICK_ADD"

    def get(self, request):
        from .forms import QuickAddFoodForm
        form = QuickAddFoodForm(user=request.user)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        from .forms import QuickAddFoodForm
        form = QuickAddFoodForm(request.POST, user=request.user)
        if form.is_valid():
            # Create a food entry with minimal info
            entry = FoodEntry.objects.create(
                user=request.user,
                food_name=form.cleaned_data['food_name'],
                quantity=1,
                serving_size=1,
                serving_unit="serving",
                total_calories=form.cleaned_data['calories'],
                total_protein_g=0,
                total_carbohydrates_g=0,
                total_fat_g=0,
                logged_date=form.cleaned_data['logged_date'],
                meal_type=form.cleaned_data['meal_type'],
                entry_source=FoodEntry.SOURCE_QUICK_ADD,
            )
            messages.success(request, f"Logged {entry.total_calories} calories.")
            return redirect("health:nutrition_home")
        return render(request, self.template_name, {"form": form})


class FoodHistoryView(HelpContextMixin, LoginRequiredMixin, ListView):
    """
    Historical food log.
    """

    model = FoodEntry
    template_name = "health/nutrition/history.html"
    context_object_name = "entries"
    paginate_by = 50
    help_context_id = "NUTRITION_HISTORY"

    def get_queryset(self):
        qs = FoodEntry.objects.filter(user=self.request.user)

        # Filter by date range
        start_date = self.request.GET.get('start')
        end_date = self.request.GET.get('end')
        if start_date:
            qs = qs.filter(logged_date__gte=start_date)
        if end_date:
            qs = qs.filter(logged_date__lte=end_date)

        # Filter by meal type
        meal_type = self.request.GET.get('meal')
        if meal_type:
            qs = qs.filter(meal_type=meal_type)

        return qs.order_by('-logged_date', '-logged_time')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["meal_choices"] = FoodEntry.MEAL_CHOICES
        context["selected_meal"] = self.request.GET.get('meal', '')
        context["start_date"] = self.request.GET.get('start', '')
        context["end_date"] = self.request.GET.get('end', '')
        return context


class NutritionStatsView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Nutrition statistics and trends.
    """

    template_name = "health/nutrition/stats.html"
    help_context_id = "NUTRITION_STATS"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_user_today(user)

        # Get period from query param (default: 7 days)
        period = self.request.GET.get('period', '7')
        try:
            days = int(period)
        except ValueError:
            days = 7

        start_date = today - timedelta(days=days - 1)
        context["period"] = days
        context["start_date"] = start_date
        context["end_date"] = today

        # Get entries for period
        entries = FoodEntry.objects.filter(
            user=user,
            logged_date__gte=start_date,
            logged_date__lte=today,
        )

        # Daily aggregates
        from django.db.models import Sum
        daily_stats = []
        current = start_date
        while current <= today:
            day_entries = entries.filter(logged_date=current)
            day_totals = day_entries.aggregate(
                calories=Sum('total_calories'),
                protein=Sum('total_protein_g'),
                carbs=Sum('total_carbohydrates_g'),
                fat=Sum('total_fat_g'),
            )
            daily_stats.append({
                "date": current,
                "calories": day_totals['calories'] or 0,
                "protein": day_totals['protein'] or 0,
                "carbs": day_totals['carbs'] or 0,
                "fat": day_totals['fat'] or 0,
                "entry_count": day_entries.count(),
            })
            current += timedelta(days=1)

        context["daily_stats"] = daily_stats

        # Period averages
        total_entries = entries.count()
        if total_entries > 0:
            period_totals = entries.aggregate(
                calories=Sum('total_calories'),
                protein=Sum('total_protein_g'),
                carbs=Sum('total_carbohydrates_g'),
                fat=Sum('total_fat_g'),
                fiber=Sum('total_fiber_g'),
                sugar=Sum('total_sugar_g'),
            )
            days_with_entries = len([d for d in daily_stats if d['entry_count'] > 0])
            if days_with_entries > 0:
                context["avg_daily_calories"] = int(float(period_totals['calories'] or 0) / days_with_entries)
                context["avg_daily_protein"] = int(float(period_totals['protein'] or 0) / days_with_entries)
                context["avg_daily_carbs"] = int(float(period_totals['carbs'] or 0) / days_with_entries)
                context["avg_daily_fat"] = int(float(period_totals['fat'] or 0) / days_with_entries)

        # Get goals for comparison
        context["goals"] = NutritionGoals.objects.filter(
            user=user,
            effective_until__isnull=True,
        ).first()

        return context


class NutritionGoalsView(HelpContextMixin, LoginRequiredMixin, View):
    """
    View and edit nutrition goals.
    """

    template_name = "health/nutrition/goals.html"
    help_context_id = "NUTRITION_GOALS"

    def get(self, request):
        from .forms import NutritionGoalsForm
        # Get current active goals
        goals = NutritionGoals.objects.filter(
            user=request.user,
            effective_until__isnull=True,
        ).first()
        form = NutritionGoalsForm(instance=goals)
        return render(request, self.template_name, {"form": form, "goals": goals})

    def post(self, request):
        from .forms import NutritionGoalsForm
        # Get or create goals
        goals = NutritionGoals.objects.filter(
            user=request.user,
            effective_until__isnull=True,
        ).first()

        if goals:
            form = NutritionGoalsForm(request.POST, instance=goals)
        else:
            form = NutritionGoalsForm(request.POST)

        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            if not goal.effective_from:
                goal.effective_from = get_user_today(request.user)
            goal.save()
            messages.success(request, "Nutrition goals updated.")
            return redirect("health:nutrition_goals")

        return render(request, self.template_name, {"form": form, "goals": goals})


class CustomFoodListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """
    List user's custom foods.
    """

    model = CustomFood
    template_name = "health/nutrition/custom_food_list.html"
    context_object_name = "foods"
    paginate_by = 30
    help_context_id = "NUTRITION_CUSTOM_FOODS"

    def get_queryset(self):
        return CustomFood.objects.filter(user=self.request.user)


class CustomFoodCreateView(HelpContextMixin, LoginRequiredMixin, CreateView):
    """
    Create a custom food.
    """

    model = CustomFood
    form_class = CustomFoodForm
    template_name = "health/nutrition/custom_food_form.html"
    success_url = reverse_lazy("health:custom_food_list")
    help_context_id = "NUTRITION_CUSTOM_FOOD_CREATE"

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Custom food created.")
        return super().form_valid(form)


class CustomFoodUpdateView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """
    Edit a custom food.
    """

    model = CustomFood
    form_class = CustomFoodForm
    template_name = "health/nutrition/custom_food_form.html"
    success_url = reverse_lazy("health:custom_food_list")
    help_context_id = "NUTRITION_CUSTOM_FOOD_EDIT"

    def get_queryset(self):
        return CustomFood.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Custom food updated.")
        return super().form_valid(form)


class CustomFoodDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a custom food.
    Supports undo via toast notification for AJAX requests.
    """

    model = CustomFood
    item_type = 'health.customfood'
    item_name = 'custom food'
    success_url = 'health:custom_food_list'

    def get_object(self):
        return get_object_or_404(
            CustomFood.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


# =============================================================================
# Food Search API
# =============================================================================


class FoodSearchAPIView(LoginRequiredMixin, View):
    """
    API endpoint for food autocomplete search.

    Searches across multiple sources:
    1. User's CustomFood items
    2. Global FoodItem database
    3. FatSecret API (if insufficient local results)
    4. AI estimation (if nothing found)

    GET /health/nutrition/api/search/?q=query&limit=10

    Returns JSON:
    {
        "results": [
            {
                "id": "local_123",
                "name": "Food Name",
                "brand": "Brand",
                "source": "local|custom|fatsecret|ai",
                "calories": 250,
                "protein_g": 12,
                ...
            }
        ]
    }
    """

    def get(self, request):
        query = request.GET.get('q', '').strip()
        limit = min(int(request.GET.get('limit', 10)), 20)

        if len(query) < 2:
            return JsonResponse({'results': []})

        try:
            from .services.food_search import food_search_service

            results = food_search_service.search(
                query=query,
                user=request.user,
                limit=limit,
                use_fatsecret=True,
                use_ai=True
            )

            return JsonResponse({
                'results': [r.to_dict() for r in results]
            })

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Food search error: {e}")
            return JsonResponse({'results': [], 'error': str(e)}, status=500)


# =============================================================================
# Blood Pressure Views
# =============================================================================


class BloodPressureListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """
    List blood pressure entries.
    """

    model = BloodPressureEntry
    template_name = "health/blood_pressure_list.html"
    context_object_name = "entries"
    paginate_by = 30
    help_context_id = "HEALTH_VITALS"

    def get_queryset(self):
        return BloodPressureEntry.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = self.get_queryset()

        if entries.exists():
            context["latest"] = entries.first()

            # Average stats
            stats = entries.aggregate(
                avg_systolic=Avg("systolic"),
                avg_diastolic=Avg("diastolic"),
                min_systolic=Min("systolic"),
                max_systolic=Max("systolic"),
            )
            context["avg_systolic"] = round(stats["avg_systolic"]) if stats["avg_systolic"] else None
            context["avg_diastolic"] = round(stats["avg_diastolic"]) if stats["avg_diastolic"] else None
            context["min_systolic"] = stats["min_systolic"]
            context["max_systolic"] = stats["max_systolic"]

        return context


class BloodPressureCreateView(HelpContextMixin, SaveAddAnotherMixin, LoginRequiredMixin, CreateView):
    """
    Log a new blood pressure entry.
    """

    model = BloodPressureEntry
    form_class = BloodPressureEntryForm
    template_name = "health/blood_pressure_form.html"
    success_url = reverse_lazy("health:blood_pressure_list")
    save_add_another_message = "Blood pressure logged. Add another!"
    help_context_id = "HEALTH_VITALS"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        if 'save_add_another' not in self.request.POST:
            messages.success(self.request, "Blood pressure logged.")
        return super().form_valid(form)


class BloodPressureUpdateView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """
    Edit a blood pressure entry.
    """

    model = BloodPressureEntry
    form_class = BloodPressureEntryForm
    template_name = "health/blood_pressure_form.html"
    success_url = reverse_lazy("health:blood_pressure_list")
    help_context_id = "HEALTH_VITALS"

    def get_queryset(self):
        return BloodPressureEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class BloodPressureDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a blood pressure entry.
    Supports undo via toast notification for AJAX requests.
    """

    model = BloodPressureEntry
    item_type = 'health.bloodpressureentry'
    item_name = 'blood pressure entry'
    success_url = 'health:blood_pressure_list'

    def get_object(self):
        return get_object_or_404(
            BloodPressureEntry.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


# =============================================================================
# Blood Oxygen Views
# =============================================================================


class BloodOxygenListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """
    List blood oxygen (SpO2) entries.
    """

    model = BloodOxygenEntry
    template_name = "health/blood_oxygen_list.html"
    context_object_name = "entries"
    paginate_by = 30
    help_context_id = "HEALTH_VITALS"

    def get_queryset(self):
        return BloodOxygenEntry.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = self.get_queryset()

        if entries.exists():
            context["latest"] = entries.first()

            # Average stats
            stats = entries.aggregate(
                avg_spo2=Avg("spo2"),
                min_spo2=Min("spo2"),
                max_spo2=Max("spo2"),
            )
            context["avg_spo2"] = round(stats["avg_spo2"]) if stats["avg_spo2"] else None
            context["min_spo2"] = stats["min_spo2"]
            context["max_spo2"] = stats["max_spo2"]

        return context


class BloodOxygenCreateView(HelpContextMixin, LoginRequiredMixin, CreateView):
    """
    Log a new blood oxygen (SpO2) entry.
    """

    model = BloodOxygenEntry
    form_class = BloodOxygenEntryForm
    template_name = "health/blood_oxygen_form.html"
    success_url = reverse_lazy("health:blood_oxygen_list")
    help_context_id = "HEALTH_VITALS"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Blood oxygen logged.")
        return super().form_valid(form)


class BloodOxygenUpdateView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """
    Edit a blood oxygen entry.
    """

    model = BloodOxygenEntry
    form_class = BloodOxygenEntryForm
    template_name = "health/blood_oxygen_form.html"
    success_url = reverse_lazy("health:blood_oxygen_list")
    help_context_id = "HEALTH_VITALS"

    def get_queryset(self):
        return BloodOxygenEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class BloodOxygenDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a blood oxygen entry.
    Supports undo via toast notification for AJAX requests.
    """

    model = BloodOxygenEntry
    item_type = 'health.bloodoxygenentry'
    item_name = 'blood oxygen entry'
    success_url = 'health:blood_oxygen_list'

    def get_object(self):
        return get_object_or_404(
            BloodOxygenEntry.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


# =============================================================================
# Medicine Refill Request Views
# =============================================================================


class MedicineRequestRefillView(LoginRequiredMixin, View):
    """
    Mark a medicine as having a refill requested.
    """

    def post(self, request, pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk
        )
        medicine.request_refill()
        messages.success(request, f"Refill requested for {medicine.name}.")
        return redirect("health:medicine_detail", pk=medicine.pk)


class MedicineClearRefillView(LoginRequiredMixin, View):
    """
    Clear the refill request (e.g., when refill is received).
    """

    def post(self, request, pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk
        )
        medicine.clear_refill_request()
        messages.success(request, f"Refill request cleared for {medicine.name}.")
        return redirect("health:medicine_detail", pk=medicine.pk)


# =============================================================================
# Medical Provider Views
# =============================================================================


class MedicalProviderListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """
    List user's medical providers.
    """

    model = None  # Set in get_queryset
    template_name = "health/providers/provider_list.html"
    context_object_name = "providers"
    paginate_by = 30
    help_context_id = "HEALTH_PROVIDERS"

    def get_queryset(self):
        from .models import MedicalProvider
        return MedicalProvider.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["specialty_choices"] = dict(self._get_specialty_choices())
        return context

    def _get_specialty_choices(self):
        from .models import MedicalProvider
        return MedicalProvider.SPECIALTY_CHOICES


class MedicalProviderDetailView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    View details of a medical provider with their staff.
    """

    template_name = "health/providers/provider_detail.html"
    help_context_id = "HEALTH_PROVIDER_DETAIL"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import MedicalProvider
        context["provider"] = get_object_or_404(
            MedicalProvider.objects.filter(user=self.request.user),
            pk=self.kwargs['pk'],
        )
        # Get all staff for this provider
        context["staff_members"] = context["provider"].staff.all()
        return context


class MedicalProviderCreateView(HelpContextMixin, LoginRequiredMixin, CreateView):
    """
    Add a new medical provider.
    """

    model = None  # Set dynamically
    template_name = "health/providers/provider_form.html"
    success_url = reverse_lazy("health:provider_list")
    help_context_id = "HEALTH_PROVIDER_CREATE"

    def get_form_class(self):
        from .forms import MedicalProviderForm
        return MedicalProviderForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Added provider: {form.instance.name}")
        return super().form_valid(form)


class MedicalProviderUpdateView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """
    Edit a medical provider.
    """

    template_name = "health/providers/provider_form.html"
    help_context_id = "HEALTH_PROVIDER_EDIT"

    def get_queryset(self):
        from .models import MedicalProvider
        return MedicalProvider.objects.filter(user=self.request.user)

    def get_form_class(self):
        from .forms import MedicalProviderForm
        return MedicalProviderForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse_lazy("health:provider_detail", kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Provider updated.")
        return super().form_valid(form)


class MedicalProviderDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a medical provider (and all associated staff via CASCADE).
    Supports undo via toast notification for AJAX requests.
    """

    item_type = 'health.medicalprovider'
    item_name = 'provider'
    success_url = 'health:provider_list'

    def get_object(self):
        from .models import MedicalProvider
        return get_object_or_404(
            MedicalProvider.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


class ProviderAILookupView(LoginRequiredMixin, View):
    """
    AI-powered lookup of provider contact information.
    Uses OpenAI to search for provider details based on name and location.
    """

    def post(self, request):
        import json
        from django.conf import settings

        provider_name = request.POST.get('name', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()

        if not provider_name:
            return JsonResponse({
                'success': False,
                'error': 'Provider name is required.'
            })

        # Build location context
        location_parts = []
        if city:
            location_parts.append(city)
        if state:
            location_parts.append(state)
        location_str = ", ".join(location_parts) if location_parts else "USA"

        try:
            # Check if OpenAI is available
            openai_api_key = getattr(settings, 'OPENAI_API_KEY', None)
            if not openai_api_key:
                return JsonResponse({
                    'success': False,
                    'error': 'AI lookup is not configured.'
                })

            import openai
            client = openai.OpenAI(api_key=openai_api_key)

            prompt = f"""Look up the contact information for this healthcare provider:
Provider Name: {provider_name}
Location: {location_str}

Please provide the following information in JSON format if available:
- phone: main phone number
- fax: fax number
- address_line1: street address
- city: city name
- state: state abbreviation
- postal_code: ZIP code
- website: practice website URL
- specialty: medical specialty (use one of: primary_care, internal_medicine, pediatrics, obgyn, cardiology, dermatology, endocrinology, gastroenterology, neurology, oncology, ophthalmology, orthopedics, psychiatry, pulmonology, rheumatology, urology, dentist, optometrist, chiropractor, physical_therapy, mental_health, pharmacy, urgent_care, hospital, lab, imaging, other)
- credentials: provider credentials (e.g., MD, DO, DDS)
- npi_number: NPI number if known

Return ONLY valid JSON with no explanation. If information is not available, omit the field.
Example format: {{"phone": "(555) 123-4567", "address_line1": "123 Main St", "city": "Springfield", "state": "IL", "postal_code": "62701"}}"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that looks up healthcare provider information. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500,
            )

            result_text = response.choices[0].message.content.strip()

            # Clean up potential markdown code blocks
            if result_text.startswith("```"):
                lines = result_text.split("\n")
                result_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            try:
                provider_data = json.loads(result_text)
            except json.JSONDecodeError:
                return JsonResponse({
                    'success': False,
                    'error': 'Could not parse AI response. Please enter information manually.'
                })

            return JsonResponse({
                'success': True,
                'data': provider_data
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'AI lookup failed: {str(e)}'
            })


# =============================================================================
# Provider Staff Views
# =============================================================================


class ProviderStaffCreateView(HelpContextMixin, LoginRequiredMixin, CreateView):
    """
    Add a staff member to a provider.
    """

    template_name = "health/providers/staff_form.html"
    help_context_id = "HEALTH_PROVIDER_STAFF_CREATE"

    def get_form_class(self):
        from .forms import ProviderStaffForm
        return ProviderStaffForm

    def get_provider(self):
        from .models import MedicalProvider
        return get_object_or_404(
            MedicalProvider.objects.filter(user=self.request.user),
            pk=self.kwargs['provider_pk']
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['provider'] = self.get_provider()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['provider'] = self.get_provider()
        return context

    def get_success_url(self):
        return reverse_lazy("health:provider_detail", kwargs={'pk': self.kwargs['provider_pk']})

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.provider = self.get_provider()
        messages.success(self.request, f"Added staff member: {form.instance.name}")
        return super().form_valid(form)


class ProviderStaffUpdateView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """
    Edit a staff member.
    """

    template_name = "health/providers/staff_form.html"
    help_context_id = "HEALTH_PROVIDER_STAFF_EDIT"

    def get_queryset(self):
        from .models import ProviderStaff
        return ProviderStaff.objects.filter(user=self.request.user)

    def get_form_class(self):
        from .forms import ProviderStaffForm
        return ProviderStaffForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['provider'] = self.object.provider
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['provider'] = self.object.provider
        return context

    def get_success_url(self):
        return reverse_lazy("health:provider_detail", kwargs={'pk': self.object.provider.pk})

    def form_valid(self, form):
        messages.success(self.request, "Staff member updated.")
        return super().form_valid(form)


class ProviderStaffDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a staff member.
    Supports undo via toast notification for AJAX requests.
    """

    item_type = 'health.providerstaff'
    item_name = 'staff member'
    _cached_object = None

    def get_object(self):
        # Cache the object since get_success_url is called after soft_delete
        # and the SoftDeleteManager would exclude the deleted object
        if self._cached_object is None:
            from .models import ProviderStaff
            self._cached_object = get_object_or_404(
                ProviderStaff.objects.filter(user=self.request.user),
                pk=self.kwargs['pk']
            )
        return self._cached_object

    def get_success_url(self):
        from django.urls import reverse
        obj = self.get_object()
        return reverse("health:provider_detail", kwargs={'pk': obj.provider.pk})


# =============================================================================
# Dexcom CGM Integration Views
# =============================================================================


class DexcomConnectView(LoginRequiredMixin, View):
    """
    Initiate Dexcom OAuth connection.
    """

    def get(self, request):
        from .services.dexcom import DexcomService

        try:
            service = DexcomService()

            if not service.is_configured:
                messages.error(
                    request,
                    "Dexcom integration is not configured. "
                    "Please contact support."
                )
                return redirect("health:glucose_dashboard")

            # Generate authorization URL with state for CSRF protection
            auth_url, state = service.get_authorization_url()

            # Store state in session for verification
            request.session['dexcom_oauth_state'] = state

            return redirect(auth_url)

        except Exception as e:
            messages.error(request, f"Failed to initiate Dexcom connection: {e}")
            return redirect("health:glucose_dashboard")


class DexcomCallbackView(LoginRequiredMixin, View):
    """
    Handle Dexcom OAuth callback.
    """

    def get(self, request):
        import logging
        from .models import DexcomCredential
        from .services.dexcom import DexcomService

        logger = logging.getLogger(__name__)

        # Log callback receipt for debugging
        logger.info(f"Dexcom callback received - User: {user_log_id(request.user) if request.user.is_authenticated else 'anonymous'}")
        logger.info(f"Dexcom callback GET params: {dict(request.GET)}")

        # Check for errors from Dexcom
        error = request.GET.get('error')
        if error:
            error_desc = request.GET.get('error_description', 'Unknown error')
            logger.error(f"Dexcom OAuth error: {error} - {error_desc}")
            messages.error(request, f"Dexcom authorization failed: {error_desc}")
            return redirect("health:glucose_dashboard")

        # Get authorization code and state
        code = request.GET.get('code')
        state = request.GET.get('state')

        logger.info(f"Dexcom callback - code present: {bool(code)}, state: {state[:20] if state else 'None'}...")

        if not code:
            logger.error("Dexcom callback - No authorization code received")
            messages.error(request, "No authorization code received from Dexcom.")
            return redirect("health:glucose_dashboard")

        # Verify state matches what we stored (CSRF protection)
        stored_state = request.session.get('dexcom_oauth_state')
        logger.info(f"Dexcom callback - stored_state: {stored_state[:20] if stored_state else 'None'}...")

        if state != stored_state:
            logger.error(f"Dexcom callback - State mismatch: received={state}, stored={stored_state}")
            messages.error(request, "Invalid state parameter. Please try again.")
            return redirect("health:glucose_dashboard")

        # Clear the state from session
        request.session.pop('dexcom_oauth_state', None)

        try:
            service = DexcomService()
            logger.info(f"Dexcom token exchange - Using sandbox: {service.use_sandbox}, redirect_uri: {service.redirect_uri}")

            credentials = service.exchange_code_for_credentials(code)
            logger.info("Dexcom token exchange successful")

            # Create or update credential record
            credential, created = DexcomCredential.objects.update_or_create(
                user=request.user,
                defaults={
                    'access_token': credentials['access_token'],
                    'refresh_token': credentials.get('refresh_token', ''),
                    'token_expiry': credentials.get('token_expiry'),
                }
            )

            if created:
                logger.info(f"Dexcom credential created for {user_log_id(request.user)}")
                messages.success(
                    request,
                    "Dexcom connected successfully! Your glucose readings "
                    "will now sync automatically."
                )
            else:
                logger.info(f"Dexcom credential updated for {user_log_id(request.user)}")
                messages.success(request, "Dexcom connection updated.")

            # Trigger initial sync
            return redirect("health:dexcom_sync")

        except Exception as e:
            logger.exception(f"Dexcom token exchange failed: {e}")
            messages.error(request, f"Failed to complete Dexcom connection: {e}")
            return redirect("health:glucose_dashboard")


class DexcomSyncView(LoginRequiredMixin, View):
    """
    Manually trigger Dexcom glucose sync.
    """

    def get(self, request):
        return self.post(request)

    def post(self, request):
        from .services.dexcom import DexcomSyncService

        sync_service = DexcomSyncService(request.user)
        credential = sync_service.get_credential()

        if not credential:
            messages.warning(
                request,
                "Dexcom is not connected. Please connect your Dexcom account first."
            )
            return redirect("health:glucose_dashboard")

        # Get days to sync from request or use default
        days = int(request.POST.get('days', credential.days_to_sync))

        created, updated, error = sync_service.sync_from_dexcom(days=days)

        if error:
            messages.error(request, f"Sync failed: {error}")
        else:
            total = created + updated
            if total > 0:
                messages.success(
                    request,
                    f"Synced {total} glucose readings ({created} new, {updated} updated)."
                )
            else:
                messages.info(request, "No new glucose readings to sync.")

        return redirect("health:glucose_dashboard")


class DexcomDisconnectView(LoginRequiredMixin, View):
    """
    Disconnect Dexcom integration.
    """

    def post(self, request):
        from .services.dexcom import DexcomSyncService

        sync_service = DexcomSyncService(request.user)
        sync_service.disconnect()

        messages.success(
            request,
            "Dexcom disconnected. Your existing glucose readings have been kept."
        )
        return redirect("health:glucose_dashboard")


class GlucoseDashboardView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Glucose tracking dashboard with Dexcom integration.
    """

    template_name = "health/glucose/dashboard.html"
    help_context_id = "GLUCOSE_DASHBOARD"

    # Valid time periods in days (0 = today only)
    VALID_PERIODS = [0, 7, 30, 60, 90]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()
        today = get_user_today(user)

        # Get time period from query param (default to 7 days)
        try:
            period = int(self.request.GET.get('period', 7))
            if period not in self.VALID_PERIODS:
                period = 7
        except (ValueError, TypeError):
            period = 7

        context['period'] = period
        context['valid_periods'] = self.VALID_PERIODS

        # Calculate date range based on period
        today_start = timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time())
        )

        if period == 0:
            # Today only
            period_start = today_start
            period_label = "Today"
        else:
            period_start = now - timedelta(days=period)
            period_label = f"Last {period} Days"

        context['period_label'] = period_label

        # Check Dexcom connection status
        from .models import DexcomCredential
        try:
            dexcom_credential = user.dexcom_credential
            context['dexcom_connected'] = dexcom_credential.is_connected
            context['dexcom_credential'] = dexcom_credential
            context['dexcom_last_sync'] = dexcom_credential.last_sync
        except DexcomCredential.DoesNotExist:
            context['dexcom_connected'] = False
            context['dexcom_credential'] = None

        # Check if Dexcom is configured
        from .services.dexcom import DexcomService
        try:
            service = DexcomService()
            context['dexcom_configured'] = service.is_configured
        except Exception:
            context['dexcom_configured'] = False

        # Glucose entries for selected period
        glucose_entries = GlucoseEntry.objects.filter(
            user=user,
            recorded_at__gte=period_start
        ).order_by('-recorded_at')

        context['glucose_entries'] = glucose_entries[:50]  # Last 50 readings
        context['glucose_count'] = glucose_entries.count()

        # Today's readings (always show for quick reference)
        today_entries = GlucoseEntry.objects.filter(
            user=user,
            recorded_at__gte=today_start
        ).order_by('-recorded_at')
        context['today_entries'] = today_entries
        context['today_count'] = today_entries.count()

        # Latest reading (always from today or most recent)
        latest_reading = GlucoseEntry.objects.filter(user=user).order_by('-recorded_at').first()
        if latest_reading:
            context['latest_reading'] = latest_reading

        # Stats for the selected period
        if glucose_entries.exists():
            stats = glucose_entries.aggregate(
                avg=Avg('value'),
                min=Min('value'),
                max=Max('value'),
            )
            context['avg_glucose'] = round(stats['avg'], 1) if stats['avg'] else None
            context['min_glucose'] = stats['min']
            context['max_glucose'] = stats['max']

            # Time in range (70-180 mg/dL)
            total = glucose_entries.count()
            in_range = glucose_entries.filter(value__gte=70, value__lte=180).count()
            context['time_in_range'] = round((in_range / total) * 100, 1) if total > 0 else 0

            # Low/high counts
            context['low_count'] = glucose_entries.filter(value__lt=70).count()
            context['high_count'] = glucose_entries.filter(value__gt=180).count()

        # Prepare chart data based on selected period
        # Chart shows data for the same period as stats
        chart_entries = GlucoseEntry.objects.filter(
            user=user,
            recorded_at__gte=period_start
        ).order_by('recorded_at')

        chart_data = []

        # For periods > 7 days, aggregate to daily averages for readability
        if period > 7:
            # Group by date and calculate daily averages
            from collections import defaultdict
            daily_data = defaultdict(list)

            for entry in chart_entries:
                day_key = entry.recorded_at.date()
                daily_data[day_key].append(float(entry.value))

            # Sort by date and create averaged data points
            for day in sorted(daily_data.keys()):
                values = daily_data[day]
                avg_value = sum(values) / len(values)
                # Create a datetime at noon for the day
                day_datetime = timezone.make_aware(
                    timezone.datetime.combine(day, timezone.datetime.min.time().replace(hour=12))
                )
                chart_data.append({
                    'time': day_datetime.isoformat(),
                    'value': round(avg_value, 1),
                    'is_average': True,
                    'reading_count': len(values),
                })
            context['chart_aggregated'] = True
        else:
            # For shorter periods, show individual readings
            for entry in chart_entries:
                chart_data.append({
                    'time': entry.recorded_at.isoformat(),
                    'value': float(entry.value),
                    'trend': entry.trend,
                    'trend_arrow': entry.trend_arrow_display,
                    'source': entry.source,
                })
            context['chart_aggregated'] = False

        context['chart_data'] = chart_data

        # Generate AI insight if user has AI enabled and consented
        context['ai_insight'] = None
        context['ai_enabled'] = False
        try:
            prefs = user.preferences
            if prefs.ai_enabled and prefs.ai_data_consent:
                context['ai_enabled'] = True
                from apps.ai.services import ai_service

                # Build glucose data for AI
                glucose_data = {
                    'reading_count': glucose_entries.count(),
                    'avg_glucose': context.get('avg_glucose'),
                    'min_glucose': context.get('min_glucose'),
                    'max_glucose': context.get('max_glucose'),
                    'time_in_range': context.get('time_in_range'),
                    'low_count': context.get('low_count', 0),
                    'high_count': context.get('high_count', 0),
                }

                # Add latest reading info
                if context.get('latest_reading'):
                    latest = context['latest_reading']
                    glucose_data['latest_value'] = float(latest.value)
                    glucose_data['latest_status'] = latest.glucose_status

                # Generate insight with user's coaching style
                context['ai_insight'] = ai_service.generate_glucose_insight(
                    glucose_data,
                    faith_enabled=prefs.faith_enabled,
                    coaching_style=prefs.ai_coaching_style
                )
        except Exception:
            # Don't fail the page if AI fails
            pass

        return context


class GlucoseListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """
    List all glucose entries with pagination.
    """

    model = GlucoseEntry
    template_name = "health/glucose/list.html"
    context_object_name = "entries"
    paginate_by = 50
    help_context_id = "GLUCOSE_LIST"

    def get_queryset(self):
        return GlucoseEntry.objects.filter(
            user=self.request.user
        ).order_by('-recorded_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Filters
        source = self.request.GET.get('source')
        if source:
            context['source_filter'] = source

        return context


class GlucoseCreateView(HelpContextMixin, LoginRequiredMixin, CreateView):
    """
    Manually log a glucose reading.
    """

    model = GlucoseEntry
    form_class = GlucoseEntryForm
    template_name = "health/glucose/form.html"
    success_url = reverse_lazy("health:glucose_dashboard")
    help_context_id = "GLUCOSE_CREATE"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.source = 'manual'
        messages.success(self.request, "Glucose reading logged.")
        return super().form_valid(form)


class GlucoseUpdateView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """
    Edit a glucose entry.
    """

    model = GlucoseEntry
    form_class = GlucoseEntryForm
    template_name = "health/glucose/form.html"
    success_url = reverse_lazy("health:glucose_dashboard")
    help_context_id = "GLUCOSE_UPDATE"

    def get_queryset(self):
        return GlucoseEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Glucose reading updated.")
        return super().form_valid(form)


class GlucoseDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a glucose entry.
    Supports undo via toast notification for AJAX requests.
    """

    model = GlucoseEntry
    item_type = 'health.glucoseentry'
    item_name = 'glucose reading'
    success_url = 'health:glucose_dashboard'

    def get_object(self):
        return get_object_or_404(
            GlucoseEntry.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )

    def get_success_url(self):
        from django.urls import reverse
        # Stay on the same page if coming from list, otherwise go to dashboard
        referer = self.request.META.get("HTTP_REFERER", "")
        if "glucose/list" in referer:
            return reverse("health:glucose_list")
        return reverse("health:glucose_dashboard")


# =============================================================================
# BULK ACTION VIEWS
# =============================================================================


class BulkDeleteWeightView(LoginRequiredMixin, View):
    """
    Bulk delete weight entries.
    Accepts JSON body with 'ids' array.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = WeightEntry.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} weight entr{"y" if count == 1 else "ies"} deleted',
            'count': count,
            'item_type': 'health.weightentry',
        })


class BulkDeleteHeartRateView(LoginRequiredMixin, View):
    """
    Bulk delete heart rate entries.
    Accepts JSON body with 'ids' array.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = HeartRateEntry.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} heart rate entr{"y" if count == 1 else "ies"} deleted',
            'count': count,
            'item_type': 'health.heartrateentry',
        })


class BulkDeleteBloodPressureView(LoginRequiredMixin, View):
    """
    Bulk delete blood pressure entries.
    Accepts JSON body with 'ids' array.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = BloodPressureEntry.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} blood pressure reading{"" if count == 1 else "s"} deleted',
            'count': count,
            'item_type': 'health.bloodpressureentry',
        })


class BulkDeleteBloodOxygenView(LoginRequiredMixin, View):
    """
    Bulk delete blood oxygen entries.
    Accepts JSON body with 'ids' array.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = BloodOxygenEntry.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} blood oxygen reading{"" if count == 1 else "s"} deleted',
            'count': count,
            'item_type': 'health.bloodoxygenentry',
        })


class BulkDeleteGlucoseView(LoginRequiredMixin, View):
    """
    Bulk delete glucose entries.
    Accepts JSON body with 'ids' array.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = GlucoseEntry.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} glucose reading{"" if count == 1 else "s"} deleted',
            'count': count,
            'item_type': 'health.glucoseentry',
        })


class BulkDeleteFastingView(LoginRequiredMixin, View):
    """
    Bulk delete fasting entries.
    Accepts JSON body with 'ids' array.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = FastingWindow.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} fast{"" if count == 1 else "s"} deleted',
            'count': count,
            'item_type': 'health.fastingwindow',
        })


# =============================================================================
# Sleep Tracking Views
# =============================================================================


class SleepListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """
    List sleep entries with stats and trends.
    """

    model = SleepEntry
    template_name = "health/sleep_list.html"
    context_object_name = "entries"
    paginate_by = 30
    help_context_id = "HEALTH_SLEEP"

    def get_queryset(self):
        return SleepEntry.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = self.get_queryset()

        if entries.exists():
            context["latest"] = entries.first()
            context["total_count"] = entries.count()

            # Stats for past 7 days
            week_ago = timezone.now() - timedelta(days=7)
            week_entries = entries.filter(sleep_date__gte=week_ago.date())
            if week_entries.exists():
                # Calculate averages
                total_minutes = sum(e.total_duration_minutes or 0 for e in week_entries)
                context["week_avg_hours"] = round(total_minutes / week_entries.count() / 60, 1)
                context["week_count"] = week_entries.count()

                # Quality distribution
                quality_counts = {}
                for entry in week_entries:
                    if entry.quality_rating:
                        quality_counts[entry.quality_rating] = quality_counts.get(entry.quality_rating, 0) + 1
                context["quality_counts"] = quality_counts

                # Average quality score if available
                scores = [e.quality_score for e in week_entries if e.quality_score]
                if scores:
                    context["week_avg_score"] = round(sum(scores) / len(scores))

            # 30-day average
            month_ago = timezone.now() - timedelta(days=30)
            month_entries = entries.filter(sleep_date__gte=month_ago.date())
            if month_entries.exists():
                total_minutes = sum(e.total_duration_minutes or 0 for e in month_entries)
                context["month_avg_hours"] = round(total_minutes / month_entries.count() / 60, 1)

            # Chart data for last 14 days
            two_weeks_ago = timezone.now() - timedelta(days=14)
            chart_entries = list(entries.filter(
                sleep_date__gte=two_weeks_ago.date()
            ).order_by("sleep_date"))

            if chart_entries:
                context["chart_labels"] = json.dumps([
                    e.sleep_date.strftime("%m/%d") for e in chart_entries
                ])
                context["chart_data"] = json.dumps([
                    round(e.total_duration_minutes / 60, 1) if e.total_duration_minutes else 0
                    for e in chart_entries
                ])
                # Quality scores for chart (if available)
                context["chart_quality"] = json.dumps([
                    e.quality_score or 0 for e in chart_entries
                ])

            # Sleep stage averages (if data exists)
            stage_entries = [e for e in month_entries if e.has_stage_data]
            if stage_entries:
                context["has_stage_data"] = True
                context["avg_deep_pct"] = round(
                    sum(e.deep_sleep_percentage or 0 for e in stage_entries) / len(stage_entries), 1
                )
                context["avg_rem_pct"] = round(
                    sum(e.rem_percentage or 0 for e in stage_entries) / len(stage_entries), 1
                )

        return context


class SleepCreateView(SaveAddAnotherMixin, LoginRequiredMixin, CreateView):
    """
    Log a new sleep entry.
    """

    model = SleepEntry
    form_class = SleepEntryForm
    template_name = "health/sleep_form.html"
    success_url = reverse_lazy("health:sleep_list")
    save_add_another_message = "Sleep logged. Add another!"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        if 'save_add_another' not in self.request.POST:
            messages.success(self.request, "Sleep logged successfully.")
        return super().form_valid(form)


class SleepQuickCreateView(LoginRequiredMixin, CreateView):
    """
    Quick log sleep - simplified form.
    """

    model = SleepEntry
    form_class = QuickSleepForm
    template_name = "health/sleep_quick_form.html"
    success_url = reverse_lazy("health:sleep_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Sleep logged.")
        return super().form_valid(form)


class SleepUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edit a sleep entry.
    """

    model = SleepEntry
    form_class = SleepEntryForm
    template_name = "health/sleep_form.html"
    success_url = reverse_lazy("health:sleep_list")

    def get_queryset(self):
        return SleepEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Sleep entry updated.")
        return super().form_valid(form)


class SleepDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """
    Delete a sleep entry.
    Supports undo via toast notification for AJAX requests.
    """

    model = SleepEntry
    item_type = 'health.sleepentry'
    item_name = 'sleep entry'
    success_url = 'health:sleep_list'

    def get_object(self):
        return get_object_or_404(
            SleepEntry.objects.filter(user=self.request.user),
            pk=self.kwargs['pk']
        )


class BulkDeleteSleepView(LoginRequiredMixin, View):
    """
    Bulk delete sleep entries.
    Accepts JSON body with 'ids' array.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = SleepEntry.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} sleep entr{"y" if count == 1 else "ies"} deleted',
            'count': count,
            'item_type': 'health.sleepentry',
        })
