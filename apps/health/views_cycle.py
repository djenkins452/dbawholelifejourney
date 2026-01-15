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
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from apps.help.mixins import HelpContextMixin

from .models import (
    Cycle,
    CycleDailyLog,
    CyclePrediction,
    CycleSettings,
)
from .serializers import (
    CycleDailyLogSerializer,
    CyclePredictionSerializer,
    CycleSerializer,
    CycleSettingsSerializer,
)


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


@method_decorator(csrf_exempt, name="dispatch")
class CycleDailyLogViewSet(CycleTrackingEnabledMixin, LoginRequiredMixin, View):
    """
    ViewSet for daily cycle logging with full CRUD operations.

    Provides:
    - GET /: List all daily logs with date filtering
    - GET /<id>/: Retrieve single daily log
    - POST /: Create a new daily log
    - PUT/PATCH /<id>/: Update an existing daily log
    - DELETE /<id>/: Soft delete a daily log
    """

    # Pagination settings
    DEFAULT_PAGE_SIZE = 30
    MAX_PAGE_SIZE = 100

    def get(self, request, log_id=None):
        """Handle GET requests - list or retrieve."""
        if log_id:
            return self.retrieve(request, log_id)
        return self.list(request)

    def post(self, request):
        """Create a new daily log."""
        return self.create(request)

    def put(self, request, log_id=None):
        """Update an existing daily log."""
        if not log_id:
            return JsonResponse({"error": "Log ID required for update."}, status=400)
        return self.update(request, log_id)

    def patch(self, request, log_id=None):
        """Partially update an existing daily log."""
        if not log_id:
            return JsonResponse({"error": "Log ID required for update."}, status=400)
        return self.update(request, log_id, partial=True)

    def delete(self, request, log_id=None):
        """Soft delete a daily log."""
        if not log_id:
            return JsonResponse({"error": "Log ID required for delete."}, status=400)
        return self.destroy(request, log_id)

    def list(self, request):
        """
        List all daily logs with date range filtering.

        Query params:
        - page: Page number (default 1)
        - page_size: Items per page (default 30, max 100)
        - start_date: Filter logs on or after this date
        - end_date: Filter logs on or before this date
        """
        logs = CycleDailyLog.objects.filter(user=request.user)

        # Date range filtering
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
                logs = logs.filter(log_date__gte=start_dt)
            except ValueError:
                return JsonResponse(
                    {"error": "Invalid start_date format. Use YYYY-MM-DD."},
                    status=400
                )

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
                logs = logs.filter(log_date__lte=end_dt)
            except ValueError:
                return JsonResponse(
                    {"error": "Invalid end_date format. Use YYYY-MM-DD."},
                    status=400
                )

        # Get total count before pagination
        total_count = logs.count()

        # Pagination
        page = int(request.GET.get("page", 1))
        page_size = min(
            int(request.GET.get("page_size", self.DEFAULT_PAGE_SIZE)),
            self.MAX_PAGE_SIZE
        )

        offset = (page - 1) * page_size
        logs = logs.order_by("-log_date")[offset:offset + page_size]

        # Serialize
        data = [CycleDailyLogSerializer(instance=log).data for log in logs]

        return JsonResponse({
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 0,
            "results": data,
        })

    def retrieve(self, request, log_id):
        """Retrieve a single daily log by ID."""
        try:
            log = CycleDailyLog.objects.get(id=log_id, user=request.user)
        except CycleDailyLog.DoesNotExist:
            return JsonResponse({"error": "Daily log not found."}, status=404)

        serializer = CycleDailyLogSerializer(instance=log)
        return JsonResponse(serializer.data)

    def create(self, request):
        """
        Create a new daily log.

        Validates that log_date is not in the future.
        Triggers period detection service after save.
        """
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        # Validate log_date is not in the future
        log_date = data.get("log_date")
        if log_date:
            try:
                log_date_parsed = datetime.strptime(log_date, "%Y-%m-%d").date()
                if log_date_parsed > date.today():
                    return JsonResponse(
                        {"error": "log_date cannot be in the future."},
                        status=400
                    )
            except ValueError:
                return JsonResponse(
                    {"error": "Invalid log_date format. Use YYYY-MM-DD."},
                    status=400
                )

        # Check if a log already exists for this date
        existing_log = CycleDailyLog.objects.filter(
            user=request.user,
            log_date=log_date or date.today()
        ).first()

        if existing_log:
            return JsonResponse(
                {"error": f"A log already exists for {existing_log.log_date}. Use PUT to update."},
                status=400
            )

        serializer = CycleDailyLogSerializer(data=data)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        log = serializer.save(user=request.user)

        # Trigger period detection service
        self._trigger_period_detection(request.user, log)

        return JsonResponse(
            CycleDailyLogSerializer(instance=log).data,
            status=201
        )

    def update(self, request, log_id, partial=False):
        """
        Update an existing daily log.

        Validates that log_date is not in the future.
        Triggers period detection service after save.
        """
        try:
            log = CycleDailyLog.objects.get(id=log_id, user=request.user)
        except CycleDailyLog.DoesNotExist:
            return JsonResponse({"error": "Daily log not found."}, status=404)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        # Validate log_date is not in the future (if being changed)
        log_date = data.get("log_date")
        if log_date:
            try:
                log_date_parsed = datetime.strptime(log_date, "%Y-%m-%d").date()
                if log_date_parsed > date.today():
                    return JsonResponse(
                        {"error": "log_date cannot be in the future."},
                        status=400
                    )
            except ValueError:
                return JsonResponse(
                    {"error": "Invalid log_date format. Use YYYY-MM-DD."},
                    status=400
                )

        serializer = CycleDailyLogSerializer(instance=log, data=data)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        log = serializer.save()

        # Trigger period detection service
        self._trigger_period_detection(request.user, log)

        return JsonResponse(CycleDailyLogSerializer(instance=log).data)

    def destroy(self, request, log_id):
        """Soft delete a daily log."""
        try:
            log = CycleDailyLog.objects.get(id=log_id, user=request.user)
        except CycleDailyLog.DoesNotExist:
            return JsonResponse({"error": "Daily log not found."}, status=404)

        log_date = log.log_date
        log.soft_delete()

        # Trigger period detection after delete (may need to recalculate)
        self._trigger_period_detection(request.user)

        return JsonResponse({
            "message": f"Daily log for {log_date} deleted successfully.",
            "deleted_id": log_id,
        })

    def _trigger_period_detection(self, user, log=None):
        """
        Trigger the period detection service after a log change.

        Uses CycleDetectionService to analyze flow patterns and
        automatically create/update Cycle records.

        The service will:
        1. Check if this is a period day (flow_level != 'none')
        2. If starting a new period, create/update Cycle record
        3. If ending a period, update period_end_date
        4. Update predictions based on new data
        """
        if log is None:
            return

        from .services.cycle_detection import CycleDetectionService
        service = CycleDetectionService(user)
        service.process_daily_log(log)


