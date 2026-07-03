# ==============================================================================
# File: apps/ai/chatgpt_cos/temporal_grounding.py
# Project: Whole Life Journey
# Capability: Temporal Grounding & Data Freshness Awareness.
#
# A Chief of Staff who makes TIME-RELATIVE statements ("last night", "today",
# "this week") must always be able to GROUND them in deterministic temporal
# truth: the current date/time/timezone, the concrete window the label resolves
# to, and the timestamp + freshness of the underlying record. And when the user
# CHALLENGES the data ("is that stale?", "which record?", "what date are you
# calling last night?"), Beth must enter a deterministic TRUST-VERIFICATION mode
# — which record, what window, when recorded/synced, freshness, whether newer
# data may exist, and honest uncertainty — rather than fail the conversation.
#
# Reusable + deterministic + NO LLM. Strengthens the existing capability
# (get_user_now / freshness / conversation_memory.compose_when/compose_is_current)
# — it is a helper, not a new architectural layer. Two rules it enforces:
#   1. Never label data as a window it doesn't cover (a 7-night average is NOT
#      "last night").
#   2. A time-relative statement is only trustworthy if Beth can name its window,
#      its record, and its freshness on request.
# ==============================================================================
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


# ── Current temporal truth (date / time / timezone) ────────────────────────

def now_context(user):
    """Deterministic current temporal truth in the USER's timezone."""
    from apps.core.utils import get_user_now, get_user_today
    now = get_user_now(user)
    today = get_user_today(user)
    return {
        "now": now, "today": today,
        "date_long": _fmt_date_long(today),
        "weekday": now.strftime("%A"),
        "time_12h": _fmt_time(now),
        "tz": str(getattr(now, "tzinfo", "") or "") or "your local timezone",
        "date_iso": today.isoformat(),
    }


def _fmt_time(dt):
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def _fmt_date_long(d):
    return d.strftime("%A, %B ") + str(d.day) + d.strftime(", %Y")


_DATE_CUES = (
    "what's the date", "whats the date", "what is the date", "what date is it",
    "what date is today", "what's today's date", "whats todays date",
    "today's date", "todays date", "what day is it", "what day is today",
    "what's the day", "whats the day", "what is today's date", "what day of the week",
)
_TIME_CUES = (
    "what time is it", "what's the time", "whats the time", "what is the time",
    "current time", "the time right now", "what time do you have", "time right now",
)
_TZ_CUES = ("what timezone", "what time zone", "which timezone", "which time zone",
            "my timezone", "my time zone", "what's my timezone", "what tz")


def answer_datetime(user, message):
    """Deterministic answer for 'what date/time/day/timezone is it', or None.
    A CoS that speaks in time-relative terms must always know the clock."""
    n = (message or "").strip().lower()
    if not n:
        return None
    try:
        ctx = now_context(user)
    except Exception:
        logger.warning("temporal: now_context failed", exc_info=True)
        return None
    if any(c in n for c in _TZ_CUES):
        return _result(
            f"Your timezone is {ctx['tz']} — right now it's {ctx['time_12h']} on "
            f"{ctx['date_long']}.")
    if any(c in n for c in _TIME_CUES):
        return _result(f"It's {ctx['time_12h']} ({ctx['tz']}) on {ctx['date_long']}.")
    if any(c in n for c in _DATE_CUES):
        return _result(f"Today is {ctx['date_long']}.")
    return None


def _result(answer, **extra):
    d = {"answer": answer, "tools_called": [], "tools_advertised": [],
         "lane": "temporal"}
    d.update(extra)
    return d


# ── Grounding a time-relative claim (never mislabel a window) ───────────────

def _relative_night(user, iso):
    """Human phrase for a sleep date relative to today: 'last night', 'the night
    of <date>', 'N nights ago'. Deterministic, tz-aware."""
    try:
        from apps.core.utils import get_user_today
        d = date.fromisoformat(iso)
        today = get_user_today(user)
    except Exception:
        return f"the night of {iso}"
    delta = (today - d).days
    if delta <= 1:
        return "last night"
    if delta == 2:
        return "the night before last"
    return f"{delta} nights ago ({_fmt_date_long(d)})"


