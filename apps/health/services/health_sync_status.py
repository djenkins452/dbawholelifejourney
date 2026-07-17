"""
Health Sync Status — the ONE deterministic truth for "is Apple Health synchronization
working?".

THREE INDEPENDENT TRUTHS (never conflate them — this separation is the whole point):

  1. IMPORT HEALTH   — did synchronization technically work?
                       Derived ONLY from the canonical ingestion audit truth
                       (``HealthIngestionRun``: run status, per-type results,
                       validation errors, and the client's own fetch telemetry).
                       This is the ONLY thing that may produce "Needs Attention".

  2. SOURCE ACTIVITY — did this metric actually produce records?
                       Derived from the persisted health rows. This is ACTIVITY truth
                       (what the user did / what the device measured) — NEVER health.

  3. ACTIVITY CLASS  — should records be expected regularly at all?
                       Declared once per type in the canonical registry
                       (``healthkit_registry.activity_class``).

WHY (incident 2026-07-16): the previous engine had a single axis — days since the last
data row — and had to express all three truths through it. So six days without stairs
rendered as "Flights Climbed has not synced in 6 days", telling the user something was
broken while synchronization was working perfectly. Record age is NOT evidence of a sync
failure. It never was.

THE RULE, structurally enforced:

    Record age can never mark a source unhealthy. For EVERY activity class — including
    `continuous` — absence of data is at most informational ("No recent X records").
    A source is only unhealthy when the ingestion truth PROVES a technical problem:
    the run failed, this type's records were rejected, the app could not read the type
    from Apple Health, or the device has stopped checking in altogether.

What WLJ deliberately does NOT claim: HealthKit hides read-authorization, so we never
guess "authorized"/"denied"/"unsupported" from silence. We only report a read problem
when the iOS client tells us its fetch actually failed (``client_debug[type].fetch_failed``).

Request-path safe: one bounded indexed query per registered type plus one ingestion-run
lookup. No heavy compute, no LLM.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from django.utils import timezone

APPLE_HEALTH = "apple_health"


# The canonical HealthKit registry (apps/health/healthkit_registry.py) is THE single
# source of truth for every synced type — identifier, WLJ metric, units, fetch
# strategy, storage destination, telemetry, activity class, category, and display
# metadata. This module re-exports it under the historical Health-Sync names so
# existing consumers keep working. To add a type, add ONE row to the canonical registry.
from apps.health.healthkit_registry import (  # noqa: E402
    HealthKitType as HealthSyncType,
    HEALTHKIT_TYPES,
    CATEGORY_ORDER,
    CATEGORY_LABELS,
    CONTINUOUS,
)

# Telemetry projection: every registry row that opts into Health Sync status.
HEALTH_SYNC_TYPES = [t for t in HEALTHKIT_TYPES if t.telemetry]
HEALTH_SYNC_TYPES_BY_KEY = {t.key: t for t in HEALTH_SYNC_TYPES}

# ── 1. Import health (technical truth — the ONLY source of "needs attention") ──
IMPORT_OK = "ok"                          # the sync path ran and this type wasn't rejected
IMPORT_FAILED = "failed"                  # this type's records were rejected by ingest
IMPORT_BLOCKED = "blocked"                # the app could not READ this type from Apple Health
IMPORT_NEVER_ATTEMPTED = "never_attempted"  # no ingestion run has ever happened

# ── Account-level sync path health ──
SYNC_OK = "ok"
SYNC_NEVER = "never_synced"
SYNC_NOT_CHECKING_IN = "not_checking_in"  # the app/device has stopped sending data
SYNC_FAILED = "failed"                    # the most recent run failed outright

# ── 2. Source activity (what the user/device produced — never health) ──
ACTIVITY_RECENT = "recent"
ACTIVITY_NONE_RECENTLY = "none_recently"
ACTIVITY_NEVER = "never"

# ── Display status (per type). Back-compatible with shipped iOS clients, which read
#    healthy | idle | no_data; "attention" is the new, verified-problem-only value. ──
STATUS_HEALTHY = "healthy"      # importing fine + produced records recently
STATUS_IDLE = "idle"            # importing fine + no recent records (NORMAL, not a fault)
STATUS_NO_DATA = "no_data"      # never received any record for this type
STATUS_ATTENTION = "attention"  # a VERIFIED technical problem (import truth proves it)

RECENT_WINDOW_DAYS = 7
# How long without ANY ingestion run before the sync path itself is the problem. This is
# the one true "we are not hearing from your phone" signal — it replaces the 13 per-metric
# false alarms the old record-age rule produced.
DEVICE_CHECKIN_STALE_HOURS = 48


def _as_datetime(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    if isinstance(value, date):
        return timezone.make_aware(datetime(value.year, value.month, value.day))
    return None


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


def _error_types(run) -> dict:
    """{metric_type: error message} from the run's validation errors."""
    out = {}
    for e in (getattr(run, "validation_errors", None) or []):
        if isinstance(e, dict) and e.get("type"):
            out.setdefault(e["type"], e.get("error", "error"))
    return out


