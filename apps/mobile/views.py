"""
Mobile API Views

Endpoints for iOS app integration:
- Token exchange (web session -> API token)
- Token revocation
- Health data ingestion
- Sync status

All endpoints return JSON responses.

Security Note on @csrf_exempt:
----------------------------
POST endpoints in this module use @csrf_exempt because they are REST API endpoints
for native mobile apps (iOS). These endpoints use Bearer token authentication
via the Authorization header, not session cookies. Since CSRF attacks rely on
browser cookies being automatically sent, CSRF protection is not applicable to
API endpoints that don't use cookie-based authentication.

The @require_mobile_auth decorator validates Bearer tokens for all protected
endpoints, providing the appropriate authentication mechanism for API clients.
"""

import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.health.models import (
    BloodOxygenEntry,
    BloodPressureEntry,
    BodyTemperatureEntry,
    GlucoseEntry,
    StepsEntry,
    SleepEntry,
    WaterEntry,
    WeightEntry,
    WorkoutSession,
)

from apps.core.utils import hash_pii
from .middleware import get_client_ip, require_auth, require_mobile_auth
from .models import (
    HealthIngestionRun,
    MobileAPIToken,
    MobileDevice,
    MobileTokenExchangeCode,
)

logger = logging.getLogger(__name__)

# Maximum payload size: 1MB
MAX_PAYLOAD_SIZE = 1024 * 1024
# Maximum metrics per request
MAX_METRICS_PER_REQUEST = 5000


# =============================================================================
# Token Exchange Views
# =============================================================================


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def generate_exchange_code(request):
    """
    Generate a one-time code for native app token exchange.

    Called from web JS when user wants to authenticate native app.
    The code is passed to the native app via JS bridge.

    POST /api/mobile/generate-code/
    Response: {"code": "abc123...", "expires_in": 300}
    """
    # Clean up old codes for this user
    MobileTokenExchangeCode.objects.filter(
        user=request.user,
        is_used=False,
        expires_at__lt=timezone.now(),
    ).delete()

    # Create new code
    code = MobileTokenExchangeCode.create_code(request.user)

    logger.info(f"Generated exchange code for {hash_pii(request.user.email, 'user')}")

    return JsonResponse({
        "code": code.code,
        "expires_in": 300,  # 5 minutes
    })


