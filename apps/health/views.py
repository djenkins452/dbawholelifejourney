"""
Health Views - Physical wellness tracking.
"""

import pytz
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Max, Min
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
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

from apps.core.utils import get_user_today
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
    MedicineLogForm,
    MedicineScheduleForm,
    PRNDoseForm,
    QuickWeightForm,
    UpdateSupplyForm,
    WeightEntryForm,
)
from .models import (
    BloodOxygenEntry,
    BloodPressureEntry,
    CardioDetails,
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
    TemplateExercise,
    WeightEntry,
    WorkoutExercise,
    WorkoutSession,
    WorkoutTemplate,
)


class HealthHomeView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Health module home - overview of all health metrics.
    """

    template_name = "health/home.html"
    help_context_id = "HEALTH_HOME"

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

                            # Get user's timezone
                            try:
                                user_tz = pytz.timezone(user.preferences.timezone or 'UTC')
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

        return context


# Weight Views

class WeightListView(LoginRequiredMixin, ListView):
    """
    List weight entries with stats.
    """

    model = WeightEntry
    template_name = "health/weight_list.html"
    context_object_name = "entries"
    paginate_by = 30

    def get_queryset(self):
        return WeightEntry.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = self.get_queryset()
        
        if entries.exists():
            context["latest"] = entries.first()
            context["total_count"] = entries.count()
            
            # Stats
            values = [e.value_in_lb for e in entries[:30]]  # Last 30 entries
            if values:
                context["min_weight"] = min(values)
                context["max_weight"] = max(values)
                context["avg_weight"] = round(sum(values) / len(values), 1)
        
        return context


class WeightCreateView(LoginRequiredMixin, CreateView):
    """
    Log a new weight entry.
    """

    model = WeightEntry
    form_class = WeightEntryForm
    template_name = "health/weight_form.html"
    success_url = reverse_lazy("health:weight_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Weight logged.")
        return super().form_valid(form)


class WeightUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edit a weight entry.
    """

    model = WeightEntry
    form_class = WeightEntryForm
    template_name = "health/weight_form.html"
    success_url = reverse_lazy("health:weight_list")

    def get_queryset(self):
        return WeightEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class WeightDeleteView(LoginRequiredMixin, View):
    """
    Delete a weight entry.
    """

    def post(self, request, pk):
        entry = get_object_or_404(
            WeightEntry.objects.filter(user=request.user),
            pk=pk
        )
        entry.soft_delete()
        messages.success(request, "Weight entry deleted.")
        return redirect("health:weight_list")


# Fasting Views

class FastingListView(LoginRequiredMixin, ListView):
    """
    List fasting windows.
    """

    model = FastingWindow
    template_name = "health/fasting_list.html"
    context_object_name = "fasts"
    paginate_by = 20

    def get_queryset(self):
        return FastingWindow.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_fast"] = FastingWindow.objects.filter(
            user=self.request.user,
            ended_at__isnull=True,
        ).first()
        # Get user's timezone for template display
        try:
            tz_name = self.request.user.preferences.timezone or "UTC"
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


class FastingDeleteView(LoginRequiredMixin, View):
    """
    Delete a fasting window.
    """

    def post(self, request, pk):
        fast = get_object_or_404(
            FastingWindow.objects.filter(user=request.user),
            pk=pk
        )
        fast.soft_delete()
        messages.success(request, "Fasting window deleted.")
        return redirect("health:fasting_list")


# Heart Rate Views

class HeartRateListView(LoginRequiredMixin, ListView):
    """
    List heart rate entries.
    """

    model = HeartRateEntry
    template_name = "health/heartrate_list.html"
    context_object_name = "entries"
    paginate_by = 30

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


class HeartRateCreateView(LoginRequiredMixin, CreateView):
    """
    Log a new heart rate entry.
    """

    model = HeartRateEntry
    form_class = HeartRateEntryForm
    template_name = "health/heartrate_form.html"
    success_url = reverse_lazy("health:heartrate_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Heart rate logged.")
        return super().form_valid(form)


class HeartRateUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edit a heart rate entry.
    """

    model = HeartRateEntry
    form_class = HeartRateEntryForm
    template_name = "health/heartrate_form.html"
    success_url = reverse_lazy("health:heartrate_list")

    def get_queryset(self):
        return HeartRateEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class HeartRateDeleteView(LoginRequiredMixin, View):
    """
    Delete a heart rate entry.
    """

    def post(self, request, pk):
        entry = get_object_or_404(
            HeartRateEntry.objects.filter(user=request.user),
            pk=pk
        )
        entry.soft_delete()
        messages.success(request, "Heart rate entry deleted.")
        return redirect("health:heartrate_list")


# Glucose Views

class GlucoseListView(LoginRequiredMixin, ListView):
    """
    List glucose entries.
    """

    model = GlucoseEntry
    template_name = "health/glucose_list.html"
    context_object_name = "entries"
    paginate_by = 30

    def get_queryset(self):
        return GlucoseEntry.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = self.get_queryset()
        
        if entries.exists():
            context["latest"] = entries.first()
            
            # Fasting glucose stats
            fasting = entries.filter(context="fasting")
            if fasting.exists():
                stats = fasting.aggregate(
                    avg=Avg("value"),
                    min=Min("value"),
                    max=Max("value"),
                )
                context["fasting_avg"] = round(stats["avg"], 1)
                context["fasting_min"] = stats["min"]
                context["fasting_max"] = stats["max"]
        
        return context


class GlucoseCreateView(LoginRequiredMixin, CreateView):
    """
    Log a new glucose entry.
    """

    model = GlucoseEntry
    form_class = GlucoseEntryForm
    template_name = "health/glucose_form.html"
    success_url = reverse_lazy("health:glucose_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Glucose logged.")
        return super().form_valid(form)


class GlucoseUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edit a glucose entry.
    """

    model = GlucoseEntry
    form_class = GlucoseEntryForm
    template_name = "health/glucose_form.html"
    success_url = reverse_lazy("health:glucose_list")

    def get_queryset(self):
        return GlucoseEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class GlucoseDeleteView(LoginRequiredMixin, View):
    """
    Delete a glucose entry.
    """

    def post(self, request, pk):
        entry = get_object_or_404(
            GlucoseEntry.objects.filter(user=request.user),
            pk=pk
        )
        entry.soft_delete()
        messages.success(request, "Glucose entry deleted.")
        return redirect("health:glucose_list")


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


class FitnessHomeView(LoginRequiredMixin, TemplateView):
    """
    Fitness module home - overview of workouts and progress.
    """

    template_name = "health/fitness/home.html"

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

        # User's templates for quick start
        context["templates"] = WorkoutTemplate.objects.filter(user=user)

        # Check if starting from a template
        template_id = self.request.GET.get("template")
        if template_id:
            try:
                template = WorkoutTemplate.objects.get(pk=template_id, user=user)
                context["from_template"] = template
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

        # Create workout session
        workout = WorkoutSession.objects.create(
            user=user,
            date=request.POST.get("date") or today,
            name=request.POST.get("name", ""),
            notes=request.POST.get("notes", ""),
            created_via=created_via,
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
        ).prefetch_related("sets", "cardio_details")
        context["date"] = workout.date
        context["editing"] = True

        # Get exercises grouped by category
        context["resistance_exercises"] = Exercise.objects.filter(
            category="resistance", is_active=True
        ).order_by("muscle_group", "name")
        context["cardio_exercises"] = Exercise.objects.filter(
            category="cardio", is_active=True
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

            except Exercise.DoesNotExist:
                continue

        messages.success(request, "Workout updated!")
        return redirect("health:workout_detail", pk=workout.pk)


class WorkoutDeleteView(LoginRequiredMixin, View):
    """
    Delete a workout session.
    """

    def post(self, request, pk):
        workout = get_object_or_404(
            WorkoutSession.objects.filter(user=request.user),
            pk=pk,
        )
        workout.soft_delete()
        messages.success(request, "Workout deleted.")
        return redirect("health:fitness_home")


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
                TemplateExercise.objects.create(
                    template=template,
                    exercise=exercise,
                    order=idx,
                    default_sets=int(default_sets) if default_sets else 3,
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
        )
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
        )
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

        # Clear and recreate exercises
        template.template_exercises.all().delete()

        exercise_ids = request.POST.getlist("exercise_id")
        for idx, exercise_id in enumerate(exercise_ids):
            try:
                exercise = Exercise.objects.get(pk=exercise_id)
                default_sets = request.POST.get(
                    f"exercise_{exercise_id}_default_sets", 3
                )
                TemplateExercise.objects.create(
                    template=template,
                    exercise=exercise,
                    order=idx,
                    default_sets=int(default_sets) if default_sets else 3,
                )
            except Exercise.DoesNotExist:
                continue

        messages.success(request, f"Template '{template.name}' updated!")
        return redirect("health:template_detail", pk=template.pk)


