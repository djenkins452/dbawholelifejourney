# ==============================================================================
# File: apps/ai/cos_services/domain_readings.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: DomainReadingsService — the generic INTRA-DAY reading-window read
#              surface (individual samples + window stats for high-frequency metrics).
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""
DomainReadingsService (Model Interface — intra-day / high-frequency branch)
===========================================================================

The single, generic Model-Interface read surface for ANY WLJ domain's INTRA-DAY
truth — the "moments" companion to `get_domain_history` ("per-day trend over a
Period"). It answers questions history structurally cannot:

    get_domain_readings(user, domain, metric, window="overnight")
    get_domain_readings(user, domain, metric, window="past 12 hours")
    get_domain_readings(user, domain, metric, start="2026-07-29T00:00", end="...T06:00")

Design rules honored (Architecture Laws + Amendment A + Model Interface design):
* REUSE ONLY — delegates to `DomainTruth(user, domain).readings(metric, window)` over
  the existing catalog. No new retrieval logic; the domain owns its query, the
  platform owns window resolution (`apps.core.truth.windows`) and the ReadingSeries
  statistics (`apps.core.truth.reading_window`).
* CATALOG-DRIVEN — every domain that declares `reading_metrics` participates
  automatically; no per-domain plumbing here.
* WINDOW AUTHORITY — WLJ resolves the natural window expression the USER said
  ("overnight", "past 12 hours", "since midnight"); the model NEVER computes
  timestamps. Explicit ISO start/end is accepted for "between two timestamps".
* NO FABRICATION — unknown domain → `unsupported_domain`; unsupported metric →
  `unsupported`; unparseable window → `unsupported` (honest, lists examples); no data
  in window → `empty`. Honest states, never a guess.
"""

import logging
import time
from datetime import datetime, timedelta

from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

DOMAIN_READINGS_SCHEMA_VERSION = "1.0"


def _emit(user_id, domain, metric, status, *, window=None, count=None, ms=None,
          error=None):
    try:
        logger.info(
            "DOMAIN_READINGS served user=%s domain=%s metric=%s status=%s "
            "window=%s count=%s ms=%s error=%s",
            user_id, domain, metric, status, window, count,
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
        "schema_version": DOMAIN_READINGS_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        # Truthful granularity: this surface carries INDIVIDUAL timestamped samples over
        # a datetime window PLUS deterministic window statistics — not a per-day trend.
        "granularity": "reading_window",
        "scope": ("Individual timestamped readings inside a time window, with window "
                  "statistics (min/max/average, in-range, below/above counts) and the "
                  "individual low/high excursions. For a per-DAY trend over weeks/months "
                  "use get_history."),
    }
    base.update(extra)
    return base


def _user_now(user):
    """The user's LOCAL timezone-aware now — every window is measured against this."""
    from apps.core.utils import get_user_now
    return get_user_now(user)


def _parse_iso_dt(value, now):
    """Parse a model-supplied start/end into an aware datetime in the user's tz. Accepts
    'YYYY-MM-DDTHH:MM[:SS]' or a bare 'YYYY-MM-DD' (→ local midnight). None on bad input."""
    if value is None or value == "":
        return None
    from django.utils import timezone as _tz
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip().replace("Z", "+00:00")
        dt = None
        try:                       # handles offset + microseconds ('...T06:00:00+00:00')
            dt = datetime.fromisoformat(s)
        except ValueError:
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    continue
        if dt is None:
            return None
    if _tz.is_naive(dt):
        dt = dt.replace(tzinfo=now.tzinfo)
    return dt


def _resolve_window(user, window_phrase, start, end):
    """Resolve the request into a `Window`, or (None, reason). Precedence:
    explicit start/end timestamps → natural intra-day phrase → a day phrase widened to
    a window. Never invents a window it cannot justify."""
    from apps.core.truth.windows import (
        MAX_WINDOW_HOURS, Window, resolve_window, window_from_period,
    )

    now = _user_now(user)

    # 1) Explicit range — "between two timestamps".
    sdt, edt = _parse_iso_dt(start, now), _parse_iso_dt(end, now)
    if sdt or edt:
        if sdt and not edt:
            edt = now
        if edt and not sdt:
            return None, "A start timestamp is required with an end."
        if edt < sdt:
            sdt, edt = edt, sdt
        span_h = (edt - sdt).total_seconds() / 3600.0
        clamped = span_h > MAX_WINDOW_HOURS
        if clamped:
            sdt = edt - timedelta(hours=MAX_WINDOW_HOURS)
        label = f"{sdt.isoformat()} – {edt.isoformat()}"
        return Window("custom", sdt, edt, label, clamped=clamped), None

    # 2) Natural intra-day phrase — "overnight", "past 12 hours", "since midnight".
    phrase = (window_phrase or "").strip()
    if not phrase:
        return None, "No window given."
    win = resolve_window(phrase, now)
    if win is not None:
        return win, None

    # 3) Fall back to a whole-day phrase ("yesterday", "last Tuesday", "July 4"),
    #    widened to a datetime window via the shared temporal authority.
    try:
        from apps.core.truth.periods import resolve_date_expression
        p = resolve_date_expression(phrase, now.date())
    except Exception:
        p = None
    if p is not None:
        return window_from_period(p, now), None

    return None, (f"Unresolvable window '{phrase}'. Pass the natural expression the "
                  f"user said — 'overnight', 'past 12 hours', 'since midnight', "
                  f"'this morning', 'yesterday' — or explicit start/end timestamps.")


def readings_capability_index():
    """{domain: (reading metrics...)} for every registered domain answering at least
    one metric as an intra-day reading window. Metric NAMES only — the capability index
    the model reads to know what it can pull, never the data itself."""
    try:
        from apps.core.truth.catalog import truth_catalog
        cat = truth_catalog()
    except Exception:
        logger.warning("domain_readings: catalog read failed", exc_info=True)
        return {}
    out = {}
    for domain, supports in (cat or {}).items():
        rd = tuple(supports.get("readings", ()) if isinstance(supports, dict) else ())
        if rd:
            out[domain] = rd
    return out


def readings_capable_domains():
    return sorted(readings_capability_index().keys())


def get_domain_readings(user, domain, metric, *, window="", start=None, end=None):
    """
    Return the intra-day READING WINDOW for `domain`.`metric` as a JSON-safe envelope.
    Delegates to `DomainTruth(user, domain).readings(metric, window)`.

    Args:
        user: Django User instance.
        domain: WLJ domain name (case-insensitive) — must be registered.
        metric: the reading metric (case-insensitive) — must be in the domain's
            `reading_metrics` (see `readings_capability_index`).
        window: the NATURAL window expression the user said ("overnight",
            "past 12 hours", "since midnight", "this morning", "yesterday"). WLJ
            resolves it against the user's local now. Do NOT compute timestamps.
        start, end: OPTIONAL explicit ISO datetimes for "between two timestamps"
            (take precedence over `window`).

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
        logger.warning("domain_readings: truth layer unavailable", exc_info=True)
        _emit(uid, domain_norm, metric_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="Truth layer unavailable; see server logs.")

    if domain_norm not in registered_domains():
        _emit(uid, domain_norm, metric_norm, "unsupported_domain")
        return _envelope(
            domain_norm, metric_norm, "unsupported_domain",
            reason="Unknown domain; not in the Truth Resolution Layer.",
            readings_capable_domains=readings_capable_domains(),
        )

    try:
        truth = get_domain_truth(user, domain_norm)
    except Exception as exc:
        logger.warning("domain_readings: get_domain_truth failed user=%s domain=%s",
                       uid, domain_norm, exc_info=True)
        _emit(uid, domain_norm, metric_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="Domain truth read failed; see server logs.")

    supported = tuple(getattr(truth, "reading_metrics", ()) or ())
    if not supported:
        _emit(uid, domain_norm, metric_norm, "unsupported")
        return _envelope(
            domain_norm, metric_norm, "unsupported",
            reason=f"'{domain_norm}' exposes no intra-day reading metrics.",
            supported_metrics=[],
        )
    if metric_norm not in supported:
        _emit(uid, domain_norm, metric_norm, "unsupported")
        return _envelope(
            domain_norm, metric_norm, "unsupported",
            reason=(f"'{metric_norm}' is not answerable as an intra-day reading window "
                    f"for '{domain_norm}'."),
            supported_metrics=sorted(supported),
        )

    # --- WINDOW AUTHORITY: WLJ resolves the window, never the model ---
    win, reason = _resolve_window(user, window, start, end)
    if win is None:
        _emit(uid, domain_norm, metric_norm, "unsupported", window=window)
        return _envelope(domain_norm, metric_norm, "unsupported", reason=reason)

    try:
        payload = truth.readings(metric_norm, win)
    except (KeyError, NotImplementedError) as exc:
        logger.warning("domain_readings: provider declares '%s.%s' but did not "
                       "resolve it: %s", domain_norm, metric_norm, exc)
        _emit(uid, domain_norm, metric_norm, "unsupported",
              window=win.name, error=type(exc).__name__)
        return _envelope(
            domain_norm, metric_norm, "unsupported",
            reason=(f"'{metric_norm}' is advertised for '{domain_norm}' but its "
                    f"reading provider does not resolve it yet."))
    except Exception as exc:
        logger.warning("domain_readings: read failed user=%s domain=%s metric=%s",
                       uid, domain_norm, metric_norm, exc_info=True)
        _emit(uid, domain_norm, metric_norm, "error", window=win.name,
              error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="Reading read failed; see server logs.")

    payload = _jsonsafe(payload or {})
    ms = (time.monotonic() - t0) * 1000
    present = bool(payload.get("present"))

    if not present:
        _emit(uid, domain_norm, metric_norm, "empty", window=win.name, count=0, ms=ms)
        return _envelope(
            domain_norm, metric_norm, "empty",
            window=payload.get("window"),
            unit=payload.get("unit"),
            reason=(f"No {metric_norm} readings in {win.label}. This means none are "
                    f"recorded for that window — not that the metric is unavailable."),
        )

    _emit(uid, domain_norm, metric_norm, "ready", window=win.name,
          count=payload.get("count"), ms=ms)
    return _envelope(domain_norm, metric_norm, "ready",
                     **{k: v for k, v in payload.items()
                        if k not in ("domain", "metric")})
