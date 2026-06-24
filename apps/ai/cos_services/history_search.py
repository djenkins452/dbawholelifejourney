# ==============================================================================
# File: apps/ai/cos_services/history_search.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: HistorySearchService (Phase 5) — ChatGPT CoS historical retrieval
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
HistorySearchService (ChatGPT CoS — Phase 5)
============================================

The canonical historical-retrieval surface for the ChatGPT reasoning layer:

    search_history(user, query, *, domain=None, timeframe=None)

REUSE ONLY (per the Readiness Audit, these search engines already exist and were
unused — Phase 5 EXPOSES them, it does not rebuild them):
* `apps.ai.search_service.SearchService` — keyword search across journal, health,
  goals, faith, organize(life/tasks), finance, capture + `search_all`. Every
  per-domain method is called uniformly as `method(keywords=..., limit=...)`
  (exactly how SearchService.search_all calls them) and returns the standardized
  `{id, title, snippet, date, url, metadata}` shape.
* `apps.notes.services.search_notes_cos` — hybrid FTS+embeddings notes search.

NO new search engine, NO new embeddings, NO duplicate indexing, NO parallel
history store. WLJ owns historical truth; ChatGPT reasons over it.

`timeframe` is parsed deterministically and applied uniformly on each result's
`date` field, so we never depend on per-method date-range support. Unknown stays
unknown — empty results return status='empty', never a fabricated history.
"""

import logging
from datetime import date, datetime, timedelta

from apps.ai.cos_services.serialization import cap as _cap
from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

HISTORY_SEARCH_SCHEMA_VERSION = "1.0"
_MAX_RESULTS = 12
_FETCH_LIMIT = 40  # fetch wider, then timeframe-filter + cap

# ChatGPT-facing domain -> SearchService method name.
_SEARCH_DOMAIN_MAP = {
    "journal": "search_journal",
    "health": "search_health",
    "goals": "search_goals",
    "purpose": "search_goals",      # exposure alias
    "faith": "search_faith",
    "life": "search_organize",      # organize = tasks/life
    "organize": "search_organize",
    "tasks": "search_organize",
    "finance": "search_finance",
    "capture": "search_capture",
}

# Full supported set (+ notes via search_notes_cos, + 'all' combined).
SUPPORTED_HISTORY_DOMAINS = sorted(set(_SEARCH_DOMAIN_MAP) | {"notes", "all"})

# Named timeframe windows (days back from today).
_TIMEFRAME_DAYS = {
    "week": 7, "month": 30, "quarter": 90, "halfyear": 180, "year": 365,
}


def _today():
    try:
        from django.utils import timezone
        return timezone.now().date()
    except Exception:
        return date.today()


def _parse_timeframe(timeframe):
    """Return (start_date, end_date) or None. Deterministic, lenient.

    Accepts: None; "<N>d" (e.g. '7d','90d'); a named window
    (week/month/quarter/halfyear/year); or an explicit 'YYYY-MM-DD:YYYY-MM-DD'.
    Unrecognized -> None (no filtering), never an error.
    """
    if not timeframe:
        return None
    tf = str(timeframe).strip().lower()
    end = _today()
    # explicit range
    if ":" in tf:
        try:
            a, b = tf.split(":", 1)
            start = datetime.strptime(a.strip(), "%Y-%m-%d").date()
            stop = datetime.strptime(b.strip(), "%Y-%m-%d").date()
            return (start, stop)
        except ValueError:
            return None
    # "<N>d"
    if tf.endswith("d") and tf[:-1].isdigit():
        return (end - timedelta(days=int(tf[:-1])), end)
    # named window
    if tf in _TIMEFRAME_DAYS:
        return (end - timedelta(days=_TIMEFRAME_DAYS[tf]), end)
    if tf.isdigit():
        return (end - timedelta(days=int(tf)), end)
    return None


def _within(result, date_range):
    """True if a standardized result's `date` falls in range (inclusive).
    Results without a parseable date are EXCLUDED when a timeframe is set."""
    if not date_range:
        return True
    iso = result.get("date") if isinstance(result, dict) else None
    if not iso:
        return False
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False
    start, stop = date_range
    if start and d < start:
        return False
    if stop and d > stop:
        return False
    return True


def _emit(user_id, domain, status, count, timeframe):
    try:
        logger.info(
            "SEARCH_HISTORY user=%s domain=%s status=%s count=%s timeframe=%s",
            user_id, domain, status, count, timeframe,
        )
    except Exception:
        pass


def _envelope(query, domain, timeframe, status, **extra):
    env = {
        "status": status,
        "query": query,
        "domain": domain,
        "timeframe": timeframe,
        "schema_version": HISTORY_SEARCH_SCHEMA_VERSION,
    }
    env.update(extra)
    return env


def search_history(user, query, *, domain=None, timeframe=None):
    """
    Search the user's deterministic history. Read-only, JSON-safe, no fabrication.

    Args:
        user: Django User instance.
        query: free-text search string.
        domain: one of SUPPORTED_HISTORY_DOMAINS, or None/'all' to search across.
        timeframe: optional window ('7d','30d','year', 'YYYY-MM-DD:YYYY-MM-DD', ...).

    Returns:
        dict envelope: status ready|empty|unsupported_domain|error, plus
        count + results (standardized {id,title,snippet,date,url,metadata}).
    """
    uid = getattr(user, "id", "?")
    dom = (domain or "all").strip().lower()
    q = (query or "").strip()
    keywords = [t for t in q.split() if t]
    date_range = _parse_timeframe(timeframe)

    # --- unknown domain ---
    if dom not in SUPPORTED_HISTORY_DOMAINS:
        _emit(uid, dom, "unsupported_domain", 0, timeframe)
        return _envelope(
            q, dom, timeframe, "unsupported_domain",
            reason="Unknown history domain.",
            supported_domains=SUPPORTED_HISTORY_DOMAINS,
        )

    try:
        if dom == "notes":
            from apps.notes.services import search_notes_cos
            raw = search_notes_cos(user, q, limit=_FETCH_LIMIT) or {}
            results = list(raw.get("results", []))
        elif dom == "all":
            from apps.ai.search_service import SearchService
            raw = SearchService(user).search_all(keywords or [q], limit=_FETCH_LIMIT) or {}
            results = list(raw.get("results", []))
        else:
            from apps.ai.search_service import SearchService
            svc = SearchService(user)
            method = getattr(svc, _SEARCH_DOMAIN_MAP[dom])
            raw = method(keywords=keywords or None, limit=_FETCH_LIMIT) or {}
            results = list(raw.get("results", []))
    except Exception as exc:
        logger.warning("search_history failed user=%s domain=%s", uid, dom,
                       exc_info=True)
        _emit(uid, dom, "error", 0, timeframe)
        return _envelope(q, dom, timeframe, "error",
                         reason="History search failed; see server logs.")

    # Uniform timeframe filter on the standardized `date` field, then cap.
    if date_range:
        results = [r for r in results if _within(r, date_range)]
    results = _jsonsafe(_cap(results, _MAX_RESULTS))
    status = "ready" if results else "empty"
    _emit(uid, dom, status, len(results), timeframe)
    return _envelope(
        q, dom, timeframe, status,
        count=len(results), results=results,
        _meta={"source": "SearchService" if dom != "notes" else "search_notes_cos"},
    )
