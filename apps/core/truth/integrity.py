# ==============================================================================
# File: apps/core/truth/integrity.py
# Platform capability (Layer 1): EVIDENCE INTEGRITY VALIDATION.
#
# A Chief of Staff, before presenting evidence, instinctively asks "does this
# evidence make sense?" — is the timestamp in the future? does "previous" actually
# precede "current"? am I about to repeat a value I can't stand behind? If the
# answer is "no", a CoS STOPS, INVESTIGATES, then reports — she never confidently
# presents evidence that contradicts itself.
#
# This is the deterministic, domain-agnostic gate for that instinct. It generalizes
# `apps.core.truth.temporal` (which validated ONE integrity class — a future
# timestamp) into the full family: TEMPORAL, SEQUENCE, and EVIDENCE integrity. It
# validates a CLAIM (the evidence object about to be presented) and returns a
# VERDICT that rides on the fact object, so EVERY consumer — the primary answer,
# every conversation-memory follow-up, the LLM phrasing prompt, the dashboard —
# reads the same verdict instead of re-deriving it (Architecture Law 1: Beth READS
# integrity, she never infers it).
#
# It lives in Layer 1, NOT in Beth, because integrity is a property of the TRUTH:
# the same invariants hold no matter who consumes the value. Put it in the narrator
# and every other consumer re-derives it and drifts — the exact failure mode this
# capability exists to prevent.
#
# Origin: Beth reported "current glucose 113 · previous 113 · recorded 11:07 AM"
# when the time was 10:11 AM — a duplicated predecessor with an impossible
# (future) timestamp, presented with full confidence and no investigation.
# ==============================================================================
from datetime import datetime, timezone as _tz

from apps.core.truth import temporal as _temporal
from apps.core.truth.freshness import STALE

# Verdict levels (weakest → strongest concern) -------------------------------
OK = "ok"              # present normally
SUSPECT = "suspect"    # something doesn't add up — hedge / investigate before trusting
IMPOSSIBLE = "impossible"  # self-contradictory — MUST investigate, never present as fact

# Violation codes, grouped by integrity class --------------------------------
# TEMPORAL
FUTURE_TIMESTAMP = "future_timestamp"
FUTURE_PREDECESSOR = "future_predecessor"
NEGATIVE_DURATION = "negative_duration"
# SEQUENCE
SEQUENCE_OUT_OF_ORDER = "sequence_out_of_order"
DUPLICATE_PREDECESSOR = "duplicate_predecessor"
MISSING_PREDECESSOR = "missing_predecessor"
# EVIDENCE
STALE_AS_CURRENT = "stale_as_current"
SOURCE_CONFLICT = "source_conflict"

_SEVERITY = {
    FUTURE_TIMESTAMP: IMPOSSIBLE,
    FUTURE_PREDECESSOR: IMPOSSIBLE,
    NEGATIVE_DURATION: IMPOSSIBLE,
    SEQUENCE_OUT_OF_ORDER: IMPOSSIBLE,
    DUPLICATE_PREDECESSOR: SUSPECT,
    MISSING_PREDECESSOR: SUSPECT,
    STALE_AS_CURRENT: SUSPECT,
    SOURCE_CONFLICT: SUSPECT,
}
_CLASS = {
    FUTURE_TIMESTAMP: "temporal", FUTURE_PREDECESSOR: "temporal",
    NEGATIVE_DURATION: "temporal",
    SEQUENCE_OUT_OF_ORDER: "sequence", DUPLICATE_PREDECESSOR: "sequence",
    MISSING_PREDECESSOR: "sequence",
    STALE_AS_CURRENT: "evidence", SOURCE_CONFLICT: "evidence",
}

# What Beth SAYS for each violation — honest, specific, in CoS voice. Never
# confidently reports the impossible value; names the inconsistency and the
# investigation. (The generic future-timestamp phrasing kept in lockstep with
# health_facts' existing temporal_warning so surfaced wording is stable.)
_DETAIL = {
    FUTURE_TIMESTAMP: ("the timestamp on this reading is later than the current "
                       "time, so I can't treat it as a real, current value yet"),
    FUTURE_PREDECESSOR: ("the earlier reading I'd compare against is itself "
                         "timestamped in the future, which shouldn't be possible"),
    NEGATIVE_DURATION: ("the start and end times on this don't make sense together "
                        "(it ends before it begins)"),
    SEQUENCE_OUT_OF_ORDER: ("the reading I'd call “previous” isn't actually "
                            "older than the current one, so the order is wrong"),
    DUPLICATE_PREDECESSOR: ("the “previous” reading is identical to the "
                            "current one with no earlier timestamp, so I don't "
                            "actually have a distinct prior reading to stand behind"),
    MISSING_PREDECESSOR: ("I don't actually have an earlier reading on hand to back "
                          "up a “previous” value"),
    STALE_AS_CURRENT: ("the most recent reading I have is older than it should be to "
                       "call it your current value"),
    SOURCE_CONFLICT: ("two sources disagree on this value, so I can't yet say which "
                      "one is right"),
}

