# ==============================================================================
# File: apps/meals/services/meals_home_summary.py
# Project: Whole Life Journey - Meal Intelligence
# Description: THE single deterministic Meals Home summary — facts only, read from the
#              request-path-safe SAE meals snapshot. One builder; every consumer
#              (meals dashboard page + Current Context provider) reads from it.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deterministic Meals Home summary (facts only).

The Meals workspace's canonical Current Context summary. It projects the cached meals
state into a compact facts-only shape the conversational model reasons over — WLJ never
renders a verdict; it exposes counts / names / dates only.

REQUEST-PATH SAFE — the single most important property. It reads the **already-cached**
meals contract via the SAE snapshot (`get_module_state(user, 'meals',
allow_rebuild=False)`), NEVER the live `build_meals_state` (pantry / plan / profile
queries). If the snapshot is not yet warm it returns `status="pending"` — it NEVER falls
back to a live rebuild.

Single authority / no drift: `build_meals_state` (the one meals-state producer) is what the
SAE caches, so this summary is rooted in the SAME truth. This module adds NO new meals
calculation, NO new authority, NO new cache — it exposes existing cached truth. Exactly the
Dashboard Day Summary pattern.

Cache architecture it depends on (owned elsewhere, reused here):
  • ownership   : SAE (UserState snapshot; module key "meals").
  • producer    : build_meals_state (single meals-state authority; household-resolved).
  • refresh     : SAE background cycle + incremental state_updater.
  • runtime cost: one cached dict read (allow_rebuild=False) — no queries on miss.
"""

import logging

logger = logging.getLogger(__name__)


def _pending():
    return {"status": "pending", "has_household": False, "has_data": False}


def build_meals_home_summary(user):
    """Return deterministic facts for the Meals workspace (facts only, never raises).

    Shape:
        {
          "status": "ready" | "pending",   # pending = SAE snapshot not warm yet
          "has_household": bool,           # False when no household is set up
          "has_data": bool,                # a household exists (facts below are meaningful)
          "household_name": str | None,
          "grocery_cycle_days": int | None,
          "pantry_item_count": int,
          "pantry_expiring_count": int,
          "expiring_item_names": [str, ...],
          "has_dinner_planned": bool,
          "dinner_recipe": str | None,
          "protein_target_daily": float | None,
          "carb_limit_daily": float | None,
        }
    """
    try:
        from apps.core.ai_state.state_engine import get_module_state

        # Request-path-safe: read the SAE snapshot ONLY. Never rebuild here.
        state = get_module_state(user, "meals", allow_rebuild=False) or {}

        if not state:
            # Snapshot not warm — honest pending state, never a live rebuild.
            return _pending()

        # No household is a warm, ready snapshot (build_meals_state returns
        # {"has_household": False}) — distinct from a cold, unbuilt snapshot ({}).
        if not state.get("has_household"):
            return {"status": "ready", "has_household": False, "has_data": False}

        return {
            "status": "ready",
            "has_household": True,
            "has_data": True,
            "household_name": state.get("household_name"),
            "grocery_cycle_days": state.get("grocery_cycle_days"),
            "pantry_item_count": state.get("pantry_item_count", 0),
            "pantry_expiring_count": state.get("pantry_expiring_count", 0),
            "expiring_item_names": list(state.get("expiring_item_names") or []),
            "has_dinner_planned": bool(state.get("has_dinner_planned")),
            "dinner_recipe": state.get("dinner_recipe"),
            "protein_target_daily": state.get("protein_target_daily"),
            "carb_limit_daily": state.get("carb_limit_daily"),
        }
    except Exception:  # pragma: no cover - defensive; a summary must never hard-fail
        logger.warning("build_meals_home_summary failed user=%s",
                       getattr(user, "id", None), exc_info=True)
        return _pending()
