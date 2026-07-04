# ==============================================================================
# File: apps/ai/management/commands/trigger_proactive_checkin.py
# DEV / EXECUTIVE-CERTIFICATION ONLY — generate a proactive guidance card on demand,
# so the interactive buttons ("Tell me more", "How to use this", "Got it") can be
# tested deterministically without waiting for the scheduler cadence.
#
# It calls the REAL production generator (ProactiveCheckInService.
# generate_cdce_correlation_check_in) — same card, same quick_replies, same dismissal
# metadata — so what you certify is exactly what production surfaces. --force bypasses
# the throttle and clears any prior "Got it" dismissal so a card is always produced.
#
#   python manage.py trigger_proactive_checkin --email you@example.com --force
# ==============================================================================
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = ("DEV ONLY: generate a proactive CDCE guidance card (with the Tell me more / "
            "How to use this / Got it buttons) on demand for certification.")

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="User to create the card for.")
        parser.add_argument(
            "--type", default="cdce", choices=["cdce"],
            help="Card type (currently the CDCE cross-domain correlation card).")
        parser.add_argument(
            "--force", action="store_true",
            help="Bypass the throttle and clear any prior dismissal so a card is produced.")
        parser.add_argument(
            "--narrative",
            default="on days you sleep 7+ hours, your journal entries are noticeably more positive",
            help="The correlation narrative to surface.")

    def handle(self, *args, **options):
        # Calls the SAME shared implementation as the in-app Executive Certification
        # Console — no duplicated business logic.
        from apps.ai.certification_console import run_action

        try:
            user = User.objects.get(email=options["email"])
        except User.DoesNotExist:
            raise CommandError(f"No user with email {options['email']}")

        result = run_action(user, "proactive_guidance", force=options["force"])

        if not result.get("ok"):
            self.stdout.write(self.style.WARNING(result.get("summary", "No card produced.")))
            return

        self.stdout.write(self.style.SUCCESS(f"{result['summary']} ({user.email})"))
        if result.get("preview"):
            self.stdout.write(f"  content: {result['preview']}")
        if result.get("buttons"):
            self.stdout.write(f"  buttons: {result['buttons']}")
        self.stdout.write("Open the assistant panel to see it and click the buttons.")