class TemplateDeleteView(LoginRequiredMixin, View):
    """
    Delete a workout template.
    """

    def post(self, request, pk):
        template = get_object_or_404(
            WorkoutTemplate.objects.filter(user=request.user),
            pk=pk,
        )
        name = template.name
        template.soft_delete()
        messages.success(request, f"Template '{name}' deleted.")
        return redirect("health:template_list")


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
    if template_id:
        try:
            template = WorkoutTemplate.objects.get(pk=template_id, user=user)
            template_name = template.name
        except WorkoutTemplate.DoesNotExist:
            pass

    workout = WorkoutSession.objects.create(
        user=user,
        date=data.get("date") or today,
        name=data.get("name") or template_name,
        started_at=timezone.now(),
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

    return JsonResponse({
        "success": True,
        "message": "Workout completed!",
        "redirect_url": f"/health/fitness/workout/{workout.pk}/",
    })


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

        # Sort by time
        today_schedules.sort(key=lambda x: x["schedule"].scheduled_time)
        context["today_schedules"] = today_schedules

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

        # Get user's timezone
        user = self.request.user
        try:
            user_tz = pytz.timezone(user.preferences.timezone or 'UTC')
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
        """Pre-populate form from query parameters (for AI Camera scan)."""
        initial = super().get_initial()
        # Support prefill from Camera Scan feature
        if self.request.GET.get('name'):
            initial['name'] = self.request.GET.get('name')
        if self.request.GET.get('dose'):
            initial['dose'] = self.request.GET.get('dose')
        if self.request.GET.get('purpose'):
            initial['purpose'] = self.request.GET.get('purpose')
        if self.request.GET.get('directions'):
            # Directions can go into notes or be displayed separately
            initial['notes'] = self.request.GET.get('directions')
        if self.request.GET.get('quantity'):
            # Try to extract supply count from quantity like "30 tablets"
            quantity = self.request.GET.get('quantity', '')
            if quantity:
                import re
                match = re.match(r'^(\d+)', quantity)
                if match:
                    initial['current_supply'] = int(match.group(1))
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user

        # Track if created via AI Camera scan
        source = self.request.GET.get('source')
        if source == 'ai_camera':
            from apps.core.models import UserOwnedModel
            form.instance.created_via = UserOwnedModel.CREATED_VIA_AI_CAMERA

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


class MedicineDeleteView(LoginRequiredMixin, View):
    """
    Delete a medicine.
    """

    def post(self, request, pk):
        medicine = get_object_or_404(
            Medicine.objects.filter(user=request.user),
            pk=pk,
        )
        name = medicine.name
        medicine.soft_delete()
        messages.success(request, f"Deleted {name}.")
        return redirect("health:medicine_list")


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

        # Mark as taken
        log.mark_taken()

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
            log = MedicineLog.objects.create(
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


class MedicineHistoryView(LoginRequiredMixin, ListView):
    """
    View medicine log history.
    """

    model = MedicineLog
    template_name = "health/medicine/history.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        queryset = MedicineLog.objects.filter(user=self.request.user)

        # Filter by medicine if specified
        medicine_id = self.request.GET.get("medicine")
        if medicine_id:
            queryset = queryset.filter(medicine_id=medicine_id)

        # Filter by date range
        start_date = self.request.GET.get("start")
        end_date = self.request.GET.get("end")
        if start_date:
            queryset = queryset.filter(scheduled_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(scheduled_date__lte=end_date)

        return queryset.select_related("medicine", "schedule")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["medicines"] = Medicine.objects.filter(user=self.request.user)
        context["selected_medicine"] = self.request.GET.get("medicine")
        return context


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
        context["breakfast_entries"] = today_entries.filter(meal_type=FoodEntry.MEAL_BREAKFAST)
        context["lunch_entries"] = today_entries.filter(meal_type=FoodEntry.MEAL_LUNCH)
        context["dinner_entries"] = today_entries.filter(meal_type=FoodEntry.MEAL_DINNER)
        context["snack_entries"] = today_entries.filter(meal_type=FoodEntry.MEAL_SNACK)

        # Calculate today's totals
        from django.db.models import Sum
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


class FoodEntryCreateView(HelpContextMixin, LoginRequiredMixin, CreateView):
    """
    Log a new food entry.
    """

    model = FoodEntry
    form_class = FoodEntryForm
    template_name = "health/nutrition/food_entry_form.html"
    success_url = reverse_lazy("health:nutrition_home")
    help_context_id = "NUTRITION_ENTRY_CREATE"

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


class FoodEntryDeleteView(LoginRequiredMixin, View):
    """
    Delete a food entry.
    """

    def post(self, request, pk):
        entry = get_object_or_404(
            FoodEntry.objects.filter(user=request.user),
            pk=pk,
        )
        entry.soft_delete()
        messages.success(request, "Food entry deleted.")

        # Redirect back to referring page or nutrition home
        next_url = request.POST.get('next', request.META.get('HTTP_REFERER'))
        if next_url:
            return redirect(next_url)
        return redirect("health:nutrition_home")


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
        from django.db.models import Sum, Avg
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


class CustomFoodDeleteView(LoginRequiredMixin, View):
    """
    Delete a custom food.
    """

    def post(self, request, pk):
        food = get_object_or_404(
            CustomFood.objects.filter(user=request.user),
            pk=pk,
        )
        food.soft_delete()
        messages.success(request, f"Deleted '{food.name}'.")
        return redirect("health:custom_food_list")


# =============================================================================
# Blood Pressure Views
# =============================================================================


class BloodPressureListView(LoginRequiredMixin, ListView):
    """
    List blood pressure entries.
    """

    model = BloodPressureEntry
    template_name = "health/blood_pressure_list.html"
    context_object_name = "entries"
    paginate_by = 30

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


class BloodPressureCreateView(LoginRequiredMixin, CreateView):
    """
    Log a new blood pressure entry.
    """

    model = BloodPressureEntry
    form_class = BloodPressureEntryForm
    template_name = "health/blood_pressure_form.html"
    success_url = reverse_lazy("health:blood_pressure_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Blood pressure logged.")
        return super().form_valid(form)


class BloodPressureUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edit a blood pressure entry.
    """

    model = BloodPressureEntry
    form_class = BloodPressureEntryForm
    template_name = "health/blood_pressure_form.html"
    success_url = reverse_lazy("health:blood_pressure_list")

    def get_queryset(self):
        return BloodPressureEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class BloodPressureDeleteView(LoginRequiredMixin, View):
    """
    Delete a blood pressure entry.
    """

    def post(self, request, pk):
        entry = get_object_or_404(
            BloodPressureEntry.objects.filter(user=request.user),
            pk=pk
        )
        entry.soft_delete()
        messages.success(request, "Blood pressure entry deleted.")
        return redirect("health:blood_pressure_list")


# =============================================================================
# Blood Oxygen Views
# =============================================================================


class BloodOxygenListView(LoginRequiredMixin, ListView):
    """
    List blood oxygen (SpO2) entries.
    """

    model = BloodOxygenEntry
    template_name = "health/blood_oxygen_list.html"
    context_object_name = "entries"
    paginate_by = 30

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


class BloodOxygenCreateView(LoginRequiredMixin, CreateView):
    """
    Log a new blood oxygen (SpO2) entry.
    """

    model = BloodOxygenEntry
    form_class = BloodOxygenEntryForm
    template_name = "health/blood_oxygen_form.html"
    success_url = reverse_lazy("health:blood_oxygen_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Blood oxygen logged.")
        return super().form_valid(form)


class BloodOxygenUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edit a blood oxygen entry.
    """

    model = BloodOxygenEntry
    form_class = BloodOxygenEntryForm
    template_name = "health/blood_oxygen_form.html"
    success_url = reverse_lazy("health:blood_oxygen_list")

    def get_queryset(self):
        return BloodOxygenEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class BloodOxygenDeleteView(LoginRequiredMixin, View):
    """
    Delete a blood oxygen entry.
    """

    def post(self, request, pk):
        entry = get_object_or_404(
            BloodOxygenEntry.objects.filter(user=request.user),
            pk=pk
        )
        entry.soft_delete()
        messages.success(request, "Blood oxygen entry deleted.")
        return redirect("health:blood_oxygen_list")


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


class MedicalProviderDeleteView(LoginRequiredMixin, View):
    """
    Delete a medical provider (and all associated staff via CASCADE).
    """

    def post(self, request, pk):
        from .models import MedicalProvider
        provider = get_object_or_404(
            MedicalProvider.objects.filter(user=request.user),
            pk=pk,
        )
        provider_name = provider.name
        provider.soft_delete()
        messages.success(request, f"Deleted provider: {provider_name}")
        return redirect("health:provider_list")


class ProviderAILookupView(LoginRequiredMixin, View):
    """
    AI-powered lookup of provider contact information.
    Uses OpenAI to search for provider details based on name and location.
    """

    def post(self, request):
        import json
        from django.conf import settings
        from .models import MedicalProvider

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


class ProviderStaffDeleteView(LoginRequiredMixin, View):
    """
    Delete a staff member.
    """

    def post(self, request, pk):
        from .models import ProviderStaff
        staff = get_object_or_404(
            ProviderStaff.objects.filter(user=request.user),
            pk=pk,
        )
        provider_pk = staff.provider.pk
        staff_name = staff.name
        staff.soft_delete()
        messages.success(request, f"Removed staff member: {staff_name}")
        return redirect("health:provider_detail", pk=provider_pk)
