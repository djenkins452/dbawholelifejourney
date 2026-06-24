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

# --- Phase 0A.1: full-conversation surfaces (text envelope, routed) ---
SURFACE_CHAT = "chat"                 # non-streaming chat (/api/chat/)
SURFACE_CHAT_STREAM = "chat_stream"   # streaming chat (/api/chat/stream/)

# Surfaces the routed gateway (respond) accepts — the runtime OWNS the whole turn.
MIGRATED_SURFACES = frozenset({SURFACE_CHAT, SURFACE_CHAT_STREAM})

# --- Phase 0A.2: narrative-bearing surfaces (gateway-owned; suppressed for CoS) ---
# These surfaces SPEAK to the user but are produced by legacy Beth narrators /
# renderers / coaching generators. With no CoS-native equivalent yet, the gateway
# SUPPRESSES the conversational output for CoS users (never silent Beth fallback).
SURFACE_STATE_ASSESSMENT = "state_assessment"
SURFACE_WEEKLY = "weekly_analysis"
SURFACE_MONTHLY = "monthly_analysis"
SURFACE_OPENING = "opening"
SURFACE_BRIEFING = "proactive_briefing"
SURFACE_SESSION_START = "session_start"
SURFACE_PRIORITIES = "daily_priorities"
SURFACE_REFLECTION = "reflection_prompt"
SURFACE_DRIFT = "drift"
SURFACE_GOALS = "goal_progress"
SURFACE_QUICK_REPLY = "quick_reply"          # action survives; message suppressed
SURFACE_EVENT_REFLECTION = "event_reflection"  # action survives; message suppressed

NARRATIVE_SURFACES = frozenset({
    SURFACE_STATE_ASSESSMENT, SURFACE_WEEKLY, SURFACE_MONTHLY, SURFACE_OPENING,
    SURFACE_BRIEFING, SURFACE_SESSION_START, SURFACE_PRIORITIES,
    SURFACE_REFLECTION, SURFACE_DRIFT, SURFACE_GOALS, SURFACE_QUICK_REPLY,
    SURFACE_EVENT_REFLECTION,
})


@dataclass
class CoSResponse:
    text: str
    runtime: Literal["chatgpt_cos", "legacy_beth"]
    surface: str
    stream_job_id: Optional[str] = None
    envelope_version: int = ENVELOPE_VERSION
    meta: dict = field(default_factory=dict)
    suppressed: bool = False
    suppressed_reason: Optional[str] = None
