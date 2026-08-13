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

        # RICH CONFIRMATION — deterministic TYPED resolution (eliminate-the-class fix for the
        # production "yes was lost" defect). When there is an OPEN confirmation bound to this
        # conversation and the user's message clearly matches one of its actions' aliases
        # ("yes"/"import"/"go ahead"/"cancel"…), resolve it deterministically through the SAME
        # engine a button uses — the model is never the load-bearing path for a confirm/cancel.
        # Only a text-only turn short-circuits; ambiguous text still flows to the model (which
        # sees pending_confirmations and can resolve or clarify).
        if message and not (kwargs.get("image_data") or kwargs.get("images_list")
                            or kwargs.get("attachment_ids")):
            from apps.ai.cos_services.action_interface import resolve_typed_confirmation
            resolved = resolve_typed_confirmation(
                user, conversation.id, message,
                turn_id=f"conv-{conversation.id}", surface=surface)
            if resolved is not None:
                return self._deliver_confirmation_result(
                    user=user, surface=surface, conversation=conversation,
                    message=message, resolved=resolved, bus=bus,
                    stream=(stream or surface == SURFACE_CHAT_STREAM))

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

        # Conversation linkage: remember which artifacts belong to THIS conversation
        # so follow-up turns can retrieve them without re-attaching (multi-turn).
        turn_artifact_ids = [a.get("artifact_id") for a in attachments if a.get("artifact_id")]
        if turn_artifact_ids:
            from apps.ai.multimodal import link_artifacts_to_conversation
            link_artifacts_to_conversation(conversation.id, turn_artifact_ids)

        # ACTIVE ARTIFACT CONTINUITY — when there is NO new upload this turn but Conversation
        # State still holds an active artifact (an image/video the user is discussing),
        # RE-DELIVER its perceivable pixels/frames so the model can still SEE it on a follow-up
        # ("how many ounces is it?"). Conversation State keeps the artifact ACTIVE, not merely
        # referenced — otherwise the model has only a reference it cannot perceive and answers
        # "the image isn't available" (prod defect, 2026-07-20). General (image + video; the
        # bytes cache covers the durable-storage-pending window). Deterministic; never fatal.
        if not attachments:
            try:
                from apps.ai.model_interface import conversation_state as _cs
                active_ids = _cs.active_artifact_ids(conversation)
                if active_ids:
                    from apps.ai.multimodal import perceive_images_for_artifacts
                    perceive_images = (perceive_images or []) + perceive_images_for_artifacts(
                        user, active_ids)
            except Exception:
                logger.warning("cos_gateway: active-artifact re-delivery skipped", exc_info=True)

        # --- streaming: dispatch the model-interface task ---
        if stream or surface == SURFACE_CHAT_STREAM:
            from apps.ai.model_interface.tasks import run_model_interface_generation
            from apps.ai.models import AssistantMessage
            from apps.ai.multimodal import receipts_from_attachments

            job_id = str(_uuid.uuid4())

            # DUPLICATE PROTECTION — synchronous persistence (below) means a genuine
            # double-submit of the SAME text (double-click / an over-eager "try again")
            # would otherwise mint a SECOND durable turn. If an identical message is
            # already in flight, do NOT create a second turn: emit the existing turn's
            # `duplicate_pending` so the client shows "already in progress — view latest".
            # (Reload/navigation never re-submits, so this only guards true resubmits.)
            if message and not (images or attachments):
                from apps.ai import idempotency as _idem
                marker = _idem.is_in_flight(user.id, message)
                if marker:
                    import time as _t
                    secs = max(0, int((_t.time() * 1000 - marker.get(
                        "submitted_at_ms", 0)) / 1000))
                    snap = bus.new_snapshot(user.id, conversation.id)
                    snap["events"].append({"type": "duplicate_pending", "data": {
                        "request_id": marker.get("request_id"),
                        "original_message": marker.get("original_message", message),
                        "pending_seconds_ago": secs,
                        "conversation_id": conversation.id}})
                    snap["status"] = "done"
                    bus.write(job_id, snap)
                    return CoSResponse(
                        text="", runtime=self.name, surface=surface,
                        stream_job_id=job_id,
                        meta={"conversation_id": conversation.id,
                              "duplicate_pending": True})
                _idem.mark_in_flight(user.id, message, job_id)

            bus.write(job_id, bus.new_snapshot(user.id, conversation.id))

            # DURABLE TURN LIFECYCLE (server-owned) — the browser is a VIEWER, it must
            # never own the lifetime of a CoS turn. Persist the USER MESSAGE and a
            # PENDING assistant turn NOW, synchronously at submit, BEFORE the enqueue.
            # The instant Danny hits send the turn exists in durable truth, so
            # navigation, a browser-tab switch, a refresh, a client timeout, a
            # pre-pickup delay, or a dropped enqueue can no longer erase it — a reload
            # rehydrates the user message + the pending turn from the DB. The worker
            # UPDATES this pending turn (it no longer creates the rows). Persist BEFORE
            # enqueue so there is never a window where the job is running but the turn
            # is not yet durable.
            user_msg = AssistantMessage.objects.create(
                conversation=conversation, role="user", content=message or "",
                message_type="text",
                attachment_receipts=receipts_from_attachments(attachments),
            )
            if images:
                from apps.ai.multimodal import attach_images_to_message
                attach_images_to_message(user_msg, images)
            pending_msg = AssistantMessage.objects.create(
                conversation=conversation, role="assistant", content="",
                message_type="text",
                metadata={"request_id": job_id, "cos_path": "model_interface",
                          "status": "processing"},
            )
            run_model_interface_generation.delay(
                user.id, conversation.id, message, page_context, job_id,
                images=perceive_images or None, attachments=attachments or None,
                assistant_msg_id=pending_msg.id, user_msg_id=user_msg.id,
            )
            logger.info(
                "COS_GATEWAY runtime=model_interface surface=%s stream job=%s user=%s "
                "durable_turn=%s",
                surface, job_id, user.id, pending_msg.id,
            )
            return CoSResponse(
                text="", runtime=self.name, surface=surface,
                stream_job_id=job_id,
                meta={"conversation_id": conversation.id,
                      "message_id": pending_msg.id},
            )

        # --- non-streaming: generate synchronously + persist (mirror the task) ---
        from apps.ai.model_interface.service import (
            ModelInterfaceService, load_conversation_history,
        )
        from apps.ai.models import AssistantMessage

        # Load PRIOR turns BEFORE persisting this one (conversation continuity).
        history = load_conversation_history(conversation)
        from apps.ai.multimodal import receipts_from_attachments
        user_msg = AssistantMessage.objects.create(
            conversation=conversation, role="user", content=message or "",
            message_type="text",
            attachment_receipts=receipts_from_attachments(attachments),
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
        # RICH CONFIRMATION — if this turn minted a confirmation, bind it to the conversation
        # and surface the client card (on the message for reload + in meta for the live turn).
        from apps.ai.model_interface import confirmation as _confirm
        card = _confirm.bind_conversation(user, conversation.id)
        AssistantMessage.objects.create(
            conversation=conversation, role="assistant", content=answer,
            message_type="text", confirmation=card,
            metadata={"cos_path": "model_interface", "status": "completed",
                      "tools_called": result.get("tools_called", [])},
        )
        logger.info(
            "COS_GATEWAY runtime=model_interface surface=%s sync user=%s answer_len=%d",
            surface, user.id, len(answer),
        )
        meta = {"conversation_id": conversation.id,
                "tools_called": result.get("tools_called", []),
                # turn_id joins this answer to its ToolCallLog audit rows so a
                # certification run can capture WHICH tool returned WHICH fact.
                "turn_id": result.get("turn_id", "")}
        if card:
            meta["confirmation"] = card
        return CoSResponse(text=answer, runtime=self.name, surface=surface, meta=meta)

    def _deliver_confirmation_result(self, *, user, surface, conversation, message,
                                     resolved, bus, stream):
        """Persist + deliver a deterministically-resolved TYPED confirmation as the next
        assistant turn — NO model call. Works for both transports; `confirmation_resolved`
        tells the client which card to mark resolved/cancelled."""
        from apps.ai.models import AssistantMessage
        text = resolved.get("result") or "Done."
        status = resolved.get("status")
        card_status = ("cancelled" if status == "declined"
                       else "resolved" if status == "ok" else "error")
        resolved_meta = {"confirmation_id": resolved.get("confirmation_id"),
                         "status": card_status}
        AssistantMessage.objects.create(
            conversation=conversation, role="user", content=message or "",
            message_type="text")
        assistant_msg = AssistantMessage.objects.create(
            conversation=conversation, role="assistant", content=text,
            message_type="text",
            metadata={"cos_path": "model_interface", "status": "completed",
                      "confirmation_resolved": resolved_meta})
        # Reflect the resolution on the ORIGINAL confirmation card so reloads render it
        # as resolved/cancelled rather than offering stale buttons.
        _mark_prior_confirmation(conversation, resolved_meta)

        if stream:
            import uuid as _uuid
            job_id = str(_uuid.uuid4())
            snap = bus.new_snapshot(user.id, conversation.id)
            snap["text"] = text
            snap["events"].append({
                "type": "done",
                "data": {"conversation_id": conversation.id,
                         "message_id": assistant_msg.id, "cos_path": "model_interface",
                         "confirmation_resolved": resolved_meta}})
            snap["status"] = "done"
            bus.write(job_id, snap)
            return CoSResponse(text="", runtime=self.name, surface=surface,
                               stream_job_id=job_id,
                               meta={"conversation_id": conversation.id,
                                     "confirmation_resolved": resolved_meta})
        return CoSResponse(
            text=text, runtime=self.name, surface=surface,
            meta={"conversation_id": conversation.id,
                  "confirmation_resolved": resolved_meta})


def _mark_prior_confirmation(conversation, resolved_meta):
    """Stamp the resolved/cancelled status onto the message that originally carried this
    confirmation card, so history/reload renders it in its final state. Best-effort."""
    cid = (resolved_meta or {}).get("confirmation_id")
    if not cid:
        return
    try:
        from apps.ai.models import AssistantMessage
        for m in AssistantMessage.objects.filter(
                conversation=conversation, role="assistant",
                confirmation__confirmation_id=cid)[:3]:
            card = dict(m.confirmation or {})
            card["status"] = resolved_meta.get("status", "resolved")
            m.confirmation = card
            m.save(update_fields=["confirmation"])
    except Exception:  # pragma: no cover - defensive
        logger.debug("rich-confirmation: mark_prior skipped", exc_info=True)


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
