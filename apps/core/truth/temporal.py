"""
Platform helper: TEMPORAL SANITY.

Every timestamp Beth narrates must be validated first. A reading "from the future"
(recorded_at later than now) is a device-sync or clock-skew artifact — never a real
"current" value. Beth must surface that honestly ("that reading is timestamped in the
future — likely a sync/clock issue") instead of confidently reporting an impossible
time, or crashing to the emergency fallback.

Deterministic and domain-agnostic: any fact carrying a timestamp can be checked here
(glucose, BP, sleep, weight, …). Reused by the foundational facts and the SAE state.
"""
from datetime import datetime, timezone as _tz, timedelta

# Allowed clock skew between a device and the server before we call it "future".
FUTURE_TOLERANCE = timedelta(minutes=5)

OK = "ok"
FUTURE = "future"
UNPARSEABLE = "unparseable"

_FUTURE_MESSAGE = ("that reading is timestamped in the future — likely a device "
                   "sync or clock issue, so treat the time as unconfirmed")


def _parse(ts):
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None


def _aware(dt):
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=_tz.utc)


def validate_timestamp(ts, now):
    """Return {'verdict', 'ok', 'message'} for a timestamp vs `now`.

    verdict: 'ok' | 'future' | 'unparseable'. `ts` may be a datetime or ISO string.
    """
    dt = _parse(ts)
    if dt is None:
        return {"verdict": UNPARSEABLE, "ok": False, "message": ""}
    if _aware(dt) > _aware(now) + FUTURE_TOLERANCE:
        return {"verdict": FUTURE, "ok": False, "message": _FUTURE_MESSAGE}
    return {"verdict": OK, "ok": True, "message": ""}


def is_future(ts, now):
    return validate_timestamp(ts, now)["verdict"] == FUTURE
