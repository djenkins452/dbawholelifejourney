# ==============================================================================
# File: services.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: AI Services - Core OpenAI API wrapper with database-driven prompts
#              and optimized caching for reduced API calls
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2025-01-01
# Last Updated: 2025-12-31 (Added system prompt caching for optimization)
# ==============================================================================
"""
AI Services for Whole Life Journey - WITH DATABASE-DRIVEN PROMPTS

This module provides AI-powered insights and encouragement based on user data.
It uses OpenAI's API to generate personalized, meaningful feedback.

Both coaching styles AND prompt configurations are now database-driven for flexibility.

Caching Optimizations (2025-12-31):
- System prompts cached by user/style combination (1 hour)
- Coaching style prompts cached (1 hour)
- AIPromptConfig cached (1 hour)
"""
import logging
import threading
import time
from typing import Optional
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# LLM call resilience defaults
LLM_MAX_RETRIES = 2  # One retry after initial failure (2 total attempts)
LLM_BASE_BACKOFF_SECONDS = 1.0  # doubles each retry: 1s, 2s, 4s
LLM_TIMEOUT_SECONDS = 8  # per-request timeout for lightweight utilities

# Per-endpoint timeout strategy: CoS chat and briefing flows need longer
# timeouts because they involve large system prompts (50+ context keys)
# and generate substantial responses.
LLM_TIMEOUT_COS_CHAT = 45  # CoS chat/briefing — large prompt, long response
LLM_TIMEOUT_INTENT = 10    # Intent recognition — structured output, moderate
LLM_TIMEOUT_GENERAL = 10   # General/unclassified calls — moderate headroom
LLM_TIMEOUT_UTILITY = 8    # Lightweight utilities (summary, extraction, etc.)

# Endpoint → timeout mapping
ENDPOINT_TIMEOUTS = {
    'cos_chat': LLM_TIMEOUT_COS_CHAT,
    'cos_briefing': LLM_TIMEOUT_COS_CHAT,
    'executive_briefing': LLM_TIMEOUT_COS_CHAT,
    'proactive_briefing': LLM_TIMEOUT_COS_CHAT,
    'intent_recognition': LLM_TIMEOUT_INTENT,
    'journal_reflection': LLM_TIMEOUT_INTENT,
    'general': LLM_TIMEOUT_GENERAL,
}


def get_timeout_for_endpoint(endpoint: str) -> int:
    """Return the appropriate timeout for a given endpoint."""
    return ENDPOINT_TIMEOUTS.get(endpoint, LLM_TIMEOUT_UTILITY)

# ==========================================================================
# OpenAI Client Singleton — Thread-safe, connection-pooling
# ==========================================================================
_client_lock = threading.Lock()
_shared_openai_client = None


def get_openai_client():
    """
    Get or create the shared OpenAI client (thread-safe).

    The OpenAI Python client uses httpx internally, which maintains
    a connection pool. Reusing a single client avoids TLS handshake
    and DNS resolution overhead on subsequent calls.
    """
    global _shared_openai_client
    if _shared_openai_client is not None:
        return _shared_openai_client
    with _client_lock:
        if _shared_openai_client is not None:
            return _shared_openai_client
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            return None
        try:
            from openai import OpenAI
            _shared_openai_client = OpenAI(
                api_key=api_key,
                timeout=LLM_TIMEOUT_COS_CHAT,  # Use longest timeout as client default; per-request overrides apply
                max_retries=0,  # No retries — 429s fail immediately to avoid blocking sync workers
            )
            logger.info("OpenAI client initialized (shared singleton)")
            return _shared_openai_client
        except ImportError:
            logger.warning("OpenAI package not installed")
            return None
        except Exception as e:
            logger.error("Failed to initialize shared OpenAI client: %s", e)
            return None


def warm_openai_client():
    """
    Pre-initialize the OpenAI client. Call during wake/keepalive.

    Returns True if client is ready, False otherwise.
    """
    client = get_openai_client()
    return client is not None

# Fallback coaching style prompt if database is unavailable
FALLBACK_COACHING_PROMPT = """
Your communication style is SUPPORTIVE PARTNER:
- Be warm but balanced—like a trusted friend walking alongside them
- Gently acknowledge both wins and gaps without judgment
- Offer encouraging nudges, not demands
- Celebrate progress genuinely
- Balance accountability with encouragement
"""

# Fallback system base prompt if database is unavailable
FALLBACK_SYSTEM_BASE = """You are a life coach integrated into "Whole Life Journey," a personal
journaling and life management app. Your role is to provide personalized insights
and encouragement based on the user's data.

Core principles:
- Be specific to their actual data—never generic
- Help users see patterns and growth
- Always maintain dignity and respect
- Never shame, mock, or be condescending"""

# Fallback faith context if database is unavailable
FALLBACK_FAITH_CONTEXT = """
FAITH CONTEXT: The user has faith/spirituality enabled. You may:
- Include occasional Scripture references when naturally relevant
- Reference spiritual growth and God's faithfulness
- Use faith-based encouragement when appropriate
- But keep it natural—don't force it or be preachy"""


# Safe response guidelines when user profile is used
PROFILE_SAFETY_INSTRUCTIONS = """
IMPORTANT SAFETY GUIDELINES:
- Never provide medical, legal, financial, or spiritual advice - only supportive observations
- If the user mentions health conditions, acknowledge supportively but don't diagnose or prescribe
- Maintain respectful, encouraging tone aligned with wholesome values
- If profile content seems concerning, focus on encouragement and suggest professional support
- Never repeat the user's profile information verbatim in responses
"""


