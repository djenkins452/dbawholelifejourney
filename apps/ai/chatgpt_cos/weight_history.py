# ==============================================================================
# File: apps/ai/chatgpt_cos/weight_history.py
# Capability: HISTORICAL TRUTH NAVIGATION for weight. Beth navigates the deterministic
# weigh-in series the way a Chief of Staff naturally would — a specific day (yesterday,
# day before yesterday, July 1, June 15, last Monday, two weeks ago), a THRESHOLD
# crossing ("when did I first drop below 290"), an EXTREMUM ("lowest weight this year"),
# or an AGGREGATE ("average weight last month"). All read the canonical weight_queries
# layer; nothing is inferred or special-cased per date.
#
# `navigate()` is the reusable engine (topic already known — no keyword gate); `answer()`
# is the lane entry (gated on a weight cue). The referential lane calls navigate()
# directly for elliptical follow-ups that carry no "weight" word.
# ==============================================================================
import logging
import re
from datetime import date, timedelta

from apps.ai.chatgpt_cos.date_reference import resolve_reference_date, fmt_date
from apps.health.services import weight_queries

logger = logging.getLogger(__name__)

_WEIGHT_CUES = ("weight", "weigh", "weighed")

# THRESHOLD crossing — a number with an explicit direction ("below 290", "above 300").
_THRESH_RE = re.compile(r"\b(below|under|beneath|above|over)\s+(\d{2,3}(?:\.\d)?)\b")
_CROSS_INTENT = ("first", "drop", "dropp", "fell", "fall", "went", "go ", "got",
                 "get ", "cross", "reach", "hit", "when", "under", "below", "above", "over")
# A crossing VERB with no explicit direction word ("break 300", "hit 290", "reach 250").
# Direction is inferred from the user's weight TREND — no hardcoded threshold. This is
# what makes navigation natural: any number, any phrasing, works.
_CROSS_VERBS = ("break", "broke", "breaking", "hit", "reach", "reached", "cross",
                "crossed", "pass", "passed", "dip", "dipped", "drop", "dropped",
                "fell", "fall", "went", "get to", "got to", "get under", "got under")
_BARE_NUM_RE = re.compile(r"\b(\d{2,3}(?:\.\d)?)\b")
_LOWEST = ("lowest", "lightest", "least i weigh", "minimum weight", "min weight")
_HIGHEST = ("highest", "heaviest", "most i weigh", "maximum weight", "max weight", "peak weight")
_EXTREMUM_INTENT = ("lowest", "highest", "lightest", "heaviest", "peak", "most i weigh",
                    "least i weigh", "minimum", "maximum")
_AVG = ("average", "avg ", "mean ")


def _fmt_lb(v):
    """Weight to one decimal, dropping a trailing .0 (284.4 → '284.4', 286.0 → '286')."""
    v = round(float(v), 1)
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def _window(user, n):
    """(start, end, label) for a time window named in the message, or (None, None,
    'on record') for the full series."""
    from apps.core.utils import get_user_today
    today = get_user_today(user)
    if "this year" in n:
        return date(today.year, 1, 1), today, "this year"
    if "last year" in n:
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), "last year"
    if "this month" in n:
        return date(today.year, today.month, 1), today, "this month"
    if "last month" in n:
        first_this = date(today.year, today.month, 1)
        last_prev = first_this - timedelta(days=1)
        return date(last_prev.year, last_prev.month, 1), last_prev, "last month"
    if "past 30" in n or "last 30" in n or "past month" in n:
        return today - timedelta(days=30), today, "the last 30 days"
    if "this week" in n:
        return today - timedelta(days=today.weekday()), today, "this week"
    if "last week" in n or "past week" in n:
        return today - timedelta(days=7), today, "the last week"
    return None, None, "on record"


def _trend_direction(user):
    """Which way the user is crossing thresholds — inferred from the weight TREND
    (oldest vs newest). A weight-loss trend crosses DOWNWARD, so 'break 300' means dropped
    below 300. Defaults to 'below' (the wellness context) when the trend is flat/unknown."""
    try:
        s = weight_queries.series(user)
        if len(s) >= 2:
            if s[-1]["value_lb"] < s[0]["value_lb"]:
                return "below"
            if s[-1]["value_lb"] > s[0]["value_lb"]:
                return "above"
    except Exception:
        logger.warning("weight_history: trend read failed", exc_info=True)
    return "below"