def _sync_path_health(run, now) -> dict:
    """Account-level TECHNICAL truth: is the app/device successfully delivering data?

    This is the only place "synchronization is broken" can be established, and it is
    established from ingestion runs — never from the age of health records.
    """
    if run is None:
        return {"status": SYNC_NEVER, "last_run_at": None, "last_run_status": None,
                "error_message": ""}

    age_hours = (now - run.created_at).total_seconds() / 3600.0
    if run.status == "failed":
        status = SYNC_FAILED
    elif age_hours > DEVICE_CHECKIN_STALE_HOURS:
        status = SYNC_NOT_CHECKING_IN
    else:
        status = SYNC_OK
    return {
        "status": status,
        "last_run_at": run.created_at.isoformat(),
        "last_run_status": run.status,
        "error_message": (getattr(run, "error_message", "") or ""),
    }


def _type_import_health(t: HealthSyncType, run, error_types: dict) -> tuple:
    """Per-type TECHNICAL truth from the ingestion audit. Returns (state, reason).

    A type simply absent from the run's results is NOT a failure — it means the client
    had nothing to send for it, which is the normal case for event-driven metrics.
    """
    if run is None:
        return IMPORT_NEVER_ATTEMPTED, ""

    if t.key in error_types:
        return IMPORT_FAILED, error_types[t.key]

    results = (getattr(run, "metric_type_results", None) or {}).get(t.key) or {}
    try:
        if int(results.get("failed", 0)) > 0:
            return IMPORT_FAILED, "records were rejected during import"
    except (TypeError, ValueError):
        pass

    # The client's own glass-box telemetry: it TRIED to read this type from Apple Health
    # and the read failed (HealthKit Code=5 — permission not granted, or the type isn't
    # available on this device). This is the ONLY proof of a read problem we ever have;
    # Apple deliberately hides authorization state, so we never infer it from silence.
    debug = (getattr(run, "client_debug", None) or {}).get(t.key) or {}
    try:
        if int(debug.get("fetch_failed", 0)) > 0:
            return IMPORT_BLOCKED, "Apple Health did not allow this data to be read"
    except (TypeError, ValueError):
        pass

    return IMPORT_OK, ""


