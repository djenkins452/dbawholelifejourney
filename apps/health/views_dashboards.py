# views_dashboards.py
# Whole Life Journey - Health Module
#
# Dashboard views for all health metrics.
# Each dashboard extends HealthMetricDashboardMixin with metric-specific config.

from django.db.models import Avg, Sum

from apps.health.models import (
    BloodPressureEntry,
    BloodOxygenEntry,
    HeartRateEntry,
    BodyTemperatureEntry,
    StepsEntry,
)
from apps.health.views_base import (
    HealthMetricDashboardMixin,
    SleepDerivedMetricDashboardMixin,
)


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


class HeartRateDashboardView(HealthMetricDashboardMixin):
    """
    Heart Rate dashboard.

    Shows heart rate readings in BPM with context-aware status badges.
    """

    model = HeartRateEntry
    template_name = "health/dashboards/heart_rate_dashboard.html"
    metric_name = "Heart Rate"
    metric_field = "bpm"
    feature_key = "heart_rate"
    unit = "bpm"
    chart_color = "#ef4444"  # Red for heart
    chart_min = 40
    chart_max = 180
    list_url_name = "health:heartrate_list"
    create_url_name = "health:heartrate_create"
    update_url_name = "health:heartrate_update"

    def get_status_for_value(self, value):
        """Get heart rate status category (resting context assumed)."""
        if value is None:
            return ('unknown', 'Unknown', 'gray')
        # Normal resting HR: 60-100 bpm
        if 60 <= value <= 100:
            return ('normal', 'Normal', 'green')
        elif 50 <= value < 60 or 100 < value <= 110:
            return ('athlete', 'Athletic' if value < 60 else 'Elevated', 'yellow')
        elif value < 50:
            return ('low', 'Low', 'orange')
        else:
            return ('high', 'High', 'red')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if context.get('latest_reading'):
            context['latest_value'] = context['latest_reading'].bpm

        return context


class HRVDashboardView(SleepDerivedMetricDashboardMixin):
    """
    Heart Rate Variability (HRV) dashboard.

    HRV is stored on SleepEntry as hrv_value (SDNN in milliseconds).
    Higher HRV generally indicates better recovery and fitness.
    """

    template_name = "health/dashboards/hrv_dashboard.html"
    metric_name = "Heart Rate Variability"
    metric_field = "hrv_value"
    feature_key = "heart_rate"  # Uses heart rate feature toggle
    unit = "ms"
    chart_color = "#8b5cf6"  # Purple for HRV
    chart_min = 0
    chart_max = 200
    list_url_name = "health:sleep_list"  # HRV is part of sleep data
    create_url_name = "health:sleep_create"

    def get_status_for_value(self, value):
        """Get HRV status category."""
        if value is None:
            return ('unknown', 'Unknown', 'gray')
        # HRV varies widely by age; these are general guidelines
        if value >= 50:
            return ('excellent', 'Excellent', 'green')
        elif value >= 30:
            return ('good', 'Good', 'green')
        elif value >= 20:
            return ('fair', 'Fair', 'yellow')
        else:
            return ('low', 'Low', 'orange')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if context.get('latest_reading'):
            context['latest_value'] = context['latest_reading'].hrv_value

        return context


class VO2MaxDashboardView(SleepDerivedMetricDashboardMixin):
    """
    VO2 Max dashboard.

    VO2 Max is stored on SleepEntry as vo2_max (mL/kg/min).
    Higher values indicate better cardiovascular fitness.
    """

    template_name = "health/dashboards/vo2_max_dashboard.html"
    metric_name = "VO2 Max"
    metric_field = "vo2_max"
    feature_key = "heart_rate"  # Uses heart rate feature toggle
    unit = "mL/kg/min"
    chart_color = "#10b981"  # Green for fitness
    chart_min = 15
    chart_max = 60
    list_url_name = "health:sleep_list"
    create_url_name = "health:sleep_create"

    def get_status_for_value(self, value):
        """Get VO2 Max fitness level (general adult categories)."""
        if value is None:
            return ('unknown', 'Unknown', 'gray')
        # Simplified fitness categories
        if value >= 45:
            return ('excellent', 'Excellent', 'green')
        elif value >= 35:
            return ('good', 'Good', 'green')
        elif value >= 25:
            return ('average', 'Average', 'yellow')
        else:
            return ('below_average', 'Below Average', 'orange')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if context.get('latest_reading'):
            context['latest_value'] = context['latest_reading'].vo2_max

        return context


