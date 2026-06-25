# ==============================================================================
# File: apps/ai/chatgpt_cos/telemetry.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Observability for the clean ChatGPT CoS path
# ==============================================================================
"""
One unambiguous log line per ChatGPT CoS request, so there is never any doubt
about what answered a message.
"""

import logging

logger = logging.getLogger("apps.ai.chatgpt_cos")

# Bump on any change to the clean-path behaviour so logs reveal the live build.
COS_BUILD_HASH = "chatgpt-clean-v1"

# The exact, ordered lifecycle stages a single Beth request passes through.
# Used to prove from production logs precisely where a request dies. `cid` is
# the single client-minted correlation id that threads every line (client +
# server); `request_id`/`job_id` are the server job id (equal in this path).
BETH_LIFECYCLE_STAGES = frozenset({
    "BETH_REQUEST_SUBMITTED",
    "BETH_JOB_CREATED",
    "BETH_TASK_STARTED",
    "BETH_GENERATE_STARTED",
    "BETH_GENERATE_FINISHED",
    "BETH_MESSAGE_PERSISTED",
    "BETH_PENDING_MARKER_CREATED",
    "BETH_RECOVERY_POLL_STARTED",
    "BETH_RECOVERY_POLL_FOUND_MESSAGE",
    "BETH_RECOVERY_POLL_TIMEOUT",
    "BETH_JOB_RECONNECTED",
    "BETH_JOB_RESUMED",
    "BETH_TASK_FINALLY",
})


def beth_lifecycle(stage, *, cid=None, job_id=None, conversation_id=None,
                   message_id=None, user_id=None, src="server", extra=None):
    """Emit ONE structured lifecycle line. Pure instrumentation — never raises.

    Every line carries the full correlation set so a single request can be
    reconstructed end-to-end from production logs:
        BETH_LIFECYCLE stage=… cid=… request_id=… job_id=… conversation_id=…
                       message_id=… user_id=… src=… extra=…
    """
    try:
        logger.info(
            "BETH_LIFECYCLE stage=%s cid=%s request_id=%s job_id=%s "
            "conversation_id=%s message_id=%s user_id=%s src=%s extra=%s",
            stage, cid or "-", job_id or "-", job_id or "-",
            conversation_id or "-", message_id or "-", user_id or "-",
            src, extra or "-",
        )
    except Exception:
        pass


def log_cos_request(*, user_id, conversation_id, message_id, request_id,
                    tools_advertised, tools_called, final_source,
                    error, latency_ms):
    """Emit the canonical COS_PATH=chatgpt_clean telemetry line."""
    try:
        logger.info(
            "COS_PATH=chatgpt_clean REQUEST_ID=%s BUILD_HASH=%s USER_ID=%s "
            "CONVERSATION_ID=%s MESSAGE_ID=%s TOOLS_ADVERTISED=%s "
            "TOOLS_CALLED=%s FINAL_RESPONSE_SOURCE=%s ERRORS=%s LATENCY_MS=%.1f",
            request_id, COS_BUILD_HASH, user_id, conversation_id, message_id,
            ",".join(tools_advertised or []) or "none",
            ",".join(tools_called or []) or "none",
            final_source, error or "none", float(latency_ms or 0.0),
        )
    except Exception:
        pass