def sleep_last_night_grounded(user, state):
    """A CORRECTLY-LABELLED sleep statement + interrogable temporal metadata.

    NEVER labels the 7-night average as 'last night'. Returns
    ``(sentence, is_strong, fact)`` where ``fact`` carries the window, record
    date, freshness and source so a follow-up ('which record? is that stale?')
    can be verified. Returns ``(None, False, None)`` when there's no sleep truth.
    """
    st = state or {}
    ln = st.get("sleep_last_night_hours")
    last_date_iso = st.get("last_sleep_entry")     # the most recent sleep record's date
    try:
        from apps.core.utils import get_user_today
        today = get_user_today(user)
    except Exception:
        today = None

    fact = {"key": "sleep_last_night", "unit": "hours", "source": "your sleep tracker"}

    # Case 1 — a genuine per-night value tied to a dated record.
    if isinstance(ln, (int, float)) and ln > 0 and last_date_iso:
        try:
            rec = date.fromisoformat(last_date_iso)
        except Exception:
            rec = None
        within_last_night = rec is not None and today is not None and (today - rec).days <= 1
        fact.update({"value": round(float(ln), 1), "for_date": last_date_iso,
                     "record_date": last_date_iso,
                     "freshness": "current" if within_last_night else "stale",
                     "window": "last night" if within_last_night else "most recent night"})
        if within_last_night:
            s = (f"You got about {ln:g} hours of sleep last night"
                 + (" — a bit short." if ln < 6.5 else "."))
            return s, (ln < 6.5), fact
        # The latest record is OLDER than last night → do NOT claim "last night".
        s = (f"Your most recent recorded night ({_relative_night(user, last_date_iso)}) "
             f"was about {ln:g} hours — I don't have last night's sleep synced yet.")
        return s, False, fact

    # Case 2 — only a 7-night AVERAGE exists → label it honestly, never "last night".
    avg = st.get("sleep_avg_hours_7d")
    n7 = st.get("sleep_entries_7d")
    if isinstance(avg, (int, float)) and avg > 0:
        fact.update({"value": round(float(avg), 1), "window": "7-night average",
                     "aggregate": True, "freshness": "current",
                     "for_date": last_date_iso, "entries": n7})
        s = (f"Over your last {int(n7) if isinstance(n7, (int, float)) and n7 else 7} "
             f"recorded nights you've averaged about {avg:g} hours — I don't have a "
             f"confirmed figure for last night specifically.")
        return s, (avg < 6.5), fact

    return None, False, None


# ── Trust-Verification Mode (the conversation shifted to TRUST) ─────────────

_TRUST_CUES = (
    "which record", "what record", "which sleep record", "which night",
    "what night", "what date are you calling", "what date is that",
    "which last night", "what timeframe", "what window", "what time window",
    "how old is", "how old's", "how recent", "is that stale", "is it stale",
    "is the data stale", "is that old", "how stale", "when was this synced",
    "when was it synced", "when did it sync", "last sync", "synchronized",
    "synchronised", "when was this synchronized", "when was it recorded",
    "when was that recorded", "are you sure you're looking at",
    "sure you're looking at", "sure that's today", "sure it's today",
    "sure that's last night", "is this today", "is that today", "up to date",
    "how confident", "are you confident", "how do you know that's last night",
    "i think your data is stale", "your data is stale", "that data is stale",
    "is that current", "is this current",
)


def is_temporal_trust_challenge(message):
    """The user is questioning the freshness/window of a time-relative statement —
    the conversation has shifted from the topic to TRUST."""
    n = (message or "").strip().lower()
    return bool(n) and any(c in n for c in _TRUST_CUES)


