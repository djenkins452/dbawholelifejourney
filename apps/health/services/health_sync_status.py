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

from datetime import date, datetime, timedelta
from typing import Optional

from django.utils import timezone

APPLE_HEALTH = "apple_health"


# The canonical HealthKit registry (apps/health/healthkit_registry.py) is THE single
# source of truth for every synced type — identifier, WLJ metric, units, fetch
# strategy, storage destination, telemetry, category, and display metadata. This
# module re-exports it under the historical Health-Sync names so existing consumers
# keep working. To add a type, add ONE row to the canonical registry.
from apps.health.healthkit_registry import (  # noqa: E402
    HealthKitType as HealthSyncType,
    HEALTHKIT_TYPES,
    CATEGORY_ORDER,
    CATEGORY_LABELS,
)

# Telemetry projection: every registry row that opts into Health Sync status.
HEALTH_SYNC_TYPES = [t for t in HEALTHKIT_TYPES if t.telemetry]
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

    # Account-level rollup for the Health Sync hero card. This is a DETERMINISTIC
    # status — the same kind of fact as each type's status, one level up — not an
    # interpretive verdict. ``healthy_count``/``active_count`` give the honest
    # fraction; ``no_data`` types (the user simply doesn't produce that data) are
    # NOT counted as failures, only issues (real regressions / missing core) are.
    healthy_count = sum(
        1 for d in data_types if d["status"] in (STATUS_HEALTHY, STATUS_IDLE)
    )
    if not active:
        overall_status = "setup"          # nothing has ever synced
    elif issues:
        overall_status = "attention"      # a real regression or a core source absent
    else:
        overall_status = "healthy"
    overall_health = {
        "status": overall_status,
        "healthy_count": healthy_count,
        "active_count": len(active),
        "total_count": len(data_types),
        "issue_count": len(issues),
    }

    return {
        "generated_at": now.isoformat(),
        "overall_health": overall_health,
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
    }
