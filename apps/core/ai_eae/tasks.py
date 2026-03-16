# ==============================================================================
# File: apps/core/ai_eae/tasks.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Celery tasks for signal aggregation
# Created: 2026-03-14 (Architecture Evolution Phase 4)
# ==============================================================================
"""
EAE Celery Tasks — Signal Aggregation & Pattern Computation

Nightly tasks that compute and persist SignalSnapshot records for all active users.
Phase 4: Signal production metrics per domain/type.
Phase 5: Cross-domain pattern computation (derived_pattern snapshots).
"""

import logging
import time

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='core.compute_nightly_signals')
def compute_nightly_signals():
    """
    Nightly signal aggregation.

    Scheduled at 11:30 PM via CELERY_BEAT_SCHEDULE.
    Iterates all active users and computes daily signal snapshots.
    Individual user failures don't halt the batch.

    Phase 4: Tracks per-domain and per-type signal production
    metrics and caches them for Ops diagnostics.
    """
    from django.contrib.auth import get_user_model
    from django.core.cache import cache
    from django.utils import timezone
    import datetime as dt

    from apps.core.utils import get_user_today
    from apps.core.ai_eae.signal_aggregation import SignalAggregationService

    User = get_user_model()

    # Only process users who have logged in within the last 30 days
    cutoff = timezone.now() - dt.timedelta(days=30)

    active_users = User.objects.filter(
        last_login__gte=cutoff,
        is_active=True,
    )

    total_users = active_users.count()
    success_count = 0
    error_count = 0
    total_signals = 0

    # Phase 4: Signal production telemetry
    signals_by_type = {}   # signal_type -> count
    signals_by_domain = {}  # domain -> count

    logger.info(
        "Starting nightly signal aggregation for %d active users",
        total_users,
    )

    for user in active_users.iterator():
        try:
            today = get_user_today(user)
            signals = SignalAggregationService.compute_daily_signals(user, today)
            total_signals += len(signals)
            success_count += 1

            # Track per-type and per-domain production
            for snapshot in signals:
                st = snapshot.signal_type
                dm = snapshot.domain
                signals_by_type[st] = signals_by_type.get(st, 0) + 1
                signals_by_domain[dm] = signals_by_domain.get(dm, 0) + 1

        except Exception as e:
            error_count += 1
            logger.error(
                "Signal aggregation failed for user %s: %s",
                user.pk, e, exc_info=True,
            )

        # Brief pause between users to avoid DB pressure
        time.sleep(0.05)

    logger.info(
        "Nightly signal aggregation complete: %d users processed, "
        "%d signals generated, %d errors",
        success_count, total_signals, error_count,
    )

    # Phase 4: Cache signal production metrics for Ops diagnostics
    signal_production_summary = {
        'timestamp': timezone.now().isoformat(),
        'total_users': total_users,
        'success_count': success_count,
        'error_count': error_count,
        'total_signals': total_signals,
        'signals_by_type': signals_by_type,
        'signals_by_domain': signals_by_domain,
        'coverage_ratio': round(
            total_signals / max(total_users, 1), 2
        ),
    }

    # Cache for 25 hours (outlives the nightly cycle)
    cache.set(
        'wlj:ops:signal_production',
        signal_production_summary,
        timeout=90000,
    )

    return signal_production_summary


@shared_task(name='core.compute_nightly_patterns')
def compute_nightly_patterns():
    """
    Phase 5: Nightly cross-domain pattern computation.

    Runs AFTER compute_nightly_signals. Reads base SignalSnapshots
    and produces derived_pattern SignalSnapshots.

    Scheduled at 4:45 AM UTC (15 minutes after signal aggregation).
    """
    from django.contrib.auth import get_user_model
    from django.core.cache import cache
    from django.utils import timezone
    import datetime as dt

    from apps.core.utils import get_user_today
    from apps.core.ai_eae.pattern_engine import PatternEngine

    User = get_user_model()

    # Only process users who have logged in within the last 30 days
    cutoff = timezone.now() - dt.timedelta(days=30)

    active_users = User.objects.filter(
        last_login__gte=cutoff,
        is_active=True,
    )

    total_users = active_users.count()
    success_count = 0
    error_count = 0
    total_patterns = 0

    # Pattern production telemetry
    patterns_by_type = {}  # pattern_type -> count

    logger.info(
        "Starting nightly pattern computation for %d active users",
        total_users,
    )

    for user in active_users.iterator():
        try:
            today = get_user_today(user)
            patterns = PatternEngine.compute_patterns(user, today)
            total_patterns += len(patterns)
            success_count += 1

            # Track per-type production
            for snapshot in patterns:
                pt = snapshot.signal_type
                patterns_by_type[pt] = patterns_by_type.get(pt, 0) + 1

        except Exception as e:
            error_count += 1
            logger.error(
                "Pattern computation failed for user %s: %s",
                user.pk, e, exc_info=True,
            )

        # Brief pause between users to avoid DB pressure
        time.sleep(0.05)

    logger.info(
        "Nightly pattern computation complete: %d users, "
        "%d patterns generated, %d errors",
        success_count, total_patterns, error_count,
    )

    # Cache pattern production metrics for Ops diagnostics
    pattern_production_summary = {
        'timestamp': timezone.now().isoformat(),
        'total_users': total_users,
        'success_count': success_count,
        'error_count': error_count,
        'total_patterns': total_patterns,
        'patterns_by_type': patterns_by_type,
        'coverage_ratio': round(
            total_patterns / max(total_users, 1), 2
        ),
    }

    # Cache for 25 hours (outlives the nightly cycle)
    cache.set(
        'wlj:ops:pattern_production',
        pattern_production_summary,
        timeout=90000,
    )

    return pattern_production_summary
