"""
CoS Naming Boundary — Enforcement tests.

FAIL if the hardcoded persona name "Beth" appears in global content
(fixtures, templates, help) where it should be "Chief of Staff".

Allowed exceptions:
- Biblical references (Bethlehem, Bethany, Bethesda, Bethune)
- Spouse keyword detection (lowercase "beth" in keyword lists)
- Historical load_initial_data function names / log messages
- Test files (test data may use any name)
- Migration files
- Documentation files (docs/) — internal, not user-facing
"""

import os
import re
import unittest

from django.test import SimpleTestCase

from apps.core.cos_naming import CoSNaming

# Directories that contain global/user-facing content
GLOBAL_CONTENT_DIRS = [
    'apps/core/fixtures',
    'apps/help/fixtures',
    'templates',
]

# Files/patterns to skip
SKIP_PATTERNS = [
    '/tests/',
    '/migrations/',
    '__pycache__',
    '.pyc',
]

# Allowed "Beth" substrings (biblical, team names, etc.)
ALLOWED_PATTERNS = re.compile(
    r'Beth(?:lehem|any|esda|une|page|el\b)',
    re.IGNORECASE,
)


class TestCoSNamingHelper(SimpleTestCase):
    """Test the CoSNaming helper itself."""

    def test_system_constant(self):
        self.assertEqual(CoSNaming.SYSTEM, "Chief of Staff")

    def test_display_with_custom_name(self):
        class FakePrefs:
            cos_display_name = "Max"

        class FakeUser:
            preferences = FakePrefs()

        self.assertEqual(CoSNaming.display(FakeUser()), "Max")

    def test_display_with_empty_name(self):
        class FakePrefs:
            cos_display_name = ""

        class FakeUser:
            preferences = FakePrefs()

        self.assertEqual(CoSNaming.display(FakeUser()), "Chief of Staff")

    def test_display_with_no_preferences(self):
        class FakeUser:
            pass

        self.assertEqual(CoSNaming.display(FakeUser()), "Chief of Staff")

    def test_display_with_whitespace_name(self):
        class FakePrefs:
            cos_display_name = "   "

        class FakeUser:
            preferences = FakePrefs()

        self.assertEqual(CoSNaming.display(FakeUser()), "Chief of Staff")


class TestBethDoesNotLeakIntoGlobalContent(SimpleTestCase):
    """Scan global content directories for hardcoded 'Beth' persona name."""

    def test_no_beth_in_global_content(self):
        """FAIL if 'Beth' appears in fixtures, templates, or help content."""
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )

        violations = []

        for content_dir in GLOBAL_CONTENT_DIRS:
            full_dir = os.path.join(project_root, content_dir)
            if not os.path.isdir(full_dir):
                continue

            for root, _dirs, files in os.walk(full_dir):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, project_root)

                    # Skip excluded patterns
                    if any(skip in rel_path for skip in SKIP_PATTERNS):
                        continue

                    # Only check text files
                    if not filename.endswith(('.json', '.html', '.txt', '.md')):
                        continue

                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            for line_num, line in enumerate(f, 1):
                                # Find "Beth" (case-sensitive, standalone word)
                                matches = re.finditer(r'\bBeth\b', line)
                                for match in matches:
                                    # Check if it's an allowed pattern
                                    start = max(0, match.start() - 4)
                                    end = min(len(line), match.end() + 10)
                                    context = line[start:end]
                                    if ALLOWED_PATTERNS.search(context):
                                        continue
                                    violations.append(
                                        f"  {rel_path}:{line_num}: "
                                        f"{line.strip()[:120]}"
                                    )
                    except (UnicodeDecodeError, PermissionError):
                        continue

        if violations:
            self.fail(
                f"Found {len(violations)} 'Beth' reference(s) in global content. "
                f"Use 'Chief of Staff' instead:\n"
                + "\n".join(violations[:20])
            )
