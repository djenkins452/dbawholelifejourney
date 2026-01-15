"""
Cycle Tracking Serializers

Serialization classes for cycle tracking models.
These follow Django REST Framework patterns but use Django's core
functionality, making it easy to migrate to DRF if needed.

Usage:
    serializer = CycleDailyLogSerializer(instance=daily_log)
    data = serializer.data  # Returns dict

    # For deserialization:
    serializer = CycleDailyLogSerializer(data=request_data)
    if serializer.is_valid():
        instance = serializer.save(user=request.user)
"""

from datetime import date
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    Cycle,
    CycleDailyLog,
    CyclePrediction,
    CycleSettings,
    CYCLE_MOOD_CHOICES,
    CYCLE_SYMPTOM_CHOICES,
    FLOW_LEVEL_CHOICES,
    CERVICAL_MUCUS_CHOICES,
)


class BaseSerializer:
    """
    Base serializer class providing DRF-like interface.

    Subclasses define `fields` dict mapping field names to their types,
    and can override validate_<field> methods for field validation.
    """

    model = None
    fields = {}
    read_only_fields = []

    def __init__(self, instance=None, data=None, **kwargs):
        self.instance = instance
        self.initial_data = data
        self.validated_data = {}
        self.errors = {}
        self._context = kwargs.get("context", {})

    @property
    def data(self):
        """Serialize instance to dict."""
        if self.instance is None:
            return {}
        return self._serialize(self.instance)

    def _serialize(self, instance):
        """Convert model instance to dict."""
        result = {}
        for field_name in self.fields:
            value = getattr(instance, field_name, None)
            result[field_name] = self._serialize_value(value)
        return result

    def _serialize_value(self, value):
        """Serialize individual values to JSON-compatible types."""
        if value is None:
            return None
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if hasattr(value, "pk"):  # Related object
            return value.pk
        return value

    def is_valid(self, raise_exception=False):
        """Validate input data."""
        if self.initial_data is None:
            self.errors = {"non_field_errors": ["No data provided"]}
            if raise_exception:
                raise ValidationError(self.errors)
            return False

        self.errors = {}
        self.validated_data = {}

        for field_name, field_type in self.fields.items():
            if field_name in self.read_only_fields:
                continue

            value = self.initial_data.get(field_name)

            # Run field-specific validation
            validate_method = getattr(self, f"validate_{field_name}", None)
            if validate_method:
                try:
                    value = validate_method(value)
                except ValidationError as e:
                    self.errors[field_name] = e.messages if hasattr(e, "messages") else [str(e)]
                    continue

            if value is not None:
                self.validated_data[field_name] = value

        # Run object-level validation
        try:
            self.validate(self.validated_data)
        except ValidationError as e:
            if hasattr(e, "message_dict"):
                self.errors.update(e.message_dict)
            else:
                self.errors["non_field_errors"] = e.messages if hasattr(e, "messages") else [str(e)]

        if self.errors and raise_exception:
            raise ValidationError(self.errors)

        return not self.errors

    def validate(self, data):
        """Object-level validation. Override in subclasses."""
        return data

    def save(self, **kwargs):
        """Create or update instance."""
        if not self.validated_data and not kwargs:
            raise ValueError("No validated data to save")

        data = {**self.validated_data, **kwargs}

        if self.instance:
            for key, value in data.items():
                setattr(self.instance, key, value)
            self.instance.save()
            return self.instance
        else:
            return self.model.objects.create(**data)


class CycleSettingsSerializer(BaseSerializer):
    """
    Serializer for CycleSettings model.

    Handles all user preferences for cycle tracking.
    """

    model = CycleSettings
    fields = {
        "id": "int",
        "cycle_tracking_enabled": "bool",
        "average_cycle_length": "int",
        "average_period_length": "int",
        "notifications_enabled": "bool",
        "fertile_window_tracking_enabled": "bool",
        "last_period_start_date": "date",
    }
    read_only_fields = ["id"]

    def validate_average_cycle_length(self, value):
        """Validate cycle length is within normal range."""
        if value is None:
            return value
        if not isinstance(value, int):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValidationError("Cycle length must be a number")
        if value < 15 or value > 60:
            raise ValidationError("Cycle length should be between 15 and 60 days")
        return value

    def validate_average_period_length(self, value):
        """Validate period length is within normal range."""
        if value is None:
            return value
        if not isinstance(value, int):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValidationError("Period length must be a number")
        if value < 1 or value > 14:
            raise ValidationError("Period length should be between 1 and 14 days")
        return value

    def validate_last_period_start_date(self, value):
        """Validate date format and ensure it's not in the future."""
        if value is None:
            return value
        if isinstance(value, str):
            try:
                from datetime import datetime
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                raise ValidationError("Invalid date format. Use YYYY-MM-DD")
        if value > date.today():
            raise ValidationError("Last period start date cannot be in the future")
        return value


