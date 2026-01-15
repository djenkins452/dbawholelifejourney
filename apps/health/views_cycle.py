"""
Cycle Tracking Views

API views for cycle tracking features.
These use Django's class-based views with JSON responses,
following patterns similar to DRF ViewSets.
"""

import json

from django.contrib.auth.mixins import LoginRequiredMixin
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
from .serializers import CycleSettingsSerializer


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