class RespiratoryRateDashboardView(SleepDerivedMetricDashboardMixin):
    """
    Respiratory Rate dashboard.

    Respiratory rate is stored on SleepEntry (breaths per minute during sleep).
    Normal adult range is 12-20 breaths per minute.
    """

    template_name = "health/dashboards/respiratory_rate_dashboard.html"
    metric_name = "Respiratory Rate"
    metric_field = "respiratory_rate"
    feature_key = "heart_rate"  # Uses heart rate feature toggle
    unit = "brpm"
    chart_color = "#06b6d4"  # Cyan for breathing
    chart_min = 8
    chart_max = 30
    list_url_name = "health:sleep_list"
    create_url_name = "health:sleep_create"

    def get_status_for_value(self, value):
        """Get respiratory rate status."""
        if value is None:
            return ('unknown', 'Unknown', 'gray')
        # Normal sleeping respiratory rate
        if 12 <= value <= 20:
            return ('normal', 'Normal', 'green')
        elif 10 <= value < 12 or 20 < value <= 24:
            return ('borderline', 'Borderline', 'yellow')
        else:
            return ('abnormal', 'Abnormal', 'orange')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if context.get('latest_reading'):
            context['latest_value'] = context['latest_reading'].respiratory_rate

        return context


class BodyTemperatureDashboardView(HealthMetricDashboardMixin):
    """
    Body Temperature dashboard.

    Shows temperature readings with fever status badges.
    """

    model = BodyTemperatureEntry
    template_name = "health/dashboards/body_temperature_dashboard.html"
    metric_name = "Body Temperature"
    metric_field = "temperature"
    feature_key = "blood_oxygen"  # Uses blood oxygen feature toggle (vitals)
    unit = "°F"
    chart_color = "#f97316"  # Orange for temperature
    chart_min = 95
    chart_max = 105
    list_url_name = ""  # No list view yet
    create_url_name = ""
    update_url_name = ""

    def get_chart_value(self, entry):
        """Return temperature in Fahrenheit for consistent charting."""
        return float(entry.temperature_fahrenheit) if entry.temperature_fahrenheit else None

    def get_status_for_value(self, value):
        """Get temperature status category (Fahrenheit)."""
        if value is None:
            return ('unknown', 'Unknown', 'gray')
        # Status based on oral temperature in Fahrenheit
        if value < 97.0:
            return ('low', 'Low', 'blue')
        elif 97.0 <= value <= 99.0:
            return ('normal', 'Normal', 'green')
        elif 99.0 < value <= 100.4:
            return ('elevated', 'Elevated', 'yellow')
        elif 100.4 < value <= 103.0:
            return ('fever', 'Fever', 'orange')
        else:
            return ('high_fever', 'High Fever', 'red')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if context.get('latest_reading'):
            entry = context['latest_reading']
            # Show in user's preferred unit (default Fahrenheit)
            context['latest_value'] = entry.temperature_fahrenheit
            context['latest_celsius'] = entry.temperature_celsius
            context['latest_context'] = entry.get_context_display()

        return context


class CaffeineDashboardView(SleepDerivedMetricDashboardMixin):
    """
    Caffeine intake dashboard.

    Caffeine is stored on SleepEntry as caffeine_mg (milligrams).
    Tracks daily caffeine consumption synced from HealthKit.
    """

    template_name = "health/dashboards/caffeine_dashboard.html"
    metric_name = "Caffeine"
    metric_field = "caffeine_mg"
    feature_key = "sleep"  # Uses sleep feature toggle
    unit = "mg"
    chart_color = "#92400e"  # Brown for coffee
    chart_min = 0
    chart_max = 600
    list_url_name = "health:sleep_list"
    create_url_name = "health:sleep_create"

    def get_status_for_value(self, value):
        """Get caffeine intake status."""
        if value is None:
            return ('unknown', 'Unknown', 'gray')
        # FDA recommends max 400mg/day for healthy adults
        if value <= 200:
            return ('moderate', 'Moderate', 'green')
        elif value <= 400:
            return ('typical', 'Typical', 'yellow')
        else:
            return ('high', 'High', 'orange')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if context.get('latest_reading'):
            context['latest_value'] = context['latest_reading'].caffeine_mg

        return context


