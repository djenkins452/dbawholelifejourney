# ==============================================================================
# File: apps/ai/cos_gateway/__init__.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Phase 0A — Single Interactive Conversational Gateway
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
Single Interactive Conversational Gateway (Phase 0A)
====================================================

One request → one gateway → one runtime → one response.

For use_chatgpt_cos=True users, ChatGPTCoSRuntime is the SOLE conversational
runtime on every migrated interactive surface; zero legacy conversational code
executes (enforced by the quarantine tripwire + import-drift tests). For
use_chatgpt_cos=False users, LegacyBethRuntime preserves existing behavior.
"""

from apps.ai.cos_gateway.envelope import (
    ENVELOPE_VERSION,
    MIGRATED_SURFACES,
    RUNTIME_CHATGPT,
    RUNTIME_LEGACY,
    SURFACE_CHAT,
    SURFACE_CHAT_STREAM,
    CoSResponse,
)
from apps.ai.cos_gateway.gateway import CoSGateway
from apps.ai.cos_gateway.runtime import (
    ChatGPTCoSRuntime,
    ConversationalRuntime,
    LegacyBethRuntime,
)

__all__ = [
    "CoSGateway",
    "CoSResponse",
    "ConversationalRuntime",
    "ChatGPTCoSRuntime",
    "LegacyBethRuntime",
    "ENVELOPE_VERSION",
    "MIGRATED_SURFACES",
    "RUNTIME_CHATGPT",
    "RUNTIME_LEGACY",
    "SURFACE_CHAT",
    "SURFACE_CHAT_STREAM",
]
