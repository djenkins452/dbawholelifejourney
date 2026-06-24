# ==============================================================================
# File: apps/ai/management/commands/validate_cos_tools.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Live end-to-end validation harness for the ChatGPT CoS tool loop
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
Live validation harness for the ChatGPT CoS evidence-tool loop (Phase 3/4).

Runs REAL OpenAI conversations through the existing bounded tool loop
(`AIService._call_api_with_tools`) and proves the full chain:

    ChatGPT -> tool selection -> dispatch -> deterministic WLJ truth ->
    tool result -> final synthesized answer

For each scenario it prints: the prompt, every tool call the model made (name +
args + dispatch ok/status), and the final synthesized answer. The dispatcher's
own `COS_TOOL` telemetry and the loop's `COS_TOOL_ROUND` lines also emit to logs.

Run in a SAFE (non-production) environment where OPENAI_API_KEY is set:

    python manage.py validate_cos_tools --email you@example.com
    python manage.py validate_cos_tools --email you@example.com --model gpt-4o

This is a DEV validation tool (not a production one-off). It does not write any
user data; every tool it exercises is read-only.
"""

import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()

# The required live-validation scenarios (master prompt) + the tool we expect.
SCENARIOS = [
    ("How am I doing?", "get_standing_context"),
    ("What is my current weight?", "get_domain_state(health)"),
    ("How is my faith life going?", "get_domain_state(faith)"),
    ("What goals are stalled?", "get_domain_state(purpose/goals)"),
    ("What should I focus on today?", "get_decision(execution)"),
    ("What is my biggest risk right now?", "get_decision(risk)"),
    ("What should I fix first?", "get_decision(fix)"),
]

SYSTEM_PROMPT = (
    "You are the user's Chief of Staff. WLJ owns the truth; you own the "
    "understanding. You MUST answer from deterministic WLJ data retrieved via "
    "the provided tools — never invent facts. Call get_standing_context for "
    "holistic 'how am I doing' questions, get_domain_state(domain) for a "
    "specific life domain (e.g. health for weight, faith, purpose for goals), "
    "and get_decision(mode) for what-to-do-next (execution), biggest-risk "
    "(risk), or what-to-fix-first (fix). If a tool result status is 'pending' "
    "or 'no_state_source', say so honestly. Keep answers brief."
)


class Command(BaseCommand):
    help = "Live end-to-end validation of the ChatGPT CoS evidence-tool loop."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True,
                            help="Email of the user to run the validation as.")
        parser.add_argument("--model", default=None,
                            help="Override model (default: settings.COS_MODEL).")

    def handle(self, *args, **opts):
        key = getattr(settings, "OPENAI_API_KEY", "") or ""
        if not key:
            raise CommandError(
                "OPENAI_API_KEY is not set in this environment. Run this in a "
                "safe non-production environment that has a real key."
            )

        try:
            user = User.objects.get(email=opts["email"])
        except User.DoesNotExist:
            raise CommandError(f"No user with email {opts['email']}")

        model = opts["model"] or getattr(settings, "COS_MODEL", None)

        # Force the flag ON for this process only (does not touch settings.py).
        settings.WLJ_COS_EVIDENCE_TOOLS_ENABLED = True

        from apps.ai.cos_services.tool_dispatcher import dispatch_tool_call
        from apps.ai.cos_services.tool_registry import (
            enabled_tool_names,
            get_tool_schemas,
        )
        from apps.ai.services import ai_service

        tools = get_tool_schemas(enabled_only=True)
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nCoS tool-loop live validation — user={user.email} model={model}"
        ))
        self.stdout.write(f"Enabled tools: {enabled_tool_names()}\n")

        passed = 0
        for prompt, expected in SCENARIOS:
            captured = []

            def _capturing_dispatch(name, args, _cap=captured):
                env = dispatch_tool_call(user, name, args)
                result = env.get("result")
                status = result.get("status") if isinstance(result, dict) else None
                _cap.append({
                    "tool": name, "args": args,
                    "ok": env.get("ok"), "status": status,
                    "code": env.get("code"),
                })
                return env

            self.stdout.write(self.style.HTTP_INFO(f"\n── Scenario: {prompt!r}"))
            self.stdout.write(f"   expected tool: {expected}")
            try:
                answer = ai_service._call_api_with_tools(
                    SYSTEM_PROMPT, prompt, tools=tools,
                    dispatch=_capturing_dispatch, endpoint="cos_chat",
                    user=user, model=model,
                )
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"    LOOP ERROR: {exc}"))
                continue

            if captured:
                for c in captured:
                    self.stdout.write(self.style.SUCCESS(
                        f"   tool_call → {c['tool']}({json.dumps(c['args'])}) "
                        f"ok={c['ok']} status={c['status']} code={c['code']}"
                    ))
                passed += 1
            else:
                self.stdout.write(self.style.WARNING(
                    "   (model returned no tool call)"
                ))
            self.stdout.write(f"   final answer: {answer}")

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nValidation complete: {passed}/{len(SCENARIOS)} scenarios "
            f"invoked a tool.\n"
        ))
