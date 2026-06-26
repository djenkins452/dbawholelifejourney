# ==============================================================================
# File: apps/ai/chatgpt_cos/service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: ChatGPTCoSService — the clean ChatGPT CoS reasoning path
# ==============================================================================
"""
ChatGPTCoSService owns the clean ChatGPT CoS answer.

generate() loads standing context, gives the OpenAI model the WLJ tool catalog,
runs the bounded tool loop (the model calls deterministic truth tools), and
returns the model-authored answer. No legacy Beth component participates.
"""

import json
import logging

from django.conf import settings

logger = logging.getLogger("apps.ai.chatgpt_cos")

_HISTORY_MESSAGES = 6
_HISTORY_CHARS = 1800
_STANDING_CHARS = 6000

_SYSTEM_PROMPT = """You are {cos_name}, {first_name}'s Chief of Staff.

WLJ owns the truth; you own the conversation. Answer ONLY from deterministic data
you retrieve through the tools — never invent facts, numbers, or status.

Tools:
- get_foundational_health_facts(keys): focused scalar health facts. ALWAYS use
  this for specific factual health questions — current_weight, last_glucose_reading,
  average_glucose_yesterday, sleep_last_night, calories_today, protein_today,
  current_medications, weight_30_day_change. Pass only the keys you need.
- get_standing_context: the user's always-loaded holistic state. Use for "how am
  I doing" / overall questions.
- get_domain_state(domain): one life domain's FULL current state. Use for broad
  overviews — 'faith' (prayer/scripture), 'purpose' (goals), 'meals', 'journal',
  'relationships', 'calendar', 'finance'. For a specific scalar HEALTH fact use
  get_foundational_health_facts instead (the full health domain is large).
- get_decision(mode): WLJ's deterministic decision — 'execution' (what to do
  next / focus today), 'risk' (biggest risk right now), 'fix' (what to clean up
  first). Use these for focus/risk/fix questions; narrate the result, do not
  invent your own.
- search_history(query, domain, timeframe): the user's past data.
- execute_action(action, params): perform a write (create_task, complete_task,
  create_goal, create_journal_entry, log_prayer, save_verse, create_event,
  log_habit, log_workout, ...). If the result is 'confirmation_required', ask the
  user to confirm, then re-call with confirmed=true.

Rules:
- If a tool result status is 'pending', 'no_state_source', 'empty', 'denied', or
  'error', say so honestly and specifically — do NOT fall back to a generic
  answer or invent the data.
- Be concise, direct, and warm. No filler greeting unless it fits.

Current standing context (already loaded for you):
{standing}
"""


class ChatGPTCoSService:
    def __init__(self, user):
        self.user = user

    # ------------------------------------------------------------------
    def _cos_name(self):
        try:
            prefs = getattr(self.user, "preferences", None)
            if prefs is not None and hasattr(prefs, "get_cos_name"):
                return prefs.get_cos_name()
        except Exception:
            pass
        return "Chief of Staff"

    def _history(self, conversation, current_message):
        """Clean conversation history from the message model (no Beth builder)."""
        try:
            recent = list(
                conversation.messages.order_by("-created_at")[:_HISTORY_MESSAGES + 2]
            )
        except Exception:
            return []
        recent = [m for m in reversed(recent) if (m.content or "").strip()]
        # Drop the just-persisted current user turn (it is the prompt).
        if (recent and recent[-1].role == "user"
                and recent[-1].content.strip() == (current_message or "").strip()):
            recent = recent[:-1]
        out = []
        for m in recent[-_HISTORY_MESSAGES:]:
            role = "assistant" if m.role == "assistant" else "user"
            out.append({"role": role, "content": (m.content or "")[:_HISTORY_CHARS]})
        return out

    def _system_prompt(self, standing):
        try:
            standing_json = json.dumps(standing, default=str)[:_STANDING_CHARS]
        except Exception:
            standing_json = "{}"
        return _SYSTEM_PROMPT.format(
            cos_name=self._cos_name(),
            first_name=(getattr(self.user, "first_name", "") or "Danny"),
            standing=standing_json,
        )

    # ------------------------------------------------------------------
    def generate(self, conversation, message, page_context=None, request_id=None):
        """
        Returns dict: {answer, tools_advertised, tools_called}.
        Raises on hard failure (the Celery task handles + persists the error).
        """
        from apps.ai.cos_services import (
            dispatch_tool_call,
            get_standing_context,
            get_tool_schemas,
        )
        from apps.ai.services import ai_service

        # The clean path runs in a background Celery task, so synchronous warming
        # is allowed here (no request-path "never live-compute" constraint).
        # Warm the SAE snapshot ONCE and pin it on the user so standing context
        # AND every get_domain_state tool call read REAL data instead of a cold
        # 'pending' shell (this is why weight/faith previously read as pending).
        try:
            from apps.core.ai_state.state_engine import get_user_state
            self.user._sae_cache = get_user_state(self.user, allow_rebuild=True)
        except Exception:
            logger.warning("chatgpt_cos: SAE warm failed", exc_info=True)

        # CONVERSATION LANE REGISTRY (framework-first, P6/P13) — ordered:
        #   Foundational Facts -> Personal Reasoning -> Clarification -> General.
        # The first two are the existing lanes (deterministic facts + the health
        # reasoning lane), wrapped UNCHANGED. The Clarification lane gracefully
        # asks instead of failing on ambiguous requests (deterministic, no LLM);
        # the General lane answers non-personal questions in a SANDBOX (no
        # personal/SAE data). If every lane declines, fall through to the tool
        # loop below (the terminal fallback, P8).
        from apps.ai.chatgpt_cos.lanes import route_message
        _routed = route_message(self.user, message)
        if _routed is not None:
            return _routed

        standing = get_standing_context(
            self.user, page_context=page_context, allow_build=True,
        )
        system_prompt = self._system_prompt(standing)
        history = self._history(conversation, message)
        tools = get_tool_schemas(enabled_only=True)
        advertised = [t["function"]["name"] for t in tools]
        called = []

        def _dispatch(name, args):
            called.append(name)
            return dispatch_tool_call(self.user, name, args)

        logger.info(
            "COS_TOOL_LOOP_START user=%s advertised=%s standing=%s",
            self.user.id, ",".join(advertised),
            (standing.get("status") if isinstance(standing, dict) else "?"),
        )
        try:
            answer = ai_service._call_api_with_tools(
                system_prompt,
                message,
                tools=tools,
                dispatch=_dispatch,
                endpoint="cos_chat",
                user=self.user,
                conversation_history=history,
                model=getattr(settings, "COS_MODEL", None),
            )
        except Exception:
            logger.error("COS_EXCEPTION user=%s stage=tool_loop",
                         self.user.id, exc_info=True)
            raise
        # Classify an empty answer BEFORE collapsing None->"" so the task can
        # show a diagnostic-safe message (never a silent "couldn't compose").
        #   answer is None  -> tool loop raised, fallback _call_api returned None
        #                      (OpenAI error / retry exhaustion).
        #   answer == ""    -> model returned empty content after tool execution.
        final = (answer or "").strip()
        empty_reason = None
        if not final:
            empty_reason = ("openai_fallback_empty" if answer is None
                            else "model_empty_after_tools")
        logger.info(
            "COS_TOOL_LOOP_FINISH user=%s tools_called=%s answer_len=%d "
            "empty_reason=%s",
            self.user.id, ",".join(called) or "none", len(final),
            empty_reason or "none",
        )
        return {
            "answer": final,
            "empty_reason": empty_reason,
            "tools_advertised": advertised,
            "tools_called": called,
        }
