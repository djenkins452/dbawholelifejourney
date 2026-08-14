# ==============================================================================
# File: apps/ai/cos_services/domain_change_point.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: DomainChangePointService — the generic "did the trend materially shift, and
#              when" read surface (segmented-regression change point over canonical
#              history). Answers "when did my weight trend change".
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""
DomainChangePointService (Model Interface — change-point branch)
================================================================

The single, generic Model-Interface read surface for the CHANGE POINT of any history
metric — the SHIFT companion to get_history (the series) and the Trend on it (the one
direction). It answers what neither can: "WHEN did my weight trend change", "when did the
recent decline begin".

    get_domain_change_point(user, "health", "weight", period="last 90 days")

REUSE ONLY — composes `get_domain_history` (which owns period resolution, the canonical
per-day series, honest statuses, and domain/metric validation) and runs the platform
`detect_change_point` (apps.core.truth.change_point) over its points. This service owns NO
retrieval and NO regression: it resolves the period to a (start, end) via the ONE shared
temporal authority, reads the history series, and hands its points to the detector.

NO FABRICATION — unknown domain/metric propagates the history status; a period with < the
detector's minimum observations, or no split that clears the residual-reduction evidence
bar, returns a NOT-supported result with a deterministic reason — never a manufactured
change date. Facts only (change date, pre/post slopes + directions, residual reduction);
the model decides whether the shift is an acceleration, an improvement, or encouraging.
"""

import logging
import time
from datetime import date

from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

DOMAIN_CHANGE_POINT_SCHEMA_VERSION = "1.0"


def _emit(user_id, domain, metric, status, *, period=None, ms=None, error=None):
    try:
        logger.info(
            "DOMAIN_CHANGE_POINT served user=%s domain=%s metric=%s status=%s "
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
        "schema_version": DOMAIN_CHANGE_POINT_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "granularity": "change_point",
        "scope": ("Whether the metric's trend materially SHIFTED within the period, and "
                  "WHEN — found by segmented linear regression: the single split date where "
                  "describing the series as two trend segments removes enough of the "
                  "one-trend error to be real. Reports the change date, the pre- and "
                  "post-change slopes and arithmetic directions, the slope delta, and the "
                  "residual_reduction (the fraction of error the split removes — the "
                  "concrete strength of the evidence, NOT a verdict). Distinct from the "
                  "Trend (one direction) and Comparison (two given periods). Answers 'when "
                  "did my trend change'. Facts only — you decide what the shift means, and "
                  "there may honestly be no supported change point."),
    }
    base.update(extra)
    return base


def change_point_capability_index():
    """{domain: (metrics...)} that can be change-point analysed — identical to the history
    capability index (any per-day series can be segmented)."""
    try:
        from apps.ai.cos_services.domain_history import history_capability_index
        return history_capability_index()
    except Exception:
        logger.warning("domain_change_point: history index unavailable", exc_info=True)
        return {}


def change_point_capable_domains():
    return sorted(change_point_capability_index().keys())


def _resolve_period_dates(user, period):
    """Resolve `period` to an inclusive (start_date, end_date) via the ONE shared temporal
    authority, or None if unresolvable. Accepts named periods, natural phrases ('last 3
    months', 'this year'), and the 'last_N_days' shorthand. Change-point questions usually
    span months, so the default is a longer window than the other analytics."""
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


def get_domain_change_point(user, domain, metric, *, period="last 90 days"):
    """
    Return the CHANGE POINT for `domain`.`metric` over `period` as a JSON-safe envelope.
    Composes `get_domain_history` and runs the platform change-point detector on its points.

    Args:
        user: Django User instance.
        domain: WLJ domain name (case-insensitive) — must be registered.
        metric: the history metric (case-insensitive) — must be in the domain's
            `history_metrics` (see `change_point_capability_index`).
        period: the span to analyse — a named period, a natural phrase ('last 6 months',
            'this year'), or 'last_N_days'. Defaults to 'last 90 days' (a change point needs
            a reasonably long series).

    Returns:
        dict envelope. `status` ∈ {"ready", "empty", "unsupported", "unsupported_domain",
        "error"}. A "ready" envelope may still report `supported: false` (no change point
        met the evidence bar) — that is a real answer, not a failure.
    """
    t0 = time.monotonic()
    uid = getattr(user, "id", "?")
    domain_norm = (domain or "").strip().lower()
    metric_norm = (metric or "").strip().lower()

    dates = _resolve_period_dates(user, period)
    if dates is None:
        _emit(uid, domain_norm, metric_norm, "unsupported", period=period)
        return _envelope(
            domain_norm, metric_norm, "unsupported",
            reason=(f"Unresolvable period '{period}'. Pass the natural expression the user "
                    f"said — 'last 6 months', 'this year', 'last 90 days' — or a named "
                    f"period."))

    try:
        from apps.ai.cos_services.domain_history import get_domain_history
    except Exception as exc:
        _emit(uid, domain_norm, metric_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="History layer unavailable; see server logs.")

    env = get_domain_history(user, domain_norm, metric_norm,
                             start=dates[0].isoformat(), end=dates[1].isoformat())
    st = env.get("status")
    if st in ("unsupported", "unsupported_domain", "error"):
        _emit(uid, domain_norm, metric_norm, st, period=period)
        # Propagate the history layer's honest reason (+ capable-domain/metric hints).
        passthrough = {k: env[k] for k in ("reason", "supported_metrics",
                                           "history_capable_domains") if k in env}
        passthrough.setdefault("reason",
                               f"{metric_norm} has no history series for {domain_norm}.")
        return _envelope(domain_norm, metric_norm, st, **passthrough)

    points = [(date.fromisoformat(p["date"]), p["value"])
              for p in (env.get("points") or []) if p.get("value") is not None]

    from apps.core.truth.change_point import detect_change_point
    result = detect_change_point(points, domain=domain_norm, metric=metric_norm,
                                 period_label=env.get("period") or period)
    result = _jsonsafe(result)
    ms = (time.monotonic() - t0) * 1000

    if not result.get("present"):
        _emit(uid, domain_norm, metric_norm, "empty", period=period, ms=ms)
        return _envelope(
            domain_norm, metric_norm, "empty", period=period,
            observations=result.get("observations", 0),
            reason=(f"No {metric_norm} history in '{period}' to analyse for a trend "
                    f"change."))

    _emit(uid, domain_norm, metric_norm, "ready", period=period, ms=ms)
    return _envelope(domain_norm, metric_norm, "ready", unit=env.get("unit"),
                     **{k: v for k, v in result.items()
                        if k not in ("domain", "metric")})
