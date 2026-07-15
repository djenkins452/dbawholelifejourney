"""
Platform capability: LIFECYCLE TRUTH — the temporal dimension of the
**Truth Presentation Contract** (`docs/WLJ_VISUAL_TRUTH_CONTRACT.md`).

The Truth Presentation Contract has ONE governing rule with two dimensions:

    The customer must never be shown a state that claims more certainty than
    WLJ has actually established.

  * Dimension 1 — VISUAL truth (spatial): only real completion may LOOK complete.
    Enforced by `apps/core/tests/test_visual_truth_contract.py`.
  * Dimension 2 — LIFECYCLE truth (temporal, this module): a customer-facing
    status must represent the highest VERIFIED deterministic stage WLJ has
    established for asynchronous work — never the furthest stage it *initiated*,
    *enqueued*, or *expects* to reach.

This module is the ONE shared lifecycle vocabulary + the product RULE. It is pure
and deterministic: it INTERPRETS truth other subsystems already own (ingestion-run
counts, summary build times, freshness verdicts). It stores no state and owns no
new source of truth — it is NOT a parallel state machine.

It composes with `apps.core.truth.freshness`: the terminal CURRENT stage is exactly
the point at which the DERIVED layer's freshness verdict is `freshness.CURRENT`.

The vocabulary is CONCEPTUAL. Individual domains keep their own persisted status
enums (`HealthIngestionRun.status`, `CaptureEntry.status`, …) and map them onto
these stages when they speak to the customer — they are not forced into identical
enums.
"""

from apps.core.truth import freshness as _freshness

# ── Canonical customer-facing lifecycle stages ────────────────────────────────
# Customer-oriented, ordered from least to most established truth.
INITIATED = "initiated"   # the user's action was accepted; work is beginning
RECEIVED = "received"     # WLJ has custody of the input server-side (not just in transit)
PERSISTED = "persisted"   # canonical records written to the system of record
DERIVED = "derived"       # downstream computed layers rebuilt from the persisted truth
CURRENT = "current"       # the derived truth is readable AND up to date on the customer's surfaces

STAGES = (INITIATED, RECEIVED, PERSISTED, DERIVED, CURRENT)
_RANK = {s: i for i, s in enumerate(STAGES)}

# ── Qualifiers — modify a stage; they are NOT points on the line ──────────────
PARTIAL = "partial"   # the stage was reached for SOME items, not all
FAILED = "failed"     # the stage could not complete; the reason is known
STALE = "stale"       # a later stage is READABLE but reflects an OLDER persisted truth

BLOCKING_QUALIFIERS = (PARTIAL, FAILED, STALE)

# Customer-facing claim keys a surface may present (facts, not prose — the surface
# or the model turns these into words).
CLAIM_UP_TO_DATE = "up_to_date"   # earned terminal state — everything shown reflects this
CLAIM_SAVED = "saved"             # durably persisted; derived layers may still be catching up
CLAIM_UPDATING = "updating"       # saved, but derived layers are rebuilding / stale
CLAIM_PARTIAL = "partial"         # some items succeeded, some did not
CLAIM_FAILED = "failed"           # nothing usable was established
CLAIM_RECEIVED = "received"       # arrived, not yet persisted
CLAIM_WORKING = "working"         # in flight, outcome not yet established


def rank(stage):
    """Ordinal of a stage (higher = more established). Unknown → -1."""
    return _RANK.get(stage, -1)


def may_claim_complete(stage, *, qualifier=None):
    """THE product rule (Dimension 2).

    A customer-facing surface may present a COMPLETION / "up to date" claim ONLY
    when verified truth has reached CURRENT with no blocking qualifier. PARTIAL,
    FAILED and STALE each forbid a completion claim — they must be shown as
    themselves, never rounded up to "complete".
    """
    if qualifier in BLOCKING_QUALIFIERS:
        return False
    return rank(stage) >= _RANK[CURRENT]


def may_claim_saved(stage, *, qualifier=None):
    """The weaker, still-honest claim: the data is durably SAVED (PERSISTED) even
    if derived layers have not caught up. FAILED forbids it entirely; PARTIAL is
    allowed but the caller MUST render it as partial (see `claim_key`)."""
    if qualifier == FAILED:
        return False
    return rank(stage) >= _RANK[PERSISTED]