class CyclePredictionViewSet(CycleTrackingEnabledMixin, LoginRequiredMixin, View):
    """
    ViewSet for cycle predictions (read-only with regenerate action).

    Provides:
    - GET /: List all predictions with pagination
    - GET /<id>/: Retrieve single prediction
    - GET /current/: Get the latest/active prediction
    - POST /regenerate/: Generate new prediction from latest cycle data
    """

    # Pagination settings
    DEFAULT_PAGE_SIZE = 10
    MAX_PAGE_SIZE = 50

    # Minimum cycles required for prediction
    MIN_CYCLES_FOR_PREDICTION = 3

    # Current algorithm version
    ALGORITHM_VERSION = "v1.0-basic"

    def get(self, request, prediction_id=None, action=None):
        """Route GET requests to appropriate handler."""
        if action == "current":
            return self.current(request)
        elif prediction_id:
            return self.retrieve(request, prediction_id)
        else:
            return self.list(request)

    def post(self, request, action=None):
        """Handle POST requests for regenerate action."""
        if action == "regenerate":
            return self.regenerate(request)
        return JsonResponse({"error": "Method not allowed."}, status=405)

    def list(self, request):
        """
        List all predictions with pagination.

        Query params:
        - page: Page number (default 1)
        - page_size: Items per page (default 10, max 50)
        """
        predictions = CyclePrediction.objects.filter(user=request.user)

        # Get total count before pagination
        total_count = predictions.count()

        # Check if user has enough cycles for predictions
        completed_cycles_count = Cycle.objects.filter(
            user=request.user,
            end_date__isnull=False
        ).count()

        if total_count == 0 and completed_cycles_count < self.MIN_CYCLES_FOR_PREDICTION:
            return JsonResponse({
                "message": f"Predictions require at least {self.MIN_CYCLES_FOR_PREDICTION} completed cycles. "
                           f"You have {completed_cycles_count} completed cycle(s).",
                "completed_cycles": completed_cycles_count,
                "cycles_needed": self.MIN_CYCLES_FOR_PREDICTION - completed_cycles_count,
                "count": 0,
                "results": [],
            })

        # Pagination
        page = int(request.GET.get("page", 1))
        page_size = min(
            int(request.GET.get("page_size", self.DEFAULT_PAGE_SIZE)),
            self.MAX_PAGE_SIZE
        )

        offset = (page - 1) * page_size
        predictions = predictions.order_by("-generated_at")[offset:offset + page_size]

        # Serialize
        data = [CyclePredictionSerializer(instance=pred).data for pred in predictions]

        return JsonResponse({
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 0,
            "algorithm_version": self.ALGORITHM_VERSION,
            "results": data,
        })

    def retrieve(self, request, prediction_id):
        """Retrieve a single prediction by ID."""
        try:
            prediction = CyclePrediction.objects.get(id=prediction_id, user=request.user)
        except CyclePrediction.DoesNotExist:
            return JsonResponse({"error": "Prediction not found."}, status=404)

        serializer = CyclePredictionSerializer(instance=prediction)
        data = serializer.data
        data["algorithm_version"] = prediction.prediction_algorithm_version
        return JsonResponse(data)

    def current(self, request):
        """
        Get the current (latest) active prediction.

        Returns the most recent prediction that hasn't been verified yet.
        Returns 404 if no active prediction exists.
        """
        # Check if user has enough cycles
        completed_cycles_count = Cycle.objects.filter(
            user=request.user,
            end_date__isnull=False
        ).count()

        if completed_cycles_count < self.MIN_CYCLES_FOR_PREDICTION:
            return JsonResponse({
                "message": f"Predictions require at least {self.MIN_CYCLES_FOR_PREDICTION} completed cycles. "
                           f"You have {completed_cycles_count} completed cycle(s).",
                "completed_cycles": completed_cycles_count,
                "cycles_needed": self.MIN_CYCLES_FOR_PREDICTION - completed_cycles_count,
            }, status=404)

        # Get active prediction
        prediction = CyclePrediction.get_active_prediction(request.user)

        if not prediction:
            return JsonResponse({
                "message": "No active prediction found. Use regenerate to create one.",
                "can_regenerate": True,
            }, status=404)

        serializer = CyclePredictionSerializer(instance=prediction)
        data = serializer.data

        # Add days until predicted period
        days_until = (prediction.predicted_period_start - date.today()).days
        data["days_until_period"] = days_until

        # Add status based on timing
        if days_until < 0:
            data["status"] = "overdue"
            data["status_message"] = f"Period was expected {abs(days_until)} day(s) ago"
        elif days_until == 0:
            data["status"] = "today"
            data["status_message"] = "Period expected today"
        elif days_until <= 3:
            data["status"] = "soon"
            data["status_message"] = f"Period expected in {days_until} day(s)"
        else:
            data["status"] = "upcoming"
            data["status_message"] = f"Period expected in {days_until} days"

        return JsonResponse(data)

    def regenerate(self, request):
        """
        Generate a new prediction based on the latest cycle data.

        Uses a simple algorithm based on average cycle length.
        Returns 400 if user has fewer than MIN_CYCLES_FOR_PREDICTION completed cycles.
        """
        # Get completed cycles
        completed_cycles = Cycle.objects.filter(
            user=request.user,
            end_date__isnull=False
        ).order_by("-start_date")

        completed_count = completed_cycles.count()

        if completed_count < self.MIN_CYCLES_FOR_PREDICTION:
            return JsonResponse({
                "error": f"Cannot generate prediction. Need at least {self.MIN_CYCLES_FOR_PREDICTION} "
                         f"completed cycles, but you have {completed_count}.",
                "completed_cycles": completed_count,
                "cycles_needed": self.MIN_CYCLES_FOR_PREDICTION - completed_count,
            }, status=400)

        # Calculate averages from completed cycles
        cycle_lengths = [c.cycle_length for c in completed_cycles if c.cycle_length]
        period_lengths = [c.period_length for c in completed_cycles if c.period_length]

        if not cycle_lengths:
            return JsonResponse({
                "error": "Cannot generate prediction. Completed cycles have no length data.",
            }, status=400)

        avg_cycle_length = round(mean(cycle_lengths))
        avg_period_length = round(mean(period_lengths)) if period_lengths else 5

        # Calculate confidence based on data consistency
        if len(cycle_lengths) >= 6:
            std = stdev(cycle_lengths)
            # Lower std = higher confidence
            confidence = max(0.3, min(0.95, 1.0 - (std / 10)))
        elif len(cycle_lengths) >= 3:
            confidence = 0.6  # Moderate confidence with limited data
        else:
            confidence = 0.5

        # Get the most recent cycle to base prediction on
        # If there's an ongoing cycle, use its start date
        # Otherwise, use the most recent completed cycle's start date + cycle length
        ongoing_cycle = Cycle.objects.filter(
            user=request.user,
            end_date__isnull=True
        ).first()

        if ongoing_cycle:
            base_date = ongoing_cycle.start_date
        else:
            latest_completed = completed_cycles.first()
            if latest_completed:
                base_date = latest_completed.start_date
            else:
                return JsonResponse({
                    "error": "No cycle data available for prediction.",
                }, status=400)

        # Calculate predicted dates
        predicted_period_start = base_date + timedelta(days=avg_cycle_length)
        predicted_period_end = predicted_period_start + timedelta(days=avg_period_length - 1)

        # Calculate fertile window (typically 12-16 days before period)
        # Ovulation is approximately 14 days before the next period
        ovulation_day = predicted_period_start - timedelta(days=14)
        fertile_start = ovulation_day - timedelta(days=5)  # Fertile window starts 5 days before ovulation
        fertile_end = ovulation_day + timedelta(days=1)  # Ends 1 day after ovulation

        # Get user's fertile window tracking preference
        try:
            settings = CycleSettings.objects.get(user=request.user)
            include_fertile = settings.fertile_window_tracking_enabled
        except CycleSettings.DoesNotExist:
            include_fertile = False

        # Create the prediction
        prediction = CyclePrediction.objects.create(
            user=request.user,
            predicted_period_start=predicted_period_start,
            predicted_period_end=predicted_period_end,
            predicted_fertile_window_start=fertile_start if include_fertile else None,
            predicted_fertile_window_end=fertile_end if include_fertile else None,
            prediction_confidence=Decimal(str(round(confidence, 2))),
            prediction_algorithm_version=self.ALGORITHM_VERSION,
        )

        serializer = CyclePredictionSerializer(instance=prediction)
        data = serializer.data

        # Add metadata
        data["message"] = "New prediction generated successfully."
        data["based_on_cycles"] = len(cycle_lengths)
        data["average_cycle_length"] = avg_cycle_length
        data["average_period_length"] = avg_period_length
        data["days_until_period"] = (predicted_period_start - date.today()).days

        return JsonResponse(data, status=201)