class CycleDailyLogSerializer(BaseSerializer):
    """
    Serializer for CycleDailyLog model.

    Handles daily logging with symptom list validation.
    """

    model = CycleDailyLog
    fields = {
        "id": "int",
        "log_date": "date",
        "flow_level": "choice",
        "symptoms": "list",
        "mood": "choice",
        "energy_level": "int",
        "cervical_mucus": "choice",
        "basal_temp": "decimal",
        "notes": "str",
        "is_period_day": "bool",  # Read-only property
    }
    read_only_fields = ["id", "is_period_day"]

    # Valid choices for validation
    VALID_SYMPTOMS = [choice[0] for choice in CYCLE_SYMPTOM_CHOICES]
    VALID_MOODS = [choice[0] for choice in CYCLE_MOOD_CHOICES]
    VALID_FLOW_LEVELS = [choice[0] for choice in FLOW_LEVEL_CHOICES]
    VALID_CERVICAL_MUCUS = [choice[0] for choice in CERVICAL_MUCUS_CHOICES]

    def _serialize(self, instance):
        """Override to include the is_period_day property."""
        data = super()._serialize(instance)
        data["is_period_day"] = instance.is_period_day
        return data

    def validate_log_date(self, value):
        """Validate date format."""
        if value is None:
            return date.today()  # Default to today
        if isinstance(value, str):
            try:
                from datetime import datetime
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                raise ValidationError("Invalid date format. Use YYYY-MM-DD")
        return value

    def validate_symptoms(self, value):
        """Validate symptoms list contains valid choices."""
        if value is None:
            return []
        if isinstance(value, str):
            import json
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = [value]  # Single symptom as string
        if not isinstance(value, list):
            raise ValidationError("Symptoms must be a list")
        invalid = [s for s in value if s not in self.VALID_SYMPTOMS]
        if invalid:
            raise ValidationError(
                f"Invalid symptom(s): {', '.join(invalid)}. "
                f"Valid options: {', '.join(self.VALID_SYMPTOMS)}"
            )
        return value

    def validate_mood(self, value):
        """Validate mood is a valid choice."""
        if not value:
            return ""
        if value not in self.VALID_MOODS:
            raise ValidationError(
                f"Invalid mood: {value}. Valid options: {', '.join(self.VALID_MOODS)}"
            )
        return value

    def validate_flow_level(self, value):
        """Validate flow level is a valid choice."""
        if not value:
            return "none"
        if value not in self.VALID_FLOW_LEVELS:
            raise ValidationError(
                f"Invalid flow level: {value}. Valid options: {', '.join(self.VALID_FLOW_LEVELS)}"
            )
        return value

    def validate_cervical_mucus(self, value):
        """Validate cervical mucus is a valid choice."""
        if not value:
            return ""
        if value not in self.VALID_CERVICAL_MUCUS:
            raise ValidationError(
                f"Invalid cervical mucus type: {value}. "
                f"Valid options: {', '.join(self.VALID_CERVICAL_MUCUS)}"
            )
        return value

    def validate_energy_level(self, value):
        """Validate energy level is 1-10."""
        if value is None:
            return None
        if not isinstance(value, int):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValidationError("Energy level must be a number")
        if value < 1 or value > 10:
            raise ValidationError("Energy level must be between 1 and 10")
        return value

    def validate_basal_temp(self, value):
        """Validate basal temperature is in reasonable range."""
        if value is None:
            return None
        if not isinstance(value, (int, float, Decimal)):
            try:
                value = Decimal(str(value))
            except:
                raise ValidationError("Basal temperature must be a number")
        if value < 95 or value > 105:
            raise ValidationError(
                "Basal temperature should be between 95°F and 105°F"
            )
        return Decimal(str(value))