class AIService:
    """
    Core AI service for generating insights and encouragement.

    This service is designed to be:
    - Warm and encouraging (never judgmental)
    - Faith-aware (respects user's Faith module setting)
    - Privacy-conscious (processes data, doesn't store prompts)
    - Style-adaptive (gentle, supportive, or direct)
    - Consent-aware (requires explicit user consent for data processing)

    Security Note (C-3): All AI processing methods should verify user consent
    via check_user_consent() before sending data to external AI services.
    """

    def __init__(self):
        self.client = None
        self.model = settings.OPENAI_MODEL
        self._initialize_client()

    @staticmethod
    def check_user_consent(user) -> bool:
        """
        Check if user has consented to AI data processing.

        Security Fix C-3: User must explicitly consent to having their
        personal data (journal entries, health metrics, etc.) processed
        by external AI services (OpenAI).

        Args:
            user: The User model instance

        Returns:
            bool: True if user has consented, False otherwise
        """
        if not hasattr(user, 'preferences'):
            return False
        prefs = user.preferences
        # Both AI must be enabled AND consent must be given
        return prefs.ai_enabled and prefs.ai_data_consent

    def _initialize_client(self):
        """Initialize OpenAI client using the shared singleton."""
        self.client = get_openai_client()

    @property
    def is_available(self) -> bool:
        """Check if AI service is available."""
        return self.client is not None

    def _get_coaching_style_prompt(self, style: str) -> str:
        """Get the coaching style instructions from database."""
        try:
            from .models import CoachingStyle
            style_obj = CoachingStyle.get_by_key(style)
            if style_obj:
                if style_obj.prompt_instructions:
                    logger.debug(f"Loaded coaching style '{style}' (actual: {style_obj.key})")
                    return "\n" + style_obj.prompt_instructions
                else:
                    logger.warning(f"Coaching style '{style}' has empty prompt_instructions")
            else:
                logger.warning(f"Coaching style '{style}' not found in database")
        except Exception as e:
            logger.warning(f"Could not load coaching style from DB: {e}")

        # Fallback if database unavailable
        logger.info(f"Using fallback coaching prompt for style '{style}'")
        return FALLBACK_COACHING_PROMPT

    def _get_prompt_config(self, prompt_type: str):
        """Get prompt configuration from database."""
        try:
            from .models import AIPromptConfig
            return AIPromptConfig.get_config(prompt_type)
        except Exception as e:
            logger.warning(f"Could not load prompt config from DB: {e}")
            return None

    def _get_system_prompt(self, faith_enabled: bool = False,
                           coaching_style: str = 'supportive',
                           prompt_type: str = None,
                           user_profile: str = None,
                           personal_context: str = None) -> str:
        """Get the base system prompt for AI interactions.

        If prompt_type is provided and exists in database, uses that config.
        Otherwise falls back to system_base config or hardcoded defaults.

        Caching Strategy (Optimization 2025-12-31):
        - Base system prompt + coaching style + faith context is cached
        - User profile is NOT cached (too variable, needs safety processing each time)
        - Cache key: system_prompt_{coaching_style}_{faith_enabled}

        Args:
            faith_enabled: Whether faith context should be included
            coaching_style: The user's preferred coaching style
            prompt_type: Specific prompt type for database lookup
            user_profile: User's personal AI profile for personalization
            personal_context: AI-learned personal facts about the user
        """
        # Try to get cached base prompt (without user profile or personal context)
        cache_key = f'system_prompt_{coaching_style}_{faith_enabled}'
        base = cache.get(cache_key)

        if base is None:
            # Build the base prompt
            base_config = self._get_prompt_config('system_base')

            if base_config:
                base = base_config.get_full_prompt()
            else:
                # Fallback to hardcoded base
                base = FALLBACK_SYSTEM_BASE

            # Add coaching style
            base += "\n" + self._get_coaching_style_prompt(coaching_style)

            # Add faith context if enabled
            if faith_enabled:
                faith_config = self._get_prompt_config('faith_context')
                if faith_config:
                    base += "\n" + faith_config.system_instructions
                else:
                    base += FALLBACK_FAITH_CONTEXT

            # Cache the base prompt (1 hour)
            cache.set(cache_key, base, 3600)

        # Add user profile context if provided (not cached - varies per user)
        if user_profile:
            from .profile_moderation import build_safe_profile_context
            profile_context = build_safe_profile_context(user_profile)
            if profile_context:
                base += "\n\n" + profile_context
                base += "\n" + PROFILE_SAFETY_INSTRUCTIONS

        # Add AI-learned personal context if provided (not cached - varies per user)
        if personal_context:
            from .personal_context import build_personal_context_prompt
            context_prompt = build_personal_context_prompt(personal_context)
            if context_prompt:
                base += context_prompt

        return base

    def _get_prompt_with_config(self, prompt_type: str, default_prompt: str,
                                faith_enabled: bool = False,
                                coaching_style: str = 'supportive',
                                user_profile: str = None) -> tuple:
        """Get system prompt and max tokens for a specific prompt type.

        Returns (system_prompt, max_tokens) tuple.
        Uses database config if available, otherwise uses defaults.

        Args:
            prompt_type: The type of prompt to load from database
            default_prompt: Fallback prompt description
            faith_enabled: Whether faith context should be included
            coaching_style: The user's preferred coaching style
            user_profile: User's personal AI profile for personalization
        """
        config = self._get_prompt_config(prompt_type)

        if config:
            # Build system prompt with specific instructions from config
            system = self._get_system_prompt(faith_enabled, coaching_style, prompt_type, user_profile)
            system += "\n\n" + config.get_full_prompt()
            return (system, config.max_tokens)
        else:
            # Use default system prompt
            system = self._get_system_prompt(faith_enabled, coaching_style, user_profile=user_profile)
            return (system, 150)  # Default max tokens

    def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 300,
        image_data: str = None,
        image_mime_type: str = None,
        temperature: float = 0.5,
        endpoint: str = 'general',
        user=None,
        conversation_history: list = None,
        all_images: list = None,
        model: str = None,
    ) -> Optional[str]:
        """
        Make an API call to OpenAI with retry, backoff, and observability.

        Supports image attachments for Vision processing when image_data
        and image_mime_type are provided, or multiple images via all_images.

        Args:
            system_prompt: The system prompt
            user_prompt: The user's message
            max_tokens: Maximum tokens for response
            image_data: Optional base64-encoded image data (single/legacy)
            image_mime_type: Optional MIME type of the image
            temperature: Controls randomness (0.0=deterministic, 1.0=creative).
                        Default 0.5 balances accuracy with natural conversation.
                        CoS uses 0.3 for data-heavy responses and 0.5 for general chat.
            endpoint: Label for observability logging (e.g. 'cos_chat', 'journal_reflection')
            user: Optional user instance for usage logging
            conversation_history: Optional list of {"role": "user"|"assistant",
                        "content": "..."} dicts representing prior conversation turns.
                        When provided, these are inserted between the system prompt
                        and the final user message for proper conversational threading.
            all_images: Optional list of (base64, mime_type) tuples for multi-image

        Returns:
            The AI response content or None if unavailable
        """
        if not self.is_available:
            logger.warning("AI service not available - no API key configured")
            return None

        # Circuit breaker: skip if we've been rate-limited recently
        if cache.get("openai_rate_limited"):
            logger.info("LLM SKIPPED endpoint=%s — circuit breaker active (rate limited)", endpoint)
            return None

        # Build the user message content — supports multiple images
        if all_images and len(all_images) > 0:
            logger.debug("Sending vision request with %d images", len(all_images))
            user_content = [{"type": "text", "text": user_prompt}]
            for img_b64, img_mime in all_images:
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img_mime};base64,{img_b64}",
                        "detail": "auto"
                    }
                })
        elif image_data and image_mime_type:
            logger.debug(f"Sending vision request with image ({image_mime_type}, {len(image_data)} chars base64)")
            user_content = [
                {"type": "text", "text": user_prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image_mime_type};base64,{image_data}",
                        "detail": "auto"
                    }
                }
            ]
        else:
            user_content = user_prompt

        # Build message array: system → [history] → user
        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_content})

        # Token governor: enforce global budget ceiling (Phase 6)
        try:
            from apps.ai.conversation.token_governor import govern_prompt
            messages, _token_report = govern_prompt(messages)
        except ImportError:
            pass
        except Exception as _gov_err:
            logger.debug("Token governor skipped: %s", _gov_err)

        last_error = None
        _effective_timeout = get_timeout_for_endpoint(endpoint)
        for attempt in range(1, LLM_MAX_RETRIES + 1):
            start_time = time.monotonic()
            try:
                effective_model = model or self.model
                response = self.client.chat.completions.create(
                    model=effective_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=_effective_timeout,
                )
                elapsed = time.monotonic() - start_time
                result = response.choices[0].message.content.strip()

                # --- Observability: log success ---
                usage = getattr(response, 'usage', None)
                prompt_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
                completion_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
                total_tokens = getattr(usage, 'total_tokens', 0) if usage else 0

                # Store usage for latency tracer to pick up (thread-local safe
                # because each request thread has its own ai_service call chain)
                self._last_usage = {
                    'prompt_tokens': prompt_tokens,
                    'completion_tokens': completion_tokens,
                    'total_tokens': total_tokens,
                }

                logger.info(
                    "LLM OK endpoint=%s model=%s tokens=%d latency=%.2fs attempt=%d",
                    endpoint, effective_model, total_tokens, elapsed, attempt,
                )

                self._log_usage(
                    user=user,
                    endpoint=endpoint,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    success=True,
                    elapsed=elapsed,
                )

                if (image_data and image_mime_type) or all_images:
                    logger.debug(f"Vision response (first 200 chars): {result[:200]}")
                return result

            except Exception as e:
                elapsed = time.monotonic() - start_time
                last_error = e
                # Rate-limit errors need longer backoff (API may say "wait 24s")
                try:
                    from openai import RateLimitError
                    is_rate_limit = isinstance(e, RateLimitError)
                except ImportError:
                    is_rate_limit = '429' in str(e)
                if is_rate_limit:
                    cache.set("openai_rate_limited", True, timeout=120)
                    logger.warning(
                        "LLM RATE LIMITED endpoint=%s attempt=%d/%d latency=%.2fs — circuit breaker set for 120s",
                        endpoint, attempt, LLM_MAX_RETRIES, elapsed,
                    )
                else:
                    logger.warning(
                        "LLM error endpoint=%s attempt=%d/%d latency=%.2fs error=%s",
                        endpoint, attempt, LLM_MAX_RETRIES, elapsed, e,
                    )
                if attempt < LLM_MAX_RETRIES:
                    if is_rate_limit:
                        backoff = 30.0  # Wait 30s — typical 429 says ~24s
                    else:
                        backoff = LLM_BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                    time.sleep(backoff)

        # All retries exhausted
        logger.error(
            "LLM FAILED endpoint=%s model=%s retries=%d final_error=%s",
            endpoint, self.model, LLM_MAX_RETRIES, last_error,
        )
        self._log_usage(
            user=user,
            endpoint=endpoint,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            success=False,
            error_message=str(last_error)[:500],
            elapsed=0,
        )
        return None

    def _call_api_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list,
        dispatch,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        endpoint: str = 'cos_chat',
        user=None,
        conversation_history: list = None,
        model: str = None,
        max_tool_rounds: int = 3,
    ):
        """
        Bounded agentic completion (ChatGPT CoS — Phase 3).

        Same client / model / logging as ``_call_api``, but the model MAY call
        registered read-only evidence tools. We dispatch each call
        deterministically via ``dispatch(name, args_dict) -> dict`` (the CoS tool
        dispatcher — WLJ truth), feed the JSON results back, and let the model
        write the final answer. WLJ owns truth; the model only narrates it.

        Safety: read-only tools, a hard round cap, and on ANY error it falls back
        to a plain ``_call_api`` completion so the answer path never regresses.
        Vision is not supported here (callers route image turns to ``_call_api``).

        Returns the final assistant text (str), or None on total failure.
        """
        import json as _json

        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_prompt})

        # Reuse the same global token governor as _call_api.
        try:
            from apps.ai.conversation.token_governor import govern_prompt
            messages, _ = govern_prompt(messages)
        except ImportError:
            pass
        except Exception as _gov_err:
            logger.debug("Token governor skipped (tools): %s", _gov_err)

        effective_model = model or self.model
        _timeout = get_timeout_for_endpoint(endpoint)

        try:
            for _round in range(max_tool_rounds + 1):
                last_round = _round == max_tool_rounds
                kwargs = {
                    "model": effective_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "timeout": _timeout,
                }
                # On the final round, drop tools so the model MUST answer in prose.
                if not last_round:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"

                logger.info("COS_OPENAI_START endpoint=%s round=%d tools=%s",
                            endpoint, _round, not last_round)
                response = self.client.chat.completions.create(**kwargs)
                msg = response.choices[0].message
                tool_calls = getattr(msg, "tool_calls", None)
                logger.info(
                    "COS_OPENAI_FINISH endpoint=%s round=%d tool_calls=%d",
                    endpoint, _round, len(tool_calls) if tool_calls else 0,
                )

                if tool_calls and not last_round:
                    # Echo the assistant tool-call turn, then append tool results.
                    messages.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in tool_calls
                        ],
                    })
                    for tc in tool_calls:
                        try:
                            _args = _json.loads(tc.function.arguments or "{}")
                        except (ValueError, TypeError):
                            _args = {}
                        try:
                            _result = dispatch(tc.function.name, _args)
                        except Exception:
                            logger.warning(
                                "COS tool dispatch raised (tool=%s)",
                                tc.function.name, exc_info=True,
                            )
                            _result = {"ok": False, "code": "dispatch_error"}
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.function.name,
                            "content": _json.dumps(_result),
                        })
                    logger.info(
                        "COS_TOOL_ROUND endpoint=%s round=%d tool_calls=%d",
                        endpoint, _round, len(tool_calls),
                    )
                    continue  # re-call with tool results in context

                # No tool calls (or final round) -> final answer.
                return (msg.content or "").strip()
        except Exception:
            logger.warning(
                "COS tool loop failed endpoint=%s — falling back to plain completion",
                endpoint, exc_info=True,
            )

        # Fallback: plain completion (no tools) — never regress the answer path.
        return self._call_api(
            system_prompt, user_prompt, max_tokens=max_tokens,
            temperature=temperature, endpoint=endpoint, user=user,
            conversation_history=conversation_history, model=model,
        )

    def _call_api_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.5,
        endpoint: str = 'general',
        user=None,
        conversation_history: list = None,
        model: str = None,
    ):
        """
        Streaming variant of _call_api. Yields content chunks as they arrive.

        Does not support image/vision (use _call_api for image messages).
        After iteration, self._last_stream_usage is populated with token counts.

        Args:
            system_prompt: The system prompt
            user_prompt: The user's message
            max_tokens: Maximum tokens for response
            temperature: Controls randomness
            endpoint: Label for observability
            user: Optional user instance for usage logging
            conversation_history: Optional conversation history

        Yields:
            str — content chunks as they are generated.
        """
        if not self.is_available:
            logger.warning("AI service not available for streaming")
            return

        # Circuit breaker: skip if we've been rate-limited recently
        if cache.get("openai_rate_limited"):
            logger.info("LLM STREAM SKIPPED endpoint=%s — circuit breaker active", endpoint)
            return

        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_prompt})

        self._last_stream_usage = None
        last_error = None
        start_time = time.monotonic()
        _effective_timeout = get_timeout_for_endpoint(endpoint)

        for attempt in range(1, LLM_MAX_RETRIES + 1):
            try:
                effective_model = model or self.model
                stream = self.client.chat.completions.create(
                    model=effective_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                    stream_options={"include_usage": True},
                    timeout=_effective_timeout,
                )

                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content

                    # Final chunk contains usage data
                    if hasattr(chunk, 'usage') and chunk.usage:
                        elapsed = time.monotonic() - start_time
                        self._last_stream_usage = {
                            'prompt_tokens': chunk.usage.prompt_tokens,
                            'completion_tokens': chunk.usage.completion_tokens,
                            'total_tokens': chunk.usage.total_tokens,
                            'elapsed': elapsed,
                        }
                        logger.info(
                            "LLM STREAM OK endpoint=%s model=%s tokens=%d latency=%.2fs",
                            endpoint, self.model,
                            chunk.usage.total_tokens, elapsed,
                        )
                        self._log_usage(
                            user=user,
                            endpoint=endpoint,
                            prompt_tokens=chunk.usage.prompt_tokens,
                            completion_tokens=chunk.usage.completion_tokens,
                            total_tokens=chunk.usage.total_tokens,
                            success=True,
                            elapsed=elapsed,
                        )

                # Zero-token detection: stream completed but yielded nothing
                if not self._last_stream_usage or (
                    self._last_stream_usage.get('completion_tokens', 0) == 0
                ):
                    elapsed = time.monotonic() - start_time
                    logger.warning(
                        "STREAM_EMPTY_RESPONSE endpoint=%s model=%s latency=%.2fs "
                        "— stream completed but produced zero completion tokens",
                        endpoint, effective_model, elapsed,
                    )

                return  # Stream completed successfully

            except Exception as e:
                elapsed = time.monotonic() - start_time
                last_error = e
                try:
                    from openai import RateLimitError
                    is_rate_limit = isinstance(e, RateLimitError)
                except ImportError:
                    is_rate_limit = '429' in str(e)

                # Detect timeout specifically
                _is_timeout = 'timeout' in str(e).lower() or 'timed out' in str(e).lower()

                if is_rate_limit:
                    cache.set("openai_rate_limited", True, timeout=120)
                    logger.warning(
                        "LLM STREAM RATE LIMITED endpoint=%s attempt=%d/%d latency=%.2fs — circuit breaker set for 120s",
                        endpoint, attempt, LLM_MAX_RETRIES, elapsed,
                    )
                elif _is_timeout:
                    logger.error(
                        "LLM_STREAM_TIMEOUT endpoint=%s model=%s timeout=%ds "
                        "latency=%.2fs — request timed out. This causes silent "
                        "fallback to generic response.",
                        endpoint, effective_model, _effective_timeout, elapsed,
                    )
                else:
                    logger.warning(
                        "LLM STREAM error endpoint=%s attempt=%d/%d latency=%.2fs error=%s",
                        endpoint, attempt, LLM_MAX_RETRIES, elapsed, e,
                    )
                if attempt < LLM_MAX_RETRIES:
                    if is_rate_limit:
                        backoff = 30.0
                    else:
                        backoff = LLM_BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                    time.sleep(backoff)
                # Reset start_time for next attempt
                start_time = time.monotonic()

        # All retries exhausted
        logger.error(
            "LLM STREAM FAILED endpoint=%s model=%s retries=%d final_error=%s",
            endpoint, self.model, LLM_MAX_RETRIES, last_error,
        )
        self._log_usage(
            user=user,
            endpoint=endpoint,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            success=False,
            error_message=str(last_error)[:500],
            elapsed=0,
        )

    def _log_usage(self, *, user, endpoint, prompt_tokens, completion_tokens,
                   total_tokens, success, error_message='', elapsed=0):
        """Persist an AIUsageLog entry. Best-effort — never raises."""
        if not user:
            return
        try:
            from .models import AIUsageLog
            AIUsageLog.objects.create(
                user=user,
                endpoint=endpoint,
                model_used=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                success=success,
                error_message=error_message,
            )
        except Exception as log_err:
            logger.debug("AIUsageLog write failed: %s", log_err)

        # --- Owner Finance telemetry (best-effort, never raises) ---
        if success and total_tokens > 0:
            try:
                from apps.owner_finance.services.telemetry import log_llm_usage
                # Map endpoint names to LLMUsageEvent feature codes
                _endpoint_to_feature = {
                    'journal_reflection': 'JOURNAL_REFLECTION',
                    'daily_insight': 'DAILY_INSIGHT',
                    'weekly_summary': 'WEEKLY_SUMMARY',
                    'cos_chat': 'COS_CHAT',
                    'exec_briefing': 'EXEC_BRIEFING',
                }
                feature = _endpoint_to_feature.get(endpoint, 'MAIN_RESPONSE')
                log_llm_usage(
                    user=user,
                    feature=feature,
                    model_name=self.model,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                )
            except Exception:
                pass  # telemetry must never break core flow

    # =========================================================================
    # JOURNAL INSIGHTS
    # =========================================================================

    def analyze_journal_entry(self, entry_text: str, mood: str = None,
                              faith_enabled: bool = False,
                              coaching_style: str = 'supportive') -> Optional[str]:
        """
        Provide a brief, encouraging reflection on a journal entry.
        """
        system, max_tokens = self._get_prompt_with_config(
            'journal_reflection',
            'Provide journal reflection',
            faith_enabled,
            coaching_style
        )

        prompt = f"""The user just wrote this journal entry:

"{entry_text[:1500]}"
{f'Their mood: {mood}' if mood else ''}

Provide a reflection. Acknowledge what they shared
and offer encouragement or insight appropriate to your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    def detect_milestone_completion(self, entry_text: str, milestones: list,
                                     coaching_style: str = 'supportive') -> Optional[dict]:
        """
        Analyze a journal entry to detect if user may have completed a milestone.

        Args:
            entry_text: The journal entry content
            milestones: List of dicts with milestone data (title, description, goal_title)

        Returns:
            Dict with 'detected' (bool), 'milestone_index' (int), 'confidence' (str),
            'explanation' (str) if a match is detected, else None
        """
        if not milestones or not entry_text:
            return None

        # Format milestones for the prompt
        milestone_list = []
        for i, m in enumerate(milestones):
            milestone_info = f"{i+1}. \"{m['title']}\" (Goal: {m['goal_title']})"
            if m.get('description'):
                milestone_info += f" - {m['description'][:100]}"
            milestone_list.append(milestone_info)

        system = """You are an AI assistant helping users track their goal milestones.
