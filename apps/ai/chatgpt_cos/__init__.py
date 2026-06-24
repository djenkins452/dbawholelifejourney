# ==============================================================================
# File: apps/ai/chatgpt_cos/__init__.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Clean ChatGPT Chief of Staff conversation path (NO legacy Beth)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
ChatGPT CoS — clean conversation path.

When `UserPreferences.use_chatgpt_cos=True`, the chat view branches here BEFORE
any legacy Beth conversational logic. This package owns the entire path:

    user message -> ChatGPTCoSService -> standing context -> OpenAI tool loop
      -> WLJ deterministic truth tools -> ChatGPT final answer -> persist

It reuses ONLY: the CoS service layer (apps/ai/cos_services), the generic tool
loop (AIService._call_api_with_tools), conversation/message models,
chat_stream_bus + Celery, the feature flag, and the distinct header.

It does NOT touch: PersonalAssistant.send_message[_stream], the deterministic
router, check-in/morning renderers, persona narration, validators, fallback
composition, or legacy intent recognition. WLJ owns truth; ChatGPT owns the
conversation.
"""
