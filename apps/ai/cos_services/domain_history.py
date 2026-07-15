# ==============================================================================
# File: apps/ai/cos_services/domain_history.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: DomainHistoryService — the generic HISTORICAL truth read surface
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-15
# ==============================================================================
"""
DomainHistoryService (Model Interface — Pillar 1, history branch)
=================================================================

The single, generic Model-Interface read surface for ANY WLJ domain's HISTORICAL
truth — the "back then" companion to `DomainStateService` (state, "now-composed")
and `get_foundational_health_facts` (current scalars):

    get_domain_history(user, domain, metric, period=..., start=..., end=...)

Design rules honored (Architecture Laws + Amendment A + Model Interface design):
* REUSE ONLY — delegates to the canonical Truth Resolution Layer
  `DomainTruth(user, domain).history(metric, period)` over the existing
  `truth_catalog()`. There is NO new retrieval logic and NO parallel history
  store: the Answer Precondition Pipeline (period resolution, one grouped query,
  deterministic aggregates, coverage-confidence) already lives INSIDE the domain
  History providers (Amendment A — Laws re-hosted inside truth tools).
* CATALOG-DRIVEN — every domain that registers `history_metrics` participates
  automatically; no per-domain plumbing here.
* NO RAW ROWS — returns a composed `HistorySeries` (points + total/average/
  count/confidence + provenance), never database rows.
* NO FABRICATION — an unknown domain returns `unsupported_domain`; an
  unsupported metric returns `unsupported`; a period with no data returns
  `empty`; a bad period returns `unsupported`. Honest states, never a guess.
* JSON-safe + observable; wrappable by the Model Interface truth envelope with
  no logic change (`_wrap_truth` maps our `status` → the canonical envelope).
"""

import logging
import time
from datetime import date, datetime

from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

DOMAIN_HISTORY_SCHEMA_VERSION = "1.0"


def _emit(user_id, domain, metric, status, *, period=None, points=None, ms=None,
          error=None):
    """Observable, structured telemetry. No silent failures."""
    try:
        logger.info(
            "DOMAIN_HISTORY served user=%s domain=%s metric=%s status=%s "
            "period=%s points=%s ms=%s error=%s",
            user_id, domain, metric, status, period, points,
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
        "schema_version": DOMAIN_HISTORY_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        # Truthful granularity: this surface is aggregate/time-series ONLY. It never
        # carries the contents of an individual record — so a detail question ("which
        # exercises?") is out of scope here and belongs to get_entity.
        "granularity": "aggregate",
        "scope": ("Aggregate values over the period (counts, totals, averages, trends) — "
                  "not the contents of any individual record. For a record's detailed "
                  "contents, use get_entity."),
    }
    base.update(extra)
    return base


def _parse_date(value):
    """Parse an ISO 'YYYY-MM-DD' (or datetime) into a date; None on empty/bad input."""
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def history_capability_index():
    """{domain: (history metrics...)} for every registered domain that answers at
    least one metric as history. Small (metric NAMES only) — this is the capability
    index the model reads to know what it can pull, never the data itself."""
    try:
        from apps.core.truth.catalog import truth_catalog
        cat = truth_catalog()
    except Exception:
        logger.warning("domain_history: catalog read failed", exc_info=True)
        return {}
    out = {}
    for domain, supports in (cat or {}).items():
        hist = tuple(supports.get("history", ()) if isinstance(supports, dict) else ())
        if hist:
            out[domain] = hist
    return out


def history_capable_domains():
    return sorted(history_capability_index().keys())


