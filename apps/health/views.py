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

from .forms import (
    FastingWindowForm,
    GlucoseEntryForm,
    HeartRateEntryForm,
    QuickWeightForm,
    WeightEntryForm,
)
from .models import (
    CardioDetails,
    Exercise,
    ExerciseSet,
    FastingWindow,
    GlucoseEntry,
    HeartRateEntry,
    PersonalRecord,
    TemplateExercise,
    WeightEntry,
    WorkoutExercise,
    WorkoutSession,
    WorkoutTemplate,
)


class HealthHomeView(LoginRequiredMixin, TemplateView):
    """
    Health module home - overview of all health metrics.
    """

    template_name = "health/home.html"

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

        # Create workout session
        workout = WorkoutSession.objects.create(
            user=user,
            date=request.POST.get("date") or today,
            name=request.POST.get("name", ""),
            notes=request.POST.get("notes", ""),
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
