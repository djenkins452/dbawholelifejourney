"""
Sleep Tracking API Views

API views for sleep tracking data sync.
Designed to support native iOS/Android app integration with wearable data.

These use Django's class-based views with JSON responses,
following patterns similar to DRF ViewSets.
"""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Count, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import SleepEntry
from .serializers import SleepEntrySerializer


@method_decorator(csrf_exempt, name="dispatch")
class SleepEntryListCreateView(LoginRequiredMixin, View):
    """
    API endpoint for listing and creating sleep entries.

    GET /health/api/sleep/
        Returns list of sleep entries, optionally filtered by date range.
        Query params:
            - start_date: YYYY-MM-DD (default: 30 days ago)
            - end_date: YYYY-MM-DD (default: today)
            - limit: int (default: 30, max: 100)
            - offset: int (default: 0)
            - source: filter by source (optional)

    POST /health/api/sleep/
        Create a new sleep entry or bulk sync from wearable.
        Body (single entry):
        {
            "sleep_date": "2024-01-15",
            "bedtime": "2024-01-15T22:30:00-05:00",
            "wake_time": "2024-01-16T06:30:00-05:00",
            "total_duration_minutes": 480,
            "quality_rating": "good",
            "source": "apple_health",
            "sync_id": "unique-id-from-device",
            ...
        }

        Body (bulk sync):
        {
            "entries": [
                {...entry1...},
                {...entry2...}
            ]
        }
    """

    def get(self, request):
        """List sleep entries with optional filtering."""
        user = request.user

        # Parse query params
        end_date = request.GET.get("end_date")
        start_date = request.GET.get("start_date")
        limit = min(int(request.GET.get("limit", 30)), 100)
        offset = int(request.GET.get("offset", 0))
        source_filter = request.GET.get("source")

        # Default date range: last 30 days
        if end_date:
            try:
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse(
                    {"error": "Invalid end_date format. Use YYYY-MM-DD"},
                    status=400
                )
        else:
            end_date = date.today()

        if start_date:
            try:
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse(
                    {"error": "Invalid start_date format. Use YYYY-MM-DD"},
                    status=400
                )
        else:
            start_date = end_date - timedelta(days=30)

        # Build queryset
        entries = SleepEntry.objects.filter(
            user=user,
            sleep_date__gte=start_date,
            sleep_date__lte=end_date
        )

        if source_filter:
            entries = entries.filter(source=source_filter)

        total_count = entries.count()
        entries = entries.order_by("-sleep_date")[offset:offset + limit]

        # Serialize
        data = [SleepEntrySerializer(instance=e).data for e in entries]

        return JsonResponse({
            "entries": data,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        })

    def post(self, request):
        """Create new sleep entry or bulk sync."""
        user = request.user

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(
                {"error": "Invalid JSON body"},
                status=400
            )

        # Check for bulk sync
        if "entries" in body:
            return self._bulk_sync(user, body["entries"])

        # Single entry creation
        return self._create_entry(user, body)

    def _create_entry(self, user, data):
        """Create a single sleep entry."""
        serializer = SleepEntrySerializer(data=data)

        if not serializer.is_valid():
            return JsonResponse(
                {"errors": serializer.errors},
                status=400
            )

        # Check for duplicate sync_id
        sync_id = data.get("sync_id")
        if sync_id:
            existing = SleepEntry.objects.filter(
                user=user,
                sync_id=sync_id
            ).first()
            if existing:
                # Update existing instead of creating duplicate
                serializer = SleepEntrySerializer(
                    instance=existing,
                    data=data
                )
                if not serializer.is_valid():
                    return JsonResponse(
                        {"errors": serializer.errors},
                        status=400
                    )
                entry = serializer.save()
                return JsonResponse({
                    "entry": SleepEntrySerializer(instance=entry).data,
                    "action": "updated"
                })

        # Create new entry
        entry = serializer.save(user=user)
        return JsonResponse(
            {
                "entry": SleepEntrySerializer(instance=entry).data,
                "action": "created"
            },
            status=201
        )

    def _bulk_sync(self, user, entries_data):
        """Bulk sync multiple sleep entries (upsert by sync_id)."""
        results = {
            "created": 0,
            "updated": 0,
            "failed": 0,
            "errors": []
        }

        for i, data in enumerate(entries_data):
            serializer = SleepEntrySerializer(data=data)

            if not serializer.is_valid():
                results["failed"] += 1
                results["errors"].append({
                    "index": i,
                    "errors": serializer.errors
                })
                continue

            sync_id = data.get("sync_id")
            if sync_id:
                existing = SleepEntry.objects.filter(
                    user=user,
                    sync_id=sync_id
                ).first()
                if existing:
                    # Update
                    for key, value in serializer.validated_data.items():
                        setattr(existing, key, value)
                    existing.save()
                    results["updated"] += 1
                    continue

            # Create new
            serializer.save(user=user)
            results["created"] += 1

        return JsonResponse(results, status=200 if results["failed"] == 0 else 207)


