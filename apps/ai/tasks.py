# ==============================================================================
# File: apps/ai/tasks.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Celery tasks for CoS readiness and keep-alive
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-28
# ==============================================================================
"""
CoS Celery Tasks

Provides keep-alive and readiness tasks for the Chief of Staff system.
These tasks run via Celery Beat to maintain CoS responsiveness for active users.
"""

import logging
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)


@shared_task(
    name="apps.ai.tasks.run_chat_generation",
    bind=True,
    # No retries / no late-ack: a retry or redelivery would generate a
    # SECOND assistant message for the same question. Losing a job on a
    # worker crash is preferable to duplicating a reply.
    max_retries=0,
    acks_late=False,
    soft_time_limit=110,
    time_limit=120,
)
def run_chat_generation(self, user_id, conversation_id, message,
                        page_context, job_id):
    """
    Own the LLM generation for one chat turn, independent of the browser.

    This is the heart of the P0 navigation fix. Generation runs here as a
    plain function call (NOT inside an HTTP response generator), so a client
    disconnecting cannot raise ``GeneratorExit`` into it. Tokens and control
    events are relayed into a cache snapshot via ``chat_stream_bus``; the web
    relay (and any later resume) merely observe that snapshot.

    The assistant message itself is persisted by ``send_message_stream``'s own
    finally-block on completion — unchanged. Reasoning logic is untouched.

    Telemetry markers: CHAT_TASK_STARTED / CHAT_TASK_COMPLETED /
    CHAT_TASK_FAILED / CHAT_TASK_TIMEOUT.
    """
    from django.contrib.auth import get_user_model

    from apps.ai import chat_stream_bus as bus
    from apps.ai.models import AssistantConversation
    from apps.ai.personal_assistant import PersonalAssistant

    User = get_user_model()
    started = time.monotonic()
    logger.info(
        "CHAT_TASK_STARTED job=%s user=%s conv=%s",
        job_id, user_id, conversation_id,
    )

    # The view writes an initial snapshot (with owner) before dispatch; fall
    # back to a fresh one if it expired between dispatch and pickup.
    snap = bus.read(job_id) or bus.new_snapshot(user_id, conversation_id)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        snap["status"] = "failed"
        bus.write(job_id, snap)
        logger.error("CHAT_TASK_NO_USER job=%s user=%s", job_id, user_id)
        return

    snap["status"] = "processing"
    bus.write(job_id, snap)

    _last_flush = 0.0
    _FLUSH_INTERVAL = 0.12  # seconds — bounds snapshot write frequency
    _first_token_ms = None
    _token_count = 0

    def _flush(force=False):
        nonlocal _last_flush
        now = time.monotonic()
        if force or (now - _last_flush) >= _FLUSH_INTERVAL:
            bus.write(job_id, snap)
            _last_flush = now

    try:
        assistant = PersonalAssistant(user)
        try:
            conversation = AssistantConversation.objects.get(
                id=conversation_id, user=user,
            )
        except AssistantConversation.DoesNotExist:
            conversation = assistant.get_or_create_conversation()

        for event in assistant.send_message_stream(
            message, conversation, page_context=page_context or {},
        ):
            etype = event.get("type")
            if etype == "token":
                if _first_token_ms is None:
                    _first_token_ms = (time.monotonic() - started) * 1000
                _token_count += 1
                snap["text"] += event.get("content", "")
                _flush()
            else:
                # Relay control events (done / correction / duplicate_pending
                # / error) verbatim so the observer re-emits identical SSE.
                snap["events"].append(event)
                _flush(force=True)

        snap["status"] = "done"
        bus.write(job_id, snap)
        logger.info(
            "CHAT_TASK_COMPLETED job=%s user=%s chars=%d events=%d "
            "ttft_ms=%s total_ms=%d tokens=%d",
            job_id, user_id, len(snap["text"]), len(snap["events"]),
            round(_first_token_ms) if _first_token_ms else None,
            round((time.monotonic() - started) * 1000), _token_count,
        )

        _run_chat_post_response(user, message, conversation)

    except SoftTimeLimitExceeded:
        snap["status"] = "failed"
        snap["events"].append(
            {"type": "error", "error": "Generation timed out"}
        )
        bus.write(job_id, snap)
        logger.error("CHAT_TASK_TIMEOUT job=%s user=%s", job_id, user_id)
    except Exception as exc:
        snap["status"] = "failed"
        if not snap["text"]:
            snap["events"].append(
                {"type": "error", "error": "Generation failed"}
            )
        bus.write(job_id, snap)
        logger.error(
            "CHAT_TASK_FAILED job=%s user=%s err=%s",
            job_id, user_id, exc, exc_info=True,
        )