Your job is to read a journal entry and determine if the user seems to have completed
one of their active milestones. Be reasonably confident before suggesting a match -
the user mentioned specific actions or accomplishments that align with a milestone.

Respond with JSON in this exact format:
{
    "detected": true/false,
    "milestone_index": <number 1-N or null if not detected>,
    "confidence": "high"/"medium"/"low",
    "explanation": "Brief explanation of why you think this milestone was completed"
}

Only return "detected": true if there's a clear indication the user accomplished
something related to a milestone. Generic mentions or intentions don't count."""

        prompt = f"""Journal entry:
"{entry_text[:2000]}"

Active milestones to check against:
{chr(10).join(milestone_list)}

Did this journal entry indicate completion of any of these milestones?
Respond with JSON only."""

        response = self._call_api(system, prompt, max_tokens=200)

        if not response:
            return None

        try:
            import json
            # Try to extract JSON from response
            response = response.strip()
            if response.startswith('```'):
                response = response.split('```')[1]
                if response.startswith('json'):
                    response = response[4:]
            result = json.loads(response)
            if result.get('detected') and result.get('milestone_index'):
                # Adjust to 0-based index
                result['milestone_index'] = result['milestone_index'] - 1
                return result
        except (json.JSONDecodeError, KeyError, IndexError):
            pass

        return None

    def generate_journal_summary(self, entries: list, period: str = "week",
                                  faith_enabled: bool = False,
                                  coaching_style: str = 'supportive') -> Optional[str]:
        """Generate a summary of journal entries over a period."""
        if not entries:
            return None

        system, max_tokens = self._get_prompt_with_config(
            'weekly_summary',
            'Generate journal summary',
            faith_enabled,
            coaching_style
        )

        entry_summaries = []
        for e in entries[:10]:
            summary = f"- {e.get('date', 'Unknown date')}: {e.get('title', 'Untitled')}"
            if e.get('mood'):
                summary += f" (mood: {e['mood']})"
            if e.get('body'):
                summary += f"\n  {e['body'][:200]}..."
            entry_summaries.append(summary)

        prompt = f"""Here are the user's journal entries from the past {period}:

{chr(10).join(entry_summaries)}

Provide a warm, insightful summary that:
1. Notes any themes or patterns you see
2. Acknowledges their journey
3. Offers perspective for the {period} ahead

Match your response to your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    # =========================================================================
    # DASHBOARD INSIGHTS
    # =========================================================================

    def generate_daily_insight(self, user_data: dict,
                               faith_enabled: bool = False,
                               coaching_style: str = 'supportive',
                               user_profile: str = None) -> Optional[str]:
        """Generate a personalized daily insight for the dashboard.

        Args:
            user_data: Dictionary of user activity and status data
            faith_enabled: Whether faith context should be included
            coaching_style: The user's preferred coaching style
            user_profile: User's personal AI profile for personalization
        """
        # Get system prompt and config from database
        system, max_tokens = self._get_prompt_with_config(
            'daily_insight',
            'Generate a personalized dashboard message',
            faith_enabled,
            coaching_style,
            user_profile
        )

        # Build comprehensive context from available data
        context_parts = []

        # ===================
        # TIME CONTEXT (for time-aware messaging)
        # ===================
        hour = user_data.get('hour_of_day', 12)
        # Use personalized threshold from user's activity pattern (falls back to 8.0)
        em_threshold = user_data.get('early_morning_threshold', 8.0)
        early_morning = hour < em_threshold
        late_day = hour >= 18
        if hour < em_threshold:
            time_of_day = "early morning"
        elif hour < 12:
            time_of_day = "morning"
        elif hour < 17:
            time_of_day = "afternoon"
        elif hour < 21:
            time_of_day = "evening"
        else:
            time_of_day = "night"
        context_parts.append(f"TIME OF DAY: {time_of_day} (hour {hour})")

        # ===================
        # TODAY'S DAILY HABITS STATUS (PRIORITY)
        # ===================
        habits_status = []

        if early_morning:
            # Before 8am: frame habits as "ahead of schedule" if done,
            # otherwise just note the day is starting - don't list as NOT DONE
            if user_data.get('journal_done_today'):
                habits_status.append("Journal: Already done (early riser!)")
            if user_data.get('workout_done_today'):
                habits_status.append("Workout: Already done (early riser!)")
            if user_data.get('medicines_expected_today', 0) > 0:
                taken = user_data.get('medicines_taken_today', 0)
                total = user_data.get('medicines_expected_today', 0)
                missed = user_data.get('medicines_missed_today', 0)
                upcoming = user_data.get('medicines_upcoming_today', 0)
                if missed == 0 and upcoming == 0:
                    habits_status.append(f"Medicines: ALL DONE ({taken}/{total} taken)")
                elif taken > 0:
                    habits_status.append(f"Medicines: {taken}/{total} taken so far")
                # If nothing taken yet before 8am, don't mention it
            if not habits_status:
                habits_status.append("Day is just getting started")
        else:
            # Normal hours: show full status
            # Journal status today
            if user_data.get('journal_done_today'):
                habits_status.append("Journal: DONE today")
            else:
                habits_status.append("Journal: NOT done today")

            # Workout status today
            if user_data.get('workout_done_today'):
                habits_status.append("Workout: DONE today")
            else:
                habits_status.append("Workout: NOT done today")

            # Medicine status today
            if user_data.get('medicines_expected_today', 0) > 0:
                missed = user_data.get('medicines_missed_today', 0)
                upcoming = user_data.get('medicines_upcoming_today', 0)
                taken = user_data.get('medicines_taken_today', 0)
                total = user_data.get('medicines_expected_today', 0)
                if missed == 0 and upcoming == 0:
                    habits_status.append(f"Medicines: ALL DONE ({taken}/{total} taken)")
                elif missed > 0:
                    habits_status.append(f"Medicines: {missed} OVERDUE ({taken}/{total} taken)")
                elif upcoming > 0 and taken > 0:
                    habits_status.append(f"Medicines: {taken}/{total} taken, {upcoming} later today")
                elif upcoming > 0:
                    habits_status.append(f"Medicines: {upcoming} scheduled later today")

        context_parts.append("TODAY'S DAILY HABITS: " + ", ".join(habits_status))

        # ===================
        # ANNUAL DIRECTION & PURPOSE
        # ===================
        if user_data.get('word_of_year'):
            context_parts.append(f"Word of the Year: '{user_data['word_of_year']}'")
        if user_data.get('annual_theme'):
            context_parts.append(f"Annual Theme: {user_data['annual_theme']}")
        if user_data.get('anchor_scripture'):
            context_parts.append(f"Anchor Scripture: {user_data['anchor_scripture']}")

        # Active intentions
        if user_data.get('active_intentions'):
            intentions = ', '.join(user_data['active_intentions'][:3])
            context_parts.append(f"Trying to embody: {intentions}")

        # Goals with details
        if user_data.get('goals_list'):
            for goal in user_data['goals_list'][:2]:
                domain = goal.get('domain__name', '')
                title = goal.get('title', '')
                goal.get('why_it_matters', '')[:50]
                if domain:
                    context_parts.append(f"Goal ({domain}): {title}")
                else:
                    context_parts.append(f"Goal: {title}")
        elif user_data.get('active_goals', 0) > 0:
            context_parts.append(f"Working on {user_data['active_goals']} life goals")

        # ===================
        # JOURNAL ACTIVITY (weekly context)
        # ===================
        if user_data.get('journal_count_week', 0) > 0:
            context_parts.append(f"Journaled {user_data['journal_count_week']} times this week")

        if user_data.get('current_streak', 0) > 1:
            context_parts.append(f"On a {user_data['current_streak']}-day journal streak")

        # ===================
        # TASK & PROJECT STATUS
        # ===================
        if user_data.get('completed_tasks_today', 0) > 0:
            context_parts.append(f"Completed {user_data['completed_tasks_today']} tasks today")

        if user_data.get('tasks_due_today', 0) > 0:
            context_parts.append(f"{user_data['tasks_due_today']} tasks due today")

        if user_data.get('overdue_tasks', 0) > 0:
            context_parts.append(f"{user_data['overdue_tasks']} overdue tasks need attention")

        if user_data.get('active_projects', 0) > 0:
            context_parts.append(f"{user_data['active_projects']} active projects")

        if user_data.get('priority_projects'):
            for proj in user_data['priority_projects']:
                context_parts.append(f"Priority project: {proj['title']} ({proj['progress']}% complete)")

        if user_data.get('events_today', 0) > 0:
            context_parts.append(f"{user_data['events_today']} events scheduled today")

        # ===================
        # FAITH CONTEXT
        # ===================
        if faith_enabled:
            if user_data.get('active_prayers', 0) > 0:
                context_parts.append(f"Tracking {user_data['active_prayers']} active prayers")
            if user_data.get('answered_prayers_month', 0) > 0:
                context_parts.append(f"{user_data['answered_prayers_month']} prayers answered this month")
            if user_data.get('memory_verse'):
                mv = user_data['memory_verse']
                context_parts.append(f"Memorizing: {mv['reference']}")
            if user_data.get('studying_scripture'):
                refs = ', '.join(user_data['studying_scripture'][:2])
                context_parts.append(f"Recently studied: {refs}")

        # ===================
        # HEALTH STATUS (weekly context)
        # ===================
        if user_data.get('weight_trend'):
            trend = user_data['weight_trend']
            if trend == 'down':
                context_parts.append("Weight trending down recently")
            elif trend == 'up':
                context_parts.append("Weight trending up recently")

        if user_data.get('weight_goal') and user_data.get('weight_remaining'):
            remaining = abs(user_data['weight_remaining'])
            user_data.get('weight_direction', 'lose')
            if remaining > 0:
                context_parts.append(f"{remaining} lbs to go to reach weight goal")

        if user_data.get('fasting_active'):
            hours = user_data.get('fasting_hours', 0)
            if hours:
                context_parts.append(f"Currently fasting ({hours:.1f} hours in)")
            else:
                context_parts.append("Currently in a fasting window")

        if user_data.get('calories_today'):
            cal = user_data['calories_today']
            remaining = user_data.get('calories_remaining', 0)
            if remaining > 0:
                context_parts.append(f"Logged {cal} calories today ({remaining} remaining)")

        if user_data.get('workouts_this_week', 0) > 0:
            context_parts.append(f"{user_data['workouts_this_week']} workouts this week")

        if user_data.get('recent_prs_count', 0) > 0:
            context_parts.append(f"Set {user_data['recent_prs_count']} personal records this month")

        if user_data.get('medicine_adherence_rate') is not None:
            rate = user_data['medicine_adherence_rate']
            # Always report the actual rate — never editorialize
            context_parts.append(f"Medicine adherence at {rate}% this week")

        if user_data.get('medicines_need_refill', 0) > 0:
            context_parts.append(f"{user_data['medicines_need_refill']} medicines need refill soon")

        if not context_parts:
            context_parts.append("Just getting started with their journey")

        prompt = f"""User's current status:
{chr(10).join('- ' + p for p in context_parts)}

