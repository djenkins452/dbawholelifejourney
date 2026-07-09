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


def record_tool_call(
    user,
    *,
    kind,
    tool_name="",
    turn_id="",
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
