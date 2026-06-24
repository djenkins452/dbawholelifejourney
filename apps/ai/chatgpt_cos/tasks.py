# ==============================================================================
# File: apps/ai/chatgpt_cos/tasks.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Server-owned generation for the clean ChatGPT CoS path
# ==============================================================================
"""
run_chatgpt_cos_generation owns ChatGPT CoS generation in a Celery task so it
survives browser navigation/refresh/disconnect (the view is a read-only relay
over the chat_stream_bus snapshot; reconnect uses the existing resume endpoint).

Clean twin of apps.ai.tasks.run_chat_generation — calls ChatGPTCoSService, never
PersonalAssistant / legacy Beth.

CRITICAL: this task MUST always write a TERMINAL snapshot status (done/failed),
or the relay tails a non-terminal snapshot forever and the chat hangs. The whole
body is guarded so any exception still publishes a terminal status.

NOTE: registration with the Celery worker is forced via an import in the
autodiscovered apps/ai/tasks.py (this sub-package is not an INSTALLED_APP).
"""

import logging
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger("apps.ai.chatgpt_cos")


@shared_task(
    name="apps.ai.chatgpt_cos.run_chatgpt_cos_generation",
    bind=True,
    max_retries=0,      # a retry would post a duplicate answer
    acks_late=False,
    soft_time_limit=95,  # < relay MAX_WALL(90)+resume and < hard limit, so the
    time_limit=110,      # SoftTimeLimit handler can publish 'failed' before kill
)
def run_chatgpt_cos_generation(self, user_id, conversation_id, message,
                               page_context, job_id):
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from apps.ai import chat_stream_bus as bus
    from apps.ai.chatgpt_cos.service import ChatGPTCoSService
    from apps.ai.chatgpt_cos.telemetry import COS_BUILD_HASH, log_cos_request
    from apps.ai.models import AssistantConversation, AssistantMessage

    User = get_user_model()
    t0 = time.monotonic()

    snap = bus.read(job_id) or bus.new_snapshot(user_id, conversation_id)
    snap["status"] = "processing"
    bus.write(job_id, snap)
    logger.info(
        "COS_REQUEST_START job=%s user=%s conv=%s build=%s",
        job_id, user_id, conversation_id, COS_BUILD_HASH,
    )

    assistant_msg = None
    error = None
    tools_called = []
    tools_advertised = []

    try:
        user = User.objects.get(id=user_id)
        conversation = AssistantConversation.objects.get(
            id=conversation_id, user=user,
        )
        # Persist the user message + an assistant placeholder (recoverable).
        AssistantMessage.objects.create(
            conversation=conversation, role="user", content=message,
            message_type="text",
        )
        assistant_msg = AssistantMessage.objects.create(
            conversation=conversation, role="assistant", content="",
            message_type="text",
            metadata={"request_id": job_id, "cos_path": "chatgpt_clean",
                      "status": "processing"},
        )

        result = ChatGPTCoSService(user).generate(
            conversation, message, page_context=page_context, request_id=job_id,
        )
        answer = result["answer"] or (
            "I couldn't compose a response just now — please try again."
        )
        tools_called = result.get("tools_called", [])
        tools_advertised = result.get("tools_advertised", [])

        snap["text"] = answer
        snap["events"].append({
            "type": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": assistant_msg.id,
                "cos_path": "chatgpt_clean",
            },
        })
        snap["status"] = "done"

        assistant_msg.content = answer
        _md = dict(assistant_msg.metadata or {})
        _md.update({"status": "completed", "tools_called": tools_called})
        assistant_msg.metadata = _md
        assistant_msg.save(update_fields=["content", "metadata"])
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["updated_at"])

    except SoftTimeLimitExceeded:
        error = "timeout"
        snap["status"] = "failed"
        snap["events"].append({"type": "error", "error": "timeout"})
        logger.error("COS_EXCEPTION job=%s user=%s type=timeout", job_id, user_id)
        _safe_set_assistant(assistant_msg,
                            "That took too long to reach your data. Please try "
                            "again.", "timeout")
    except Exception as exc:
        error = type(exc).__name__
        snap["status"] = "failed"
        snap["events"].append({"type": "error", "error": "generation_failed"})
        logger.error("COS_EXCEPTION job=%s user=%s err=%s",
                     job_id, user_id, exc, exc_info=True)
        _safe_set_assistant(assistant_msg,
                            "I hit an error reaching your data. Please try "
                            "again in a moment.", "failed")
    finally:
        # ALWAYS publish a terminal status — never leave the relay hanging.
        if snap.get("status") not in bus.TERMINAL_STATUSES:
            snap["status"] = "failed"
            snap["events"].append({"type": "error", "error": "unknown"})
        logger.info("COS_STREAM_PUBLISH job=%s status=%s", job_id,
                    snap.get("status"))
        bus.write(job_id, snap)
        try:
            from apps.ai.idempotency import clear_in_flight
            clear_in_flight(user_id, message)
        except Exception:
            pass
        _ms = (time.monotonic() - t0) * 1000
        log_cos_request(
            user_id=user_id, conversation_id=conversation_id,
            message_id=getattr(assistant_msg, "id", None), request_id=job_id,
            tools_advertised=tools_advertised, tools_called=tools_called,
            final_source="chatgpt", error=error, latency_ms=_ms,
        )
        logger.info(
            "COS_REQUEST_FINISH job=%s user=%s status=%s error=%s "
            "tools_called=%s latency_ms=%.1f",
            job_id, user_id, snap.get("status"), error or "none",
            ",".join(tools_called) or "none", _ms,
        )


def _safe_set_assistant(assistant_msg, content, status):
    """Best-effort write of an error message to the assistant placeholder."""
    if assistant_msg is None:
        return
    try:
        assistant_msg.content = content
        _md = dict(assistant_msg.metadata or {}); _md["status"] = status
        assistant_msg.metadata = _md
        assistant_msg.save(update_fields=["content", "metadata"])
    except Exception:
        logger.warning("COS_ASSISTANT_SAVE_FAILED", exc_info=True)