_FUTURE_WARNING = ("the timestamp on this reading is in the future — likely a sync "
                   "or clock issue, so the time is unconfirmed")


def _now(now):
    if now is not None:
        return now
    from django.utils import timezone
    return timezone.now()


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


def _values_equal(a, b):
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()


def validate_evidence(claim, now=None):
    """Validate an evidence CLAIM against the integrity invariants. Deterministic,
    domain-agnostic, no LLM.

    `claim` describes the evidence Beth is about to present::

        {
          "value":            <the value>,
          "unit":             <str>,                 # optional, for messaging
          "recorded_at":      <datetime|iso|None>,   # when the value was recorded
          "freshness":        <freshness verdict|None>,
          "presented_as":     "current" | "previous" | None,
          "temporal_warning": <str|None>,            # already flagged upstream (SAE)
          "predecessor":      {"value":.., "recorded_at":..} | None,  # the "previous"
          "predecessor_role": "provenance" | "comparison",  # default "provenance":
                                                     # strict ordering/distinctness.
                                                     # "comparison" = a different-period
                                                     # reference; ordering is definitional,
                                                     # not validated.
          "predecessor_expected": <bool>,            # a prior reading was requested
          "start": <dt|iso>, "end": <dt|iso>,        # optional interval (durations)
          "sources": [ {"source":.., "value":..}, .. ] | None,
        }

    Returns::

        {"integrity": "ok"|"suspect"|"impossible", "ok": bool,
         "violations": [{"code","class","severity","message"}],
         "investigation": <deterministic CoS investigation sentence, or "">}
    """
    now = _aware(_now(now))
    claim = claim or {}
    violations = []

    def add(code):
        violations.append({"code": code, "class": _CLASS[code],
                           "severity": _SEVERITY[code], "message": _DETAIL[code]})

    value = claim.get("value")
    recorded_at = claim.get("recorded_at")
    predecessor = claim.get("predecessor")

    # ── TEMPORAL ────────────────────────────────────────────────────────────
    # An upstream layer (SAE) may have already dropped the impossible time and
    # left a temporal_warning — honour that as a future-timestamp violation so
    # the verdict is consistent whether we see the raw ts or the pre-flag.
    if claim.get("temporal_warning"):
        add(FUTURE_TIMESTAMP)
    elif recorded_at is not None and _temporal.is_future(recorded_at, now):
        add(FUTURE_TIMESTAMP)

    pred_ts = _parse((predecessor or {}).get("recorded_at")) if predecessor else None
    if pred_ts is not None and _temporal.is_future(pred_ts, now):
        add(FUTURE_PREDECESSOR)

    start, end = _parse(claim.get("start")), _parse(claim.get("end"))
    if start is not None and end is not None and _aware(end) < _aware(start):
        add(NEGATIVE_DURATION)

    # ── SEQUENCE ────────────────────────────────────────────────────────────
    # Two invariants with DIFFERENT scope. STRICT ORDERING ("previous" must
    # precede "current") is a PROVENANCE-only invariant: a COMPARISON reference
    # (yesterday, recent average) is intentionally a different period whose
    # ordering is definitional, and coarse day-level anchors would false-flag it
    # ("steps today vs yesterday", "glucose vs average" refused to answer). A
    # DUPLICATE predecessor (same value with NO distinct earlier timestamp — the
    # value wearing two hats) is a data-integrity defect in BOTH framings (the
    # production "previous 113 == current 113, no time" bug arrives via a
    # comparison), so it is validated regardless of role.
    role = claim.get("predecessor_role", "provenance")
    if predecessor is not None:
        p_val = predecessor.get("value")
        cur_ts = _parse(recorded_at)
        # "previous" must strictly precede "current" — PROVENANCE chains only.
        if role == "provenance" and pred_ts is not None and cur_ts is not None and \
                _aware(pred_ts) >= _aware(cur_ts):
            add(SEQUENCE_OUT_OF_ORDER)
        # A "previous" identical to current with no distinct earlier timestamp is
        # not a real prior reading — the current value wearing two hats (any role).
        elif _values_equal(p_val, value) and (
                pred_ts is None or (cur_ts is not None and
                                    _aware(pred_ts) == _aware(cur_ts))):
            add(DUPLICATE_PREDECESSOR)
    elif claim.get("predecessor_expected"):
        add(MISSING_PREDECESSOR)

    # ── EVIDENCE ────────────────────────────────────────────────────────────
    if claim.get("presented_as") == "current" and claim.get("freshness") == STALE:
        add(STALE_AS_CURRENT)

    sources = claim.get("sources")
    if sources and len([s for s in sources if s.get("value") is not None]) >= 2:
        vals = [float(s["value"]) for s in sources
                if s.get("value") is not None and _is_number(s["value"])]
        if len(vals) >= 2 and (max(vals) - min(vals)) > _source_tolerance(vals):
            add(SOURCE_CONFLICT)

    # ── Verdict ──────────────────────────────────────────────────────────────
    if any(v["severity"] == IMPOSSIBLE for v in violations):
        level = IMPOSSIBLE
    elif violations:
        level = SUSPECT
    else:
        level = OK
    return {
        "integrity": level,
        "ok": level == OK,
        "violations": violations,
        "investigation": _investigation(violations) if violations else "",
    }


