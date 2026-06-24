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

from apps.ai.cos_gateway.envelope import (
    MIGRATED_SURFACES,
    RUNTIME_CHATGPT,
    RUNTIME_LEGACY,
    CoSResponse,
)
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
    def is_cos(user) -> bool:
        """True when ChatGPT CoS owns this user's conversation."""
        return CoSGateway.resolve_runtime(user).name == RUNTIME_CHATGPT

    # ------------------------------------------------------------------
    # Phase 0A.2 — narrative-bearing surfaces.
    #
    # These surfaces are produced by legacy Beth narrators/renderers/coaching
    # generators. There is no CoS-native equivalent yet, so for CoS users the
    # gateway SUPPRESSES the conversational output — the legacy producer is
    # NEVER invoked (no silent Beth fallback). Truth/data the surface computes
    # from canonical providers is unaffected.
    # ------------------------------------------------------------------
    @staticmethod
    def structured(*, user, surface, legacy, suppressed):
        """Route a STRUCTURED narrative surface. `legacy` and `suppressed` are
        zero-/one-arg callables returning the final response payload. For CoS
        users only `suppressed(reason)` runs; `legacy` (the Beth producer) is
        never called."""
        if CoSGateway.is_cos(user):
            reason = (f"ChatGPT CoS '{surface}' narrative is not yet "
                      f"implemented; suppressed (no legacy Beth fallback).")
            logger.info("COS_GATEWAY_SUPPRESS user=%s surface=%s",
                        getattr(user, "id", None), surface)
            return suppressed(reason)
        return legacy()

    @staticmethod
    def narrative(*, user, surface, legacy_producer=None) -> CoSResponse:
        """Gateway-owned conversational text for an action endpoint. The action
        is executed by the caller (truth); only the language is gated here. CoS
        users get a suppressed envelope; the legacy text producer is not run."""
        if CoSGateway.is_cos(user):
            return CoSResponse(
                text="", runtime=RUNTIME_CHATGPT, surface=surface,
                suppressed=True,
                suppressed_reason=(f"ChatGPT CoS '{surface}' confirmation is "
                                   f"not yet implemented; suppressed."),
            )
        text = (legacy_producer() if legacy_producer else "") or ""
        return CoSResponse(text=text, runtime=RUNTIME_LEGACY, surface=surface)

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
