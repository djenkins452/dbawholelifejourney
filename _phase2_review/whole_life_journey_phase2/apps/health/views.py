"""
Health Views - Physical wellness tracking.
"""

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

from .forms import (
    FastingWindowForm,
    GlucoseEntryForm,
    HeartRateEntryForm,
    QuickWeightForm,
    WeightEntryForm,
)
from .models import FastingWindow, GlucoseEntry, HeartRateEntry, WeightEntry


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
        return context


class StartFastView(LoginRequiredMixin, CreateView):
    """
    Start a new fasting window.
    """

    model = FastingWindow
    form_class = FastingWindowForm
    template_name = "health/fasting_form.html"
    success_url = reverse_lazy("health:fasting_list")

    def get_initial(self):
        initial = super().get_initial()
        initial["started_at"] = timezone.now()
        return initial

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
