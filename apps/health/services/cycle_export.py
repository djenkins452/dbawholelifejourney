"""
Cycle Data Export Service

Exports user cycle tracking data in JSON and CSV formats.
Supports full data export including settings, daily logs, cycles, and predictions.

Key Features:
- JSON export with complete nested structure
- CSV export with flattened structure for spreadsheets
- ISO 8601 date formatting
- Pagination for large data sets
- No PII in export metadata

Usage:
    from apps.health.services.cycle_export import CycleDataExportService

    service = CycleDataExportService(user)
    json_data = service.export_to_json()
    csv_data = service.export_to_csv()
"""

import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from django.utils import timezone

from ..models import Cycle, CycleDailyLog, CyclePrediction, CycleSettings


class CycleDataExportService:
    """
    Service for exporting cycle tracking data in JSON and CSV formats.

    Exports all cycle-related data for a user while ensuring privacy
    and proper formatting.
    """

    # Maximum records per export type to prevent memory issues
    MAX_DAILY_LOGS = 1000
    MAX_CYCLES = 100
    MAX_PREDICTIONS = 50

    # Export version for data structure compatibility tracking
    EXPORT_VERSION = "1.0"

    def __init__(self, user):
        """
        Initialize the export service for a specific user.

        Args:
            user: The User instance to export data for
        """
        self.user = user

    def _serialize_date(self, value: Optional[date]) -> Optional[str]:
        """
        Serialize a date to ISO 8601 format.

        Args:
            value: Date to serialize

        Returns:
            ISO 8601 formatted string or None
        """
        if value is None:
            return None
        return value.isoformat()

    def _serialize_datetime(self, value: Optional[datetime]) -> Optional[str]:
        """
        Serialize a datetime to ISO 8601 format.

        Args:
            value: Datetime to serialize

        Returns:
            ISO 8601 formatted string or None
        """
        if value is None:
            return None
        return value.isoformat()

    def _serialize_decimal(self, value: Optional[Decimal]) -> Optional[float]:
        """
        Serialize a Decimal to float for JSON.

        Args:
            value: Decimal to serialize

        Returns:
            Float value or None
        """
        if value is None:
            return None
        return float(value)

    def _get_settings_data(self) -> Optional[dict]:
        """
        Get cycle settings for the user.

        Returns:
            Settings dict or None if not configured
        """
        try:
            settings = CycleSettings.objects.get(user=self.user)
            return {
                "cycle_tracking_enabled": settings.cycle_tracking_enabled,
                "average_cycle_length": settings.average_cycle_length,
                "average_period_length": settings.average_period_length,
                "notifications_enabled": settings.notifications_enabled,
                "fertile_window_tracking_enabled": settings.fertile_window_tracking_enabled,
                "last_period_start_date": self._serialize_date(
                    settings.last_period_start_date
                ),
            }
        except CycleSettings.DoesNotExist:
            return None

    def _get_daily_logs_data(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> list[dict]:
        """
        Get daily log entries for the user.

        Args:
            limit: Maximum number of records to return
            offset: Starting offset for pagination

        Returns:
            List of daily log dictionaries
        """
        effective_limit = limit or self.MAX_DAILY_LOGS
        logs = CycleDailyLog.objects.filter(user=self.user).order_by("-log_date")[
            offset : offset + effective_limit
        ]

        return [
            {
                "id": log.id,
                "log_date": self._serialize_date(log.log_date),
                "flow_level": log.flow_level,
                "symptoms": log.symptoms,
                "mood": log.mood or None,
                "energy_level": log.energy_level,
                "cervical_mucus": log.cervical_mucus or None,
                "basal_temp": self._serialize_decimal(log.basal_temp),
                "notes": log.notes or None,
                "created_at": self._serialize_datetime(log.created_at),
                "updated_at": self._serialize_datetime(log.updated_at),
            }
            for log in logs
        ]

    def _get_cycles_data(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> list[dict]:
        """
        Get cycle records for the user.

        Args:
            limit: Maximum number of records to return
            offset: Starting offset for pagination

        Returns:
            List of cycle dictionaries
        """
        effective_limit = limit or self.MAX_CYCLES
        cycles = Cycle.objects.filter(user=self.user).order_by("-start_date")[
            offset : offset + effective_limit
        ]

        return [
            {
                "id": cycle.id,
                "cycle_number": cycle.cycle_number,
                "start_date": self._serialize_date(cycle.start_date),
                "end_date": self._serialize_date(cycle.end_date),
                "period_end_date": self._serialize_date(cycle.period_end_date),
                "cycle_length": cycle.cycle_length,
                "period_length": cycle.period_length,
                "is_predicted": cycle.is_predicted,
                "is_complete": cycle.is_complete,
                "notes": cycle.notes or None,
                "created_at": self._serialize_datetime(cycle.created_at),
                "updated_at": self._serialize_datetime(cycle.updated_at),
            }
            for cycle in cycles
        ]

    def _get_predictions_data(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> list[dict]:
        """
        Get prediction records for the user.

        Args:
            limit: Maximum number of records to return
            offset: Starting offset for pagination

        Returns:
            List of prediction dictionaries
        """
        effective_limit = limit or self.MAX_PREDICTIONS
        predictions = CyclePrediction.objects.filter(user=self.user).order_by(
            "-generated_at"
        )[offset : offset + effective_limit]

        return [
            {
                "id": prediction.id,
                "predicted_period_start": self._serialize_date(
                    prediction.predicted_period_start
                ),
                "predicted_period_end": self._serialize_date(
                    prediction.predicted_period_end
                ),
                "predicted_fertile_window_start": self._serialize_date(
                    prediction.predicted_fertile_window_start
                ),
                "predicted_fertile_window_end": self._serialize_date(
                    prediction.predicted_fertile_window_end
                ),
                "prediction_confidence": self._serialize_decimal(
                    prediction.prediction_confidence
                ),
                "prediction_algorithm_version": prediction.prediction_algorithm_version,
                "generated_at": self._serialize_datetime(prediction.generated_at),
                "actual_period_start": self._serialize_date(
                    prediction.actual_period_start
                ),
                "accuracy_days": prediction.accuracy,
                "created_at": self._serialize_datetime(prediction.created_at),
                "updated_at": self._serialize_datetime(prediction.updated_at),
            }
            for prediction in predictions
        ]

    def _get_export_metadata(self) -> dict:
        """
        Generate export metadata without PII.

        Returns:
            Metadata dict with export info
        """
        return {
            "export_version": self.EXPORT_VERSION,
            "exported_at": timezone.now().isoformat(),
            "data_type": "cycle_tracking",
            "record_counts": {
                "daily_logs": CycleDailyLog.objects.filter(user=self.user).count(),
                "cycles": Cycle.objects.filter(user=self.user).count(),
                "predictions": CyclePrediction.objects.filter(user=self.user).count(),
            },
        }

    def export_to_json(
        self,
        include_settings: bool = True,
        include_daily_logs: bool = True,
        include_cycles: bool = True,
        include_predictions: bool = True,
        daily_logs_limit: Optional[int] = None,
        cycles_limit: Optional[int] = None,
        predictions_limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Export cycle data as a JSON-compatible dictionary.

        Args:
            include_settings: Include cycle settings
            include_daily_logs: Include daily log entries
            include_cycles: Include cycle records
            include_predictions: Include predictions
            daily_logs_limit: Max daily logs to include
            cycles_limit: Max cycles to include
            predictions_limit: Max predictions to include

        Returns:
            Dictionary with all requested cycle data
        """
        export_data = {
            "metadata": self._get_export_metadata(),
        }

        if include_settings:
            export_data["settings"] = self._get_settings_data()

        if include_daily_logs:
            export_data["daily_logs"] = self._get_daily_logs_data(
                limit=daily_logs_limit
            )

        if include_cycles:
            export_data["cycles"] = self._get_cycles_data(limit=cycles_limit)

        if include_predictions:
            export_data["predictions"] = self._get_predictions_data(
                limit=predictions_limit
            )

        return export_data

    def export_to_json_string(self, **kwargs) -> str:
        """
        Export cycle data as a JSON string.

        Args:
            **kwargs: Arguments passed to export_to_json

        Returns:
            JSON formatted string
        """
        data = self.export_to_json(**kwargs)
        return json.dumps(data, indent=2, ensure_ascii=False)

    def export_to_csv(
        self,
        data_type: str = "daily_logs",
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> str:
        """
        Export cycle data as CSV format.

        Flattens the data structure for spreadsheet compatibility.

        Args:
            data_type: Type of data to export ('daily_logs', 'cycles', 'predictions')
            limit: Maximum number of records
            offset: Starting offset for pagination

        Returns:
            CSV formatted string

        Raises:
            ValueError: If data_type is invalid
        """
        output = io.StringIO()

        if data_type == "daily_logs":
            self._export_daily_logs_csv(output, limit, offset)
        elif data_type == "cycles":
            self._export_cycles_csv(output, limit, offset)
        elif data_type == "predictions":
            self._export_predictions_csv(output, limit, offset)
        else:
            raise ValueError(
                f"Invalid data_type: {data_type}. "
                "Must be 'daily_logs', 'cycles', or 'predictions'"
            )

        return output.getvalue()

    def _export_daily_logs_csv(
        self, output: io.StringIO, limit: Optional[int], offset: int
    ) -> None:
        """
        Export daily logs to CSV format.

        Args:
            output: StringIO to write to
            limit: Maximum records
            offset: Starting offset
        """
        fieldnames = [
            "id",
            "log_date",
            "flow_level",
            "symptoms",
            "mood",
            "energy_level",
            "cervical_mucus",
            "basal_temp",
            "notes",
            "created_at",
            "updated_at",
        ]

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        data = self._get_daily_logs_data(limit=limit, offset=offset)
        for row in data:
            # Flatten symptoms list to comma-separated string
            row["symptoms"] = ",".join(row["symptoms"]) if row["symptoms"] else ""
            writer.writerow(row)

    def _export_cycles_csv(
        self, output: io.StringIO, limit: Optional[int], offset: int
    ) -> None:
        """
        Export cycles to CSV format.

        Args:
            output: StringIO to write to
            limit: Maximum records
            offset: Starting offset
        """
        fieldnames = [
            "id",
            "cycle_number",
            "start_date",
            "end_date",
            "period_end_date",
            "cycle_length",
            "period_length",
            "is_predicted",
            "is_complete",
            "notes",
            "created_at",
            "updated_at",
        ]

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        data = self._get_cycles_data(limit=limit, offset=offset)
        for row in data:
            writer.writerow(row)

    def _export_predictions_csv(
        self, output: io.StringIO, limit: Optional[int], offset: int
    ) -> None:
        """
        Export predictions to CSV format.

        Args:
            output: StringIO to write to
            limit: Maximum records
            offset: Starting offset
        """
        fieldnames = [
            "id",
            "predicted_period_start",
            "predicted_period_end",
            "predicted_fertile_window_start",
            "predicted_fertile_window_end",
            "prediction_confidence",
            "prediction_algorithm_version",
            "generated_at",
            "actual_period_start",
            "accuracy_days",
            "created_at",
            "updated_at",
        ]

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        data = self._get_predictions_data(limit=limit, offset=offset)
        for row in data:
            writer.writerow(row)

    def get_export_size_estimate(self) -> dict:
        """
        Estimate the size of a full export.

        Returns:
            Dictionary with estimated sizes and counts
        """
        daily_logs_count = CycleDailyLog.objects.filter(user=self.user).count()
        cycles_count = Cycle.objects.filter(user=self.user).count()
        predictions_count = CyclePrediction.objects.filter(user=self.user).count()

        # Rough estimates based on average record sizes
        estimated_json_size = (
            daily_logs_count * 300  # ~300 bytes per daily log
            + cycles_count * 200  # ~200 bytes per cycle
            + predictions_count * 250  # ~250 bytes per prediction
            + 500  # Metadata and settings
        )

        estimated_csv_size = (
            daily_logs_count * 150  # ~150 bytes per daily log row
            + cycles_count * 120  # ~120 bytes per cycle row
            + predictions_count * 180  # ~180 bytes per prediction row
            + 300  # Headers
        )

        return {
            "counts": {
                "daily_logs": daily_logs_count,
                "cycles": cycles_count,
                "predictions": predictions_count,
            },
            "estimated_json_bytes": estimated_json_size,
            "estimated_csv_bytes": estimated_csv_size,
            "would_paginate": {
                "daily_logs": daily_logs_count > self.MAX_DAILY_LOGS,
                "cycles": cycles_count > self.MAX_CYCLES,
                "predictions": predictions_count > self.MAX_PREDICTIONS,
            },
        }
