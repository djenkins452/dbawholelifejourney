# ==============================================================================
# File: apps/core/truth/envelope.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The canonical truth-tool envelope (WLJ ↔ model interface, Pillar 1)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
Truth Envelope — the single shape every WLJ truth answer wears (Pillar 1).

docs/WLJ_MODEL_INTERFACE_DESIGN.md §Pillar 1 / §3.2 (truth envelope).

Every deterministic fact WLJ hands the conversational model — in the standing
context or from a truth tool — is wrapped in ONE shape so the model always receives
provenance alongside the value:

    {
      "value":      <composed, human-usable value or None>,
      "freshness":  current | stale | pending | partial | missing,   (Law 1)
      "confidence": high | medium | low | none,                       (Law 2)
      "source":     <provenance string>,
      "as_of":      <ISO timestamp the value is true as of, or None>,
      "status":     ok | pending | empty | insufficient_evidence | missing | error,
      # optional: "unit", "detail", "investigation", "reason"
    }

`insufficient_evidence` / `missing` / `pending` / `empty` are FIRST-CLASS answers —
never substitute a plausible value (Laws 0/1/2). This module is REUSE-ONLY: it
composes the existing `freshness` / `confidence` / `integrity` vocabulary and the
`CurrentTruth` object. It performs no reasoning and calls no LLM.
"""

from apps.core.truth import confidence as _conf
from apps.core.truth import freshness as _fresh
from apps.core.truth import integrity as _integrity

# -- status vocabulary --------------------------------------------------------
STATUS_OK = "ok"
STATUS_PENDING = "pending"                       # asked-for now, not arrived yet
STATUS_EMPTY = "empty"                            # a valid empty result (no rows)
STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # cannot answer honestly
STATUS_MISSING = "missing"                        # no value at all
STATUS_ERROR = "error"                            # retrieval/compute failure

# Confidence ordering for deterministic downgrades.
_CONF_RANK = {_conf.NONE: 0, _conf.LOW: 1, _conf.MEDIUM: 2, _conf.HIGH: 3}
_RANK_CONF = {v: k for k, v in _CONF_RANK.items()}


def _min_confidence(a: str, b: str) -> str:
    """Weakest of two confidence verdicts wins."""
    return _RANK_CONF[min(_CONF_RANK.get(a, 0), _CONF_RANK.get(b, 0))]


def _derive_status(value_present: bool, freshness: str) -> str:
    if value_present and freshness in (_fresh.CURRENT, _fresh.STALE, _fresh.PARTIAL):
        return STATUS_OK
    if freshness == _fresh.PENDING:
        return STATUS_PENDING
    if freshness == _fresh.MISSING:
        return STATUS_MISSING
    return STATUS_INSUFFICIENT_EVIDENCE


def make_envelope(
    value,
    *,
    freshness=_fresh.CURRENT,
    confidence=None,
    source="",
    as_of=None,
    status=None,
    unit=None,
    detail=None,
    investigation="",
    reason="",
) -> dict:
    """Build a canonical truth envelope. Confidence and status are derived
    deterministically when not supplied."""
    present = value is not None
    if confidence is None:
        confidence = (
            _conf.combine(
                _conf.confidence_from_freshness(freshness),
                _conf.confidence_from_source(source),
            )
            if present
            else _conf.NONE
        )
    if status is None:
        status = _derive_status(present, freshness)

    env = {
        "value": value,
        "freshness": freshness,
        "confidence": confidence,
        "source": source,
        "as_of": as_of,
        "status": status,
    }
    if unit:
        env["unit"] = unit
    if detail:
        env["detail"] = dict(detail)
    if investigation:
        env["investigation"] = investigation
    if reason:
        env["reason"] = reason
    return env


# -- honest-absence constructors (first-class answers) ------------------------
def pending(*, source="", reason="") -> dict:
    return make_envelope(None, freshness=_fresh.PENDING, source=source,
                         status=STATUS_PENDING, reason=reason)


def missing(*, source="", reason="") -> dict:
    return make_envelope(None, freshness=_fresh.MISSING, source=source,
                         status=STATUS_MISSING, reason=reason)


def insufficient_evidence(*, source="", reason="", detail=None) -> dict:
    return make_envelope(None, freshness=_fresh.MISSING, source=source,
                         status=STATUS_INSUFFICIENT_EVIDENCE, reason=reason,
                         detail=detail)


def empty(*, source="", reason="") -> dict:
    """A valid, deterministically-empty result (e.g. a search with no matches)."""
    return make_envelope([], freshness=_fresh.CURRENT, confidence=_conf.HIGH,
                         source=source, status=STATUS_EMPTY, reason=reason)


def error(message: str, *, source="") -> dict:
    """A retrieval/compute failure — reported as a failure, never as AI-unavailable
    (Law 4)."""
    return make_envelope(None, freshness=_fresh.MISSING, confidence=_conf.NONE,
                         source=source, status=STATUS_ERROR, reason=message)


# -- adapter: existing CurrentTruth → envelope --------------------------------
def from_current_truth(ct) -> dict:
    """Map an `apps.core.truth.current.CurrentTruth` into the canonical envelope.
    Reuses the object's already-composed value/freshness/confidence/source."""
    if not getattr(ct, "present", False):
        fresh = getattr(ct, "freshness", _fresh.MISSING)
        status = STATUS_PENDING if fresh == _fresh.PENDING else STATUS_MISSING
        return make_envelope(None, freshness=fresh, confidence=_conf.NONE,
                             source=getattr(ct, "source", ""), status=status,
                             reason=getattr(ct, "reason", ""))
    return make_envelope(
        ct.value,
        freshness=ct.freshness,
        confidence=ct.confidence,       # already composed in CurrentTruth
        source=ct.source,
        as_of=ct.as_of,
        unit=ct.unit,
        detail=(ct.detail or None),
    )


# -- integrity gate -----------------------------------------------------------
def apply_integrity(envelope: dict, claim: dict) -> dict:
    """Run the evidence-integrity check over a claim and fold its verdict into the
    envelope BEFORE exposure (Contract §3.2). Returns a NEW envelope:

    * IMPOSSIBLE (self-contradictory) → status=insufficient_evidence, confidence=none,
      value withheld — never presented as fact; carries the investigation text.
    * SUSPECT → confidence downgraded to at most `low`; carries the investigation text.
    * OK → unchanged.
    """
    verdict = _integrity.validate_evidence(claim)
    level = verdict.get("integrity", _integrity.OK)
    investigation = verdict.get("investigation", "") or ""

    if level == _integrity.OK:
        return dict(envelope)

    out = dict(envelope)
    if investigation:
        out["investigation"] = investigation
    out["integrity"] = level

    if level == _integrity.IMPOSSIBLE:
        out["value"] = None
        out["confidence"] = _conf.NONE
        out["status"] = STATUS_INSUFFICIENT_EVIDENCE
    else:  # SUSPECT — keep the value but hedge hard
        out["confidence"] = _min_confidence(out.get("confidence", _conf.NONE), _conf.LOW)
    return out
