# ==============================================================================
# File: apps/ai/cos_services/domain_adherence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: DomainAdherenceService — the ONE reusable "actual vs target" capability
#              for ANY metric with a declared target (nutrition macros, steps, …).
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""
DomainAdherenceService (Model Interface — adherence branch)
===========================================================

The single, generic Model-Interface surface for "am I in line with my target?" —
the half the CoS could not answer for "do I need more carbs or are they in line?":

    get_domain_adherence(user, domain, metric, period="last_7_days")

REUSE ONLY — composes the actual (a trend-aware `get_domain_history` per-day series)
against the user's canonical target (apps.core.truth.targets registry). It owns no
retrieval and no per-domain logic; every metric with a registered target is answerable
automatically. There is NO nutrition-adherence / steps-adherence — there is ONE.

FACTS, NOT A VERDICT: WLJ returns the target, the average daily actual, the signed
variance, percent of target, and per-day met/over/under counts — plus whether the target
is a `target` (reach) or a `limit` (stay under). The model decides "in line" / "need
more"; WLJ never renders that verdict.
"""
import logging
import time

logger = logging.getLogger(__name__)

DOMAIN_ADHERENCE_SCHEMA_VERSION = "1.0"


def _emit(user_id, domain, metric, status, *, period=None, ms=None, error=None):
    try:
        logger.info(
            "DOMAIN_ADHERENCE served user=%s domain=%s metric=%s status=%s "
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
        "schema_version": DOMAIN_ADHERENCE_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "granularity": "adherence",
        "scope": ("Average daily actual vs the user's stored target/limit over the "
                  "period, with signed variance, percent of target, and per-day "
                  "met/over/under counts. 'kind' says whether the number is a target to "
                  "reach or a limit to stay under. WLJ supplies the facts; interpret "
                  "'in line' yourself."),
    }
    base.update(extra)
    return base


def adherence_capability_index():
    """{domain: (metrics with a registered target...)} — the capability index the model
    reads to know which metrics support adherence."""
    try:
        from apps.core.truth.targets import target_capability_index
        return target_capability_index()
    except Exception:
        logger.warning("domain_adherence: target index unavailable", exc_info=True)
        return {}


def adherence_capable_domains():
    return sorted(adherence_capability_index().keys())


def get_domain_adherence(user, domain, metric, *, period="last_7_days"):
    """
    Return actual-vs-target adherence for `domain`.`metric` over `period` as a JSON-safe
    envelope. `status` ∈ {"ready", "empty", "no_target", "unsupported", "error"}.
      * no_target — the metric has no registered target, or the user has none set
        (honest: adherence is undefined without a target).
      * empty — a target exists but there is no actual data in the period.
    """
    t0 = time.monotonic()
    uid = getattr(user, "id", "?")
    domain_norm = (domain or "").strip().lower()
    metric_norm = (metric or "").strip().lower()
    period_norm = (period or "last_7_days").strip()

    # -- target (the user's canonical stored aim) --
    try:
        from apps.core.truth.targets import resolve_target, target_capability_index
    except Exception as exc:
        _emit(uid, domain_norm, metric_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="Target layer unavailable; see server logs.")

    target = resolve_target(user, domain_norm, metric_norm)
    if target is None:
        idx = target_capability_index()
        has_provider = metric_norm in idx.get(domain_norm, ())
        _emit(uid, domain_norm, metric_norm, "no_target", period=period_norm)
        return _envelope(
            domain_norm, metric_norm, "no_target",
            reason=(f"No target is set for {domain_norm}.{metric_norm}."
                    if has_provider else
                    f"{domain_norm}.{metric_norm} has no target to measure adherence "
                    f"against."),
            adherence_capable={d: list(m) for d, m in idx.items()},
        )

    # -- actual (reuse the trend-aware history series) --
    try:
        from apps.ai.cos_services.domain_history import get_domain_history
    except Exception as exc:
        _emit(uid, domain_norm, metric_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="History layer unavailable; see server logs.")

    hist = get_domain_history(user, domain_norm, metric_norm, period=period_norm)
    st = hist.get("status")
    if st in ("unsupported", "unsupported_domain", "error"):
        _emit(uid, domain_norm, metric_norm, st, period=period_norm)
        return _envelope(domain_norm, metric_norm, "unsupported",
                         reason=hist.get("reason")
                         or f"No actual {metric_norm} series to compare to target.")

    points = hist.get("points") or []
    ms = (time.monotonic() - t0) * 1000
    if not hist.get("present") or not points:
        _emit(uid, domain_norm, metric_norm, "empty", period=period_norm, ms=ms)
        return _envelope(domain_norm, metric_norm, "empty",
                         target=target.to_dict(), period=hist.get("period"),
                         reason=f"No {metric_norm} logged in {hist.get('period')} to "
                                f"measure against the target.")

    tgt = float(target.value)
    day_values = [float(p["value"]) for p in points if p.get("value") is not None]
    days = len(day_values)
    avg_daily = round(sum(day_values) / days, 1) if days else None
    variance = round(avg_daily - tgt, 1) if avg_daily is not None else None
    pct = round((avg_daily / tgt) * 100, 1) if (avg_daily is not None and tgt) else None

    # Per-day met/over/under (met = within 5% of target either way).
    band = 0.05 * tgt
    days_over = sum(1 for v in day_values if v > tgt + band)
    days_under = sum(1 for v in day_values if v < tgt - band)
    days_met = days - days_over - days_under

    _emit(uid, domain_norm, metric_norm, "ready", period=period_norm, ms=ms)
    return _envelope(
        domain_norm, metric_norm, "ready",
        unit=target.unit or hist.get("unit"),
        period=hist.get("period"),
        target=target.to_dict(),
        actual={"avg_daily": avg_daily, "days": days,
                "total": round(sum(day_values), 1)},
        variance={"avg_daily_delta": variance, "pct_of_target": pct},
        days_at_or_near_target=days_met,
        days_over_target=days_over,
        days_under_target=days_under,
        # The full trend-aware series is included so the model can reason over the shape
        # (the same one get_history would return) without a second call.
        change=hist.get("change"),
    )
