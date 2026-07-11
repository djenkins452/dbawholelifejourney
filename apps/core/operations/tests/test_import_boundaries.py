"""
WLJ Operations — permanent import-boundary contract (WLJ_OPERATIONS_VISION.md §11).

CI-enforceable assertions of the frozen one-way arrows:
  * ``ai_observability/`` (truth) MUST NEVER import ``operations/`` (action).
  * ``operations/`` (action) MUST NEVER import Chief-of-Staff reasoning /
    conversation / Current-Context reasoning / LLM orchestration / prompt
    composition / model-interface code.
  * Chief-of-Staff code MUST NEVER import the recovery internals of ``operations/``.

These make Principles 13/14 (bidirectional independence) structural, not
disciplinary. AST-scans import statements only (no execution).
"""
from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[4]
APPS_DIR = REPO_ROOT / "apps"
OBS_DIR = APPS_DIR / "core" / "ai_observability"
OPS_DIR = APPS_DIR / "core" / "operations"

# CoS-reasoning module prefixes the ACTION package may never import.
FORBIDDEN_FROM_OPERATIONS = (
    "apps.ai.personal_assistant",
    "apps.ai.assistant_intelligence",
    "apps.ai.proactive_checkins",
    "apps.ai.intent_service",
    "apps.ai.action_handlers",
    "apps.core.ai_orchestrator",
    "apps.core.ai_state",
    "apps.core.model_interface",
    "apps.core.current_context",
)

# Recovery internals the Chief of Staff may never import (it consumes only the
# composed Operations Truth surface).
OPERATIONS_RECOVERY_INTERNALS = (
    "apps.core.operations.recovery",
    "apps.core.operations.models",
    "apps.core.operations.tasks",
)


def _imported_modules(path: Path):
    """Yield (lineno, dotted_module) for every import in a file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.lineno, node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


class OperationsImportBoundaryTests(SimpleTestCase):
    def test_scanner_finds_files(self):
        """Guard against a vacuous pass (moved tree / bad glob)."""
        self.assertGreater(len(list(OPS_DIR.rglob("*.py"))), 3)
        self.assertGreater(len(list(OBS_DIR.rglob("*.py"))), 5)

    def test_observability_never_imports_operations(self):
        """Truth never imports action."""
        violations = []
        for path in OBS_DIR.rglob("*.py"):
            for lineno, mod in _imported_modules(path):
                if mod == "apps.core.operations" or mod.startswith("apps.core.operations."):
                    violations.append(f"{_rel(path)}:{lineno} → {mod}")
        self.assertEqual(
            violations, [],
            "ai_observability (truth) imported operations (action) — forbidden by "
            "§11. Publish/consume via a cache key instead:\n" + "\n".join(violations),
        )

    def test_operations_never_imports_cos_reasoning(self):
        """Action never imports Chief-of-Staff reasoning."""
        violations = []
        for path in OPS_DIR.rglob("*.py"):
            for lineno, mod in _imported_modules(path):
                if any(mod == f or mod.startswith(f + ".") for f in FORBIDDEN_FROM_OPERATIONS):
                    violations.append(f"{_rel(path)}:{lineno} → {mod}")
        self.assertEqual(
            violations, [],
            "operations (action) imported Chief-of-Staff reasoning — forbidden by "
            "§11 (Principles 13/14):\n" + "\n".join(violations),
        )

    def test_cos_never_imports_operations_recovery_internals(self):
        """The Chief of Staff never reaches into recovery internals."""
        violations = []
        ai_dir = APPS_DIR / "ai"
        for path in ai_dir.rglob("*.py"):
            if "/tests/" in path.as_posix() or path.name.startswith("test_"):
                continue
            for lineno, mod in _imported_modules(path):
                if any(mod == f or mod.startswith(f + ".") for f in OPERATIONS_RECOVERY_INTERNALS):
                    violations.append(f"{_rel(path)}:{lineno} → {mod}")
        self.assertEqual(
            violations, [],
            "Chief-of-Staff code imported operations recovery internals — it may "
            "consume only composed Operations Truth (§11):\n" + "\n".join(violations),
        )
