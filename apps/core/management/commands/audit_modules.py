# ==============================================================================
# File: apps/core/management/commands/audit_modules.py
# Description: Audit module catalog and domain registry alignment
# ==============================================================================
"""
Management command to audit module catalog compliance.

Validates:
    - Every mapped_domain_key resolves to a registered DomainCapability
    - Every DomainCapability is owned by exactly one module (or is cross-cutting)
    - System layers have always_available=True
    - Coming-soon modules have default_enabled=False
    - Active modules with show_in_navigation resolve their routes
    - Internal modules have correct visibility flags
    - No orphan domains (registered but unowned)

Usage:
    python manage.py audit_modules           # Report mode
    python manage.py audit_modules --check   # CI mode (exits 1 on errors)
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Audit WLJ module catalog and domain registry alignment"

    def add_arguments(self, parser):
        parser.add_argument(
            '--check',
            action='store_true',
            help='Exit with code 1 if any errors found (for CI)',
        )

    def handle(self, *args, **options):
        from apps.users.models import ModuleDefinition
        from apps.core.domain_registry import registry, autodiscover

        # Ensure domain discovery has run
        autodiscover()
        registered_domains = registry.get_all()

        # Load catalog
        catalog = {m.slug: m for m in ModuleDefinition.objects.all()}

        errors = []
        warnings = []

        self.stdout.write(self.style.SUCCESS(
            f"\n{'=' * 60}"
            f"\n  Module Catalog Audit ({len(catalog)} entries)"
            f"\n{'=' * 60}\n"
        ))

        # ── Display catalog ──
        for slug in sorted(catalog.keys(), key=lambda s: (catalog[s].layer, catalog[s].default_order)):
            m = catalog[slug]
            status_color = {
                'active': self.style.SUCCESS,
                'coming_soon': self.style.WARNING,
                'internal': self.style.NOTICE if hasattr(self.style, 'NOTICE') else self.style.WARNING,
            }.get(m.status, self.style.ERROR)

            self.stdout.write(
                f"  L{m.layer} {m.catalog_type:8s} | {slug:15s} | "
                f"{status_color(m.status):12s} | "
                f"always={m.always_available!s:5s} | "
                f"cos={m.cos_participation!s:5s} | "
                f"domains={m.mapped_domain_keys}"
            )

        # ── Validate domain mapping ──
        self.stdout.write(self.style.SUCCESS(
            f"\n{'=' * 60}"
            f"\n  Domain Mapping Validation"
            f"\n{'=' * 60}\n"
        ))

        owned_domains = {}
        for slug, m in catalog.items():
            for dk in (m.mapped_domain_keys or []):
                if dk in owned_domains:
                    errors.append(
                        f"Domain '{dk}' claimed by both '{owned_domains[dk]}' and '{slug}'"
                    )
                owned_domains[dk] = slug

                if dk not in registered_domains:
                    # 'documents' is a planned domain — warn, don't error
                    if dk == 'documents':
                        warnings.append(
                            f"Domain '{dk}' mapped by '{slug}' but not yet in domain registry "
                            f"(expected — will be registered in Phase 3)"
                        )
                    else:
                        errors.append(
                            f"Domain '{dk}' mapped by '{slug}' but NOT in domain registry"
                        )

        # Check for orphan domains (registered but not owned)
        for dk in registered_domains:
            if dk not in owned_domains:
                # Capture has mapped_domain_keys=[] by design (Layer 1)
                warnings.append(
                    f"Domain '{dk}' is registered in domain registry but not owned by any module"
                )

        # ── Validate catalog_type rules ──
        self.stdout.write(self.style.SUCCESS(
            f"\n{'=' * 60}"
            f"\n  Catalog Type Validation"
            f"\n{'=' * 60}\n"
        ))

        for slug, m in catalog.items():
            # System entries must be always_available
            if m.catalog_type == 'system' and not m.always_available:
                errors.append(
                    f"'{slug}': catalog_type=SYSTEM but always_available=False"
                )

            # Internal must be invisible
            if m.catalog_type == 'internal':
                if m.show_in_navigation:
                    errors.append(f"'{slug}': INTERNAL but show_in_navigation=True")
                if m.show_in_preferences:
                    errors.append(f"'{slug}': INTERNAL but show_in_preferences=True")
                if not m.always_available:
                    errors.append(f"'{slug}': INTERNAL but always_available=False")

            # Coming soon must not be default_enabled
            if m.status == 'coming_soon' and m.default_enabled:
                errors.append(
                    f"'{slug}': status=coming_soon but default_enabled=True"
                )

            # Modules must have at least one domain (except coming_soon with no app yet)
            if (m.catalog_type == 'module'
                    and m.status == 'active'
                    and not m.mapped_domain_keys):
                warnings.append(
                    f"'{slug}': active MODULE with no mapped_domain_keys"
                )

        # ── Validate route resolution ──
        self.stdout.write(self.style.SUCCESS(
            f"\n{'=' * 60}"
            f"\n  Route Validation"
            f"\n{'=' * 60}\n"
        ))

        from django.urls import reverse, NoReverseMatch
        for slug, m in catalog.items():
            if m.status == 'active' and m.show_in_navigation and m.route_name:
                try:
                    reverse(m.route_name)
                    self.stdout.write(f"  {slug:15s} → {m.route_name:30s} ✓")
                except NoReverseMatch:
                    errors.append(
                        f"'{slug}': route_name '{m.route_name}' does not resolve"
                    )
                    self.stdout.write(self.style.ERROR(
                        f"  {slug:15s} → {m.route_name:30s} ✗ UNRESOLVABLE"
                    ))

        # ── Validate CoS builder domain associations (Phase 2) ──
        self.stdout.write(self.style.SUCCESS(
            f"\n{'=' * 60}"
            f"\n  CoS Builder Domain Mapping Validation"
            f"\n{'=' * 60}\n"
        ))

        try:
            from apps.core.ai_orchestrator.cos_context import _TAGGED_BUILDERS
            from apps.core.module_catalog import get_domain_to_module_map

            domain_to_module = get_domain_to_module_map()
            for tag, _fn, domain_key in _TAGGED_BUILDERS:
                if domain_key is None:
                    self.stdout.write(f"  {tag:20s} → system (always run) ✓")
                elif domain_key in domain_to_module:
                    module_slug = domain_to_module[domain_key]
                    self.stdout.write(
                        f"  {tag:20s} → domain:{domain_key:15s} "
                        f"→ module:{module_slug} ✓"
                    )
                else:
                    errors.append(
                        f"Builder '{tag}': domain_key '{domain_key}' "
                        f"has no module mapping in catalog"
                    )
                    self.stdout.write(self.style.ERROR(
                        f"  {tag:20s} → domain:{domain_key:15s} "
                        f"→ ✗ NO MODULE MAPPING"
                    ))
        except ImportError as e:
            warnings.append(f"Could not validate builders: {e}")

        # ── Report ──
        self.stdout.write(f"\n{'=' * 60}")

        if warnings:
            self.stdout.write(self.style.WARNING(
                f"\n  Warnings ({len(warnings)}):"
            ))
            for w in warnings:
                self.stdout.write(self.style.WARNING(f"    ⚠ {w}"))

        if errors:
            self.stdout.write(self.style.ERROR(
                f"\n  Errors ({len(errors)}):"
            ))
            for e in errors:
                self.stdout.write(self.style.ERROR(f"    ✗ {e}"))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\n  ✓ No errors — catalog is compliant"
            ))

        self.stdout.write(f"\n{'=' * 60}\n")

        # CI mode
        if options['check'] and errors:
            self.stderr.write(self.style.ERROR(
                f"audit_modules --check: {len(errors)} error(s) found"
            ))
            raise SystemExit(1)
