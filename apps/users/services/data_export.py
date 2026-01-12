# ==============================================================================
# File: apps/users/services/data_export.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: GDPR data export service for user data portability
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12 (CISO Security Review)
# Last Updated: 2026-01-12
# ==============================================================================
"""
GDPR Data Export Service

Provides user data export functionality for GDPR compliance (data portability).
Supports multiple export formats: JSON, CSV, and PDF.

Security Notes:
    - Only exports data owned by the requesting user
    - Excludes sensitive system fields (password hashes, tokens)
    - Logs all export requests for audit purposes
    - Rate limited at the view level
"""

import csv
import io
import json
import logging
import zipfile
from datetime import datetime
from typing import Any

from django.apps import apps
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)

User = get_user_model()


class DataExportService:
    """
    Service class for exporting user data in various formats.

    Supported formats:
        - JSON: Machine-readable, single file
        - CSV: Spreadsheet-compatible, one file per data type in ZIP
    """

    # Models to export, grouped by app
    # Format: (app_label, model_name, human_readable_name)
    EXPORTABLE_MODELS = [
        # User data
        ('users', 'User', 'Profile'),
        ('users', 'UserPreferences', 'Preferences'),

        # Journal
        ('journal', 'JournalEntry', 'Journal Entries'),

        # Health
        ('health', 'WeightEntry', 'Weight Entries'),
        ('health', 'FastEntry', 'Fasting Entries'),
        ('health', 'FoodEntry', 'Food Entries'),
        ('health', 'MealFoodItem', 'Meal Items'),
        ('health', 'Exercise', 'Exercise Entries'),
        ('health', 'SleepEntry', 'Sleep Entries'),
        ('health', 'Medicine', 'Medications'),
        ('health', 'MedicineLog', 'Medication Logs'),
        ('health', 'GlucoseReading', 'Glucose Readings'),

        # Faith
        ('faith', 'PrayerRequest', 'Prayer Requests'),
        ('faith', 'ScriptureReflection', 'Scripture Reflections'),
        ('faith', 'FaithMilestone', 'Faith Milestones'),
        ('faith', 'DailyReflection', 'Daily Reflections'),

        # Life/Tasks
        ('life', 'Task', 'Tasks'),
        ('life', 'Project', 'Projects'),
        ('life', 'Goal', 'Goals'),

        # Finance
        ('finance', 'BankConnection', 'Bank Connections'),
        ('finance', 'Budget', 'Budgets'),
        ('finance', 'Transaction', 'Transactions'),

        # Purpose
        ('purpose', 'LifeDirection', 'Life Directions'),
        ('purpose', 'LifeRole', 'Life Roles'),
    ]

    # Fields to exclude from export (sensitive/system fields)
    EXCLUDED_FIELDS = {
        'password', 'api_key', 'access_token', 'refresh_token',
        'secret', 'token', 'key', 'hash', 'salt',
    }

    def __init__(self, user: User):
        self.user = user
        self.export_timestamp = timezone.now()

    def export_json(self) -> str:
        """
        Export all user data as a JSON string.

        Returns:
            JSON string containing all user data
        """
        data = self._collect_all_data()
        return json.dumps(data, indent=2, default=str, ensure_ascii=False)

    def export_csv_zip(self) -> bytes:
        """
        Export all user data as a ZIP file containing CSV files.

        Returns:
            Bytes containing the ZIP file
        """
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add metadata file
            metadata = {
                'export_date': self.export_timestamp.isoformat(),
                'user_email': self.user.email,
                'format': 'CSV',
            }
            zip_file.writestr(
                'export_metadata.json',
                json.dumps(metadata, indent=2)
            )

            # Export each model as a separate CSV
            for app_label, model_name, display_name in self.EXPORTABLE_MODELS:
                try:
                    csv_content = self._export_model_csv(app_label, model_name)
                    if csv_content:
                        filename = f"{display_name.lower().replace(' ', '_')}.csv"
                        zip_file.writestr(filename, csv_content)
                except Exception as e:
                    logger.warning(f"Failed to export {app_label}.{model_name}: {e}")

        zip_buffer.seek(0)
        return zip_buffer.read()

    def _collect_all_data(self) -> dict:
        """Collect all user data into a dictionary."""
        data = {
            'export_metadata': {
                'export_date': self.export_timestamp.isoformat(),
                'user_email': self.user.email,
                'format': 'JSON',
            },
            'data': {}
        }

        for app_label, model_name, display_name in self.EXPORTABLE_MODELS:
            try:
                model_data = self._export_model_data(app_label, model_name)
                if model_data:
                    key = display_name.lower().replace(' ', '_')
                    data['data'][key] = model_data
            except Exception as e:
                logger.warning(f"Failed to export {app_label}.{model_name}: {e}")

        return data

    def _export_model_data(self, app_label: str, model_name: str) -> list[dict]:
        """Export data for a single model as list of dicts."""
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            return []

        # Handle User model specially (single record, no user FK)
        if model_name == 'User':
            return [self._serialize_instance(self.user)]

        # Handle UserPreferences specially (OneToOne, no user FK filter)
        if model_name == 'UserPreferences':
            try:
                prefs = self.user.preferences
                return [self._serialize_instance(prefs)]
            except Exception:
                return []

        # For other models, filter by user
        if hasattr(model, 'user'):
            # Use all_objects if available (for soft-delete models)
            manager = getattr(model, 'all_objects', model.objects)
            queryset = manager.filter(user=self.user)
            return [self._serialize_instance(obj) for obj in queryset]

        return []

    def _export_model_csv(self, app_label: str, model_name: str) -> str | None:
        """Export data for a single model as CSV string."""
        data = self._export_model_data(app_label, model_name)
        if not data:
            return None

        output = io.StringIO()
        if data:
            # Get all unique keys from all records
            all_keys = set()
            for record in data:
                all_keys.update(record.keys())
            fieldnames = sorted(all_keys)

            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data)

        return output.getvalue()

    def _serialize_instance(self, instance: Any) -> dict:
        """Serialize a model instance to a dictionary."""
        data = {}

        for field in instance._meta.get_fields():
            # Skip reverse relations
            if field.is_relation and not field.concrete:
                continue

            # Skip excluded fields
            field_name = field.name
            if any(excluded in field_name.lower() for excluded in self.EXCLUDED_FIELDS):
                continue

            try:
                value = getattr(instance, field_name, None)

                # Handle special types
                if value is None:
                    data[field_name] = None
                elif isinstance(value, datetime):
                    data[field_name] = value.isoformat()
                elif hasattr(value, 'pk'):
                    # Foreign key - just store the ID
                    data[field_name] = value.pk
                elif hasattr(value, '__iter__') and not isinstance(value, (str, bytes, dict)):
                    # ManyToMany or similar - store as list of IDs
                    data[field_name] = list(value.values_list('pk', flat=True))
                else:
                    # Try to make it JSON-serializable
                    try:
                        json.dumps(value)
                        data[field_name] = value
                    except (TypeError, ValueError):
                        data[field_name] = str(value)

            except Exception as e:
                logger.debug(f"Could not serialize field {field_name}: {e}")

        return data


def export_user_data(user: User, export_format: str = 'json') -> tuple[bytes, str, str]:
    """
    Export user data in the specified format.

    Args:
        user: The user whose data to export
        export_format: 'json' or 'csv'

    Returns:
        Tuple of (content_bytes, content_type, filename)
    """
    service = DataExportService(user)
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')

    if export_format == 'csv':
        content = service.export_csv_zip()
        content_type = 'application/zip'
        filename = f'wlj_data_export_{timestamp}.zip'
    else:
        content = service.export_json().encode('utf-8')
        content_type = 'application/json'
        filename = f'wlj_data_export_{timestamp}.json'

    logger.info(f"Data export completed for user {user.id} in {export_format} format")
    return content, content_type, filename
