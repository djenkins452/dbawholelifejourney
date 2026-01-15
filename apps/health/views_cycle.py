"""
Cycle Tracking Views

API views for cycle tracking features.
These use Django's class-based views with JSON responses,
following patterns similar to DRF ViewSets.
"""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import mean, stdev

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Count, Max, Min
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import (
    Cycle,
    CycleDailyLog,
    CyclePrediction,
    CycleSettings,
)
from .serializers import CycleSerializer, CycleSettingsSerializer


class CycleTrackingEnabledMixin:
    """
    Mixin that ensures cycle tracking is enabled before allowing access.

    Returns 403 if user doesn't have cycle settings or tracking is disabled.
    Use on views that require cycle tracking to be enabled.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"error": "Authentication required"},
                status=401
            )

        try:
            settings = CycleSettings.objects.get(user=request.user)
            if not settings.is_enabled:
                return JsonResponse(
                    {"error": "Cycle tracking is not enabled. Enable it in settings first."},
                    status=403
                )
        except CycleSettings.DoesNotExist:
            return JsonResponse(
                {"error": "Cycle tracking is not set up. Call opt_in first."},
                status=403
            )

        return super().dispatch(request, *args, **kwargs)


@method_decorator(csrf_exempt, name="dispatch")
class CycleSettingsViewSet(LoginRequiredMixin, View):
    """
    ViewSet-like class for managing cycle settings.

    Provides:
    - GET: Retrieve current settings
    - PUT/PATCH: Update settings
    - POST /opt_in/: Enable cycle tracking
    - POST /opt_out/: Disable and optionally delete data
    """

    def get(self, request):
        """
        Retrieve the user's cycle settings.

        Returns 404 if no settings exist (user hasn't opted in).
        """
        try:
            settings = CycleSettings.objects.get(user=request.user)
        except CycleSettings.DoesNotExist:
            return JsonResponse(
                {
                    "error": "Cycle settings not found. Call opt_in to enable.",
                    "is_enabled": False,
                },
                status=404
            )

        serializer = CycleSettingsSerializer(instance=settings)
        data = serializer.data
        data["is_enabled"] = settings.is_enabled
        return JsonResponse(data)

    def put(self, request):
        """Update cycle settings."""
        return self._update_settings(request)

    def patch(self, request):
        """Partially update cycle settings."""
        return self._update_settings(request)

    def _update_settings(self, request):
        """Handle settings update for both PUT and PATCH."""
        try:
            settings = CycleSettings.objects.get(user=request.user)
        except CycleSettings.DoesNotExist:
            return JsonResponse(
                {"error": "Cycle settings not found. Call opt_in first."},
                status=404
            )

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        serializer = CycleSettingsSerializer(instance=settings, data=data)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()
        return JsonResponse(serializer.data)


@method_decorator(csrf_exempt, name="dispatch")
class CycleOptInView(LoginRequiredMixin, View):
    """
    Opt-in endpoint for cycle tracking.

    POST /api/cycle/opt_in/

    Creates CycleSettings if not exists, or reactivates if soft-deleted.
    Enables cycle tracking by default.
    """

    def post(self, request):
        """
        Enable cycle tracking for the user.

        Creates CycleSettings if not exists, or enables it if exists.
        """
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            data = {}

        # Try to get existing settings (including soft-deleted)
        try:
            settings = CycleSettings.all_objects.get(user=request.user)
            # Reactivate if soft-deleted
            if not settings.is_active:
                settings.is_active = True
            settings.cycle_tracking_enabled = True
            settings.save()
            created = False
        except CycleSettings.DoesNotExist:
            # Create new settings
            settings = CycleSettings.objects.create(
                user=request.user,
                cycle_tracking_enabled=True,
                average_cycle_length=data.get("average_cycle_length", 28),
                average_period_length=data.get("average_period_length", 5),
            )
            created = True

        serializer = CycleSettingsSerializer(instance=settings)
        response_data = serializer.data
        response_data["created"] = created
        response_data["message"] = (
            "Cycle tracking enabled successfully."
            if created
            else "Cycle tracking re-enabled."
        )

        return JsonResponse(response_data, status=201 if created else 200)


@method_decorator(csrf_exempt, name="dispatch")
class CycleOptOutView(LoginRequiredMixin, View):
    """
    Opt-out endpoint for cycle tracking.

    POST /api/cycle/opt_out/

    Optionally soft-deletes all cycle data based on confirmation flag.
    """

    def post(self, request):
        """
        Disable cycle tracking for the user.

        If confirm_delete=True, also soft-deletes all cycle data.
        """
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            data = {}

        confirm_delete = data.get("confirm_delete", False)

        try:
            settings = CycleSettings.objects.get(user=request.user)
        except CycleSettings.DoesNotExist:
            return JsonResponse(
                {"error": "Cycle tracking is not enabled."},
                status=404
            )

        deleted_counts = {
            "settings": False,
            "daily_logs": 0,
            "cycles": 0,
            "predictions": 0,
        }

        if confirm_delete:
            # Soft delete all cycle data
            deleted_counts["daily_logs"] = CycleDailyLog.objects.filter(
                user=request.user
            ).update(is_active=False)

            deleted_counts["cycles"] = Cycle.objects.filter(
                user=request.user
            ).update(is_active=False)

            deleted_counts["predictions"] = CyclePrediction.objects.filter(
                user=request.user
            ).update(is_active=False)

            # Soft delete settings
            settings.soft_delete()
            deleted_counts["settings"] = True
            message = "Cycle tracking disabled and all data deleted."
        else:
            # Just disable tracking
            settings.cycle_tracking_enabled = False
            settings.save()
            message = "Cycle tracking disabled. Data preserved."

        return JsonResponse({
            "message": message,
            "deleted": deleted_counts,
            "data_preserved": not confirm_delete,
        })


class CycleSettingsCheckView(LoginRequiredMixin, View):
    """
    Quick check endpoint for cycle tracking status.

    GET /api/cycle/check/

    Returns whether cycle tracking is enabled without full settings.
    Useful for UI to determine whether to show cycle features.
    """

    def get(self, request):
        """Check if cycle tracking is enabled for the user."""
        try:
            settings = CycleSettings.objects.get(user=request.user)
            return JsonResponse({
                "is_enabled": settings.is_enabled,
                "cycle_tracking_enabled": settings.cycle_tracking_enabled,
                "fertile_window_tracking_enabled": settings.fertile_window_tracking_enabled,
            })
        except CycleSettings.DoesNotExist:
            return JsonResponse({
                "is_enabled": False,
                "cycle_tracking_enabled": False,
                "fertile_window_tracking_enabled": False,
            })


class CycleViewSet(CycleTrackingEnabledMixin, LoginRequiredMixin, View):
    """
    ViewSet for cycle history (read-only).

    Provides:
    - GET /: List all cycles with pagination and date filtering
    - GET /<id>/: Retrieve single cycle
    - GET /current/: Get the current (ongoing) cycle
    - GET /statistics/: Get cycle averages and trends
    """

    # Pagination settings
    DEFAULT_PAGE_SIZE = 10
    MAX_PAGE_SIZE = 50

    def get(self, request, cycle_id=None, action=None):
        """Route GET requests to appropriate handler."""
        if action == "current":
            return self.current_cycle(request)
        elif action == "statistics":
            return self.statistics(request)
        elif cycle_id:
            return self.retrieve(request, cycle_id)
        else:
            return self.list(request)

    def list(self, request):
        """
        List all cycles with pagination and date filtering.

        Query params:
        - page: Page number (default 1)
        - page_size: Items per page (default 10, max 50)
        - start_date: Filter cycles starting on or after this date
        - end_date: Filter cycles starting on or before this date
        """
        cycles = Cycle.objects.filter(user=request.user)

        # Date range filtering
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
                cycles = cycles.filter(start_date__gte=start_dt)
            except ValueError:
                return JsonResponse(
                    {"error": "Invalid start_date format. Use YYYY-MM-DD."},
                    status=400
                )

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
                cycles = cycles.filter(start_date__lte=end_dt)
            except ValueError:
                return JsonResponse(
                    {"error": "Invalid end_date format. Use YYYY-MM-DD."},
                    status=400
                )

        # Get total count before pagination
        total_count = cycles.count()

        # Pagination
        page = int(request.GET.get("page", 1))
        page_size = min(
            int(request.GET.get("page_size", self.DEFAULT_PAGE_SIZE)),
            self.MAX_PAGE_SIZE
        )

        offset = (page - 1) * page_size
        cycles = cycles.order_by("-start_date")[offset:offset + page_size]

        # Serialize
        serializer_context = {"include_daily_logs": request.GET.get("include_logs") == "true"}
        data = [
            CycleSerializer(instance=cycle, context=serializer_context).data
            for cycle in cycles
        ]

        return JsonResponse({
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 0,
            "results": data,
        })

    def retrieve(self, request, cycle_id):
        """
        Retrieve a single cycle by ID.

        Includes daily logs by default.
        """
        try:
            cycle = Cycle.objects.get(id=cycle_id, user=request.user)
        except Cycle.DoesNotExist:
            return JsonResponse(
                {"error": "Cycle not found."},
                status=404
            )

        serializer = CycleSerializer(
            instance=cycle,
            context={"include_daily_logs": True}
        )
        return JsonResponse(serializer.data)

    def current_cycle(self, request):
        """
        Get the current (ongoing) cycle.

        Returns the cycle with no end_date (is_ongoing=True).
        Returns 404 if no ongoing cycle exists.
        """
        try:
            cycle = Cycle.objects.get(user=request.user, end_date__isnull=True)
        except Cycle.DoesNotExist:
            return JsonResponse(
                {"error": "No current cycle found. Start a new period to create one."},
                status=404
            )

        serializer = CycleSerializer(
            instance=cycle,
            context={"include_daily_logs": True}
        )
        data = serializer.data
        data["days_since_start"] = (date.today() - cycle.start_date).days
        return JsonResponse(data)

    def statistics(self, request):
        """
        Get cycle statistics and trends.

        Returns:
        - Average cycle length
        - Average period length
        - Cycle length range (min/max)
        - Period length range (min/max)
        - Standard deviation
        - Cycle count
        - Regularity score (based on consistency)
        - Recent trend (getting longer/shorter/stable)
        """
        completed_cycles = Cycle.objects.filter(
            user=request.user,
            end_date__isnull=False  # Only completed cycles
        ).order_by("-start_date")

        total_cycles = completed_cycles.count()

        if total_cycles == 0:
            return JsonResponse({
                "message": "No completed cycles yet. Statistics require at least one completed cycle.",
                "cycle_count": 0,
            })

        # Calculate cycle lengths
        cycle_lengths = []
        period_lengths = []
        for cycle in completed_cycles:
            if cycle.cycle_length:
                cycle_lengths.append(cycle.cycle_length)
            if cycle.period_length:
                period_lengths.append(cycle.period_length)

        stats = {
            "cycle_count": total_cycles,
            "completed_cycles": len(cycle_lengths),
        }

        # Cycle length statistics
        if cycle_lengths:
            stats["cycle_length"] = {
                "average": round(mean(cycle_lengths), 1),
                "min": min(cycle_lengths),
                "max": max(cycle_lengths),
                "standard_deviation": round(stdev(cycle_lengths), 1) if len(cycle_lengths) > 1 else 0,
            }

            # Regularity score (0-100, based on standard deviation)
            # Lower std dev = more regular
            if len(cycle_lengths) > 1:
                std = stdev(cycle_lengths)
                # A std of 0 = 100% regular, std of 7+ = 0% regular
                regularity = max(0, min(100, round(100 - (std / 7 * 100))))
            else:
                regularity = None
            stats["regularity_score"] = regularity

            # Trend analysis (last 3 vs previous 3 cycles)
            if len(cycle_lengths) >= 6:
                recent_avg = mean(cycle_lengths[:3])
                older_avg = mean(cycle_lengths[3:6])
                diff = recent_avg - older_avg
                if diff > 2:
                    trend = "lengthening"
                elif diff < -2:
                    trend = "shortening"
                else:
                    trend = "stable"
                stats["trend"] = {
                    "direction": trend,
                    "recent_average": round(recent_avg, 1),
                    "older_average": round(older_avg, 1),
                }
            elif len(cycle_lengths) >= 3:
                stats["trend"] = {
                    "direction": "insufficient_data",
                    "message": "Need at least 6 cycles for trend analysis",
                }
            else:
                stats["trend"] = None
        else:
            stats["cycle_length"] = None
            stats["regularity_score"] = None
            stats["trend"] = None

        # Period length statistics
        if period_lengths:
            stats["period_length"] = {
                "average": round(mean(period_lengths), 1),
                "min": min(period_lengths),
                "max": max(period_lengths),
            }
        else:
            stats["period_length"] = None

        # Recent cycles summary (last 3)
        recent_cycles = completed_cycles[:3]
        stats["recent_cycles"] = [
            {
                "cycle_number": c.cycle_number,
                "start_date": c.start_date.isoformat(),
                "cycle_length": c.cycle_length,
                "period_length": c.period_length,
            }
            for c in recent_cycles
        ]

        return JsonResponse(stats)
