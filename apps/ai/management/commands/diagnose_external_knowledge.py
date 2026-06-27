"""
Diagnose the "external knowledge service" (OpenAI) that powers Beth's GENERAL
educational answers ("What is Metformin commonly used for?").

WLJ owns personal truth deterministically; general knowledge requires the external
LLM (no offline encyclopedia by design). When that service is unreachable, the
General lane returns "…my external knowledge service is temporarily unavailable…"
and the tool loop falls back to "I couldn't pull that together…". This command
reports EXACTLY why — usually a missing/invalid OPENAI_API_KEY or exhausted quota
(an ENVIRONMENT issue, not a code bug).

    python manage.py diagnose_external_knowledge          # config/availability only
    python manage.py diagnose_external_knowledge --ping    # also make one live call
"""

from django.core.cache import cache
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Report whether Beth's external knowledge service (OpenAI) is configured/reachable."

    def add_arguments(self, parser):
        parser.add_argument("--ping", action="store_true",
                            help="Make one tiny live OpenAI call to verify reachability.")

    def handle(self, *args, **options):
        from django.conf import settings
        from apps.ai.services import ai_service

        key = getattr(settings, "OPENAI_API_KEY", None)
        report = {
            "api_key_configured": bool(key),
            "client_initialized": ai_service.is_available,  # is_available == client is not None
            "model": getattr(settings, "OPENAI_MODEL", None),
            "cos_model": getattr(settings, "COS_MODEL", None),
            "circuit_breaker_active": bool(cache.get("openai_rate_limited")),
        }

        self.stdout.write("External Knowledge Service (OpenAI) — diagnosis")
        self.stdout.write("-" * 52)
        for k, v in report.items():
            self.stdout.write(f"  {k:24} = {v}")

        if not report["api_key_configured"]:
            self.stdout.write(self.style.ERROR(
                "\nROOT CAUSE: OPENAI_API_KEY is not set → client is None → "
                "is_available False → general/educational answers return "
                "'external knowledge service temporarily unavailable'. "
                "ENVIRONMENT issue: set OPENAI_API_KEY (with quota) in the deploy env."))
            return
        if not report["client_initialized"]:
            self.stdout.write(self.style.ERROR(
                "\nROOT CAUSE: OPENAI_API_KEY is set but the client failed to "
                "initialize (package/init error). Check logs for "
                "'Failed to initialize shared OpenAI client'."))
            return

        if options["ping"]:
            self.stdout.write("\nPinging OpenAI (one minimal call)…")
            answer = ai_service._call_api(
                "You are a test.", "Reply with the single word: ok.",
                max_tokens=5, temperature=0, endpoint="cos_chat",
                bypass_breaker=True,
            )
            if answer:
                self.stdout.write(self.style.SUCCESS(
                    f"  LIVE OK — reachable. Reply: {answer!r}"))
            else:
                self.stdout.write(self.style.ERROR(
                    "  LIVE FAIL — call returned None. Likely invalid key, exhausted "
                    "quota/billing, an unavailable model, or a network/timeout error. "
                    "See the 'LLM FAILED endpoint=cos_chat model=… final_error=…' log line."))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\nConfigured and client initialized. Run with --ping to verify a live call."))
