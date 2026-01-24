"""
Mobile API Views

Endpoints for iOS app integration:
- Token exchange (web session -> API token)
- Token revocation
- Health data ingestion
- Sync status

All endpoints return JSON responses.
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
    GlucoseEntry,
    StepsEntry,
    SleepEntry,
    WaterEntry,
    WeightEntry,
)

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
# Maximum metrics per request (temporarily increased for initial HealthKit backfill)
MAX_METRICS_PER_REQUEST = 10000


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

    logger.info(f"Generated exchange code for user {request.user.email}")

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
        f"Token exchanged for user {user.email}, "
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
        f"Token revoked for user {request.user.email}, "
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

    logger.info(f"All tokens revoked for user {request.user.email}, count={count}")

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
            f"from user {user.email}"
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
        f"Health ingestion completed: user={user.email}, "
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
        "water_intake": process_water_intake_metric,
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
    Process blood glucose metric from HealthKit.

    GlucoseEntry fields:
    - value (Decimal): glucose reading
    - unit (str): mg/dL or mmol/L
    - recorded_at (datetime): timestamp of reading
    - source (str): manual, dexcom, imported
    - context (str): cgm for HealthKit data
    """
    value = data.get("value")
    unit = data.get("unit", "mg/dL")
    timestamp = data.get("timestamp")

    if value is None:
        raise ValueError("value is required for blood_glucose")

    try:
        value = Decimal(str(value))
    except (TypeError, InvalidOperation):
        raise ValueError(f"Invalid blood glucose value: {value}")

    # Validate ranges (mg/dL)
    if unit == "mg/dL" and (value < 20 or value > 600):
        raise ValueError(f"Blood glucose value out of range: {value}")

    # Parse timestamp for recorded_at
    recorded_at = None
    if timestamp:
        try:
            # Try ISO8601 format
            recorded_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            pass

    if not recorded_at:
        # Fall back to start of day
        recorded_at = timezone.make_aware(datetime.combine(metric_date, datetime.min.time()))

    # Map apple_health source to "imported" for GlucoseEntry
    glucose_source = "imported" if source == "apple_health" else source

    # Check for existing entry with same sync_id
    if sync_id:
        existing = GlucoseEntry.objects.filter(
            user=user,
            source=glucose_source,
            dexcom_record_id=sync_id,  # Use dexcom_record_id field for sync tracking
        ).first()

        if existing:
            if existing.value != value:
                existing.value = value
                existing.save(update_fields=["value", "updated_at"])
                return "updated"
            return "skipped"

    # Check for existing entry at same timestamp from same source
    # Allow 30 second tolerance for matching
    time_window_start = recorded_at - timedelta(seconds=30)
    time_window_end = recorded_at + timedelta(seconds=30)

    existing = GlucoseEntry.objects.filter(
        user=user,
        source=glucose_source,
        recorded_at__gte=time_window_start,
        recorded_at__lte=time_window_end,
    ).first()

    if existing:
        if existing.value != value:
            existing.value = value
            existing.dexcom_record_id = sync_id
            existing.save(update_fields=["value", "dexcom_record_id", "updated_at"])
            return "updated"
        return "skipped"

    # Create new entry
    GlucoseEntry.objects.create(
        user=user,
        value=value,
        unit=unit,
        recorded_at=recorded_at,
        source=glucose_source,
        dexcom_record_id=sync_id,
        context="cgm",  # CGM readings from HealthKit
    )
    return "created"


def process_blood_oxygen_metric(user, metric_date, source, sync_id, data):
    """
    Process blood oxygen (SpO2) metric from HealthKit.

    Note: WLJ doesn't have a dedicated SpO2 model yet.
    For now, we skip these metrics silently.
    Future: Could add SpO2Entry model or store in a generic vitals table.
    """
    # Acknowledge receipt but don't store (no model available)
    # This prevents "Unknown metric type" errors
    return "skipped"


def process_water_intake_metric(user, metric_date, source, sync_id, data):
    """
    Process water intake metric from HealthKit.

    WaterEntry fields:
    - amount (Decimal): amount consumed
    - unit (str): oz, ml, cups, liters
    - logged_date (date): date logged
    - recorded_at (datetime): when recorded
    """
    value = data.get("value")
    unit = data.get("unit", "fl_oz")

    if value is None:
        raise ValueError("value is required for water_intake")

    try:
        value = Decimal(str(value))
    except (TypeError, InvalidOperation):
        raise ValueError(f"Invalid water intake value: {value}")

    # Convert fl_oz to oz (they're the same)
    if unit == "fl_oz":
        unit = "oz"

    # Validate unit
    if unit not in ("oz", "ml", "cups", "liters"):
        unit = "oz"  # Default to oz

    # Validate ranges
    if unit == "oz" and (value < 0 or value > 500):
        raise ValueError(f"Water intake value out of range: {value}")

    # Check for existing entry on same date with same sync_id
    if sync_id:
        existing = WaterEntry.objects.filter(
            user=user,
            logged_date=metric_date,
            notes__contains=sync_id,
        ).first()

        if existing:
            if existing.amount != value:
                existing.amount = value
                existing.save(update_fields=["amount", "updated_at"])
                return "updated"
            return "skipped"

    # Check for existing daily total from apple_health
    existing = WaterEntry.objects.filter(
        user=user,
        logged_date=metric_date,
        notes__contains="apple_health",
    ).first()

    if existing:
        if existing.amount != value:
            existing.amount = value
            existing.notes = f"Synced from {source} ({sync_id})"
            existing.save(update_fields=["amount", "notes", "updated_at"])
            return "updated"
        return "skipped"

    # Create new entry
    WaterEntry.objects.create(
        user=user,
        amount=value,
        unit=unit,
        logged_date=metric_date,
        recorded_at=timezone.now(),
        container="other",
        notes=f"Synced from {source} ({sync_id})",
    )
    return "created"


# =============================================================================
# Sync Status
# =============================================================================


@csrf_exempt
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

    # Get last ingestion run (most recent first)
    last_run = HealthIngestionRun.objects.filter(
        user=user,
        device=device,
    ).order_by('-created_at').first()

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

    return JsonResponse({
        "last_sync": last_run.created_at.isoformat() if last_run else None,
        "last_sync_status": last_run.status if last_run else None,
        "metrics_synced": {
            "steps": latest_steps.isoformat() if latest_steps else None,
            # latest_weight is a datetime, get just the date
            "weight": latest_weight.date().isoformat() if latest_weight else None,
            "sleep": latest_sleep.isoformat() if latest_sleep else None,
        },
        "device": {
            "name": device.device_name or device.device_model or "Unknown",
            "last_seen": device.last_seen_at.isoformat() if device.last_seen_at else None,
        },
    })


# =============================================================================
# Device Management
# =============================================================================


@csrf_exempt
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
