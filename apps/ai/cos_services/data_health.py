# ==============================================================================
# File: apps/ai/cos_services/data_health.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Proactive Missing-Data Intervention (Proactive Phase 2, M3).
#   A compact, FACTS-ONLY truth surface over the EXISTING single authority
#   apps/health/services/health_sync_status.build_health_sync_status. It lets the certified
#   CoS reason over deterministic *source-sync* missingness — the one gap it could not see:
#   whether a health data SOURCE has stopped syncing (so a stale metric is "I can't see it",
#   not "you stopped doing it"). WLJ supplies the deterministic facts (sync state, last sync,
#   which sources are stale + how many days, any technical issues); OpenAI decides whether it
#   MATERIALLY limits its help and whether to raise it — no importance score is computed here.
#   On-demand only (not standing context) — build_health_sync_status is query-heavy, so the
#   model calls this when it suspects a data-source gap, never every turn.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)

# A source is worth flagging as "quiet" only after this many days with no records — below
# this it is simply recent/normal, not a gap. Fact threshold, not a verdict.
_STALE_SOURCE_DAYS = 3


def get_data_health(user, now=None):
    """Return a compact, facts-only view of health data-source freshness for the CoS.
    Reuses the single sync-status authority; never renders a life verdict. Never raises."""
    try:
        from apps.health.services.health_sync_status import build_health_sync_status
        raw = build_health_sync_status(user, now=now)
    except Exception:
        logger.warning("get_data_health failed user=%s", getattr(user, "pk", None),
                       exc_info=True)
        return {"status": "unavailable",
                "message": "Data-sync status could not be read right now."}

    overall = raw.get("overall_health") or {}
    last_sync = raw.get("last_sync") or None

    # Sources that have gone quiet (no records for >= threshold days) — a FACT per source,
    # never "unhealthy" (record age never condemns a source; see health_sync_status).
    quiet_sources = []
    for d in (raw.get("data_types") or []):
        days = d.get("days_since_last_record")
        if isinstance(days, (int, float)) and days >= _STALE_SOURCE_DAYS:
            quiet_sources.append({"source": d.get("label") or d.get("key"),
                                  "days_since_last_record": int(days)})
    quiet_sources.sort(key=lambda s: -s["days_since_last_record"])

    # Technical issues = the ONLY "needs attention" signal (import health), each with the
    # deterministic corrective action already defined by the authority.
    issues = [{"summary": i.get("summary") or i.get("title") or "",
               "action": i.get("action") or ""}
              for i in (raw.get("issues") or [])]

    return {
        "status": "ok",
        # 'setup' (never verifiably synced), 'healthy' (a sync has completed), 'attention'
        # (a verified technical problem). Sync-plumbing fact, not a life judgment.
        "sync_state": overall.get("status"),
        "last_sync_at": (last_sync or {}).get("at"),
        "active_sources": overall.get("active_count", 0),
        "total_sources": overall.get("total_count", 0),
        "quiet_sources": quiet_sources[:8],
        "issues": issues[:6],
        "quiet_source_threshold_days": _STALE_SOURCE_DAYS,
    }