class MindfulMinutesDashboardView(SleepDerivedMetricDashboardMixin):
    """
    Mindful Minutes dashboard.

    Mindful minutes are stored on SleepEntry (meditation/breathing exercises).
    Tracks mindfulness practice synced from HealthKit.
    """

    template_name = "health/dashboards/mindful_minutes_dashboard.html"
    metric_name = "Mindful Minutes"
    metric_field = "mindful_minutes"
    feature_key = "sleep"  # Uses sleep feature toggle
    unit = "min"
    chart_color = "#7c3aed"  # Violet for mindfulness
    chart_min = 0
    chart_max = 120
    list_url_name = "health:sleep_list"
    create_url_name = "health:sleep_create"

    def get_status_for_value(self, value):
        """Get mindfulness practice status."""
        if value is None:
            return ('unknown', 'Unknown', 'gray')
        # Encourage regular practice
        if value >= 20:
            return ('excellent', 'Excellent', 'green')
        elif value >= 10:
            return ('good', 'Good', 'green')
        elif value >= 5:
            return ('fair', 'Fair', 'yellow')
        else:
            return ('minimal', 'Minimal', 'gray')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if context.get('latest_reading'):
            context['latest_value'] = context['latest_reading'].mindful_minutes

        return context


class ActivityDashboardView(HealthMetricDashboardMixin):
    """
    Activity dashboard combining steps, calories, and distance.

    Provides an overview of daily activity metrics from StepsEntry.
    """

    model = StepsEntry
    template_name = "health/dashboards/activity_dashboard.html"
    metric_name = "Activity"
    metric_field = "count"  # Steps as primary metric
    feature_key = "steps"
    unit = "steps"
    chart_color = "#22c55e"  # Green for activity
    chart_min = 0
    chart_max = 20000
    list_url_name = "health:steps_list"
    create_url_name = "health:steps_create"
    update_url_name = "health:steps_update"

    def get_statistics(self, queryset):
        """Calculate activity-specific statistics."""
        stats = queryset.aggregate(
            total_steps=Sum('count'),
            avg_steps=Avg('count'),
            total_calories=Sum('calories_burned'),
            avg_calories=Avg('calories_burned'),
            total_distance=Sum('distance_miles'),
            avg_distance=Avg('distance_miles'),
        )
        return {
            'total_steps': stats['total_steps'] or 0,
            'avg_steps': round(float(stats['avg_steps']), 0) if stats['avg_steps'] else 0,
            'total_calories': stats['total_calories'] or 0,
            'avg_calories': round(float(stats['avg_calories']), 0) if stats['avg_calories'] else 0,
            'total_distance': round(float(stats['total_distance']), 1) if stats['total_distance'] else 0,
            'avg_distance': round(float(stats['avg_distance']), 1) if stats['avg_distance'] else 0,
            'count': queryset.values('logged_date').distinct().count(),
        }

    def get_chart_entry_extras(self, entry):
        """Include calories and distance in chart data."""
        return {
            'calories': entry.calories_burned,
            'distance': float(entry.distance_miles) if entry.distance_miles else None,
        }

    def get_status_for_value(self, value):
        """Get activity status based on step count."""
        if value is None:
            return ('unknown', 'Unknown', 'gray')
        # Step count goals
        if value >= 10000:
            return ('excellent', 'Goal Reached', 'green')
        elif value >= 7500:
            return ('good', 'Good', 'green')
        elif value >= 5000:
            return ('moderate', 'Moderate', 'yellow')
        else:
            return ('low', 'Low Activity', 'orange')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if context.get('latest_reading'):
            entry = context['latest_reading']
            context['latest_value'] = entry.count
            context['latest_calories'] = entry.calories_burned
            context['latest_distance'] = entry.distance_miles

        return context
