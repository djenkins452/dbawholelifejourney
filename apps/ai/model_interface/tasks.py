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


@shared_task(name="apps.ai.model_interface.warm_understanding",
             bind=False, max_retries=0, ignore_result=True)
def warm_understanding(user_id):
    """Background warm of the Deterministic Understanding cache (heavy interpret() +
    day-continuity), so the request path only ever reads cache. Understanding owns its
    own cache/cadence (Architecture Law — refresh cadence is an ownership boundary).
    Never raises."""
    try:
        from django.contrib.auth import get_user_model
        from apps.ai.model_interface import understanding
        user = get_user_model().objects.get(id=user_id)
        understanding.warm(user)
    except Exception:
        logger.warning("warm_understanding failed user=%s", user_id, exc_info=True)


@shared_task(
    name="apps.ai.model_interface.run_model_interface_generation",
    bind=True,
    max_retries=0,
    acks_late=False,
    soft_time_limit=95,
    time_limit=110,
)
def run_model_interface_generation(self, user_id, conversation_id, message,
                                   page_context, job_id, images=None,
                                   attachments=None):
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
        # Load PRIOR turns BEFORE persisting this one (conversation continuity).
        from apps.ai.model_interface.service import load_conversation_history
        history = load_conversation_history(conversation)
        from apps.ai.multimodal import receipts_from_attachments
        user_msg = AssistantMessage.objects.create(
            conversation=conversation, role="user", content=message or "",
            message_type="text",
            attachment_receipts=receipts_from_attachments(attachments),
        )
        # Conversation integrity: persist the submitted image(s) onto the user's message so
        # the transcript stays faithful after reload — independent of the artifact lifecycle.
        if images:
            from apps.ai.multimodal import attach_images_to_message
            attach_images_to_message(user_msg, [tuple(img) for img in images])
        assistant_msg = AssistantMessage.objects.create(
            conversation=conversation, role="assistant", content="",
            message_type="text",
            metadata={"request_id": job_id, "cos_path": "model_interface",
                      "status": "processing"},
        )
        result = ModelInterfaceService(user).generate(
            conversation, message, page_context=page_context, surface="chat_stream",
            request_id=job_id, conversation_history=history,
            images=images, attachments=attachments,
        )
        answer = result.get("answer") or (
            "I reached the model-interface path, but the model returned an empty "
            "response after tool execution. Please try again."
        )
        # RICH CONFIRMATION — bind any confirmation minted this turn to the conversation and
        # surface the client card on the streaming `done` event + persist it for reload.
        from apps.ai.model_interface import confirmation as _confirm
        card = _confirm.bind_conversation(user, conversation.id)
        snap["text"] = answer
        done_data = {"conversation_id": conversation.id,
                     "message_id": assistant_msg.id,
                     "cos_path": "model_interface"}
        if card:
            done_data["confirmation"] = card
        snap["events"].append({"type": "done", "data": done_data})
        snap["status"] = "done"
        assistant_msg.content = answer
        if card:
            assistant_msg.confirmation = card
        _md = dict(assistant_msg.metadata or {})
        _md.update({"status": "completed",
                    "tools_called": result.get("tools_called", [])})
        assistant_msg.metadata = _md
        _fields = ["content", "metadata"] + (["confirmation"] if card else [])
        assistant_msg.save(update_fields=_fields)
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
