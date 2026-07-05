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
        # Class A — defer to Celery, fire-and-forget. Eliminates ~1.5–3s of
        # request-thread cost per water/coffee/medication/etc.
        #
        # No synchronous fallback: this runs on the request path, so a broker
        # outage must NOT drop into a synchronous DailyHealthSummary rebuild
        # (that reintroduces the exact 15–20s request-thread block this whole
        # change removes). safe_enqueue is bounded and swallows infra errors;
        # if the enqueue fails, the periodic SAME cycle reconciles the Class A
        # summary. A briefly-stale habit-tracking summary is acceptable.
        from datetime import date
        from apps.core.celery_utils import safe_enqueue
        from apps.health.tasks import deferred_rebuild_health_summary
        safe_enqueue(
            deferred_rebuild_health_summary,
            event.user.id, date.today().isoformat(),
        )

    # Phase 3: also warm the SAE 'health' module in the background
    # (separate from DailyHealthSummary above — different snapshot).
    # This is what lets the dashboard's read-only path see fresh
    # health gauges on the next render after a water / med / weight
    # write. Fail-safe; runs for both Class A and Class B.
    try:
        from apps.core.ai_state.tasks import enqueue_module_warm
        enqueue_module_warm(event.user, "health")
    except Exception:
        pass


def _invalidate_and_warm_sae(user, module):
    """Phase 3 — invalidate the SAE cache key and enqueue a background
    per-module warm task so the dashboard's read-only path
    (allow_rebuild=False) sees fresh state on the NEXT render WITHOUT
    a request-path rebuild.

    Replaces the old "delete only" pattern: the delete preserves
    correctness for any non-dashboard caller that still rebuilds on
    cache miss; the background warm ensures the dashboard never has
    to. Fail-safe — never raises into the subscriber.
    """
    if not user:
        return
    try:
        from django.core.cache import cache
        cache.delete(f"wlj:user_state:{user.id}")
    except Exception:
        pass
    try:
        from apps.core.ai_state.tasks import enqueue_module_warm
        enqueue_module_warm(user, module)
    except Exception:
        logger.warning(
            "SAE warm enqueue failed (user=%s module=%s)",
            getattr(user, "id", "?"), module, exc_info=True,
        )


@subscribe("journal.*")
def on_journal_event_invalidate_state(event):
    """Invalidate SAE + warm 'journal' module in background (Phase 3)."""
    _invalidate_and_warm_sae(event.user, "journal")


@subscribe("purpose.*")
def on_purpose_event_invalidate_state(event):
    """Invalidate SAE + warm 'goals' module in background (Phase 3)."""
    _invalidate_and_warm_sae(event.user, "goals")


@subscribe("task.*")
def on_task_event_invalidate_state(event):
    """Invalidate SAE + warm 'tasks' module in background (Phase 3)."""
    _invalidate_and_warm_sae(event.user, "tasks")


# =========================================================================
# Significant Event Pipeline — the Chief-of-Staff reflex (v1)
# =========================================================================
#
# Mission-significant events (a milestone or goal reaching completion) must be
# recognized and acted on IN THE MOMENT — not on the 3-hour CoS Event Engine
# schedule. Before this, a `purpose.*` event only invalidated the SAE 'goals'
# cache (above); nothing evaluated significance, notified Danny, or re-planned
# until the scheduler happened to run.
#
# These subscribers evaluate significance and ENQUEUE the reaction on a
# background worker, so the emitting request path stays fast (Observability
# Performance Law). See apps/ai/significant_events.py.

@subscribe("purpose.milestone.completed")
def on_milestone_completed_react(event):
    """Recognize + react to a milestone completion (Significant Event Pipeline)."""
    try:
        from apps.ai.significant_events import enqueue_significant_event_reaction
        enqueue_significant_event_reaction(
            event.user, event.event_type, event.data)
    except Exception:
        logger.warning("significant_event: milestone subscriber failed",
                       exc_info=True)


@subscribe("purpose.goal.completed")
def on_goal_completed_react(event):
    """Recognize + react to a goal completion (Significant Event Pipeline)."""
    try:
        from apps.ai.significant_events import enqueue_significant_event_reaction
        enqueue_significant_event_reaction(
            event.user, event.event_type, event.data)
    except Exception:
        logger.warning("significant_event: goal subscriber failed", exc_info=True)


@subscribe("faith.*")
def on_faith_event_invalidate_state(event):
    """Invalidate SAE + warm 'faith' module in background (Phase 3)."""
    _invalidate_and_warm_sae(event.user, "faith")


# =========================================================================
# PIE — Proactive Insight Engine (check for patterns on key events)
# =========================================================================

def _run_health_pie(user, action):
    """Run a real-time PIE pass for a health write.

    Routes the event into the SAME ``run_insights()`` entry point the AI
    orchestrator uses (execution_engine.py:_run_pie_chain), so the full
    rule set fires immediately on a dashboard/web write — not just on the
    next scheduled SAME-cycle pass.

    History (bug fixed 2026-06-27): these subscribers used to call
    per-domain ``check_weight_insights`` / ``check_medication_insights`` /
    ``check_sleep_insights`` helpers that NO LONGER EXIST — the engine
    consolidated on ``run_insights()``. The missing symbols raised
    ImportError, which a blanket ``except ImportError: pass`` swallowed, so
    web/dashboard dose, weight, and sleep logging fired NO insight pass at
    all — silently. ImportError is now treated as a real error (logged,
    never swallowed) because ``run_insights`` is a core dependency of these
    handlers, not an optional module. See CLAUDE.md "Exception Handling".

    Args:
        user: Django user instance (no-op if falsy).
        action: PIE action string the insight rules key on
            (e.g. "log_weight", "log_medication", "log_sleep").
    """
    if not user:
        return
    try:
        # Importing the engine module also runs apps.core.ai_insights
        # __init__, which registers every rule via @register.
        from apps.core.ai_insights.insight_engine import run_insights
        from apps.core.time.system_clock import get_current_time
    except ImportError:
        # NOT optional — run_insights is the core PIE entry point. A failure
        # here means a real breakage (renamed/removed symbol); log it loudly
        # so it can never be silently swallowed like the original bug.
        logger.warning(
            "PIE entry point unavailable — health insight pass skipped "
            "(action=%s).", action, exc_info=True,
        )
        return
    try:
        run_insights(user, {
            "event_type": "record_created",
            "module": "health",
            "action": action,
            "timestamp_utc": get_current_time().isoformat(),
        })
    except Exception:
        logger.warning(
            "PIE health insight pass failed (action=%s user=%s)",
            action, getattr(user, "id", "?"), exc_info=True,
        )


@subscribe("health.weight.logged")
def on_weight_logged_check_insights(event):
    """Trigger a real-time PIE pass after weight logging."""
    _run_health_pie(event.user, "log_weight")


@subscribe("health.medication.taken")
def on_medication_taken_check_adherence(event):
    """Trigger a real-time PIE pass after medication logging."""
    _run_health_pie(event.user, "log_medication")


@subscribe("health.sleep.logged")
def on_sleep_logged_check_insights(event):
    """Trigger a real-time PIE pass after sleep logging."""
    _run_health_pie(event.user, "log_sleep")


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