def _type_status(user, t: HealthSyncType, now: datetime, run,
                 error_types: dict) -> dict:
    """The three truths for one data type, kept separate.

    ``import_health``  — technical (from ingestion truth)
    ``source_activity``— did records arrive (from persisted rows)
    ``activity_class`` — should they be expected (from the registry)

    ``status`` is the derived display value, and it can only be "attention" when
    import_health proves a problem. Record age never contributes to it.
    """
    Model = t.get_model()
    qs = Model.objects.filter(user=user, source=APPLE_HEALTH)
    if t.presence_filter:
        qs = qs.filter(**t.presence_filter)

    latest = qs.order_by(f"-{t.date_field}").first()
    total = qs.count()
    recent_cutoff = (now - timedelta(days=RECENT_WINDOW_DAYS)).date()
    recent = qs.filter(**{f"{t.date_field}__gte": recent_cutoff}).count()

    last_dt = _as_datetime(getattr(latest, t.date_field)) if latest is not None else None
    days_since = (now.date() - last_dt.date()).days if last_dt else None

    import_health, import_reason = _type_import_health(t, run, error_types)

    # ── Source activity (activity truth only) ──
    # "Recent" means within the type's expected cadence when it has one (continuous
    # types), otherwise within the standard 7-day observation window.
    window = t.stale_after_days if t.stale_after_days is not None else RECENT_WINDOW_DAYS
    if latest is None or total == 0:
        source_activity = ACTIVITY_NEVER
    elif days_since is not None and days_since > window:
        source_activity = ACTIVITY_NONE_RECENTLY
    else:
        source_activity = ACTIVITY_RECENT

    # ── Derived display status. Attention ONLY from verified technical truth. ──
    if import_health in (IMPORT_FAILED, IMPORT_BLOCKED):
        status = STATUS_ATTENTION
    elif source_activity == ACTIVITY_NEVER:
        status = STATUS_NO_DATA
    elif source_activity == ACTIVITY_RECENT:
        status = STATUS_HEALTHY
    else:
        # Has produced records before, none lately. Normal for every class — a rest day,
        # no stairs, the scale untouched, the watch not worn. Informational, never a fault.
        status = STATUS_IDLE

    message = _type_message(t, status, import_health, import_reason,
                            recent, days_since)

    return {
        "key": t.key, "label": t.label, "unit": t.unit, "category": t.category,
        # ── the three separated truths ──
        "import_health": import_health,
        "import_reason": import_reason,
        "source_activity": source_activity,
        "activity_class": t.activity_class,
        # ── derived display ──
        "status": status,
        "last_record_at": last_dt.isoformat() if last_dt else None,
        "recent_count": recent, "total_count": total,
        "days_since_last_record": days_since,
        # Legacy alias kept for shipped iOS clients (Int?); it is a FACT (record age),
        # not a verdict — nothing derives health from it any more.
        "stale_days": days_since,
        "message": message,
    }


def _type_message(t: HealthSyncType, status, import_health, import_reason,
                  recent, days_since) -> str:
    """Product wording derived from the facts. Never claims a sync problem the
    ingestion truth hasn't proven — in particular, never says "has not synced"."""
    if import_health == IMPORT_BLOCKED:
        return f"Apple Health isn't sharing {t.label} with WLJ"
    if import_health == IMPORT_FAILED:
        return f"Last import rejected {t.label}: {import_reason}"
    if status == STATUS_NO_DATA:
        return "No records received"
    if status == STATUS_HEALTHY:
        return f"{recent} record{'s' if recent != 1 else ''} in the last {RECENT_WINDOW_DAYS} days"
    # STATUS_IDLE — no recent records. Say exactly that, and nothing more.
    return f"No recent {t.label} records — last {_humanize_days(days_since)}"


def _last_sync_summary(run) -> Optional[dict]:
    """Human-readable per-type result of the MOST RECENT sync run.

    Driven by the deterministic per-type results the ingest endpoint persisted
    (``metric_type_results``) plus its validation errors. Never fabricated.
    """
    if run is None:
        return None
    results = getattr(run, "metric_type_results", None) or {}
    error_types = _error_types(run)

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


def _build_issues(data_types, sync_path, any_active) -> list:
    """The "what is actually broken" list. EVERY entry must be backed by verified
    technical truth — an ingestion failure, a proven read block, or the device having
    stopped checking in. Inactivity NEVER appears here.

    ``action`` drives the client's corrective affordance and is only
    "open_health_settings" when Apple Health sharing is the PROVEN cause.
    """
    issues = []

    # Account-level: the sync path itself.
    if sync_path["status"] == SYNC_FAILED:
        detail = sync_path.get("error_message") or "the last sync did not complete"
        issues.append({
            "key": "_sync", "severity": "warning", "action": "open_app_and_sync",
            "message": f"Your last health sync failed — {detail}",
        })
    elif sync_path["status"] == SYNC_NOT_CHECKING_IN:
        issues.append({
            "key": "_sync", "severity": "warning", "action": "open_app_and_sync",
            "message": (
                "WLJ hasn't received health data from your iPhone in over "
                f"{DEVICE_CHECKIN_STALE_HOURS // 24} days. Open WLJ on your iPhone to sync."
            ),
        })

    # Per-type: only verified technical problems.
    for d in data_types:
        t = HEALTH_SYNC_TYPES_BY_KEY[d["key"]]
        if d["import_health"] == IMPORT_BLOCKED:
            issues.append({
                "key": d["key"], "severity": "warning", "action": "open_health_settings",
                "message": (
                    f"{d['label']} could not be read from Apple Health — turn it on under "
                    f"Apple Health → Sharing → Whole Life Journey."
                ),
            })
        elif d["import_health"] == IMPORT_FAILED:
            issues.append({
                "key": d["key"], "severity": "warning", "action": None,
                "message": f"{d['label']} was rejected during the last sync: {d['import_reason']}",
            })
        elif (d["status"] == STATUS_NO_DATA and t.core and any_active
              and sync_path["status"] not in (SYNC_FAILED, SYNC_NOT_CHECKING_IN)):
            # Sync demonstrably works (other sources HAVE arrived) yet a phone-native,
            # universally-produced source has NEVER delivered a single record. The
            # evidence is the other sources' data, not record age. Suppressed when the
            # sync path is already known broken — the account-level issue covers that.
            issues.append({
                "key": d["key"], "severity": "warning", "action": "open_health_settings",
                "message": (
                    f"{d['label']} has never sent data while your other sources are "
                    f"syncing — grant {d['label']} access in Apple Health → Sharing."
                ),
            })
    return issues


