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
    QUESTIONS, evaluate, questions_for, GOAL_INTENTS, categorize_rule,
    is_critical_rule, grade as grade_run, RELEASE_THRESHOLD,
)

SLOW_MS = 9000      # a response slower than this earns a warning

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
        "distinct_group": spec.get("distinct_group", ""),
        "criticality": spec.get("criticality", "normal"),
        "spec": spec, "fails": fails, "passed": not fails,
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
    specs = questions_for(run.suite_name, run.depth or "full")
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

    _detect_duplicates(rows)
    _finalize(run, rows, round((time.monotonic() - t0) * 1000))
    return run


def _detect_duplicates(rows):
    """Within each distinct_group, answers from DIFFERENT intents that are
    substantially identical (same normalized text OR same first 20 words) are
    duplicates. Paraphrases of the SAME intent are allowed to match."""
    def norm(a):
        return " ".join((a or "").strip().lower().split())

    def first20(a):
        return " ".join(norm(a).split()[:20])

    groups = {}
    for r in rows:
        g = r.get("distinct_group")
        if g:
            groups.setdefault(g, []).append(r)
    for members in groups.values():
        seen_full, seen_head = {}, {}
        for r in members:
            if not r["answer"] or r["answer"].startswith("<EXCEPTION"):
                continue
            nf, nh = norm(r["answer"]), first20(r["answer"])
            for store, key in ((seen_full, nf), (seen_head, nh)):
                prev = store.get(key)
                if prev and prev["intent"] != r["intent"]:
                    r["fails"].append("duplicate_answer")
                    r["passed"] = False
                store.setdefault(key, r)


def _finalize(run, rows, duration_ms):
    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    # per-row criticality + slow + category, persisted to the result objects
    category = {}
    critical = warnings = 0
    objs = list(run.results.order_by("sort_order"))
    for r, obj in zip(rows, objs):
        r_critical = any(is_critical_rule(f, r.get("spec")) for f in r["fails"]) \
            or (not r["passed"] and r.get("criticality") == "critical")
        r_slow = r["ms"] >= SLOW_MS
        if r_critical:
            critical += 1
        if r_slow:
            warnings += 1
        for f in r["fails"]:
            cat = categorize_rule(f)
            category[cat] = category.get(cat, 0) + 1
        obj.passed = r["passed"]
        obj.failed_rules = r["fails"]
        obj.is_critical = r_critical
        obj.is_slow = r_slow
        obj.save(update_fields=["passed", "failed_rules", "is_critical", "is_slow"])

    run.total_count = total
    run.pass_count = passed
    run.fail_count = total - passed
    run.score_percent = round(passed / total * 100) if total else 0
    run.duration_ms = duration_ms
    run.avg_response_ms = round(sum(r["ms"] for r in rows) / total) if total else 0
    run.critical_count = critical
    run.warning_count = warnings
    run.category_summary = category
    run.grade = grade_run(run.score_percent, critical)
    run.status = "completed"
    run.completed_at = timezone.now()
    run.raw_report_json = {"rows": [{k: v for k, v in r.items() if k != "spec"}
                                    for r in rows],
                           "suite": run.suite_name, "depth": run.depth}
    run.chatgpt_review_prompt = build_chatgpt_review_prompt(run, rows)
    run.claude_fix_prompt = build_claude_fix_prompt(run, rows)
    run.save()


def create_and_execute(suite="full", depth="full", target_user=None,
                       created_by=None, evening=True):
    """Convenience for the CLI: create the AcceptanceRun then execute it."""
    from apps.admin_console.models import AcceptanceRun
    run = AcceptanceRun.objects.create(
        suite_name=suite, depth=depth, target_user=target_user, created_by=created_by,
        environment=environment_label(), git_commit=git_commit())
    return execute_run(run, evening=evening)


# ---- failure analytics + prompt generators ---------------------------------
def _category_summary(rows):
    cats = {}
    for r in rows:
        for f in r["fails"]:
            c = categorize_rule(f)
            cats[c] = cats.get(c, 0) + 1
    return cats


_CATEGORY_ORDER = ["banned_phrase", "missing_required", "wrong_domain",
                   "empty_response", "duplicate_answer", "general_failure",
                   "checkin_time_awareness", "forbidden_concept", "response_quality",
                   "slow_response"]


