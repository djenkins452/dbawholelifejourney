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
# NOTE: keys answered by the date-scoped/carry-forward authorities are NOT listed
# here — `current_weight`, `calories_today`, `protein_today` and the `*_yesterday`
# keys were removed from this map when they were delegated (2026-07-22). A key must
# have exactly ONE producer; leaving a stale SAE spec behind is how the two drift.
# Field names verified against live SAE state (health/medicine/nutrition modules).
_FACT_MAP = {
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
    # (`sleep_last_night` is answered by CurrentHealth.latest_sleep — see
    # _SLEEP_FACT_KEYS. Its old 7-day-average spec was UNREACHABLE dead config and was
    # removed with the other duplicates; `average_sleep_7d` below still serves that
    # genuinely different question.)
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

# Batch 1 — PER-DAY deterministic facts. The classifier
# (foundational_facts._refine_to_day) routes "yesterday/today/last night" questions here.
#
# SINGLE DATE-SCOPED AUTHORITY (2026-07-22 — WLJ_WEIGHT_YESTERDAY_INVESTIGATION):
# these keys are CONVENIENCE NAMES for "metric X on calendar date D". They no longer
# retrieve anything themselves — each DELEGATES to the one date-scoped authority
# (`metric_date.metric_on_date`), which in turn delegates to the systematic history
# authority behind `get_history`. This surface previously read
# DailyHealthQueries.weight_on(), whose `recorded_at__date__lte` CARRIED FORWARD an
# older observation and returned it under `for_date: <yesterday>` — contradicting
# get_history's exact-date empty for the identical question. Curated keys must never
# hold a second implementation of a deterministic question.
#
# DERIVED, NEVER HAND-LISTED (2026-07-22 — WLJ_NUTRITION_PROTEIN_INVESTIGATION):
# the day keys used to be a hand-maintained dict, and its INCOMPLETENESS was itself a
# defect. `calories_yesterday` existed but `protein_yesterday` did not, so a "protein
# yesterday" question made the model substitute the nearest key it was offered —
# `protein_today` — which correctly returned "not recorded for TODAY" and was reported
# as YESTERDAY's answer, while the page showed 79 g (runtime-proven 2/2). Measured
# across the capability index: 3 of 5 curated metrics were asymmetric.
#
# The key set is now DERIVED from the systematic capability index, so `<metric>_today`
# and `<metric>_yesterday` exist for EVERY metric that the one date-scoped authority
# can answer, symmetrically, by construction. A metric can never again be offered for
# one date but not the other.
_DAY_SUFFIXES = {"_today": 0, "_yesterday": 1}


def _date_scoped_index():
    """{key: (domain, metric, days_back)} for every metric × {today, yesterday} the
    systematic history authority advertises. Computed from `history_capability_index()`
    — one source, so this can never drift from what is actually answerable."""
    from apps.ai.cos_services.domain_history import history_capability_index
    out = {}
    for domain, metrics in (history_capability_index() or {}).items():
        for metric in metrics:
            for suffix, days in _DAY_SUFFIXES.items():
                key = f"{metric}{suffix}"
                # First domain to claim a metric name wins; a genuine collision would
                # be ambiguous for the caller, so it is never silently reassigned.
                out.setdefault(key, (domain, metric, days))
    return out


class _DateScopedFacts(dict):
    """Lazy view of `_date_scoped_index()` — the capability index needs the Django app
    registry, which is not ready at import time. Behaves as the mapping it replaced."""

    def _resolved(self):
        return _date_scoped_index()

    def get(self, key, default=None):
        return self._resolved().get(key, default)

    def __getitem__(self, key):
        return self._resolved()[key]

    def __contains__(self, key):
        return key in self._resolved()

    def __iter__(self):
        return iter(self._resolved())

    def __len__(self):
        return len(self._resolved())

    def keys(self):
        return self._resolved().keys()

    def items(self):
        return self._resolved().items()

    def values(self):
        return self._resolved().values()


_DATE_SCOPED_FACTS = _DateScopedFacts()

# Goal/target scalars that ACCOMPANY a delegated value. The target is a stored
# preference, not an observation — it is attached alongside the fact (clearly a
# different kind of thing) rather than being re-derived or allowed to keep the whole
# key on the snapshot path. key -> (SAE module, target field).
_FACT_TARGETS = {
    "calories_today": ("nutrition", "calorie_target"),
    "protein_today": ("nutrition", "protein_target"),
}

# RESIDUAL (deliberate, logged): `sleep_last_night` names a relative NIGHT, not a
# calendar date, and its canonical accessor (`CurrentHealth` → `latest_sleep`) returns
# the most recent sleep record regardless of date. Whether "last night" maps to
# yesterday's or today's `SleepEntry.sleep_date` (night-of vs wake date) is a separate
# truth question that needs its own runtime proof — changing it blind would silently
# alter every sleep answer. It keeps its existing authority for now and is routed
# through the SAME envelope so its semantics are disclosed, not implied.
_SLEEP_FACT_KEYS = {"sleep_last_night"}

def _is_day_fact_key(key):
    """True for any derived `<metric>_today` / `<metric>_yesterday` key, or sleep."""
    return key in _SLEEP_FACT_KEYS or key in _DATE_SCOPED_FACTS


def day_fact_keys():
    """Every date-scoped key this surface can SERVE (derived; complete by construction)."""
    return set(_DATE_SCOPED_FACTS) | _SLEEP_FACT_KEYS

# Current/latest keys whose honest meaning is "the most recent observation" — a
# CARRY-FORWARD contract. They delegate to the explicitly-named carry-forward
# authority so the real observation date and age travel WITH the value. Previously
# `current_weight` read the SAE snapshot, which `get_user_state()` rebuilds only when
# the row is missing — a populated-but-stale snapshot stayed authoritative forever and
# carried no freshness envelope at all (prod: a 105-day-old value reported as "your
# current weight").
_LATEST_OBSERVATION_FACTS = {
    "current_weight": ("health", "weight"),
}

def supported_facts():
    """Every key this surface can SERVE — including all derived day keys. Used by
    internal/legacy callers that name a key directly."""
    return sorted(set(_FACT_MAP) | day_fact_keys() | set(_LATEST_OBSERVATION_FACTS))


# ---------------------------------------------------------------------------
# RETRIEVAL AUTHORITY METADATA CONTRACT (platform F0).
# Every key this surface serves declares its authority + semantics, so ownership is
# MECHANICALLY classifiable and never requires reading this file. Declarations are
# honest: a key still backed by its own snapshot is declared `shadow_authority`, which
# is what makes the remaining residuals countable instead of invisible.
# ---------------------------------------------------------------------------

# Curated keys that still read the SAE snapshot directly. Declared truthfully so the
# contract test can pin them; each is closed by delegating or renaming (see
# docs/WLJ_RETRIEVAL_PLATFORM_CERTIFICATION.md F1-F6).
_CURATED_DECLARATIONS = {
    # (semantics, truth_category, classification, note)
    "average_glucose_yesterday": (
        "rolling_average", "metric", "shadow_authority",
        "Name claims a date scope but serves a 7-day average; F1 = rename."),
    "last_glucose_reading": (
        "latest_observation", "metric", "shadow_authority",
        "Latest-observation key still on SAE; F2 = delegate as current_weight did."),
    "steps_recent": (
        "rolling_average", "metric", "shadow_authority",
        "7-day average under a recency-implying name; F3 = rename."),
    "latest_meal_logged": (
        "latest_observation", "record", "shadow_authority",
        "Nutrition entity authority owns meals; F4 = delegate."),
    "average_sleep_7d": (
        "rolling_average", "metric", "shadow_authority",
        "Snapshot aggregate; claims no date scope so cannot contradict exact-date."),
    "sleep_trend": (
        "rolling_average", "metric", "shadow_authority",
        "Snapshot-derived trend; same class as average_sleep_7d."),
    "weight_30_day_change": (
        "aggregate", "metric", "shadow_authority",
        "Snapshot delta; get_history windows own change."),
    "last_blood_pressure_reading": (
        "latest_observation", "metric", "missing_projection",
        "Canonical bp_systolic/bp_diastolic/bp_pulse exist; F6 = composite projection."),
    # Served by the loop but absent from every key set — an anonymous key found BY
    # the F0 contract itself. It reads the canonical prior-reading accessor (never the
    # SAE "latest"), so it is a compliant projection; it was simply never declared.
    "previous_glucose_reading": (
        "latest_observation", "metric", "projection",
        "Canonical prior-reading accessor; declared by F0 (was undeclared)."),
}

# Keys whose declaration must name a delegation target (projections), resolved when
# the declaration is built rather than hard-coded beside the note above.
_CURATED_DELEGATES = {
    "previous_glucose_reading": "CurrentHealth.previous_glucose",
}


def authority_declarations():
    """{key: AuthorityDeclaration} for EVERY key this surface can serve.

    Derived day keys and delegating keys are declared programmatically from the same
    index that produces them, so a declaration can never drift from what is served.
    """
    from apps.core.truth import authority as A
    out = {}
    # Derived <metric>_today / <metric>_yesterday — projections of the one
    # date-scoped authority, which is itself a projection of get_history.
    for key, (domain, metric, _days) in (_date_scoped_index() or {}).items():
        out[key] = A.AuthorityDeclaration(
            authority=f"metric_date.metric_on_date:{domain}.{metric}",
            semantics=A.EXACT_DATE, truth_category=A.CATEGORY_METRIC,
            classification=A.PROJECTION_OF,
            delegates_to=f"get_domain_history:{domain}.{metric}")
    # "Current/latest" carry-forward keys.
    for key, (domain, metric) in _LATEST_OBSERVATION_FACTS.items():
        out[key] = A.AuthorityDeclaration(
            authority=f"metric_date.latest_observation_on_or_before:{domain}.{metric}",
            semantics=A.LATEST_ON_OR_BEFORE, truth_category=A.CATEGORY_METRIC,
            classification=A.PROJECTION_OF,
            delegates_to=f"get_domain_history:{domain}.{metric}")
    # Sleep — a disclosed residual on its own canonical accessor (not a shadow: it
    # delegates to CurrentHealth and discloses its semantics).
    for key in _SLEEP_FACT_KEYS:
        out[key] = A.AuthorityDeclaration(
            authority="CurrentHealth.latest_sleep", semantics=A.LATEST_OBSERVATION,
            truth_category=A.CATEGORY_METRIC, classification=A.PROJECTION_OF,
            delegates_to="CurrentHealth.latest_sleep",
            note="Night-of vs wake-date is a separate truth question; semantics disclosed.")
    # Medicine — reads LIVE from the canonical Medicine Domain Truth, never SAE.
    for key in _MEDICINE_DOMAIN_KEYS:
        out[key] = A.AuthorityDeclaration(
            authority="MedicineQueries", semantics=A.CURRENT,
            truth_category=A.CATEGORY_INVENTORY, classification=A.PROJECTION_OF,
            delegates_to="MedicineQueries")
    # Curated snapshot-backed keys — declared honestly (mostly defects).
    for key, (sem, cat, cls, note) in _CURATED_DECLARATIONS.items():
        spec = _FACT_MAP.get(key) or {}
        module, field = spec.get("module"), spec.get("value")
        delegates = _CURATED_DELEGATES.get(key, "")
        out[key] = A.AuthorityDeclaration(
            authority=(delegates or (f"SAE.{module}.{field}" if module and field
                                     else f"health_facts.{key}")),
            semantics=sem, truth_category=cat, classification=cls,
            delegates_to=delegates, note=note)
    return out


def served_keys():
    """Every key `get_foundational_health_facts` can actually RETURN — including keys
    handled only inside the serve loop (e.g. `previous_glucose_reading`). This is the
    set the F0 contract test validates declarations against."""
    return set(supported_facts()) | set(_MEDICINE_DOMAIN_KEYS) | set(_CURATED_DECLARATIONS)


def model_facing_facts():
    """The keys ADVERTISED to the conversational model — deliberately WITHOUT the
    date-scoped `<metric>_today`/`<metric>_yesterday` keys.

    "Metric X on calendar date D" has ONE door: `get_history`, which answers every
    metric for every date and takes the natural date expression. Advertising a second,
    curated door for the same question is what produced the defect — the model picks
    the curated key, and if the exact (metric, date) pair is missing from the list it
    substitutes the nearest one and answers falsely. Removing the keys from the enum
    removes the choice; nothing is lost, because `get_history` answers strictly more.

    `sleep_last_night` and the `current_*`/latest keys REMAIN: they are not
    date-scoped questions (see `_SLEEP_FACT_KEYS` / `_LATEST_OBSERVATION_FACTS`).
    """
    return sorted(set(_FACT_MAP) | _SLEEP_FACT_KEYS | set(_LATEST_OBSERVATION_FACTS))


# Back-compat module attribute; resolved LAZILY (the capability index needs the Django
# app registry, which is not ready at import time). Still the full SERVEABLE set —
# legacy callers name keys directly and must keep resolving.
def __getattr__(name):
    if name == "SUPPORTED_FACTS":
        return supported_facts()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

_META_FIELDS = ("unit", "trend", "recorded_at", "count", "target", "diastolic",
                "for_date", "as_of", "exact")


def _day_fact(user, key):
    """Per-day fact → flat dict from the ONE date-scoped metric authority.

    This key is a NAME for "metric X on calendar date D"; `metric_date` is the only
    producer of that answer. When the requested day holds no observation the result is
    an honest `status="not_recorded"` — never a neighbouring day's value wearing this
    date's label.
    """
    from apps.ai.cos_services import metric_date as _md
    spec = _DATE_SCOPED_FACTS.get(key)
    if spec is None:
        if key in _SLEEP_FACT_KEYS:
            return _sleep_fact(user, key)
        return {"status": "unsupported_fact", "supported": sorted(day_fact_keys())}
    from datetime import timedelta
    domain, metric, days_back = spec
    today = _md.user_today(user)
    return _md.metric_on_date(user, domain, metric, today - timedelta(days=days_back),
                              today=today)


def _sleep_fact(user, key):
    """`sleep_last_night` — kept on its existing canonical accessor (see the
    `_SLEEP_FACT_KEYS` residual note) but with its semantics DISCLOSED, so no consumer
    can mistake a latest-record read for an exact-date one."""
    from apps.core.truth.domain import get_domain_truth
    fact = get_domain_truth(user, "health").current(key).to_fact_dict()
    if isinstance(fact, dict):
        fact.setdefault("semantics", "latest_observation")
        fact.setdefault("authority", "CurrentHealth.latest_sleep")
    return fact


def _latest_observation_fact(user, key):
    """A "current/latest" fact → the explicitly-named CARRY-FORWARD authority, so the
    value always travels with the date it was actually observed and its age. A stale
    value can still be returned — it simply can no longer pretend to be today's."""
    from apps.ai.cos_services import metric_date as _md
    domain, metric = _LATEST_OBSERVATION_FACTS[key]
    today = _md.user_today(user)
    return _md.latest_observation_on_or_before(user, domain, metric, today,
                                               today=today)


# Medication facts answered by the canonical Medicine Domain Truth (read live, never SAE).
_MEDICINE_DOMAIN_KEYS = {
    "current_medications", "current_supplements", "current_otc", "current_wellness",
    "current_intake_all", "medications_remaining_today",
    "medication_execution_today", "supplement_execution_today",
    "medication_profile", "supplement_profile",
    "adherence_7d", "adherence_30d", "adherence_90d",
    "supplement_adherence_7d", "supplement_adherence_30d", "supplement_adherence_90d",
}


def _medicine_fact(user, key):
    """Medication fact → flat dict, retrieved through the canonical Medicine DOMAIN TRUTH
    (`get_domain_truth(user, "medicine").current(key)`). Read live from the canonical
    models — independent of the SAE snapshot, so it can never go missing or stale."""
    from apps.core.truth.domain import get_domain_truth
    return get_domain_truth(user, "medicine").current(key).to_fact_dict()


def _previous_glucose_fact(user):
    """The immediately-prior glucose reading as a complete fact dict — value,
    timestamp, provenance, freshness, clinical interpretation, and its relation to
    the current reading. Distinguishes "only one reading" (no earlier reading) from
    "no readings at all" — it NEVER substitutes the latest reading for the previous."""
    from apps.health.services import glucose_queries
    from apps.health.services.glucose_interpretation import interpret
    from apps.core.truth import integrity as _integrity
    try:
        prev = glucose_queries.previous(user)
    except Exception:
        logger.warning("health_facts: previous glucose read failed", exc_info=True)
        return {"status": "unknown", "reason": "could not read glucose history"}
    if prev is None:
        has_current = False
        try:
            has_current = glucose_queries.latest(user) is not None
        except Exception:
            pass
        return {"status": "no_previous", "has_current": has_current,
                "reason": ("only one glucose reading on record" if has_current
                           else "no glucose readings on record")}
    fact = {
        "value": prev["value"], "unit": prev["unit"],
        "recorded_at": prev["recorded_at"], "provenance": prev["source"],
        "freshness": prev["freshness"], "relation": prev.get("relation") or {},
        "presented_as": "previous",
    }
    gi = interpret(prev["value"], prev["unit"])
    if gi:
        fact["interpretation"] = gi
    _integrity.attach(fact)         # validate the prior reading's own timestamp too
    return fact


def get_foundational_health_facts(user, keys=None):
    """
    Return focused scalar foundational health facts.

    Args:
        user: Django User instance.
        keys: list of fact keys (subset of supported_facts()). None/empty -> all.

    Returns:
        dict { key: {value, source, [unit/trend/recorded_at/count/target/note]}
                    | {status: unknown, reason}
                    | {status: unsupported_fact, supported} }
        Always small and JSON-safe; STATE-FIRST (SAE snapshot, read-only).
    """
    from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe
    from apps.core.ai_state.state_engine import get_module_state

    # A bare call (no keys) returns the SMALL foundational set — never the full
    # serveable set, which now includes ~100 derived `<metric>_today/_yesterday` keys
    # and would produce a ~48KB payload for a tool whose entire purpose is a tiny one.
    # Date-scoped keys are still served when named explicitly.
    _all = supported_facts()
    requested = [k for k in (keys or model_facing_facts())]
    if not requested:
        requested = list(model_facing_facts())

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
        # Per-day deterministic facts route to the ONE date-scoped metric authority
        # (exact-date semantics), NOT the SAE snapshot and NOT a second row read.
        if _is_day_fact_key(key):
            fact = _day_fact(user, key)
            tspec = _FACT_TARGETS.get(key)
            if tspec and isinstance(fact, dict):
                tval = _state(tspec[0]).get(tspec[1])
                if tval not in (None, ""):
                    fact["target"] = tval
            out[key] = _jsonsafe(fact)
            continue
        # "Current/latest" facts route to the explicitly-named carry-forward authority,
        # which discloses the real observation date + age instead of implying "now".
        if key in _LATEST_OBSERVATION_FACTS:
            out[key] = _jsonsafe(_latest_observation_fact(user, key))
            continue
        # PRIOR-READING TRUTH: the immediately-prior glucose reading — DISTINCT and
        # EARLIER than the current one. Canonical Layer 1 accessor, never the SAE
        # "latest" (previous must never collapse into current).
        if key == "previous_glucose_reading":
            out[key] = _jsonsafe(_previous_glucose_fact(user))
            continue
        spec = _FACT_MAP.get(key)
        if spec is None:
            out[key] = {"status": "unsupported_fact",
                        "supported": _all}
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
            # PROVENANCE: the human-facing source (device/manual), so "where did that
            # come from?" answers the SOURCE — not the SAE pipeline debug string.
            if key == "last_glucose_reading":
                # NOT presented_as="current": a "last reading" is a HISTORICAL point
                # lookup, so its age is a freshness caveat, never a STALE_AS_CURRENT
                # integrity fault that withholds the value. (STALE_AS_CURRENT is
                # reserved for a claim genuinely presented as the live current value.)
                try:
                    from apps.health.services import glucose_queries as _gq
                    _lt = _gq.latest(user)
                    if _lt and _lt.get("source"):
                        fact["provenance"] = _lt["source"]
                except Exception:
                    logger.warning("health_facts: glucose provenance failed",
                                   exc_info=True)
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
        # EVIDENCE INTEGRITY (Layer 1): validate the assembled evidence BEFORE it can
        # be presented — future timestamp, out-of-order/duplicate predecessor,
        # stale-as-current — and attach the verdict so every downstream consumer
        # (the answer, every follow-up, the phrasing prompt) reads it instead of
        # re-checking. Subsumes the old ad-hoc future-timestamp guard (which it
        # keeps: a future time is still flagged and the impossible value dropped).
        #
        # STALE_AS_CURRENT applies ONLY to a claim presented as the user's LIVE
        # current value (current_*). A "last reading" (last_glucose_reading) is a
        # HISTORICAL point lookup — its age is an honest caveat carried by the
        # freshness layer, NOT an integrity fault that withholds the value. Marking
        # it "current" made an old-but-real reading refuse to answer ("what was my
        # last glucose reading?" → an investigation instead of the number).
        from apps.core.truth import integrity as _integrity
        _presented = "current" if key.startswith("current_") else None
        _integrity.attach(fact, presented_as=_presented)
        out[key] = fact

    # CALORIE questions want a TOTAL: "no food logged" = 0 calories (a real, numeric
    # answer), never "unknown" (which would leave the reply without a value and fail a
    # calorie value-gate). Meal questions are a separate intent and are unaffected.
    # ("not_recorded" is the date-scoped authority's honest absence — the same
    # condition the older "unknown"/"no_data" statuses expressed. The derived nature of
    # the zero stays DISCLOSED rather than implied.)
    for ck in ("calories_today", "calories_yesterday"):
        cur = out.get(ck)
        if isinstance(cur, dict) and cur.get("status") in ("unknown", "no_data",
                                                           "not_recorded"):
            out[ck] = {"value": 0, "unit": "kcal", "source": "nutrition",
                       "freshness": "current", "semantics": "derived_zero",
                       "requested_date": cur.get("requested_date"),
                       "reason": "No food logged for that day — 0 kcal consumed."}

    # RETRIEVAL AUTHORITY METADATA CONTRACT (platform F0): every served value carries
    # its declared authority + semantics, so ownership is mechanically classifiable
    # and never requires reading this file. `stamp` never overwrites what the
    # canonical producer already supplied — a delegated fact keeps its own, more
    # specific, authority.
    try:
        from apps.core.truth import authority as _authority
        _decls = authority_declarations()
        for _k, _f in out.items():
            _d = _decls.get(_k)
            if _d is not None:
                _authority.stamp(_f, _d)
    except Exception:  # pragma: no cover - metadata must never break truth delivery
        logger.warning("health_facts: authority stamping skipped", exc_info=True)

    return _jsonsafe(out)
