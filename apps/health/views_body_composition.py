"""
Body Composition & Health Profile Views.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View

from apps.core.views import SaveAddAnotherMixin, UndoDeleteMixin
from apps.help.mixins import HelpContextMixin

from .forms import BodyCompositionEntryForm, HealthProfileForm
from .models import (
    BODY_COMPOSITION_METRIC_CHOICES,
    BodyCompositionEntry,
    HealthProfile,
)


class BodyCompositionListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """List body composition entries with stats."""

    model = BodyCompositionEntry
    template_name = "health/body_composition_list.html"
    context_object_name = "entries"
    paginate_by = 30
    help_context_id = "HEALTH_BODY_COMPOSITION"

    def get_queryset(self):
        qs = BodyCompositionEntry.objects.filter(user=self.request.user)
        metric_filter = self.request.GET.get("metric")
        if metric_filter:
            qs = qs.filter(metric_name=metric_filter)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_entries = BodyCompositionEntry.objects.filter(user=self.request.user)
        context["total_count"] = all_entries.count()
        context["metric_filter"] = self.request.GET.get("metric", "")
        context["metric_choices"] = BODY_COMPOSITION_METRIC_CHOICES

        # Get distinct metrics the user has logged
        context["user_metrics"] = (
            all_entries.values_list("metric_name", flat=True)
            .distinct()
            .order_by("metric_name")
        )

        # Latest value per metric (for stats)
        metrics_summary = []
        for metric_name in context["user_metrics"]:
            latest = all_entries.filter(metric_name=metric_name).first()
            if latest:
                metrics_summary.append({
                    "name": latest.get_metric_display(),
                    "value": latest.value,
                    "unit": latest.unit,
                    "date": latest.measurement_date,
                    "metric_name": metric_name,
                })
        context["metrics_summary"] = metrics_summary[:8]  # Top 8 for stats bar
        return context


class BodyCompositionCreateView(
    HelpContextMixin, SaveAddAnotherMixin, LoginRequiredMixin, CreateView
):
    """Log a new body composition measurement."""

    model = BodyCompositionEntry
    form_class = BodyCompositionEntryForm
    template_name = "health/body_composition_form.html"
    success_url = reverse_lazy("health:body_composition_list")
    save_add_another_message = "Measurement logged. Add another!"
    help_context_id = "HEALTH_BODY_COMPOSITION"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        if "save_add_another" not in self.request.POST:
            messages.success(self.request, "Measurement logged.")
        return super().form_valid(form)


class BodyCompositionUpdateView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """Edit a body composition entry."""

    model = BodyCompositionEntry
    form_class = BodyCompositionEntryForm
    template_name = "health/body_composition_form.html"
    success_url = reverse_lazy("health:body_composition_list")
    help_context_id = "HEALTH_BODY_COMPOSITION"

    def get_queryset(self):
        return BodyCompositionEntry.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class BodyCompositionDeleteView(LoginRequiredMixin, UndoDeleteMixin, View):
    """Delete a body composition entry (soft delete with undo)."""

    model = BodyCompositionEntry
    item_type = "health.bodycompositionentry"
    item_name = "body composition entry"
    success_url = "health:body_composition_list"

    def get_object(self):
        return get_object_or_404(
            BodyCompositionEntry.objects.filter(user=self.request.user),
            pk=self.kwargs["pk"],
        )


class HealthProfileView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """Edit health profile (height + activity level)."""

    model = HealthProfile
    form_class = HealthProfileForm
    template_name = "health/health_profile_form.html"
    success_url = reverse_lazy("health:home")
    help_context_id = "HEALTH_PROFILE"

    def get_object(self, queryset=None):
        profile, _ = HealthProfile.objects.get_or_create(user=self.request.user)
        return profile

    def form_valid(self, form):
        messages.success(self.request, "Health profile updated.")
        return super().form_valid(form)
