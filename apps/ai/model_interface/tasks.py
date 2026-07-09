# ==============================================================================
# File: apps/ai/model_interface/tasks.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Server-owned generation for the model-interface runtime (streaming)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
run_model_interface_generation — the streaming twin of the non-streaming path.

Mirrors the ChatGPT-CoS task contract: it runs ModelInterfaceService.generate in a
Celery task and ALWAYS writes a terminal snapshot (done/failed) so the SSE relay never
hangs. Registered with the worker via an import in apps/ai/tasks.py.
"""

import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger("apps.ai.model_interface")


@shared_task(
    name="apps.ai.model_interface.run_model_interface_generation",
    bind=True,
    max_retries=0,
    acks_late=False,
    soft_time_limit=95,
    time_limit=110,
)
def run_model_interface_generation(self, user_id, conversation_id, message,
                                   page_context, job_id):
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from apps.ai import chat_stream_bus as bus
    from apps.ai.model_interface.service import ModelInterfaceService
    from apps.ai.models import AssistantConversation, AssistantMessage

    User = get_user_model()
    snap = bus.read(job_id) or bus.new_snapshot(user_id, conversation_id)
    snap["status"] = "processing"
    bus.write(job_id, snap)

    assistant_msg = None
    try:
        user = User.objects.get(id=user_id)
        conversation = AssistantConversation.objects.get(id=conversation_id, user=user)
        AssistantMessage.objects.create(
            conversation=conversation, role="user", content=message or "",
            message_type="text",
        )
        assistant_msg = AssistantMessage.objects.create(
            conversation=conversation, role="assistant", content="",
            message_type="text",
            metadata={"request_id": job_id, "cos_path": "model_interface",
                      "status": "processing"},
        )
        result = ModelInterfaceService(user).generate(
            conversation, message, page_context=page_context, surface="chat_stream",
            request_id=job_id,
        )
        answer = result.get("answer") or (
            "I reached the model-interface path, but the model returned an empty "
            "response after tool execution. Please try again."
        )
        snap["text"] = answer
        snap["events"].append({
            "type": "done",
            "data": {"conversation_id": conversation.id,
                     "message_id": assistant_msg.id,
                     "cos_path": "model_interface"},
        })
        snap["status"] = "done"
        assistant_msg.content = answer
        _md = dict(assistant_msg.metadata or {})
        _md.update({"status": "completed",
                    "tools_called": result.get("tools_called", [])})
        assistant_msg.metadata = _md
        assistant_msg.save(update_fields=["content", "metadata"])
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["updated_at"])

    except SoftTimeLimitExceeded:
        _fail(bus, snap, job_id, assistant_msg, "timeout")
        return
    except Exception:
        logger.warning("MODEL_INTERFACE task failed job=%s user=%s",
                       job_id, user_id, exc_info=True)
        _fail(bus, snap, job_id, assistant_msg, "error")
        return

    bus.write(job_id, snap)


def _fail(bus, snap, job_id, assistant_msg, reason):
    """Always publish a TERMINAL snapshot so the relay never hangs."""
    try:
        snap["status"] = "failed"
        snap.setdefault("events", []).append({"type": "error", "data": {"reason": reason}})
        snap["text"] = ("Something went wrong reaching the model-interface path. "
                        "Please try again.")
        bus.write(job_id, snap)
        if assistant_msg is not None:
            _md = dict(assistant_msg.metadata or {})
            _md.update({"status": "failed", "reason": reason})
            assistant_msg.metadata = _md
            assistant_msg.content = snap["text"]
            assistant_msg.save(update_fields=["content", "metadata"])
    except Exception:
        logger.error("MODEL_INTERFACE terminal-snapshot write failed job=%s",
                     job_id, exc_info=True)
