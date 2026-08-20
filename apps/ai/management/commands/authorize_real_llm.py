# ==============================================================================
# File: apps/ai/management/commands/authorize_real_llm.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Mint a narrow, finite, expiring authorization for paid provider calls
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-20
# ==============================================================================
"""Authorize a specific paid provider run — Danny only.

    python manage.py authorize_real_llm --calls 1 --reason "persona smoke test"

Authorization is deliberately NARROW: a small call count, a stated purpose, and an expiry.
It approves *this test*, not "real AI testing". When the budget is spent the authorization
is over — it is never reset or raised; mint a new one if a new test is genuinely warranted.

**This command refuses to run without an interactive terminal.** That is the technical
control that stops automated tooling — Claude Code included — from self-authorizing. Claude
may consume a budget Danny has already approved, and must stop when it is exhausted.
"""

import secrets
import sys

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.ai.models import RealLLMAuthorization

CONFIRM_PHRASE = "spend real money"
MAX_REASONABLE_CALLS = 25


class Command(BaseCommand):
    help = "Authorize a finite number of REAL (paid) provider calls for one run."

    def add_arguments(self, parser):
        parser.add_argument("--calls", type=int, required=True,
                            help="Hard maximum number of paid provider requests.")
        parser.add_argument("--reason", type=str, required=True,
                            help="What this run is for, in plain words.")
        parser.add_argument("--minutes", type=int, default=60,
                            help="How long the authorization stays live (default 60).")
        parser.add_argument("--list", action="store_true",
                            help="Show recent authorizations and their remaining budget.")

    def handle(self, *args, **opts):
        if opts.get("list"):
            return self._list()

        calls = opts["calls"]
        if calls < 1:
            raise CommandError("--calls must be at least 1.")
        if calls > MAX_REASONABLE_CALLS:
            raise CommandError(
                f"--calls {calls} exceeds the sanity ceiling of {MAX_REASONABLE_CALLS}. "
                f"A development validation that needs more than this is a design smell — "
                f"use deterministic tests, or mint several small authorizations knowingly."
            )

        # THE control that keeps automated tooling out. A non-interactive process (Claude
        # Code's shell, CI, a script) has no TTY and cannot get past this.
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise CommandError(
                "REFUSED: authorizing real spend requires an interactive terminal.\n"
                "This is deliberate — it is what prevents automated tooling (including "
                "Claude Code) from authorizing paid calls on Danny's account.\n"
                "Danny: run this yourself from a real terminal."
            )

        self.stdout.write(self.style.WARNING(
            f"\nThis authorizes up to {calls} REAL provider call(s) against the configured "
            f"OpenAI account.\nPurpose: {opts['reason']}\n"
        ))
        typed = input(f'Type "{CONFIRM_PHRASE}" to confirm: ').strip()
        if typed != CONFIRM_PHRASE:
            raise CommandError("Not confirmed — nothing authorized.")

        auth = RealLLMAuthorization.objects.create(
            run_id=f"wlj-llm-{secrets.token_hex(8)}",
            reason=opts["reason"],
            calls_authorized=calls,
            calls_remaining=calls,
            expires_at=timezone.now() + timezone.timedelta(minutes=opts["minutes"]),
        )
        self.stdout.write(self.style.SUCCESS(
            f"\nAuthorized {calls} call(s), expiring in {opts['minutes']} minutes.\n"
            f"\nExport these in the shell that will run the test:\n"
            f"\n  export WLJ_ALLOW_REAL_LLM=1"
            f"\n  export WLJ_LLM_RUN_ID={auth.run_id}\n"
            f"\nWhen the budget is spent, calls fail closed. Do not reset it.\n"
        ))

    def _list(self):
        rows = RealLLMAuthorization.objects.all()[:15]
        if not rows:
            self.stdout.write("No authorizations have ever been minted.")
            return
        self.stdout.write(f"{'run_id':<28}{'used/total':<14}{'live':<7}{'reason'}")
        for a in rows:
            self.stdout.write(
                f"{a.run_id:<28}{a.calls_used}/{a.calls_authorized:<11}"
                f"{'yes' if a.is_live else 'no':<7}{a.reason[:44]}"
            )
