# ==============================================================================
# File: apps/core/trend_range.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reusable TREND-RANGE primitives — the shared "how far back am I
#              looking?" capability for every trend/metric page (Weight first, then
#              Glucose, Blood Pressure, Heart Rate, Sleep, Body Fat, …). Provides the
#              canonical range OPTIONS, deterministic range→start-date resolution,
#              query-param parsing, and per-page preference persistence. It is
#              deliberately domain-agnostic: it knows about *windows of time*, never
#              about weight, glucose, or any metric. A page becomes a consumer by
#              (1) parsing the range, (2) computing its own facts over the resolved
#              window, (3) rendering the shared selector component. No page re-invents
#              range parsing, validation, persistence, or the option list.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Domain-agnostic trend-range selection.

One place defines the ranges (All Time / 2Y / 1Y / 6M / 3M), one place resolves a
range key to a start date, one place validates the `?range=` param, and one place
persists a user's last-selected range per page. Every trend page shares these so the
selector behaves identically everywhere and preferences are stored uniformly.
"""
from dateutil.relativedelta import relativedelta

# Canonical ordered ranges. `months=None` means "all time" (no lower bound).
# `suffix` is the short label a page appends to its stat labels — Low (6M), Avg (1Y),
# Lowest Ever (ALL is spelled out by the page, not forced here).
#   key,   label,        months, suffix
TREND_RANGES = [
    ("all", "All Time", None, "ALL"),
    ("2y", "2 Years", 24, "2Y"),
    ("1y", "1 Year", 12, "1Y"),
    ("6m", "6 Months", 6, "6M"),
    ("3m", "3 Months", 3, "3M"),
]

DEFAULT_TREND_RANGE = "all"

_BY_KEY = {key: (label, months, suffix) for key, label, months, suffix in TREND_RANGES}


def is_valid_range(key):
    """True when `key` is a known range key."""
    return key in _BY_KEY


def normalize_range(key, default=DEFAULT_TREND_RANGE):
    """Return `key` if valid, else `default` (which is itself validated → falls back to
    the module default). Never raises — bad input degrades to a safe range."""
    if is_valid_range(key):
        return key
    return default if is_valid_range(default) else DEFAULT_TREND_RANGE


def range_label(key):
    """Human label for a range key (e.g. '6 Months'); '' for unknown keys."""
    entry = _BY_KEY.get(key)
    return entry[0] if entry else ""


def range_suffix(key):
    """Short stat suffix for a range key (e.g. '6M', 'ALL'); '' for unknown keys."""
    entry = _BY_KEY.get(key)
    return entry[2] if entry else ""


def range_start_date(key, today):
    """The inclusive local-day START of `key` given `today` (a date), or None for
    'all time' / unknown keys. Calendar-accurate (relativedelta): 6 months before
    Aug 2 is Feb 2, matching what a person means by 'the last 6 months'."""
    entry = _BY_KEY.get(key)
    if not entry:
        return None
    months = entry[1]
    if months is None:
        return None
    return today - relativedelta(months=months)


def trend_range_options(selected_key):
    """The option list a selector/JSON payload renders: one dict per range with its
    key, label, suffix, and whether it's the active selection. Order is canonical."""
    selected = normalize_range(selected_key)
    return [
        {"key": key, "label": label, "suffix": suffix, "active": key == selected}
        for key, label, months, suffix in TREND_RANGES
    ]


# ---- query-param + preference plumbing (shared by every trend page) ----------

def parse_range_param(request, default):
    """Validated range key from `?range=` on the request, falling back to `default`
    (typically the user's saved range). Domain pages never re-parse the param."""
    return normalize_range((request.GET.get("range") or "").strip(), default=default)


def get_saved_range(user, page_key, default=DEFAULT_TREND_RANGE):
    """The user's last-selected range for `page_key` (e.g. 'health.weight'), or
    `default`. Stored under UserPreferences.dashboard_config['trend_range'][page_key] —
    the same JSON store other per-page view preferences use. Read-only; never raises."""
    try:
        prefs = user.preferences
    except Exception:
        return normalize_range(default)
    store = (prefs.dashboard_config or {}).get("trend_range") or {}
    return normalize_range(store.get(page_key), default=default)


def save_range(user, page_key, key):
    """Persist `key` as the user's last-selected range for `page_key`. No-op when the
    value is unchanged (avoids a needless write on the read path). Returns the stored
    (normalized) key. Safe on the request path — one small JSON-field row update."""
    key = normalize_range(key)
    try:
        prefs = user.preferences
    except Exception:
        return key
    cfg = dict(prefs.dashboard_config or {})
    store = dict(cfg.get("trend_range") or {})
    if store.get(page_key) == key:
        return key                                   # unchanged → skip the write
    store[page_key] = key
    cfg["trend_range"] = store
    prefs.dashboard_config = cfg
    prefs.save(update_fields=["dashboard_config"])
    return key
