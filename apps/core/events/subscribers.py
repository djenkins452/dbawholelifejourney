"""
Event Subscribers — Connects domain events to intelligence engines.

Project: Whole Life Journey
Path: apps/core/events/subscribers.py
Purpose: Registers lightweight event handlers that trigger intelligence
         engine updates when domain data changes. Handlers enqueue work
         rather than performing heavy processing inline.

Usage:
    # Import this module during app startup (e.g., in AppConfig.ready())
    # to register all event subscriptions.
    import apps.core.events.subscribers  # noqa: F401

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

from apps.core.events.domain_events import EventTypes, subscribe

logger = logging.getLogger(__name__)


# =========================================================================
# Class A vs Class B health-event routing (latency Phase 1)
# =========================================================================
#
# Class B = safety-sensitive / reasoning-critical writes. The
# DailyHealthSummaryBuilder MUST run synchronously so the next CoS or
# Beth reasoning pass sees the just-written value. These stay on the
# request thread.
#
# Class A = everything else under health.*. The builder is deferred to a
# Celery task so the user's dashboard reload doesn't block on a 1.5–3s
# rebuild. The SAE cache is still invalidated synchronously; the
# summary catches up asynchronously (~1–2s after).
#
# Hard-coded (not config) so a misroute can't happen via a settings
# typo. New safety-critical event types must be added here explicitly.
SYNC_HEALTH_EVENTS = frozenset({
    EventTypes.HEALTH_GLUCOSE_LOGGED,
    EventTypes.HEALTH_BP_LOGGED,          # treat all BP as Class B (crisis-range possible)
    EventTypes.HEALTH_SYNC_COMPLETED,     # iOS/CGM/Dexcom batch — may include glucose
})


# =========================================================================
# SAE — State Awareness Engine (invalidate user state on data changes)
# =========================================================================

@subscribe("health.*")
def on_health_event_invalidate_state(event):
    """Invalidate SAE cached state and rebuild today's health summary.

    Cache invalidation always runs synchronously so the next request
    sees fresh state. The DailyHealthSummaryBuilder runs sync for
    Class B (safety-sensitive) events and is deferred to Celery for
    Class A (habit-tracking) events — see SYNC_HEALTH_EVENTS above.
    """
    if not event.user:
        return
    try:
        from django.core.cache import cache
        cache_key = f"wlj:user_state:{event.user.id}"
        cache.delete(cache_key)
        logger.debug(
            "SAE cache invalidated for user %s (event: %s)",
            event.user.id, event.event_type,
        )
    except Exception as e:
        logger.debug("SAE cache invalidation skipped: %s", e)

    # Class A vs B routing.
    is_class_b = event.event_type in SYNC_HEALTH_EVENTS
    if is_class_b:
        # Class B — sync rebuild. Trust contract: glucose / BP / sync
        # ingestion drive safety reasoning; the next read must see
        # fresh summary data.
        try:
            from datetime import date
            from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
            DailyHealthSummaryBuilder().build_for_date(event.user, date.today())
        except Exception:
            logger.warning(
                "Class B health summary rebuild failed (event=%s user=%s)",
                event.event_type, event.user.id, exc_info=True,
            )
    else:
        # Class A — defer to Celery. Eliminates ~1.5–3s of
        # request-thread cost per water/coffee/medication/etc.
        try:
            from datetime import date
            from apps.health.tasks import deferred_rebuild_health_summary
            deferred_rebuild_health_summary.delay(
                event.user.id, date.today().isoformat(),
            )
        except Exception:
            logger.warning(
                "Class A health summary defer failed (event=%s user=%s) — "
                "falling back to sync rebuild for correctness",
                event.event_type, event.user.id, exc_info=True,
            )
            # Fail-safe: if Celery enqueue fails (broker down, etc.),
            # fall back to sync so we don't lose the summary update
            # entirely. Worst case: same latency as before this change.
            try:
                from datetime import date as _d
                from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
                DailyHealthSummaryBuilder().build_for_date(event.user, _d.today())
            except Exception:
                logger.error(
                    "Class A sync fallback ALSO failed (event=%s user=%s)",
                    event.event_type, event.user.id, exc_info=True,
                )


@subscribe("journal.*")
def on_journal_event_invalidate_state(event):
    """Invalidate SAE cached state when journal data changes."""
    if not event.user:
        return
    try:
        from django.core.cache import cache
        cache.delete(f"wlj:user_state:{event.user.id}")
    except Exception:
        pass


@subscribe("purpose.*")
def on_purpose_event_invalidate_state(event):
    """Invalidate SAE cached state when purpose/habit data changes."""
    if not event.user:
        return
    try:
        from django.core.cache import cache
        cache.delete(f"wlj:user_state:{event.user.id}")
    except Exception:
        pass


@subscribe("task.*")
def on_task_event_invalidate_state(event):
    """Invalidate SAE cached state when task data changes."""
    if not event.user:
        return
    try:
        from django.core.cache import cache
        cache.delete(f"wlj:user_state:{event.user.id}")
    except Exception:
        pass


@subscribe("faith.*")
def on_faith_event_invalidate_state(event):
    """Invalidate SAE cached state when faith data changes."""
    if not event.user:
        return
    try:
        from django.core.cache import cache
        cache.delete(f"wlj:user_state:{event.user.id}")
    except Exception:
        pass


# =========================================================================
# PIE — Proactive Insight Engine (check for patterns on key events)
# =========================================================================

@subscribe("health.weight.logged")
def on_weight_logged_check_insights(event):
    """Trigger lightweight weight pattern check after weight logging."""
    if not event.user:
        return
    try:
        from apps.core.ai_insights.insight_engine import check_weight_insights
        check_weight_insights(event.user)
    except ImportError:
        pass  # PIE module may not be available
    except Exception as e:
        logger.warning("PIE weight insight check failed: %s", e)


@subscribe("health.medication.taken")
def on_medication_taken_check_adherence(event):
    """Trigger adherence pattern check after medication logging."""
    if not event.user:
        return
    try:
        from apps.core.ai_insights.insight_engine import check_medication_insights
        check_medication_insights(event.user)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("PIE medication insight check failed: %s", e)


@subscribe("health.sleep.logged")
def on_sleep_logged_check_insights(event):
    """Trigger sleep pattern check after sleep logging."""
    if not event.user:
        return
    try:
        from apps.core.ai_insights.insight_engine import check_sleep_insights
        check_sleep_insights(event.user)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("PIE sleep insight check failed: %s", e)


# =========================================================================
# CoS Context — Invalidate CoS context cache on domain changes
# =========================================================================

@subscribe("health.*")
def on_health_event_invalidate_cos(event):
    """Invalidate CoS context cache when health data changes."""
    if not event.user:
        return
    try:
        from apps.ai.readiness_cache import invalidate_cos_context
        invalidate_cos_context(event.user)
    except Exception:
        pass
    try:
        from django.core.cache import cache
        cache.delete(f"cos:health_summary:{event.user.id}")
    except Exception:
        pass


@subscribe("task.*")
def on_task_change_invalidate_cos(event):
    """Invalidate CoS context cache on ANY task state change.

    Previously only subscribed to task.completed — missed task.skipped,
    task.deleted, and task.updated events, causing stale CoS reads.
    """
    if not event.user:
        return
    try:
        from apps.ai.readiness_cache import invalidate_cos_context
        invalidate_cos_context(event.user)
    except Exception:
        pass
    try:
        from django.core.cache import cache
        cache.delete(f"cos:tasks_summary:{event.user.id}")
    except Exception:
        pass


@subscribe("finance.*")
def on_finance_event_invalidate_cos(event):
    """Invalidate CoS context cache when finance data changes."""
    if not event.user:
        return
    try:
        from apps.ai.readiness_cache import invalidate_cos_context
        invalidate_cos_context(event.user)
    except Exception:
        pass


@subscribe("meals.*")
def on_meals_event_invalidate_cos(event):
    """
    Invalidate CoS context + SAE state when pantry/meals data changes.

    Added 2026-04-18 as part of the pantry signal consistency pass.
    Before this subscriber, pantry ingestion (receipt, barcode, photo
    scan) wrote to the DB but never notified the intelligence layer,
    so CoS/SAE could serve stale "user has no food" reads for up to
    the cache TTL after a grocery run. The same `meals.*` pattern now
    keeps both caches fresh regardless of ingestion source.

    Mirrors the health/task/finance pattern — fail-soft, never raises.
    """
    if not event.user:
        return
    try:
        from apps.ai.readiness_cache import invalidate_cos_context
        invalidate_cos_context(event.user)
    except Exception:
        pass
    try:
        from django.core.cache import cache
        cache.delete(f"cos:meals_summary:{event.user.id}")
        cache.delete(f"wlj:user_state:{event.user.id}")
    except Exception:
        pass


# =========================================================================
# Telemetry — Track domain event volume for observability
# =========================================================================

@subscribe("*")
def on_any_event_telemetry(event):
    """Track domain event volume for system observability."""
    try:
        from django.core.cache import cache
        # Increment daily event counter
        counter_key = "wlj:domain_events:daily_count"
        try:
            cache.incr(counter_key)
        except ValueError:
            cache.set(counter_key, 1, timeout=86400)

        # Per-type hourly counter (for Ops Wall top event types)
        type_key = f"wlj:domain_events:hourly:{event.event_type}"
        try:
            cache.incr(type_key)
        except ValueError:
            cache.set(type_key, 1, timeout=3600)
    except Exception:
        pass
