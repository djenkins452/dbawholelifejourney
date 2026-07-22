# ==============================================================================
# File: apps/ai/cos_services/metric_date.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The ONE date-scoped metric authority ("metric X on calendar date D")
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-22
# ==============================================================================
"""
Date-Scoped Metric Authority — "what was metric X on calendar date D?"
======================================================================

THE single deterministic producer for a metric's value on a specific user-local
calendar date. Every convenience/curated surface (`get_foundational_health_facts`
day keys, current-value keys) DELEGATES here; none re-reads rows, re-reads a
snapshot, or applies its own date rules.

Origin (2026-07-22, `docs/WLJ_WEIGHT_YESTERDAY_INVESTIGATION.md`): four surfaces
answered "my weight yesterday" under different contracts. Proven divergence — with
no observation on the requested date, one surface silently carried forward a
105-day-old value and labelled it `for_date: yesterday`, while the systematic
history authority correctly returned empty. Two deterministic authorities, two
contradictory answers, no model involved.

TWO EXPLICITLY NAMED SEMANTICS — never conflated
------------------------------------------------
* ``metric_on_date(...)`` → ``semantics="exact_date"``
      An observation ATTRIBUTED TO THAT EXACT user-local calendar date. If none
      exists the answer is ``status="not_recorded"`` — an honest absence. It NEVER
      substitutes a neighbouring day's value.

* ``latest_observation_on_or_before(...)`` → ``semantics="latest_on_or_before"``
      The most recent observation at or before the date, WITH its real
      ``observed_on`` date and ``age_days``. Carry-forward is legitimate truth —
      but only under this name, never under an exact-date key.

REUSE ONLY. Both delegate to the systematic authority
`get_domain_history(domain, metric, period="custom", start=…, end=…)` — the same
producer behind the `get_history` tool. There is no second retrieval path here,
no ORM access, and no date math (dates come from the caller / the shared
`apps.core.truth.periods` resolver). Request-path safe: bounded aggregate reads.

The envelope is complete by contract (`_fact`): status, semantics, value, unit,
requested_date, observed_on, user_local_date, age_days, freshness, confidence,
authority. A stale value can never present as current without disclosing its real
observation date — the model can always judge usability.
"""

import logging

logger = logging.getLogger(__name__)

METRIC_DATE_SCHEMA_VERSION = "1.0"

EXACT_DATE = "exact_date"
LATEST_ON_OR_BEFORE = "latest_on_or_before"

# How far back a carry-forward read may look. Bounded so the query stays cheap and
# an ancient value can never silently masquerade as "recent".
DEFAULT_LOOKBACK_DAYS = 400


def _iso(d):
    try:
        return d.isoformat()
    except Exception:
        return None


def user_today(user):
    """The user's LOCAL today. Every date attribution in this module is user-local."""
    from apps.core.utils import get_user_today
    return get_user_today(user)


def _authority(domain, metric):
    return f"get_domain_history:{domain}.{metric}"


def _fact(*, domain, metric, semantics, status, requested_date, today,
          value=None, unit=None, observed_on=None, reason=None, **extra):
    """The complete, self-describing truth envelope every consumer reads.

    Freshness/confidence come from the shared platform classifiers — this module
    never invents its own verdicts, and never claims precision it wasn't given.
    """
    from apps.core.truth import confidence as _conf
    from apps.core.truth.freshness import classify_period_freshness

    has_data = status == "ok"
    fresh = classify_period_freshness(
        has_data=has_data, requested_date=requested_date,
        data_date=observed_on, today=today,
    )
    out = {
        "status": status,
        "semantics": semantics,
        "schema_version": METRIC_DATE_SCHEMA_VERSION,
        "domain": domain,
        "metric": metric,
        "requested_date": _iso(requested_date),
        "user_local_date": _iso(today),
        "observed_on": _iso(observed_on),
        "freshness": fresh,
        "confidence": _conf.confidence_from_freshness(fresh),
        "source": _authority(domain, metric),
        "authority": _authority(domain, metric),
    }
    if value is not None:
        out["value"] = value
    if unit:
        out["unit"] = unit
    if reason:
        out["reason"] = reason
    # Age is only meaningful once we actually observed something.
    if observed_on is not None and requested_date is not None:
        try:
            out["age_days"] = (requested_date - observed_on).days
        except Exception:
            pass
    # An exact-date answer is exact by construction; a carry-forward answer is
    # exact only when it happens to land on the requested day.
    out["exact"] = bool(has_data and observed_on == requested_date)
    # `as_of` is the platform-wide name for "the moment this value belongs to" — carried
    # so the shared integrity/precision layers read this envelope without special-casing.
    if observed_on is not None:
        out["as_of"] = _iso(observed_on)
    out.update(extra)
    # EVIDENCE INTEGRITY (Layer 1): validate the assembled evidence at COMPOSITION —
    # an impossible (future) observation date is caught here, once, rather than by each
    # consumer. A sound fact stays lean (no `integrity` key added).
    try:
        from apps.core.truth import integrity as _integrity
        _integrity.attach(out)
    except Exception:  # pragma: no cover - defensive; truth must still be returned
        logger.warning("metric_date: integrity attach skipped", exc_info=True)
    return out


