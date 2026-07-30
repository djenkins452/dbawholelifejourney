# ==============================================================================
# File: apps/core/management/commands/certify_questions.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Render the data-driven Question Certification matrix for a domain.
#              The operator's view of the permanent certification artifact.
# ==============================================================================
"""`python manage.py certify_questions [domain]`

Prints the live Question Certification matrix — computed against the wired capability
registries, not asserted. With no domain, certifies every registered catalog.
"""
from django.core.management.base import BaseCommand

from apps.core.truth.question_catalog import certify, registered_domains


class Command(BaseCommand):
    help = "Render the data-driven Question Certification matrix."

    def add_arguments(self, parser):
        parser.add_argument("domain", nargs="?", default=None,
                            help="Catalog domain (e.g. 'health'); omit for all.")
        parser.add_argument("--gaps", action="store_true",
                            help="Show only uncertified questions.")

    def handle(self, *args, **opts):
        domain = opts.get("domain")
        rep = certify(domain)
        s = rep["summary"]
        if not s["total"]:
            self.stdout.write(self.style.WARNING(
                f"No questions registered for {domain or 'any domain'}. "
                f"Known catalogs: {', '.join(registered_domains()) or '(none)'}"))
            return

        for q in rep["questions"]:
            if opts.get("gaps") and q["certified"]:
                continue
            mark = self.style.SUCCESS("PASS") if q["certified"] else self.style.ERROR("GAP ")
            line = f"  [{mark}] {q['topic'] or q['domain']:>16} · {q['category']:<15} {q['id']}"
            self.stdout.write(line)
            if not q["certified"]:
                ff = q["first_failing_layer"]
                self.stdout.write(f"         └─ first failing layer: {ff['layer']} "
                                  f"(needs {ff['needs']})")

        pct = s["pct"]
        style = self.style.SUCCESS if s["uncertified"] == 0 else self.style.WARNING
        self.stdout.write("")
        self.stdout.write(style(
            f"  {s['certified']}/{s['total']} questions certified ({pct}%) "
            f"across {len(s['by_domain'])} domain(s)."))
