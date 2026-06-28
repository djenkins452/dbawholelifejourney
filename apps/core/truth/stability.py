"""
Platform capability: STABILITY (Architecture Law 5 — Stable Truth).

The same question, asked again within a window with unchanged data, must return the
same answer. Truth that flaps is untrustworthy even when each individual read is
"correct". This module makes stability *provable*: it derives a deterministic
SIGNATURE of a truth object's DATA (value / points / as-of — not the volatile
now-relative fields), so identical reads can be compared, and offers `verify_stable`
to assert a retriever does not drift across repeated reads.

Domain-agnostic; consumed by Current Truth objects, History series, and the
acceptance/regression gates (which back the `unstable_fact` critical rule).
"""
import hashlib
import json


def signature(*parts):
    """Deterministic sha256 over a canonical JSON encoding of `parts`."""
    blob = json.dumps(parts, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def current_signature(ct):
    """Signature of a CurrentTruth's DATA — domain/metric/presence/value/as_of.
    Excludes freshness & confidence (derived from 'now', not the underlying value)."""
    return signature("current", ct.domain, ct.metric, ct.present, ct.value,
                     ct.unit, ct.as_of)


def series_signature(hs):
    """Signature of a HistorySeries' DATA — domain/metric/range/points."""
    return signature("history", hs.domain, hs.metric,
                     hs.period.start, hs.period.end,
                     [(p.date, p.value) for p in hs.points])


def truth_signature(obj):
    """Signature of any supported truth object (CurrentTruth or HistorySeries)."""
    if hasattr(obj, "points") and hasattr(obj, "period"):
        return series_signature(obj)
    if hasattr(obj, "present") and hasattr(obj, "metric"):
        return current_signature(obj)
    return signature("raw", obj)


def verify_stable(retriever, *args, rounds=3, sig=truth_signature, **kwargs):
    """Call `retriever(*args, **kwargs)` `rounds` times and confirm every result has
    the same signature. Returns {"stable": bool, "signatures": [...], "rounds": n}.
    Use in regression/acceptance to prove a fact does not drift across reads."""
    sigs = [sig(retriever(*args, **kwargs)) for _ in range(rounds)]
    return {"stable": len(set(sigs)) == 1, "signatures": sigs, "rounds": rounds}