class CycleSettingsPageView(HelpContextMixin, LoginRequiredMixin, CycleTrackingEnabledMixin, TemplateView):
    """
    Cycle tracking settings page.

    Allows users to configure:
    - Average cycle length
    - Average period length
    - Fertile window display toggle
    - Notification preferences
    """

    template_name = "health/cycle/settings.html"
    help_context_id = "HEALTH_CYCLE_SETTINGS"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        try:
            settings = CycleSettings.objects.get(user=user)
            context["settings"] = settings
        except CycleSettings.DoesNotExist:
            context["settings"] = None

        return context


class CycleOptInPageView(LoginRequiredMixin, TemplateView):
    """
    Cycle tracking opt-in page.

    Shows privacy information and allows users to enable cycle tracking.
    If already enabled (e.g., auto-enabled based on gender), shows status
    with option to disable.
    """

    template_name = "health/cycle/opt_in.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Check if cycle tracking already exists
        try:
            settings = CycleSettings.objects.get(user=user)
            context["cycle_settings"] = settings
            context["is_enabled"] = settings.is_enabled
        except CycleSettings.DoesNotExist:
            context["cycle_settings"] = None
            context["is_enabled"] = False

        # Check if user's gender is female (indicating auto-enable)
        try:
            prefs = user.preferences
            context["user_gender"] = prefs.gender
            context["was_auto_enabled"] = (
                prefs.gender == "female"
                and context.get("cycle_settings") is not None
            )
        except Exception:
            context["user_gender"] = None
            context["was_auto_enabled"] = False

        return context


