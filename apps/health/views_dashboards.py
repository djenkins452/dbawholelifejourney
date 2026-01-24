# views_dashboards.py
# Whole Life Journey - Health Module
#
# Dashboard views for all health metrics.
# Each dashboard extends HealthMetricDashboardMixin with metric-specific config.

from django.db.models import Avg

from apps.health.models import (
    BloodPressureEntry,
    BloodOxygenEntry,
)
from apps.health.views_base import HealthMetricDashboardMixin


class BloodPressureDashboardView(HealthMetricDashboardMixin):
    """
    Blood Pressure dashboard with systolic/diastolic display.

    Shows BP readings as systolic/diastolic with AHA category badges.
    """

    model = BloodPressureEntry
    template_name = "health/dashboards/blood_pressure_dashboard.html"
    metric_name = "Blood Pressure"
    metric_field = "systolic"
    feature_key = "blood_pressure"
    unit = "mmHg"
    chart_color = "#ef4444"  # Red for blood pressure
    list_url_name = "health:blood_pressure_list"
    create_url_name = "health:blood_pressure_create"
    update_url_name = "health:blood_pressure_update"

    def get_statistics(self, queryset):
        """Calculate BP-specific statistics with both systolic and diastolic."""
        stats = queryset.aggregate(
            systolic_avg=Avg('systolic'),
            diastolic_avg=Avg('diastolic'),
            pulse_avg=Avg('pulse'),
        )
        return {
            'systolic_avg': round(float(stats['systolic_avg']), 0) if stats['systolic_avg'] else None,
            'diastolic_avg': round(float(stats['diastolic_avg']), 0) if stats['diastolic_avg'] else None,
            'pulse_avg': round(float(stats['pulse_avg']), 0) if stats['pulse_avg'] else None,
            'count': queryset.count(),
        }

    def get_chart_value(self, entry):
        """Return systolic for chart (primary value)."""
        return float(entry.systolic) if entry.systolic else None

    def get_chart_entry_extras(self, entry):
        """Include diastolic and pulse in chart data."""
        return {
            'diastolic': entry.diastolic,
            'pulse': entry.pulse,
        }

    def get_status_for_value(self, value):
        """
        Get BP category based on AHA guidelines.
        Note: This only uses systolic; the template shows the full category.
        """
        # Use latest reading's category property instead
        latest = self.get_latest_reading()
        if latest:
            category = latest.category
            categories = {
                'normal': ('normal', 'Normal', 'green'),
                'elevated': ('elevated', 'Elevated', 'yellow'),
                'high_stage1': ('high_stage1', 'High (Stage 1)', 'orange'),
                'high_stage2': ('high_stage2', 'High (Stage 2)', 'red'),
                'crisis': ('crisis', 'Crisis', 'red'),
            }
            return categories.get(category, ('unknown', 'Unknown', 'gray'))
        return ('normal', 'Normal', 'green')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add latest reading formatted value
        if context.get('latest_reading'):
            context['latest_value'] = context['latest_reading'].reading

        return context


class BloodOxygenDashboardView(HealthMetricDashboardMixin):
    """
    Blood Oxygen (SpO2) dashboard.

    Shows oxygen saturation percentage with status badges.
    """

    model = BloodOxygenEntry
    template_name = "health/dashboards/blood_oxygen_dashboard.html"
    metric_name = "Blood Oxygen"
    metric_field = "spo2"
    feature_key = "blood_oxygen"
    unit = "%"
    chart_color = "#3b82f6"  # Blue for oxygen
    chart_min = 85
    chart_max = 100
    list_url_name = "health:blood_oxygen_list"
    create_url_name = "health:blood_oxygen_create"
    update_url_name = "health:blood_oxygen_update"

    def get_status_for_value(self, value):
        """Get SpO2 status category."""
        if value is None:
            return ('unknown', 'Unknown', 'gray')
        if value >= 95:
            return ('normal', 'Normal', 'green')
        elif value >= 90:
            return ('low', 'Low', 'yellow')
        elif value >= 85:
            return ('concerning', 'Concerning', 'orange')
        else:
            return ('critical', 'Critical', 'red')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add latest reading formatted value
        if context.get('latest_reading'):
            context['latest_value'] = context['latest_reading'].spo2

        return context