@method_decorator(csrf_exempt, name="dispatch")
class SleepEntryDetailView(LoginRequiredMixin, View):
    """
    API endpoint for retrieving, updating, and deleting a single sleep entry.

    GET /health/api/sleep/<id>/
        Retrieve a single sleep entry.

    PUT/PATCH /health/api/sleep/<id>/
        Update a sleep entry.

    DELETE /health/api/sleep/<id>/
        Delete a sleep entry (soft delete).
    """

    def get_entry(self, user, entry_id):
        """Get entry for user or return error response."""
        try:
            return SleepEntry.objects.get(pk=entry_id, user=user)
        except SleepEntry.DoesNotExist:
            return None

    def get(self, request, entry_id):
        """Retrieve a single sleep entry."""
        entry = self.get_entry(request.user, entry_id)
        if not entry:
            return JsonResponse(
                {"error": "Sleep entry not found"},
                status=404
            )

        return JsonResponse({
            "entry": SleepEntrySerializer(instance=entry).data
        })

    def put(self, request, entry_id):
        """Update a sleep entry (full update)."""
        return self._update(request, entry_id)

    def patch(self, request, entry_id):
        """Update a sleep entry (partial update)."""
        return self._update(request, entry_id)

    def _update(self, request, entry_id):
        """Handle update for PUT and PATCH."""
        entry = self.get_entry(request.user, entry_id)
        if not entry:
            return JsonResponse(
                {"error": "Sleep entry not found"},
                status=404
            )

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(
                {"error": "Invalid JSON body"},
                status=400
            )

        serializer = SleepEntrySerializer(instance=entry, data=body)
        if not serializer.is_valid():
            return JsonResponse(
                {"errors": serializer.errors},
                status=400
            )

        entry = serializer.save()
        return JsonResponse({
            "entry": SleepEntrySerializer(instance=entry).data
        })

    def delete(self, request, entry_id):
        """Delete a sleep entry (soft delete)."""
        entry = self.get_entry(request.user, entry_id)
        if not entry:
            return JsonResponse(
                {"error": "Sleep entry not found"},
                status=404
            )

        entry.soft_delete()
        return JsonResponse({"deleted": True})


