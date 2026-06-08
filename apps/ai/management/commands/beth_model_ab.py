"""Model A/B runner — Phase 0 SCAFFOLD. Does NOT call any model API.

Refuses to execute candidate generation unless explicitly approved + flagged.
In Phase 0 it only lists the prompts it *would* evaluate and confirms the safety
stop is in place.

    python manage.py beth_model_ab            # dry list, no API calls
    python manage.py beth_model_ab --confirm  # still blocked until approval/flag
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.ai.cognitive_mode import golden_corpus as gc
from apps.ai.cognitive_mode import model_ab


class Command(BaseCommand):
    help = "Phase 0 scaffold for the model A/B. Lists prompts; does NOT call any API."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true",
                            help="Attempt a run (will be blocked unless approved+flagged).")

    def handle(self, *args, **opts):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== Beth Model A/B (Phase 0 scaffold — no API execution) ==="))
        self.stdout.write(f"  Candidate prompts (golden corpus): {len(gc.GOLDEN)}")
        for e in gc.GOLDEN:
            self.stdout.write(f"    - {e['id']:28} [{e['expected_mode']}]")

        if not opts.get("confirm"):
            self.stdout.write(self.style.WARNING(
                "\n  Dry run only. Re-run with --confirm to test the safety stop.\n"))
            return

        # Demonstrate that the safety stop holds even when --confirm is passed.
        try:
            model_ab.generate_candidate(
                prompt="(noop)", context_payload={}, model_id="", approved=False)
        except model_ab.ModelABNotApproved as exc:
            self.stdout.write(self.style.SUCCESS(
                f"\n  Safety stop confirmed — generation blocked:\n    {exc}\n"))
            return
        # Should be unreachable in Phase 0.
        self.stdout.write(self.style.ERROR(
            "  WARNING: safety stop did NOT engage — investigate before any run.\n"))