def _parse_threshold(user, n):
    """(threshold, direction) for a crossing question, or None. Accepts an EXPLICIT
    direction ('below 290', 'over 300') OR a bare-number crossing verb ('break 300',
    'hit 250') whose direction is inferred from the trend — so any threshold navigates."""
    m = _THRESH_RE.search(n)
    if m and any(w in n for w in _CROSS_INTENT):
        word = m.group(1)
        return float(m.group(2)), ("above" if word in ("above", "over") else "below")
    if any(v in n for v in _CROSS_VERBS):
        bm = _BARE_NUM_RE.search(n)
        if bm:
            return float(bm.group(1)), _trend_direction(user)
    return None


def navigate(user, message):
    """Navigate the weight series for `message`. Returns a human answer string, or None
    when the message isn't a weight-history navigation. Topic is assumed to be weight —
    callers gate on that (the lane on a weight cue, the referential lane on the active
    topic). No special-cased dates: every branch reads the canonical weight_queries."""
    n = (message or "").lower()
    try:
        # 1) THRESHOLD crossing — explicit ("drop below 290") OR a bare-number crossing
        #    verb ("when did I break 300?") with direction inferred from the trend.
        thr = _parse_threshold(user, n)
        if thr is not None:
            num, direction = thr
            verb = "climbed above" if direction == "above" else "dropped below"
            rec = weight_queries.first_crossing(user, num, direction)
            if rec:
                return (f"You first {verb} {_fmt_lb(num)} lb on {fmt_date(rec['date'])} — "
                        f"you were {_fmt_lb(rec['value_lb'])} lb that day.")
            ext = weight_queries.extremum(user, "lowest" if direction == "below" else "highest")
            if ext:
                edge = "lowest" if direction == "below" else "highest"
                return (f"You haven't {verb} {_fmt_lb(num)} lb yet — your {edge} on record is "
                        f"{_fmt_lb(ext['value_lb'])} lb on {fmt_date(ext['date'])}.")
            return "I don't have any weigh-ins on record yet."

        # 2) EXTREMUM — "lowest weight this year", "when did I reach my lowest?"
        if any(w in n for w in _EXTREMUM_INTENT):
            kind = "highest" if any(w in n for w in _HIGHEST) else "lowest"
            start, end, label = _window(user, n)
            rec = weight_queries.extremum(user, kind, start, end)
            if rec:
                where = "" if label == "on record" else f" {label}"
                return (f"Your {kind} weight{where} was {_fmt_lb(rec['value_lb'])} lb on "
                        f"{fmt_date(rec['date'])}.")
            return f"I don't have any weigh-ins {('' if label == 'on record' else label)} to check.".replace("  ", " ")

        # 3) AGGREGATE — "average weight last month / this week / last 30 days"
        if any(w in n for w in _AVG):
            start, end, label = _window(user, n)
            if start is None:                              # "average weight" with no window
                from apps.core.utils import get_user_today
                end = get_user_today(user)
                start, label = end - timedelta(days=30), "the last 30 days"
            avg = weight_queries.average_over(user, start, end)
            period = f"over {label}" if label.startswith("the ") else label
            if avg:
                return (f"Your average weight {period} was {_fmt_lb(avg['avg_lb'])} lb "
                        f"({avg['n']} weigh-in{'s' if avg['n'] != 1 else ''}).")
            return f"I don't have any weigh-ins {period} to average."

        # 4) POINT-IN-TIME — a specific day (yesterday, July 1, June 15, last Monday…)
        target = resolve_reference_date(user, message, include_today=False)
        if target is not None:
            rec = weight_queries.on_date(user, target)
            if rec is None:
                return f"I don't have a weight reading for {fmt_date(target)}."
            return f"On {fmt_date(target)} you weighed {_fmt_lb(rec['value_lb'])} lb."
    except Exception:
        logger.warning("weight_history: navigate failed", exc_info=True)
        return None
    return None


def answer(user, message, conversation=None):
    """Lane entry — gated on a weight cue so it never steals a non-weight message. The
    navigation itself is done by navigate()."""
    n = (message or "").lower()
    if not any(c in n for c in _WEIGHT_CUES):
        return None
    ans = navigate(user, message)
    if ans is None:
        return None
    out = {"answer": ans, "tools_called": [], "tools_advertised": [],
           "lane": "weight_history"}
    try:                                  # backward-compat: expose the resolved point-in-time day
        target = resolve_reference_date(user, message, include_today=False)
        if target is not None:
            out["weight_date"] = target.isoformat()
    except Exception:
        pass
    return out