def _root_cause_groups(failed):
    """Group failures into likely systemic root-cause buckets (Claude prompt)."""
    groups = []
    has = lambda pred: [r for r in failed if any(pred(f) for f in r["fails"])]
    coaching = [r for r in failed if any(
        f.startswith("banned_phrase:") and f.split(":", 1)[1] in COACHING_HINT for f in r["fails"])]
    if coaching:
        groups.append(("Legacy generic coaching language leaking into LLM goal answers.",
                       coaching))
    system = has(lambda f: f.startswith("banned_phrase:") and any(
        s in f for s in ("source of truth", "state builder", "momentum score",
                         "confidence score", "signal", "canonical")))
    if system:
        groups.append(("Internal/system language leaking to the user.", system))
    deflect = has(lambda f: f.startswith("banned_phrase:") and any(
        s in f for s in ("dashboard", "goals page", "open the app", "navigate")))
    if deflect:
        groups.append(("Deflection — pointing the user elsewhere instead of answering.",
                       deflect))
    slipping = [r for r in failed if r["key"].startswith("goal_concern")
                or r.get("expected_intent") == "goal_concerns"]
    if slipping:
        groups.append(("Goal 'slipping' filter — the concerns answer lists healthy "
                       "goals or misses the slipping/none requirement.", slipping))
    routing = has(lambda f: f.startswith("wrong_domain"))
    if routing:
        groups.append(("Routing — questions reaching the wrong domain/intent.", routing))
    general = [r for r in failed if r["suite"] == "general"]
    if general:
        groups.append(("General-knowledge lane reliability (empty/failure/rate-limit).",
                       general))
    quality = has(lambda f: f.startswith(("gate_", "too_short")))
    if quality:
        groups.append(("Response quality — missing evidence/synthesis/actionable step.",
                       quality))
    return groups


# coaching phrases (for grouping) — kept as a module set to avoid re-import cost
from apps.ai.chatgpt_cos.acceptance_rules import COACHING_BANNED as COACHING_HINT  # noqa: E402


def _summary_block(run, rows):
    failed = [r for r in rows if not r["passed"]]
    cats = run.category_summary or _category_summary(rows)
    passed_suites = {}
    for r in rows:
        passed_suites.setdefault(r["suite"], [0, 0])
        passed_suites[r["suite"]][0 if r["passed"] else 1] += 1
    dupes = [r["key"] for r in rows if "duplicate_answer" in r["fails"]]
    slow = [(r["key"], r["ms"]) for r in rows if r["ms"] >= SLOW_MS]
    openai_fail = sum(1 for r in rows if "openai_failure_message" in r["fails"]
                      or (not r["openai_called"] and r["suite"] == "general"))
    status = "PASS" if (run.grade == "GREEN") else "FAIL"
    lines = [
        "OVERALL RESULT:",
        f"  Pass rate: {run.score_percent}% ({run.pass_count}/{run.total_count})",
        f"  Release threshold: {RELEASE_THRESHOLD}% and zero critical failures",
        f"  Grade: {run.grade}   Current status: {status}",
        f"  Critical failures: {run.critical_count}   Warnings(slow): {run.warning_count}"
        f"   Avg response: {run.avg_response_ms} ms",
        "",
        "FAILURE SUMMARY BY CATEGORY:",
    ]
    for c in _CATEGORY_ORDER:
        lines.append(f"  - {c}: {cats.get(c, 0)}")
    lines.append("")
    lines.append("SUITE RESULTS (pass/fail):")
    for s, (p, f) in sorted(passed_suites.items()):
        lines.append(f"  - {s}: {p} passed, {f} failed")
    lines.append("")
    lines.append(f"OpenAI/fallback failure count: {openai_fail}")
    lines.append(f"Duplicate-answer warnings: {', '.join(dupes) or 'none'}")
    lines.append("Slow responses (>9s): "
                 + (", ".join(f"{k}={ms}ms" for k, ms in slow) or "none"))
    return "\n".join(lines), failed


