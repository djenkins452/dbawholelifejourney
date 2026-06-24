# ==============================================================================
# File: apps/ai/cos_gateway/gateway.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Phase 0A — the single interactive conversational gateway
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
CoSGateway.respond — the ONE interactive conversational entry point.

Responsibilities (and only these):
  1. Resolve runtime ownership ONCE (evidence_tools_enabled = the canonical
     resolver for use_chatgpt_cos + the global override).
  2. Invoke the selected runtime behind the ConversationalRuntime interface.
  3. Return a standardized CoSResponse envelope.

No conversational surface decides runtime ownership; the gateway does.
"""

import logging

from apps.ai.cos_gateway.envelope import MIGRATED_SURFACES, CoSResponse
from apps.ai.cos_gateway.runtime import ChatGPTCoSRuntime, LegacyBethRuntime

logger = logging.getLogger(__name__)


class CoSGateway:

    @staticmethod
    def resolve_runtime(user):
        """Return the runtime instance that owns this user's conversation."""
        from apps.ai.cos_services.tool_registry import evidence_tools_enabled
        if evidence_tools_enabled(user):
            return ChatGPTCoSRuntime()
        return LegacyBethRuntime()

    @staticmethod
    def respond(*, user, surface, message=None, conversation=None,
                page_context=None, stream=False, **kwargs) -> CoSResponse:
        if surface not in MIGRATED_SURFACES:
            raise ValueError(
                f"CoSGateway: surface '{surface}' is not migrated in Phase 0A "
                f"(migrated: {sorted(MIGRATED_SURFACES)})."
            )
        runtime = CoSGateway.resolve_runtime(user)
        logger.info(
            "COS_GATEWAY_DISPATCH user=%s surface=%s runtime=%s stream=%s",
            getattr(user, "id", None), surface, runtime.name, bool(stream),
        )
        return runtime.respond(
            user=user, surface=surface, message=message,
            conversation=conversation, page_context=page_context,
            stream=stream, **kwargs,
        )
