"""
CurrentHealth — Health's authoritative Current Truth provider (Layer 1).

THE single deterministic source for "what is the user's current health X". Composes
the lower platform capabilities — Per-Day Truth (`DailyHealthQueries`) + Freshness
(`apps.core.truth.freshness`) — into `CurrentTruth` objects (apps.core.truth.current).
Beth and engines read these objects; nobody re-derives the value or the freshness.

History (a value on a past date) stays in DailyHealthQueries.* / trend analyzers —
Current Truth answers "now / last night / today", not "on March 15".
"""
import logging

from apps.core.truth.current import CurrentTruth
from apps.core.truth.freshness import classify_period_freshness

logger = logging.getLogger(__name__)


class CurrentHealth:
    # metric key -> (DailyHealthQueries method name, requested-period, cumulative?)
    _ROUTES = {
        "steps_today": ("steps_on", "today", True),
        "steps_yesterday": ("steps_on", "yesterday", False),
        "sleep_last_night": ("latest_sleep", "yesterday", False),
        "calories_yesterday": ("calories_on", "yesterday", False),
        "weight_yesterday": ("weight_on", "yesterday", False),
        "glucose_yesterday": ("glucose_on", "yesterday", False),
    }
    SUPPORTED = frozenset(_ROUTES)

    @classmethod
    def get(cls, user, metric):
        """Return a CurrentTruth for a current-state health metric."""
        from apps.health.services.daily_health_queries import DailyHealthQueries as Q
        route = cls._ROUTES.get(metric)
        if route is None:
            return CurrentTruth.absent("health", metric, reason="unsupported metric")

        method, period, cumulative = route
        today, yest = Q.today(user), Q.yesterday(user)
        requested = today if period == "today" else yest
        try:
            res = (Q.latest_sleep(user) if method == "latest_sleep"
                   else getattr(Q, method)(user, requested))
        except Exception:
            logger.warning("CurrentHealth: %s failed user=%s", metric,
                           getattr(user, "id", None), exc_info=True)
            return CurrentTruth.absent("health", metric, reason="retrieval failed")

        if res.get("status") != "ok":
            fresh = classify_period_freshness(
                has_data=False, requested_date=requested, data_date=None, today=today)
            return CurrentTruth.absent("health", metric, freshness=fresh,
                                       source="DailyHealthQueries",
                                       reason=f"no {res.get('metric', metric)} for the day")

        data_date = cls._parse_date(res.get("as_of") or res.get("for_date"))
        fresh = classify_period_freshness(
            has_data=True, requested_date=requested, data_date=data_date,
            today=today, is_cumulative=cumulative)
        detail = {k: res[k] for k in ("for_date", "recorded_at", "as_of", "exact",
                                      "count") if k in res}
        return CurrentTruth.found("health", metric, res["value"], fresh,
                                  unit=res.get("unit"), as_of=res.get("for_date"),
                                  source="DailyHealthQueries", detail=detail)

    @staticmethod
    def _parse_date(raw):
        from datetime import date as _date
        try:
            return _date.fromisoformat(raw) if raw else None
        except (TypeError, ValueError):
            return None
