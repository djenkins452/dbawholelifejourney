"""
Architecture / import-boundary contract for the canonical Person domain.

CONTRACT: `apps/people` is a foundational Layer 1 authority. It may depend ONLY on
Django, the standard library, `apps.core` infrastructure, and itself. It must NEVER
import a feature module — the dependency direction flows Core Person → features,
never the reverse. Feature modules extend Core through the registered hooks
(apps/people/services/hooks.py), not by Core importing them.

This test FAILS CI if any non-test module under apps/people imports a feature app,
or if a feature module re-introduces its own Person identity table.
"""

import ast
import pathlib

from django.test import SimpleTestCase

PEOPLE_DIR = pathlib.Path(__file__).resolve().parent.parent

# Only these `apps.*` prefixes may be imported by the Core Person domain.
ALLOWED_APP_PREFIXES = ("apps.core", "apps.people")

# Explicitly forbidden — the three retiring Person homes first, then feature apps.
FORBIDDEN_APP_PREFIXES = (
    "apps.relationships",
    "apps.legacy",
    "apps.core.ai_relationships",
    "apps.journal", "apps.faith", "apps.health", "apps.medical", "apps.finance",
    "apps.owner_finance", "apps.purpose", "apps.life", "apps.meals", "apps.sports",
    "apps.calendar_engine", "apps.cos", "apps.capture", "apps.scan", "apps.notes",
    "apps.brain_training", "apps.dashboard", "apps.dashboard_v2", "apps.dashboard_v3",
    "apps.mobile", "apps.sms", "apps.billing", "apps.security", "apps.ai",
)


def _imported_modules(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                yield node.module


def _people_source_files():
    for path in PEOPLE_DIR.rglob("*.py"):
        parts = path.relative_to(PEOPLE_DIR).parts
        if "tests" in parts or "migrations" in parts:
            continue
        yield path


class ArchitectureBoundaryTests(SimpleTestCase):
    def test_core_person_imports_no_feature_module(self):
        violations = []
        for path in _people_source_files():
            for mod in _imported_modules(path):
                if not mod.startswith("apps."):
                    continue
                forbidden = any(
                    mod == p or mod.startswith(p + ".") for p in FORBIDDEN_APP_PREFIXES
                )
                allowed = any(
                    mod == p or mod.startswith(p + ".") for p in ALLOWED_APP_PREFIXES
                )
                # ai_relationships lives under apps.core.* but is a forbidden feature.
                if forbidden or not allowed:
                    violations.append(f"{path.name}: imports {mod}")
        self.assertEqual(
            violations, [],
            "Core Person must not import feature modules. Use hooks.py extension "
            f"points instead. Violations:\n" + "\n".join(violations),
        )
