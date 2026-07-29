# ==============================================================================
# File: apps/health/services/glucose_readings.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Canonical INTRA-DAY glucose reading truth — the single producer of
#              individual timestamped CGM readings + window statistics/excursions,
#              consumed by BOTH the Glucose page (Current Context) and the Chief of
#              Staff (get_readings). First adopter of the platform ReadingWindow
#              capability (apps.core.truth.reading_window / .windows).
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Glucose reading-window truth — the deterministic answer to intra-day questions.

    "What were my lows overnight?"          → low_excursions + minimum
    "Show my glucose for the last 12 hours" → samples + count
    "Did I spend much time below 70 last night?" → below_low / below_low_pct
    "My readings between midnight and 6 AM"  → an explicit Window

The architectural condition this removes: individual 5-minute CGM readings existed in
`GlucoseEntry` but were reachable ONLY as per-day averages (history) or a 30-record
cap (entity) — so the CoS answered overnight-lows questions with a daily mean, and the
Glucose page was invisible to the assistant. `glucose_reading_window` is now the ONE
producer of intra-day glucose truth; the page's Current Context provider
(`health.glucose`) and the CoS `get_readings` tool both call it, so page and assistant
can never disagree about the readings on screen.

Facts only — WLJ exposes the numbers and the excursions; the model decides what they
mean (never a "your control is poor" verdict here). Deterministic; request-path-safe
(one indexed, window-bounded query; stats in Python over a clamped intra-day span).
"""
from django.utils import timezone
from django.utils.dateformat import format as _dj_date

from apps.core.truth.reading_window import ReadingWindowSpec, build_reading_series
from apps.core.truth.windows import Window, resolve_window


# Clinical bands (mg/dL), aligned with the canonical interpreter
# (apps.health.services.glucose_interpretation) and the dashboard's TIR convention:
#   in-range = 70–180 · low < 70 (caution) · very-low < 54 (danger) · very-high ≥ 251.
GLUCOSE_LOW = 70.0
GLUCOSE_HIGH = 180.0
GLUCOSE_URGENT_LOW = 54.0
GLUCOSE_URGENT_HIGH = 250.0

# The metric spec the platform producer consumes. `value_getter` returns the reading
# already normalized to mg/dL (GlucoseEntry.value_in_mg_dl), so mixed-unit rows
# (mmol/L) are compared correctly against the mg/dL thresholds.
GLUCOSE_READING_SPEC = ReadingWindowSpec(
    domain="health",
    metric="glucose",
    unit="mg/dL",
    value_getter=lambda e: e.value_in_mg_dl,
    time_getter=lambda e: e.recorded_at,
    low=GLUCOSE_LOW,
    high=GLUCOSE_HIGH,
    urgent_low=GLUCOSE_URGENT_LOW,
    urgent_high=GLUCOSE_URGENT_HIGH,
)


def glucose_reading_window(user, window: Window) -> dict:
    """THE single producer of intra-day glucose truth. Returns a ReadingSeries dict
    (individual samples + window statistics + low excursions) for `window`.

    One window-bounded query over the `(user, source, recorded_at)` index; statistics
    computed over the clamped intra-day span. Same DB state → same dict."""
    from apps.health.models import GlucoseEntry

    rows = list(
        GlucoseEntry.objects.filter(
            user=user,
            recorded_at__gte=window.start,
            recorded_at__lte=window.end,
        )
        .only("value", "unit", "recorded_at")
        .order_by("recorded_at")
    )
    return build_reading_series(GLUCOSE_READING_SPEC, window, rows).to_dict()


# ── Current Context page summary (the Glucose page's deterministic truth) ──────

def _t(iso_str):
    """Local 'h:mm AM/PM' for an ISO timestamp string (from the ReadingSeries)."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso_str)
    except (TypeError, ValueError):
        return iso_str or "—"
    return _dj_date(timezone.localtime(dt), "g:i A")


def _g(v):
    """Render a mg/dL number without a trailing '.0' (68.0 → '68', 68.5 → '68.5')."""
    if v is None:
        return "—"
    return f"{v:g}"