YOUR ROLE: You're their accountability assistant. Help them stay on track today.

RULES:
1. Do NOT start with a greeting (no "Good morning", "Good evening", etc.)—the page already shows a greeting
2. Focus on INCOMPLETE daily habits (medicines, workout, journal)—tell them what needs to happen
3. Acknowledge what they've ALREADY DONE today first, then mention what's still pending
4. EARLY MORNING (before 8am): The day is just starting. Be warm and welcoming. Do NOT point out what hasn't been done yet—it's too early for that.
5. MORNING TO AFTERNOON (8am-5pm): Gentle, helpful reminders about what's still on the list
6. EVENING (after 6pm): Be more direct and urgent—the day is winding down and things need to get done
7. If everything is done, briefly say so and suggest they relax or take a break
8. Plain conversational prose only—NO markdown, NO lists, NO bullet points
9. 2-3 natural sentences maximum
10. Be direct and helpful, like a friend keeping them accountable

Generate the message now."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    def generate_accountability_nudge(self, gap_data: dict,
                                      faith_enabled: bool = False,
                                      coaching_style: str = 'supportive') -> Optional[str]:
        """
        Generate a nudge for something the user has been neglecting.

        Args:
            gap_data: Dict with info about what's been missed:
                - gap_type: 'journal', 'goal', 'task', 'health', etc.
                - days_since: days since last activity
                - item_name: specific item name if applicable
                - user_stated_importance: what user said about why it matters
        """
        system, max_tokens = self._get_prompt_with_config(
            'accountability_nudge',
            'Generate a gentle nudge',
            faith_enabled,
            coaching_style
        )

        gap_type = gap_data.get('gap_type', 'activity')
        days_since = gap_data.get('days_since', 0)
        item_name = gap_data.get('item_name', '')
        importance = gap_data.get('user_stated_importance', '')

        prompt = f"""The user has a gap in their {gap_type}:
- Days since last activity: {days_since}
{f'- Specific item: {item_name}' if item_name else ''}
{f'- They previously said this matters because: {importance}' if importance else ''}

Generate a nudge that acknowledges this gap.
Match your coaching style exactly—this is important for how you frame it."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    def generate_celebration(self, achievement_data: dict,
                             faith_enabled: bool = False,
                             coaching_style: str = 'supportive') -> Optional[str]:
        """
        Generate a celebration message for an achievement.

        Args:
            achievement_data: Dict with:
                - achievement_type: 'streak', 'goal_complete', 'milestone', etc.
                - details: specific details about what was achieved
                - streak_count: if applicable
        """
        system, max_tokens = self._get_prompt_with_config(
            'celebration',
            'Generate a celebration message',
            faith_enabled,
            coaching_style
        )

        prompt = f"""The user just achieved something:
