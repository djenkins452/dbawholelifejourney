# ==============================================================================
# File: apps/ai/management/commands/validate_model_interface.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Pre-live validation harness for the Model Interface runtime.
# ==============================================================================
"""
Controlled integration harness for the WLJ ↔ conversational-model interface.

Exercises the REAL model-interface runtime against a real account with a REAL
conversational model — the full stack (AI Relationship projection, Current Context,
truth tools + truth envelope, tool audit, stateful action confirmation) — WITHOUT:
  * creating a normal chat conversation (isolated; no AssistantMessage rows), and
  * modifying any user data (actions run in DRY-RUN by default — the single write path
    `IntentService.execute_intent` is stubbed to a simulated result).

It answers one question: "If we turned this on for the owner right now, would we trust it?"

Usage:
    python manage.py validate_model_interface --email you@example.com --scenario all \
        --dry-run-actions

    # opt into REAL writes (not recommended for validation):
    python manage.py validate_model_interface --email you@example.com --live-actions
"""

import json
import os
import time
from types import SimpleNamespace
from unittest import mock

from django.core.management.base import BaseCommand, CommandError


# --- scenarios ----------------------------------------------------------------
# Each scenario is one or more user turns; `expect` documents what good looks like.
SCENARIOS = [
    {
        "key": "general",
        "title": "General conversation (should NOT pull personal truth)",
        "turns": ["What's a good general approach to building a morning routine?"],
        "expect_no_truth_tools": True,
    },
    {
        "key": "planning",
        "title": "Planning (has Current Context baseline available)",
        "turns": ["Help me think through how to prioritize my day."],
    },
    {
        "key": "health_trend",
        "title": "Health trend (should pull health truth; must not fabricate)",
        "turns": ["How has my sleep been trending lately?"],
        "expect_truth_tools": ["get_foundational_health_facts", "get_domain_state"],
    },
    {
        "key": "unavailable",
        "title": "Unavailable info (should state insufficient evidence)",
        "turns": ["What was my exact blood pressure at 3:00 PM last Tuesday?"],
    },
    {
        "key": "action",
        "title": "Action request (dry-run; confirmation flow)",
        "turns": [
            "Please move my task 'Empty the dishwasher' to 9:00 PM today.",
            "Yes, go ahead and move it to 9:00 PM.",
        ],
        "expect_action": True,
    },
    {
        "key": "history",
        "title": "History question (should call history tools)",
        "turns": ["What have I written about my family recently?"],
        "expect_truth_tools": ["search_history"],
    },
    {
        "key": "relationship",
        "title": "Relationship behavior (AI Relationship is honored)",
        "turns": ["Give me a quick status check on where things stand."],
    },
]


