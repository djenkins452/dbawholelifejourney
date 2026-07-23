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
# REQUEST-PATH SAFETY: only LIGHT, bounded single-module builders belong here —
# they run synchronously on the read path, so a heavy builder would violate the
# "no heavy recomputation on the request thread" guarantee. journal (~5 queries)
# and nutrition (~10 queries) qualify. `health` does NOT: its builder
# (`build_health_state`) is the ~69-query heavy path, so it was removed
# (2026-07-05) — health snapshot freshness comes from the write-time async warm
# (`enqueue_module_warm(user, "health")` fired by the health.* event subscribers)
# plus the periodic SAME cycle, never a synchronous read-path rebuild. Device- and
# aggregate-driven modules must stay background-only.
_MANUAL_MODULE_SOURCES = {
    "journal": ("apps.journal.models.JournalEntry", "updated_at"),
    "nutrition": ("apps.health.models.FoodEntry", "updated_at"),
    # Faith is manual-entry too: a prayer or a marked reading day must feel
    # near-real-time when Beth reads faith truth on the request path (the
    # journal-snapshot staleness class, 2026-06-16). Two raw write surfaces →
    # a tuple OF (path, field) pairs; the staleness check below is satisfied by
    # a newer write in EITHER. build_faith_state (~10 bounded queries) is the
    # light single-module rebuild, comparable to nutrition. (The routine→faith
    # bridge is a different write path with its own refresh; this covers the
    # DIRECT faith entries — prayers and reading-plan day completions.)
    "faith": (
        ("apps.faith.models.PrayerRequest", "updated_at"),
        ("apps.faith.models.UserReadingProgress", "updated_at"),
    ),
}


# DATE-BOUND modules: their snapshot describes a specific user-local CALENDAR DAY, so
# they go stale when the DAY changes even though no raw row was written. A raw-write
# check structurally cannot see that (there is no write to detect), so overnight the
# snapshot kept reporting yesterday's totals under `daily_*` — the snapshot said 79 g
# "today" while the canonical authority said not_recorded (runtime-proven 2026-07-23,
# docs/WLJ_NUTRITION_STATE_INVESTIGATION.md).
# module -> the state field holding the ISO date those day-bound fields describe.
_DATE_BOUND_MODULES = {
    "nutrition": "daily_totals_date",
}


def day_bound_field(module):
    """The state field holding the ISO date a module's day-bound fields describe,
    or None when the module has none. Read by disclosure layers so there is ONE
    registry of which modules are day-bound."""
    return _DATE_BOUND_MODULES.get(module)


def _date_rolled_over(user, module, state_field):
    """True when the module's day-bound fields describe a DIFFERENT user-local day
    than today. One cheap dict read — no query, no aggregation. Never raises."""
    try:
        from apps.core.ai_state.state_engine import get_module_state
        from apps.core.utils import get_user_today
        stamped = (get_module_state(user, module, allow_rebuild=False) or {}).get(
            state_field)
        if not stamped:
            # Never stamped (pre-upgrade snapshot) → treat as rolled over ONCE so the
            # next read re-stamps it, rather than trusting an undated day claim.
            return True
        return str(stamped) != get_user_today(user).isoformat()
    except Exception:
        logger.warning("FRESHNESS user=%s module=%s — date check failed",
                       getattr(user, "id", "?"), module, exc_info=True)
        return False


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

    # DATE ROLLOVER first — it needs no snapshot timestamp comparison and is the one
    # staleness a raw-write check cannot detect. Same bounded single-module rebuild.
    for module in list(eligible):
        field = _DATE_BOUND_MODULES.get(module)
        if field and _date_rolled_over(user, module, field):
            try:
                from apps.core.ai_state.state_updater import update_user_state
                update_user_state(user, module)
                refreshed.add(module)
                eligible.remove(module)      # already rebuilt; skip the write check
            except Exception:
                logger.warning("FRESHNESS user=%s module=%s — date-rollover repair "
                               "failed", getattr(user, "id", "?"), module,
                               exc_info=True)

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
        # Normalize to a tuple OF (path, field) pairs. A single source is a flat
        # 2-tuple of strings ((path, field)) → wrap into a 1-tuple; a multi-source
        # value is already a tuple of pairs (its first element is a tuple) → leave.
        if sources and isinstance(sources[0], str):
            sources = (sources,)
        try:
            is_stale = False
            for dotted_path, ts_field in sources:
                model = _resolve_model(dotted_path)
                # Detect across ALL rows incl. soft-deleted: soft_delete()/restore()
                # bump `updated_at` on a row hidden from the default manager, so a
                # `.objects` check would miss a deletion of the latest entry (the
                # snapshot would keep showing the deleted row). The REBUILD below
                # still uses the canonical `.objects` (excludes deleted) — only the
                # staleness DETECTION widens to catch delete/restore writes.
                mgr = getattr(model, "all_objects", None) or model.objects
                if mgr.filter(
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
