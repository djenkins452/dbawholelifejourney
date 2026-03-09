# ==============================================================================
# File: apps/core/management/commands/audit_domains.py
# Description: Audit domain registry compliance
# ==============================================================================
"""
Management command to audit domain registry compliance.

Usage:
    python manage.py audit_domains
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Audit WLJ domain registry — show registered domains and warnings"

    def handle(self, *args, **options):
        from apps.core.domain_registry import registry, autodiscover

        # Ensure discovery has run
        autodiscover()

        domains = registry.get_all()

        self.stdout.write(self.style.SUCCESS(
            f"\n=== Domain Registry Audit ({len(domains)} domains) ===\n"
        ))

        # Show each domain
        for name in sorted(domains.keys()):
            d = domains[name]
            score = d.coverage_score()
            score_color = self.style.SUCCESS if score >= 75 else (
                self.style.WARNING if score >= 50 else self.style.ERROR
            )
            self.stdout.write(
                f"  {d.display_name} ({d.name})\n"
                f"    Intents: {len(d.intent_types)} | "
                f"Signals: {len(d.proactive_signals)} | "
                f"Models: {len(d.primary_models)} | "
                f"Context: {'Yes' if d.context_builders else 'No'} | "
                f"Coverage: {score_color(f'{score:.0f}%')}\n"
            )

        # Warnings
        warnings = []
        for name, d in domains.items():
            if not d.intent_types:
                warnings.append(f"  {d.display_name}: No intent types registered")
            if not d.proactive_signals:
                warnings.append(f"  {d.display_name}: No proactive signals registered")
            if not d.context_builders:
                warnings.append(f"  {d.display_name}: No context builders registered")

        if warnings:
            self.stdout.write(self.style.WARNING(
                f"\n=== Warnings ({len(warnings)}) ===\n"
            ))
            for w in warnings:
                self.stdout.write(self.style.WARNING(w))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\n=== No warnings — all domains fully registered ===\n"
            ))

        # Summary
        total_intents = len(registry.get_all_intent_types())
        total_signals = len(registry.get_all_proactive_signals())
        avg_coverage = sum(d.coverage_score() for d in domains.values()) / max(len(domains), 1)

        self.stdout.write(f"\nTotal intents: {total_intents}")
        self.stdout.write(f"Total proactive signals: {total_signals}")
        self.stdout.write(f"Average coverage: {avg_coverage:.0f}%\n")
