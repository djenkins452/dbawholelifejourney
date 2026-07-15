"""
Health Sync Status — the ONE deterministic truth for "is each Apple Health source
healthy?".

This is reusable platform truth, not page-specific logic: the redesigned Health
Sync page consumes it, and any future Health Operations / diagnostic view should
too. It answers, per synced data type and for the account as a whole:

  * Did this data type ever sync?  When did it last produce a record?
  * How many records arrived recently?
  * Is the source going stale (no data for longer than its expected cadence)?
  * What did the most recent sync actually do (imported / no change / failed)?
  * What issues need the user's attention?

Everything is derived deterministically from persisted truth — the domain health
models (last record per type, filtered to Apple Health) and the latest
``HealthIngestionRun`` (per-type sync results + errors). Nothing is fabricated:
if we cannot see records for a type, we say "no records received" rather than
guessing "authorized" — because HealthKit deliberately hides read-authorization,
so *received data* is the only trustworthy signal.

Request-path safe: a bounded set of indexed ``latest()``/``count()`` lookups
(one small query per registered type). No heavy compute, no LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from django.utils import timezone

APPLE_HEALTH = "apple_health"


@dataclass(frozen=True)
class HealthSyncType:
    """Registry entry: how to find the latest Apple-Health record for one type.

    ``key`` matches the metric ``type`` the iOS app sends (see
    ``ios/.../Models/HealthMetric.swift`` and ``mobile/views.process_health_metric``).
    """
    key: str
    label: str
    model_path: str          # "apps.health.models.StepsEntry"
    date_field: str          # field to order by / read the record instant from
    unit: str = ""
    # Extra filter that identifies THIS type's rows when several metric types
    # share one model (e.g. active_calories lives on StepsEntry.calories_burned).
    presence_filter: dict = field(default_factory=dict)
    # Days after which a source with an expected daily/continuous cadence is
    # "stale". None = irregular by nature (weight, workouts) — never flags stale.
    stale_after_days: Optional[int] = None
    # If True, a *never-synced* state for this type is raised as a top-level ISSUE
    # (only when sync is otherwise working). Reserve for phone-native, universally
    # expected metrics — chiefly Steps — to avoid noisy "issues" for optional
    # sources a given user simply doesn't have. Every type still shows its status
    # in the data-type list; only issue-surfacing is gated by this flag.
    core: bool = False
    # Grouping key for the Health Sync UI (see CATEGORY_ORDER). Purely
    # presentational — never affects ingestion or status computation.
    category: str = "other"

    def get_model(self):
        from django.apps import apps as django_apps
        model_name = self.model_path.rsplit(".", 1)[1]
        return django_apps.get_model("health", model_name)


# --------------------------------------------------------------------------- #
# Categories — the grouping the Health Sync UI renders (ordered).             #
# Purely presentational; add a category here + tag types below.               #
# --------------------------------------------------------------------------- #
CATEGORY_ORDER: list[tuple[str, str]] = [
    ("activity", "Activity"),
    ("heart_vitals", "Heart & Vitals"),
    ("respiratory", "Respiratory"),
    ("sleep", "Sleep & Recovery"),
    ("body", "Body Measurements"),
    ("mobility", "Mobility"),
    ("nutrition", "Nutrition"),
    ("hearing", "Hearing"),
    ("mental", "Mental Wellbeing"),
    ("workouts", "Workouts"),
    ("other", "Other"),
]
CATEGORY_LABELS = dict(CATEGORY_ORDER)


# --------------------------------------------------------------------------- #
# The registry — the canonical list of Apple-Health-synced data types.        #
# ONE row per metric type the ingest layer accepts                            #
# (apps/mobile/views.process_health_metric ``handlers``). This list and that  #
# dict must stay in agreement — enforced by                                   #
# apps/health/tests/test_health_sync_registry_contract.py.                    #
#                                                                             #
# Types that share a model are distinguished by ``presence_filter`` (e.g.     #
# StepsEntry holds steps/active_calories/distance/…; SleepEntry holds the      #
# nightly rollup fields; MobilityEntry/HeartRateEventEntry/BodyCompositionEntry #
# are field- or discriminator-keyed). Add a type by adding a row here; every  #
# consumer (status, grouping, telemetry) updates automatically.               #
# --------------------------------------------------------------------------- #
HEALTH_SYNC_TYPES: list[HealthSyncType] = [
    # ── Activity (StepsEntry daily rollup + fields) ───────────────────────── #
    HealthSyncType("steps", "Steps", "apps.health.models.StepsEntry", "logged_date",
                   unit="steps", presence_filter={"count__gt": 0}, stale_after_days=2,
                   core=True, category="activity"),  # phone-native — should always be present
    HealthSyncType("active_calories", "Active Calories", "apps.health.models.StepsEntry",
                   "logged_date", unit="kcal", presence_filter={"calories_burned__gt": 0},
                   stale_after_days=2, category="activity"),
    HealthSyncType("resting_calories", "Resting Calories", "apps.health.models.StepsEntry",
                   "logged_date", unit="kcal", presence_filter={"resting_calories__gt": 0},
                   stale_after_days=2, category="activity"),
    HealthSyncType("distance", "Distance", "apps.health.models.StepsEntry", "logged_date",
                   unit="mi", presence_filter={"distance_miles__gt": 0}, stale_after_days=2,
                   category="activity"),
    HealthSyncType("flights_climbed", "Flights Climbed", "apps.health.models.StepsEntry",
                   "logged_date", unit="flights", presence_filter={"flights_climbed__gt": 0},
                   stale_after_days=2, category="activity"),
    HealthSyncType("exercise_minutes", "Exercise Minutes", "apps.health.models.StepsEntry",
                   "logged_date", unit="min", presence_filter={"exercise_minutes__gt": 0},
                   stale_after_days=2, category="activity"),
    HealthSyncType("stand_hours", "Stand Hours", "apps.health.models.StepsEntry",
                   "logged_date", unit="hours", presence_filter={"stand_hours__gt": 0},
                   stale_after_days=2, category="activity"),

    # ── Heart & Vitals ────────────────────────────────────────────────────── #
    HealthSyncType("heart_rate", "Heart Rate", "apps.health.models.HeartRateEntry", "recorded_at",
                   unit="bpm", stale_after_days=2, category="heart_vitals"),
    HealthSyncType("hrv", "Heart Rate Variability", "apps.health.models.SleepEntry", "sleep_date",
                   unit="ms", presence_filter={"hrv_value__isnull": False}, stale_after_days=3,
                   category="heart_vitals"),
    HealthSyncType("vo2_max", "VO₂ Max", "apps.health.models.SleepEntry", "sleep_date",
                   unit="mL/kg/min", presence_filter={"vo2_max__isnull": False}, stale_after_days=None,
                   category="heart_vitals"),
    HealthSyncType("blood_pressure", "Blood Pressure", "apps.health.models.BloodPressureEntry",
                   "recorded_at", unit="mmHg", stale_after_days=None, category="heart_vitals"),
    HealthSyncType("blood_oxygen", "Blood Oxygen", "apps.health.models.BloodOxygenEntry", "recorded_at",
                   unit="%", stale_after_days=3, category="heart_vitals"),
    HealthSyncType("blood_glucose", "Blood Glucose", "apps.health.models.GlucoseEntry", "recorded_at",
                   unit="mg/dL", stale_after_days=2, category="heart_vitals"),
    HealthSyncType("body_temperature", "Body Temperature", "apps.health.models.BodyTemperatureEntry",
                   "recorded_at", unit="°F", stale_after_days=None, category="heart_vitals"),
    HealthSyncType("high_heart_rate_event", "High Heart Rate Events",
                   "apps.health.models.HeartRateEventEntry", "recorded_at", unit="events",
                   presence_filter={"event_type": "high_hr"}, stale_after_days=None,
                   category="heart_vitals"),
    HealthSyncType("low_heart_rate_event", "Low Heart Rate Events",
                   "apps.health.models.HeartRateEventEntry", "recorded_at", unit="events",
                   presence_filter={"event_type": "low_hr"}, stale_after_days=None,
                   category="heart_vitals"),
    HealthSyncType("irregular_rhythm_event", "Irregular Rhythm Events",
                   "apps.health.models.HeartRateEventEntry", "recorded_at", unit="events",
                   presence_filter={"event_type": "irregular_rhythm"}, stale_after_days=None,
                   category="heart_vitals"),

    # ── Respiratory ───────────────────────────────────────────────────────── #
    HealthSyncType("respiratory_rate", "Respiratory Rate", "apps.health.models.SleepEntry", "sleep_date",
                   unit="breaths/min", presence_filter={"respiratory_rate__isnull": False},
                   stale_after_days=3, category="respiratory"),

    # ── Sleep & Recovery ──────────────────────────────────────────────────── #
    HealthSyncType("sleep", "Sleep", "apps.health.models.SleepEntry", "sleep_date",
                   unit="nights", stale_after_days=2, category="sleep"),

    # ── Body Measurements ─────────────────────────────────────────────────── #
    HealthSyncType("weight", "Weight", "apps.health.models.WeightEntry", "recorded_at",
                   unit="lbs", stale_after_days=None, category="body"),
    HealthSyncType("body_fat", "Body Fat", "apps.health.models.WeightEntry", "recorded_at",
                   unit="%", presence_filter={"body_fat_percentage__isnull": False},
                   stale_after_days=None, category="body"),
    HealthSyncType("lean_body_mass", "Lean Body Mass", "apps.health.models.WeightEntry", "recorded_at",
                   unit="lbs", presence_filter={"lean_body_mass__isnull": False},
                   stale_after_days=None, category="body"),
    HealthSyncType("bmi", "Body Mass Index", "apps.health.models.BodyCompositionEntry",
                   "measurement_date", unit="", presence_filter={"metric_name": "bmi"},
                   stale_after_days=None, category="body"),
    HealthSyncType("waist", "Waist Circumference", "apps.health.models.BodyCompositionEntry",
                   "measurement_date", unit="in", presence_filter={"metric_name": "waist"},
                   stale_after_days=None, category="body"),

    # ── Mobility (MobilityEntry — field-keyed) ────────────────────────────── #
    HealthSyncType("walking_speed", "Walking Speed", "apps.health.models.MobilityEntry", "metric_date",
                   unit="mph", presence_filter={"walking_speed__isnull": False}, stale_after_days=None,
                   category="mobility"),
    HealthSyncType("step_length", "Step Length", "apps.health.models.MobilityEntry", "metric_date",
                   unit="in", presence_filter={"step_length__isnull": False}, stale_after_days=None,
                   category="mobility"),
    HealthSyncType("walking_asymmetry", "Walking Asymmetry", "apps.health.models.MobilityEntry",
                   "metric_date", unit="%", presence_filter={"walking_asymmetry__isnull": False},
                   stale_after_days=None, category="mobility"),
    HealthSyncType("double_support_time", "Double Support Time", "apps.health.models.MobilityEntry",
                   "metric_date", unit="%", presence_filter={"double_support_time__isnull": False},
                   stale_after_days=None, category="mobility"),
    HealthSyncType("walking_steadiness", "Walking Steadiness", "apps.health.models.MobilityEntry",
                   "metric_date", unit="", presence_filter={"walking_steadiness__gt": ""},
                   stale_after_days=None, category="mobility"),
    HealthSyncType("stair_ascent_speed", "Stair Ascent Speed", "apps.health.models.MobilityEntry",
                   "metric_date", unit="ft/s", presence_filter={"stair_ascent_speed__isnull": False},
                   stale_after_days=None, category="mobility"),
    HealthSyncType("stair_descent_speed", "Stair Descent Speed", "apps.health.models.MobilityEntry",
                   "metric_date", unit="ft/s", presence_filter={"stair_descent_speed__isnull": False},
                   stale_after_days=None, category="mobility"),
    HealthSyncType("six_min_walk", "Six-Minute Walk", "apps.health.models.MobilityEntry", "metric_date",
                   unit="m", presence_filter={"six_min_walk_distance__isnull": False},
                   stale_after_days=None, category="mobility"),

    # ── Nutrition ─────────────────────────────────────────────────────────── #
    HealthSyncType("water", "Water", "apps.health.models.WaterEntry", "logged_date",
                   unit="fl oz", stale_after_days=None, category="nutrition"),
    HealthSyncType("caffeine", "Caffeine", "apps.health.models.SleepEntry", "sleep_date",
                   unit="mg", presence_filter={"caffeine_mg__isnull": False}, stale_after_days=None,
                   category="nutrition"),
    HealthSyncType("dietary_nutrients", "Nutrition (Macros & Micros)",
                   "apps.health.models.DietaryNutrientEntry", "metric_date", unit="",
                   stale_after_days=None, category="nutrition"),

    # ── Hearing ───────────────────────────────────────────────────────────── #
    HealthSyncType("headphone_audio", "Headphone Audio", "apps.health.models.AudioExposureEntry",
                   "metric_date", unit="dB", presence_filter={"headphone_level_db__isnull": False},
                   stale_after_days=None, category="hearing"),
    HealthSyncType("environmental_audio", "Environmental Audio", "apps.health.models.AudioExposureEntry",
                   "metric_date", unit="dB", presence_filter={"environmental_level_db__isnull": False},
                   stale_after_days=None, category="hearing"),

    # ── Mental Wellbeing ──────────────────────────────────────────────────── #
    HealthSyncType("mindful_minutes", "Mindful Minutes", "apps.health.models.SleepEntry", "sleep_date",
                   unit="min", presence_filter={"mindful_minutes__isnull": False}, stale_after_days=None,
                   category="mental"),

    # ── Workouts ──────────────────────────────────────────────────────────── #
    HealthSyncType("workout", "Workouts", "apps.health.models.WorkoutSession", "date",
                   unit="workouts", stale_after_days=None, category="workouts"),
]

HEALTH_SYNC_TYPES_BY_KEY = {t.key: t for t in HEALTH_SYNC_TYPES}

# Status values (most→least healthy)
STATUS_HEALTHY = "healthy"     # recent records, within expected cadence
STATUS_STALE = "stale"         # has records but older than the expected cadence
STATUS_IDLE = "idle"           # has records; type is irregular so "stale" doesn't apply
STATUS_NO_DATA = "no_data"     # never received any record for this type
RECENT_WINDOW_DAYS = 7


def _as_datetime(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    if isinstance(value, date):
        return timezone.make_aware(datetime(value.year, value.month, value.day))
    return None


def _type_status(user, t: HealthSyncType, now: datetime) -> dict:
    """Deterministic health for one data type from persisted records only."""
    Model = t.get_model()
    qs = Model.objects.filter(user=user, source=APPLE_HEALTH)
    if t.presence_filter:
        qs = qs.filter(**t.presence_filter)

    latest = qs.order_by(f"-{t.date_field}").first()
    total = qs.count()
    recent_cutoff = (now - timedelta(days=RECENT_WINDOW_DAYS)).date()
    recent = qs.filter(**{f"{t.date_field}__gte": recent_cutoff}).count()

    if latest is None or total == 0:
        return {
            "key": t.key, "label": t.label, "unit": t.unit, "category": t.category,
            "status": STATUS_NO_DATA, "last_record_at": None,
            "recent_count": 0, "total_count": 0, "stale_days": None,
            "message": "No records received",
        }

    last_dt = _as_datetime(getattr(latest, t.date_field))
    stale_days = (now.date() - last_dt.date()).days if last_dt else None

    if t.stale_after_days is None:
        status = STATUS_IDLE
        message = f"Last synced {_humanize_days(stale_days)}"
    elif stale_days is not None and stale_days > t.stale_after_days:
        status = STATUS_STALE
        message = f"No new data in {stale_days} day{'s' if stale_days != 1 else ''}"
    else:
        status = STATUS_HEALTHY
        message = f"{recent} record{'s' if recent != 1 else ''} in the last {RECENT_WINDOW_DAYS} days"

    return {
        "key": t.key, "label": t.label, "unit": t.unit, "category": t.category,
        "status": status,
        "last_record_at": last_dt.isoformat() if last_dt else None,
        "recent_count": recent, "total_count": total,
        "stale_days": stale_days, "message": message,
    }


def _humanize_days(days: Optional[int]) -> str:
    if days is None:
        return "recently"
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def _latest_ingestion_run(user):
    from apps.mobile.models import HealthIngestionRun
    return (HealthIngestionRun.objects
            .filter(user=user)
            .order_by("-created_at")
            .first())


def _last_sync_summary(run) -> Optional[dict]:
    """Human-readable per-type result of the MOST RECENT sync run.

    Driven by the deterministic per-type results the ingest endpoint persisted
    (``metric_type_results``) plus its validation errors. Never fabricated.
    """
    if run is None:
        return None
    results = getattr(run, "metric_type_results", None) or {}
    errors = getattr(run, "validation_errors", None) or []
    error_types = {}
    for e in errors:
        if isinstance(e, dict) and e.get("type"):
            error_types.setdefault(e["type"], e.get("error", "error"))

    imported, no_changes, failed = [], [], []
    for key, r in results.items():
        label = HEALTH_SYNC_TYPES_BY_KEY[key].label if key in HEALTH_SYNC_TYPES_BY_KEY else key.replace("_", " ").title()
        created = int(r.get("created", 0))
        updated = int(r.get("updated", 0))
        failed_n = int(r.get("failed", 0))
        if failed_n:
            failed.append({"key": key, "label": label, "reason": error_types.get(key, "failed")})
        elif created + updated > 0:
            imported.append({"key": key, "label": label, "count": created + updated})
        else:
            no_changes.append({"key": key, "label": label})
    # Types that errored but never reached a per-type result row.
    for key, reason in error_types.items():
        if not any(f["key"] == key for f in failed):
            label = HEALTH_SYNC_TYPES_BY_KEY[key].label if key in HEALTH_SYNC_TYPES_BY_KEY else key.replace("_", " ").title()
            failed.append({"key": key, "label": label, "reason": reason})

    imported.sort(key=lambda x: -x["count"])
    return {
        "at": run.created_at.isoformat(),
        "status": run.status,
        "imported": imported,
        "no_changes": no_changes,
        "failed": failed,
    }


def _recent_runs(user, now, minutes=15, limit=12):
    """Ingestion runs in the last `minutes` — one user sync = several batch runs."""
    from apps.mobile.models import HealthIngestionRun
    cutoff = now - timedelta(minutes=minutes)
    return list(
        HealthIngestionRun.objects
        .filter(user=user, created_at__gte=cutoff)
        .order_by("-created_at")[:limit]
    )


def steps_pipeline_diagnostics(user, now: Optional[datetime] = None) -> dict:
    """Deterministic glass-box: prove exactly where Steps disappear.

    Compares, for the most recent sync session (last 15 min of batch runs):
    what the CLIENT reported it fetched/sent (``client_debug.steps``), what the
    SERVER received/processed (``metric_type_results.steps`` + validation errors),
    and what actually PERSISTED (``StepsEntry``) — then names the failing stage.
    Reusable for a Health Ops diagnostic view; safe/read-only.
    """
    now = now or timezone.now()
    runs = _recent_runs(user, now)

    # Aggregate the server's per-type steps outcome across the session's batches.
    received = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
    failure_reasons = []
    client_steps = None  # most recent client_debug.steps
    for r in runs:
        tr = (getattr(r, "metric_type_results", None) or {}).get("steps")
        if tr:
            for k in received:
                received[k] += int(tr.get(k, 0))
        for e in (getattr(r, "validation_errors", None) or []):
            if isinstance(e, dict) and (e.get("type", "").lower() == "steps"):
                failure_reasons.append(e.get("error", "error"))
        cd = (getattr(r, "client_debug", None) or {}).get("steps")
        if cd and client_steps is None:
            client_steps = cd

    from django.apps import apps as django_apps
    StepsEntry = django_apps.get_model("health", "StepsEntry")
    persisted_total = StepsEntry.objects.filter(user=user, source=APPLE_HEALTH).count()
    latest = (StepsEntry.objects.filter(user=user, source=APPLE_HEALTH)
              .order_by("-logged_date").first())
    server_touched = received["created"] + received["updated"]

    # Deterministic verdict — the failing stage.
    if not runs:
        verdict = "No sync in the last 15 minutes. Trigger a sync, then reopen this page."
        stage = "no_recent_sync"
    elif client_steps is not None and int(client_steps.get("raw_samples", -1)) == 0:
        verdict = ("HealthKit returned 0 raw step samples for the 7-day window "
                   "(even though permission is granted) — a device query/data issue, not the server.")
        stage = "healthkit_returned_zero"
    elif client_steps is not None and int(client_steps.get("built", -1)) == 0:
        verdict = ("Raw step samples exist but the daily-total (cumulative-sum) query "
                   "produced 0 metrics — the fetchSteps aggregation is the problem.")
        stage = "aggregation_zero"
    elif failure_reasons:
        verdict = f"The server RECEIVED steps but REJECTED them: {failure_reasons[0]}"
        stage = "server_rejected"
    elif (received["created"] + received["updated"] + received["skipped"] + received["failed"]) == 0:
        if client_steps is not None and int(client_steps.get("sent", 0)) > 0:
            verdict = ("The device says it SENT step metrics, but the server received none "
                       "in this session — a transport/serialization or batching/user mismatch.")
            stage = "not_received"
        else:
            verdict = ("No step metrics were sent in this session. Either fetchSteps built none, "
                       "or the client build predates glass-box telemetry (update the app).")
            stage = "not_sent"
    elif server_touched > 0 and persisted_total == 0:
        verdict = ("The server processed step metrics but no StepsEntry persisted — "
                   "a persistence anomaly (investigate process_steps_metric).")
        stage = "not_persisted"
    else:
        verdict = (f"Steps are flowing: server created/updated {server_touched} this session; "
                   f"{persisted_total} StepsEntry rows total.")
        stage = "healthy"

    return {
        "stage": stage,
        "verdict": verdict,
        "client_reported": client_steps,  # {raw_samples, built, sent} or None
        "server_received": received,
        "server_rejection_reasons": failure_reasons[:3],
        "persisted_total": persisted_total,
        "latest_persisted_date": (
            latest.logged_date.isoformat() if latest and latest.logged_date else None
        ),
        "recent_run_count": len(runs),
    }


def build_health_sync_status(user, now: Optional[datetime] = None) -> dict:
    """THE deterministic Health Sync status for a user. Facts only — never a verdict."""
    now = now or timezone.now()

    data_types = [_type_status(user, t, now) for t in HEALTH_SYNC_TYPES]
    by_key = {d["key"]: d for d in data_types}

    # Grouped by category for the redesigned Health Sync UI (ordered; a category
    # with no registered types is omitted). Presentational only — the flat
    # ``data_types`` list remains the source of truth for existing consumers.
    categories = []
    for cat_key, cat_label in CATEGORY_ORDER:
        cat_types = [d for d in data_types if d.get("category") == cat_key]
        if not cat_types:
            continue
        categories.append({
            "key": cat_key,
            "label": cat_label,
            "types": cat_types,
            "active_count": sum(1 for d in cat_types if d["status"] != STATUS_NO_DATA),
            "total_count": len(cat_types),
            "stale_count": sum(1 for d in cat_types if d["status"] == STATUS_STALE),
        })

    # Active = any type that has ever produced Apple-Health data.
    active = [d for d in data_types if d["status"] != STATUS_NO_DATA]

    # Newest data across all types.
    dated = [d for d in data_types if d["last_record_at"]]
    newest = max(dated, key=lambda d: d["last_record_at"], default=None)
    # Oldest of the ACTIVE sources (the one lagging behind the others).
    oldest = min(dated, key=lambda d: d["last_record_at"], default=None)

    # Issues (the "what's broken" summary):
    #   * any source that HAD data and went stale (a real regression), and
    #   * a phone-native core source (Steps) that has never produced data while
    #     other sources ARE syncing — i.e. sync works but this one type is absent
    #     (the exact "Steps enabled but no data" failure).
    any_active = len(active) > 0
    issues = []
    for d in data_types:
        t = HEALTH_SYNC_TYPES_BY_KEY[d["key"]]
        if d["status"] == STATUS_STALE:
            issues.append({
                "key": d["key"],
                "message": f"{d['label']} has not synced in {d['stale_days']} days.",
                "severity": "warning",
            })
        elif d["status"] == STATUS_NO_DATA and t.core and any_active:
            issues.append({
                "key": d["key"],
                "message": (
                    f"{d['label']} is enabled but no data has arrived — grant "
                    f"{d['label']} access in Apple Health → Sharing."
                ),
                "severity": "warning",
            })

    run = _latest_ingestion_run(user)

    return {
        "generated_at": now.isoformat(),
        "last_sync": (
            {"at": run.created_at.isoformat(), "status": run.status, "ingestion_id": run.id}
            if run else None
        ),
        "active_types_count": len(active),
        "total_types_count": len(data_types),
        "newest_data": (
            {"key": newest["key"], "label": newest["label"], "at": newest["last_record_at"]}
            if newest else None
        ),
        "oldest_active_source": (
            {"key": oldest["key"], "label": oldest["label"], "at": oldest["last_record_at"]}
            if oldest else None
        ),
        "issues": issues,
        "data_types": data_types,
        "categories": categories,
        "last_sync_summary": _last_sync_summary(run),
        # Temporary glass-box: pinpoint exactly where Steps disappear.
        "diagnostics": {"steps": steps_pipeline_diagnostics(user, now)},
    }
