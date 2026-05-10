"""
Chat Snapshot Artifact (B1 — flag-gated observability).

Captures a single per-request artifact tying together what the LLM saw
and what the system computed, so divergences can be debugged after the
fact.

Behind the feature flag `WLJ_CHAT_SNAPSHOTS_ENABLED`. When the flag is
unset or False, `dump_chat_snapshot` returns immediately — zero
overhead. When enabled, writes a single JSON file under
LOG_DIR/chat_snapshots/<YYYY-MM-DD>/<request_id>.json.

Schema (stable):

    {
      "request_id": str,
      "user_id": int,
      "timestamp": ISO8601 UTC,
      "user_message": str,
      "prompt_sections": [
        {"tier": str, "title": str, "line_count": int, "content_hash": str}
      ],
      "execution_snapshot": {...},
      "selector_outputs": {"execution": {...}, "risk": {...}, "fix": {...}},
      "rollup_summaries": {"domains": {...}, "medications": {...}},
      "contradictions": [...],
      "narration_validations": {...},
      "llm_response": {"text": str, "model": str, "duration_ms": int}
    }

NOT a separate platform. NOT a database. One JSON file per request,
auto-pruned by an external cron after 24 h.
"""

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────

_TIER_HEADER_RE = re.compile(r"^\[TIER:([a-z_]+)\]\s*(.*)$", re.MULTILINE)


def _is_enabled() -> bool:
    return bool(getattr(settings, "WLJ_CHAT_SNAPSHOTS_ENABLED", False))


def _snapshot_dir() -> Path:
    base = getattr(settings, "LOG_DIR", None) or getattr(settings, "BASE_DIR", ".")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = Path(str(base)) / "chat_snapshots" / today
    path.mkdir(parents=True, exist_ok=True)
    return path


def _hash(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:12]


def parse_prompt_sections(prompt_text: str):
    """Walk a rendered system prompt and return a list of section
    summaries: {tier, title, line_count, content_hash}.

    Only sections with explicit [TIER:...] headers are listed; the
    Narration Contract treats untagged content as 'contextual' by
    default (see narration_contract.py preamble).
    """
    if not prompt_text:
        return []
    sections = []
    matches = list(_TIER_HEADER_RE.finditer(prompt_text))
    for i, m in enumerate(matches):
        tier = m.group(1)
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(prompt_text)
        body = prompt_text[start:end]
        sections.append({
            "tier": tier,
            "title": title,
            "line_count": body.count("\n"),
            "content_hash": _hash(body),
        })
    return sections


def extract_tier_blob(prompt_text: str, tier: str) -> str:
    """Return the concatenation of all sections of a given tier from
    the rendered prompt, including their content. Used by the
    narration validator to look up canonical / rollup evidence."""
    if not prompt_text:
        return ""
    chunks = []
    matches = list(_TIER_HEADER_RE.finditer(prompt_text))
    for i, m in enumerate(matches):
        if m.group(1) != tier:
            continue
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(prompt_text)
        chunks.append(prompt_text[start:end])
    return "\n".join(chunks)


# ── Public API ──────────────────────────────────────────────────────

def new_request_id() -> str:
    return uuid.uuid4().hex


def dump_chat_snapshot(payload: dict) -> str:
    """Persist a chat-turn snapshot. Returns the file path on success,
    empty string otherwise.

    No-op (returns "") when WLJ_CHAT_SNAPSHOTS_ENABLED is False.
    """
    if not _is_enabled():
        return ""
    try:
        request_id = payload.get("request_id") or new_request_id()
        payload.setdefault("request_id", request_id)
        payload.setdefault(
            "timestamp", datetime.now(timezone.utc).isoformat(),
        )
        out_dir = _snapshot_dir()
        path = out_dir / f"{request_id}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, default=str, indent=2)
        return str(path)
    except Exception:
        # Snapshot is observability — must NEVER fail a chat turn.
        logger.warning(
            "CHAT_SNAPSHOT dump failed user=%s",
            payload.get("user_id"),
            exc_info=True,
        )
        return ""


def build_snapshot_payload(
    *,
    request_id: str,
    user_id: int,
    user_message: str,
    rendered_prompt: str,
    execution_state: dict,
    selector_outputs: dict,
    rollup_summaries: dict,
    contradictions: list,
    narration_validations: dict,
    llm_response_text: str,
    llm_model: str,
    llm_duration_ms: int,
) -> dict:
    """Pure builder — produce the snapshot dict without writing it."""
    return {
        "request_id": request_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_message": user_message,
        "prompt_sections": parse_prompt_sections(rendered_prompt),
        "execution_snapshot": _safe_jsonify(execution_state),
        "selector_outputs": _safe_jsonify(selector_outputs),
        "rollup_summaries": _safe_jsonify(rollup_summaries),
        "contradictions": _safe_jsonify(contradictions),
        "narration_validations": narration_validations,
        "llm_response": {
            "text": llm_response_text,
            "model": llm_model,
            "duration_ms": llm_duration_ms,
        },
    }


def _safe_jsonify(obj):
    """Best-effort conversion to JSON-serializable shape. Datetime,
    time, and dataclass instances are all stringified."""
    try:
        json.dumps(obj, default=str)
        return obj
    except Exception:
        return str(obj)