def get_domain_history(user, domain, metric, *, period="last_7_days",
                       start=None, end=None):
    """
    Return the canonical HISTORY series for `domain`.`metric` over a period as a
    JSON-safe envelope. Delegates to `DomainTruth(user, domain).history(...)`.

    Args:
        user: Django User instance.
        domain: WLJ domain name (case-insensitive) — must be registered.
        metric: the history metric (case-insensitive) — must be in the domain's
            `history_metrics` (see `history_capability_index`).
        period: a named period ("today", "yesterday", "last_7_days", "this_week",
            "last_week", "this_month", "last_month", "this_quarter", "last_quarter",
            "this_year", "last_year") or "custom". A specific date ("what did I
            weigh on July 4th") is expressed as start=end=that date.
        start, end: ISO 'YYYY-MM-DD' dates. When either is present the range is
            treated as custom; a single date may be passed as `start` alone.

    Returns:
        dict envelope. `status` is one of:
            "ready"              — series present, returned (may be empty of points)
            "empty"              — no data points in the resolved period
            "unsupported_domain" — unknown domain (lists history-capable domains)
            "unsupported"        — metric not answerable as history, or bad period
            "error"              — read failed (logged with exc_info)
    """
    t0 = time.monotonic()
    uid = getattr(user, "id", "?")
    domain_norm = (domain or "").strip().lower()
    metric_norm = (metric or "").strip().lower()
    period_norm = (period or "last_7_days").strip().lower()

    # --- Truth Resolution Layer ---
    try:
        from apps.core.truth.domain import get_domain_truth, registered_domains
    except Exception as exc:
        logger.warning("domain_history: truth layer unavailable", exc_info=True)
        _emit(uid, domain_norm, metric_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="Truth layer unavailable; see server logs.")

    # --- unknown domain ---
    if domain_norm not in registered_domains():
        _emit(uid, domain_norm, metric_norm, "unsupported_domain")
        return _envelope(
            domain_norm, metric_norm, "unsupported_domain",
            reason="Unknown domain; not in the Truth Resolution Layer.",
            history_capable_domains=history_capable_domains(),
        )

    try:
        truth = get_domain_truth(user, domain_norm)
    except Exception as exc:
        logger.warning("domain_history: get_domain_truth failed user=%s domain=%s",
                       uid, domain_norm, exc_info=True)
        _emit(uid, domain_norm, metric_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="Domain truth read failed; see server logs.")

    supported = tuple(getattr(truth, "history_metrics", ()) or ())

    # --- domain answers nothing as history ---
    if not supported:
        _emit(uid, domain_norm, metric_norm, "unsupported")
        return _envelope(
            domain_norm, metric_norm, "unsupported",
            reason=f"'{domain_norm}' exposes no history metrics.",
            supported_metrics=[],
        )

    # --- metric not answerable as history ---
    if metric_norm not in supported:
        _emit(uid, domain_norm, metric_norm, "unsupported")
        return _envelope(
            domain_norm, metric_norm, "unsupported",
            reason=(f"'{metric_norm}' is not answerable as history for "
                    f"'{domain_norm}'."),
            supported_metrics=sorted(supported),
        )

    # --- period: a specific date / custom range vs a named window ---
    sd, ed = _parse_date(start), _parse_date(end)
    if sd or ed or period_norm == "custom":
        if sd and not ed:
            ed = sd
        if ed and not sd:
            sd = ed
        if not (sd and ed):
            _emit(uid, domain_norm, metric_norm, "unsupported", period=period_norm)
            return _envelope(
                domain_norm, metric_norm, "unsupported",
                reason="A custom/specific-date period requires start (and end).",
            )
        if ed < sd:
            sd, ed = ed, sd
        period_norm = "custom"

    # --- resolve deterministically inside the domain History provider ---
    try:
        series = truth.history(metric_norm, period_norm, start=sd, end=ed)
    except ValueError as exc:
        # e.g. unknown period name — honest "unsupported", list valid windows.
        from apps.core.truth.periods import NAMED_PERIODS
        _emit(uid, domain_norm, metric_norm, "unsupported", period=period_norm,
              error=str(exc)[:80])
        return _envelope(
            domain_norm, metric_norm, "unsupported",
            reason=f"Unresolvable period '{period_norm}'.",
            valid_periods=list(NAMED_PERIODS) + ["custom"],
        )
    except (KeyError, NotImplementedError) as exc:
        # The domain advertised the metric in `history_metrics` but its History
        # provider does not resolve it (a provider-contract gap, not a runtime
        # error). Report honestly as unsupported — never a generic failure.
        logger.warning("domain_history: provider declares '%s.%s' as history but "
                       "did not resolve it: %s", domain_norm, metric_norm, exc)
        _emit(uid, domain_norm, metric_norm, "unsupported", period=period_norm,
              error=type(exc).__name__)
        return _envelope(
            domain_norm, metric_norm, "unsupported",
            reason=(f"'{metric_norm}' is advertised for '{domain_norm}' but its "
                    f"history provider does not resolve it yet."),
        )
    except Exception as exc:
        logger.warning("domain_history: history read failed user=%s domain=%s "
                       "metric=%s", uid, domain_norm, metric_norm, exc_info=True)
        _emit(uid, domain_norm, metric_norm, "error", period=period_norm,
              error=type(exc).__name__)
        return _envelope(domain_norm, metric_norm, "error",
                         reason="History read failed; see server logs.")

    if series is None:
        _emit(uid, domain_norm, metric_norm, "empty", period=period_norm)
        return _envelope(domain_norm, metric_norm, "empty",
                         reason="No history series for that request.")

    payload = _jsonsafe(series.to_dict())
    present = bool(payload.get("present"))
    ms = (time.monotonic() - t0) * 1000

    # No data points in the window is an HONEST empty, not an error — the model
    # must say "no reading for that period", never fabricate.
    if not present:
        _emit(uid, domain_norm, metric_norm, "empty", period=period_norm,
              points=0, ms=ms)
        return _envelope(
            domain_norm, metric_norm, "empty",
            period=payload.get("period"),
            start=payload.get("start"), end=payload.get("end"),
            unit=payload.get("unit"),
            reason=f"No {metric_norm} data in {payload.get('period')}.",
        )

    _emit(uid, domain_norm, metric_norm, "ready", period=period_norm,
          points=payload.get("count"), ms=ms)
    return _envelope(domain_norm, metric_norm, "ready",
                     **{k: v for k, v in payload.items()
                        if k not in ("domain", "metric")})
