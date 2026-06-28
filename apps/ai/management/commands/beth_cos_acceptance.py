"""
Run the CHIEF-OF-STAFF Acceptance Suite (the layer above Deep) against a user.

Gated: refuses unless the latest Deep (Truth Certification) run is GREEN.

    python manage.py beth_cos_acceptance --user-email danny@example.com
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai.chatgpt_cos.cos_acceptance_service import (
    CoSDeepNotGreen, create_and_execute_cos, latest_deep_grade,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Run the Chief-of-Staff Acceptance Suite (requires a GREEN Deep run)."

    def add_arguments(self, parser):
        parser.add_argument("--user-email", required=True)

    def handle(self, *args, **opts):
        try:
            user = User.objects.get(email=opts["user_email"])
        except User.DoesNotExist:
            raise CommandError(f"No user with email {opts['user_email']}")

        self.stdout.write(f"Latest Deep grade: {latest_deep_grade() or '(none)'}")
        try:
            run = create_and_execute_cos(user, created_by=user)
        except CoSDeepNotGreen as e:
            raise CommandError(f"Chief of Staff is locked — {e}")

        a = run.analysis or {}
        self.stdout.write(self.style.SUCCESS(
            f"\nCHIEF OF STAFF — grade={run.grade} avg_weighted={a.get('avg_weighted')} "
            f"first_class={run.pass_count}/{run.total_count} hard_fails={run.critical_count}"))
        for e in a.get("entries", []):
            mark = "✓" if e["behaved_like"] == "chief_of_staff" else "✗"
            self.stdout.write(f"  {mark} {e['id']} [{e['grade']}] {e['what_happened']}")
            if e["behaved_like"] == "chatbot":
                self.stdout.write(f"      law={e['law_violated']} class={e['classification']} "
                                  f"missing={e['missing_capability']}")
        if a.get("priority_by_capability"):
            self.stdout.write("\nEngineering priorities by capability:")
            for cap, ids in a["priority_by_capability"].items():
                self.stdout.write(f"  {cap}: {', '.join(ids)}")
