# ==============================================================================
# File: apps/ai/chatgpt_cos/acceptance_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Shared Beth acceptance RUNNER. Executes the validation questions
#   through the REAL chat path (ChatGPTCoSService.generate), evaluates each
#   response with the shared rules, persists an AcceptanceRun + AcceptanceResults,
#   and generates the ChatGPT-review and Claude-fix prompts. Called by BOTH the
#   `beth_acceptance` management command and the Admin Console (via a Celery task).
#
#   Read-only validation: generate() does not persist chat messages, send
#   notifications, fire proactive behavior, or mutate user data. The throwaway
#   conversation is deleted after the run.
# ==============================================================================
import logging
import os
import re
import time
from contextlib import contextmanager

from django.utils import timezone

from apps.ai.chatgpt_cos.acceptance_rules import (
    QUESTIONS, evaluate, questions_for, GOAL_INTENTS,
)

logger = logging.getLogger(__name__)


# ---- telemetry capture (intent / lane / fallback / openai-called) ----------
class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception:
            pass


_INTENT_RE = re.compile(r"intent=([a-z_]+)")
_LANE_RE = re.compile(r"\blane=([a-z_]+)")


def parse_telemetry(lines):
    intent = lane = None
    fallback_used = None
    openai_called = False
    for ln in lines:
        if "BETH_GOAL_ROUTE_RESULT" in ln or "COS_REASONING_GOAL_PREROUTE" in ln:
            m = _INTENT_RE.search(ln)
            if m:
                intent = m.group(1)
        if "COS_REASONING_RESPONSE" in ln:
            m = _INTENT_RE.search(ln)
            if m:
                intent = m.group(1)
            if "fallback=True" in ln:
                fallback_used = True
            elif "fallback=False" in ln:
                fallback_used = False
                openai_called = True
        if "BETH_GENERAL_CALL" in ln:
            lane = "general_conversation"
            if "call_outcome=content" in ln:
                openai_called = True
            if "fallback_used=True" in ln:
                fallback_used = True
            elif "fallback_used=False" in ln:
                fallback_used = False
        if "COS_LANE_TRACE" in ln and lane is None:
            m = _LANE_RE.search(ln)
            if m:
                lane = m.group(1)
        if "LLM RESPONSE" in ln or "call_outcome=content" in ln:
            openai_called = True
    return intent, lane, fallback_used, openai_called


@contextmanager
def _telemetry():
    cap = _Capture()
    cap.setLevel(logging.DEBUG)
    loggers = [logging.getLogger("apps.ai.chatgpt_cos"),
               logging.getLogger("apps.ai"),
               logging.getLogger("apps.ai.services")]
    for lg in loggers:
        lg.addHandler(cap)
    try:
        yield cap
    finally:
        for lg in loggers:
            lg.removeHandler(cap)


def environment_label():
    env = os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("DJANGO_ENV")
    return env or ("production" if not os.environ.get("DEBUG") else "development")


def git_commit():
    return (os.environ.get("RAILWAY_GIT_COMMIT_SHA", "") or "development")[:12]


# ---- run a single question through the real chat path ----------------------
def run_one(svc, conversation, spec, evening=False):
    text = spec["text"]
    patches = []
    if spec.get("evening") and evening:
        from unittest.mock import patch
        patches.append(patch(
            "apps.core.cos_briefing.daily_agenda._user_hour", return_value=21))
    for p in patches:
        p.start()
    t0 = time.monotonic()
    answer, intent, lane, fb, openai = "", None, None, None, False
    try:
        with _telemetry() as cap:
            res = svc.generate(conversation, text) or {}
        answer = (res.get("answer") or "").strip()
        lane = res.get("lane")
        intent, plane, fb, openai = parse_telemetry(cap.lines)
        lane = lane or plane
    except Exception as exc:
        logger.warning("beth_acceptance run_one failed key=%s", spec.get("key"),
                       exc_info=True)
        answer = f"<EXCEPTION: {type(exc).__name__}: {exc}>"
    finally:
        for p in patches:
            p.stop()
    elapsed = round((time.monotonic() - t0) * 1000)
    fails = evaluate(spec, answer, intent=intent, lane=lane)
    if answer.startswith("<EXCEPTION"):
        fails = ["exception"] + fails
    return {
        "key": spec["key"], "suite": _suite_of(spec), "question": text,
        "answer": answer, "expected_intent": spec.get("expect_intent", ""),
        "expected_lane": spec.get("expect_lane", ""), "intent": intent, "lane": lane,
        "fallback_used": fb, "openai_called": openai, "ms": elapsed,
        "required": spec.get("required", []) + spec.get("required_any", []),
        "forbidden": spec.get("forbidden", []),
        "fails": fails, "passed": not fails,
    }