def build_health_sync_status(user, now: Optional[datetime] = None) -> dict:
    """THE deterministic Health Sync status for a user. Facts only — never a verdict."""
    now = now or timezone.now()

    run = _latest_ingestion_run(user)
    sync_path = _sync_path_health(run, now)
    error_types = _error_types(run)

    data_types = [
        _type_status(user, t, now, run, error_types)
        for t in HEALTH_SYNC_TYPES
    ]

    # Grouped by category for the Health Sync UI (ordered; a category with no
    # registered types is omitted). Presentational only — the flat ``data_types``
    # list remains the source of truth for existing consumers.
    categories = []
    for cat_key, cat_label in CATEGORY_ORDER:
        cat_types = [d for d in data_types if d.get("category") == cat_key]
        if not cat_types:
            continue
        attention = sum(1 for d in cat_types if d["status"] == STATUS_ATTENTION)
        categories.append({
            "key": cat_key,
            "label": cat_label,
            "types": cat_types,
            "active_count": sum(1 for d in cat_types if d["status"] != STATUS_NO_DATA),
            "total_count": len(cat_types),
            "attention_count": attention,
            # Legacy alias for shipped iOS clients (SyncCategory.staleCount drives the
            # category badge). It now counts VERIFIED problems, never inactivity.
            "stale_count": attention,
        })

    # Active = any type that has ever produced Apple-Health data.
    active = [d for d in data_types if d["status"] != STATUS_NO_DATA]
    any_active = len(active) > 0

    dated = [d for d in data_types if d["last_record_at"]]
    newest = max(dated, key=lambda d: d["last_record_at"], default=None)
    oldest = min(dated, key=lambda d: d["last_record_at"], default=None)

    issues = _build_issues(data_types, sync_path, any_active)

    # ── Account-level rollup ──
    # HEALTH is import health: how many sources are importing without a technical
    # problem. Inactivity is NOT sickness, and an idle source is NOT "artificially
    # healthy" — it is simply not unhealthy, because nothing is wrong with it.
    attention_types = [d for d in data_types if d["status"] == STATUS_ATTENTION]
    healthy_count = sum(
        1 for d in active if d["status"] != STATUS_ATTENTION
    )
    if not any_active and sync_path["status"] in (SYNC_NEVER,):
        overall_status = "setup"          # nothing has ever synced
    elif issues:
        overall_status = "attention"      # a VERIFIED technical problem
    else:
        overall_status = "healthy"

    # ACTIVITY, reported separately and never labeled as health.
    produced_recently = sum(1 for d in data_types if d["source_activity"] == ACTIVITY_RECENT)
    no_recent_records = sum(
        1 for d in data_types if d["source_activity"] == ACTIVITY_NONE_RECENTLY
    )

    overall_health = {
        "status": overall_status,
        "healthy_count": healthy_count,
        "active_count": len(active),
        "total_count": len(data_types),
        "issue_count": len(issues),
        "attention_count": len(attention_types),
    }

    return {
        "generated_at": now.isoformat(),
        "overall_health": overall_health,
        # The technical truth about synchronization itself (the new authority for
        # "is sync working?"). Consumers should read THIS, not record ages.
        "sync_path": sync_path,
        "source_activity_summary": {
            "produced_recently": produced_recently,
            "no_recent_records": no_recent_records,
            "never_recorded": sum(
                1 for d in data_types if d["source_activity"] == ACTIVITY_NEVER
            ),
        },
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