- Type: {achievement_data.get('achievement_type', 'milestone')}
- Details: {achievement_data.get('details', 'Completed something meaningful')}
{f"- Streak count: {achievement_data.get('streak_count')}" if achievement_data.get('streak_count') else ''}

Generate a celebration message.
Match your coaching style—even Direct Coach should acknowledge wins warmly."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    # =========================================================================
    # GOAL & PURPOSE INSIGHTS
    # =========================================================================

    def analyze_goal_progress(self, goal_data: dict,
                              faith_enabled: bool = False,
                              coaching_style: str = 'supportive') -> Optional[str]:
        """Provide encouragement on goal progress."""
        system, max_tokens = self._get_prompt_with_config(
            'goal_progress',
            'Provide goal progress feedback',
            faith_enabled,
            coaching_style
        )

        prompt = f"""The user has this life goal:
Title: {goal_data.get('title', 'Untitled goal')}
Description: {goal_data.get('description', 'No description')[:500]}
Timeframe: {goal_data.get('timeframe', 'Ongoing')}
Started: {goal_data.get('created_date', 'Recently')}
Progress notes: {goal_data.get('progress_notes', 'None yet')[:300]}

Provide feedback about their goal journey.
Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    # =========================================================================
    # HEALTH INSIGHTS
    # =========================================================================

    def generate_health_encouragement(self, health_data: dict,
                                       faith_enabled: bool = False,
                                       coaching_style: str = 'supportive') -> Optional[str]:
        """Generate encouraging health insight."""
        system, max_tokens = self._get_prompt_with_config(
            'health_encouragement',
            'Generate health encouragement',
            faith_enabled,
            coaching_style
        )

        context = []
        if health_data.get('weight_entries_month', 0) > 0:
            context.append(f"Logged weight {health_data['weight_entries_month']} times this month")
        if health_data.get('weight_change'):
            direction = "down" if health_data['weight_change'] < 0 else "up"
            context.append(f"Weight is {direction} {abs(health_data['weight_change'])} lbs this month")
        if health_data.get('fasts_completed_month', 0) > 0:
            context.append(f"Completed {health_data['fasts_completed_month']} fasts this month")
        if health_data.get('avg_fast_hours'):
            context.append(f"Average fast length: {health_data['avg_fast_hours']} hours")
        if health_data.get('sleep_entries_month', 0) > 0:
            context.append(f"Logged sleep {health_data['sleep_entries_month']} times this month")
        if health_data.get('avg_sleep_hours_month'):
            context.append(f"Averaging {health_data['avg_sleep_hours_month']} hours of sleep per night")
        if health_data.get('avg_sleep_quality_month'):
            context.append(f"Sleep quality rating: {health_data['avg_sleep_quality_month']}")

        if not context:
            return None

        prompt = f"""User's health tracking this month:
{chr(10).join('- ' + c for c in context)}

