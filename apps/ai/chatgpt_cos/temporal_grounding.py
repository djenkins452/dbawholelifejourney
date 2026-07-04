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


# ── Clarification vs Trust Challenge ───────────────────────────────────────
#
# A production-ready CoS ANSWERS a simple question before escalating. Asking
# "which date / which record / what source / when recorded" is a CLARIFICATION —
# answer it directly, no mode change. Only when the user CHALLENGES the
# correctness / freshness / provenance / trustworthiness of the prior claim does
# the conversation's PURPOSE change → VERIFY mode. Keep these disjoint.

# CLARIFICATION — asking FOR a detail about the prior statement. Answer directly.
_CLARIFICATION_CUES = (
    "what date", "which date", "what day", "which day", "what date are you",
    "which record", "what record", "which sleep record", "which night",
    "what night", "which last night", "referring to", "are you referring",
    "what are you calling", "what timeframe", "which timeframe", "what window",
    "what time window", "when was it recorded", "when was that recorded",
    "when was this recorded", "when recorded", "when was it synced",
    "when was this synced", "when did it sync", "when synced", "last sync",
    "when was this synchronized", "when synchronized", "what source",
    "what's the source", "whats the source", "which source", "where's that from",
    "where is that from", "where does that come from", "how old is", "how old's",
    "how recent", "how many days old",
    # PROVENANCE — "where did that number come from?" / "what's that based on?".
    # Answer the SOURCE directly; disjoint from the trust cues below.
    "come from", "where did that", "where did the", "where did this",
    "that based on", "this based on",
)

# TRUST CHALLENGE — questioning the CORRECTNESS / FRESHNESS / PROVENANCE /
# TRUSTWORTHINESS of the prior claim. Only THIS enters VERIFY mode.
_TRUST_CHALLENGE_CUES = (
    "is that stale", "is it stale", "is the data stale", "is that old", "how stale",
    "your data is stale", "that data is stale", "i think your data is stale",
    "i think the data is stale", "data might be stale", "i think that's stale",
    "are you sure", "you sure", "are you certain", "you certain", "how confident",
    "are you confident", "how do you know", "how would you know", "prove it",
    "prove that", "what's your evidence", "what is your evidence",
    "show me the evidence", "verify that", "can you verify", "double check",
    "double-check", "sanity check", "that can't be right", "that cant be right",
    "that's wrong", "thats wrong", "that's not right", "thats not right",
    "i don't believe", "i dont believe", "i don't think that's right",
    "i dont think that's right", "that doesn't sound right", "that doesnt sound right",
    "that seems wrong", "is that reliable", "how reliable", "is that accurate",
    "is that correct", "is that current", "is this current", "up to date",
    "was that actually", "is that actually", "actually last night or",
    "or just the most recent", "just the most recent record", "the most recent record",
    "are you sure you're looking at", "sure you're looking at", "sure that's today",
    "sure it's today", "based on what", "says who", "where did you get",
    "where'd you get", "where are you getting",
    # TEMPORAL IMPOSSIBILITY — the user asserts a timestamp/value can't be true given
    # the actual time. This is a challenge to the evidence → VERIFY / evidence integrity.
    "that's impossible", "thats impossible", "that is impossible", "impossible",
    "it's only", "it is only", "its only", "but it's only", "but its only",
    "how could it be", "how can it be", "in the future",
    "future timestamp", "timestamp is in the future", "that timestamp",
    "can't be later", "cant be later", "hasn't happened yet", "hasnt happened yet",
)


def is_clarification_question(message):
    """The user is asking FOR a detail about Beth's prior statement (which date /
    record / source / when recorded). Answer it directly — NOT a mode change."""
    n = (message or "").strip().lower()
    return bool(n) and any(c in n for c in _CLARIFICATION_CUES)