class CycleDashboardView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Main cycle tracking dashboard page.

    Displays:
    - Cycle summary card with current cycle day and phase
    - Recent 7 days of logs
    - Quick actions for logging, calendar, settings
    - Empty state for users who haven't enabled cycle tracking
    """

    template_name = "health/cycle/dashboard.html"
    help_context_id = "HEALTH_CYCLE_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.now().date()

        # Check if cycle tracking is enabled
        try:
            settings = CycleSettings.objects.get(user=user)
            cycle_enabled = settings.is_enabled
        except CycleSettings.DoesNotExist:
            cycle_enabled = False

        context["cycle_enabled"] = cycle_enabled
        context["today"] = today

        if not cycle_enabled:
            return context

        # Get current cycle
        current_cycle = Cycle.objects.filter(
            user=user,
            end_date__isnull=True,
        ).first()
        context["cycle"] = current_cycle

        # Get current phase
        if current_cycle:
            from .services.cycle_phase import get_current_phase
            phase = get_current_phase(user, today)
            context["phase"] = phase

        # Get current prediction
        prediction = CyclePrediction.get_active_prediction(user)
        context["prediction"] = prediction

        if prediction:
            days_until = (prediction.predicted_period_start - today).days
            context["days_until_period"] = days_until

        # Get recent 7 days of logs
        week_ago = today - timedelta(days=7)
        recent_logs = CycleDailyLog.objects.filter(
            user=user,
            log_date__gte=week_ago,
            log_date__lte=today,
        ).order_by("-log_date")

        # Mark today's log
        logs_with_today = []
        for log in recent_logs:
            log.is_today = (log.log_date == today)
            logs_with_today.append(log)

        context["recent_logs"] = logs_with_today

        return context


class CyclePeriodToggleView(LoginRequiredMixin, CycleTrackingEnabledMixin, View):
    """
    Quick toggle for period start/end from dashboard.

    POST with action: "start" or "end"
    Returns an HTML fragment for HTMX replacement.
    """

    def post(self, request):
        action = request.POST.get("action")
        today = timezone.now().date()
        user = request.user

        if action == "start":
            # Create or update today's log with flow level
            log, created = CycleDailyLog.objects.get_or_create(
                user=user,
                log_date=today,
                defaults={"flow_level": "medium"}
            )
            if not created and not log.flow_level:
                log.flow_level = "medium"
                log.save()

            # Start a new cycle if needed
            current_cycle = Cycle.objects.filter(
                user=user,
                end_date__isnull=True
            ).first()

            if not current_cycle:
                # Create new cycle
                Cycle.objects.create(
                    user=user,
                    start_date=today,
                )

            is_period_day = True

        elif action == "end":
            # Update today's log to mark period ended (set flow to none/spotting)
            log, created = CycleDailyLog.objects.get_or_create(
                user=user,
                log_date=today,
                defaults={"flow_level": "spotting"}
            )
            if not created:
                # Mark as spotting or none to indicate end
                log.flow_level = "spotting"
                log.save()

            # Update current cycle's period_end_date
            current_cycle = Cycle.objects.filter(
                user=user,
                end_date__isnull=True
            ).first()

            if current_cycle and not current_cycle.period_end_date:
                current_cycle.period_end_date = today
                current_cycle.save()

            is_period_day = True  # Still showing something logged

        else:
            return JsonResponse({"error": "Invalid action"}, status=400)

        # Return HTML fragment for HTMX
        from django.template.loader import render_to_string

        html = render_to_string(
            "health/cycle/includes/period_toggle_status.html",
            {
                "is_period_day": is_period_day,
                "action": action,
            },
            request=request
        )

        from django.http import HttpResponse
        return HttpResponse(html)


class CycleCalendarView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Calendar view for cycle tracking.

    Displays a monthly calendar with:
    - Color-coded period days based on flow level
    - Predicted period days with dashed borders
    - Optional fertile window highlighting
    - Click-to-log functionality
    - Month navigation and touch swipe support
    """

    template_name = "health/cycle/calendar.html"
    help_context_id = "HEALTH_CYCLE_CALENDAR"

    def get_context_data(self, **kwargs):
        import json
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.now().date()

        # Get requested month/year or default to current
        year = self.request.GET.get("year")
        month = self.request.GET.get("month")

        if year and month:
            try:
                current_year = int(year)
                current_month = int(month) - 1  # Convert to 0-indexed for JS
            except ValueError:
                current_year = today.year
                current_month = today.month - 1
        else:
            current_year = today.year
            current_month = today.month - 1

        context["current_year"] = current_year
        context["current_month_num"] = current_month

        # For display in template
        display_date = date(current_year, current_month + 1, 1)
        context["current_month"] = display_date

        # Get logs for visible range (current month plus padding)
        # Fetch 6 weeks of data to cover any month
        month_start = date(current_year, current_month + 1, 1)
        if current_month == 11:
            month_end = date(current_year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(current_year, current_month + 2, 1) - timedelta(days=1)

        # Extend range for calendar padding (days from prev/next month)
        range_start = month_start - timedelta(days=7)
        range_end = month_end + timedelta(days=7)

        # Fetch daily logs
        logs = CycleDailyLog.objects.filter(
            user=user,
            log_date__gte=range_start,
            log_date__lte=range_end
        )

        logs_dict = {}
        for log in logs:
            logs_dict[log.log_date.isoformat()] = {
                "flow_level": log.flow_level,
                "mood": log.mood,
                "energy_level": log.energy_level,
                "symptoms": log.symptoms,
                "notes": log.notes[:100] if log.notes else None,
            }

        context["logs_json"] = json.dumps(logs_dict)

        # Get current prediction
        prediction = CyclePrediction.get_active_prediction(user)
        predictions_dict = {}
        if prediction:
            predictions_dict = {
                "predicted_period_start": prediction.predicted_period_start.isoformat() if prediction.predicted_period_start else None,
                "predicted_period_end": prediction.predicted_period_end.isoformat() if prediction.predicted_period_end else None,
                "predicted_fertile_window_start": prediction.predicted_fertile_window_start.isoformat() if prediction.predicted_fertile_window_start else None,
                "predicted_fertile_window_end": prediction.predicted_fertile_window_end.isoformat() if prediction.predicted_fertile_window_end else None,
            }

        context["predictions_json"] = json.dumps(predictions_dict)

        # Get cycle history (start dates)
        cycles = Cycle.objects.filter(user=user).order_by("-start_date")[:12]
        cycles_list = [
            {
                "start_date": c.start_date.isoformat(),
                "end_date": c.end_date.isoformat() if c.end_date else None,
            }
            for c in cycles
        ]
        context["cycles_json"] = json.dumps(cycles_list)

        return context


class CycleDayModalView(LoginRequiredMixin, CycleTrackingEnabledMixin, View):
    """
    Returns the day detail modal HTML for a specific date.

    Used by the calendar view to load modal content when a day is clicked.
    GET /health/cycle/api/day-modal/?date=YYYY-MM-DD
    """

    def get(self, request):
        from django.template.loader import render_to_string
        from django.http import HttpResponse

        date_str = request.GET.get("date")
        if not date_str:
            return HttpResponse("Missing date parameter", status=400)

        try:
            log_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return HttpResponse("Invalid date format", status=400)

        user = request.user
        today = timezone.now().date()

        # Get existing log for this date
        try:
            log = CycleDailyLog.objects.get(user=user, log_date=log_date)
        except CycleDailyLog.DoesNotExist:
            log = None

        # Determine if this day is editable (not in the future)
        is_editable = log_date <= today

        # Get choices for form
        from .models import CYCLE_MOOD_CHOICES, CYCLE_SYMPTOM_CHOICES

        context = {
            "log": log,
            "log_date": log_date,
            "is_today": log_date == today,
            "is_editable": is_editable,
            "mood_choices": CYCLE_MOOD_CHOICES,
            "symptom_choices": CYCLE_SYMPTOM_CHOICES,
        }

        html = render_to_string(
            "health/cycle/includes/day_modal.html",
            context,
            request=request
        )

        return HttpResponse(html)


class CycleDataManagementView(LoginRequiredMixin, CycleTrackingEnabledMixin, TemplateView):
    """
    Data management page for cycle tracking.

    Allows users to:
    - Export their data in JSON or CSV format
    - Delete all their cycle tracking data (with double confirmation)
    - View statistics about their stored data
    """

    template_name = "health/cycle/data_management.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Get data counts
        daily_logs_count = CycleDailyLog.objects.filter(user=user).count()
        cycles_count = Cycle.objects.filter(user=user).count()
        predictions_count = CyclePrediction.objects.filter(user=user).count()

        # Get date range
        oldest_log = CycleDailyLog.objects.filter(user=user).order_by("log_date").first()
        newest_log = CycleDailyLog.objects.filter(user=user).order_by("-log_date").first()

        context["stats"] = {
            "daily_logs": daily_logs_count,
            "cycles": cycles_count,
            "predictions": predictions_count,
            "date_range": {
                "oldest": oldest_log.log_date if oldest_log else None,
                "newest": newest_log.log_date if newest_log else None,
            },
        }

        return context


class CycleExportJSONView(LoginRequiredMixin, CycleTrackingEnabledMixin, View):
    """
    Export all cycle data as JSON file download.
    """

    def post(self, request):
        from django.http import HttpResponse
        from .services.cycle_export import CycleDataExportService

        service = CycleDataExportService(request.user)
        json_data = service.export_to_json_string()

        response = HttpResponse(
            json_data,
            content_type="application/json"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="cycle_data_{timezone.now().strftime("%Y%m%d")}.json"'
        )
        return response


class CycleExportCSVView(LoginRequiredMixin, CycleTrackingEnabledMixin, View):
    """
    Export cycle daily logs as CSV file download.
    """

    def post(self, request):
        from django.http import HttpResponse
        from .services.cycle_export import CycleDataExportService

        service = CycleDataExportService(request.user)

        # Export daily logs as CSV (main data)
        csv_data = service.export_to_csv(data_type="daily_logs")

        response = HttpResponse(
            csv_data,
            content_type="text/csv"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="cycle_logs_{timezone.now().strftime("%Y%m%d")}.csv"'
        )
        return response


class CycleDeleteAllView(LoginRequiredMixin, CycleTrackingEnabledMixin, View):
    """
    Delete all cycle tracking data for the user.

    Requires confirmation text to be "DELETE" to proceed.
    Redirects to opt-in page after successful deletion.
    """

    def post(self, request):
        from django.shortcuts import redirect
        from django.contrib import messages

        confirmation_text = request.POST.get("confirmation_text", "").strip().upper()

        if confirmation_text != "DELETE":
            messages.error(
                request,
                "Deletion cancelled. Confirmation text did not match."
            )
            return redirect("health:cycle_data_management")

        user = request.user

        # Count before deletion for message
        daily_logs_count = CycleDailyLog.objects.filter(user=user).count()
        cycles_count = Cycle.objects.filter(user=user).count()
        predictions_count = CyclePrediction.objects.filter(user=user).count()

        # Soft delete all data
        CycleDailyLog.objects.filter(user=user).update(deleted_at=timezone.now())
        Cycle.objects.filter(user=user).update(deleted_at=timezone.now())
        CyclePrediction.objects.filter(user=user).update(deleted_at=timezone.now())

        # Soft delete settings (disables tracking)
        try:
            settings = CycleSettings.objects.get(user=user)
            settings.soft_delete()
        except CycleSettings.DoesNotExist:
            pass

        messages.success(
            request,
            f"Deleted {daily_logs_count} logs, {cycles_count} cycles, and {predictions_count} predictions. "
            "Cycle tracking has been disabled."
        )

        return redirect("health:cycle_opt_in")


class CycleExportAPIView(LoginRequiredMixin, CycleTrackingEnabledMixin, View):
    """
    API endpoint for exporting cycle data with rate limiting.

    GET /health/api/cycle/export/?format=json
    GET /health/api/cycle/export/?format=csv

    Rate limited to 5 exports per hour per user.

    Query parameters:
        format: Export format - 'json' (default) or 'csv'

    Returns:
        - File download with Content-Disposition header
        - 429 Too Many Requests if rate limit exceeded
        - 400 Bad Request if invalid format
        - 204 No Content if user has no cycle data
    """

    # Rate limit: 5 exports per hour per user
    EXPORTS_PER_HOUR = 5
    RATE_LIMIT_KEY_PREFIX = "cycle_export_rate_limit"

    def get(self, request):
        """Handle export request with rate limiting."""
        from django.core.cache import cache
        from django.http import HttpResponse

        # Check rate limit (per user, not per IP)
        user_id = request.user.id
        hour_key = f"{self.RATE_LIMIT_KEY_PREFIX}:user:{user_id}:{timezone.now().strftime('%Y%m%d%H')}"
        export_count = cache.get(hour_key, 0)

        if export_count >= self.EXPORTS_PER_HOUR:
            return JsonResponse(
                {
                    "error": "Export rate limit exceeded. Maximum 5 exports per hour.",
                    "retry_after": 3600,
                    "exports_remaining": 0,
                },
                status=429
            )

        # Validate format parameter
        export_format = request.GET.get("format", "json").lower()
        if export_format not in ("json", "csv"):
            return JsonResponse(
                {"error": "Invalid format. Must be 'json' or 'csv'."},
                status=400
            )

        # Check if user has any data
        from .services.cycle_export import CycleDataExportService
        service = CycleDataExportService(request.user)
        size_estimate = service.get_export_size_estimate()

        total_records = (
            size_estimate["counts"]["daily_logs"]
            + size_estimate["counts"]["cycles"]
            + size_estimate["counts"]["predictions"]
        )

        if total_records == 0:
            return JsonResponse(
                {
                    "message": "No cycle data to export.",
                    "counts": size_estimate["counts"],
                },
                status=204
            )

        # Increment rate limit counter
        cache.set(hour_key, export_count + 1, timeout=3600)

        # Generate export
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")

        if export_format == "json":
            content = service.export_to_json_string()
            content_type = "application/json"
            filename = f"cycle_data_{timestamp}.json"
        else:  # csv
            content = service.export_to_csv(data_type="daily_logs")
            content_type = "text/csv"
            filename = f"cycle_logs_{timestamp}.csv"

        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["X-Exports-Remaining"] = str(self.EXPORTS_PER_HOUR - export_count - 1)

        return response


class CycleDeleteAllAPIView(LoginRequiredMixin, View):
    """
    API endpoint for deleting all cycle data with confirmation.

    POST /health/api/cycle/delete-all/

    Request body:
        {
            "confirmation": "DELETE ALL MY CYCLE DATA",
            "hard_delete": false  // optional, defaults to false (soft delete)
        }

    Returns:
        - 200 OK with counts of deleted records
        - 400 Bad Request if confirmation missing or incorrect
        - 403 Forbidden if cycle tracking not enabled

    Note: Soft delete (default) marks records as deleted but retains them for 30 days.
          Hard delete permanently removes all records and cannot be undone.
    """

    CONFIRMATION_TEXT = "DELETE ALL MY CYCLE DATA"

    def post(self, request):
        """Handle delete all request with confirmation."""
        import json
        from apps.core.security_logging import log_security_event

        user = request.user

        # Check if cycle tracking is enabled
        try:
            cycle_settings = CycleSettings.objects.get(user=user)
            if not cycle_settings.is_enabled:
                return JsonResponse(
                    {"error": "Cycle tracking is not enabled for this user."},
                    status=403
                )
        except CycleSettings.DoesNotExist:
            return JsonResponse(
                {"error": "Cycle tracking is not enabled for this user."},
                status=403
            )

        # Parse request body
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse(
                {"error": "Invalid JSON in request body."},
                status=400
            )

        # Validate confirmation
        confirmation = data.get("confirmation", "").strip()
        if confirmation != self.CONFIRMATION_TEXT:
            return JsonResponse(
                {
                    "error": "Confirmation text does not match.",
                    "expected": self.CONFIRMATION_TEXT,
                },
                status=400
            )

        # Check for hard delete option
        hard_delete = data.get("hard_delete", False)

        # Count records before deletion
        daily_logs_count = CycleDailyLog.objects.filter(user=user).count()
        cycles_count = Cycle.objects.filter(user=user).count()
        predictions_count = CyclePrediction.objects.filter(user=user).count()

        total_count = daily_logs_count + cycles_count + predictions_count + 1  # +1 for settings

        # Perform deletion
        if hard_delete:
            # Hard delete - permanently remove all records
            CycleDailyLog.all_objects.filter(user=user).delete()
            Cycle.all_objects.filter(user=user).delete()
            CyclePrediction.all_objects.filter(user=user).delete()
            CycleSettings.all_objects.filter(user=user).delete()
            deletion_type = "hard"
        else:
            # Soft delete - mark as deleted
            now = timezone.now()
            CycleDailyLog.objects.filter(user=user).update(
                status="deleted", deleted_at=now
            )
            Cycle.objects.filter(user=user).update(
                status="deleted", deleted_at=now
            )
            CyclePrediction.objects.filter(user=user).update(
                status="deleted", deleted_at=now
            )
            cycle_settings.soft_delete()
            deletion_type = "soft"

        # Create audit log entry
        log_security_event(
            event_type="data_export",  # Using data_export type for data deletion
            severity="warning",
            message=f"User deleted all cycle tracking data ({deletion_type} delete)",
            request=request,
            user=user,
            details={
                "action": "cycle_data_delete_all",
                "deletion_type": deletion_type,
                "counts": {
                    "daily_logs": daily_logs_count,
                    "cycles": cycles_count,
                    "predictions": predictions_count,
                    "settings": 1,
                },
                "total_records": total_count,
            }
        )

        return JsonResponse({
            "success": True,
            "message": f"All cycle data has been {'permanently deleted' if hard_delete else 'deleted'}.",
            "deletion_type": deletion_type,
            "counts": {
                "daily_logs": daily_logs_count,
                "cycles": cycles_count,
                "predictions": predictions_count,
                "settings": 1,
            },
            "total_deleted": total_count,
        })
