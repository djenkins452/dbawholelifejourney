# ==============================================================================
# File: apps/core/data_retention.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Bounded, batched retention for append-only telemetry tables
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-10-21
# ==============================================================================
"""
Telemetry retention — ONE policy registry, ONE batched purge.

Eight append-only telemetry tables grew without limit because their cleanup
either never existed or was never scheduled (2026-10 Railway cost review: they
were ~5.1 GB of a 6.2 GB production database). This module is the single place
that decides how long each one is kept and the single code path that deletes.

Every retention window below is derived from the LONGEST LOOKBACK of any reader
(traced 2026-10-21), plus margin — never from the table's name. Each policy's
``rationale`` records that reader so a future change can re-check it.

Deletion is bounded and resumable:
- rows are deleted oldest-first in primary-key batches, each its own short
  transaction (autocommit), so no long lock or giant WAL spike;
- a run stops at a deadline / batch cap and reports ``complete=False``; the next
  run continues where it stopped;
- ``dry_run`` counts eligible rows and deletes nothing.

None of these models is referenced by a ForeignKey/OneToOne from any other
model and none has delete signals, so a batch delete is a single DELETE.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from django.apps import apps as django_apps
from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 2000


def _api_log_retention_days() -> int:
    return int(getattr(settings, "WLJ_SETTINGS", {}).get("API_LOG_RETENTION_DAYS", 30))


def _protect_latest_run_per_engine(qs: QuerySet) -> QuerySet:
    """Never delete an engine's most recent run, however old.

    ``heartbeat.compute_heartbeats`` reports NEVER_RUN when an engine has no
    row, and ``same_engine._detect_engine_starvation`` only raises when an
    engine has *ever* run. Purging a stalled engine's last row would turn a
    MISSED/starved engine into a silent NEVER_RUN.
    """
    model = qs.model
    # "Latest" exactly as heartbeat.compute_heartbeats defines it: newest started_at.
    latest_ids = [
        model.objects.filter(engine_name=name).order_by("-started_at", "-pk").values_list("pk", flat=True).first()
        for name in model.objects.values_list("engine_name", flat=True).distinct().order_by()
    ]
    return qs.exclude(pk__in=latest_ids)


@dataclass(frozen=True)
class RetentionPolicy:
    key: str
    model_label: str  # "app_label.ModelName"
    timestamp_field: str
    retention_days: Callable[[], int] | int
    rationale: str
    keep: Q | None = None  # rows matching this are never purged by the base window
    extra_windows: tuple[tuple[Q, int], ...] = ()  # (rows matching Q, longer retention days)
    protect: Callable[[QuerySet], QuerySet] | None = None

    @property
    def model(self):
        return django_apps.get_model(self.model_label)

    def days(self) -> int:
        return self.retention_days() if callable(self.retention_days) else self.retention_days


RETENTION_POLICIES: tuple[RetentionPolicy, ...] = (
    RetentionPolicy(
        key="engine_heartbeat",
        model_label="core.EngineHeartbeat",
        timestamp_field="observed_at",
        retention_days=7,
        rationale="Longest reader: Ops Wall cadence timeline, 120 min cap "
        "(ops_views.CadenceTimelineView). Latest-per-engine reads use the newest rows. "
        "7 days kept for incident forensics.",
    ),
    RetentionPolicy(
        key="system_integrity_snapshot",
        model_label="core.SystemIntegritySnapshot",
        timestamp_field="created_at",
        retention_days=14,
        rationale="Longest reader: Ops Wall integrity sparkline, last 30 rows (~30 min) "
        "(ops_views.IntegrityIndexView). 14 days kept for incident forensics.",
    ),
    RetentionPolicy(
        key="engine_run",
        model_label="core.EngineRun",
        timestamp_field="started_at",
        retention_days=30,
        rationale="Longest reader: diagnostic starvation scan, interval x 3 = 21 days for "
        "weekly engines (diagnostic_engine.py); heartbeat MISSED for weekly engines at 8 days; "
        "maturity safety score 7 days. The latest run per engine is always kept.",
        protect=_protect_latest_run_per_engine,
    ),
    RetentionPolicy(
        key="engine_span",
        model_label="core.EngineSpan",
        timestamp_field="started_at",
        retention_days=14,
        rationale="Only reader: staff trace-detail view by trace_id (diagnostics_views). "
        "Nothing computes from spans.",
    ),
    RetentionPolicy(
        key="decision_record",
        model_label="core.DecisionRecord",
        timestamp_field="created_at",
        retention_days=30,
        rationale="Longest reader: SAME suppression-storm 7-day baseline (same_engine.py). "
        "Also the validator/escalation audit stream, so kept 30 days to match API-log forensics.",
    ),
    RetentionPolicy(
        key="api_request_log",
        model_label="core.APIRequestLog",
        timestamp_field="created_at",
        retention_days=_api_log_retention_days,
        rationale="Longest reader: Ops API health, 24h (ops_telemetry). Security/forensic policy "
        "is WLJ_SETTINGS['API_LOG_RETENTION_DAYS'] (30, CISO review 2026-01-12). Anomaly rows "
        "are kept 90 days for security review.",
        extra_windows=((Q(is_anomaly=True), 90),),
    ),
    RetentionPolicy(
        key="arbitration_decision_log",
        model_label="core.ArbitrationDecisionLog",
        timestamp_field="timestamp",
        retention_days=30,
        rationale="Longest reader: staff observability dashboard, 7 days. Weight tuner reads the "
        "last 50 rows WITH feedback — those rows are never purged. Its all-time count() only "
        "picks WHEN tuning is attempted (every 50th decision), so a purge shifts that phase only.",
        keep=Q(user_response__isnull=False) | Q(outcome_score__isnull=False),
    ),
    RetentionPolicy(
        key="health_briefing_snapshot",
        model_label="core.HealthBriefingSnapshot",
        timestamp_field="generated_at",
        retention_days=30,
        rationale="Only reader: CoS context, latest snapshot under its 30-min TTL "
        "(cos_context._build_health_briefing_slot). Older rows are kept 30 days for the "
        "documented forensic replay by briefing_id (which appears only in logs).",
    ),
)

POLICIES_BY_KEY = {p.key: p for p in RETENTION_POLICIES}


@dataclass
class PurgeResult:
    key: str
    table: str
    retention_days: int
    eligible: int | None = None  # filled on dry run
    deleted: int = 0
    batches: int = 0
    complete: bool = True
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "table": self.table,
            "retention_days": self.retention_days,
            "eligible": self.eligible,
            "deleted": self.deleted,
            "batches": self.batches,
            "complete": self.complete,
            "error": self.error,
        }


def eligible_queryset(policy: RetentionPolicy, now=None) -> QuerySet:
    """Rows this policy would purge right now."""
    now = now or timezone.now()
    model = policy.model
    ts = policy.timestamp_field
    base_cutoff = now - timedelta(days=policy.days())

    qs = model.objects.filter(**{f"{ts}__lt": base_cutoff})
    if policy.keep is not None:
        qs = qs.exclude(policy.keep)
    for match, days in policy.extra_windows:
        # Rows in a longer window are only eligible once past THAT window.
        longer_cutoff = now - timedelta(days=days)
        qs = qs.exclude(match & Q(**{f"{ts}__gte": longer_cutoff}))
    if policy.protect is not None:
        qs = policy.protect(qs)
    return qs


def purge(
    policy: RetentionPolicy,
    *,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int | None = None,
    deadline: float | None = None,
    pause_seconds: float = 0.0,
    now=None,
) -> PurgeResult:
    """Delete one policy's expired rows oldest-first in bounded batches."""
    now = now or timezone.now()
    result = PurgeResult(key=policy.key, table=policy.model._meta.db_table, retention_days=policy.days())
    qs = eligible_queryset(policy, now=now)

    if dry_run:
        result.eligible = qs.count()
        return result

    model = policy.model
    last_pk = None  # keyset: never re-walk index entries of rows already deleted
    while True:
        if max_batches is not None and result.batches >= max_batches:
            result.complete = False
            break
        if deadline is not None and time.monotonic() >= deadline:
            result.complete = False
            break
        window = qs if last_pk is None else qs.filter(pk__gt=last_pk)
        ids = list(window.order_by("pk").values_list("pk", flat=True)[:batch_size])
        if not ids:
            break
        last_pk = ids[-1]
        deleted, _ = model.objects.filter(pk__in=ids).delete()
        result.deleted += deleted
        result.batches += 1
        if len(ids) < batch_size:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    return result


def run_retention(
    keys: list[str] | None = None,
    *,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int | None = None,
    time_budget_seconds: float | None = None,
    pause_seconds: float = 0.0,
) -> list[PurgeResult]:
    """Run every (or the named) retention policy. One table's failure never
    stops the others; failures are logged at ERROR and reported in the result."""
    policies = [POLICIES_BY_KEY[k] for k in keys] if keys else list(RETENTION_POLICIES)
    deadline = time.monotonic() + time_budget_seconds if time_budget_seconds else None
    results = []
    for policy in policies:
        try:
            result = purge(
                policy,
                dry_run=dry_run,
                batch_size=batch_size,
                max_batches=max_batches,
                deadline=deadline,
                pause_seconds=pause_seconds,
            )
        except Exception as exc:  # report, continue with the next table
            logger.error("Telemetry retention failed for %s", policy.key, exc_info=True)
            result = PurgeResult(
                key=policy.key,
                table=policy.model._meta.db_table,
                retention_days=policy.days(),
                complete=False,
                error=f"{type(exc).__name__}: {exc}",
            )
        results.append(result)
        logger.info("Telemetry retention %s", result.as_dict())
    return results
