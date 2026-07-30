# ==============================================================================
# File: apps/ai/cos_services/domain_event_frequency.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: DomainEventFrequencyService — the generic "how often does this event
#              happen over time" read surface (event counts across recurring windows +
#              the frequency trend). Answers "are my overnight lows getting more frequent".
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""
DomainEventFrequencyService (Model Interface — event-frequency branch)
======================================================================

The single, generic Model-Interface read surface for ANY event-producing metric's
FREQUENCY OVER TIME — the SERIES companion to `get_domain_readings` ("what happened in
ONE window"). It answers what neither readings, history, nor comparison can:

    get_domain_event_frequency(user, "health", "glucose",
                               event="low", window="night", period="last_month")

REUSE ONLY — delegates to `DomainTruth(user, domain).event_frequency(metric, event,
windows)`, which counts each recurring window with the reading-window stats engine and
derives the trend from the Trend primitive. This service owns NO retrieval, NO counter,
and NO trend math: it resolves the recurring windows (the ONE window authority,
`apps.core.truth.windows.daily_windows`) and the period (the ONE temporal authority,
`apps.core.truth.periods`), then hands them to the domain producer.

WINDOW AUTHORITY — the model passes a recurring KIND ("night", "day", "morning", …); WLJ
builds the concrete per-day windows against the user's local clock. The model NEVER
computes timestamps.

NO FABRICATION — unknown domain → `unsupported_domain`; unsupported metric/event →
`unsupported`; unresolvable window kind or period → `unsupported`; no windows with data
→ `empty` (NOT "no events"). Facts only; the model renders the verdict.
"""

import logging
import time

from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe
from apps.core.truth.reading_window import EVENTS
from apps.core.truth.windows import WINDOW_KINDS

logger = logging.getLogger(__name__)

DOMAIN_EVENT_FREQUENCY_SCHEMA_VERSION = "1.0"

SUPPORTED_EVENTS = tuple(EVENTS)
SUPPORTED_WINDOW_KINDS = tuple(WINDOW_KINDS.keys())


def _emit(user_id, domain, metric, event, status, *, window=None, period=None,
          windows=None, ms=None, error=None):
    try:
        logger.info(
            "DOMAIN_EVENT_FREQUENCY served user=%s domain=%s metric=%s event=%s "
            "status=%s window=%s period=%s windows=%s ms=%s error=%s",
            user_id, domain, metric, event, status, window, period, windows,
            ("%.1f" % ms) if ms is not None else "na", error,
        )
    except Exception:
        pass


def _envelope(domain, metric, event, status, **extra):
    from django.utils import timezone
    base = {
        "status": status,
        "domain": domain,
        "metric": metric,
        "event": event,
        "schema_version": DOMAIN_EVENT_FREQUENCY_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "granularity": "event_frequency",
        "scope": ("The count of a named event (a low, a high, an episode) in each "
                  "recurring window (each night / each day / …) over the period, plus "
                  "the frequency TREND (rising/falling/flat), the event rate, the "
                  "highest/lowest windows, and the hour-of-day and weekday clustering of "
                  "the events. Answers 'are my <events> getting more frequent'. Facts "
                  "only — you decide whether more/fewer is good."),
    }
    base.update(extra)
    return base


def event_frequency_capability_index():
    """{domain: (event-frequency metrics...)} for every registered domain that answers at
    least one metric as an event-frequency series. Metric NAMES only — the capability
    index the model reads to know what it can pull, never the data itself."""
    try:
        from apps.core.truth.catalog import truth_catalog
        cat = truth_catalog()
    except Exception:
        logger.warning("domain_event_frequency: catalog read failed", exc_info=True)
        return {}
    out = {}
    for domain, supports in (cat or {}).items():
        ef = tuple(supports.get("event_frequency", ())
                   if isinstance(supports, dict) else ())
        if ef:
            out[domain] = ef
    return out


def event_frequency_capable_domains():
    return sorted(event_frequency_capability_index().keys())


def _user_now(user):
    from apps.core.utils import get_user_now
    return get_user_now(user)


def _resolve_period_dates(user, period):
    """Resolve `period` to an inclusive (start_date, end_date) via the ONE shared temporal
    authority, or None if unresolvable. Accepts named periods ('this_month', 'last_month',
    'last_week'), natural phrases ('last month', 'June', 'last 30 days'), and the
    'last_N_days' shorthand. Never does calendar math beyond the shared resolver + the
    trailing-N shorthand."""
    from datetime import timedelta
    import re

    from apps.core.utils import get_user_today

    today = get_user_today(user)
    p = (period or "").strip().lower()
    if not p:
        return None

    # last_N_days / last N days shorthand — frequency questions are usually "the last
    # month" ≈ 30 days; the named periods stop at last_7_days.
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


def get_domain_event_frequency(user, domain, metric, *, event="low",
                               window="night", period="last_month"):
    """
    Return the EVENT-FREQUENCY series for `domain`.`metric`.`event` across recurring
    `window`s over `period`, as a JSON-safe envelope. Delegates to
    `DomainTruth(user, domain).event_frequency(metric, event, windows)`.

    Args:
        user: Django User instance.
        domain: WLJ domain name (case-insensitive) — must be registered.
        metric: the event-producing metric (case-insensitive) — must be in the domain's
            `event_frequency_metrics` (see `event_frequency_capability_index`).
        event: which event to count — one of SUPPORTED_EVENTS
            ('low', 'urgent_low', 'high', 'urgent_high', 'in_range').
        window: the recurring daily KIND — one of SUPPORTED_WINDOW_KINDS
            ('night', 'day', 'morning', 'afternoon', 'evening', 'full_day').
        period: the span of days to build the series over — a named period, a natural
            phrase ('last month', 'this quarter'), or 'last_N_days'. Defaults to
            'last_month'.

    Returns:
        dict envelope. `status` ∈ {"ready", "empty", "unsupported_domain",
        "unsupported", "error"}.
    """
    t0 = time.monotonic()
    uid = getattr(user, "id", "?")
    domain_norm = (domain or "").strip().lower()
    metric_norm = (metric or "").strip().lower()
    event_norm = (event or "low").strip().lower()
    window_norm = (window or "night").strip().lower()

    if event_norm not in SUPPORTED_EVENTS:
        _emit(uid, domain_norm, metric_norm, event_norm, "unsupported")
        return _envelope(domain_norm, metric_norm, event_norm, "unsupported",
                         reason=f"Unknown event '{event_norm}'.",
                         supported_events=list(SUPPORTED_EVENTS))
    if window_norm not in WINDOW_KINDS:
        _emit(uid, domain_norm, metric_norm, event_norm, "unsupported", window=window_norm)
        return _envelope(domain_norm, metric_norm, event_norm, "unsupported",
                         reason=(f"Unknown window kind '{window_norm}'. Pass a recurring "
                                 f"daily window."),
                         supported_windows=list(SUPPORTED_WINDOW_KINDS))

    try:
        from apps.core.truth.domain import get_domain_truth, registered_domains
    except Exception as exc:
        logger.warning("domain_event_frequency: truth layer unavailable", exc_info=True)
        _emit(uid, domain_norm, metric_norm, event_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, event_norm, "error",
                         reason="Truth layer unavailable; see server logs.")

    if domain_norm not in registered_domains():
        _emit(uid, domain_norm, metric_norm, event_norm, "unsupported_domain")
        return _envelope(
            domain_norm, metric_norm, event_norm, "unsupported_domain",
            reason="Unknown domain; not in the Truth Resolution Layer.",
            event_frequency_capable_domains=event_frequency_capable_domains(),
        )

    try:
        truth = get_domain_truth(user, domain_norm)
    except Exception as exc:
        logger.warning("domain_event_frequency: get_domain_truth failed user=%s domain=%s",
                       uid, domain_norm, exc_info=True)
        _emit(uid, domain_norm, metric_norm, event_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, event_norm, "error",
                         reason="Domain truth read failed; see server logs.")

    supported = tuple(getattr(truth, "event_frequency_metrics", ()) or ())
    if not supported:
        _emit(uid, domain_norm, metric_norm, event_norm, "unsupported")
        return _envelope(domain_norm, metric_norm, event_norm, "unsupported",
                         reason=f"'{domain_norm}' exposes no event-frequency metrics.",
                         supported_metrics=[])
    if metric_norm not in supported:
        _emit(uid, domain_norm, metric_norm, event_norm, "unsupported")
        return _envelope(
            domain_norm, metric_norm, event_norm, "unsupported",
            reason=(f"'{metric_norm}' has no event-frequency series for "
                    f"'{domain_norm}'."),
            supported_metrics=sorted(supported),
        )

    # --- PERIOD + WINDOW AUTHORITY: WLJ builds the recurring windows, never the model ---
    dates = _resolve_period_dates(user, period)
    if dates is None:
        _emit(uid, domain_norm, metric_norm, event_norm, "unsupported", period=period)
        return _envelope(
            domain_norm, metric_norm, event_norm, "unsupported",
            reason=(f"Unresolvable period '{period}'. Pass the natural expression the "
                    f"user said — 'last month', 'this quarter', 'last 30 days' — or a "
                    f"named period."))
    from apps.core.truth.windows import daily_windows
    now = _user_now(user)
    windows = daily_windows(window_norm, dates[0], dates[1], now)
    if not windows:
        _emit(uid, domain_norm, metric_norm, event_norm, "empty", window=window_norm,
              period=period)
        return _envelope(
            domain_norm, metric_norm, event_norm, "empty",
            window_kind=window_norm, period=period,
            reason=f"No {window_norm} windows resolved for '{period}'.")

    period_label = f"{window_norm} · {period}"
    try:
        payload = truth.event_frequency(metric_norm, event_norm, windows)
    except (KeyError, NotImplementedError) as exc:
        logger.warning("domain_event_frequency: provider declares '%s.%s' but did not "
                       "resolve it: %s", domain_norm, metric_norm, exc)
        _emit(uid, domain_norm, metric_norm, event_norm, "unsupported",
              window=window_norm, error=type(exc).__name__)
        return _envelope(
            domain_norm, metric_norm, event_norm, "unsupported",
            reason=(f"'{metric_norm}' is advertised for '{domain_norm}' but its "
                    f"event-frequency provider does not resolve it yet."))
    except Exception as exc:
        logger.warning("domain_event_frequency: read failed user=%s domain=%s metric=%s",
                       uid, domain_norm, metric_norm, exc_info=True)
        _emit(uid, domain_norm, metric_norm, event_norm, "error", window=window_norm,
              error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, event_norm, "error",
                         reason="Event-frequency read failed; see server logs.")

    payload = _jsonsafe(payload or {})
    ms = (time.monotonic() - t0) * 1000
    present = bool(payload.get("present"))

    if not present:
        _emit(uid, domain_norm, metric_norm, event_norm, "empty", window=window_norm,
              period=period, windows=len(windows), ms=ms)
        return _envelope(
            domain_norm, metric_norm, event_norm, "empty",
            window_kind=window_norm, period=period,
            reason=(f"No {metric_norm} readings in any {window_norm} window over "
                    f"'{period}'. This means nothing was recorded for those windows — "
                    f"not that there were no events."))

    _emit(uid, domain_norm, metric_norm, event_norm, "ready", window=window_norm,
          period=period, windows=payload.get("windows"), ms=ms)
    return _envelope(domain_norm, metric_norm, event_norm, "ready",
                     **{k: v for k, v in payload.items()
                        if k not in ("domain", "metric", "event")})