def claim_key(stage, *, qualifier=None):
    """Map a (stage, qualifier) to the single honest customer-facing claim key.

    Never returns a claim more optimistic than the verified stage allows. This is
    the function every surface routes through so "complete" cannot be assembled
    from an initiation or transmission event.
    """
    if qualifier == FAILED and rank(stage) < _RANK[PERSISTED]:
        return CLAIM_FAILED
    if qualifier == PARTIAL:
        return CLAIM_PARTIAL
    if qualifier == STALE:
        return CLAIM_UPDATING
    if may_claim_complete(stage, qualifier=qualifier):
        return CLAIM_UP_TO_DATE
    if may_claim_saved(stage, qualifier=qualifier):
        return CLAIM_SAVED
    if rank(stage) >= _RANK[RECEIVED]:
        return CLAIM_RECEIVED
    return CLAIM_WORKING


def sync_lifecycle(*, received, created, updated, skipped, failed, derived=None):
    """Interpret an ingestion-run-style count set into the highest VERIFIED stage
    + qualifier. Consumes counts the ingest endpoint ALREADY computed — it never
    re-runs ingestion.

    Args:
        received: total metrics the server took custody of this run.
        created/updated/skipped/failed: per-run outcome counts.
        derived: optional freshness verdict (`freshness.*`) for the derived layer.
            When it is `freshness.CURRENT` and the run is otherwise clean, the run
            may advance to the CURRENT stage. Left None (the common case for a
            just-finished sync), the run caps at PERSISTED — the honest "Saved"
            terminal claim, because derived freshness is not yet known.

    Returns facts only:
        {stage, qualifier, saved, skipped, failed, total, claim}
    """
    received = int(received or 0)
    created = int(created or 0)
    updated = int(updated or 0)
    skipped = int(skipped or 0)
    failed = int(failed or 0)
    saved = created + updated

    if received == 0:
        stage, qualifier = INITIATED, (FAILED if failed else None)
    elif saved == 0 and failed > 0:
        # Arrived, nothing persisted, and there were hard failures.
        stage, qualifier = RECEIVED, FAILED
    else:
        # Something durable happened: either new/updated rows, or skips (dedup =
        # "already persisted, no change needed"). The truth is PERSISTED.
        stage = PERSISTED
        qualifier = PARTIAL if failed > 0 else None
        if qualifier is None and derived is not None:
            if derived == _freshness.CURRENT:
                stage = CURRENT
            elif derived in (_freshness.STALE, _freshness.PENDING, _freshness.PARTIAL):
                stage, qualifier = DERIVED, STALE

    return {
        "stage": stage,
        "qualifier": qualifier,
        "saved": saved,
        "skipped": skipped,
        "failed": failed,
        "total": received,
        "claim": claim_key(stage, qualifier=qualifier),
    }


def derived_state(*, persisted_at, derived_at):
    """Is a DERIVED artifact current with the PERSISTED truth it summarizes?

    The reusable freshness check for any "raw data persisted → summary/score/
    intelligence rebuilt" surface (Body Intelligence, scores, executive summaries).
    Facts only; composes with `freshness` verdicts.

        derived_at is None                → DERIVED not built yet   → PENDING
        persisted_at is newer than derived → derived lags behind    → STALE (updating)
        otherwise                          → up to date             → CURRENT

    Args:
        persisted_at: timestamp of the most recent persistence of the underlying
            truth (e.g. latest ingestion run / latest canonical entry). May be None.
        derived_at: timestamp the derived artifact was last (re)built. May be None.

    Returns: {stage, qualifier, verdict, persisted_at, derived_at}
    """
    if derived_at is None:
        return {
            "stage": PERSISTED, "qualifier": None,
            "verdict": _freshness.PENDING,
            "persisted_at": persisted_at, "derived_at": None,
        }
    if persisted_at is not None and persisted_at > derived_at:
        return {
            "stage": DERIVED, "qualifier": STALE,
            "verdict": _freshness.STALE,
            "persisted_at": persisted_at, "derived_at": derived_at,
        }
    return {
        "stage": CURRENT, "qualifier": None,
        "verdict": _freshness.CURRENT,
        "persisted_at": persisted_at, "derived_at": derived_at,
    }
