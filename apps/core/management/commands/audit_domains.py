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
    help = "Audit WLJ domain registry — show registered domains, governance alignment, and warnings"

    def handle(self, *args, **options):
        from apps.core.domain_registry import (
            registry, autodiscover, get_registry_health_summary,
        )

        # Ensure discovery has run
        autodiscover()

        domains = registry.get_all()

        self.stdout.write(self.style.SUCCESS(
            f"\n=== Domain Registry Audit ({len(domains)} domains) ===\n"
        ))

        # Show each domain with Phase 3 classification
        for name in sorted(domains.keys()):
            d = domains[name]
            score = d.coverage_score()
            score_color = self.style.SUCCESS if score >= 75 else (
                self.style.WARNING if score >= 50 else self.style.ERROR
            )
            cls_label = d.domain_class.upper()
            self.stdout.write(
                f"  {d.display_name} ({d.name}) [{cls_label}]\n"
                f"    Intents: {len(d.intent_types)} | "
                f"Signals: {len(d.proactive_signals)} | "
                f"Models: {len(d.primary_models)} | "
                f"Context: {'Yes' if d.context_builders else 'No'} | "
                f"Coverage: {score_color(f'{score:.0f}%')}\n"
            )

        # Phase 3: Governance alignment
        self.stdout.write(self.style.SUCCESS(
            "\n=== Phase 3: Governance Alignment ===\n"
        ))

        health = get_registry_health_summary()

        # Domain class breakdown
        self.stdout.write("  Domain classes:")
        for cls, count in sorted(health['by_class'].items()):
            self.stdout.write(f"    {cls}: {count}")

        # Alignment status
        status_style = (
            self.style.SUCCESS if health['status'] == 'healthy'
            else self.style.ERROR
        )
        self.stdout.write(f"\n  Registry status: {status_style(health['status'])}")

        if health['issues']:
            self.stdout.write(self.style.ERROR(
                f"\n  Alignment issues ({len(health['issues'])}):"
            ))
            for issue in health['issues']:
                self.stdout.write(self.style.ERROR(f"    - {issue}"))
        else:
            self.stdout.write(self.style.SUCCESS(
                "  All domain references resolve to canonical governance."
            ))

        # Completion warnings (existing)
        warnings = []
        for name, d in domains.items():
            if d.is_user_life_domain and not d.intent_types:
                warnings.append(f"  {d.display_name}: No intent types (behavioral domain)")
            if not d.proactive_signals:
                warnings.append(f"  {d.display_name}: No proactive signals registered")
            if d.participates_in_cos and not d.context_builders:
                warnings.append(f"  {d.display_name}: CoS-participating but no context builders")

        if warnings:
            self.stdout.write(self.style.WARNING(
                f"\n=== Completion Warnings ({len(warnings)}) ===\n"
            ))
            for w in warnings:
                self.stdout.write(self.style.WARNING(w))

        # Summary
        total_intents = len(registry.get_all_intent_types())
        total_signals = len(registry.get_all_proactive_signals())
        avg_coverage = sum(d.coverage_score() for d in domains.values()) / max(len(domains), 1)

        self.stdout.write(f"\nTotal intents: {total_intents}")
        self.stdout.write(f"Total proactive signals: {total_signals}")
        self.stdout.write(f"Average coverage: {avg_coverage:.0f}%\n")