def _run_chat_post_response(user, message, conversation):
    """
    Post-response intelligence, relocated from the streaming view's daemon
    thread. Each extractor is independently guarded — a failure here must
    never mark the chat turn as failed. (Mirrors prior view behaviour, which
    passed an empty response string to these extractors.)
    """
    try:
        from apps.ai.learning_extraction import extract_learning
        extract_learning(user, message, "")
    except Exception as e:
        logger.debug("Chat post-response learning extraction failed: %s", e)
    try:
        from apps.ai.correction_detector import detect_correction
        detect_correction(user, message, conversation)
    except Exception as e:
        logger.debug("Chat post-response correction detection failed: %s", e)
    try:
        from apps.ai.pattern_detector import detect_patterns
        detect_patterns(user, message, "")
    except Exception as e:
        logger.debug("Chat post-response pattern detection failed: %s", e)
    try:
        from apps.core.ai_memory.life_fact_extractor import (
            extract_life_facts_from_message,
        )
        extract_life_facts_from_message(user, message, "")
    except Exception as e:
        logger.debug("Chat post-response life fact extraction failed: %s", e)


@shared_task(
    name="apps.ai.tasks.cos_keepalive_task",
    bind=True,
    max_retries=1,
    default_retry_delay=10,
    soft_time_limit=25,
    acks_late=True,
)
def cos_keepalive_task(self):
    """
    Keep CoS context warm for recently active users.

    Runs every 30 seconds via Celery Beat. Checks for users who have
    interacted in the last 5 minutes and refreshes their context cache.
    This prevents context rebuild latency on subsequent messages.

    Lightweight: only processes up to 5 users per cycle.
    Safe: read-only context builds, no LLM calls, no memory writes.
    """
    from apps.ai.readiness_cache import (
        get_active_user_ids, prewarm_cos_context, warm_openai_client,
    )
    from apps.ai.readiness_telemetry import log_keepalive_cycle

    # Ensure OpenAI client connection pool stays warm
    warm_openai_client()

    try:
        active_ids = get_active_user_ids()
        if not active_ids:
            return

        from django.contrib.auth import get_user_model
        User = get_user_model()

        refreshed = 0
        for user_id in active_ids[:5]:  # Cap at 5 per cycle
            try:
                user = User.objects.get(id=user_id)
                prewarm_cos_context(user)
                refreshed += 1
            except User.DoesNotExist:
                from apps.ai.readiness_cache import remove_active_user
                remove_active_user(user_id)
            except Exception:
                logger.debug(
                    "CoS keepalive: failed to refresh user %s", user_id
                )

        log_keepalive_cycle(len(active_ids), refreshed)

    except Exception as exc:
        logger.warning("CoS keepalive task failed: %s", exc)
        raise self.retry(exc=exc)


# =============================================================================
# Register the clean ChatGPT CoS generation task with the Celery WORKER.
# It lives in apps.ai.chatgpt_cos.tasks — a sub-package that
# `app.autodiscover_tasks()` does NOT scan (chatgpt_cos is not an INSTALLED_APP),
# so the worker would otherwise never register it. Dispatched jobs would then sit
# unconsumed and the ChatGPT CoS chat would hang forever (the bus snapshot never
# reaches a terminal status). Importing the module here — apps.ai.tasks IS
# autodiscovered — guarantees the task is registered on every worker.
# =============================================================================
from apps.ai.chatgpt_cos.tasks import (  # noqa: E402,F401
    run_chatgpt_cos_generation,
)
