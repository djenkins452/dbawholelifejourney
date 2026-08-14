# ==============================================================================
# File: apps/ai/cos_services/domain_consistency.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: DomainConsistencyService — the generic "how regular is this repeated
#              observation over time" read surface (spread of bedtime / wake / duration
#              around their centre + whether it is tightening). Answers "how consistent
#              has my sleep schedule been".
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""
DomainConsistencyService (Model Interface — consistency branch)
===============================================================

The single, generic Model-Interface read surface for ANY repeated observation's
REGULARITY over time — the SPREAD companion to history() ("what is the LEVEL / trend").
It answers what neither history nor trend can:

    get_domain_consistency(user, "health", "sleep", period="last_month")

REUSE ONLY — delegates to `DomainTruth(user, domain).consistency(metric, start, end)`,
which builds the per-field spread with the platform Consistency capability (midnight-safe
circular statistics for clock fields, ordinary statistics for durations). This service
owns NO retrieval and NO statistics: it resolves the period (the ONE temporal authority,
`apps.core.truth.periods`) to (start, end) and hands them to the domain producer.

NO FABRICATION — unknown domain → `unsupported_domain`; unsupported metric → `unsupported`;
unresolvable period → `unsupported`; fewer than two measurable observations → `empty`
(NOT "perfectly consistent"). A missing bedtime/wake is never invented as midnight. Facts
only (centre, std-dev in minutes, arithmetic direction of the change); the model renders
the verdict ("regular" / "erratic" / "improving").
"""

import logging
import time

from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

DOMAIN_CONSISTENCY_SCHEMA_VERSION = "1.0"


def _emit(user_id, domain, metric, status, *, period=None, ms=None, error=None):
    try:
        logger.info(
            "DOMAIN_CONSISTENCY served user=%s domain=%s metric=%s status=%s "
            "period=%s ms=%s error=%s",
            user_id, domain, metric, status, period,
            ("%.1f" % ms) if ms is not None else "na", error,
        )
    except Exception:
        pass


def _envelope(domain, metric, status, **extra):
    from django.utils import timezone
    base = {
        "status": status,
        "domain": domain,
        "metric": metric,
        "schema_version": DOMAIN_CONSISTENCY_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "granularity": "consistency",
        "scope": ("The REGULARITY of a repeated observation over the period — for each "
                  "field (bedtime, wake time, duration): the typical value, how much it "
                  "varies (std dev / mean-absolute-deviation in minutes), the most and "
                  "least regular days, and whether the spread is tightening or loosening "
                  "(first half vs second half). Clock times are handled on a 24h ring so "
                  "11:50 PM and 12:10 AM are 20 min apart, not a day. Answers 'how "
                  "consistent has my schedule been'. Facts only — you decide whether more "
                  "or less regular is good, and never confuse spread with the average."),
    }
    base.update(extra)
    return base


def consistency_capability_index():
    """{domain: (consistency metrics...)} for every registered domain that answers at least
    one metric as a consistency series. Metric NAMES only — the capability index the model
    reads to know what it can pull, never the data itself."""
    try:
        from apps.core.truth.catalog import truth_catalog
        cat = truth_catalog()
    except Exception:
        logger.warning("domain_consistency: catalog read failed", exc_info=True)
        return {}
    out = {}
    for domain, supports in (cat or {}).items():
        cc = tuple(supports.get("consistency", ())
                   if isinstance(supports, dict) else ())
        if cc:
            out[domain] = cc
    return out


def consistency_capable_domains():
    return sorted(consistency_capability_index().keys())


def _resolve_period_dates(user, period):
    """Resolve `period` to an inclusive (start_date, end_date) via the ONE shared temporal
    authority, or None if unresolvable. Accepts named periods, natural phrases ('last
    month', 'the last two weeks'), and the 'last_N_days' shorthand. Never does calendar
    math beyond the shared resolver + the trailing-N shorthand. (Mirrors the event-frequency
    resolver — consistency questions are usually 'lately' ≈ the last few weeks.)"""
    from datetime import timedelta
    import re

    from apps.core.utils import get_user_today

    today = get_user_today(user)
    p = (period or "").strip().lower()
    if not p:
        return None

    m = re.match(r"^(?:the\s+)?(?:last|past|previous)[ _](\d+)[ _]days?$", p)
    if m:
        n = max(1, min(int(m.group(1)), 366))
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


def get_domain_consistency(user, domain, metric, *, period="last_month"):
    """
    Return the CONSISTENCY (regularity) series for `domain`.`metric` over `period`, as a
    JSON-safe envelope. Delegates to `DomainTruth(user, domain).consistency(metric, start,
    end)`.

    Args:
        user: Django User instance.
        domain: WLJ domain name (case-insensitive) — must be registered.
        metric: the metric whose schedule regularity is asked about (case-insensitive) —
            must be in the domain's `consistency_metrics` (see
            `consistency_capability_index`).
        period: the span of days to measure regularity over — a named period, a natural
            phrase ('last month', 'the last two weeks'), or 'last_N_days'. Defaults to
            'last_month'.

    Returns:
        dict envelope. `status` ∈ {"ready", "empty", "unsupported_domain",
        "unsupported", "error"}.
    """
    t0 = time.monotonic()
    uid = getattr(user, "id", "?")
    domain_norm = (domain or "").strip().lower()
    metric_norm = (metric or "").strip().lower()

    try:
        from apps.core.truth.domain import get_domain_truth, registered_domains
    except Exception as exc:
        logger.warning("domain_consistency: truth layer unavailable", exc_info=True)
        _emit(uid, domain_norm, metric_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="Truth layer unavailable; see server logs.")

    if domain_norm not in registered_domains():
        _emit(uid, domain_norm, metric_norm, "unsupported_domain")
        return _envelope(
            domain_norm, metric_norm, "unsupported_domain",
            reason="Unknown domain; not in the Truth Resolution Layer.",
            consistency_capable_domains=consistency_capable_domains(),
        )

    try:
        truth = get_domain_truth(user, domain_norm)
    except Exception as exc:
        logger.warning("domain_consistency: get_domain_truth failed user=%s domain=%s",
                       uid, domain_norm, exc_info=True)
        _emit(uid, domain_norm, metric_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="Domain truth read failed; see server logs.")

    supported = tuple(getattr(truth, "consistency_metrics", ()) or ())
    if not supported:
        _emit(uid, domain_norm, metric_norm, "unsupported")
        return _envelope(domain_norm, metric_norm, "unsupported",
                         reason=f"'{domain_norm}' exposes no consistency metrics.",
                         supported_metrics=[])
    if metric_norm not in supported:
        _emit(uid, domain_norm, metric_norm, "unsupported")
        return _envelope(
            domain_norm, metric_norm, "unsupported",
            reason=f"'{metric_norm}' has no consistency series for '{domain_norm}'.",
            supported_metrics=sorted(supported),
        )

    dates = _resolve_period_dates(user, period)
    if dates is None:
        _emit(uid, domain_norm, metric_norm, "unsupported", period=period)
        return _envelope(
            domain_norm, metric_norm, "unsupported",
            reason=(f"Unresolvable period '{period}'. Pass the natural expression the user "
                    f"said — 'last month', 'the last two weeks', 'last 30 days' — or a "
                    f"named period."))

    period_label = period
    try:
        payload = truth.consistency(metric_norm, dates[0], dates[1],
                                    period_label=period_label)
    except (KeyError, NotImplementedError) as exc:
        logger.warning("domain_consistency: provider declares '%s.%s' but did not resolve "
                       "it: %s", domain_norm, metric_norm, exc)
        _emit(uid, domain_norm, metric_norm, "unsupported", error=type(exc).__name__)
        return _envelope(
            domain_norm, metric_norm, "unsupported",
            reason=(f"'{metric_norm}' is advertised for '{domain_norm}' but its "
                    f"consistency provider does not resolve it yet."))
    except Exception as exc:
        logger.warning("domain_consistency: read failed user=%s domain=%s metric=%s",
                       uid, domain_norm, metric_norm, exc_info=True)
        _emit(uid, domain_norm, metric_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="Consistency read failed; see server logs.")

    payload = _jsonsafe(payload or {})
    ms = (time.monotonic() - t0) * 1000
    if not bool(payload.get("present")):
        _emit(uid, domain_norm, metric_norm, "empty", period=period, ms=ms)
        return _envelope(
            domain_norm, metric_norm, "empty", period=period,
            nights_with_data=payload.get("nights_with_data", 0),
            reason=(f"Not enough {metric_norm} timing recorded over '{period}' to measure "
                    f"schedule consistency (need at least two observations with times). "
                    f"This means the data isn't there — not that the schedule is perfectly "
                    f"regular."))

    _emit(uid, domain_norm, metric_norm, "ready", period=period, ms=ms)
    return _envelope(domain_norm, metric_norm, "ready",
                     **{k: v for k, v in payload.items()
                        if k not in ("domain", "metric")})
