# ==============================================================================
# File: apps/ai/cos_gateway/runtime.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Phase 0A — ConversationalRuntime interface + the two runtimes
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
Two conversational runtimes behind one interface. The gateway selects exactly
one per request; the surface never knows which ran.

  ChatGPTCoSRuntime  — imports ONLY the clean CoS runtime + truth/streaming infra.
                       It must never import a legacy conversational generator
                       (enforced by the import-drift test).
  LegacyBethRuntime  — wraps the EXISTING legacy generators verbatim, so flag-OFF
                       behavior is unchanged. Legacy imports live HERE, isolated.

Phase 0A surfaces: chat (non-streaming) and chat_stream (SSE). Other surfaces are
deferred (see PHASE_0A notes in the changelog) and rejected by the gateway.
"""

import logging
import uuid as _uuid
from abc import ABC, abstractmethod

from apps.ai.cos_gateway.envelope import (
    RUNTIME_CHATGPT,
    RUNTIME_LEGACY,
    RUNTIME_MODEL_INTERFACE,
    SURFACE_CHAT_STREAM,
    CoSResponse,
)

logger = logging.getLogger(__name__)


class ConversationalRuntime(ABC):
    """One runtime owns the entire interaction for a given user."""

    name = "base"

    @abstractmethod
    def respond(self, *, user, surface, message=None, conversation=None,
                page_context=None, stream=False, **kwargs) -> CoSResponse:
        ...


class ChatGPTCoSRuntime(ConversationalRuntime):
    """The sole conversational runtime for use_chatgpt_cos=True users.

    Reuses ONLY: ChatGPTCoSService (clean runtime), the CoS Celery task,
    chat_stream_bus (streaming), AssistantConversation/AssistantMessage
    (persistence). No legacy conversational component is touched.
    """

    name = RUNTIME_CHATGPT

    def respond(self, *, user, surface, message=None, conversation=None,
                page_context=None, stream=False, **kwargs):
        from apps.ai import chat_stream_bus as bus
        from apps.ai.models import AssistantConversation

        if conversation is None:
            conversation = AssistantConversation.get_or_create_active(user)

        # --- streaming: dispatch the CoS task, return the relay job id ---
        if stream or surface == SURFACE_CHAT_STREAM:
            from apps.ai.chatgpt_cos.tasks import run_chatgpt_cos_generation
            job_id = str(_uuid.uuid4())
            bus.write(job_id, bus.new_snapshot(user.id, conversation.id))
            run_chatgpt_cos_generation.delay(
                user.id, conversation.id, message, page_context, job_id,
            )
            logger.info(
                "COS_GATEWAY runtime=chatgpt_cos surface=%s stream job=%s user=%s",
                surface, job_id, user.id,
            )
            try:
                from apps.ai.chatgpt_cos.telemetry import beth_lifecycle
                beth_lifecycle(
                    "BETH_JOB_CREATED",
                    cid=(page_context or {}).get("beth_cid"),
                    job_id=job_id, conversation_id=conversation.id,
                    user_id=user.id, src="server",
                )
            except Exception:
                pass
            return CoSResponse(
                text="", runtime=self.name, surface=surface,
                stream_job_id=job_id,
                meta={"conversation_id": conversation.id},
            )

        # --- non-streaming: generate synchronously + persist (mirror the task) ---
        from apps.ai.chatgpt_cos.service import ChatGPTCoSService
        from apps.ai.models import AssistantMessage

        AssistantMessage.objects.create(
            conversation=conversation, role="user", content=message or "",
            message_type="text",
        )
        result = ChatGPTCoSService(user).generate(
            conversation, message, page_context=page_context,
        )
        answer = result.get("answer") or ""
        if not answer:
            # Same diagnostic-safe contract as the streaming task.
            reason = result.get("empty_reason")
            answer = (
                "I reached OpenAI, but the response came back empty after "
                "retries. Please try again."
                if reason == "openai_fallback_empty" else
                "I reached the ChatGPT CoS path, but the model returned an "
                "empty response after tool execution. Please try again."
            )
        AssistantMessage.objects.create(
            conversation=conversation, role="assistant", content=answer,
            message_type="text",
            metadata={"cos_path": "chatgpt_clean", "status": "completed",
                      "tools_called": result.get("tools_called", [])},
        )
        logger.info(
            "COS_GATEWAY runtime=chatgpt_cos surface=%s sync user=%s answer_len=%d",
            surface, user.id, len(answer),
        )
        return CoSResponse(
            text=answer, runtime=self.name, surface=surface,
            meta={"conversation_id": conversation.id,
                  "tools_called": result.get("tools_called", [])},
        )


class ModelInterfaceRuntime(ConversationalRuntime):
    """The runtime for use_model_interface=True users — the WLJ ↔ conversational-model
    interface (Phase II). A THIRD, separate runtime: it imports ONLY the clean
    model-interface service/task + streaming/persistence infra, and never touches the
    legacy or ChatGPT-CoS conversational generators. Mirrors ChatGPTCoSRuntime's shape
    (Celery task for streaming, synchronous generate for non-streaming)."""

    name = RUNTIME_MODEL_INTERFACE

    def respond(self, *, user, surface, message=None, conversation=None,
                page_context=None, stream=False, **kwargs):
        from apps.ai import chat_stream_bus as bus
        from apps.ai.models import AssistantConversation

        if conversation is None:
            conversation = AssistantConversation.get_or_create_active(user)

        # Multimodal arrival path — store each uploaded image as an artifact (provenance +
        # hash dedup) BEFORE generation, and produce the perception payload the model reads.
        # Runs for BOTH sync and streaming so the artifact_id exists regardless of path.
        from apps.ai.multimodal import (
            attachments_from_ids, frames_for_attachments, ingest_uploads,
        )
        images, attachments = ingest_uploads(
            user,
            image_data=kwargs.get("image_data"),
            image_mime_type=kwargs.get("image_mime_type"),
            images_list=kwargs.get("images_list"),
        )
        # Pre-uploaded attachments (from the WLJ Attachment Framework via the
        # /attachments/ endpoint) arrive as artifact ids. Resolve the caller's own
        # artifacts and merge as attachments-as-data (dedup by id — an inline image
        # already surfaced as an artifact must not appear twice).
        extra = attachments_from_ids(user, kwargs.get("attachment_ids"))
        if extra:
            seen = {a["artifact_id"] for a in attachments}
            attachments = attachments + [a for a in extra if a["artifact_id"] not in seen]

        # VIDEO perception: deliver the sampled frames of any referenced video to the
        # model's image path so it can SEE the video (the transcript already rides in
        # the attachment's `text`). Frames are NOT persisted to the transcript (they
        # are derived, not what the user submitted) — only the user's own images are.
        perceive_images = images + frames_for_attachments(user, kwargs.get("attachment_ids"))

        # --- streaming: dispatch the model-interface task ---
        if stream or surface == SURFACE_CHAT_STREAM:
            from apps.ai.model_interface.tasks import run_model_interface_generation
            job_id = str(_uuid.uuid4())
            bus.write(job_id, bus.new_snapshot(user.id, conversation.id))
            run_model_interface_generation.delay(
                user.id, conversation.id, message, page_context, job_id,
                images=perceive_images or None, attachments=attachments or None,
            )
            logger.info(
                "COS_GATEWAY runtime=model_interface surface=%s stream job=%s user=%s",
                surface, job_id, user.id,
            )
            return CoSResponse(
                text="", runtime=self.name, surface=surface,
                stream_job_id=job_id,
                meta={"conversation_id": conversation.id},
            )

        # --- non-streaming: generate synchronously + persist (mirror the task) ---
        from apps.ai.model_interface.service import (
            ModelInterfaceService, load_conversation_history,
        )
        from apps.ai.models import AssistantMessage

        # Load PRIOR turns BEFORE persisting this one (conversation continuity).
        history = load_conversation_history(conversation)
        user_msg = AssistantMessage.objects.create(
            conversation=conversation, role="user", content=message or "",
            message_type="text",
        )
        # Conversation integrity: the transcript keeps the image the user submitted, even
        # after the artifact resolves into truth (artifact lifecycle ≠ conversation lifecycle).
        if images:
            from apps.ai.multimodal import attach_images_to_message
            attach_images_to_message(user_msg, images)
        result = ModelInterfaceService(user).generate(
            conversation, message, page_context=page_context, surface=surface,
            conversation_history=history,
            images=perceive_images or None, attachments=attachments or None,
        )
        answer = result.get("answer") or (
            "I reached the model-interface path, but the model returned an empty "
            "response after tool execution. Please try again."
        )
        AssistantMessage.objects.create(
            conversation=conversation, role="assistant", content=answer,
            message_type="text",
            metadata={"cos_path": "model_interface", "status": "completed",
                      "tools_called": result.get("tools_called", [])},
        )
        logger.info(
            "COS_GATEWAY runtime=model_interface surface=%s sync user=%s answer_len=%d",
            surface, user.id, len(answer),
        )
        return CoSResponse(
            text=answer, runtime=self.name, surface=surface,
            meta={"conversation_id": conversation.id,
                  "tools_called": result.get("tools_called", []),
                  # turn_id joins this answer to its ToolCallLog audit rows so a
                  # certification run can capture WHICH tool returned WHICH fact.
                  "turn_id": result.get("turn_id", "")},
        )


class LegacyBethRuntime(ConversationalRuntime):
    """The runtime for use_chatgpt_cos=False users. Wraps existing legacy
    generators verbatim — flag-OFF behavior is intentionally unchanged. All
    legacy conversational imports are isolated to this class."""

    name = RUNTIME_LEGACY

    def respond(self, *, user, surface, message=None, conversation=None,
                page_context=None, stream=False, assistant=None, **kwargs):
        from apps.ai import chat_stream_bus as bus

        # Preserve the authoritative day-start briefing (idempotent), exactly as
        # the legacy chat views did before the gateway.
        try:
            from apps.ai.executive_briefing import handle_day_start
            handle_day_start(user)
        except Exception:
            logger.warning("legacy day-start failed", exc_info=True)

        if assistant is None:
            from apps.ai.personal_assistant import PersonalAssistant
            assistant = PersonalAssistant(user)
        if conversation is None:
            conversation = assistant.get_or_create_conversation()

        # --- streaming: dispatch the legacy generation task ---
        if stream or surface == SURFACE_CHAT_STREAM:
            from apps.ai.tasks import run_chat_generation
            job_id = str(_uuid.uuid4())
            bus.write(job_id, bus.new_snapshot(user.id, conversation.id))
            run_chat_generation.delay(
                user.id, conversation.id, message, page_context, job_id,
            )
            logger.info(
                "COS_GATEWAY runtime=legacy_beth surface=%s stream job=%s user=%s",
                surface, job_id, user.id,
            )
            return CoSResponse(
                text="", runtime=self.name, surface=surface,
                stream_job_id=job_id,
                meta={"conversation_id": conversation.id},
            )

        # --- non-streaming: identical to the prior AssistantChatView path ---
        send_kwargs = {
            k: kwargs[k]
            for k in ("image_data", "image_mime_type", "images_list")
            if k in kwargs
        }
        result = assistant.send_message(
            message, conversation, page_context=page_context, **send_kwargs,
        )
        if isinstance(result, dict):
            text = result.get("response", "")
            meta = {"conversation_id": conversation.id, "legacy_result": result}
        else:
            text = result or ""
            meta = {"conversation_id": conversation.id}
        return CoSResponse(text=text, runtime=self.name, surface=surface,
                           meta=meta)
