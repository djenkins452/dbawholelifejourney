# ==============================================================================
# File: apps/ai/chatgpt_cos/tasks.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Server-owned generation for the clean ChatGPT CoS path
# ==============================================================================
"""
run_chatgpt_cos_generation owns ChatGPT CoS generation in a Celery task so it
survives browser navigation/refresh/disconnect (the view is a read-only relay
over the chat_stream_bus snapshot; reconnect uses the existing resume endpoint).

This is the clean twin of apps.ai.tasks.run_chat_generation — it calls
ChatGPTCoSService and NEVER PersonalAssistant / legacy Beth.
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
    soft_time_limit=110,
    time_limit=120,
)
def run_chatgpt_cos_generation(self, user_id, conversation_id, message,
                               page_context, job_id):
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from apps.ai import chat_stream_bus as bus
    from apps.ai.chatgpt_cos.service import ChatGPTCoSService
    from apps.ai.chatgpt_cos.telemetry import log_cos_request
    from apps.ai.models import AssistantConversation, AssistantMessage

    User = get_user_model()
    t0 = time.monotonic()
    snap = bus.read(job_id) or bus.new_snapshot(user_id, conversation_id)
    snap["status"] = "processing"
    bus.write(job_id, snap)

    try:
        user = User.objects.get(id=user_id)
        conversation = AssistantConversation.objects.get(
            id=conversation_id, user=user,
        )
    except Exception:
        snap["status"] = "failed"
        snap["events"].append({"type": "error", "error": "setup_failed"})
        bus.write(job_id, snap)
        logger.error("CHATGPT_COS_SETUP_FAILED job=%s user=%s", job_id, user_id,
                     exc_info=True)
        return

    # Persist the user message + an assistant placeholder (recoverable on resume).
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

    error = None
    tools_called = []
    tools_advertised = []
    try:
        result = ChatGPTCoSService(user).generate(
            conversation, message, page_context=page_context, request_id=job_id,
        )
        answer = result["answer"] or (
            "I couldn't compose a response just now — please try again."
        )
        tools_called = result["tools_called"]
        tools_advertised = result["tools_advertised"]

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
        assistant_msg.content = (
            "That took too long to reach your data. Please try again."
        )
        _md = dict(assistant_msg.metadata or {}); _md["status"] = "timeout"
        assistant_msg.metadata = _md
        assistant_msg.save(update_fields=["content", "metadata"])
        logger.error("CHATGPT_COS_TIMEOUT job=%s user=%s", job_id, user_id)
    except Exception as exc:
        error = type(exc).__name__
        snap["status"] = "failed"
        snap["events"].append({"type": "error", "error": "generation_failed"})
        assistant_msg.content = (
            "I hit an error reaching your data. Please try again in a moment."
        )
        _md = dict(assistant_msg.metadata or {}); _md["status"] = "failed"
        assistant_msg.metadata = _md
        assistant_msg.save(update_fields=["content", "metadata"])
        logger.error("CHATGPT_COS_TASK_FAILED job=%s user=%s err=%s",
                     job_id, user_id, exc, exc_info=True)
    finally:
        bus.write(job_id, snap)
        try:
            from apps.ai.idempotency import clear_in_flight
            clear_in_flight(user_id, message)
        except Exception:
            pass
        log_cos_request(
            user_id=user_id, conversation_id=conversation_id,
            message_id=assistant_msg.id, request_id=job_id,
            tools_advertised=tools_advertised, tools_called=tools_called,
            final_source="chatgpt", error=error,
            latency_ms=(time.monotonic() - t0) * 1000,
        )