Provide feedback about their health journey.
Focus on consistency and self-care. Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    def generate_glucose_insight(self, glucose_data: dict,
                                  faith_enabled: bool = False,
                                  coaching_style: str = 'supportive') -> Optional[str]:
        """
        Generate personalized insight for blood glucose dashboard.

        Args:
            glucose_data: Dictionary with glucose statistics:
                - avg_glucose: 7-day average glucose (mg/dL)
                - min_glucose: minimum reading
                - max_glucose: maximum reading
                - time_in_range: percentage of time in target range (70-180)
                - low_count: number of low events
                - high_count: number of high events
                - reading_count: total readings in period
                - latest_value: most recent reading
                - latest_status: status of latest reading (normal, high, low)
            faith_enabled: Whether faith context should be included
            coaching_style: The user's preferred coaching style
        """
        system, max_tokens = self._get_prompt_with_config(
            'glucose_insight',
            'Generate blood glucose insight',
            faith_enabled,
            coaching_style
        )

        context = []

        # Reading count context
        reading_count = glucose_data.get('reading_count', 0)
        if reading_count == 0:
            # No data yet
            prompt = """The user has no glucose readings yet.
Provide a brief, encouraging message about starting to track blood glucose.
Keep it to 2-3 sentences. Match your coaching style."""
            return self._call_api(system, prompt, max_tokens=max_tokens)

        context.append(f"{reading_count} glucose readings in the past 7 days")

        # Average and range
        if glucose_data.get('avg_glucose'):
            avg = glucose_data['avg_glucose']
            context.append(f"Average glucose: {avg} mg/dL")
            if avg < 100:
                context.append("Average is in excellent range")
            elif avg < 126:
                context.append("Average is in normal range")
            elif avg < 180:
                context.append("Average is slightly elevated")
            else:
                context.append("Average is elevated")

        # Time in range
        if glucose_data.get('time_in_range') is not None:
            tir = glucose_data['time_in_range']
            context.append(f"Time in range (70-180): {tir}%")
            if tir >= 70:
                context.append("Time in range is good")
            elif tir >= 50:
                context.append("Time in range has room for improvement")

        # Low/high events
        if glucose_data.get('low_count', 0) > 0:
            context.append(f"{glucose_data['low_count']} low glucose events (<70)")
        if glucose_data.get('high_count', 0) > 0:
            context.append(f"{glucose_data['high_count']} high glucose events (>180)")

        # Min/max range
        if glucose_data.get('min_glucose') and glucose_data.get('max_glucose'):
            context.append(f"Range: {glucose_data['min_glucose']} - {glucose_data['max_glucose']} mg/dL")

        # Latest reading
        if glucose_data.get('latest_value'):
            status = glucose_data.get('latest_status', 'normal')
            context.append(f"Most recent reading: {glucose_data['latest_value']} mg/dL ({status})")

        prompt = f"""User's blood glucose data (past 7 days):
{chr(10).join('- ' + c for c in context)}

Generate a personalized, supportive insight about their glucose management.
Focus on patterns, achievements, or gentle encouragement.
IMPORTANT: You are NOT a medical professional. Do not give medical advice.
Instead, offer observational insights and encouragement.
Keep it to 2-4 sentences. Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    # =========================================================================
    # HOME PAGE INSIGHTS
    # =========================================================================

    def generate_journal_home_insight(self, journal_data: dict,
                                       faith_enabled: bool = False,
                                       coaching_style: str = 'supportive') -> Optional[str]:
        """
        Generate personalized insight for Journal home page.

        Args:
            journal_data: Dictionary with journaling statistics
            faith_enabled: Whether faith context should be included
            coaching_style: The user's preferred coaching style
        """
        system, max_tokens = self._get_prompt_with_config(
            'journal_home',
            'Generate journal home insight',
            faith_enabled,
            coaching_style
        )

        context = []

        total = journal_data.get('total', 0)
        if total == 0:
            prompt = """The user has no journal entries yet.