def is_trust_challenge(message):
    """The user is CHALLENGING the correctness/freshness/provenance/trustworthiness
    of Beth's prior claim — the conversation's PURPOSE has changed. Only this
    enters VERIFY mode. A trust challenge takes precedence over a clarification."""
    n = (message or "").strip().lower()
    return bool(n) and any(c in n for c in _TRUST_CHALLENGE_CUES)


# The subset of trust challenges that dispute a TIMESTAMP as temporally impossible
# ("that's impossible", "it's only 10:11", "that's in the future", "how could it be
# 11:07 when it's 10:11"). These get a TIMESTAMP RECONCILIATION against the real clock.
_TEMPORAL_IMPOSSIBILITY_CUES = (
    "impossible", "it's only", "it is only", "its only", "in the future",
    "future timestamp", "timestamp is in the future", "how could it be",
    "how can it be", "can't be later", "cant be later", "hasn't happened yet",
    "hasnt happened yet", "that timestamp",
)


def is_temporal_impossibility_challenge(message):
    """A trust challenge specifically disputing a timestamp as impossible/in the
    future — answered by reconciling the referenced record's time with the clock."""
    n = (message or "").strip().lower()
    return bool(n) and any(c in n for c in _TEMPORAL_IMPOSSIBILITY_CUES)


# Backward-compatible name (now narrowed to genuine challenges only).
is_temporal_trust_challenge = is_trust_challenge


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
        return _result(_verify_sleep(user, fact, message), lane="trust_verification")

    return _result(_verify_generic_fact(user, fact, message),
                   lane="trust_verification")


def _reconcile_timestamp(user, fact):
    """Reconcile a referenced record's recorded time with the real clock, for a
    temporal-impossibility challenge. Cites the record's time AND now, so Beth
    addresses the user's specific objection instead of a generic 'that's based on…'.
    Returns None when there is no timestamp to reconcile (caller routes on)."""
    from datetime import datetime
    ra = fact.get("recorded_at") or fact.get("as_of")
    if not ra:
        return None
    try:
        dt = datetime.fromisoformat(str(ra))
        ctx = now_context(user)
        tz = ctx["now"].tzinfo
        dt = dt.astimezone(tz) if dt.tzinfo else dt
    except Exception:
        return None
    when = f"{_fmt_date_long(dt.date())} at {_fmt_time(dt)}"
    now_s = f"{ctx['time_12h']} on {ctx['date_long']}"
    if dt <= ctx["now"]:
        # The record is in the PAST relative to now — the impossibility the user sees
        # is a clock/timezone mismatch, not a real future reading. Reconcile plainly.
        return (f"Let me reconcile that. The reading I referenced was recorded {when}, "
                f"and right now it's {now_s} — so its timestamp is in the past, not the "
                "future. If it looks off on your end, that's almost always a device "
                "clock or timezone mismatch between your app and the record. Want me to "
                "re-check the source directly?")
    # Genuinely in the future (defensive — integrity should have already caught it):
    # do NOT stand behind it; investigate.
    from apps.core.truth import integrity as _integrity
    v = _integrity.validate_evidence({"value": fact.get("value"), "recorded_at": ra},
                                     ctx["now"])
    return v.get("investigation") or (
        f"That timestamp reads {when}, which is later than right now ({now_s}) — that "
        "shouldn't be possible, so I won't stand behind it until I've checked whether "
        "it's a sync or clock issue.")


def _verify_generic_fact(user, fact, message):
    """Present the EVIDENCE behind a grounded fact — source, record date,
    freshness — with honest uncertainty. Never restates the claim as settled."""
    parts = ["Fair question — here's what that's based on."]
    if fact.get("source"):
        parts.append(f"Source: {fact['source']}.")
    fd = fact.get("for_date") or fact.get("record_date")
    if fd:
        parts.append(f"The record is dated {fd}.")
    if fact.get("window"):
        parts.append(f"I'm treating it as your {fact['window']}.")
    fr = fact.get("freshness")
    if fr == "stale":
        parts.append("I've flagged it as not fully current — treat it as the most "
                     "recent I have, not necessarily the latest.")
    elif fr in ("pending", "missing"):
        parts.append("I don't have a confirmed current value — treat it as unconfirmed.")
    elif fr == "current":
        parts.append("It's the most recent reading I have.")
    return " ".join(parts)


