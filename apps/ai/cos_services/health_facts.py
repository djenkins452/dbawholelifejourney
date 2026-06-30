# ==============================================================================
# File: apps/ai/cos_services/health_facts.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Focused foundational health facts (scalar, state-first, tiny)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
get_foundational_health_facts(user, keys) — focused scalar facts for high-value
foundational questions ("what is my current weight?", "what's my glucose?", ...).

Exists because get_domain_state("health") returns the FULL health domain (70+
keys, >8KB) which the tool dispatcher truncates at 8000 chars, stripping the
actual scalar. This tool returns ONLY the requested scalars (tiny payload), read
STATE-FIRST from SAE module state (no raw ORM), with source + explainability
metadata. Missing values are explicit `{status: unknown, reason}` — never a
generic "data size constraints" failure.
"""

import logging

logger = logging.getLogger(__name__)

# fact key -> {module, value field, optional metadata fields, optional note}.
# Field names verified against live SAE state (health/medicine/nutrition modules).
_FACT_MAP = {
    "current_weight": {
        "module": "health", "value": "weight_current",
        "unit": "weight_unit", "trend": "weight_trend",
        "recorded_at": "last_weight_entry",
    },
    "weight_30_day_change": {
        # SAE health state has no 30-day delta scalar -> resolves to unknown.
        "module": "health", "value": "weight_change_30d",
        "unit": "weight_unit",
    },
    "last_glucose_reading": {
        "module": "health", "value": "latest_glucose",
        "unit": "latest_glucose_unit", "recorded_at": "last_glucose_entry",
    },
    "average_glucose_yesterday": {
        "module": "health", "value": "glucose_avg_7d",
        "unit": "latest_glucose_unit", "recorded_at": "last_glucose_entry",
        "note": "7-day average; SAE has no yesterday-specific glucose average.",
    },
    "sleep_last_night": {
        "module": "health", "value": "sleep_avg_hours_7d",
        "unit": "hours", "trend": "sleep_trend", "recorded_at": "last_sleep_entry",
        "note": "7-day average hours; SAE has no last-night-specific value.",
    },
    "average_sleep_7d": {
        "module": "health", "value": "sleep_avg_hours_7d",
        "unit": "hours", "trend": "sleep_trend",
    },
    "sleep_trend": {
        "module": "health", "value": "sleep_trend",
    },
    "current_medications": {
        "module": "medicine", "value": "active_medications",
        "count": "medication_count",
    },
    "calories_today": {
        "module": "nutrition", "value": "daily_calories",
        "unit": "kcal", "target": "calorie_target",
    },
    "protein_today": {
        "module": "nutrition", "value": "daily_protein_g",
        "unit": "g", "target": "protein_target",
    },
    "last_blood_pressure_reading": {
        "module": "health", "value": "bp_systolic",
        "diastolic": "bp_diastolic", "recorded_at": "last_bp_entry",
    },
    "latest_meal_logged": {
        # SAE has no meal name/description; the canonical truth is the date of
        # the most recent food/meal entry.
        "module": "nutrition", "value": "last_food_entry",
    },
    "steps_recent": {
        # Law 4 fix: "how many steps" previously had NO foundational fact, so it
        # fell into the LLM path (deterministic question → AI dependency). SAE has
        # no per-day steps value, so — exactly like sleep_last_night — the canonical
        # scalar is the 7-day average daily steps. Keeps steps on the deterministic
        # fast path with honest freshness when there's no data (steps_status).
        "module": "health", "value": "steps_avg_7d",
        "note": "7-day average daily steps; SAE has no yesterday-specific value.",
    },
}

# Batch 1 — PER-DAY deterministic facts. These bypass the SAE 7-day-average path
# and read the specific day straight from the canonical models via DailyHealthQueries
# ("retrieve, never derive"). The classifier (foundational_facts._refine_to_day)
# routes "yesterday/today/last night" questions here.
_DAY_FACT_KEYS = {"steps_today", "steps_yesterday", "sleep_last_night",
                  "calories_yesterday", "weight_yesterday", "glucose_yesterday"}

SUPPORTED_FACTS = sorted(set(_FACT_MAP.keys()) | _DAY_FACT_KEYS)

_META_FIELDS = ("unit", "trend", "recorded_at", "count", "target", "diastolic",
                "for_date", "as_of", "exact")


def _day_fact(user, key):
    """Per-day fact → flat dict, retrieved through the canonical Health DOMAIN TRUTH
    interface (`get_domain_truth(user, "health").current(key)`). Beth is a consumer of
    the one per-domain interface — it does not reach into individual capabilities."""
    from apps.core.truth.domain import get_domain_truth
    if key not in _DAY_FACT_KEYS:
        return {"status": "unsupported_fact", "supported": sorted(_DAY_FACT_KEYS)}
    return get_domain_truth(user, "health").current(key).to_fact_dict()


# Medication facts answered by the canonical Medicine Domain Truth (read live, never SAE).
_MEDICINE_DOMAIN_KEYS = {"current_medications", "medication_execution_today",
                         "adherence_7d", "adherence_30d", "adherence_90d"}


def _medicine_fact(user, key):
    """Medication fact → flat dict, retrieved through the canonical Medicine DOMAIN TRUTH
    (`get_domain_truth(user, "medicine").current(key)`). Read live from the canonical
    models — independent of the SAE snapshot, so it can never go missing or stale."""
    from apps.core.truth.domain import get_domain_truth
    return get_domain_truth(user, "medicine").current(key).to_fact_dict()


def get_foundational_health_facts(user, keys=None):
    """
    Return focused scalar foundational health facts.

    Args:
        user: Django User instance.
        keys: list of fact keys (subset of SUPPORTED_FACTS). None/empty -> all.

    Returns:
        dict { key: {value, source, [unit/trend/recorded_at/count/target/note]}
                    | {status: unknown, reason}
                    | {status: unsupported_fact, supported} }
        Always small and JSON-safe; STATE-FIRST (SAE snapshot, read-only).
    """
    from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe
    from apps.core.ai_state.state_engine import get_module_state

    requested = [k for k in (keys or SUPPORTED_FACTS)]
    if not requested:
        requested = list(SUPPORTED_FACTS)

    _module_cache = {}

    def _state(module):
        if module not in _module_cache:
            try:
                _module_cache[module] = (
                    get_module_state(user, module, allow_rebuild=False) or {}
                )
            except Exception:
                logger.warning("health_facts: module read failed module=%s",
                               module, exc_info=True)
                _module_cache[module] = {}
        return _module_cache[module]

    out = {}
    for key in requested:
        # MEDICATION CANONICAL TRUTH: inventory / today-execution / adherence read LIVE
        # from the Medicine Domain Truth (never the SAE snapshot), so they can't go
        # missing or stale. "Medicine" = prescription only.
        if key in _MEDICINE_DOMAIN_KEYS:
            out[key] = _jsonsafe(_medicine_fact(user, key))
            continue
        # Per-day deterministic facts route to DailyHealthQueries (specific day),
        # NOT the SAE 7-day-average path.
        if key in _DAY_FACT_KEYS:
            out[key] = _jsonsafe(_day_fact(user, key))
            continue
        spec = _FACT_MAP.get(key)
        if spec is None:
            out[key] = {"status": "unsupported_fact",
                        "supported": SUPPORTED_FACTS}
            continue

        st = _state(spec["module"])
        val = st.get(spec["value"])
        # 0 / 0.0 are VALID values (e.g. 0 calories logged today); only
        # None / missing / "" count as unknown.
        if val is None or val == "":
            out[key] = {
                "status": "unknown",
                "reason": (f"SAE {spec['module']} state did not include "
                           f"{spec['value']}."),
            }
            continue

        fact = {"value": val, "source": f"SAE.{spec['module']}.{spec['value']}"}
        for meta in _META_FIELDS:
            field = spec.get(meta)
            if field and st.get(field) not in (None, ""):
                fact[meta] = st.get(field)
        if "note" in spec:
            fact["note"] = spec["note"]
        # INTERPRETATION layer (clinical safety): glucose facts carry a deterministic
        # clinical verdict so narration can never invent reassurance over a dangerous
        # value (e.g. 43 mg/dL must never read as "good range").
        if key in ("last_glucose_reading", "average_glucose_yesterday"):
            from apps.health.services.glucose_interpretation import interpret
            gi = interpret(val, fact.get("unit", "mg/dL"))
            if gi:
                fact["interpretation"] = gi
            # SAE already removed an impossible (future) glucose time and left a
            # warning — carry it so the foundational answer surfaces it too.
            sae_tw = st.get("last_glucose_entry_warning")
            if sae_tw:
                fact["temporal_warning"] = sae_tw
                fact.pop("recorded_at", None)
            # COMPLETE the fact object: value + timestamp + freshness + confidence +
            # interpretation, so any follow-up ("at what time?") reads ONE object.
            ra = fact.get("recorded_at")
            if ra:
                from datetime import datetime
                from django.utils import timezone as _tznow2
                from apps.core.truth.freshness import classify_sync_freshness
                from apps.core.truth import confidence as _conf
                try:
                    _dt = datetime.fromisoformat(str(ra))
                    fr = classify_sync_freshness(has_data=True, last_sync=_dt,
                                                 now=_tznow2.now(),
                                                 stale_after_seconds=6 * 3600)
                    fact["freshness"] = fr
                    fact["confidence"] = _conf.confidence_from_freshness(fr)
                except (TypeError, ValueError):
                    pass
        # TEMPORAL SANITY: a timestamp in the future is a device-sync/clock artifact.
        # Flag it and drop the impossible time so narration never reports it as real.
        ra = fact.get("recorded_at")
        if ra:
            from django.utils import timezone as _tznow
            from apps.core.truth.temporal import validate_timestamp
            if validate_timestamp(ra, _tznow.now())["verdict"] == "future":
                fact["temporal_warning"] = (
                    "the timestamp on this reading is in the future — likely a sync "
                    "or clock issue, so the time is unconfirmed")
                fact.pop("recorded_at", None)
        out[key] = fact

    # CALORIE questions want a TOTAL: "no food logged" = 0 calories (a real, numeric
    # answer), never "unknown" (which would leave the reply without a value and fail a
    # calorie value-gate). Meal questions are a separate intent and are unaffected.
    for ck in ("calories_today", "calories_yesterday"):
        cur = out.get(ck)
        if isinstance(cur, dict) and cur.get("status") in ("unknown", "no_data"):
            out[ck] = {"value": 0, "unit": "kcal", "source": "nutrition",
                       "freshness": "current"}

    return _jsonsafe(out)
