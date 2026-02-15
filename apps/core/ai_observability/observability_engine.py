"""
IOCD — Observability Engine.

Main entry point for generating daily intelligence metrics snapshots.
Aggregates metrics from existing engine models via metrics_calculator.

Does NOT generate intelligence — only observes and records system metrics.

Project: Whole Life Journey
Path: apps/core/ai_observability/observability_engine.py

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.ai_observability.metrics_calculator import calculate_daily_metrics
from apps.core.ai_observability.models import IntelligenceMetricsSnapshot

logger = logging.getLogger(__name__)


def generate_daily_snapshot(target_date=None):
    """
    Generate a daily intelligence metrics snapshot.

    Pipeline:
    1. Default target_date to yesterday
    2. Check for existing snapshot (skip if exists)
    3. Calculate metrics from engine models
    4. Create IntelligenceMetricsSnapshot record

    Args:
        target_date: date object. Defaults to yesterday.

    Returns:
        IntelligenceMetricsSnapshot instance (new or existing).
        None on error.
    """
    try:
        if target_date is None:
            target_date = (timezone.now() - timedelta(days=1)).date()

        # Skip if already generated
        existing = IntelligenceMetricsSnapshot.objects.filter(
            snapshot_date=target_date,
        ).first()
        if existing:
            logger.info(
                f"IOCD: Snapshot already exists for {target_date}"
            )
            return existing

        # Calculate metrics
        metrics = calculate_daily_metrics(target_date)

        # Create snapshot
        snapshot = IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=target_date,
            **metrics,
        )

        logger.info(f"IOCD: Created snapshot for {target_date}")
        return snapshot

    except Exception as e:
        logger.error(f"IOCD: Failed to generate snapshot: {e}")
        return None


def get_latest_snapshot():
    """
    Get the most recent metrics snapshot.

    Returns:
        IntelligenceMetricsSnapshot or None.
    """
    return IntelligenceMetricsSnapshot.objects.first()


def get_snapshot_history(days=30):
    """
    Get snapshot history for the last N days.

    Args:
        days: Number of days to look back (default 30).

    Returns:
        QuerySet of IntelligenceMetricsSnapshot ordered by date desc.
    """
    cutoff = timezone.now().date() - timedelta(days=days)
    return IntelligenceMetricsSnapshot.objects.filter(
        snapshot_date__gte=cutoff,
    )
