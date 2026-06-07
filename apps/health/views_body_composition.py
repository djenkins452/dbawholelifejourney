"""
Body Composition & Health Profile Views.
"""

import csv
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, UpdateView, View

from apps.core.views import SaveAddAnotherMixin, UndoDeleteMixin
from apps.help.mixins import HelpContextMixin

from .forms import BodyCompositionEntryForm, HealthProfileForm
from .models import (
    BODY_COMPOSITION_METRIC_CHOICES,
    BodyCompositionEntry,
    HealthProfile,
)
from .services.body_composition_snapshot import METRIC_LABELS


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


class BodyCompositionExportView(LoginRequiredMixin, View):
    """Export body composition entries as CSV or Excel.

    Query params:
        format:    'csv' (default) or 'xlsx'
        from_date: ISO date — inclusive lower bound (optional)
        to_date:   ISO date — inclusive upper bound (optional)

    When no date range is supplied, exports ALL entries. Read-only.
    Soft-deleted rows are excluded by the default SoftDeleteManager
    (the BodyCompositionEntry queryset already excludes status="deleted"
    in production paths).

    Columns: Date, Metric, Value, Unit, Source, Notes — plus optional
    Previous Value / Difference / Percent Change. Order is fixed.
    """

    COLUMNS = [
        "Date", "Metric", "Value", "Unit", "Source", "Notes",
        "Previous Value", "Difference", "Percent Change",
    ]

    def _parse_date(self, raw):
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    def _build_rows(self, user, from_date, to_date):
        """Return list[dict] in column order. Deterministic."""
        qs = BodyCompositionEntry.objects.filter(user=user)
        if from_date is not None:
            qs = qs.filter(measurement_date__gte=from_date)
        if to_date is not None:
            qs = qs.filter(measurement_date__lte=to_date)
        # Group by metric to compute Previous Value / Difference /
        # Percent Change row-by-row. We iterate in chronological order so
        # the "previous" reference is the most recent earlier value for
        # that same metric.
        entries = list(qs.order_by("measurement_date", "created_at"))
        last_per_metric = {}
        rows = []
        for e in entries:
            metric_label = METRIC_LABELS.get(e.metric_name, e.metric_name)
            prior = last_per_metric.get(e.metric_name)
            if prior is not None:
                diff = float(e.value) - float(prior)
                pct = (
                    round((diff / float(prior)) * 100, 1)
                    if float(prior) != 0 else ""
                )
                prior_val = float(prior)
            else:
                diff = ""
                pct = ""
                prior_val = ""
            rows.append({
                "Date": e.measurement_date.isoformat(),
                "Metric": metric_label,
                "Value": float(e.value),
                "Unit": e.unit,
                "Source": e.get_source_display() if e.source else "",
                "Notes": (e.notes or "").replace("\n", " ").strip(),
                "Previous Value": prior_val,
                "Difference": diff if diff == "" else round(diff, 2),
                "Percent Change": pct,
            })
            last_per_metric[e.metric_name] = e.value
        return rows

    def _filename_stem(self, from_date, to_date):
        today = timezone.now().date().isoformat()
        if from_date and to_date:
            return f"body-composition-{from_date}-to-{to_date}"
        if from_date:
            return f"body-composition-from-{from_date}"
        if to_date:
            return f"body-composition-through-{to_date}"
        return f"body-composition-{today}"

    def get(self, request, *args, **kwargs):
        fmt = (request.GET.get("format") or "csv").lower()
        from_date = self._parse_date(request.GET.get("from_date"))
        to_date = self._parse_date(request.GET.get("to_date"))

        rows = self._build_rows(request.user, from_date, to_date)
        stem = self._filename_stem(from_date, to_date)

        if fmt in ("xlsx", "excel"):
            return self._respond_xlsx(rows, stem)
        return self._respond_csv(rows, stem)

    def _respond_csv(self, rows, stem):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="{stem}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(self.COLUMNS)
        for r in rows:
            writer.writerow([r[col] for col in self.COLUMNS])
        return response

    def _respond_xlsx(self, rows, stem):
        """Best-effort Excel export. Falls back to CSV when openpyxl
        is unavailable so the export button never errors out."""
        try:
            from openpyxl import Workbook
        except ImportError:
            # Graceful degradation — exact same data, .csv extension.
            return self._respond_csv(rows, stem)
        wb = Workbook()
        ws = wb.active
        ws.title = "Body Composition"
        ws.append(self.COLUMNS)
        for r in rows:
            ws.append([r[col] for col in self.COLUMNS])
        from io import BytesIO
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        response = HttpResponse(
            buf.read(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{stem}.xlsx"'
        )
        return response


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
