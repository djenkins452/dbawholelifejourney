# ==============================================================================
# File: apps/ai/cos_services/domain_comparison.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: DomainComparisonService — the ONE reusable "period A vs period B"
#              capability for ANY domain metric (weight, steps, glucose, carbs, …).
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""
DomainComparisonService (Model Interface — comparison branch)
=============================================================

The single, generic Model-Interface surface for "how does <metric> in period A compare
to period B" — yesterday vs today, this week vs last week, this month vs last month:

    get_domain_comparison(user, domain, metric, period_a="last_week", period_b="this_week")

REUSE ONLY — composes TWO `get_domain_history` calls (which already resolve natural
date phrases against the user's today and return the trend-aware series). This service
adds ONLY the deterministic cross-period delta; it owns no retrieval, no date math, and
no per-domain logic. Every history-capable (domain, metric) is comparable automatically
— there is NO nutrition-comparison, weight-comparison, glucose-comparison; there is ONE
comparison.

CONVENTION: `period_a` is the BASELINE/earlier; `period_b` is the FOCUS/recent. `change`
is period_b relative to period_a. Direction is arithmetic (rising/falling/flat), never a
"better/worse" verdict — desirability is metric-specific and the model's to interpret.
"""
import logging
import time

logger = logging.getLogger(__name__)

DOMAIN_COMPARISON_SCHEMA_VERSION = "1.0"

_FLAT_REL_BAND = 0.005          # |Δ| within 0.5% of magnitude reads as flat


def _emit(user_id, domain, metric, status, *, pa=None, pb=None, ms=None, error=None):
    try:
        logger.info(
            "DOMAIN_COMPARISON served user=%s domain=%s metric=%s status=%s "
            "period_a=%s period_b=%s ms=%s error=%s",
            user_id, domain, metric, status, pa, pb,
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
        "schema_version": DOMAIN_COMPARISON_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "granularity": "comparison",
        "scope": ("Two periods of the same metric with the deterministic change between "
                  "them (delta, percent, direction). Baseline = period_a; focus = "
                  "period_b; change is period_b relative to period_a."),
    }
    base.update(extra)
    return base


def comparison_capability_index():
    """{domain: (metrics...)} comparable as period-vs-period — identical to the history
    capability index (anything with a per-day series can be compared)."""
    try:
        from apps.ai.cos_services.domain_history import history_capability_index
        return history_capability_index()
    except Exception:
        logger.warning("domain_comparison: history index unavailable", exc_info=True)
        return {}


def comparison_capable_domains():
    return sorted(comparison_capability_index().keys())


def _side(env):
    """Extract the comparable aggregates from a get_domain_history envelope."""
    return {
        "period": env.get("period"),
        "start": env.get("start"), "end": env.get("end"),
        "present": bool(env.get("present")),
        "count": env.get("count"),
        "average": env.get("average"),
        "total": env.get("total"),
        "unit": env.get("unit"),
    }


def _delta(b, a):
    """Deterministic change of b relative to a for one aggregate. None-safe."""
    if a is None or b is None:
        return None
    a, b = float(a), float(b)
    delta = round(b - a, 4)
    mag = max(abs(a), abs(b)) or 1.0
    pct = round((delta / abs(a)) * 100, 1) if a not in (0, 0.0) else None
    if abs(delta) < _FLAT_REL_BAND * mag:
        direction = "flat"
    else:
        direction = "rising" if delta > 0 else "falling"
    return {"delta": delta, "pct_change": pct, "direction": direction}


def get_domain_comparison(user, domain, metric, *, period_a, period_b):
    """
    Compare `domain`.`metric` between two periods as a JSON-safe envelope. Composes two
    `get_domain_history` reads (each resolves its own natural date phrase). Baseline =
    period_a; focus = period_b.

    `status` ∈ {"ready", "empty", "unsupported", "unsupported_domain", "error"}.
    `empty` when NEITHER period has data (an honest "no data in either window").
    """
    t0 = time.monotonic()
    uid = getattr(user, "id", "?")
    domain_norm = (domain or "").strip().lower()
    metric_norm = (metric or "").strip().lower()
    pa = (period_a or "").strip()
    pb = (period_b or "").strip()

    if not pa or not pb:
        _emit(uid, domain_norm, metric_norm, "unsupported", pa=pa, pb=pb)
        return _envelope(domain_norm, metric_norm, "unsupported",
                         reason="Two periods are required (period_a and period_b).")

    try:
        from apps.ai.cos_services.domain_history import get_domain_history
    except Exception as exc:
        _emit(uid, domain_norm, metric_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="History layer unavailable; see server logs.")

    env_a = get_domain_history(user, domain_norm, metric_norm, period=pa)
    env_b = get_domain_history(user, domain_norm, metric_norm, period=pb)

    # Honest error propagation — if the metric/domain is unsupported, say so once.
    for env in (env_a, env_b):
        st = env.get("status")
        if st in ("unsupported", "unsupported_domain", "error"):
            _emit(uid, domain_norm, metric_norm, st, pa=pa, pb=pb)
            return _envelope(domain_norm, metric_norm, st,
                             reason=env.get("reason")
                             or f"{metric_norm} is not comparable for {domain_norm}.",
                             **({"supported_metrics": env["supported_metrics"]}
                                if env.get("supported_metrics") else {}))

    a, b = _side(env_a), _side(env_b)
    ms = (time.monotonic() - t0) * 1000

    if not (a["present"] or b["present"]):
        _emit(uid, domain_norm, metric_norm, "empty", pa=pa, pb=pb, ms=ms)
        return _envelope(domain_norm, metric_norm, "empty",
                         period_a=a, period_b=b,
                         reason=(f"No {metric_norm} data in either period. This means "
                                 f"nothing is recorded for those windows — not that the "
                                 f"metric is unavailable."))

    change = {
        "average": _delta(b["average"], a["average"]),
        "total": _delta(b["total"], a["total"]),
    }
    _emit(uid, domain_norm, metric_norm, "ready", pa=pa, pb=pb, ms=ms)
    return _envelope(domain_norm, metric_norm, "ready",
                     unit=a["unit"] or b["unit"],
                     period_a=a, period_b=b, change=change)
