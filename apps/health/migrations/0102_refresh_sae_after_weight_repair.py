# ==============================================================================
# Data migration: refresh the persisted SAE snapshot + caches after the weight
# decontamination (2026-07-12).
#
# Blast-radius finding: migration 0100 soft-deleted the contaminated WeightEntry rows via
# the HISTORICAL model, so the real WeightEntry post_save / domain-event chain
# (subscribers.on_health_event_invalidate_state) NEVER fired. Consequently the persisted
# SAE snapshot (UserState.state_data, read with allow_rebuild=False) and the SAE cache key
# `wlj:user_state:{id}` still hold the contaminated weight_current (51.0/112.4). Every
# consumer that reads the persisted snapshot without rebuilding — the dashboard_v3 mission
# weight status, the CoS truth envelope weight_current, health-briefing trends, and the
# dashboard_v2 weight tile — would therefore stay stale until some unrelated health write
# rebuilt the snapshot. (The live consumers — Weight page, M5 card via _fresh_module_state,
# Body Intelligence — already read the canonical WeightEntry and are correct.)
#
# Targeted repair (NOT a blanket recompute): for exactly the users who had contaminated
# rows, drop the SAE cache key and rebuild the persisted snapshot from the now-clean
# WeightEntry, and invalidate the 5-minute dashboard health cache. DailyHealthSummary was
# already rebuilt in migration 0101. Idempotent; no-op on clean DBs; best-effort so a
# deploy can never be blocked.
# ==============================================================================
from django.db import migrations


_WEIGHT_UNITS = ("lb", "kg")


def refresh(apps, schema_editor):
    WeightEntry = apps.get_model("health", "WeightEntry")
    affected_ids = list(
        WeightEntry.objects.filter(status="deleted")
        .exclude(unit__in=_WEIGHT_UNITS)
        .values_list("user_id", flat=True)
        .distinct()
    )
    if not affected_ids:
        return  # clean DB — nothing to refresh

    try:
        from django.contrib.auth import get_user_model
        from django.core.cache import cache
        from apps.core.ai_state.state_engine import rebuild_user_state
    except Exception as exc:  # pragma: no cover
        print(f"  [refresh_sae] deps unavailable ({exc}); SAE will refresh on next health write")
        return

    User = get_user_model()
    refreshed = 0
    for uid in affected_ids:
        try:
            user = User.objects.filter(pk=uid).first()
            if user is None:
                continue
            cache.delete(f"wlj:user_state:{uid}")
            rebuild_user_state(user)  # recompute + persist state_data from clean WeightEntry
            try:
                from apps.dashboard.cache import DashboardCacheService
                DashboardCacheService.invalidate_health(user)
            except Exception:
                pass
            refreshed += 1
        except Exception as exc:  # pragma: no cover
            print(f"  [refresh_sae] user={uid} refresh failed ({exc}); will heal on next write")

    if refreshed:
        print(f"  [refresh_sae] rebuilt SAE snapshot for {refreshed} affected user(s)")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0101_rebuild_contaminated_daily_summaries"),
    ]

    operations = [
        migrations.RunPython(refresh, noop_reverse),
    ]