def _series(user, domain, metric, start, end):
    """One delegated read through the systematic history authority.

    Returns (points, unit, error_envelope_or_None). Points are the provider's own
    per-day aggregates — never rows, never re-derived here.
    """
    from apps.ai.cos_services.domain_history import get_domain_history
    raw = get_domain_history(user, domain, metric, period="custom",
                             start=start, end=end)
    status = (raw or {}).get("status")
    if status == "ready":
        return list(raw.get("points") or []), raw.get("unit"), None
    if status == "empty":
        return [], raw.get("unit"), None
    # unsupported / unsupported_domain / error — propagate honestly, never guess.
    return None, None, raw


def _passthrough(domain, metric, raw, semantics, requested_date, today):
    """Carry a delegated failure through in THIS module's envelope shape, so a
    consumer never has to branch on which surface answered."""
    status = (raw or {}).get("status") or "error"
    return _fact(
        domain=domain, metric=metric, semantics=semantics,
        status=("unsupported" if status.startswith("unsupported") else "error"),
        requested_date=requested_date, today=today,
        reason=(raw or {}).get("reason") or "History authority could not answer.",
        delegated_status=status,
    )


def _point_value(point):
    """A point's value; None when the provider produced no usable number."""
    if not isinstance(point, dict):
        return None
    return point.get("value")


def _point_date(point):
    """A point's date as a `date`. The history providers emit ISO strings after
    JSON-safing; accept either."""
    from datetime import date as _date
    from datetime import datetime as _dt
    raw = (point or {}).get("date") if isinstance(point, dict) else None
    if isinstance(raw, _date) and not isinstance(raw, _dt):
        return raw
    if isinstance(raw, _dt):
        return raw.date()
    try:
        return _dt.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def metric_on_date(user, domain, metric, on_date, *, today=None):
    """EXACT-DATE truth: metric `domain`.`metric` observed ON `on_date`.

    Returns the standard envelope with ``semantics="exact_date"``. When no
    observation is attributed to that date the status is ``"not_recorded"`` —
    WLJ never substitutes an older value under an exact-date question.
    """
    today = today or user_today(user)
    points, unit, err = _series(user, domain, metric, on_date, on_date)
    if err is not None:
        return _passthrough(domain, metric, err, EXACT_DATE, on_date, today)

    # A single-day window yields at most one per-day aggregate point.
    point = points[-1] if points else None
    value = _point_value(point)
    observed = _point_date(point)
    if value is None or observed != on_date:
        return _fact(
            domain=domain, metric=metric, semantics=EXACT_DATE,
            status="not_recorded", requested_date=on_date, today=today, unit=unit,
            reason=f"No {metric} observation recorded on {_iso(on_date)}.",
        )
    return _fact(
        domain=domain, metric=metric, semantics=EXACT_DATE, status="ok",
        requested_date=on_date, today=today, value=value, unit=unit,
        observed_on=observed,
    )


def latest_observation_on_or_before(user, domain, metric, on_date, *, today=None,
                                    lookback_days=DEFAULT_LOOKBACK_DAYS):
    """CARRY-FORWARD truth: the most recent `domain`.`metric` observation at or
    before `on_date`, disclosed WITH its real ``observed_on`` and ``age_days``.

    ``semantics="latest_on_or_before"`` — this value must never be presented under
    an exact-date key. ``status="not_recorded"`` when nothing exists in the
    bounded lookback window.
    """
    from datetime import timedelta
    today = today or user_today(user)
    start = on_date - timedelta(days=max(1, int(lookback_days)))
    points, unit, err = _series(user, domain, metric, start, on_date)
    if err is not None:
        return _passthrough(domain, metric, err, LATEST_ON_OR_BEFORE, on_date, today)

    # The history providers order points ascending by date; the newest usable one wins.
    for point in reversed(points or []):
        value = _point_value(point)
        observed = _point_date(point)
        if value is not None and observed is not None:
            return _fact(
                domain=domain, metric=metric, semantics=LATEST_ON_OR_BEFORE,
                status="ok", requested_date=on_date, today=today, value=value,
                unit=unit, observed_on=observed, lookback_days=lookback_days,
            )
    return _fact(
        domain=domain, metric=metric, semantics=LATEST_ON_OR_BEFORE,
        status="not_recorded", requested_date=on_date, today=today, unit=unit,
        reason=(f"No {metric} observation on or before {_iso(on_date)} "
                f"within {lookback_days} days."),
        lookback_days=lookback_days,
    )
