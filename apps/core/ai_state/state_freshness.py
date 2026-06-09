"""
SAE — Manual-entry freshness guard.

Manual-entry domains (journal, nutrition, medications, habits, check-ins) must
feel near real-time on the dashboard. The normal refresh path is the post_save
signal → Celery ``deferred_sae_refresh`` (see apps/ai/signals.py). That path is
fire-and-forget: ``.delay()`` only falls back to a synchronous rebuild if the
broker itself is unreachable. If the broker accepts the task but the worker is
backed up or down, the ``UserState`` snapshot silently lags until the nightly
full rebuild — and the mission card shows stale "0/wk" / "0% macros" minutes
after the user logged. That breaks dashboard trust ("did my data save?").

This guard closes that gap on the ONE path the user is staring at, without
violating the WLJ request-path rule (no heavy compute) or the signals
architecture (raw → signal → narrative, never raw → narrative):

  * Cheap staleness check — one indexed ``.exists()`` per manual module asking
    "is there a raw write newer than the snapshot?". No aggregation, no joins.
  * Targeted recompute ONLY when stale — runs the module's own SAE builder
    (journal ~5 queries, nutrition ~10), the SAME builder the signal layer
    uses. Never the 69-query health builder, never system analytics.
  * Self-healing and idempotent — after a refresh the snapshot's
    ``last_updated`` is bumped past the raw write, so the next load is a no-op.

Only modules registered in ``_MANUAL_MODULE_SOURCES`` are eligible. Device- and
aggregate-driven modules (health, fitness) are deliberately excluded — their
builders are heavy and must stay on the nightly / SAME-cycle background path.
"""

import logging

from apps.core.ai_state.models import UserState

logger = logging.getLogger(__name__)


# Registry of manual-entry modules eligible for request-path freshness repair.
# Keyed by canonical SAE module name → (model dotted path, timestamp field).
# The timestamp field is compared against ``UserState.last_updated`` to detect
# raw writes the snapshot has not yet absorbed.
#
# Phased rollout (see "deferred = phased, not maybe"): journal + nutrition ship
# now because they are the signals the mission card actually reads and were the
# reported staleness. Additional manual domains promote here the moment the
# mission card (or another request-path reader) consumes their signal:
#   - "medicine"  → apps.health.models.IntakeLog (updated_at)   [trigger: mission/Action-Center reads medicine adherence]
#   - "habits"    → apps.habits model (updated_at)              [trigger: mission reads habit streaks]
#   - "checkins"  → check-in model (updated_at)                 [trigger: mission reads check-in cadence]
# Adding one is a single registry line — no control-flow changes.
_MANUAL_MODULE_SOURCES = {
    "journal": ("apps.journal.models.JournalEntry", "updated_at"),
    "nutrition": ("apps.health.models.FoodEntry", "updated_at"),
    # Health is synced from several device/manual tables (HealthKit weight,
    # glucose, sleep). A write to ANY of them means the cached health snapshot
    # is stale — the snapshot is not invalidated on these writes, which is the
    # root cause of the stale-weight regression. A list of sources is supported.
    "health": [
        ("apps.health.models.WeightEntry", "recorded_at"),
        ("apps.health.models.GlucoseEntry", "recorded_at"),
        ("apps.health.models.SleepEntry", "recorded_at"),
    ],
}


def _resolve_model(dotted_path):
    """Import a model from its dotted path lazily (avoids app-load cycles)."""
    module_path, _, cls_name = dotted_path.rpartition(".")
    from importlib import import_module
    return getattr(import_module(module_path), cls_name)


def ensure_fresh(user, modules):
    """Repair stale manual-entry SAE modules before a request-path read.

    For each requested module that is registered as manual-entry, cheaply checks
    whether the raw table has a write newer than the persisted snapshot and, only
    when it does, runs a targeted single-module rebuild so the signal the caller
    is about to read reflects what the user just entered.

    READ-PATH SAFE: at most one ``.exists()`` per module on a clean load; a
    bounded single-module rebuild only when genuinely stale. Never raises — a
    freshness failure must never break the dashboard; the caller simply reads
    the (possibly slightly stale) snapshot as before.

    Args:
        user: Django User instance.
        modules: iterable of canonical SAE module names to consider.

    Returns:
        set[str] — modules that were actually rebuilt (for telemetry / tests).
    """
    refreshed: set[str] = set()

    eligible = [m for m in modules if m in _MANUAL_MODULE_SOURCES]
    if not eligible:
        return refreshed

    # One cheap row read. If the user has no snapshot yet, the downstream
    # get_user_state() will build it fresh anyway — nothing to repair here.
    try:
        state_obj = UserState.objects.only("last_updated").get(user=user)
    except UserState.DoesNotExist:
        return refreshed
    except Exception:
        logger.warning("FRESHNESS user=%s — snapshot read failed", getattr(user, "id", "?"), exc_info=True)
        return refreshed

    reference_ts = state_obj.last_updated
    if reference_ts is None:
        return refreshed

    for module in eligible:
        sources = _MANUAL_MODULE_SOURCES[module]
        if isinstance(sources, tuple):
            sources = (sources,)  # normalize single-source to a 1-tuple
        try:
            is_stale = False
            for dotted_path, ts_field in sources:
                model = _resolve_model(dotted_path)
                if model.objects.filter(
                    user=user, **{f"{ts_field}__gt": reference_ts}
                ).exists():
                    is_stale = True
                    break
            if not is_stale:
                continue

            from apps.core.ai_state.state_updater import update_user_state
            update_user_state(user, module)
            refreshed.add(module)
        except Exception:
            # Never let a freshness repair break the page — log and move on.
            logger.warning(
                "FRESHNESS user=%s module=%s — repair failed",
                getattr(user, "id", "?"), module, exc_info=True,
            )

    # If anything was rebuilt, drop any per-request SAE cache so the subsequent
    # get_user_state() re-reads the freshly persisted snapshot instead of a
    # stale in-memory copy set earlier in the same request.
    if refreshed and getattr(user, "_sae_cache", None) is not None:
        try:
            del user._sae_cache
        except Exception:
            pass

    return refreshed