Provide a brief, encouraging message about starting a journaling practice.
Keep it to 2-3 sentences. Match your coaching style."""
            return self._call_api(system, prompt, max_tokens=max_tokens)

        context.append(f"Total journal entries: {total}")

        if journal_data.get('this_week', 0) > 0:
            context.append(f"Entries this week: {journal_data['this_week']}")
        if journal_data.get('this_month', 0) > 0:
            context.append(f"Entries this month: {journal_data['this_month']}")
        if journal_data.get('streak', 0) > 0:
            context.append(f"Current streak: {journal_data['streak']} days")

        # Mood stats
        mood_stats = journal_data.get('mood_stats', [])
        if mood_stats:
            moods = [f"{m['emoji']} {m['mood']} ({m['percentage']}%)" for m in mood_stats[:3]]
            context.append(f"Recent moods: {', '.join(moods)}")

        prompt = f"""User's journaling activity:
{chr(10).join('- ' + c for c in context)}

Generate a personalized, encouraging insight about their journaling practice.
Acknowledge their consistency, note patterns, or offer gentle encouragement.
Keep it to 2-3 sentences. Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    def generate_faith_home_insight(self, faith_data: dict,
                                     coaching_style: str = 'supportive') -> Optional[str]:
        """
        Generate personalized insight for Faith home page.

        Args:
            faith_data: Dictionary with faith/spiritual activity data
            coaching_style: The user's preferred coaching style
        """
        system, max_tokens = self._get_prompt_with_config(
            'faith_home',
            'Generate faith home insight',
            True,  # Faith is always enabled for faith page
            coaching_style
        )

        context = []

        active_prayers = faith_data.get('active_prayers', 0)
        answered_prayers = faith_data.get('answered_prayers', 0)

        if active_prayers == 0 and answered_prayers == 0:
            prompt = """The user is starting their faith journey tracking.
Provide a brief, welcoming message about their spiritual practice.
Keep it to 2-3 sentences. Match your coaching style."""
            return self._call_api(system, prompt, max_tokens=max_tokens)

        if active_prayers > 0:
            context.append(f"Active prayer requests: {active_prayers}")
        if answered_prayers > 0:
            context.append(f"Answered prayers: {answered_prayers}")
        if faith_data.get('recent_reflections', 0) > 0:
            context.append(f"Recent faith reflections: {faith_data['recent_reflections']}")
        if faith_data.get('milestones', 0) > 0:
            context.append(f"Faith milestones: {faith_data['milestones']}")
        if faith_data.get('todays_verse'):
            context.append(f"Today's verse: {faith_data['todays_verse']}")

        prompt = f"""User's faith journey activity:
{chr(10).join('- ' + c for c in context)}

Generate a personalized, encouraging insight about their spiritual practice.
Acknowledge their faithfulness, celebrate answered prayers, or offer gentle encouragement.
This is a faith-focused context, so biblical references or spiritual language is appropriate.
Keep it to 2-3 sentences. Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    def generate_health_home_insight(self, health_data: dict,
                                      faith_enabled: bool = False,
                                      coaching_style: str = 'supportive') -> Optional[str]:
        """
        Generate personalized insight for Health home page.

        Args:
            health_data: Dictionary with health metrics overview
            faith_enabled: Whether faith context should be included
            coaching_style: The user's preferred coaching style
        """
        system, max_tokens = self._get_prompt_with_config(
            'health_home',
            'Generate health home insight',
            faith_enabled,
            coaching_style
        )

        context = []

        # Check if any health data exists
        has_data = any([
            health_data.get('weight_count', 0) > 0,
            health_data.get('fasts_this_month', 0) > 0,
            health_data.get('has_heart_rate'),
            health_data.get('has_glucose'),
            health_data.get('has_blood_pressure'),
            health_data.get('sleep_count', 0) > 0,
        ])

        if not has_data:
            prompt = """The user is just starting to track their health.
