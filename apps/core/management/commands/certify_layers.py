"""
certify_layers — the WLJ layer release gate.

Re-runs the deterministic certification suites for every certified layer (or up to a
given layer). A higher layer may only certify if EVERY lower certified layer remains
GREEN — this command enforces that invariant in CI and locally.

    python manage.py certify_layers              # all certified layers
    python manage.py certify_layers --up-to 1    # layers 1..1
    python manage.py certify_layers --list       # show the gate modules, run nothing
"""
from django.core.management.base import BaseCommand
from django.test.utils import get_runner
from django.conf import settings

from apps.core.truth import certification as CERT


class Command(BaseCommand):
    help = "Run the deterministic certification gate for certified WLJ layers."

    def add_arguments(self, parser):
        parser.add_argument("--up-to", type=int, default=None,
                            help="Highest layer number to include (default: highest certified).")
        parser.add_argument("--list", action="store_true",
                            help="List the gate modules and exit (run nothing).")

    def handle(self, *args, **opts):
        up_to = opts["up_to"] or CERT.highest_certified_layer()
        if up_to < 1:
            self.stdout.write(self.style.WARNING("No certified layers yet."))
            return
        modules = CERT.certification_modules(up_to)

        names = ", ".join(l["name"] for l in CERT.layers_up_to(up_to))
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Layer certification gate — layers 1..{up_to} ({names})"))
        for m in modules:
            self.stdout.write(f"  • {m}")
        if opts["list"]:
            return

        runner = get_runner(settings)(verbosity=1, keepdb=True)
        failures = runner.run_tests(modules)
        if failures:
            raise SystemExit(self.style.ERROR(
                f"CERTIFICATION FAILED — {failures} failure(s). "
                f"A certified layer regressed; release is blocked."))
        self.stdout.write(self.style.SUCCESS(
            f"CERTIFICATION GREEN — layers 1..{up_to} intact."))