def verify_last_claim(user, last, message):
    """VERIFY MODE — the conversation has become a TRUST INVESTIGATION. Prove the
    EVIDENCE behind Beth's LAST assertion (source · record · timestamp · freshness),
    acknowledge uncertainty honestly, and NEVER restate the claim as settled. Works
    on WHATEVER Beth last asserted — a structured fact, a grounded temporal fact,
    or an ungrounded narrative claim. Returns a result dict, or None only when
    there is no prior assertion at all (so the caller routes on)."""
    last = last or {}
    # A challenge to GENERAL/EXTERNAL knowledge is not a personal-data trust
    # investigation — don't verify general facts as "your tracked data". Let the
    # general lanes / tool loop handle it.
    if (last.get("lane") or "") in ("general_conversation", "general_continuity"):
        return None
    answer = (last.get("answer") or "").strip()
    fact = last.get("fact") or (last.get("active_subject") or {}).get("fact") or {}
    fk = (last.get("fact_key") or fact.get("key") or "")
    low = answer.lower()

    # EVIDENCE INTEGRITY FIRST: if the referenced reading itself is self-contradictory
    # (an impossible/future timestamp), a challenge like "that's impossible, it's only
    # 10:11" is CORRECT — do not defend the value, investigate it.
    from apps.core.truth import integrity as _integrity
    if _integrity.failed(fact):
        return _result(_integrity.investigation_for(fact), lane="trust_verification")

    # TEMPORAL IMPOSSIBILITY: the user says the timestamp can't be true given the
    # actual time. Reconcile the referenced record's recorded time against the real
    # clock — cite both, and explain a genuine future time or a clock/tz mismatch.
    if is_temporal_impossibility_challenge(message):
        rec = _reconcile_timestamp(user, fact)
        if rec:
            return _result(rec, lane="trust_verification")

    # Sleep / "last night" claims → verify against the canonical sleep record
    # (works even if the prior turn recorded no structured fact — it reads the
    # record directly, so an ungrounded narrative claim is still provable).
    if fk.startswith("sleep") or "last night" in low or \
            ("sleep" in low and ("hour" in low or "slept" in low)):
        return _result(_verify_sleep(user, fact, message), lane="trust_verification")

    # Any other grounded fact carrying temporal/source metadata → present it.
    if fact.get("for_date") or fact.get("record_date") or fact.get("recorded_at") \
            or fact.get("freshness") or fact.get("source"):
        return _result(_verify_generic_fact(user, fact, message),
                       lane="trust_verification")

    # An UNGROUNDED narrative claim → be honest about the evidence, acknowledge the
    # mode shift, and do NOT restate the claim as if it were settled.
    if answer:
        snippet = answer if len(answer) <= 140 else answer[:137].rstrip() + "…"
        return _result(
            "Fair question — let me be straight about the evidence rather than just "
            f"restating it. I told you “{snippet}” from your tracked data, but I "
            "can't point to the exact record behind it right now, so please treat it "
            "as unconfirmed until I can show you the specific reading. Want me to pull "
            "the source record?", lane="trust_verification")
    return None


