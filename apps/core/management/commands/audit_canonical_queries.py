"""
Management command: Canonical Query Audit (Ops Wall 2.0 — Phase 7).

Scans Python files for direct ORM queries that bypass canonical domain
services. Returns exit code 1 if violations found (CI-friendly).

Usage:
    python manage.py audit_canonical_queries
    python manage.py audit_canonical_queries --domain life
    python manage.py audit_canonical_queries --json
    python manage.py audit_canonical_queries --cache  # update Ops Wall cache

Project: Whole Life Journey
Path: apps/core/management/commands/audit_canonical_queries.py
"""

import json
import os
import sys

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Detect direct ORM queries bypassing canonical domain services"

    def add_arguments(self, parser):
        parser.add_argument(
            "--domain",
            type=str,
            default=None,
            help="Audit a single domain (e.g., life, intelligence, guidance)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            default=False,
            help="Output results as JSON",
        )
        parser.add_argument(
            "--cache",
            action="store_true",
            default=False,
            help="Cache results for Ops Wall display",
        )

    def handle(self, *args, **options):
        from apps.core.canonical_audit import CANONICAL_RULES, run_audit

        # Determine base directory (project root)
        base_dir = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
            )
        )

        # Filter rules by domain if specified
        rules = CANONICAL_RULES
        if options["domain"]:
            domain = options["domain"]
            rules = {
                k: v for k, v in CANONICAL_RULES.items() if v["domain"] == domain
            }
            if not rules:
                self.stderr.write(
                    self.style.ERROR(f"No rules found for domain: {domain}")
                )
                sys.exit(1)

        # Run audit
        result = run_audit(base_dir, rules)

        # Cache results if requested
        if options["cache"]:
            self._cache_result(result)

        # Output
        if options["json"]:
            self._output_json(result)
        else:
            self._output_table(result, options.get("domain"))

        # Exit code: 1 if violations found
        if result.violations:
            sys.exit(1)

    def _output_table(self, result, domain_filter=None):
        """Print human-readable violation report."""
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("CANONICAL QUERY AUDIT"))
        self.stdout.write("=" * 50)
        if domain_filter:
            self.stdout.write(f"Domain filter: {domain_filter}")
        self.stdout.write(f"Files scanned: {result.files_scanned}")
        self.stdout.write(f"Models audited: {result.models_audited}")
        self.stdout.write(
            f"Violations found: {len(result.violations)}"
        )
        self.stdout.write(
            f"Compliance score: {result.compliance_score}%"
        )
        self.stdout.write("")

        if not result.violations:
            self.stdout.write(
                self.style.SUCCESS("No violations found. All queries use canonical services.")
            )
            return

        # Group violations by domain
        by_domain = {}
        for v in result.violations:
            by_domain.setdefault(v.domain, []).append(v)

        for domain, violations in sorted(by_domain.items()):
            self.stdout.write(
                self.style.WARNING(f"\n{domain.upper()} DOMAIN — {len(violations)} violation(s)")
            )
            self.stdout.write("-" * 50)
            for v in violations:
                self.stdout.write(f"  file: {v.file}")
                self.stdout.write(f"  line: {v.line}")
                self.stdout.write(f"  model: {v.model}")
                self.stdout.write(f"  query: {v.query}")
                self.stdout.write(
                    self.style.MIGRATE_HEADING(f"  expected: {v.suggested_service}")
                )
                self.stdout.write("")

    def _output_json(self, result):
        """Print JSON output for CI integration."""
        output = {
            "files_scanned": result.files_scanned,
            "models_audited": result.models_audited,
            "violations_count": len(result.violations),
            "compliance_score": result.compliance_score,
            "violations": [
                {
                    "file": v.file,
                    "line": v.line,
                    "model": v.model,
                    "query": v.query,
                    "domain": v.domain,
                    "suggested_service": v.suggested_service,
                }
                for v in result.violations
            ],
        }
        self.stdout.write(json.dumps(output, indent=2))

    def _cache_result(self, result):
        """Cache audit result for Ops Wall display."""
        try:
            from django.core.cache import cache

            cache.set(
                "wlj:ops:canonical_compliance",
                {
                    "score": result.compliance_score,
                    "violations": len(result.violations),
                    "scanned": result.files_scanned,
                    "models_audited": result.models_audited,
                    "last_run": timezone.now().isoformat(),
                },
                timeout=86400,  # 24h TTL
            )
            self.stdout.write(
                self.style.SUCCESS("Cached compliance score for Ops Wall.")
            )
        except Exception as e:
            self.stderr.write(
                self.style.WARNING(f"Failed to cache result: {e}")
            )