def _is_number(x):
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _source_tolerance(vals):
    # A small relative tolerance so rounding/units jitter isn't a "conflict".
    return max(1.0, 0.02 * max(abs(v) for v in vals))


def _investigation(violations):
    """Compose the deterministic CoS investigation message: name what doesn't add
    up, and say Beth will confirm before giving a number — never restate the value
    as settled. (Mission voice: protect trust before protecting appearances.)"""
    if not violations:
        return ""
    # De-dup detail messages, most-severe class first, preserving order.
    seen, details = set(), []
    for v in sorted(violations, key=lambda x: 0 if x["severity"] == IMPOSSIBLE else 1):
        d = v["message"]
        if d not in seen:
            seen.add(d)
            details.append(d)
    body = details[0] if len(details) == 1 else \
        "; and ".join([details[0], ", ".join(details[1:])])
    return (
        "Before I answer, I'm seeing something in this that doesn't add up: "
        f"{body}. I don't want to give you a number I can't stand behind, so let "
        "me confirm whether this is stale data, a sync issue, or a bad record "
        "first — then I'll give you a straight answer."
    )


# ── Composition helper — attach the verdict to a fact dict ───────────────────

def attach(fact, now=None, *, predecessor=None, predecessor_expected=False,
           presented_as=None, sources=None):
    """Compute the integrity verdict for a fact dict and attach it as
    ``fact['integrity']``. Call at COMPOSITION (where value + timestamp + source
    are assembled) so every downstream consumer reads the verdict instead of
    re-checking. Domain-agnostic — a no-op verdict for a fact with nothing to
    validate.

    Back-compat: when the timestamp is in the future, keeps the existing
    behaviour (set ``temporal_warning`` and drop the impossible ``recorded_at``)
    so callers/tests relying on that contract are unchanged."""
    if not isinstance(fact, dict):
        return fact
    claim = {
        "value": fact.get("value"),
        "unit": fact.get("unit"),
        "recorded_at": fact.get("recorded_at") or fact.get("as_of"),
        "freshness": fact.get("freshness"),
        "temporal_warning": fact.get("temporal_warning"),
        "presented_as": presented_as or fact.get("presented_as"),
        "predecessor": predecessor if predecessor is not None
        else fact.get("predecessor"),
        "predecessor_role": fact.get("predecessor_role", "provenance"),
        "predecessor_expected": predecessor_expected or
        fact.get("predecessor_expected", False),
        "start": fact.get("start"), "end": fact.get("end"),
        "sources": sources if sources is not None else fact.get("sources"),
    }
    verdict = validate_evidence(claim, now)
    # Only carry the verdict when it matters — a sound fact stays lean (no key), so
    # composition adds zero payload to healthy truth; consumers use failed()/attach.
    if not verdict["ok"]:
        fact["integrity"] = verdict
        # Future-timestamp back-compat: flag + drop the impossible time.
        if any(v["code"] == FUTURE_TIMESTAMP for v in verdict["violations"]):
            if not fact.get("temporal_warning"):
                fact["temporal_warning"] = _FUTURE_WARNING
            fact.pop("recorded_at", None)
    return fact


def failed(fact):
    """True when a fact carries a non-OK integrity verdict (a consumer must
    investigate rather than confidently present)."""
    integ = (fact or {}).get("integrity") if isinstance(fact, dict) else None
    return isinstance(integ, dict) and not integ.get("ok", True)


def investigation_for(fact):
    """The investigation message for a failed fact (or '' when it passes)."""
    integ = (fact or {}).get("integrity") if isinstance(fact, dict) else None
    if isinstance(integ, dict) and not integ.get("ok", True):
        return integ.get("investigation") or ""
    return ""