class CycleSerializer(BaseSerializer):
    """
    Serializer for Cycle model.

    Includes nested daily logs (read-only) for complete cycle view.
    """

    model = Cycle
    fields = {
        "id": "int",
        "cycle_number": "int",
        "start_date": "date",
        "end_date": "date",
        "period_end_date": "date",
        "is_predicted": "bool",
        "notes": "str",
        "cycle_length": "int",  # Read-only property
        "period_length": "int",  # Read-only property
        "is_complete": "bool",  # Read-only property
        "is_ongoing": "bool",  # Read-only property
    }
    read_only_fields = ["id", "cycle_number", "cycle_length", "period_length", "is_complete", "is_ongoing"]

    def _serialize(self, instance):
        """Override to include computed properties and nested daily logs."""
        data = super()._serialize(instance)

        # Add computed properties
        data["cycle_length"] = instance.cycle_length
        data["period_length"] = instance.period_length
        data["is_complete"] = instance.is_complete
        data["is_ongoing"] = instance.is_ongoing

        # Add nested daily logs if within the cycle dates
        if self._context.get("include_daily_logs", False):
            daily_logs = CycleDailyLog.objects.filter(
                user=instance.user,
                log_date__gte=instance.start_date,
            )
            if instance.end_date:
                daily_logs = daily_logs.filter(log_date__lte=instance.end_date)

            data["daily_logs"] = [
                CycleDailyLogSerializer(instance=log).data
                for log in daily_logs.order_by("log_date")
            ]

        return data

    def validate_start_date(self, value):
        """Validate start date format."""
        if value is None:
            raise ValidationError("Start date is required")
        if isinstance(value, str):
            try:
                from datetime import datetime
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                raise ValidationError("Invalid date format. Use YYYY-MM-DD")
        return value

    def validate_end_date(self, value):
        """Validate end date format."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                from datetime import datetime
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                raise ValidationError("Invalid date format. Use YYYY-MM-DD")
        return value

    def validate(self, data):
        """Ensure end_date is after start_date."""
        start = data.get("start_date")
        end = data.get("end_date")
        if start and end and end < start:
            raise ValidationError({"end_date": "End date must be after start date"})
        return data


class CyclePredictionSerializer(BaseSerializer):
    """
    Serializer for CyclePrediction model.

    Includes formatted confidence display.
    """

    model = CyclePrediction
    fields = {
        "id": "int",
        "predicted_period_start": "date",
        "predicted_period_end": "date",
        "predicted_fertile_window_start": "date",
        "predicted_fertile_window_end": "date",
        "prediction_confidence": "decimal",
        "prediction_algorithm_version": "str",
        "generated_at": "datetime",
        "actual_period_start": "date",
        "accuracy": "int",  # Read-only property
        "is_verified": "bool",  # Read-only property
        "accuracy_percentage": "int",  # Read-only property
        "confidence_display": "str",  # Computed field
    }
    read_only_fields = [
        "id", "accuracy", "is_verified", "accuracy_percentage",
        "confidence_display", "generated_at"
    ]

    def _serialize(self, instance):
        """Override to include computed properties and confidence display."""
        data = super()._serialize(instance)

        # Add computed properties
        data["accuracy"] = instance.accuracy
        data["is_verified"] = instance.is_verified
        data["accuracy_percentage"] = instance.accuracy_percentage

        # Format confidence as percentage string
        confidence = instance.prediction_confidence
        if confidence is not None:
            data["confidence_display"] = f"{float(confidence) * 100:.0f}%"
        else:
            data["confidence_display"] = "N/A"

        return data

    def _serialize_value(self, value):
        """Extended to handle datetime."""
        from datetime import datetime
        if isinstance(value, datetime):
            return value.isoformat()
        return super()._serialize_value(value)

    def validate_prediction_confidence(self, value):
        """Validate confidence is between 0 and 1."""
        if value is None:
            raise ValidationError("Prediction confidence is required")
        if not isinstance(value, (int, float, Decimal)):
            try:
                value = Decimal(str(value))
            except:
                raise ValidationError("Confidence must be a number")
        if value < 0 or value > 1:
            raise ValidationError("Confidence must be between 0 and 1")
        return Decimal(str(value))

    def validate_predicted_period_start(self, value):
        """Validate date format."""
        if value is None:
            raise ValidationError("Predicted period start is required")
        if isinstance(value, str):
            try:
                from datetime import datetime
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                raise ValidationError("Invalid date format. Use YYYY-MM-DD")
        return value

    def validate_predicted_period_end(self, value):
        """Validate date format."""
        if value is None:
            raise ValidationError("Predicted period end is required")
        if isinstance(value, str):
            try:
                from datetime import datetime
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                raise ValidationError("Invalid date format. Use YYYY-MM-DD")
        return value

    def validate(self, data):
        """Ensure predicted_period_end is after predicted_period_start."""
        start = data.get("predicted_period_start")
        end = data.get("predicted_period_end")
        if start and end and end < start:
            raise ValidationError({
                "predicted_period_end": "Predicted period end must be after start"
            })
        return data