class SleepStatsView(LoginRequiredMixin, View):
    """
    API endpoint for sleep statistics and insights.

    GET /health/api/sleep/stats/
        Returns aggregated sleep statistics.
        Query params:
            - days: number of days to analyze (default: 30, max: 365)

    Returns:
        {
            "period_days": 30,
            "entries_count": 25,
            "avg_duration_hours": 7.2,
            "avg_asleep_hours": 6.8,
            "avg_quality_score": 72,
            "avg_sleep_efficiency": 85.5,
            "avg_deep_minutes": 65,
            "avg_rem_minutes": 90,
            "quality_breakdown": {
                "excellent": 4,
                "good": 12,
                "fair": 6,
                "poor": 3,
                "terrible": 0
            },
            "source_breakdown": {
                "manual": 5,
                "apple_health": 20
            },
            "trend": "improving" | "declining" | "stable"
        }
    """

    def get(self, request):
        user = request.user
        days = min(int(request.GET.get("days", 30)), 365)

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        entries = SleepEntry.objects.filter(
            user=user,
            sleep_date__gte=start_date,
            sleep_date__lte=end_date
        )

        count = entries.count()
        if count == 0:
            return JsonResponse({
                "period_days": days,
                "entries_count": 0,
                "message": "No sleep data for this period"
            })

        # Calculate averages
        aggregates = entries.aggregate(
            avg_duration=Avg("total_duration_minutes"),
            avg_asleep=Avg("asleep_duration_minutes"),
            avg_quality=Avg("quality_score"),
            avg_efficiency=Avg("sleep_efficiency"),
            avg_deep=Avg("stage_deep_minutes"),
            avg_rem=Avg("stage_rem_minutes"),
            avg_light=Avg("stage_light_minutes"),
            avg_awake=Avg("stage_awake_minutes"),
        )

        # Quality breakdown
        quality_breakdown = {}
        for choice in ["excellent", "good", "fair", "poor", "terrible"]:
            quality_breakdown[choice] = entries.filter(quality_rating=choice).count()

        # Source breakdown
        source_breakdown = {}
        for entry in entries.values("source").annotate(count=Count("id")):
            source_breakdown[entry["source"]] = entry["count"]

        # Calculate trend (compare first half to second half)
        mid_point = start_date + timedelta(days=days // 2)
        first_half = entries.filter(sleep_date__lt=mid_point)
        second_half = entries.filter(sleep_date__gte=mid_point)

        trend = "stable"
        if first_half.count() >= 3 and second_half.count() >= 3:
            first_avg = first_half.aggregate(avg=Avg("total_duration_minutes"))["avg"]
            second_avg = second_half.aggregate(avg=Avg("total_duration_minutes"))["avg"]
            if first_avg and second_avg:
                diff = second_avg - first_avg
                if diff > 15:  # 15 minutes improvement
                    trend = "improving"
                elif diff < -15:
                    trend = "declining"

        return JsonResponse({
            "period_days": days,
            "entries_count": count,
            "avg_duration_hours": round(aggregates["avg_duration"] / 60, 1) if aggregates["avg_duration"] else None,
            "avg_asleep_hours": round(aggregates["avg_asleep"] / 60, 1) if aggregates["avg_asleep"] else None,
            "avg_quality_score": round(aggregates["avg_quality"]) if aggregates["avg_quality"] else None,
            "avg_sleep_efficiency": round(float(aggregates["avg_efficiency"]), 1) if aggregates["avg_efficiency"] else None,
            "avg_deep_minutes": round(aggregates["avg_deep"]) if aggregates["avg_deep"] else None,
            "avg_rem_minutes": round(aggregates["avg_rem"]) if aggregates["avg_rem"] else None,
            "avg_light_minutes": round(aggregates["avg_light"]) if aggregates["avg_light"] else None,
            "avg_awake_minutes": round(aggregates["avg_awake"]) if aggregates["avg_awake"] else None,
            "quality_breakdown": quality_breakdown,
            "source_breakdown": source_breakdown,
            "trend": trend,
        })


class SleepSyncStatusView(LoginRequiredMixin, View):
    """
    API endpoint to check sync status for wearable integration.

    GET /health/api/sleep/sync-status/
        Returns the last sync info for each source.

    Returns:
        {
            "sources": {
                "apple_health": {
                    "last_sync": "2024-01-15T08:30:00Z",
                    "last_entry_date": "2024-01-15",
                    "entries_count": 45
                },
                "fitbit": null
            }
        }
    """

    def get(self, request):
        user = request.user

        sources = {}
        for source_code, source_name in SleepEntry.SOURCE_CHOICES:
            if source_code == "manual":
                continue  # Skip manual entries

            entries = SleepEntry.objects.filter(
                user=user,
                source=source_code
            )

            if entries.exists():
                latest = entries.first()
                sources[source_code] = {
                    "name": source_name,
                    "last_sync": latest.updated_at.isoformat() if hasattr(latest, "updated_at") else None,
                    "last_entry_date": latest.sleep_date.isoformat(),
                    "entries_count": entries.count()
                }
            else:
                sources[source_code] = None

        return JsonResponse({"sources": sources})