def verify_temporal_trust(user, last, message):
    """Deterministic TRUST-VERIFICATION over the last time-relative fact: which
    record, what window/date, when recorded/synced, freshness, whether newer data
    may exist, and honest uncertainty. Returns a result dict, or None when the
    last answer carries no groundable temporal fact (so the caller routes on)."""
    # The grounded fact may live on the active_subject after a prior verification
    # overwrote the top-level fact — read both.
    fact = (last or {}).get("fact") or \
        ((last or {}).get("active_subject") or {}).get("fact") or {}
    fk = (last or {}).get("fact_key") or fact.get("key") or ""
    for_date = fact.get("for_date") or fact.get("record_date")
    window = fact.get("window")
    freshness = fact.get("freshness")
    # Only enter verification for a GROUNDED time-relative narration (it carries a
    # window / aggregate marker, or is the sleep check-in fact). Standard facts
    # (glucose, weight) keep their own freshness follow-up via why_explainer.
    is_grounded_temporal = bool(window or fact.get("aggregate")) or fk.startswith("sleep")
    if not is_grounded_temporal:
        return None

    # Sleep gets fully-grounded verification straight from the canonical record
    # (one indexed read — this is a direct user question, not the hot path).
    if fk == "sleep_last_night" or (fk or "").startswith("sleep"):
        return _result(_verify_sleep(user, fact, message))

    # Generic temporal fact — verify from the metadata we already hold.
    parts = []
    if window:
        parts.append(f"I'm referring to your {window}")
    if for_date:
        parts.append(f"the record dated {for_date}")
    if freshness == "stale":
        parts.append("and I've flagged it as not fully current — treat it as the "
                     "most recent I have, not necessarily the latest")
    elif freshness in ("pending", "missing"):
        parts.append("and I don't have a confirmed current value for it")
    elif freshness == "current":
        parts.append("and it's the most recent reading I have")
    if not parts:
        return None
    return _result(". ".join(p[0].upper() + p[1:] for p in [", ".join(parts)]) + ".")


def _verify_sleep(user, fact, message):
    """Ground the sleep claim against the canonical SleepEntry (date, sync time,
    source) and answer the specific trust question honestly."""
    n = (message or "").strip().lower()
    rec = _latest_sleep_record(user)
    ctx = now_context(user)
    aggregate = bool(fact.get("aggregate"))

    # What date/window am I calling this?
    if aggregate:
        base = ("To be clear, that figure was your average over your last several "
                "recorded nights — not last night specifically. ")
    elif rec and rec.get("sleep_date"):
        base = (f"I'm referring to your sleep record for "
                f"{_relative_night(user, rec['sleep_date'].isoformat())} "
                f"({_fmt_date_long(rec['sleep_date'])}). ")
    elif fact.get("for_date"):
        base = (f"I'm referring to your sleep record dated {fact['for_date']}. ")
    else:
        base = ("I don't have a specific sleep record to point to right now. ")

    # When was it recorded / synced?
    if any(c in n for c in ("sync", "recorded", "how old", "how recent", "how stale")):
        if rec and rec.get("recorded_at"):
            when = _fmt_date_long(rec["recorded_at"].astimezone(ctx["now"].tzinfo).date())
            t = _fmt_time(rec["recorded_at"].astimezone(ctx["now"].tzinfo))
            src = rec.get("source") or "your tracker"
            return (base + f"It came in from {src} and was recorded {when} at {t}. "
                    "If your tracker has synced a newer night since then, I may not "
                    "have picked it up yet — say the word and I'll treat this as "
                    "unconfirmed.")
        return (base + "I don't have a reliable sync timestamp for it, so I can't "
                "confirm exactly how fresh it is — treat it as unconfirmed until it "
                "re-syncs.")

    # Are you sure it's today's / last night's? / confidence / staleness.
    if rec and rec.get("sleep_date"):
        delta = (ctx["today"] - rec["sleep_date"]).days
        if aggregate:
            return (base + "So I wouldn't lean on it as last night's number — want me "
                    "to pull just the most recent night instead?")
        if delta <= 1:
            return (base + "That's the most recent night I have and it lines up with "
                    "last night, so I'm confident it represents it. If you think a "
                    "newer sync exists, I can re-check.")
        return (base + f"That's {delta} nights old, so it does NOT represent last "
                "night — I don't have last night synced yet. I shouldn't have implied "
                "it was last night; treat it as your most recent recorded night.")
    return (base + "I can't confirm which night it represents right now, so please "
            "treat it as unconfirmed rather than as last night.")


def _latest_sleep_record(user):
    try:
        from apps.health.models import SleepEntry
        return (SleepEntry.objects.filter(user=user)
                .order_by("-sleep_date", "-recorded_at")
                .values("sleep_date", "recorded_at", "source",
                        "total_duration_minutes").first())
    except Exception:
        logger.warning("temporal: latest sleep record read failed", exc_info=True)
        return None
