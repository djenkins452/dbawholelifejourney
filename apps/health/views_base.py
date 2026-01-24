# views_base.py
# Whole Life Journey - Health Module
#
# Base dashboard mixin for health metric dashboards.
# Provides reusable functionality for period selection, statistics,
# chart data preparation, and feature enablement checking.

from datetime import timedelta
from collections import defaultdict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Max, Min, Count
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView

from apps.core.utils import get_user_today
from apps.help.mixins import HelpContextMixin


class HealthMetricDashboardMixin(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Base mixin for health metric dashboards.

    Provides common functionality:
    - Period selection (Today, 7d, 30d, 60d, 90d, or custom days)
    - Date range filtering
    - Statistics aggregation
    - Chart data preparation
    - AI insight generation
    - Feature enablement checking

    Subclasses must define:
    - model: The Django model class
    - metric_name: Display name (e.g., "Blood Pressure")
    - metric_field: Primary value field for stats (e.g., "systolic")
    - template_name: Dashboard template path
    - feature_key: Key in HEALTH_FEATURES for preference checking

    Optional overrides:
    - date_field: Field to filter by date (default: "recorded_at")
    - unit: Display unit (e.g., "mmHg")
    - list_url_name: URL name for list view
    - create_url_name: URL name for create view
    - update_url_name: URL name for update view
    - chart_color: Hex color for chart line
    - chart_min/chart_max: Y-axis bounds
    """

    # Required - subclass must define
    model = None
    metric_name = ""
    metric_field = ""
    feature_key = ""

    # Optional with defaults
    date_field = "recorded_at"
    unit = ""
    list_url_name = ""
    create_url_name = ""
    update_url_name = ""

    # Chart configuration
    chart_color = "#6366f1"  # Default indigo
    chart_min = None
    chart_max = None

    # Period options
    PRESET_PERIODS = [0, 7, 30, 60, 90]
    MAX_CUSTOM_PERIOD = 730  # 2 years max

    def dispatch(self, request, *args, **kwargs):
        """Check if feature is enabled before proceeding."""
        if request.user.is_authenticated and hasattr(request.user, 'preferences'):
            if not request.user.preferences.is_feature_enabled('health', self.feature_key):
                return redirect('health:home')
        return super().dispatch(request, *args, **kwargs)

    def get_period(self):
        """Get validated period from query params (preset or custom)."""
        try:
            period = int(self.request.GET.get('period', 7))
            # Allow preset periods or any custom value up to max
            if period < 0:
                period = 7
            elif period > self.MAX_CUSTOM_PERIOD:
                period = self.MAX_CUSTOM_PERIOD
        except (ValueError, TypeError):
            period = 7
        return period

    def get_period_start(self, period):
        """Calculate period start datetime."""
        now = timezone.now()

        if period == 0:
            # Today only
            today = get_user_today(self.request.user)
            return timezone.make_aware(
                timezone.datetime.combine(today, timezone.datetime.min.time())
            )
        return now - timedelta(days=period)

    def get_period_label(self, period):
        """Get human-readable period label."""
        if period == 0:
            return "Today"
        elif period == 7:
            return "Last 7 Days"
        elif period == 30:
            return "Last 30 Days"
        elif period == 60:
            return "Last 60 Days"
        elif period == 90:
            return "Last 90 Days"
        elif period == 365:
            return "Last Year"
        else:
            return f"Last {period} Days"

    def get_queryset(self):
        """Get base queryset for user."""
        return self.model.objects.filter(user=self.request.user)

    def get_period_queryset(self, period_start):
        """Get queryset filtered by period."""
        filter_kwargs = {
            'user': self.request.user,
            f'{self.date_field}__gte': period_start,
        }
        return self.model.objects.filter(**filter_kwargs).order_by(f'-{self.date_field}')

    def get_statistics(self, queryset):
        """
        Calculate aggregate statistics.

        Override for metrics with multiple values (e.g., blood pressure).
        """
        stats = queryset.aggregate(
            avg=Avg(self.metric_field),
            min_val=Min(self.metric_field),
            max_val=Max(self.metric_field),
            count=Count('id'),
        )
        return {
            'avg': round(float(stats['avg']), 1) if stats['avg'] else None,
            'min': stats['min_val'],
            'max': stats['max_val'],
            'count': stats['count'],
        }

    def get_chart_value(self, entry):
        """
        Extract chart value from entry.

        Override for complex metrics or different field access.
        """
        value = getattr(entry, self.metric_field, None)
        return float(value) if value is not None else None

    def get_chart_entry_extras(self, entry):
        """
        Additional chart data per entry.

        Override to include extra data like secondary values, categories, etc.
        """
        return {}

    def get_chart_data(self, queryset, period, aggregated=False):
        """
        Prepare chart data.

        For periods > 7 days, aggregates to daily averages.
        Otherwise returns individual readings.
        """
        entries = list(queryset.order_by(self.date_field))

        if not entries:
            return []

        if aggregated and period > 7:
            # Group by day for longer periods
            daily_data = defaultdict(list)

            for entry in entries:
                date_value = getattr(entry, self.date_field)
                if date_value:
                    day = date_value.date()
                    value = self.get_chart_value(entry)
                    if value is not None:
                        daily_data[day].append(value)

            chart_data = []
            for day in sorted(daily_data.keys()):
                values = daily_data[day]
                if values:
                    avg_value = sum(values) / len(values)
                    day_datetime = timezone.make_aware(
                        timezone.datetime.combine(day, timezone.datetime.min.time().replace(hour=12))
                    )
                    chart_data.append({
                        'time': day_datetime.isoformat(),
                        'value': round(avg_value, 1),
                        'is_average': True,
                        'reading_count': len(values),
                    })
            return chart_data

        # Individual readings
        chart_data = []
        for entry in entries:
            date_value = getattr(entry, self.date_field)
            value = self.get_chart_value(entry)
            if date_value and value is not None:
                chart_data.append({
                    'time': date_value.isoformat(),
                    'value': value,
                    'is_average': False,
                    **self.get_chart_entry_extras(entry),
                })
        return chart_data

    def get_latest_reading(self):
        """Get most recent reading."""
        return self.get_queryset().first()

    def get_status_for_value(self, value):
        """
        Get status category for a value.

        Override for metric-specific categorization.
        Returns tuple of (status_key, status_display, status_color).
        """
        return ('normal', 'Normal', 'green')

    def get_ai_insight(self, stats_data, entries):
        """
        Generate AI insight.

        Override to customize or return None to disable.
        """
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        period = self.get_period()
        period_start = self.get_period_start(period)

        # Period info
        context['period'] = period
        context['preset_periods'] = self.PRESET_PERIODS
        context['max_custom_period'] = self.MAX_CUSTOM_PERIOD
        context['period_label'] = self.get_period_label(period)
        context['is_custom_period'] = period not in self.PRESET_PERIODS

        # Metric info
        context['metric_name'] = self.metric_name
        context['unit'] = self.unit
        context['feature_key'] = self.feature_key
        context['list_url_name'] = self.list_url_name
        context['create_url_name'] = self.create_url_name
        context['update_url_name'] = self.update_url_name

        # Data
        queryset = self.get_period_queryset(period_start)
        context['entries'] = queryset[:50]
        context['entry_count'] = queryset.count()

        # Latest reading
        latest = self.get_latest_reading()
        context['latest_reading'] = latest
        if latest:
            latest_value = self.get_chart_value(latest)
            if latest_value is not None:
                status_key, status_display, status_color = self.get_status_for_value(latest_value)
                context['latest_status'] = status_key
                context['latest_status_display'] = status_display
                context['latest_status_color'] = status_color

        # Statistics
        context['stats'] = None
        if queryset.exists():
            context['stats'] = self.get_statistics(queryset)

        # Chart
        aggregated = period > 7
        context['chart_data'] = self.get_chart_data(queryset, period, aggregated)
        context['chart_aggregated'] = aggregated
        context['chart_color'] = self.chart_color
        context['chart_min'] = self.chart_min
        context['chart_max'] = self.chart_max

        # AI Insight
        context['ai_insight'] = None
        context['ai_enabled'] = False
        try:
            prefs = user.preferences
            if prefs.ai_enabled and prefs.ai_data_consent:
                context['ai_enabled'] = True
                context['ai_insight'] = self.get_ai_insight(
                    context.get('stats', {}),
                    list(queryset[:20])
                )
        except Exception:
            pass

        return context


class SleepDerivedMetricDashboardMixin(HealthMetricDashboardMixin):
    """
    Specialized mixin for metrics stored as fields on SleepEntry.

    Used for: HRV, VO2 Max, Respiratory Rate, Caffeine, Mindful Minutes.
    These are stored on SleepEntry but displayed as standalone dashboards.
    """

    date_field = "sleep_date"

    def get_queryset(self):
        """Get SleepEntry records that have this metric."""
        from apps.health.models import SleepEntry

        filter_kwargs = {
            'user': self.request.user,
            f'{self.metric_field}__isnull': False,
        }
        return SleepEntry.objects.filter(**filter_kwargs)

    def get_period_queryset(self, period_start):
        """Get SleepEntry records filtered by period with non-null metric."""
        from apps.health.models import SleepEntry

        filter_kwargs = {
            'user': self.request.user,
            f'{self.metric_field}__isnull': False,
            f'{self.date_field}__gte': period_start.date(),
        }
        return SleepEntry.objects.filter(**filter_kwargs).order_by(f'-{self.date_field}')
