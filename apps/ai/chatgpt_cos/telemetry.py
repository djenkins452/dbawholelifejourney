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
