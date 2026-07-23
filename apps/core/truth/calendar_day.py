# ==============================================================================
# File: apps/core/truth/calendar_day.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The ONE user-local calendar authority + the calendar-bound truth contract
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-23
# ==============================================================================
"""
User-Local Calendar Authority
=============================

THE single deterministic answer to "what day/time is it *for this user*" and the
contract every calendar-bound cached value must carry.

WHY (runtime-proven, `docs/WLJ_NUTRITION_STATE_INVESTIGATION.md`): a cached value whose
meaning depends on a calendar day cannot be considered fresh merely because no newer
write exists — **calendar days advance without writes; midnight writes nothing.** A
nutrition snapshot kept reporting the previous day's macros as "today" until someone
logged food. The same shape exists wherever a projection says `*_today`.

And the day itself must be the USER's. At 11:00 PM Eastern it is still today for the
user even though UTC has already crossed midnight; at 12:30 AM Eastern "yesterday" is
the preceding *Eastern* day. UTC must never change what "today" means for a person.

COMPOSES, NEVER DUPLICATES — this module owns no date math of its own:
  * timezone / now / today  → `apps.core.utils` (`_get_user_tz`, `get_user_now`,
    `get_user_today`) — zoneinfo-based, so DST gaps/folds are handled deterministically.
  * named windows + natural phrases → `apps.core.truth.periods` (`resolve_period`,
    `resolve_date_expression`) — PURE functions that take `today`, so their correctness
    depends entirely on being handed a USER-LOCAL today. That is what this façade
    guarantees: callers pass a user, never a date they computed themselves.
  * part-of-day (morning/evening/tonight) → `apps.core.truth.daypart`.

THE CALENDAR-BOUND TRUTH CONTRACT
---------------------------------
Any cached/projected value that makes a claim about a calendar day must carry
`stamp(user)` — the represented day, the timezone it was resolved in, when it was
generated, and the authority that produced it. Readers call `day_freshness()` to learn
whether that stamp still describes the user's today. A stale value is still returned;
it is DISCLOSED, never silently presented as current and never hidden.
"""

import logging

logger = logging.getLogger(__name__)

CALENDAR_CONTRACT_VERSION = "1.0"
AUTHORITY = "core.truth.calendar_day"

# Freshness verdicts for a calendar-bound claim.
CURRENT = "current"      # the stamp is the user's today
STALE = "stale"          # the stamp is a different (past or future) day
UNKNOWN = "unknown"      # no stamp — the claim's day cannot be verified

# The stamp key a calendar-bound projection stores.
STAMP_KEY = "calendar_day"


# ── the user's clock ─────────────────────────────────────────────────────────
def tz(user):
    """The user's IANA timezone as a ZoneInfo (zoneinfo → deterministic DST)."""
    from apps.core.utils import _get_user_tz
    return _get_user_tz(user)


def tz_name(user):
    """The user's IANA timezone NAME, carried in every stamp so a value can always
    be re-interpreted in the zone it was resolved in."""
    try:
        return str(user.preferences.timezone_iana)
    except Exception:
        return "UTC"


def now(user):
    """The current instant AS THE USER SEES IT (timezone-aware, user's zone)."""
    from apps.core.utils import get_user_now
    return get_user_now(user)


def today(user):
    """The user's LOCAL calendar day. The only acceptable answer to "what is today"
    for any conversational or truth-producing purpose."""
    from apps.core.utils import get_user_today
    return get_user_today(user)


def yesterday(user):
    from datetime import timedelta
    return today(user) - timedelta(days=1)


# ── boundaries ───────────────────────────────────────────────────────────────
def day_bounds(user, on_date=None):
    """(start, end_exclusive) as timezone-AWARE datetimes bounding a user-local day.

    The boundary is the USER's midnight, not UTC's, so a query filtered on these bounds
    selects the user's day. The end is "start of the NEXT local day" rather than
    `start + 24h`, which keeps DST days exact (23h in spring, 25h in autumn).

    ⚠️ To measure the day's LENGTH use `day_length()`, never `end - start`: CPython
    skips offset arithmetic when both operands share a tzinfo object (documented
    behaviour), so subtracting these two directly returns a flat 24h on DST days.
    """
    from datetime import datetime, time, timedelta
    d = on_date or today(user)
    zone = tz(user)
    start = datetime.combine(d, time.min, tzinfo=zone)
    end = datetime.combine(d + timedelta(days=1), time.min, tzinfo=zone)
    return start, end