def _suite_of(spec):
    from apps.ai.chatgpt_cos.acceptance_rules import suite_of
    return suite_of(spec)


# ---- the orchestrator: fill an AcceptanceRun in place ----------------------
def execute_run(run, evening=True):
    """Run `run.suite_name` against the live stack, persist results onto `run`,
    compute score + prompts, and mark the run completed/failed. Returns `run`."""
    from django.contrib.auth import get_user_model
    from apps.ai.models import AssistantConversation
    from apps.ai.chatgpt_cos.service import ChatGPTCoSService
    from apps.admin_console.models import AcceptanceResult

    run.status = "running"
    run.started_at = timezone.now()
    run.environment = run.environment or environment_label()
    run.git_commit = run.git_commit or git_commit()
    run.save(update_fields=["status", "started_at", "environment", "git_commit"])

    User = get_user_model()
    user = run.target_user or User.objects.filter(is_superuser=True).first()
    if user is None:
        run.status = "failed"
        run.error_message = "No target user available."
        run.completed_at = timezone.now()
        run.save()
        return run

    conv = AssistantConversation.objects.create(
        user=user, title="[acceptance] Beth validation", session_type="general",
        is_active=False)
    svc = ChatGPTCoSService(user)
    specs = questions_for(run.suite_name)
    rows = []
    t0 = time.monotonic()
    try:
        for i, spec in enumerate(specs):
            r = run_one(svc, conv, spec, evening=evening)
            rows.append(r)
            AcceptanceResult.objects.create(
                run=run, question_key=r["key"], suite=r["suite"],
                question_text=r["question"], expected_intent=r["expected_intent"] or "",
                expected_lane=r["expected_lane"] or "", actual_intent=r["intent"] or "",
                actual_lane=r["lane"] or "", response_text=r["answer"],
                response_time_ms=r["ms"], passed=r["passed"], failed_rules=r["fails"],
                required_concepts=r["required"], forbidden_concepts=r["forbidden"],
                openai_called=r["openai_called"],
                fallback_used=r["fallback_used"], raw_result_json=r, sort_order=i)
    finally:
        try:
            conv.delete()      # never pollute chat history
        except Exception:
            pass

    # Cross-intent distinctness (goal intents must not duplicate verbatim).
    seen = {}
    for r in rows:
        if r["intent"] in GOAL_INTENTS:
            norm = (r["answer"] or "").strip().lower()
            if norm and norm in seen:
                r["fails"].append("duplicate_answer")
                r["passed"] = False
            seen[norm] = r["key"]

    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    run.total_count = total
    run.pass_count = passed
    run.fail_count = total - passed
    run.score_percent = round(passed / total * 100) if total else 0
    run.duration_ms = round((time.monotonic() - t0) * 1000)
    run.status = "completed"
    run.completed_at = timezone.now()
    run.raw_report_json = {"rows": rows, "suite": run.suite_name}
    run.chatgpt_review_prompt = build_chatgpt_review_prompt(run, rows)
    run.claude_fix_prompt = build_claude_fix_prompt(run, rows)
    # persist the recomputed pass flags onto the result rows
    for r, obj in zip(rows, run.results.order_by("sort_order")):
        if obj.passed != r["passed"]:
            obj.passed = r["passed"]
            obj.failed_rules = r["fails"]
            obj.save(update_fields=["passed", "failed_rules"])
    run.save()
    return run


