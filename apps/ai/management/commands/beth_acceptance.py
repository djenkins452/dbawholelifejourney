# ==============================================================================
# File: apps/ai/management/commands/beth_acceptance.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: LIVE Beth acceptance harness (CLI). Runs the validation questions
#   through the REAL chat path via the SHARED runner (apps.ai.chatgpt_cos.
#   acceptance_service) — the same logic the Admin Console Beth Acceptance Center
#   uses — persists an AcceptanceRun, prints a PASS/FAIL report, and exits
#   non-zero on any failure so it can gate the beth-stable-v3 release.
#
#   Usage (environment with an OpenAI key + the user's real data):
#     python manage.py beth_acceptance --user-email dannyjenkins71@gmail.com \
#         --suite full --evening --json report.json
#   Makes REAL OpenAI calls — run in staging/eval, not collected by the test runner.
# ==============================================================================
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ai.chatgpt_cos.acceptance_rules import SUITES, DEPTHS


class Command(BaseCommand):
    help = "Run the LIVE Beth acceptance harness (real chat path) via the shared runner."

    def add_arguments(self, parser):
        parser.add_argument("--user-email", default=None)
        parser.add_argument("--suite", default="full", choices=list(SUITES))
        parser.add_argument("--depth", default="full", choices=list(DEPTHS),
                            help="smoke (~fast gate) / full (release gate) / deep (stress).")
        parser.add_argument("--evening", action="store_true",
                            help="Force evening (9 PM) for the check-in agenda turn.")
        parser.add_argument("--json", default=None, help="Write the full report to this path.")

    def handle(self, *args, **opts):
        from django.contrib.auth import get_user_model
        from apps.ai.chatgpt_cos.acceptance_service import create_and_execute

        User = get_user_model()
        email = opts["user_email"] or getattr(settings, "WLJ_OWNER_EMAIL", None) \
            or "dannyjenkins71@gmail.com"
        user = User.objects.filter(email=email).first() \
            or User.objects.filter(is_superuser=True).first()
        if user is None:
            raise CommandError(f"No user found for {email!r} (and no superuser).")

        run = create_and_execute(suite=opts["suite"], depth=opts["depth"],
                                 target_user=user, created_by=user,
                                 evening=opts["evening"])
        rows = (run.raw_report_json or {}).get("rows", [])

        w = self.stdout.write
        w("\n" + "=" * 78)
        w(f"BETH LIVE ACCEPTANCE — suite={run.suite_name}/{run.depth} "
          f"grade={run.grade} env={run.environment} commit={run.git_commit}")
        w("=" * 78)
        for r in rows:
            tag = self.style.SUCCESS("PASS") if r["passed"] else self.style.ERROR("FAIL")
            w(f"\n[{tag}] {r['key']}  ({r['ms']}ms)")
            w(f"  Q: {r['question']}")
            w(f"  intent={r['intent']} lane={r['lane']} openai={r['openai_called']} "
              f"fallback={r['fallback_used']}")
            ans = (r["answer"] or "").replace("\n", " ")
            w(f"  A: {ans[:300]}{'…' if len(ans) > 300 else ''}")
            if r["fails"]:
                w(self.style.ERROR(f"  FAILED RULES: {', '.join(r['fails'])}"))
        w("\n" + "-" * 78)
        w(f"TOTAL: {run.pass_count}/{run.total_count} passed  ({run.score_percent}%)  "
          f"run_id={run.pk}")

        if opts["json"]:
            with open(opts["json"], "w") as fh:
                json.dump(run.raw_report_json, fh, indent=2, default=str)
            w(f"Wrote {opts['json']}")

        if run.fail_count:
            raise CommandError(
                f"BETH ACCEPTANCE FAILED: {run.fail_count}/{run.total_count} failed. "
                f"NOT ready for beth-stable-v3.")
        w(self.style.SUCCESS(
            f"\nBETH ACCEPTANCE PASSED: {run.total_count}/{run.total_count}. "
            f"Eligible for beth-stable-v3."))