def answer_clarification(user, last, message):
    """ANSWER a clarification question about Beth's prior statement DIRECTLY (the
    date / record / source / timestamp) — a normal answer, NOT a trust
    investigation. A world-class CoS just answers 'which date?' before escalating.
    Returns a result dict (lane 'clarification_answer'), or None if there's nothing
    groundable to clarify (so the caller routes on)."""
    last = last or {}
    if (last.get("lane") or "") in ("general_conversation", "general_continuity"):
        return None
    answer = (last.get("answer") or "").strip()
    fact = last.get("fact") or (last.get("active_subject") or {}).get("fact") or {}
    fk = (last.get("fact_key") or fact.get("key") or "")
    low = answer.lower()
    n = (message or "").strip().lower()
    if fk.startswith("sleep") or "last night" in low or \
            ("sleep" in low and ("hour" in low or "slept" in low)):
        return _result(_clarify_sleep(user, fact, n), lane="clarification_answer")
    if (fact.get("for_date") or fact.get("record_date") or fact.get("provenance")
            or fact.get("recorded_at") or fact.get("as_of")
            or _clean_source(fact.get("source"))):
        txt = _clarify_generic(user, fact, n)
        if txt:
            return _result(txt, lane="clarification_answer")
    return None


def _clarify_sleep(user, fact, n):
    rec = _latest_sleep_record(user)
    ctx = now_context(user)
    d = None
    if rec and rec.get("sleep_date"):
        d = rec["sleep_date"]
    elif fact.get("for_date"):
        try:
            d = date.fromisoformat(fact["for_date"])
        except Exception:
            d = None
    if any(c in n for c in ("recorded", "sync", "synchron")):
        if rec and rec.get("recorded_at"):
            when = _fmt_date_long(rec["recorded_at"].astimezone(ctx["now"].tzinfo).date())
            t = _fmt_time(rec["recorded_at"].astimezone(ctx["now"].tzinfo))
            src = rec.get("source") or "your tracker"
            return f"It came in from {src}, recorded {when} at {t}."
        return "I don't have an exact recording time saved for that one."
    if any(c in n for c in ("source", "where", "from")):
        src = (rec or {}).get("source") or fact.get("source") or "your sleep tracker"
        if d:
            return (f"It's from {src} — your sleep record for the night ending "
                    f"{_fmt_date_long(d)}.")
        return f"It's from {src}."
    if any(c in n for c in ("how old", "how recent", "days old")):
        if d:
            days = (ctx["today"] - d).days
            age = "last night" if days <= 1 else f"{days} days old"
            return f"It's your sleep record for {_fmt_date_long(d)} — {age}."
        return "I can't confirm how recent that record is right now."
    # Default: which date / record / "referring to".
    if d:
        return (f"The night ending {_fmt_date_long(d)} — that's your most recent "
                "sleep record.")
    return "I don't have a specific dated sleep record to point to right now."


def _clean_source(source):
    """The human-facing source, ignoring internal pipeline debug strings
    ('SAE.health.latest_glucose') which must never be shown as provenance."""
    if not source or str(source).startswith("SAE."):
        return None
    return source


def _clarify_generic(user, fact, n):
    """Answer a PROVENANCE / clarification question about a generic (non-sleep) fact —
    e.g. a glucose reading: its source and when it was recorded. Answers the
    SOURCE/timestamp, never restates the value."""
    fd = fact.get("for_date") or fact.get("record_date")
    src = fact.get("provenance") or _clean_source(fact.get("source"))
    ra = fact.get("recorded_at") or fact.get("as_of")
    when = None
    if ra:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(str(ra))
            ctx = now_context(user)
            tz = ctx["now"].tzinfo
            dt = dt.astimezone(tz) if dt.tzinfo else dt
            when = f"{_fmt_date_long(dt.date())} at {_fmt_time(dt)}"
        except Exception:
            when = None
    provenance_asked = any(c in n for c in ("source", "where", "from", "come from",
                                            "based on", "get that", "get it"))
    if provenance_asked or src or when:
        if src and when:
            return f"That's from {src}, recorded {when}."
        if src:
            return f"That's from {src}" + (f", dated {fd}." if fd else ".")
        if when:
            return f"That reading was recorded {when}."
    if fd:
        return f"That's the record dated {fd}."
    return None


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