def day_length(user, on_date=None):
    """The REAL elapsed length of a user-local day as a timedelta — 23h on spring
    forward, 25h on fall back, 24h otherwise. Computed in UTC precisely because
    same-tzinfo subtraction would hide the transition (see `day_bounds`)."""
    from zoneinfo import ZoneInfo
    start, end = day_bounds(user, on_date)
    utc = ZoneInfo("UTC")
    return end.astimezone(utc) - start.astimezone(utc)


def week_bounds(user, on_date=None):
    """(start_date, end_date) inclusive for the user-local week containing `on_date`.
    Delegates to the shared period resolver so "this week" means ONE thing platform-wide."""
    from apps.core.truth.periods import resolve_period
    p = resolve_period("this_week", on_date or today(user))
    return p.start, p.end


def resolve(user, phrase):
    """Resolve a natural date/period PHRASE against the USER's calendar.

    The one place a conversational expression becomes dates. `periods` does the parsing;
    this guarantees it is anchored to the user's local today rather than a server date.
    Returns a `Period`, or None when unparseable (callers reject honestly, never guess).
    """
    from apps.core.truth.periods import resolve_date_expression
    return resolve_date_expression(phrase, today(user))


def part_of_day(user):
    """The user-local execution phase ('morning'/'midday'/'evening'/'night') — so
    "this morning" / "tonight" mean the user's morning and night."""
    from apps.core.truth import daypart
    try:
        return daypart.phase_of_day(user)
    except Exception:
        logger.warning("calendar_day: daypart resolution failed", exc_info=True)
        return None


# ── the calendar-bound truth contract ────────────────────────────────────────
def stamp(user, on_date=None, *, authority=None, semantics="exact_date"):
    """The metadata a calendar-bound cached value MUST carry.

    Without this a `*_today` field is an undated claim: correct when written, silently
    wrong after midnight, and impossible for a reader to verify.
    """
    from django.utils import timezone as _dj_tz
    d = on_date or today(user)
    return {
        "represented_day": d.isoformat(),
        "timezone": tz_name(user),
        "generated_at": _dj_tz.now().isoformat(),
        "authority": authority or AUTHORITY,
        "semantics": semantics,
        "contract_version": CALENDAR_CONTRACT_VERSION,
    }


def day_freshness(user, stamped, *, on_date=None):
    """Does `stamped` still describe the day it claims? Facts only, never a fix.

    Accepts either a stamp dict (from `stamp()`) or a bare ISO date string, so both the
    full contract and a simple date-stamped field can be evaluated by ONE reader.
    Returns {day_freshness, represented_day, user_local_date, timezone[, reason]}.
    """
    expected = (on_date or today(user)).isoformat()
    zone = tz_name(user)
    represented = None
    if isinstance(stamped, dict):
        represented = stamped.get("represented_day")
        zone = stamped.get("timezone") or zone
    elif stamped:
        represented = str(stamped)

    if not represented:
        return {"day_freshness": UNKNOWN, "represented_day": None,
                "user_local_date": expected, "timezone": zone,
                "reason": ("This value does not record which calendar day it "
                           "describes, so it cannot be verified as today's.")}
    if str(represented) == expected:
        return {"day_freshness": CURRENT, "represented_day": str(represented),
                "user_local_date": expected, "timezone": zone}
    return {"day_freshness": STALE, "represented_day": str(represented),
            "user_local_date": expected, "timezone": zone,
            "reason": (f"These day-bound values describe {represented} ({zone}), NOT "
                       f"the user's today ({expected}). Do not report them as today's "
                       f"— retrieve the day you mean from the canonical authority.")}


def is_stale(user, stamped, *, on_date=None):
    """True when a calendar-bound value no longer describes the day it claims —
    including the UNKNOWN case, which must never be trusted as current."""
    return day_freshness(user, stamped, on_date=on_date)["day_freshness"] != CURRENT
