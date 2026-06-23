# ==============================================================================
# File: apps/ai/chat_stream_bus.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Cache-backed relay bus for background chat generation (P0 fix)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-23
# ==============================================================================
"""
Chat Stream Bus — decouples LLM generation from the live HTTP request.

Background
----------
Previously, the SSE streaming endpoint ran the LLM token loop *inside* the
StreamingHttpResponse generator. On a synchronous gunicorn worker, when the
client navigated away the TCP connection closed, gunicorn stopped pulling
from the generator, and ``GeneratorExit`` killed generation mid-answer.
Navigation therefore abandoned the response.

New model
---------
Generation now runs in a Celery task (``apps.ai.tasks.run_chat_generation``).
The task is the SINGLE WRITER of a per-job *snapshot* held in the Django cache.
HTTP requests (the initial POST relay and any later resume) are READ-ONLY
observers that tail the snapshot and re-emit it as SSE. The browser
disconnecting only ends an observer; the task keeps running and persists the
assistant message on completion.

Why the Django cache (not a raw Redis queue)
--------------------------------------------
* Production cache backend is Redis, shared across the web and worker
  services, so a snapshot written by the worker is visible to the web relay.
* In dev/test with ``CELERY_TASK_ALWAYS_EAGER=True`` the task runs in the
  same process as the request, so an in-process LocMemCache is shared too —
  the relay reads a fully-populated snapshot and streams it at once.
* A *snapshot* (growing text + ordered control events), unlike a consumed
  queue, can be replayed from the beginning by an unlimited number of
  readers — which is exactly what reconnect-by-job_id requires.

Snapshot shape
--------------
``{
    'owner': int,                 # user id — enforced on resume
    'conversation_id': int|None,
    'status': str,                # queued -> processing -> done|failed|interrupted
    'text': str,                  # accumulated assistant token text
    'events': [event_dict, ...],  # ordered control events (done/correction/...)
    'updated_ms': int,
}``

Only the task mutates a snapshot (single writer), so reads never race a
partial write. Snapshots carry a short TTL and a terminal ``status`` acting
as the done sentinel.
"""

import json
import logging
import time

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Short TTL — long enough to survive a page reload / brief absence, short
# enough that abandoned jobs evaporate. Refreshed on every write.
CHAT_JOB_TTL = 600  # seconds (10 minutes)

_KEY_PREFIX = "wlj:chat:job:"

# Terminal statuses act as the "done sentinel": once a snapshot reaches one
# of these, readers drain remaining events and stop.
TERMINAL_STATUSES = frozenset({"done", "failed", "interrupted"})


def make_key(job_id):
    return f"{_KEY_PREFIX}{job_id}"


def new_snapshot(owner_id, conversation_id):
    """Build a fresh snapshot dict for a queued job."""
    return {
        "owner": int(owner_id),
        "conversation_id": conversation_id,
        "status": "queued",
        "text": "",
        "events": [],
        "updated_ms": int(time.time() * 1000),
    }


def write(job_id, snapshot, ttl=CHAT_JOB_TTL):
    """Persist a snapshot (single-writer: the Celery task only)."""
    snapshot["updated_ms"] = int(time.time() * 1000)
    try:
        cache.set(make_key(job_id), snapshot, ttl)
    except Exception:
        logger.error("CHAT_BUS_WRITE_FAILED job=%s", job_id, exc_info=True)


def read(job_id):
    """Read the current snapshot, or None if expired/unknown."""
    try:
        return cache.get(make_key(job_id))
    except Exception:
        logger.error("CHAT_BUS_READ_FAILED job=%s", job_id, exc_info=True)
        return None


def clear(job_id):
    try:
        cache.delete(make_key(job_id))
    except Exception:
        pass


def format_sse(event):
    """
    Convert a relayed control event dict into an SSE frame string.

    Mirrors the framing the legacy streaming view used so the existing
    frontend parser keeps working unchanged. Token text is NOT formatted
    here — the relay emits token deltas directly from the accumulated
    ``text`` field.

    Returns an empty string for event types that were not surfaced by the
    legacy view (e.g. raw 'quick_replies'), preserving prior behaviour.
    """
    etype = event.get("type")
    if etype == "token":
        return (
            "event: token\n"
            f"data: {json.dumps({'content': event.get('content', '')})}\n\n"
        )
    if etype == "done":
        return (
            "event: done\n"
            f"data: {json.dumps(event.get('data', {}))}\n\n"
        )
    if etype == "correction":
        return (
            "event: correction\n"
            f"data: {json.dumps({'content': event.get('content', '')})}\n\n"
        )
    if etype == "duplicate_pending":
        return (
            "event: duplicate_pending\n"
            f"data: {json.dumps(event.get('data', {}))}\n\n"
        )
    if etype == "error":
        return (
            "event: error\n"
            f"data: {json.dumps({'error': event.get('error', 'Stream failed')})}\n\n"
        )
    return ""
