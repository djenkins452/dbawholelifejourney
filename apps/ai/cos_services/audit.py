# ==============================================================================
# File: apps/ai/cos_services/audit.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tool-call audit recorder (WLJ ↔ model interface — Audit pillar)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
Tool-call audit recorder.

docs/WLJ_MODEL_INTERFACE_DESIGN.md §8 — the audit EXPLAINS, it does not reason. This
records what truth was provided, what actions were requested, what actually occurred,
and what response was returned — an append-only ledger for traceability, forensics,
and a golden-transcript test substrate. It is NOT a second AI judging the first.

Design rules:
* APPEND-ONLY. `record_tool_call` only ever creates a row.
* REQUEST-PATH-SAFE. The recorder NEVER raises and NEVER blocks a turn — a failed
  audit write must not break the conversation. It swallows and logs its own errors.
* JSON-safe + capped payloads (reuses cos_services.serialization).
"""

import logging

from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

# Keep audit payloads bounded so a huge tool result can't bloat the ledger.
_MAX_JSON_CHARS = 4000


def _bounded(value):
    """JSON-safe + size-bounded representation for storage."""
    safe = _jsonsafe(value if value is not None else {})
    try:
        import json
        if len(json.dumps(safe)) > _MAX_JSON_CHARS:
            return {"_truncated": True, "_preview": str(safe)[:_MAX_JSON_CHARS]}
    except (TypeError, ValueError):
        return {"_unserializable": str(safe)[:_MAX_JSON_CHARS]}
    return safe


# The evidence fields that make an audit row answer "what truth was provided?" rather
# than only "what was requested?". Deliberately narrow: scalars that describe the
# ANSWER and its provenance — never raw payloads, never lists of records, never prose.
_EVIDENCE_FIELDS = (
    "status", "value", "unit", "semantics", "requested_date", "user_local_date",
    "observed_on", "as_of", "for_date", "age_days", "exact", "freshness",
    "confidence", "authority", "source", "period", "start", "end", "count",
    "average", "total", "reason",
)
_MAX_EVIDENCE_FACTS = 8


def _evidence(payload):
    """Pull the bounded evidence SCALARS out of one truth payload.

    A nested container under an evidence name (e.g. an envelope's `value` holding a
    whole fact map) is not a scalar answer — it is handled by the per-fact pass, so it
    is skipped here rather than duplicated into the digest.
    """
    if not isinstance(payload, dict):
        return None
    ev = {k: payload[k] for k in _EVIDENCE_FIELDS
          if k in payload and not isinstance(payload[k], (dict, list))}
    return ev or None


def truth_digest(tool_name, args, envelope):
    """A structured digest of the truth ACTUALLY RETURNED, for the audit ledger.

    Records the returned status/value/unit, the requested date or period, the real
    observation date, the answering authority, and the exact-vs-carry-forward
    semantics — the evidence an incident review needs. Previously the digest for
    `get_foundational_health_facts` held only the requested `keys`, so the ledger could
    not show WHICH number was handed to the model (proven 2026-07-22). Bounded and
    JSON-safe; never raises.
    """
    try:
        out = {"tool": tool_name}
        for k in ("domain", "metric", "entity_type", "name", "subject", "period",
                  "start", "end", "keys", "section", "query"):
            if isinstance(args, dict) and args.get(k) not in (None, ""):
                out[k] = args[k]
        # Canonical envelope → payload under `value` (truth.envelope.make_envelope);
        # `data` and a bare payload are accepted for the other truth surfaces.
        payload = None
        if isinstance(envelope, dict):
            for key in ("value", "data"):
                if isinstance(envelope.get(key), dict):
                    payload = envelope[key]
                    break
        if payload is None:
            payload = envelope
        if isinstance(envelope, dict) and envelope.get("status"):
            out["envelope_status"] = envelope["status"]
        # Envelope-level provenance (freshness/confidence/source) PLUS the payload's own
        # scalars — the payload wins where both describe the answer.
        top = dict(_evidence(envelope) or {})
        top.update(_evidence(payload) or {})
        if top:
            out["evidence"] = top
        # A multi-fact payload (curated health facts) → one evidence entry per fact, so
        # the ledger shows every value the model received, not just the first.
        if isinstance(payload, dict):
            facts = {}
            for key, val in list(payload.items())[:40]:
                ev = _evidence(val)
                if ev:
                    facts[key] = ev
                if len(facts) >= _MAX_EVIDENCE_FACTS:
                    break
            if facts:
                out["facts"] = facts
        return out
    except Exception:  # pragma: no cover - the digest must never break a turn
        logger.warning("ToolCallLog: truth_digest failed tool=%s", tool_name,
                       exc_info=True)
        return {"tool": tool_name, "_digest_error": True}


def record_tool_call(
    user,
    *,
    kind,
    tool_name="",
    turn_id="",
    conversation_id="",
    surface="",
    args=None,
    result_status="",
    result_digest=None,
):
    """Append one audit row. Returns the created row, or None on any failure.

    NEVER raises — a failed audit write must not break the turn.
    """
    try:
        from apps.ai.models import ToolCallLog
        return ToolCallLog.objects.create(
            user=user,
            kind=kind,
            tool_name=(tool_name or "")[:64],
            turn_id=(turn_id or "")[:64],
            conversation_id=str(conversation_id or "")[:64],
            surface=(surface or "")[:32],
            args=_bounded(args),
            result_status=(result_status or "")[:32],
            result_digest=_bounded(result_digest),
        )
    except Exception:  # never break a turn on an audit failure
        logger.warning(
            "ToolCallLog: failed to record kind=%s tool=%s user=%s",
            kind, tool_name, getattr(user, "id", "?"), exc_info=True,
        )
        return None
