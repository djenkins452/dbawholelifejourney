# ==============================================================================
# File: apps/ai/management/commands/beth_acceptance.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: LIVE Beth acceptance harness. Runs the core validation questions
#   through the REAL chat service path (ChatGPTCoSService.generate — the same
#   orchestrator the UI calls), evaluates the ACTUAL responses against the
#   gold-standard gates, and prints a PASS/FAIL report. Exits non-zero on any
#   failure so it can gate the beth-stable-v3 release.
#
#   Usage (run in an environment with an OpenAI key + the user's real data):
#     python manage.py beth_acceptance --user-email dannyjenkins71@gmail.com
#     python manage.py beth_acceptance --evening          # force evening check-in
#     python manage.py beth_acceptance --json report.json
#
#   Makes REAL OpenAI calls — run in staging/eval, NOT collected by the test runner.
# ==============================================================================
import json
import logging
import re
import time
from contextlib import contextmanager

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ai.chatgpt_cos.acceptance_rules import QUESTIONS, evaluate, GOAL_INTENTS


class _Capture(logging.Handler):
    """Capture Beth telemetry emitted during one generate() call."""
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


def _parse_telemetry(lines):
    """Best-effort extraction of intent / lane / fallback / openai-called."""
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
        if "COS_LANE_TRACE" in ln or "lane=" in ln:
            m = _LANE_RE.search(ln)
            if m and lane is None:
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


class Command(BaseCommand):
    help = "Run the LIVE Beth gold-standard acceptance harness (real chat path)."

    def add_arguments(self, parser):
        parser.add_argument("--user-email", default=None,
                            help="Account to test (defaults to WLJ owner / first superuser).")
        parser.add_argument("--evening", action="store_true",
                            help="Force evening (9 PM) for the check-in agenda turn.")
        parser.add_argument("--json", default=None, help="Write the full report to this path.")

    def handle(self, *args, **opts):
        from django.contrib.auth import get_user_model
        from apps.ai.models import AssistantConversation
        from apps.ai.chatgpt_cos.service import ChatGPTCoSService

        User = get_user_model()
        email = opts["user_email"] or getattr(settings, "WLJ_OWNER_EMAIL", None) \
            or "dannyjenkins71@gmail.com"
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.filter(is_superuser=True).first()
        if user is None:
            raise CommandError(f"No user found for {email!r} (and no superuser).")

        conv = AssistantConversation.objects.create(user=user, title="acceptance")
        svc = ChatGPTCoSService(user)
        results = []
        goal_answers = {}

        for spec in QUESTIONS:
            text = spec["text"]
            patches = []
            if spec.get("evening") and opts["evening"]:
                from unittest.mock import patch
                patches.append(patch(
                    "apps.core.cos_briefing.daily_agenda._user_hour", return_value=21))
            for p in patches:
                p.start()
            t0 = time.monotonic()
            answer, intent, lane, fb, openai = "", None, None, None, False
            try:
                with _telemetry() as cap:
                    res = svc.generate(conv, text) or {}
                answer = (res.get("answer") or "").strip()
                lane = res.get("lane")
                intent, plane, fb, openai = _parse_telemetry(cap.lines)
                lane = lane or plane
            except Exception as exc:  # a crash IS a failure, never swallow
                answer = f"<EXCEPTION: {type(exc).__name__}: {exc}>"
            finally:
                for p in patches:
                    p.stop()
            elapsed = round((time.monotonic() - t0) * 1000)

            fails = evaluate(spec, answer, intent=intent, lane=lane)
            if answer.startswith("<EXCEPTION"):
                fails = ["exception"] + fails
            if spec.get("domain") == "goals" and intent in GOAL_INTENTS:
                goal_answers[spec["key"]] = answer

            results.append({
                "key": spec["key"], "question": text, "answer": answer,
                "intent": intent, "lane": lane, "fallback_used": fb,
                "openai_called": openai, "ms": elapsed,
                "fails": fails, "passed": not fails,
            })

        # Cross-intent distinctness (goal intents must not duplicate).
        dupe_fail = []
        seen = {}
        for k, a in goal_answers.items():
            norm = a.strip().lower()
            if norm in seen:
                dupe_fail.append(f"{k} duplicates {seen[norm]}")
            seen[norm] = k
        for r in results:
            if r["key"] in goal_answers:
                for d in dupe_fail:
                    if r["key"] in d:
                        r["fails"].append("duplicate_answer")
                        r["passed"] = False

        self._report(results, dupe_fail)
        if opts["json"]:
            with open(opts["json"], "w") as fh:
                json.dump(results, fh, indent=2, default=str)
            self.stdout.write(f"\nWrote {opts['json']}")

        failed = [r for r in results if not r["passed"]]
        conv.delete()
        if failed:
            raise CommandError(
                f"\nBETH ACCEPTANCE FAILED: {len(failed)}/{len(results)} questions failed. "
                f"NOT ready for beth-stable-v3.")
        self.stdout.write(self.style.SUCCESS(
            f"\nBETH ACCEPTANCE PASSED: {len(results)}/{len(results)} questions. "
            f"Eligible for beth-stable-v3."))

    def _report(self, results, dupe_fail):
        w = self.stdout.write
        w("\n" + "=" * 78)
        w("BETH LIVE ACCEPTANCE REPORT")
        w("=" * 78)
        for r in results:
            tag = self.style.SUCCESS("PASS") if r["passed"] else self.style.ERROR("FAIL")
            w(f"\n[{tag}] {r['key']}  ({r['ms']}ms)")
            w(f"  Q: {r['question']}")
            w(f"  intent={r['intent']} lane={r['lane']} "
              f"openai={r['openai_called']} fallback={r['fallback_used']}")
            ans = r["answer"].replace("\n", " ")
            w(f"  A: {ans[:300]}{'…' if len(ans) > 300 else ''}")
            if r["fails"]:
                w(self.style.ERROR(f"  FAILED RULES: {', '.join(r['fails'])}"))
        if dupe_fail:
            w(self.style.ERROR(f"\nDUPLICATE GOAL ANSWERS: {dupe_fail}"))
        n_pass = sum(1 for r in results if r["passed"])
        w("\n" + "-" * 78)
        w(f"TOTAL: {n_pass}/{len(results)} passed")
