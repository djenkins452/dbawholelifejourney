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
        from apps.ai.proactive_checkins import ProactiveCheckInService

        try:
            user = User.objects.get(email=options["email"])
        except User.DoesNotExist:
            raise CommandError(f"No user with email {options['email']}")

        correlation_type = "sleep_mood"
        svc = ProactiveCheckInService(user)

        if options["force"]:
            # Dev bypass: ignore the cadence throttle and any prior "Got it" dismissal.
            svc.throttler.can_send = lambda *a, **k: True
            try:
                from django.core.cache import cache
                cache.delete(f"wlj:guidance_dismissed:{user.id}:{correlation_type}")
            except Exception:
                pass

        msg = svc.generate_cdce_correlation_check_in(
            correlation_type=correlation_type,
            narrative=options["narrative"],
            strength="strong",
            domains=["sleep", "journal"],
        )

        if not msg:
            self.stdout.write(self.style.WARNING(
                "No card produced (throttled or already dismissed). Re-run with --force."))
            return

        labels = [q.get("label") for q in (msg.quick_replies or [])]
        self.stdout.write(self.style.SUCCESS(
            f"Created proactive card id={msg.id} for {user.email}"))
        self.stdout.write(f"  content: {msg.content}")
        self.stdout.write(f"  buttons: {labels}")
        self.stdout.write("Open the assistant panel to see it and click the buttons.")