@csrf_exempt
@require_http_methods(["POST"])
def exchange_token(request):
    """
    Exchange a one-time code for an API token.

    Called by native app after receiving code from JS bridge.

    POST /api/mobile/token/exchange/
    Body: {
        "code": "abc123...",
        "device_id": "uuid-from-keychain",
        "device_name": "Danny's iPhone",
        "device_model": "iPhone 15 Pro",
        "os_version": "iOS 17.2",
        "app_version": "1.0.0"
    }

    Response (success): {
        "token": "full-token-here",
        "expires_at": "2024-06-15T12:00:00Z",
        "user": {"id": 1, "email": "user@example.com"}
    }

    Response (error): {
        "error": "invalid_code",
        "message": "Code is invalid or expired"
    }
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "invalid_json", "message": "Invalid JSON body"},
            status=400,
        )

    # Validate required fields
    code_value = data.get("code", "").strip()
    device_id = data.get("device_id", "").strip()

    if not code_value:
        return JsonResponse(
            {"error": "missing_code", "message": "code is required"},
            status=400,
        )

    if not device_id:
        return JsonResponse(
            {"error": "missing_device_id", "message": "device_id is required"},
            status=400,
        )

    # Find and validate code
    try:
        exchange_code = MobileTokenExchangeCode.objects.select_related("user").get(
            code=code_value,
            is_used=False,
        )
    except MobileTokenExchangeCode.DoesNotExist:
        logger.warning(f"Invalid exchange code attempt: {code_value[:8]}...")
        return JsonResponse(
            {"error": "invalid_code", "message": "Code is invalid or already used"},
            status=400,
        )

    # Check expiration
    if exchange_code.expires_at < timezone.now():
        logger.warning(f"Expired exchange code attempt: {code_value[:8]}...")
        return JsonResponse(
            {"error": "expired_code", "message": "Code has expired"},
            status=400,
        )

    user = exchange_code.user
    client_ip = get_client_ip(request)

    with transaction.atomic():
        # Get or create device
        device, created = MobileDevice.objects.get_or_create(
            user=user,
            device_id=device_id,
            defaults={
                "device_name": data.get("device_name", ""),
                "device_model": data.get("device_model", ""),
                "os_version": data.get("os_version", ""),
                "app_version": data.get("app_version", ""),
            },
        )

        if not created:
            # Update device info
            device.device_name = data.get("device_name", device.device_name)
            device.device_model = data.get("device_model", device.device_model)
            device.os_version = data.get("os_version", device.os_version)
            device.app_version = data.get("app_version", device.app_version)
            device.is_active = True
            device.save()

        # Revoke any existing tokens for this device
        MobileAPIToken.objects.filter(
            device=device,
            is_active=True,
        ).update(is_active=False)

        # Create new token
        token, raw_token = MobileAPIToken.create_token(
            user=user,
            device=device,
            expires_days=90,
            ip_address=client_ip,
        )

        # Consume the exchange code
        exchange_code.consume(device_id)

    logger.info(
        f"Token exchanged for user {hash_pii(user.email, 'user')}, "
        f"device {device.device_name or device_id[:8]}"
    )

    return JsonResponse({
        "token": raw_token,
        "expires_at": token.expires_at.isoformat(),
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
    })


@csrf_exempt
@require_mobile_auth
@require_http_methods(["POST"])
def revoke_token(request):
    """
    Revoke the current API token.

    Called when user logs out of native app.

    POST /api/mobile/token/revoke/
    Response: {"success": true}
    """
    token = request.mobile_token
    token.revoke()

    logger.info(
        f"Token revoked for {hash_pii(request.user.email, 'user')}, "
        f"device {request.mobile_device.device_name or request.mobile_device.device_id[:8]}"
    )

    return JsonResponse({"success": True})


@csrf_exempt
@require_mobile_auth
@require_http_methods(["POST"])
def revoke_all_tokens(request):
    """
    Revoke all API tokens for the current user.

    Called when user wants to log out of all devices.

    POST /api/mobile/token/revoke-all/
    Response: {"success": true, "revoked_count": 3}
    """
    count = MobileAPIToken.objects.filter(
        user=request.user,
        is_active=True,
    ).update(is_active=False)

    logger.info(f"All tokens revoked for {hash_pii(request.user.email, 'user')}, count={count}")

    return JsonResponse({"success": True, "revoked_count": count})


# =============================================================================
# Health Data Ingestion
# =============================================================================


@csrf_exempt
@require_mobile_auth
@require_http_methods(["POST"])
def health_ingest(request):
    """
    Ingest health data from iOS HealthKit.

    POST /api/health/ingest/
    Body: {
        "client_timestamp": "2024-01-15T10:30:00Z",
        "metrics": [
            {
                "type": "steps",
                "date": "2024-01-15",
                "value": 8500,
                "source": "apple_health",
                "sync_id": "unique-id-from-healthkit"
            },
            {
                "type": "weight",
                "date": "2024-01-15",
                "value": 175.5,
                "unit": "lbs",
                "source": "apple_health",
                "sync_id": "unique-id"
            },
            {
                "type": "sleep",
                "date": "2024-01-15",
                "bedtime": "2024-01-14T23:00:00Z",
                "wake_time": "2024-01-15T07:00:00Z",
                "total_minutes": 480,
                "deep_minutes": 90,
                "rem_minutes": 120,
                "light_minutes": 240,
                "awake_minutes": 30,
                "source": "apple_health",
                "sync_id": "unique-id"
            },
            {
                "type": "heart_rate",
                "date": "2024-01-15",
                "resting_hr": 62,
                "avg_hr": 72,
                "max_hr": 145,
                "source": "apple_health",
                "sync_id": "unique-id"
            }
        ]
    }

    Response: {
        "success": true,
        "ingestion_id": 123,
        "created": 3,
        "updated": 1,
        "skipped": 0,
        "errors": []
    }
    """
    user = request.user
    device = request.mobile_device
    token = request.mobile_token
    client_ip = get_client_ip(request)

    # Check payload size
    content_length = len(request.body)
    if content_length > MAX_PAYLOAD_SIZE:
        logger.warning(
            f"Oversized payload rejected: {content_length} bytes "
            f"from user {hash_pii(user.email, 'user')}"
        )
        return JsonResponse(
            {
                "error": "payload_too_large",
                "message": f"Payload exceeds {MAX_PAYLOAD_SIZE} bytes",
            },
            status=413,
        )

    # Parse JSON
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError as e:
        return JsonResponse(
            {"error": "invalid_json", "message": str(e)},
            status=400,
        )

    # Validate structure
    metrics = data.get("metrics", [])
    if not isinstance(metrics, list):
        return JsonResponse(
            {"error": "invalid_format", "message": "metrics must be an array"},
            status=400,
        )

    if len(metrics) > MAX_METRICS_PER_REQUEST:
        return JsonResponse(
            {
                "error": "too_many_metrics",
                "message": f"Maximum {MAX_METRICS_PER_REQUEST} metrics per request",
            },
            status=400,
        )

    if not metrics:
        return JsonResponse(
            {"error": "empty_metrics", "message": "No metrics provided"},
            status=400,
        )

    # Parse client timestamp
    client_timestamp = data.get("client_timestamp")
    if client_timestamp:
        try:
            client_timestamp = datetime.fromisoformat(
                client_timestamp.replace("Z", "+00:00")
            )
        except ValueError:
            client_timestamp = timezone.now()
    else:
        client_timestamp = timezone.now()

    # Create ingestion run for audit
    ingestion_run = HealthIngestionRun.objects.create(
        user=user,
        device=device,
        token=token,
        request_ip=client_ip,
        request_timestamp=client_timestamp,
        payload_size_bytes=content_length,
        metrics_received=len(metrics),
    )

    ingestion_run.mark_processing()

    # Process metrics
    created = 0
    updated = 0
    skipped = 0
    errors = []

    for i, metric in enumerate(metrics):
        try:
            result = process_health_metric(user, metric)
            if result == "created":
                created += 1
            elif result == "updated":
                updated += 1
            elif result == "skipped":
                skipped += 1
        except ValueError as e:
            errors.append({
                "index": i,
                "type": metric.get("type", "unknown"),
                "error": str(e),
            })
            skipped += 1

    # Update ingestion run
    if errors:
        ingestion_run.mark_partial(created, updated, skipped, errors)
    else:
        ingestion_run.mark_completed(created, updated, skipped)

    logger.info(
        f"Health ingestion completed: user={hash_pii(user.email, 'user')}, "
        f"created={created}, updated={updated}, skipped={skipped}, errors={len(errors)}"
    )

    return JsonResponse({
        "success": True,
        "ingestion_id": ingestion_run.id,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    })


def process_health_metric(user, metric):
    """
    Process a single health metric.

    Returns: "created", "updated", or "skipped"
    Raises: ValueError if invalid
    """
    metric_type = metric.get("type", "").lower()
    metric_date = metric.get("date")
    source = metric.get("source", "apple_health")
    sync_id = metric.get("sync_id", "")

    if not metric_type:
        raise ValueError("type is required")

    if not metric_date:
        raise ValueError("date is required")

    # Parse date
    try:
        if isinstance(metric_date, str):
            metric_date = datetime.strptime(metric_date, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date format: {metric_date}")

    # Route to appropriate handler
    handlers = {
        "steps": process_steps_metric,
        "weight": process_weight_metric,
        "sleep": process_sleep_metric,
        "heart_rate": process_heart_rate_metric,
        "blood_glucose": process_blood_glucose_metric,
        "blood_oxygen": process_blood_oxygen_metric,
        "water": process_water_metric,
        "active_calories": process_active_calories_metric,
        "distance": process_distance_metric,
        "resting_calories": process_resting_calories_metric,
        "flights_climbed": process_flights_climbed_metric,
        "exercise_minutes": process_exercise_minutes_metric,
        "stand_hours": process_stand_hours_metric,
        "body_fat": process_body_fat_metric,
        "workout": process_workout_metric,
        "lean_body_mass": process_lean_body_mass_metric,
        "respiratory_rate": process_respiratory_rate_metric,
        "hrv": process_hrv_metric,
        "vo2_max": process_vo2_max_metric,
        "caffeine": process_caffeine_metric,
        "mindful_minutes": process_mindful_minutes_metric,
        "blood_pressure": process_blood_pressure_metric,
        "body_temperature": process_body_temperature_metric,
    }

    handler = handlers.get(metric_type)
    if not handler:
        raise ValueError(f"Unknown metric type: {metric_type}")

    return handler(user, metric_date, source, sync_id, metric)


def process_steps_metric(user, metric_date, source, sync_id, data):
    """Process steps metric. StepsEntry uses 'count' and 'logged_date' fields."""
    value = data.get("value")
    if value is None:
        raise ValueError("value is required for steps")

    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid steps value: {value}")

    if value < 0 or value > 200000:
        raise ValueError(f"Steps value out of range: {value}")

    # Check for existing entry with same sync_id
    if sync_id:
        existing = StepsEntry.objects.filter(
            user=user,
            source=source,
            sync_id=sync_id,
        ).first()

        if existing:
            if existing.count != value:
                existing.count = value
                existing.save(update_fields=["count", "updated_at"])
                return "updated"
            return "skipped"

    # Check for existing entry on same date from same source
    existing = StepsEntry.objects.filter(
        user=user,
        logged_date=metric_date,
        source=source,
    ).first()

    if existing:
        if existing.count != value:
            existing.count = value
            existing.sync_id = sync_id
            existing.save(update_fields=["count", "sync_id", "updated_at"])
            return "updated"
        return "skipped"

    # Create new entry
    StepsEntry.objects.create(
        user=user,
        logged_date=metric_date,
        count=value,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_weight_metric(user, metric_date, source, sync_id, data):
    """
    Process weight metric.

    Note: WeightEntry uses 'value', 'unit', and 'recorded_at' (datetime, not date).
    It doesn't have source/sync_id fields, so we match by date only.
    """
    value = data.get("value")
    unit = data.get("unit", "lb")

    if value is None:
        raise ValueError("value is required for weight")

    try:
        value = Decimal(str(value))
    except (TypeError, InvalidOperation):
        raise ValueError(f"Invalid weight value: {value}")

    # Normalize unit to match model choices
    if unit.lower() in ("lbs", "lb", "pounds"):
        unit = "lb"
    elif unit.lower() in ("kg", "kilograms"):
        unit = "kg"
    else:
        unit = "lb"

    # Validate ranges based on unit
    if unit == "lb" and (value < 50 or value > 1000):
        raise ValueError(f"Weight value out of range: {value}")
    if unit == "kg" and (value < 20 or value > 450):
        raise ValueError(f"Weight value out of range: {value}")

    # Check for existing entry on same date (WeightEntry has no source/sync_id)
    from datetime import time as dt_time
    start_of_day = timezone.make_aware(datetime.combine(metric_date, dt_time.min))
    end_of_day = timezone.make_aware(datetime.combine(metric_date, dt_time.max))

    existing = WeightEntry.objects.filter(
        user=user,
        recorded_at__gte=start_of_day,
        recorded_at__lte=end_of_day,
    ).first()

    if existing:
        if existing.value != value or existing.unit != unit:
            existing.value = value
            existing.unit = unit
            # Add source info to notes if not already there
            if source and source not in (existing.notes or ""):
                existing.notes = f"Synced from {source}" if not existing.notes else existing.notes
            existing.save(update_fields=["value", "unit", "notes", "updated_at"])
            return "updated"
        return "skipped"

    # Create new entry (use noon as default time)
    WeightEntry.objects.create(
        user=user,
        value=value,
        unit=unit,
        recorded_at=timezone.make_aware(datetime.combine(metric_date, dt_time(12, 0))),
        notes=f"Synced from {source}" if source else "",
    )
    return "created"


def process_sleep_metric(user, metric_date, source, sync_id, data):
    """
    Process sleep metric.

    SleepEntry uses:
    - sleep_date (date)
    - bedtime, wake_time (datetime, required)
    - total_duration_minutes (required)
    - asleep_duration_minutes (optional)
    - stage_deep_minutes, stage_rem_minutes, stage_light_minutes, stage_awake_minutes
    """
    total_minutes = data.get("total_minutes")
    if total_minutes is None:
        raise ValueError("total_minutes is required for sleep")

    try:
        total_minutes = int(total_minutes)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid total_minutes: {total_minutes}")

    if total_minutes < 0 or total_minutes > 1440:  # Max 24 hours
        raise ValueError(f"Sleep minutes out of range: {total_minutes}")

    # Parse optional fields
    deep_minutes = data.get("deep_minutes")
    rem_minutes = data.get("rem_minutes")
    light_minutes = data.get("light_minutes")
    awake_minutes = data.get("awake_minutes")

    # Parse times (required for SleepEntry)
    bedtime = None
    wake_time = None

    if data.get("bedtime"):
        try:
            bedtime = datetime.fromisoformat(
                data["bedtime"].replace("Z", "+00:00")
            )
        except ValueError:
            pass

    if data.get("wake_time"):
        try:
            wake_time = datetime.fromisoformat(
                data["wake_time"].replace("Z", "+00:00")
            )
        except ValueError:
            pass

    # If no bedtime/wake_time provided, create defaults
    if not bedtime:
        # Default to 10 PM the night before
        from datetime import time as dt_time
        bedtime = timezone.make_aware(
            datetime.combine(metric_date, dt_time(22, 0)) - timedelta(days=1)
        )
    if not wake_time:
        # Calculate from bedtime + total_minutes
        wake_time = bedtime + timedelta(minutes=total_minutes)

    # Prepare update data using correct field names
    sleep_data = {
        "total_duration_minutes": total_minutes,
        "asleep_duration_minutes": total_minutes - (awake_minutes or 0),
        "source": source,
        "sync_id": sync_id,
        "bedtime": bedtime,
        "wake_time": wake_time,
    }

    if deep_minutes is not None:
        sleep_data["stage_deep_minutes"] = deep_minutes
    if rem_minutes is not None:
        sleep_data["stage_rem_minutes"] = rem_minutes
    if light_minutes is not None:
        sleep_data["stage_light_minutes"] = light_minutes
    if awake_minutes is not None:
        sleep_data["stage_awake_minutes"] = awake_minutes

    # Check for existing entry with same sync_id
    if sync_id:
        existing = SleepEntry.objects.filter(
            user=user,
            source=source,
            sync_id=sync_id,
        ).first()

        if existing:
            changed = False
            for key, val in sleep_data.items():
                if getattr(existing, key, None) != val:
                    setattr(existing, key, val)
                    changed = True

            if changed:
                existing.save()
                return "updated"
            return "skipped"

    # Check for existing entry on same date from same source
    existing = SleepEntry.objects.filter(
        user=user,
        sleep_date=metric_date,
        source=source,
    ).first()

    if existing:
        changed = False
        for key, val in sleep_data.items():
            if getattr(existing, key, None) != val:
                setattr(existing, key, val)
                changed = True

        if changed:
            existing.save()
            return "updated"
        return "skipped"

    # Create new entry
    SleepEntry.objects.create(
        user=user,
        sleep_date=metric_date,
        **sleep_data,
    )
    return "created"


def process_heart_rate_metric(user, metric_date, source, sync_id, data):
    """
    Process heart rate metric.

    Note: Heart rate is stored with sleep entries in WLJ.
    We update the sleep entry for that date if it exists,
    or create a minimal sleep entry to store the HR data.
    """
    resting_hr = data.get("resting_hr")
    avg_hr = data.get("avg_hr")
    max_hr = data.get("max_hr")
    min_hr = data.get("min_hr")

    if not any([resting_hr, avg_hr, max_hr, min_hr]):
        raise ValueError("At least one heart rate value required")

    # Validate ranges
    for name, value in [("resting_hr", resting_hr), ("avg_hr", avg_hr),
                        ("max_hr", max_hr), ("min_hr", min_hr)]:
        if value is not None:
            try:
                value = int(value)
                if value < 20 or value > 300:
                    raise ValueError(f"{name} out of range: {value}")
            except (TypeError, ValueError):
                raise ValueError(f"Invalid {name}: {value}")

    # Find or create sleep entry for this date
    sleep_entry = SleepEntry.objects.filter(
        user=user,
        sleep_date=metric_date,
    ).first()

    hr_data = {}
    if resting_hr is not None:
        hr_data["heart_rate_avg"] = resting_hr  # Use resting as avg if available
    if avg_hr is not None:
        hr_data["heart_rate_avg"] = avg_hr
    if max_hr is not None:
        hr_data["heart_rate_max"] = max_hr
    if min_hr is not None:
        hr_data["heart_rate_min"] = min_hr

    if sleep_entry:
        changed = False
        for key, value in hr_data.items():
            if getattr(sleep_entry, key, None) != value:
                setattr(sleep_entry, key, value)
                changed = True

        if changed:
            sleep_entry.save()
            return "updated"
        return "skipped"

    # Create minimal sleep entry to store HR data
    # SleepEntry requires bedtime/wake_time, so create dummy values for HR-only entries
    # Bedtime is night before (10 PM), wake time is morning of metric_date (6 AM)
    from datetime import time as dt_time
    prev_day = metric_date - timedelta(days=1)
    dummy_bedtime = timezone.make_aware(datetime.combine(prev_day, dt_time(22, 0)))
    dummy_wake_time = timezone.make_aware(datetime.combine(metric_date, dt_time(6, 0)))

    SleepEntry.objects.create(
        user=user,
        sleep_date=metric_date,
        source=source,
        sync_id=sync_id,
        total_duration_minutes=480,  # 8 hours dummy value for HR-only entry
        bedtime=dummy_bedtime,
        wake_time=dummy_wake_time,
        **hr_data,
    )
    return "created"


def process_blood_glucose_metric(user, metric_date, source, sync_id, data):
    """
    Process blood glucose metric from Apple HealthKit.

    GlucoseEntry uses:
    - value (decimal, required)
    - unit (mg/dL or mmol/L)
    - recorded_at (datetime)
    - source, sync_id for deduplication
    - context defaults to 'cgm' for synced data
    """
    # For blood glucose, the date field is actually a timestamp
    glucose_value = data.get("glucose_value")
    glucose_unit = data.get("glucose_unit", "mg/dL")

    if glucose_value is None:
        raise ValueError("glucose_value is required for blood_glucose")

    try:
        glucose_value = Decimal(str(glucose_value))
    except (TypeError, InvalidOperation):
        raise ValueError(f"Invalid glucose value: {glucose_value}")

    # Normalize unit
    if glucose_unit.lower() in ("mg/dl", "mgdl"):
        glucose_unit = "mg/dL"
    elif glucose_unit.lower() in ("mmol/l", "mmoll"):
        glucose_unit = "mmol/L"
    else:
        glucose_unit = "mg/dL"

    # Validate ranges based on unit
    if glucose_unit == "mg/dL" and (glucose_value < 20 or glucose_value > 600):
        raise ValueError(f"Glucose value out of range: {glucose_value}")
    if glucose_unit == "mmol/L" and (glucose_value < 1.1 or glucose_value > 33.3):
        raise ValueError(f"Glucose value out of range: {glucose_value}")

    # Parse recorded_at timestamp from the date field (ISO format with time)
    recorded_at = None
    date_str = data.get("date", "")
    if date_str:
        try:
            recorded_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            # If it's just a date, use noon
            try:
                from datetime import time as dt_time
                metric_date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                recorded_at = timezone.make_aware(
                    datetime.combine(metric_date_obj, dt_time(12, 0))
                )
            except ValueError:
                recorded_at = timezone.now()
    else:
        recorded_at = timezone.now()

    # Check for existing entry with same sync_id
    if sync_id:
        existing = GlucoseEntry.objects.filter(
            user=user,
            sync_id=sync_id,
        ).first()

        if existing:
            # Update if value changed
            if existing.value != glucose_value or existing.unit != glucose_unit:
                existing.value = glucose_value
                existing.unit = glucose_unit
                existing.recorded_at = recorded_at
                existing.save(update_fields=["value", "unit", "recorded_at", "updated_at"])
                return "updated"
            return "skipped"

    # Check for existing entry at same timestamp from same source (within 1 minute)
    time_window_start = recorded_at - timedelta(minutes=1)
    time_window_end = recorded_at + timedelta(minutes=1)

    existing = GlucoseEntry.objects.filter(
        user=user,
        source=source,
        recorded_at__gte=time_window_start,
        recorded_at__lte=time_window_end,
    ).first()

    if existing:
        if existing.value != glucose_value:
            existing.value = glucose_value
            existing.unit = glucose_unit
            existing.sync_id = sync_id
            existing.save(update_fields=["value", "unit", "sync_id", "updated_at"])
            return "updated"
        return "skipped"

    # Create new entry
    GlucoseEntry.objects.create(
        user=user,
        value=glucose_value,
        unit=glucose_unit,
        context="cgm",  # CGM reading from HealthKit
        recorded_at=recorded_at,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_blood_oxygen_metric(user, metric_date, source, sync_id, data):
    """
    Process blood oxygen (SpO2) metric from Apple HealthKit.

    BloodOxygenEntry uses:
    - spo2 (integer percentage)
    - recorded_at (datetime)
    - source, sync_id for deduplication
    """
    spo2_value = data.get("spo2_value")

    if spo2_value is None:
        raise ValueError("spo2_value is required for blood_oxygen")

    try:
        spo2_value = int(spo2_value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid spo2 value: {spo2_value}")

    # Validate range (50-100%)
    if spo2_value < 50 or spo2_value > 100:
        raise ValueError(f"SpO2 value out of range: {spo2_value}")

    # Parse recorded_at timestamp from the date field (ISO format with time)
    recorded_at = None
    date_str = data.get("date", "")
    if date_str:
        try:
            recorded_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            recorded_at = timezone.now()
    else:
        recorded_at = timezone.now()

    # Check for existing entry with same sync_id
    if sync_id:
        existing = BloodOxygenEntry.objects.filter(
            user=user,
            sync_id=sync_id,
        ).first()

        if existing:
            if existing.spo2 != spo2_value:
                existing.spo2 = spo2_value
                existing.recorded_at = recorded_at
                existing.save(update_fields=["spo2", "recorded_at", "updated_at"])
                return "updated"
            return "skipped"

    # Check for existing entry at same timestamp from same source (within 1 minute)
    time_window_start = recorded_at - timedelta(minutes=1)
    time_window_end = recorded_at + timedelta(minutes=1)

    existing = BloodOxygenEntry.objects.filter(
        user=user,
        source=source,
        recorded_at__gte=time_window_start,
        recorded_at__lte=time_window_end,
    ).first()

    if existing:
        if existing.spo2 != spo2_value:
            existing.spo2 = spo2_value
            existing.sync_id = sync_id
            existing.save(update_fields=["spo2", "sync_id", "updated_at"])
            return "updated"
        return "skipped"

    # Create new entry
    BloodOxygenEntry.objects.create(
        user=user,
        spo2=spo2_value,
        context="sleeping",  # Apple Watch measures SpO2 during sleep
        measurement_method="wrist",
        recorded_at=recorded_at,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_water_metric(user, metric_date, source, sync_id, data):
    """
    Process water intake metric from Apple HealthKit.

    WaterEntry uses:
    - amount (decimal)
    - unit (oz, ml, etc.)
    - logged_date (date)
    - source, sync_id for deduplication
    """
    water_amount = data.get("water_amount")
    water_unit = data.get("water_unit", "oz")

    if water_amount is None:
        raise ValueError("water_amount is required for water")

    try:
        water_amount = Decimal(str(water_amount))
    except (TypeError, InvalidOperation):
        raise ValueError(f"Invalid water amount: {water_amount}")

    # Normalize unit
    if water_unit.lower() in ("oz", "ounce", "ounces", "fl oz"):
        water_unit = "oz"
    elif water_unit.lower() in ("ml", "milliliter", "milliliters"):
        water_unit = "ml"
    elif water_unit.lower() in ("l", "liter", "liters"):
        water_unit = "liters"
    else:
        water_unit = "oz"

    # Validate range
    if water_unit == "oz" and (water_amount < 0 or water_amount > 500):
        raise ValueError(f"Water amount out of range: {water_amount}")
    if water_unit == "ml" and (water_amount < 0 or water_amount > 15000):
        raise ValueError(f"Water amount out of range: {water_amount}")

    # Check for existing entry with same sync_id
    if sync_id:
        existing = WaterEntry.objects.filter(
            user=user,
            sync_id=sync_id,
        ).first()

        if existing:
            if existing.amount != water_amount:
                existing.amount = water_amount
                existing.unit = water_unit
                existing.save(update_fields=["amount", "unit", "updated_at"])
                return "updated"
            return "skipped"

    # Check for existing entry on same date from same source
    existing = WaterEntry.objects.filter(
        user=user,
        logged_date=metric_date,
        source=source,
    ).first()

    if existing:
        # For water, we want to replace the daily total rather than add
        if existing.amount != water_amount:
            existing.amount = water_amount
            existing.unit = water_unit
            existing.sync_id = sync_id
            existing.save(update_fields=["amount", "unit", "sync_id", "updated_at"])
            return "updated"
        return "skipped"

    # Create new entry
    WaterEntry.objects.create(
        user=user,
        amount=water_amount,
        unit=water_unit,
        logged_date=metric_date,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_active_calories_metric(user, metric_date, source, sync_id, data):
    """
    Process active calories metric from Apple HealthKit.

    Updates the calories_burned field on the StepsEntry for this date.
    Creates a minimal StepsEntry if one doesn't exist.
    """
    calories_value = data.get("calories_value")

    if calories_value is None:
        raise ValueError("calories_value is required for active_calories")

    try:
        calories_value = int(calories_value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid calories value: {calories_value}")

    # Validate range (0 to 10,000 calories is reasonable)
    if calories_value < 0 or calories_value > 10000:
        raise ValueError(f"Calories value out of range: {calories_value}")

    # Find existing StepsEntry for this date and source
    existing = StepsEntry.objects.filter(
        user=user,
        logged_date=metric_date,
        source=source,
    ).first()

    if existing:
        if existing.calories_burned != calories_value:
            existing.calories_burned = calories_value
            existing.save(update_fields=["calories_burned", "updated_at"])
            return "updated"
        return "skipped"

    # Create new StepsEntry with just calories (count=0)
    StepsEntry.objects.create(
        user=user,
        logged_date=metric_date,
        count=0,  # Will be updated by steps sync
        calories_burned=calories_value,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_distance_metric(user, metric_date, source, sync_id, data):
    """
    Process distance walking/running metric from Apple HealthKit.

    Updates the distance_miles field on the StepsEntry for this date.
    Creates a minimal StepsEntry if one doesn't exist.
    """
    distance_value = data.get("distance_value")
    distance_unit = data.get("distance_unit", "mi")

    if distance_value is None:
        raise ValueError("distance_value is required for distance")

    try:
        distance_value = Decimal(str(distance_value))
    except (TypeError, InvalidOperation):
        raise ValueError(f"Invalid distance value: {distance_value}")

    # Convert to miles if needed
    if distance_unit.lower() in ("km", "kilometer", "kilometers"):
        distance_value = distance_value / Decimal("1.60934")
    elif distance_unit.lower() not in ("mi", "mile", "miles"):
        # Assume miles if unknown unit
        pass

    # Validate range (0 to 100 miles is reasonable)
    if distance_value < 0 or distance_value > 100:
        raise ValueError(f"Distance value out of range: {distance_value}")

    # Find existing StepsEntry for this date and source
    existing = StepsEntry.objects.filter(
        user=user,
        logged_date=metric_date,
        source=source,
    ).first()

    if existing:
        if existing.distance_miles != distance_value:
            existing.distance_miles = distance_value
            existing.save(update_fields=["distance_miles", "updated_at"])
            return "updated"
        return "skipped"

    # Create new StepsEntry with just distance (count=0)
    StepsEntry.objects.create(
        user=user,
        logged_date=metric_date,
        count=0,  # Will be updated by steps sync
        distance_miles=distance_value,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_resting_calories_metric(user, metric_date, source, sync_id, data):
    """
    Process resting/basal calories metric from Apple HealthKit.

    Updates the resting_calories field on the StepsEntry for this date.
    Creates a minimal StepsEntry if one doesn't exist.
    """
    resting_calories_value = data.get("resting_calories_value")

    if resting_calories_value is None:
        raise ValueError("resting_calories_value is required for resting_calories")

    try:
        resting_calories_value = int(resting_calories_value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid resting calories value: {resting_calories_value}")

    # Validate range (0 to 5,000 calories is reasonable for basal)
    if resting_calories_value < 0 or resting_calories_value > 5000:
        raise ValueError(f"Resting calories value out of range: {resting_calories_value}")

    # Find existing StepsEntry for this date and source
    existing = StepsEntry.objects.filter(
        user=user,
        logged_date=metric_date,
        source=source,
    ).first()

    if existing:
        if existing.resting_calories != resting_calories_value:
            existing.resting_calories = resting_calories_value
            existing.save(update_fields=["resting_calories", "updated_at"])
            return "updated"
        return "skipped"

    # Create new StepsEntry with just resting calories (count=0)
    StepsEntry.objects.create(
        user=user,
        logged_date=metric_date,
        count=0,  # Will be updated by steps sync
        resting_calories=resting_calories_value,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_flights_climbed_metric(user, metric_date, source, sync_id, data):
    """
    Process flights climbed metric from Apple HealthKit.

    Updates the flights_climbed field on the StepsEntry for this date.
    Creates a minimal StepsEntry if one doesn't exist.
    """
    flights_value = data.get("flights_value")

    if flights_value is None:
        raise ValueError("flights_value is required for flights_climbed")

    try:
        flights_value = int(flights_value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid flights value: {flights_value}")

    # Validate range (0 to 500 flights is reasonable)
    if flights_value < 0 or flights_value > 500:
        raise ValueError(f"Flights value out of range: {flights_value}")

    # Find existing StepsEntry for this date and source
    existing = StepsEntry.objects.filter(
        user=user,
        logged_date=metric_date,
        source=source,
    ).first()

    if existing:
        if existing.flights_climbed != flights_value:
            existing.flights_climbed = flights_value
            existing.save(update_fields=["flights_climbed", "updated_at"])
            return "updated"
        return "skipped"

    # Create new StepsEntry with just flights (count=0)
    StepsEntry.objects.create(
        user=user,
        logged_date=metric_date,
        count=0,  # Will be updated by steps sync
        flights_climbed=flights_value,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_exercise_minutes_metric(user, metric_date, source, sync_id, data):
    """
    Process exercise minutes metric from Apple HealthKit.

    Updates the exercise_minutes field on the StepsEntry for this date.
    Creates a minimal StepsEntry if one doesn't exist.
    """
    exercise_minutes_value = data.get("exercise_minutes_value")

    if exercise_minutes_value is None:
        raise ValueError("exercise_minutes_value is required for exercise_minutes")

    try:
        exercise_minutes_value = int(exercise_minutes_value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid exercise minutes value: {exercise_minutes_value}")

    # Validate range (0 to 1440 minutes = 24 hours)
    if exercise_minutes_value < 0 or exercise_minutes_value > 1440:
        raise ValueError(f"Exercise minutes value out of range: {exercise_minutes_value}")

    # Find existing StepsEntry for this date and source
    existing = StepsEntry.objects.filter(
        user=user,
        logged_date=metric_date,
        source=source,
    ).first()

    if existing:
        if existing.exercise_minutes != exercise_minutes_value:
            existing.exercise_minutes = exercise_minutes_value
            existing.save(update_fields=["exercise_minutes", "updated_at"])
            return "updated"
        return "skipped"

    # Create new StepsEntry with just exercise minutes (count=0)
    StepsEntry.objects.create(
        user=user,
        logged_date=metric_date,
        count=0,  # Will be updated by steps sync
        exercise_minutes=exercise_minutes_value,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_stand_hours_metric(user, metric_date, source, sync_id, data):
    """
    Process stand hours metric from Apple HealthKit.

    Updates the stand_hours field on the StepsEntry for this date.
    Creates a minimal StepsEntry if one doesn't exist.
    """
    stand_hours_value = data.get("stand_hours_value")

    if stand_hours_value is None:
        raise ValueError("stand_hours_value is required for stand_hours")

    try:
        stand_hours_value = int(stand_hours_value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid stand hours value: {stand_hours_value}")

    # Validate range (0 to 24 hours)
    if stand_hours_value < 0 or stand_hours_value > 24:
        raise ValueError(f"Stand hours value out of range: {stand_hours_value}")

    # Find existing StepsEntry for this date and source
    existing = StepsEntry.objects.filter(
        user=user,
        logged_date=metric_date,
        source=source,
    ).first()

    if existing:
        if existing.stand_hours != stand_hours_value:
            existing.stand_hours = stand_hours_value
            existing.save(update_fields=["stand_hours", "updated_at"])
            return "updated"
        return "skipped"

    # Create new StepsEntry with just stand hours (count=0)
    StepsEntry.objects.create(
        user=user,
        logged_date=metric_date,
        count=0,  # Will be updated by steps sync
        stand_hours=stand_hours_value,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_body_fat_metric(user, metric_date, source, sync_id, data):
    """
    Process body fat percentage metric from Apple HealthKit.

    Updates or creates a WeightEntry with body_fat_percentage for this date.
    If a weight entry already exists for this date, updates the body fat.
    Otherwise creates a minimal entry with just body fat (no weight value).
    """
    body_fat_percentage = data.get("body_fat_percentage")

    if body_fat_percentage is None:
        raise ValueError("body_fat_percentage is required for body_fat")

    try:
        body_fat_percentage = Decimal(str(body_fat_percentage))
    except (TypeError, InvalidOperation):
        raise ValueError(f"Invalid body fat value: {body_fat_percentage}")

    # Validate range (0 to 60% is reasonable)
    if body_fat_percentage < 0 or body_fat_percentage > 60:
        raise ValueError(f"Body fat percentage out of range: {body_fat_percentage}")

    # Check for existing entry with this sync_id
    existing = WeightEntry.objects.filter(
        user=user,
        sync_id=sync_id,
    ).first()

    if existing:
        if existing.body_fat_percentage != body_fat_percentage:
            existing.body_fat_percentage = body_fat_percentage
            existing.save(update_fields=["body_fat_percentage", "updated_at"])
            return "updated"
        return "skipped"

    # Check for weight entry on this date that we can update
    weight_entry = WeightEntry.objects.filter(
        user=user,
        recorded_at__date=metric_date,
    ).order_by("-recorded_at").first()

    if weight_entry:
        if weight_entry.body_fat_percentage != body_fat_percentage:
            weight_entry.body_fat_percentage = body_fat_percentage
            weight_entry.save(update_fields=["body_fat_percentage", "updated_at"])
            return "updated"
        return "skipped"

    # Create new WeightEntry with just body fat (value=0 as placeholder)
    # Note: This is a compromise - ideally we'd have a separate BodyFatEntry model
    WeightEntry.objects.create(
        user=user,
        value=Decimal("0"),  # Placeholder - will be updated by weight sync
        unit="lb",
        recorded_at=timezone.make_aware(
            datetime.combine(metric_date, datetime.min.time().replace(hour=12))
        ),
        body_fat_percentage=body_fat_percentage,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_workout_metric(user, metric_date, source, sync_id, data):
    """
    Process workout session metric from Apple HealthKit.

    Creates or updates a WorkoutSession from HealthKit workout data.
    """
    workout_type = data.get("workout_type", "")
    workout_duration = data.get("workout_duration")
    workout_calories = data.get("workout_calories")
    workout_distance = data.get("workout_distance")
    workout_start_time = data.get("workout_start_time")
    workout_end_time = data.get("workout_end_time")

    if workout_duration is None:
        raise ValueError("workout_duration is required for workout")

    try:
        workout_duration = int(workout_duration)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid workout duration: {workout_duration}")

    # Validate duration (0 to 720 minutes = 12 hours)
    if workout_duration < 0 or workout_duration > 720:
        raise ValueError(f"Workout duration out of range: {workout_duration}")

    # Parse optional calories
    if workout_calories is not None:
        try:
            workout_calories = int(workout_calories)
            if workout_calories < 0 or workout_calories > 5000:
                workout_calories = None
        except (TypeError, ValueError):
            workout_calories = None

    # Parse optional distance
    if workout_distance is not None:
        try:
            workout_distance = Decimal(str(workout_distance))
            if workout_distance < 0 or workout_distance > 100:
                workout_distance = None
        except (TypeError, InvalidOperation):
            workout_distance = None

    # Parse start and end times
    started_at = None
    completed_at = None
    if workout_start_time:
        try:
            started_at = datetime.fromisoformat(workout_start_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
    if workout_end_time:
        try:
            completed_at = datetime.fromisoformat(workout_end_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    # Check for existing workout with this sync_id
    existing = WorkoutSession.objects.filter(
        user=user,
        sync_id=sync_id,
    ).first()

    if existing:
        # Check if anything has changed
        changed = False
        if existing.workout_type != workout_type:
            existing.workout_type = workout_type
            changed = True
        if existing.duration_minutes != workout_duration:
            existing.duration_minutes = workout_duration
            changed = True
        if existing.calories_burned != workout_calories:
            existing.calories_burned = workout_calories
            changed = True
        if existing.distance_miles != workout_distance:
            existing.distance_miles = workout_distance
            changed = True

        if changed:
            existing.save()
            return "updated"
        return "skipped"

    # Create new WorkoutSession
    WorkoutSession.objects.create(
        user=user,
        date=metric_date,
        name=workout_type,  # Use workout type as default name
        workout_type=workout_type,
        duration_minutes=workout_duration,
        calories_burned=workout_calories,
        distance_miles=workout_distance,
        started_at=started_at,
        completed_at=completed_at,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_lean_body_mass_metric(user, metric_date, source, sync_id, data):
    """
    Process lean body mass metric from Apple HealthKit.

    Updates or creates a WeightEntry with lean_body_mass for this date.
    If a weight entry already exists for this date, updates the lean mass.
    Otherwise creates a minimal entry with just lean mass (no weight value).
    """
    lean_mass_value = data.get("lean_mass_value")
    lean_mass_unit = data.get("lean_mass_unit", "lb")

    if lean_mass_value is None:
        raise ValueError("lean_mass_value is required for lean_body_mass")

    try:
        lean_mass_value = Decimal(str(lean_mass_value))
    except (TypeError, InvalidOperation):
        raise ValueError(f"Invalid lean mass value: {lean_mass_value}")

    # Convert to pounds if needed
    if lean_mass_unit.lower() == "kg":
        lean_mass_value = lean_mass_value * Decimal("2.20462")

    # Validate range (10 to 300 lbs is reasonable for lean mass)
    if lean_mass_value < 10 or lean_mass_value > 300:
        raise ValueError(f"Lean body mass out of range: {lean_mass_value}")

    # Check for existing entry with this sync_id
    existing = WeightEntry.objects.filter(
        user=user,
        sync_id=sync_id,
    ).first()

    if existing:
        if existing.lean_body_mass != lean_mass_value:
            existing.lean_body_mass = lean_mass_value
            existing.save(update_fields=["lean_body_mass", "updated_at"])
            return "updated"
        return "skipped"

    # Check for weight entry on this date that we can update
    weight_entry = WeightEntry.objects.filter(
        user=user,
        recorded_at__date=metric_date,
    ).order_by("-recorded_at").first()

    if weight_entry:
        if weight_entry.lean_body_mass != lean_mass_value:
            weight_entry.lean_body_mass = lean_mass_value
            weight_entry.save(update_fields=["lean_body_mass", "updated_at"])
            return "updated"
        return "skipped"

    # Create new WeightEntry with just lean mass (value=0 as placeholder)
    WeightEntry.objects.create(
        user=user,
        value=Decimal("0"),  # Placeholder - will be updated by weight sync
        unit="lb",
        recorded_at=timezone.make_aware(
            datetime.combine(metric_date, datetime.min.time().replace(hour=12))
        ),
        lean_body_mass=lean_mass_value,
        source=source,
        sync_id=sync_id,
    )
    return "created"


def process_respiratory_rate_metric(user, metric_date, source, sync_id, data):
    """
    Process respiratory rate metric from Apple HealthKit.

    Updates the respiratory_rate field on the SleepEntry for this date.
    Creates a minimal SleepEntry if one doesn't exist.
    """
    respiratory_rate = data.get("respiratory_rate")

    if respiratory_rate is None:
        raise ValueError("respiratory_rate is required for respiratory_rate")

    try:
        respiratory_rate = Decimal(str(respiratory_rate))
    except (TypeError, InvalidOperation):
        raise ValueError(f"Invalid respiratory rate value: {respiratory_rate}")

    # Validate range (5 to 40 breaths per minute is reasonable)
    if respiratory_rate < 5 or respiratory_rate > 40:
        raise ValueError(f"Respiratory rate out of range: {respiratory_rate}")

    # Find existing SleepEntry for this date
    existing = SleepEntry.objects.filter(
        user=user,
        sleep_date=metric_date,
    ).order_by("-bedtime").first()

    if existing:
        if existing.respiratory_rate != respiratory_rate:
            existing.respiratory_rate = respiratory_rate
            existing.save(update_fields=["respiratory_rate", "updated_at"])
            return "updated"
        return "skipped"

    # No sleep entry for this date - respiratory rate is typically measured during sleep
    # We'll skip creating a minimal entry since it doesn't make sense without sleep data
    # The data will be captured when the next sleep sync includes this date
    return "skipped"


def process_hrv_metric(user, metric_date, source, sync_id, data):
    """
    Process Heart Rate Variability (HRV) metric from Apple HealthKit.

    Updates the hrv_value field on the SleepEntry for this date.
    HRV is typically measured during sleep or rest.
    """
    hrv_value = data.get("hrv_value")

    if hrv_value is None:
        raise ValueError("hrv_value is required for hrv")

    try:
        hrv_value = Decimal(str(hrv_value))
    except (TypeError, InvalidOperation):
        raise ValueError(f"Invalid HRV value: {hrv_value}")

    # Validate range (10 to 200 ms is reasonable for SDNN)
    if hrv_value < 5 or hrv_value > 300:
        raise ValueError(f"HRV value out of range: {hrv_value}")

    # Find existing SleepEntry for this date
    existing = SleepEntry.objects.filter(
        user=user,
        sleep_date=metric_date,
    ).order_by("-bedtime").first()

    if existing:
        if existing.hrv_value != hrv_value:
            existing.hrv_value = hrv_value
            existing.save(update_fields=["hrv_value", "updated_at"])
            return "updated"
        return "skipped"

    # No sleep entry for this date - HRV is typically measured during sleep/rest
    # Skip creating a minimal entry
    return "skipped"


def process_vo2_max_metric(user, metric_date, source, sync_id, data):
    """
    Process VO2 Max metric from Apple HealthKit.

    Updates the vo2_max field on the SleepEntry for this date.
    VO2 Max is a cardiorespiratory fitness indicator.
    """
    vo2_max_value = data.get("vo2_max_value")

    if vo2_max_value is None:
        raise ValueError("vo2_max_value is required for vo2_max")

    try:
        vo2_max_value = Decimal(str(vo2_max_value))
    except (TypeError, InvalidOperation):
        raise ValueError(f"Invalid VO2 Max value: {vo2_max_value}")

    # Validate range (10 to 90 mL/kg/min is reasonable)
    if vo2_max_value < 10 or vo2_max_value > 100:
        raise ValueError(f"VO2 Max value out of range: {vo2_max_value}")

    # Find existing SleepEntry for this date
    existing = SleepEntry.objects.filter(
        user=user,
        sleep_date=metric_date,
    ).order_by("-bedtime").first()

    if existing:
        if existing.vo2_max != vo2_max_value:
            existing.vo2_max = vo2_max_value
            existing.save(update_fields=["vo2_max", "updated_at"])
            return "updated"
        return "skipped"

    # No sleep entry for this date - skip creating a minimal entry
    return "skipped"


def process_caffeine_metric(user, metric_date, source, sync_id, data):
    """
    Process caffeine intake metric from Apple HealthKit.

    Updates the caffeine_mg field on the SleepEntry for this date.
    Caffeine intake affects sleep quality.
    """
    caffeine_value = data.get("caffeine_value")

    if caffeine_value is None:
        raise ValueError("caffeine_value is required for caffeine")

    try:
        caffeine_value = Decimal(str(caffeine_value))
    except (TypeError, InvalidOperation):
        raise ValueError(f"Invalid caffeine value: {caffeine_value}")

    # Validate range (0 to 2000 mg is reasonable - about 20 cups of coffee)
    if caffeine_value < 0 or caffeine_value > 2000:
        raise ValueError(f"Caffeine value out of range: {caffeine_value}")

    # Find existing SleepEntry for this date
    existing = SleepEntry.objects.filter(
        user=user,
        sleep_date=metric_date,
    ).order_by("-bedtime").first()

    if existing:
        if existing.caffeine_mg != caffeine_value:
            existing.caffeine_mg = caffeine_value
            existing.save(update_fields=["caffeine_mg", "updated_at"])
            return "updated"
        return "skipped"

    # No sleep entry for this date - skip creating a minimal entry
    return "skipped"


def process_mindful_minutes_metric(user, metric_date, source, sync_id, data):
    """
    Process mindful minutes metric from Apple HealthKit.

    Updates the mindful_minutes field on the SleepEntry for this date.
    Mindfulness practice can improve sleep quality.
    """
    mindful_minutes_value = data.get("mindful_minutes_value")

    if mindful_minutes_value is None:
        raise ValueError("mindful_minutes_value is required for mindful_minutes")

    try:
        mindful_minutes_value = int(mindful_minutes_value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid mindful minutes value: {mindful_minutes_value}")

    # Validate range (0 to 1440 minutes = 24 hours max)
    if mindful_minutes_value < 0 or mindful_minutes_value > 1440:
        raise ValueError(f"Mindful minutes value out of range: {mindful_minutes_value}")

    # Find existing SleepEntry for this date
    existing = SleepEntry.objects.filter(
        user=user,
        sleep_date=metric_date,
    ).order_by("-bedtime").first()

    if existing:
        if existing.mindful_minutes != mindful_minutes_value:
            existing.mindful_minutes = mindful_minutes_value
            existing.save(update_fields=["mindful_minutes", "updated_at"])
            return "updated"
        return "skipped"

    # No sleep entry for this date - skip creating a minimal entry
    return "skipped"


def process_blood_pressure_metric(user, metric_date, source, sync_id, data):
    """
    Process blood pressure metric from Apple HealthKit.

    Creates or updates BloodPressureEntry records.
    """
    systolic_value = data.get("systolic_value")
    diastolic_value = data.get("diastolic_value")
    recorded_at_str = data.get("recorded_at")

    if systolic_value is None or diastolic_value is None:
        raise ValueError("systolic_value and diastolic_value are required for blood_pressure")

    try:
        systolic_value = int(systolic_value)
        diastolic_value = int(diastolic_value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid blood pressure values: {systolic_value}/{diastolic_value}")

    # Validate ranges (reasonable BP range: 60-250 systolic, 30-150 diastolic)
    if systolic_value < 60 or systolic_value > 250:
        raise ValueError(f"Systolic value out of range: {systolic_value}")
    if diastolic_value < 30 or diastolic_value > 150:
        raise ValueError(f"Diastolic value out of range: {diastolic_value}")

    # Parse recorded_at timestamp
    recorded_at = None
    if recorded_at_str:
        try:
            from django.utils.dateparse import parse_datetime
            recorded_at = parse_datetime(recorded_at_str)
        except (TypeError, ValueError):
            pass

    if not recorded_at:
        from django.utils import timezone as tz
        recorded_at = tz.make_aware(
            datetime.combine(metric_date, datetime.min.time().replace(hour=12))
        )

    # Check for existing entry by sync_id
    existing = BloodPressureEntry.objects.filter(
        user=user,
        sync_id=sync_id,
    ).first()

    if existing:
        updated = False
        if existing.systolic != systolic_value:
            existing.systolic = systolic_value
            updated = True
        if existing.diastolic != diastolic_value:
            existing.diastolic = diastolic_value
            updated = True
        if updated:
            existing.save(update_fields=["systolic", "diastolic", "updated_at"])
            return "updated"
        return "skipped"

    # Create new entry
    BloodPressureEntry.objects.create(
        user=user,
        systolic=systolic_value,
        diastolic=diastolic_value,
        recorded_at=recorded_at,
        source=source,
        sync_id=sync_id,
        context="resting",  # Default context for HealthKit data
    )
    return "created"


def process_body_temperature_metric(user, metric_date, source, sync_id, data):
    """
    Process body temperature metric from Apple HealthKit.

    Creates or updates BodyTemperatureEntry records.
    """
    temperature_value = data.get("temperature_value")
    temperature_unit = data.get("temperature_unit", "fahrenheit")
    recorded_at_str = data.get("recorded_at")

    if temperature_value is None:
        raise ValueError("temperature_value is required for body_temperature")

    try:
        temperature_value = float(temperature_value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid temperature value: {temperature_value}")

    # Validate range (reasonable range: 90-110°F or 32-43°C)
    if temperature_unit == "fahrenheit":
        if temperature_value < 90.0 or temperature_value > 110.0:
            raise ValueError(f"Temperature value out of range: {temperature_value}°F")
    else:
        if temperature_value < 32.0 or temperature_value > 43.0:
            raise ValueError(f"Temperature value out of range: {temperature_value}°C")

    # Parse recorded_at timestamp
    recorded_at = None
    if recorded_at_str:
        try:
            from django.utils.dateparse import parse_datetime
            recorded_at = parse_datetime(recorded_at_str)
        except (TypeError, ValueError):
            pass

    if not recorded_at:
        from django.utils import timezone as tz
        recorded_at = tz.make_aware(
            datetime.combine(metric_date, datetime.min.time().replace(hour=12))
        )

    # Check for existing entry by sync_id
    existing = BodyTemperatureEntry.objects.filter(
        user=user,
        sync_id=sync_id,
    ).first()

    if existing:
        if float(existing.temperature) != temperature_value:
            existing.temperature = temperature_value
            existing.save(update_fields=["temperature", "updated_at"])
            return "updated"
        return "skipped"

    # Create new entry
    BodyTemperatureEntry.objects.create(
        user=user,
        temperature=temperature_value,
        unit=temperature_unit,
        recorded_at=recorded_at,
        source=source,
        sync_id=sync_id,
        context="other",  # Default context for HealthKit data
    )
    return "created"


# =============================================================================
# Sync Status
# =============================================================================


@require_mobile_auth
@require_http_methods(["GET"])
def sync_status(request):
    """
    Get sync status for the current device.

    GET /api/health/sync-status/
    Response: {
        "last_sync": "2024-01-15T10:30:00Z",
        "last_sync_status": "completed",
        "metrics_synced": {
            "steps": "2024-01-15",
            "weight": "2024-01-14",
            "sleep": "2024-01-15",
            "heart_rate": "2024-01-15"
        },
        "device": {
            "name": "Danny's iPhone",
            "last_seen": "2024-01-15T10:30:00Z"
        }
    }
    """
    user = request.user
    device = request.mobile_device

    # Get last ingestion run
    last_run = HealthIngestionRun.objects.filter(
        user=user,
        device=device,
    ).first()

    # Get latest dates for each metric type
    latest_steps = StepsEntry.objects.filter(
        user=user,
        source="apple_health",
    ).order_by("-logged_date").values_list("logged_date", flat=True).first()

    # WeightEntry doesn't have source field, just get latest
    latest_weight = WeightEntry.objects.filter(
        user=user,
    ).order_by("-recorded_at").values_list("recorded_at", flat=True).first()

    latest_sleep = SleepEntry.objects.filter(
        user=user,
        source="apple_health",
    ).order_by("-sleep_date").values_list("sleep_date", flat=True).first()

    latest_glucose = GlucoseEntry.objects.filter(
        user=user,
        source="apple_health",
    ).order_by("-recorded_at").values_list("recorded_at", flat=True).first()

    return JsonResponse({
        "last_sync": last_run.created_at.isoformat() if last_run else None,
        "last_sync_status": last_run.status if last_run else None,
        "metrics_synced": {
            "steps": latest_steps.isoformat() if latest_steps else None,
            # latest_weight is a datetime, get just the date
            "weight": latest_weight.date().isoformat() if latest_weight else None,
            "sleep": latest_sleep.isoformat() if latest_sleep else None,
            "blood_glucose": latest_glucose.isoformat() if latest_glucose else None,
        },
        "device": {
            "name": device.device_name or device.device_model or "Unknown",
            "last_seen": device.last_seen_at.isoformat() if device.last_seen_at else None,
        },
    })


# =============================================================================
# Device Management
# =============================================================================


@require_mobile_auth
@require_http_methods(["GET"])
def list_devices(request):
    """
    List all devices for the current user.

    GET /api/mobile/devices/
    Response: {
        "devices": [
            {
                "id": 1,
                "device_id": "uuid...",
                "device_name": "Danny's iPhone",
                "device_model": "iPhone 15 Pro",
                "is_active": true,
                "last_seen": "2024-01-15T10:30:00Z",
                "is_current": true
            }
        ]
    }
    """
    devices = MobileDevice.objects.filter(user=request.user).order_by("-last_seen_at")

    return JsonResponse({
        "devices": [
            {
                "id": d.id,
                "device_id": d.device_id,
                "device_name": d.device_name,
                "device_model": d.device_model,
                "os_version": d.os_version,
                "app_version": d.app_version,
                "is_active": d.is_active,
                "last_seen": d.last_seen_at.isoformat() if d.last_seen_at else None,
                "is_current": d.id == request.mobile_device.id,
            }
            for d in devices
        ]
    })


@csrf_exempt
@require_mobile_auth
@require_http_methods(["POST"])
def deactivate_device(request, device_id):
    """
    Deactivate a device (revokes all its tokens).

    POST /api/mobile/devices/<id>/deactivate/
    Response: {"success": true}
    """
    try:
        device = MobileDevice.objects.get(id=device_id, user=request.user)
    except MobileDevice.DoesNotExist:
        return JsonResponse(
            {"error": "not_found", "message": "Device not found"},
            status=404,
        )

    device.is_active = False
    device.save(update_fields=["is_active", "updated_at"])

    # Revoke all tokens for this device
    MobileAPIToken.objects.filter(device=device).update(is_active=False)

    logger.info(f"Device deactivated: {device.device_name or device.device_id[:8]}")

    return JsonResponse({"success": True})