def create_and_execute(suite="full", target_user=None, created_by=None, evening=True):
    """Convenience for the CLI: create the AcceptanceRun then execute it."""
    from apps.admin_console.models import AcceptanceRun
    run = AcceptanceRun.objects.create(
        suite_name=suite, target_user=target_user, created_by=created_by,
        environment=environment_label(), git_commit=git_commit())
    return execute_run(run, evening=evening)


# ---- prompt generators -----------------------------------------------------
def _header(run):
    return (f"Environment: {run.environment}\n"
            f"Commit: {run.git_commit}\n"
            f"Timestamp: {run.completed_at or run.created_at}\n"
            f"Suite: {run.suite_name}\n"
            f"Score: {run.score_percent}%  ({run.pass_count}/{run.total_count} passed, "
            f"{run.fail_count} failed)\n"
            f"Duration: {run.duration_ms} ms\n")


def build_chatgpt_review_prompt(run, rows):
    failed = [r for r in rows if not r["passed"]]
    passed_suites = sorted({r["suite"] for r in rows if r["passed"]})
    lines = [
        "You are reviewing an automated acceptance run for 'Beth', a personal "
        "Chief-of-Staff AI inside a wellness app. Assess release readiness — do NOT "
        "ask me follow-up questions; everything you need is below.\n",
        _header(run),
        f"Passing suites (at least one pass): {', '.join(passed_suites) or 'none'}\n",
    ]
    if failed:
        lines.append(f"\nFAILED QUESTIONS ({len(failed)}):")
        for r in failed:
            lines.append(
                f"\n- [{r['key']}] suite={r['suite']}\n"
                f"  Q: {r['question']}\n"
                f"  expected_intent={r['expected_intent'] or '-'} "
                f"actual_intent={r['intent'] or '-'} lane={r['lane'] or '-'} "
                f"openai={r['openai_called']} fallback={r['fallback_used']} "
                f"time={r['ms']}ms\n"
                f"  failed_rules: {', '.join(r['fails'])}\n"
                f"  actual_response: {r['answer'][:600]}")
    else:
        lines.append("\nNo failed questions — every response passed its rules.")
    lines.append(
        "\n\nPlease:\n"
        "1. Assess release readiness for Beth.\n"
        "2. Identify the most likely root cause of each failure.\n"
        "3. Prioritize the fixes (highest user impact first).\n"
        "4. Recommend whether Beth is ready for a 'beth-stable-v3' tag.\n"
        "5. Suggest any missing acceptance tests we should add.")
    return "\n".join(lines)


def build_claude_fix_prompt(run, rows):
    failed = [r for r in rows if not r["passed"]]
    lines = [
        "This is an implementation task for Claude Code working in the WLJ Django "
        "repo. Fix the failing Beth acceptance questions below.\n",
        _header(run),
    ]
    if not failed:
        lines.append("\nThe run is GREEN — no fixes required. If you want, add new "
                     "acceptance questions to harden coverage.")
    else:
        lines.append(f"\nFAILING QUESTIONS TO FIX ({len(failed)}):")
        for r in failed:
            lines.append(
                f"\n- [{r['key']}] suite={r['suite']}\n"
                f"  Question: {r['question']}\n"
                f"  Expected: routes to intent '{r['expected_intent'] or '(correct domain)'}' "
                f"and passes rules.\n"
                f"  Actual: intent={r['intent'] or '-'} lane={r['lane'] or '-'} "
                f"openai={r['openai_called']} fallback={r['fallback_used']}.\n"
                f"  Failed rules: {', '.join(r['fails'])}\n"
                f"  Actual response: {r['answer'][:600]}")
    lines.append(
        "\n\nInstructions:\n"
        "- Fix the ROOT CAUSE of each failure (routing, reasoning, fallback, or "
        "phrasing) — not the symptom.\n"
        "- Add or update automated tests covering each fixed behavior.\n"
        "- Preserve all currently-passing behaviors (Health byte-identical; goals "
        "differentiation intact).\n"
        "- Re-run the acceptance suite (manage.py beth_acceptance or the Admin "
        "Console Beth Acceptance Center) until green.\n"
        "- Deploy to main when green.\n"
        "- Do not stop for approval unless there is a migration, security issue, or "
        "architectural conflict.")
    return "\n".join(lines)