Provide a brief, encouraging message about starting a health tracking journey.
Keep it to 2-3 sentences. Match your coaching style."""
            return self._call_api(system, prompt, max_tokens=max_tokens)

        if health_data.get('weight_count', 0) > 0:
            context.append(f"Weight entries: {health_data['weight_count']}")
            if health_data.get('weight_change_30d') is not None:
                change = health_data['weight_change_30d']
                if change > 0:
                    context.append(f"Weight change (30 days): +{change} lbs")
                elif change < 0:
                    context.append(f"Weight change (30 days): {change} lbs")

        if health_data.get('fasts_this_month', 0) > 0:
            context.append(f"Fasts this month: {health_data['fasts_this_month']}")
            if health_data.get('avg_fast_duration'):
                context.append(f"Average fast duration: {health_data['avg_fast_duration']} hours")

        if health_data.get('avg_resting_hr'):
            context.append(f"Average resting heart rate: {health_data['avg_resting_hr']} bpm")

        if health_data.get('avg_fasting_glucose'):
            context.append(f"Average fasting glucose: {health_data['avg_fasting_glucose']} mg/dL")

        if health_data.get('avg_blood_pressure'):
            context.append(f"Average blood pressure: {health_data['avg_blood_pressure']}")

        if health_data.get('sleep_count', 0) > 0:
            context.append(f"Sleep entries (7 days): {health_data['sleep_count']}")
            if health_data.get('avg_sleep_hours'):
                context.append(f"Average sleep: {health_data['avg_sleep_hours']} hours/night")
            if health_data.get('avg_sleep_quality'):
                context.append(f"Average sleep quality: {health_data['avg_sleep_quality']}")
            if health_data.get('sleep_trend'):
                context.append(f"Sleep trend: {health_data['sleep_trend']}")

        prompt = f"""User's health overview:
{chr(10).join('- ' + c for c in context)}

Generate a personalized, supportive insight about their health tracking.
Note patterns, celebrate consistency, or offer gentle encouragement.
IMPORTANT: You are NOT a medical professional. Do not give medical advice.
Keep it to 2-3 sentences. Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    def generate_life_home_insight(self, life_data: dict,
                                    faith_enabled: bool = False,
                                    coaching_style: str = 'supportive') -> Optional[str]:
        """
        Generate personalized insight for Life home page.

        Args:
            life_data: Dictionary with life management data
            faith_enabled: Whether faith context should be included
            coaching_style: The user's preferred coaching style
        """
        system, max_tokens = self._get_prompt_with_config(
            'life_home',
            'Generate life home insight',
            faith_enabled,
            coaching_style
        )

        context = []

        has_data = any([
            life_data.get('active_projects', 0) > 0,
            life_data.get('pending_tasks', 0) > 0,
            life_data.get('completed_tasks', 0) > 0,
            life_data.get('todays_events', 0) > 0,
        ])

        if not has_data:
            prompt = """The user is starting to organize their life.
Provide a brief, encouraging message about life organization.
Keep it to 2-3 sentences. Match your coaching style."""
            return self._call_api(system, prompt, max_tokens=max_tokens)

        if life_data.get('active_projects', 0) > 0:
            context.append(f"Active projects: {life_data['active_projects']}")
        if life_data.get('pending_tasks', 0) > 0:
            context.append(f"Pending tasks: {life_data['pending_tasks']}")
        if life_data.get('completed_tasks', 0) > 0:
            context.append(f"Completed tasks: {life_data['completed_tasks']}")
        if life_data.get('overdue_tasks', 0) > 0:
            context.append(f"Overdue tasks: {life_data['overdue_tasks']}")
        if life_data.get('todays_events', 0) > 0:
            context.append(f"Events today: {life_data['todays_events']}")
        if life_data.get('upcoming_events', 0) > 0:
            context.append(f"Upcoming events (7 days): {life_data['upcoming_events']}")
        if life_data.get('now_tasks', 0) > 0:
            context.append(f"Priority 'Now' tasks: {life_data['now_tasks']}")

        prompt = f"""User's life management overview:
{chr(10).join('- ' + c for c in context)}

Generate a personalized, encouraging insight about their day and tasks.
Acknowledge their organization, note priorities, or offer gentle encouragement.
Keep it to 2-3 sentences. Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    def generate_purpose_home_insight(self, purpose_data: dict,
                                       faith_enabled: bool = False,
                                       coaching_style: str = 'supportive') -> Optional[str]:
        """
        Generate personalized insight for Purpose home page.

        Args:
            purpose_data: Dictionary with purpose/goals data
            faith_enabled: Whether faith context should be included
            coaching_style: The user's preferred coaching style
        """
        system, max_tokens = self._get_prompt_with_config(
            'purpose_home',
            'Generate purpose home insight',
            faith_enabled,
            coaching_style
        )

        context = []

        has_data = any([
            purpose_data.get('word_of_year'),
            purpose_data.get('annual_theme'),
            purpose_data.get('active_goals', 0) > 0,
            purpose_data.get('active_intentions', 0) > 0,
        ])

        if not has_data:
            prompt = """The user is starting to define their purpose and direction.
Provide a brief, inspiring message about discovering purpose.
Keep it to 2-3 sentences. Match your coaching style."""
            return self._call_api(system, prompt, max_tokens=max_tokens)

        if purpose_data.get('word_of_year'):
            context.append(f"Word of the Year: '{purpose_data['word_of_year']}'")
        if purpose_data.get('annual_theme'):
            context.append(f"Annual Theme: {purpose_data['annual_theme']}")
        if purpose_data.get('active_goals', 0) > 0:
            context.append(f"Active goals: {purpose_data['active_goals']}")
        if purpose_data.get('completed_goals', 0) > 0:
            context.append(f"Completed goals: {purpose_data['completed_goals']}")
        if purpose_data.get('active_intentions', 0) > 0:
            context.append(f"Active intentions: {purpose_data['active_intentions']}")
        if purpose_data.get('domains'):
            context.append(f"Life domains with goals: {purpose_data['domains']}")

        prompt = f"""User's purpose and direction:
{chr(10).join('- ' + c for c in context)}

Generate a personalized, inspiring insight about their goals and direction.
Connect to their word/theme if present, celebrate progress, or encourage focus.
Keep it to 2-3 sentences. Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    # =========================================================================
    # FAITH INSIGHTS
    # =========================================================================

    def generate_prayer_encouragement(self, prayer_data: dict,
                                       coaching_style: str = 'supportive') -> Optional[str]:
        """Generate encouragement around prayer life."""
        system, max_tokens = self._get_prompt_with_config(
            'prayer_encouragement',
            'Generate prayer encouragement',
            faith_enabled=True,
            coaching_style=coaching_style
        )

        context = []
        if prayer_data.get('active_count', 0) > 0:
            context.append(f"Tracking {prayer_data['active_count']} active prayers")
        if prayer_data.get('answered_count', 0) > 0:
            context.append(f"{prayer_data['answered_count']} prayers answered")
        if prayer_data.get('recent_themes'):
            context.append(f"Recent prayer themes: {', '.join(prayer_data['recent_themes'][:3])}")

        prompt = f"""User's prayer life:
{chr(10).join('- ' + c for c in context) if context else '- Just starting their prayer tracking'}

Provide encouragement about their prayer journey.
You may include a short, relevant Scripture reference if it fits naturally.
Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)


# Singleton instance
ai_service = AIService()
