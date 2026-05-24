"""
Isolation tests — enforce the hard module boundary between Journey and the
existing reading-plan system.

Per spec §2, Journey code must not import ReadingPlanTemplate, ReadingPlanDay,
UserReadingPlan, UserReadingProgress, ReadingPlanAssessment, or anything else
from `apps.faith.models`.

Implementation note: uses Python's `ast` module to inspect only *code*
references — imports, names, attribute accesses — not docstrings, comments,
or string literals. This way the spec doc and the model docstring can
legitimately reference the forbidden names for documentation purposes
without tripping the test.
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase


JOURNEY_ROOT = Path(__file__).resolve().parent.parent  # apps/faith/journey/


def _journey_python_files():
    """All Python source files under apps/faith/journey/, excluding migrations and this test."""
    files = []
    for p in JOURNEY_ROOT.rglob("*.py"):
        if "migrations" in p.parts:
            continue
        if p.name == "test_isolation.py":
            continue
        files.append(p)
    return files


# The four annotation models are the documented safe carve-out (see spec §2):
# reference-keyed, per-user, not coupled to reading plans. Importing these from
# apps.faith.models is explicitly allowed.
ALLOWED_FAITH_MODELS = {
    "BibleHighlight",
    "BibleBookmark",
    "BibleStudyNote",
    "SavedVerse",
    "BIBLE_TRANSLATION_CHOICES",  # constant used to align translation choices
}

# Reading-plan symbols — always forbidden.
FORBIDDEN_READING_PLAN_SYMBOLS = {
    "ReadingPlanTemplate",
    "ReadingPlanDay",
    "UserReadingPlan",
    "UserReadingProgress",
    "ReadingPlanAssessment",
    "UserAssessmentResponse",
}


def _find_forbidden_imports(tree: ast.AST) -> list[str]:
    """Return forbidden imports from apps.faith.models.

    Allows imports of the four documented annotation models
    (BibleHighlight, BibleBookmark, BibleStudyNote, SavedVerse) and
    BIBLE_TRANSLATION_CHOICES. Anything else imported from
    apps.faith.models is an isolation violation.
    """
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "apps.faith.models":
                for alias in node.names:
                    if alias.name not in ALLOWED_FAITH_MODELS:
                        offenders.append(
                            f"from apps.faith.models import {alias.name} "
                            f"(only {sorted(ALLOWED_FAITH_MODELS)} are allowed)"
                        )
            elif node.module == "apps.faith":
                for alias in node.names:
                    if alias.name == "models":
                        offenders.append("from apps.faith import models (use specific imports)")
            elif node.module and node.module.startswith("apps.faith.") and node.module not in {"apps.faith.journey"}:
                # Allow imports from journey itself; flag deeper imports into other faith submodules.
                if not node.module.startswith("apps.faith.journey"):
                    # Block imports from apps.faith.services, apps.faith.engagement, etc.
                    if node.module not in {"apps.faith.models"}:  # already handled above
                        offenders.append(f"from {node.module} import ... (not allowed for isolation)")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "apps.faith.models":
                    offenders.append("import apps.faith.models (use specific imports)")
    return offenders


def _find_forbidden_symbol_uses(tree: ast.AST) -> list[str]:
    """Return forbidden reading-plan symbols used as code identifiers in this AST.

    Only inspects Name and Attribute nodes — does NOT look at string contents,
    docstrings, or comments. The spec doc and docstrings may legitimately
    reference these names for documentation purposes.
    """
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_READING_PLAN_SYMBOLS:
            offenders.append(f"Name reference: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_READING_PLAN_SYMBOLS:
            offenders.append(f"Attribute reference: .{node.attr}")
    return offenders


class JourneyIsolationTests(SimpleTestCase):
    """Enforce the module boundary documented in CLAUDE_WALKING_WITH_GOD.md §2."""

    def test_no_reading_plan_imports_in_journey(self):
        offenders = []
        for path in _journey_python_files():
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for bad in _find_forbidden_imports(tree):
                offenders.append(f"{path.relative_to(JOURNEY_ROOT.parent.parent.parent)}: {bad}")
        self.assertEqual(
            offenders, [],
            "Journey code must not import from apps.faith.models. "
            "See docs/CLAUDE_WALKING_WITH_GOD.md §2. Offenders:\n" + "\n".join(offenders),
        )

    def test_no_reading_plan_symbol_uses_in_journey(self):
        offenders = []
        for path in _journey_python_files():
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for bad in _find_forbidden_symbol_uses(tree):
                offenders.append(f"{path.relative_to(JOURNEY_ROOT.parent.parent.parent)}: {bad}")
        self.assertEqual(
            offenders, [],
            "Journey code must not reference reading-plan model symbols as identifiers. "
            "Build journey-native models instead. Offenders:\n" + "\n".join(offenders),
        )
