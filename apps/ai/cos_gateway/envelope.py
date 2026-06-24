# ==============================================================================
# File: apps/ai/cos_gateway/envelope.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Phase 0A — standard conversational response envelope + surface IDs
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
Standard envelope every interactive conversational surface consumes.

The envelope is the ONLY shape a migrated surface sees — it never learns which
runtime produced it. `text` is the conversational answer; `stream_job_id` is set
for SSE surfaces (the view builds the StreamingHttpResponse from it); `meta`
carries non-conversational extras (conversation_id, tools_called, and — for the
legacy runtime — the raw legacy result dict so existing JSON contracts are
preserved byte-for-byte for flag-OFF users).
"""

from dataclasses import dataclass, field
from typing import Literal, Optional

ENVELOPE_VERSION = 1

# Runtime identifiers
RUNTIME_CHATGPT = "chatgpt_cos"
RUNTIME_LEGACY = "legacy_beth"

# Interactive conversational surfaces migrated in Phase 0A.
SURFACE_CHAT = "chat"                 # non-streaming chat (/api/chat/)
SURFACE_CHAT_STREAM = "chat_stream"   # streaming chat (/api/chat/stream/)

# Full set the gateway currently accepts.
MIGRATED_SURFACES = frozenset({SURFACE_CHAT, SURFACE_CHAT_STREAM})


@dataclass
class CoSResponse:
    text: str
    runtime: Literal["chatgpt_cos", "legacy_beth"]
    surface: str
    stream_job_id: Optional[str] = None
    envelope_version: int = ENVELOPE_VERSION
    meta: dict = field(default_factory=dict)