class Command(BaseCommand):
    help = "Pre-live validation harness for the Model Interface runtime (real model)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--scenario", default="all",
                            help="'all' or a scenario key.")
        parser.add_argument("--dry-run-actions", action="store_true", default=True,
                            help="(default) Actions are simulated; no data is modified.")
        parser.add_argument("--live-actions", action="store_true", default=False,
                            help="Danger: execute REAL writes. Off by default.")
        parser.add_argument("--model", default=None,
                            help="Model id override (default settings.COS_MODEL).")
        parser.add_argument("--keep-audit", action="store_true", default=False,
                            help="Keep the validation ToolCallLog rows (default: clean up).")

    # -- helpers ---------------------------------------------------------------
    def _real_ai_service(self, model):
        """An AIService with a REAL OpenAI client built from the environment key
        (settings.OPENAI_API_KEY may be unset in this process)."""
        from apps.ai.services import AIService
        key = os.environ.get("OPENAI_API_KEY") or getattr(
            __import__("django.conf", fromlist=["settings"]).settings,
            "OPENAI_API_KEY", "")
        if not key:
            raise CommandError(
                "No OPENAI_API_KEY available in this process. Set it in the "
                "environment before running the harness (a real model is required).")
        from openai import OpenAI
        svc = AIService()
        svc.client = OpenAI(api_key=key, timeout=60, max_retries=1)
        return svc

    def _dry_run_patch(self):
        """Stub the single write path so actions are simulated, not executed."""
        from apps.ai.intent_service import IntentService

        def _fake_execute_intent(self_svc, intent, user, *a, **kw):
            return SimpleNamespace(
                success=True, error=None,
                message=(f"[DRY RUN] would execute '{intent.intent_type}' "
                         f"with {json.dumps(intent.parameters, default=str)}"),
            )
        return mock.patch.object(IntentService, "execute_intent",
                                 new=_fake_execute_intent)

    def _run_scenario(self, svc, user, scenario, model):
        """Run one scenario (possibly multi-turn) and return a structured record."""
        from apps.ai.model_interface.service import ModelInterfaceService

        mi = ModelInterfaceService(user, ai_service=svc)
        history = []
        tool_trace = []          # [{turn, name, args, result_status, freshness, ...}]
        turns_out = []
        t0 = time.monotonic()
        turn_ids = []

        for i, message in enumerate(scenario["turns"]):
            captured = []

            def observer(name, args, result, _cap=captured):
                _cap.append({"name": name, "args": args, "result": result})

            request_id = f"validate-{scenario['key']}-{i}"
            turn_ids.append(request_id)
            result = mi.generate(
                SimpleNamespace(id=f"validate-{scenario['key']}"),
                message, request_id=request_id, surface="chat",
                observer=observer, conversation_history=list(history),
            )
            answer = result.get("answer", "")
            for c in captured:
                tool_trace.append({"turn": i, **c})
            turns_out.append({"user": message, "assistant": answer,
                              "tools_called": result.get("tools_called", [])})
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": answer})

        duration_ms = (time.monotonic() - t0) * 1000.0

        # Standing context (AI Relationship + Current Context) from the last turn.
        standing = result.get("standing_context", {})
        # Audit rows for this scenario.
        from apps.ai.models import ToolCallLog
        audit = list(ToolCallLog.objects.filter(
            user=user, turn_id__in=turn_ids).order_by("created_at").values(
            "kind", "tool_name", "result_status", "args", "result_digest", "created_at"))

        warnings = self._warnings(scenario, tool_trace, turns_out, audit)
        return {
            "scenario": scenario,
            "turns": turns_out,
            "tool_trace": tool_trace,
            "standing_context": standing,
            "audit": audit,
            "warnings": warnings,
            "duration_ms": duration_ms,
            "turn_ids": turn_ids,
        }

    def _warnings(self, scenario, tool_trace, turns_out, audit):
        w = []
        truth_tools_called = [t["name"] for t in tool_trace
                              if t["name"] in ("get_domain_state", "search_history",
                                               "get_foundational_health_facts")]
        if scenario.get("expect_no_truth_tools") and truth_tools_called:
            w.append(f"Expected NO personal truth pulls, but called: "
                     f"{truth_tools_called}")
        if scenario.get("expect_truth_tools") and not truth_tools_called:
            w.append(f"Expected a truth pull ({scenario['expect_truth_tools']}) but "
                     f"none was called — check for fabrication in the answer.")
        if scenario.get("expect_action"):
            statuses = [a["result_status"] for a in audit if a["kind"] == "action"]
            if "confirmation_required" not in statuses:
                w.append("Expected a confirmation_required action; not observed.")
        # Cheap fabrication heuristic: a specific-looking numeric claim with no truth pull.
        if not truth_tools_called:
            for t in turns_out:
                a = t["assistant"] or ""
                if any(tok in a for tok in ("mg/dL", "bpm", " hrs", " hours of sleep")):
                    w.append("Answer contains specific metrics with no truth pull — "
                             "verify this is not fabricated.")
                    break
        return w

    # -- output ----------------------------------------------------------------
    def _print(self, rec):
        s = rec["scenario"]
        line = "═" * 78
        self.stdout.write(f"\n{line}\nSCENARIO: {s['title']}  [{s['key']}]\n{line}")

        self.stdout.write("\n▶ CONVERSATION")
        for t in rec["turns"]:
            self.stdout.write(f"  USER: {t['user']}")
            self.stdout.write(f"  AI:   {t['assistant']}")
            if t["tools_called"]:
                self.stdout.write(f"        (tools: {', '.join(t['tools_called'])})")

        self.stdout.write("\n▶ TOOL CALLS / TRUTH RETURNED")
        if not rec["tool_trace"]:
            self.stdout.write("  (none)")
        for t in rec["tool_trace"]:
            res = t["result"]
            status = res.get("status") if isinstance(res, dict) else res
            fresh = res.get("freshness") if isinstance(res, dict) else None
            conf = res.get("confidence") if isinstance(res, dict) else None
            self.stdout.write(f"  • {t['name']}({json.dumps(t['args'], default=str)})")
            self.stdout.write(f"      → status={status} freshness={fresh} "
                              f"confidence={conf}")
            snippet = json.dumps(res, default=str)[:280]
            self.stdout.write(f"      → {snippet}")

        rel = rec["standing_context"].get("ai_relationship", {})
        self.stdout.write("\n▶ AI RELATIONSHIP (projected into context)")
        self.stdout.write(f"  name={rel.get('assistant', {}).get('display_name')} "
                          f"relationship={rel.get('assistant', {}).get('default_relationship')}")
        self.stdout.write(f"  communication={rel.get('communication')}")
        self.stdout.write(f"  truth_preferences={rel.get('truth_preferences')}")
        self.stdout.write(f"  learned_preferences={rel.get('learned_preferences')}")

        cc = rec["standing_context"].get("current_context", {})
        self.stdout.write("\n▶ CURRENT CONTEXT (baseline)")
        self.stdout.write(f"  clock={cc.get('clock')}")
        self.stdout.write(f"  priority={cc.get('priority')}")
        self.stdout.write(f"  day_continuity={cc.get('day_continuity')}")
        self.stdout.write(f"  capabilities={cc.get('capabilities', {}).get('answerable_domains')}")

        self.stdout.write("\n▶ AUDIT ENTRIES")
        for a in rec["audit"]:
            self.stdout.write(
                f"  [{a['created_at'].strftime('%H:%M:%S')}] {a['kind']:9s} "
                f"{a['tool_name'] or '-':32s} status={a['result_status']}  "
                f"digest={json.dumps(a['result_digest'], default=str)[:120]}")

        self.stdout.write(f"\n▶ WARNINGS")
        if rec["warnings"]:
            for wn in rec["warnings"]:
                self.stdout.write(f"  ⚠ {wn}")
        else:
            self.stdout.write("  ✓ none")

        self.stdout.write(f"\n▶ DURATION: {rec['duration_ms']:.0f} ms")

    # -- entry -----------------------------------------------------------------
    def handle(self, *args, **opts):
        from django.contrib.auth import get_user_model
        from django.conf import settings

        User = get_user_model()
        try:
            user = User.objects.get(email__iexact=opts["email"])
        except User.DoesNotExist:
            raise CommandError(f"No user with email {opts['email']}")

        model = opts["model"] or getattr(settings, "COS_MODEL", "gpt-4o")
        live = opts["live_actions"]
        dry = not live

        which = opts["scenario"]
        scenarios = SCENARIOS if which == "all" else [
            s for s in SCENARIOS if s["key"] == which]
        if not scenarios:
            raise CommandError(f"Unknown scenario '{which}'. "
                               f"Options: all, {', '.join(s['key'] for s in SCENARIOS)}")

        self.stdout.write(self.style.WARNING(
            f"\nModel Interface Validation Harness\n"
            f"  user={user.email}  model={model}  "
            f"actions={'DRY-RUN (no data modified)' if dry else 'LIVE WRITES'}\n"
            f"  isolated: no chat conversation is created.\n"))
        if live:
            self.stdout.write(self.style.ERROR(
                "  !! LIVE ACTIONS ENABLED — real data may be modified.\n"))

        svc = self._real_ai_service(model)

        # Warm the Current Context cache the way the prod background worker would, so
        # priority / clinical-safety / day-continuity are populated (never live-computed
        # on the request path — the runtime only ever READS this cache).
        from apps.ai.model_interface import context_warm
        warmed = context_warm.warm(user)
        self.stdout.write(
            f"  warmed Current Context: priority="
            f"{(warmed or {}).get('priority_action')}\n")

        # Clear any stale pending confirmation before we start.
        from apps.ai.intent_service import IntentService
        IntentService().clear_pending_confirmation(user)

        records = []
        ctx = self._dry_run_patch() if dry else _nullcontext()
        with ctx:
            for s in scenarios:
                try:
                    rec = self._run_scenario(svc, user, s, model)
                except Exception as exc:
                    rec = {"scenario": s, "turns": [], "tool_trace": [],
                           "standing_context": {}, "audit": [],
                           "warnings": [f"HARNESS ERROR: {exc!r}"],
                           "duration_ms": 0.0, "turn_ids": []}
                records.append(rec)
                self._print(rec)
                IntentService().clear_pending_confirmation(user)  # isolate scenarios

        # Summary.
        self.stdout.write("\n" + "═" * 78 + "\nSUMMARY\n" + "═" * 78)
        total_warn = 0
        for rec in records:
            n = len(rec["warnings"])
            total_warn += n
            flag = self.style.SUCCESS("✓") if n == 0 else self.style.WARNING(f"⚠ {n}")
            self.stdout.write(f"  {flag}  {rec['scenario']['title']}")
        verdict = (self.style.SUCCESS("No warnings — review transcript for judgment.")
                   if total_warn == 0 else
                   self.style.WARNING(f"{total_warn} warning(s) — review before enabling."))
        self.stdout.write(f"\n  {verdict}")

        # Cleanup: remove validation audit rows unless asked to keep them.
        if not opts["keep_audit"]:
            from apps.ai.models import ToolCallLog
            all_turn_ids = [tid for rec in records for tid in rec["turn_ids"]]
            deleted, _ = ToolCallLog.objects.filter(
                user=user, turn_id__in=all_turn_ids).delete()
            self.stdout.write(f"\n  (cleaned up {deleted} validation audit rows; "
                              f"pass --keep-audit to retain)")
        self.stdout.write("")


class _nullcontext:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False