def build_glucose_page_summary(user) -> dict:
    """Deterministic Current Context for the Glucose dashboard — the SAME truth the page
    shows (latest reading, recent readings, lows), sourced from `glucose_reading_window`
    so the assistant answers "look at this page" and "my lows overnight" WITHOUT
    retrieval and can never contradict the screen. Facts only; the model interprets.

    Returns the uniform {title, content, kind} the Current Context system consumes."""
    from apps.core.utils import get_user_now
    from apps.health.services.glucose_snapshot import (
        build_glucose_latest,
        build_glucose_summary,
    )

    now = get_user_now(user)
    latest = build_glucose_latest(user)
    if latest is None:
        return {"title": "Glucose", "kind": "glucose overview",
                "content": "Glucose — no readings logged yet."}

    # Intra-day block: a trailing 24-hour window ALWAYS covers "last night", regardless
    # of the hour the page is opened — sourced from the single reading-window producer.
    win = resolve_window("past 24 hours", now)
    day = glucose_reading_window(user, win)

    lines = []

    # 1) Latest reading (value, trend, freshness, source) — the headline on the page.
    lead = f"Latest reading: {_g(latest['value'])} {latest['unit']}"
    if latest.get("trend_label"):
        lead += f", {latest['trend_label']}"
        if latest.get("trend_arrow"):
            lead += f" {latest['trend_arrow']}"
    mins = latest.get("minutes_ago")
    if mins is not None:
        lead += (" (just now)" if mins <= 1 else f" ({mins} min ago)")
    if latest.get("source_label"):
        lead += f" from {latest['source_label']}"
    if latest.get("stale"):
        lead += " — note: this is the most recent reading but it is over 2 hours old"
    lines.append(lead + ".")

    # 2) Last-24h window facts (min/max/avg, in-range, below-70) — the individual-reading
    #    truth the page's recent-readings list shows, summarized deterministically.
    if day.get("present"):
        seg = (f"Last 24 hours: {day['count']} readings — "
               f"low {_g(day['minimum'])}, high {_g(day['maximum'])}, "
               f"average {_g(day['average'])} mg/dL")
        below = day.get("below_low")
        if below is not None and day.get("below_low_pct") is not None:
            seg += (f". Below 70 mg/dL: {below} reading"
                    f"{'' if below == 1 else 's'} ({day['below_low_pct']}%)")
        if day.get("in_range_pct") is not None:
            seg += f". In range (70–180): {day['in_range_pct']}%"
        lines.append(seg + ".")

        # 3) The individual LOW readings with timestamps — the exact truth behind
        #    "extreme lows in the 40s and 50s overnight". Worst-first, capped.
        lows = day.get("low_excursions") or []
        if lows:
            shown = lows[:10]
            listed = ", ".join(f"{_g(r['value'])} at {_t(r['at'])}" for r in shown)
            more = "" if len(lows) <= len(shown) else f", +{len(lows) - len(shown)} more"
            lines.append(f"Low readings (below 70) in the last 24h: {listed}{more}.")

    # 3b) EXPLICIT OVERNIGHT segment (local 12 AM–6 AM) from the SAME producer — so
    #     "what happened overnight" is answerable verbatim from Current Context, never a
    #     retrieval. A named window the user asks about should be labeled on the page.
    ov_win = resolve_window("overnight", now)
    ov = glucose_reading_window(user, ov_win) if ov_win else {"present": False}
    if ov.get("present"):
        seg = (f"Overnight (12 AM–6 AM): {ov['count']} readings — "
               f"low {_g(ov['minimum'])}, average {_g(ov['average'])} mg/dL")
        ov_below = ov.get("below_low")
        if ov_below:
            seg += f", {ov_below} below 70"
            if ov.get("urgent_low_count"):
                seg += f" ({ov['urgent_low_count']} below 54 — severe)"
            ov_lows = ov.get("low_excursions") or []
            if ov_lows:
                listed = ", ".join(f"{_g(r['value'])} at {_t(r['at'])}" for r in ov_lows[:8])
                seg += f". Overnight lows: {listed}"
        elif ov_below == 0:
            seg += ", none below 70"
        lines.append(seg + ".")

    # 4) Multi-day aggregates the page also renders (7/30/90-day averages, TIR, A1C).
    summ = build_glucose_summary(user)
    if summ:
        agg = []
        if summ.get("average_7d") is not None:
            agg.append(f"7-day average {summ['average_7d']} mg/dL")
        if summ.get("time_in_range_pct_7d") is not None:
            agg.append(f"7-day time in range {summ['time_in_range_pct_7d']}%")
        if summ.get("overnight_avg") is not None:
            agg.append(f"overnight average {_g(summ['overnight_avg'])} mg/dL")
        if summ.get("projected_a1c") is not None:
            conf = summ.get("projected_a1c_confidence") or ""
            agg.append(f"projected A1C {summ['projected_a1c']}%"
                       + (f" ({conf} confidence)" if conf else ""))
        if agg:
            lines.append("Trends: " + " · ".join(agg) + ".")
        if summ.get("sync_stale"):
            lines.append("Note: no recent readings have synced — these figures may be "
                         "out of date.")

    return {"title": "Glucose", "kind": "glucose overview",
            "content": "Glucose\n" + "\n".join(lines)}