def build_chatgpt_review_prompt(run, rows):
    summary, failed = _summary_block(run, rows)
    lines = [
        "You are reviewing an automated acceptance run for 'Beth', a personal "
        "Chief-of-Staff AI. Assess RELEASE READINESS. Identify SYSTEMIC failure "
        "patterns, not just individual failed questions. Do NOT ask me follow-up "
        "questions — everything you need is below.\n",
        f"Environment: {run.environment}   Commit: {run.git_commit}   "
        f"Suite: {run.suite_name}/{run.depth}   Time: {run.completed_at or run.created_at}\n",
        summary,
        "",
        "TOP FAILURE THEMES (you fill these in): identify the 1-3 systemic themes "
        "behind the failures above.",
    ]
    if failed:
        lines.append(f"\nFAILED QUESTIONS ({len(failed)}):")
        for r in failed:
            crit = " [CRITICAL]" if any(
                is_critical_rule(f, r.get("spec")) for f in r["fails"]) else ""
            lines.append(
                f"\n- [{r['key']}] suite={r['suite']} depth={r.get('spec',{}).get('depth','')}{crit}\n"
                f"  Q: {r['question']}\n"
                f"  expected_intent={r['expected_intent'] or '-'} "
                f"actual_intent={r['intent'] or '-'} lane={r['lane'] or '-'} "
                f"openai={r['openai_called']} fallback={r['fallback_used']} time={r['ms']}ms\n"
                f"  failed_rules: {', '.join(r['fails'])}\n"
                f"  actual_response: {r['answer'][:500]}")
    else:
        lines.append("\nNo failed questions — every response passed its rules.")
    lines.append(
        "\n\nRELEASE READINESS — please answer:\n"
        "1. Identify the systemic failure patterns (the defect CLASSES), not just "
        "individual questions.\n"
        "2. Stable-tag eligible (beth-stable-v3): yes/no, and why.\n"
        "3. Blocking failures (the critical ones that must be fixed first).\n"
        "4. Recommended fix priority order.\n"
        "5. Any missing acceptance tests we should add.")
    return "\n".join(lines)


def build_claude_fix_prompt(run, rows):
    failed = [r for r in rows if not r["passed"]]
    lines = [
        "This is an implementation task for Claude Code in the WLJ Django repo. Fix "
        "the failing Beth acceptance behaviors below.\n",
        f"Environment: {run.environment}   Commit: {run.git_commit}   "
        f"Suite: {run.suite_name}/{run.depth}   Grade: {run.grade}   "
        f"Score: {run.score_percent}% ({run.pass_count}/{run.total_count})   "
        f"Critical: {run.critical_count}\n",
    ]
    if not failed:
        lines.append("The run is GREEN — no fixes required. Optionally add new "
                     "acceptance questions to harden coverage.")
        return "\n".join(lines)

    groups = _root_cause_groups(failed)
    lines.append("LIKELY ROOT-CAUSE GROUPS (treat each as a SYSTEMIC defect — fix the "
                 "defect class, not only the individual question):")
    for i, (label, members) in enumerate(groups, 1):
        lines.append(f"  {i}. {label}  [{', '.join(m['key'] for m in members)}]")
    if not groups:
        lines.append("  (no obvious grouping — treat each failure individually)")

    lines.append(f"\nFAILING QUESTIONS ({len(failed)}):")
    for r in failed:
        lines.append(
            f"\n- [{r['key']}] suite={r['suite']}\n"
            f"  Question: {r['question']}\n"
            f"  Expected: routes to '{r['expected_intent'] or '(correct domain)'}' and "
            f"passes its rules.\n"
            f"  Actual: intent={r['intent'] or '-'} lane={r['lane'] or '-'} "
            f"openai={r['openai_called']} fallback={r['fallback_used']}.\n"
            f"  Failed rules: {', '.join(r['fails'])}\n"
            f"  Actual response: {r['answer'][:500]}")
    lines.append(
        "\n\nInstructions:\n"
        "- Treat the grouped failures as SYSTEMIC defects: fix the defect class, not "
        "only the individual question.\n"
        "- Fix the ROOT CAUSE (routing, reasoning, fallback, profile, or evaluator).\n"
        "- Add/Update regression tests covering each fixed behavior.\n"
        "- PRESERVE all currently-passing behaviors (Health byte-identical; goal "
        "intent differentiation intact).\n"
        "- Re-run the acceptance suite (Admin Console Beth Acceptance Center, or "
        "`python manage.py beth_acceptance`) until green.\n"
        "- Deploy to main when green.\n"
        "- Do not stop for approval unless there is a migration, security issue, or "
        "architectural conflict.")
    return "\n".join(lines)
