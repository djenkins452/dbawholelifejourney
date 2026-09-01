# ==============================================================================
# File: apps/ai/cos_services/domain_ranked_entity.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: DomainRankedEntityService — the generic "which entities rank highest/lowest
#              by a canonical measure" read surface. Answers "which meals contributed the
#              most carbs". Registry-controlled (no arbitrary DB ranking); reuses the
#              domain's canonical entity producer and its ALREADY-authoritative values.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""
DomainRankedEntityService (Model Interface — ranked-entity branch)
==================================================================

The single, generic read surface for "which X had the most/least Y over a period":

    get_domain_ranked_entity(user, "meal_by_carbs", period="this_month")

REGISTRY-CONTROLLED — NOT a query engine. Every rankable (domain, entity, measure) is a
DECLARED subject in `RANKING_SUBJECTS`. The model selects a subject KEY; it can never send a
model/table/field/order-by. There is no shadow database surface.

REUSE ONLY — the entities and their measure values come from the domain's OWN canonical
producer (`DomainTruth(user, domain).describe(entity_type, filters)`); this service reads
the ALREADY-authoritative value off each entity and hands the list to the platform ranker
(`apps.core.truth.ranked_entity.build_ranking`). It never re-computes a nutrient total, a
calorie burn, or any measure — the owning domain does. It returns canonical entity
REFERENCES (each entity's identity) so a follow-up ("tell me about the top one") flows back
into the existing entity-retrieval path.

NO FABRICATION — unknown subject → `unsupported`; unresolvable period → `unsupported`; a
measure absent on an entity → that entity is EXCLUDED (counted, never zeroed); no qualifying
entities → `empty`. Facts only; the model judges (WLJ never labels a meal good/bad).
"""

import logging
import time

from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

DOMAIN_RANKED_ENTITY_SCHEMA_VERSION = "1.0"


# ── the registry: the ONLY rankable subjects (declaration-only; no arbitrary fields) ──
# Each subject declares: the domain, the canonical entity_type its producer returns, where
# the ALREADY-authoritative measure lives on that entity (source dict + key), the unit, a
# human label, and the aggregation semantics (so the model never guesses the SQL meaning).
RANKING_SUBJECTS = {
    "meal_by_carbs": {
        "domain": "nutrition", "entity_type": "meal",
        "measure_source": "performance", "measure_key": "carbohydrates_g",
        "unit": "g", "label": "carbohydrates",
        # A "meal" is one (date, meal_type) OCCURRENCE — each breakfast/lunch/dinner/snack
        # is ranked independently (the domain's canonical meal entity). NOT aggregated by
        # meal-type across days; the model infers any "your dinners tend to be highest"
        # pattern from the ranked occurrences.
        "aggregation": "occurrence",
        # Identifying detail carried INTO each ranked result (the meal's real foods), so
        # "what was in it" is answered from truth in hand — never a generic substitution.
        "detail_keys": ("meal_type", "item_count", "items"),
    },
    "transaction_by_spend": {
        "domain": "finance", "entity_type": "transaction",
        "measure_source": "definition", "measure_key": "spend_amount",
        "unit": "USD", "label": "spending",
        # A "transaction" is one OCCURRENCE — the individual purchase, ranked by its
        # own outflow magnitude. NOT aggregated by merchant or category: "which single
        # purchase was biggest" is a different question from "which merchant did I
        # spend the most at", and conflating them is how a ranking starts lying.
        "aggregation": "occurrence",
        # The producer must order by the MEASURE, not by date: its result is capped, so
        # a date-ordered population could omit the largest spend entirely.
        "producer_filters": {"order_by": "spend_desc"},
        # Identifying detail carried into each ranked result, so "what was it / where /
        # which account" is answered from the row itself.
        "detail_keys": ("payee", "category", "account", "direction", "amount"),
    },
    "transaction_by_payment": {
        "domain": "finance", "entity_type": "transaction",
        "measure_source": "definition", "measure_key": "payment_amount",
        "unit": "USD", "label": "debt/payment activity",
        # Mortgage, auto loan, credit-card settlement — real, important outflows that
        # are NOT consumption. Ranked separately so "largest payment" and "largest
        # spend" stay different questions with different answers.
        "aggregation": "occurrence",
        "producer_filters": {"order_by": "payment_desc"},
        "detail_keys": ("payee", "category", "account", "amount"),
    },
    "transaction_by_cash_outflow": {
        "domain": "finance", "entity_type": "transaction",
        "measure_source": "definition", "measure_key": "outflow_amount",
        "unit": "USD", "label": "money out",
        # The broad money-out view: consumption + payments + cash withdrawals.
        # Internal transfers are excluded by the measure — moving your own money
        # between your own accounts is not money leaving.
        "aggregation": "occurrence",
        "producer_filters": {"order_by": "outflow_desc"},
        "detail_keys": ("payee", "category", "account", "amount"),
    },
    "category_by_spend": {
        "domain": "finance", "entity_type": "category_spend",
        "measure_source": "definition", "measure_key": "spend_amount",
        "unit": "USD", "label": "spending by category",
        # Finance aggregates and Finance ranks. The model is never handed hundreds of
        # transactions to total — that is a calculation, and calculations are WLJ's.
        "aggregation": "category_total",
        "detail_keys": ("category", "transaction_count", "largest_purchase"),
    },
    "workout_by_volume": {
        "domain": "health", "entity_type": "workout",
        "measure_source": "performance", "measure_key": "strength_load_lb",
        "unit": "lb", "label": "training volume",
        # A "workout" is one completed WorkoutSession OCCURRENCE, ranked by its canonical
        # strength_load_lb (Σ ExerciseSet.volume). Not recomputed here — the workout entity
        # already carries it. "which workouts had the most volume".
        "aggregation": "occurrence",
        # The workout's REAL exercises carried into each ranked result, so "which exercises
        # had the most volume" is grounded in the actual session — not a generic guess.
        "detail_keys": ("workout_type", "exercise_count", "exercises"),
    },
}


def ranked_entity_capability_index():
    """{domain: (subject keys...)} for every registered ranking subject — the capability
    index the certifier and the model read to know what is rankable."""
    out = {}
    for key, spec in RANKING_SUBJECTS.items():
        out.setdefault(spec["domain"], []).append(key)
    return {d: tuple(sorted(keys)) for d, keys in out.items()}


def ranked_entity_capable_domains():
    return sorted(ranked_entity_capability_index().keys())


def _emit(user_id, subject, status, *, period=None, ms=None, error=None):
    try:
        logger.info(
            "DOMAIN_RANKED_ENTITY served user=%s subject=%s status=%s period=%s ms=%s "
            "error=%s", user_id, subject, status, period,
            ("%.1f" % ms) if ms is not None else "na", error)
    except Exception:
        pass


def _envelope(subject, status, **extra):
    from django.utils import timezone
    base = {
        "status": status,
        "subject": subject,
        "schema_version": DOMAIN_RANKED_ENTITY_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "granularity": "ranked_entity",
        "scope": ("The canonical entities of a registered subject, ORDERED by an "
                  "already-authoritative deterministic measure over the period, with each "
                  "entity's value, its share of the total, and a canonical reference for "
                  "follow-up. WLJ does NOT recompute the measure and does NOT rank arbitrary "
                  "fields — only declared subjects. Facts only: you decide what the ranking "
                  "means (never a 'worst/unhealthy meal' verdict from WLJ)."),
    }
    base.update(extra)
    return base


def _resolve_period_dates(user, period):
    """Resolve `period` to an inclusive (start_date, end_date) via the ONE shared temporal
    authority, or None. Accepts named periods, natural phrases, and 'last_N_days'."""
    from datetime import timedelta
    import re

    from apps.core.utils import get_user_today

    today = get_user_today(user)
    p = (period or "").strip().lower()
    if not p:
        return None
    m = re.match(r"^(?:the\s+)?(?:last|past|previous)[ _](\d+)[ _]days?$", p)
    if m:
        n = max(1, min(int(m.group(1)), 3660))
        return (today - timedelta(days=n - 1), today)
    from apps.core.truth.periods import NAMED_PERIODS, resolve_date_expression, resolve_period
    if p in set(NAMED_PERIODS):
        per = resolve_period(p, today)
        return (per.start, per.end)
    try:
        per = resolve_date_expression(period, today)
    except Exception:
        per = None
    if per is not None:
        return (per.start, per.end)
    return None


def _entity_value(entity, source, key):
    """Read the ALREADY-authoritative measure off a CompleteEntity's declared source dict."""
    d = getattr(entity, source, None)
    if isinstance(d, dict):
        v = d.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return None


def get_domain_ranked_entity(user, subject, *, period="this_month",
                             order="desc", limit=10):
    """
    Return the ranked entities for a REGISTERED `subject` over `period`, as a JSON-safe
    envelope. Reuses the domain's canonical `describe(entity_type)` producer and the
    platform ranker; never recomputes the measure or ranks arbitrary fields.

    Args:
        user: Django User instance.
        subject: a registered ranking subject key (see `RANKING_SUBJECTS`), e.g.
            'meal_by_carbs'.
        period: the window — a named period, a natural phrase ('this month', 'last 30
            days'), or 'last_N_days'. Defaults to 'this_month'.
        order: 'desc' (most first, default) or 'asc' (least first).
        limit: bounded top-N (default 10, max 50).

    Returns:
        dict envelope. `status` ∈ {"ready", "empty", "unsupported", "error"}.
    """
    t0 = time.monotonic()
    uid = getattr(user, "id", "?")
    subject_norm = (subject or "").strip().lower()

    spec = RANKING_SUBJECTS.get(subject_norm)
    if spec is None:
        _emit(uid, subject_norm, "unsupported")
        return _envelope(subject_norm, "unsupported",
                         reason=(f"Unknown ranking subject '{subject_norm}'."),
                         supported_subjects=sorted(RANKING_SUBJECTS))

    dates = _resolve_period_dates(user, period)
    if dates is None:
        _emit(uid, subject_norm, "unsupported", period=period)
        return _envelope(subject_norm, "unsupported",
                         reason=(f"Unresolvable period '{period}'. Pass the natural "
                                 f"expression the user said — 'this month', 'past month', "
                                 f"'last 30 days' — or a named period. Pass their WORDS; "
                                 f"do not translate them: 'past month' is the trailing 30 "
                                 f"days and 'last month' is the previous CALENDAR month, "
                                 f"so substituting one for the other answers a different "
                                 f"question than the one asked."))

    try:
        from apps.core.truth.domain import get_domain_truth, registered_domains
    except Exception as exc:
        _emit(uid, subject_norm, "error", error=type(exc).__name__)
        return _envelope(subject_norm, "error",
                         reason="Truth layer unavailable; see server logs.")

    domain = spec["domain"]
    if domain not in registered_domains():
        _emit(uid, subject_norm, "unsupported")
        return _envelope(subject_norm, "unsupported",
                         reason=f"Domain '{domain}' is not registered.")

    try:
        truth = get_domain_truth(user, domain)
        # A subject may declare the retrieval its MEASURE requires (e.g. order by the
        # measure so a capped producer cannot truncate the ranking). Declaration-only —
        # the model still cannot send arbitrary filters.
        producer_filters = dict(spec.get("producer_filters") or {})
        producer_filters.update({"start": dates[0].isoformat(),
                                 "end": dates[1].isoformat()})
        entities = truth.describe(spec["entity_type"], filters=producer_filters)
    except Exception as exc:
        logger.warning("domain_ranked_entity: describe failed user=%s subject=%s",
                       uid, subject_norm, exc_info=True)
        _emit(uid, subject_norm, "error", error=type(exc).__name__)
        return _envelope(subject_norm, "error",
                         reason="Entity retrieval failed; see server logs.")

    from apps.core.truth.ranked_entity import RankItem, build_ranking
    items = []
    detail_keys = spec.get("detail_keys") or ()
    for e in (entities or []):
        defn = getattr(e, "definition", {}) or {}
        occurred = defn.get("date")
        # Carry the entity's OWN canonical IDENTIFYING detail (the subject declares WHICH
        # definition keys — a meal's foods, a workout's exercises) INTO the ranked result, so
        # "which had the most, and what was in it / which exercises" is answered from the
        # truth already in hand. Without the entity's real sub-items the model was observed
        # to SUBSTITUTE generic examples (e.g. "squats/deadlifts") for a top workout whose
        # actual exercises it never saw (2026-08-14). Domain's own detail — no recompute.
        meta = {k: defn[k] for k in detail_keys if k in defn}
        items.append(RankItem(
            ref=str(getattr(e, "identity", "") or ""),
            name=str(getattr(e, "identity", "") or ""),
            value=_entity_value(e, spec["measure_source"], spec["measure_key"]),
            occurred_on=(occurred.isoformat() if hasattr(occurred, "isoformat")
                         else (str(occurred) if occurred else None)),
            meta=meta,
        ))

    ranking = build_ranking(
        items, measure=spec["measure_key"], unit=spec["unit"],
        domain=domain, entity_type=spec["entity_type"], subject=subject_norm,
        order=order, limit=limit)
    ranking = _jsonsafe(ranking)
    ms = (time.monotonic() - t0) * 1000

    if not ranking.get("present"):
        _emit(uid, subject_norm, "empty", period=period, ms=ms)
        return _envelope(
            subject_norm, "empty", period=period, measure=spec["measure_key"],
            unit=spec["unit"], aggregation=spec["aggregation"],
            entities_ranked=ranking.get("entities_ranked", 0),
            missing_excluded=ranking.get("missing_excluded", 0),
            reason=(f"No {domain} {spec['entity_type']} entities with "
                    f"{spec['label']} in '{period}'."))

    _emit(uid, subject_norm, "ready", period=period, ms=ms)
    return _envelope(subject_norm, "ready", period=period, label=spec["label"],
                     aggregation=spec["aggregation"],
                     **{k: v for k, v in ranking.items() if k != "subject"})
