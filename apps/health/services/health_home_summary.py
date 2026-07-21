# ==============================================================================
# File: apps/health/services/health_home_summary.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: THE single deterministic Health Home summary — facts only, read from the
#              request-path-safe SAE health snapshot. One builder; every consumer
#              (health home page + Current Context provider) reads from it.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deterministic Health Home summary (facts only).

The Health workspace's canonical Current Context summary. It projects the cached health
state into a compact facts-only shape the conversational model reasons over — WLJ never
renders a verdict ("healthy"/"at risk"); it exposes numbers only.

REQUEST-PATH SAFE — the single most important property. It reads the **already-cached**
health contract via the SAE snapshot (`get_module_state(user, 'health',
allow_rebuild=False)`), NEVER the live `build_health_state` (the ~69-query health builder,
which is banned on the request path). If the snapshot is not yet warm it returns
`status="pending"` — it NEVER falls back to a live rebuild.

Single authority / no drift: `build_health_state` (the one health-state producer) is what
the SAE caches AND what the Health Home page reads (`hs`), so this summary is rooted in the
SAME truth the page renders. This module adds NO new health calculation, NO new authority,
NO new cache — it exposes existing cached truth. Exactly the Dashboard Day Summary pattern.

Cache architecture it depends on (owned elsewhere, reused here):
  • ownership   : SAE (UserState snapshot; module key "health").
  • producer    : build_health_state (single health-state authority).
  • refresh     : SAE background cycle + incremental state_updater.
  • runtime cost: one cached dict read (allow_rebuild=False) — no queries on miss.
"""

import logging

logger = logging.getLogger(__name__)


def _pending():
    return {"status": "pending", "has_data": False}


def build_health_home_summary(user):
    """Return deterministic facts for the Health workspace (facts only, never raises).

    Shape (every metric value is optional — the SAE health snapshot carries only what the
    user has data for):
        {
          "status": "ready" | "pending",   # pending = SAE snapshot not warm yet
          "has_data": bool,
          "weight_current": float | None,
          "weight_change_30d": float | None,
          "sleep_avg_hours_7d": float | None,
          "steps_avg_7d": int | None,
          "heart_rate_avg_7d": int | None,
          "glucose_latest": float | None,
          "glucose_avg_7d": float | None,
          "bp_systolic": int | None,
          "bp_diastolic": int | None,
          "water_today_oz": float | None,
          "water_goal_oz": float | None,
          "medication_status": str | None,   # a FACT the SAE already resolved
        }
    """
    try:
        from apps.core.ai_state.state_engine import get_module_state

        # Request-path-safe: read the SAE snapshot ONLY. Never rebuild here.
        state = get_module_state(user, "health", allow_rebuild=False) or {}

        if not state:
            # Snapshot not warm — honest pending state, never a live rebuild.
            return _pending()

        return {
            "status": "ready",
            "has_data": True,
            "weight_current": state.get("weight_current"),
            "weight_change_30d": state.get("weight_change_30d"),
            "sleep_avg_hours_7d": state.get("sleep_avg_hours_7d"),
            "steps_avg_7d": state.get("steps_avg_7d"),
            "heart_rate_avg_7d": state.get("heart_rate_avg_7d"),
            "glucose_latest": state.get("glucose_latest"),
            "glucose_avg_7d": state.get("glucose_avg_7d"),
            "bp_systolic": state.get("bp_systolic"),
            "bp_diastolic": state.get("bp_diastolic"),
            "water_today_oz": state.get("water_today_oz"),
            "water_goal_oz": state.get("water_goal_oz"),
            "medication_status": state.get("medication_status"),
        }
    except Exception:  # pragma: no cover - defensive; a summary must never hard-fail
        logger.warning("build_health_home_summary failed user=%s",
                       getattr(user, "id", None), exc_info=True)
        return _pending()
